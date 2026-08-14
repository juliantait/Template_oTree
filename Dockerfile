# oTree-Template — container image that serves the study.
#
# Deliberately boring: a stock slim Python base, a pinned oTree, no build tools,
# no non-root user gymnastics, no multi-stage tricks. A build failure here costs
# a human a round trip, and every study copied from this template inherits this
# file, so it favours predictability over cleverness.
#
# Build/run commands and the environment variables that matter: see the "Docker"
# section of README.md.
#
# NO DATABASE IS BAKED IN. .dockerignore drops any db.sqlite3 from the build
# context, and with the default (sqlite) configuration the container creates its
# own at /app/data/db.sqlite3 on first boot (see CMD). Mount that directory as a
# volume to keep participant data across container replacements:
#   -v <study>-db:/app/data
# Set DATABASE_URL to run against Postgres instead; the boot guard supports both
# (see CMD), and the Postgres driver is already installed — nothing to add (see
# the psycopg2-binary note above the pip install below for why it is not
# optional).
FROM python:3.12-slim-bookworm

# Unbuffered stdout so `docker logs` shows the prelaunch banner and the server
# log as they happen rather than in blocks; no .pyc files in the image.
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The four apps import nothing outside the standard library except oTree itself
# (`import common` is this repo's own root module). pandas / requests /
# playwright / jinja2 appear only in scripts/, tests/ and the previews
# generator — host-side tooling, not the served study — so they stay out of the
# image. Pinned rather than floating: an oTree minor bump must be a deliberate,
# reviewed change, not something a rebuild picks up silently.
#
# psycopg2-binary is NOT optional even though the default configuration is
# sqlite. `pip install otree` ships no Postgres driver, so without this a
# DATABASE_URL pointing at Postgres cannot be opened by anything — including the
# boot guard below, which would then correctly report "I cannot see the
# database" and correctly refuse to start. A guard whose safe direction is
# triggered by our own missing dependency would fail 100% of Postgres deploys
# while looking like a database problem. The driver costs ~3 MB in an image that
# may never use it; a study that cannot boot on the platform it was deployed to
# costs a session. Binary wheel, so no compiler or libpq-dev in the image.
RUN pip install --no-cache-dir otree==6.0.15 psycopg2-binary==2.9.12

COPY . .

# A study copied from this template may add third-party dependencies; it drops
# a requirements.txt at the root and they are installed here. The template
# itself ships none, so this is a no-op until one exists (an `if` rather than a
# COPY, because a COPY of a file that does not exist fails the build).
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Trust the reverse proxy's X-Forwarded-Proto from any source IP. Behind a
# TLS-terminating front (Cloudflare Tunnel, `tailscale serve`) the request
# reaches the container from the docker gateway address, not 127.0.0.1, so
# without this uvicorn ignores the header and builds absolute http:// links on
# an https site — broken redirects and assets. Baked in so the container is
# correct even if someone forgets the -e flag at run time.
ENV FORWARDED_ALLOW_IPS=*

# Port 8101 is this project's standing test-hosting convention (see README.md
# and MACMINI_HOSTING.md); override with -e PORT=... plus a matching -p.
ENV PORT=8101
EXPOSE 8101

# OTREE_PRODUCTION is deliberately NOT set here. DEBUG is the environment-driven
# axis (unset -> DEBUG on: skip controls and quiz solutions in the browser), and
# the same image must be runnable both ways — a debug clickthrough and a real
# run are one `-e OTREE_PRODUCTION=1` apart. Pass it for anything a participant
# touches. OTREE_AUTH_LEVEL / OTREE_REST_KEY / OTREE_ADMIN_PASSWORD are likewise
# passed at run time, never baked.

# Liveness only: the port accepts a TCP connection. It deliberately does not
# assert on an HTTP status, since a correctly locked-down server answers most
# paths with a redirect to the admin login.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python3 -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('PORT','8101'))), 3).close()"

# Startup, inline so the image needs no entrypoint script of its own:
#   1. keep the sqlite file under /app/data and symlink /app/db.sqlite3 at it,
#      so a volume mounted on /app/data preserves it. The symlink is what makes
#      the volume work at all: oTree 6 opens the RELATIVE name `db.sqlite3` from
#      the process CWD (otree/database.py: DB_FILE), which is /app, so without
#      the link the database would live in the container's own writable layer and
#      vanish with the container. (settings.DATABASES is NOT what decides this —
#      oTree 6 dropped Django and never reads it; see DECISIONS.md.) Harmless
#      under Postgres, where nothing but a stray zero-byte file appears there.
#   2. initialise the database ONLY when it has not been initialised yet, or when
#      RESET_DB=1 is passed explicitly. A restart must never wipe participant
#      data — `otree resetdb` reflects the target database and drop_all()s it
#      (otree/cli/resetdb.py), so "initialise" means "destroy whatever is there".
#      NOTE WHAT THIS BRANCH IS AND IS NOT DOING: oTree builds its own schema on
#      every start — `otree.main.setup()` -> `init_orm()` ->
#      `AnyModel.metadata.create_all(engine)` (otree/database.py:369), which adds
#      missing tables and never drops or alters an existing one. So the
#      initialise branch is belt and braces; the guard's real and only job is
#      NEGATIVE — to stop `resetdb` running against a database that has data in
#      it. That is why refusing when the answer is unclear costs so little.
#   3. `exec` the production server, so it replaces the startup shell instead of
#      running as its child and `docker stop`'s SIGTERM reaches the server.
# PATH is set explicitly because prodserver spawns `otree timeoutsubprocess` by
# name and dies at boot if it is not resolvable.
#
# WHAT THE GUARD ASKS, AND WHY IT DOES NOT ASK ABOUT A FILE
# ---------------------------------------------------------
# It asks scripts/db_state.py one question: DOES THE DATABASE OTREE WILL CONNECT
# TO ALREADY CONTAIN OTREE'S TABLES? That is the question "should I initialise?"
# actually depends on, and it has the same meaning on every backend.
#
# It used to ask `[ ! -f /app/data/db.sqlite3 ]` — "is there a sqlite file?" —
# as a proxy. DO NOT PUT THAT BACK. The proxy is only equivalent to the real
# question when the database IS that file:
#   * Under DATABASE_URL=postgres://... the file never exists, so the condition
#     is TRUE ON EVERY BOOT and every restart runs resetdb against the managed
#     Postgres — silently, with no error in the log. On Railway/Heroku/Fly, where
#     the container filesystem is ephemeral, that is a total data loss on every
#     single restart. Verified against a real Postgres 16: a session row written
#     before the restart was gone after it.
#   * It is not sound for sqlite either. Importing otree.database runs
#     `sqlite3.connect('db.sqlite3')` at module scope — unconditionally, even
#     when DATABASE_URL points at Postgres — which CREATES a zero-byte file. A
#     zero-byte db.sqlite3 is a file that exists and a database that was never
#     initialised, and `-f` cannot tell those apart.
# File existence is a fact about a filesystem; the guard needs a fact about a
# database. See DECISIONS.md ("Boot initialisation is decided by inspecting the
# database, not by a sqlite file") for the full reasoning.
#
# The probe never guesses: it answers `needs-init` only for a database with NO
# tables at all, and exits non-zero (stopping the boot, loudly) when it cannot
# reach the database, when the schema is not oTree's, or when oTree's own table
# registry has changed shape. "I cannot see the database" and "the database is
# empty" are different answers, and collapsing them is exactly how the defect
# above destroys data. RESET_DB=1 remains the explicit, operator-chosen escape
# hatch: it initialises unconditionally and does not consult the probe.
#
# THE FAILURE PATH REFUSES TO BOOT. THIS IS A DELIBERATE CHOICE, NOT AN OVERSIGHT
# ------------------------------------------------------------------------------
# When the probe cannot establish the database's state, the container STOPS. It
# does not fall back to initialising, and it does not fall back to starting the
# server anyway. Whoever meets this refusal will be tempted to make it
# permissive — the container is down, the fix looks like one `|| true`. DO NOT.
#
# The realistic causes are all Postgres connection failures: a managed URL whose
# TLS requirement is unmet (`?sslmode=require`), a connection pooler refusing or
# rewriting the connection, wrong credentials, or a transient network partition.
# EVERY ONE of those is a database that is reachable-in-principle and probably
# FULL OF PARTICIPANT DATA. A permissive failure path turns each of them into
# "looks empty to me" — which is precisely the defect described above,
# reintroduced through the error handler instead of through the condition.
#
# A COLD START IS NOT ONE OF THOSE CAUSES, and must not be treated as one. A
# managed Postgres is very often not accepting connections at the instant the
# container starts — platform starts both at once, database still provisioning,
# pooler not up. So the probe WAITS (DB_WAIT_ATTEMPTS x DB_WAIT_SECONDS, default
# 30 x 2s) for a database that is not answering, and only then calls it
# unanswerable. Refusing is the verdict after waiting, never the first answer;
# without the wait this guard would convert every normal cold start into a
# failed deploy, which is how a safety mechanism gets switched off for being
# annoying. Only "did not answer" is retried — a missing driver or a foreign
# schema is already an answer and fails at once.
#
# The asymmetry that settles it: a container that refuses to start is a line in
# `docker logs` and a study that begins late; a container that initialises on a
# bad guess is a study that is already over and unrecoverable. oTree has no
# migrations and this image ships no backup step, so there is no undo. Refusing
# is also honest about the actual state of affairs — an unreachable database
# means the server could not have served anyone anyway.
#
# If a refusal is a genuine first deploy against a genuinely empty database, the
# answer is not to weaken this path: fix the URL so the probe can see the
# database, or state the intent explicitly with RESET_DB=1.
CMD bash -c ' \
    set -euo pipefail; \
    export PATH="/usr/local/bin:$PATH"; \
    mkdir -p /app/data; \
    ln -sf /app/data/db.sqlite3 /app/db.sqlite3; \
    if [ "${RESET_DB:-0}" = "1" ]; then \
        echo "[boot] RESET_DB=1 — initialising from scratch. ANY EXISTING DATA IS DESTROYED."; \
        case "${DATABASE_URL:-sqlite}" in \
            sqlite*) rm -f /app/data/db.sqlite3 ;; \
            *) echo "[boot] backend is not sqlite; resetdb will drop the tables itself." ;; \
        esac; \
        otree resetdb --noinput; \
    else \
        if ! DB_STATE="$(python3 /app/scripts/db_state.py)"; then \
            echo "[boot] REFUSING TO START — see the message above. No database was modified." >&2; \
            exit 1; \
        fi; \
        echo "[boot] database state: ${DB_STATE}"; \
        if [ "${DB_STATE}" = "needs-init" ]; then \
            otree resetdb --noinput; \
        fi; \
    fi; \
    exec otree prodserver 0.0.0.0:"${PORT:-8101}" \
'
