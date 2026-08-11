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
# context, and the container creates its own at /app/data/db.sqlite3 on first
# boot (see CMD). Mount that directory as a volume to keep participant data
# across container replacements:  -v <study>-db:/app/data
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
RUN pip install --no-cache-dir otree==6.0.15

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
#   1. keep the sqlite file under /app/data and symlink /app/db.sqlite3 at it, so
#      a volume mounted on /app/data preserves it. The symlink covers both ways
#      oTree 6 can resolve the sqlite path (settings.DATABASES' absolute
#      /app/db.sqlite3, and the literal ./db.sqlite3 it opens relative to the
#      process CWD, which is /app).
#   2. initialise the database ONLY when there is none, or when RESET_DB=1 is
#      passed explicitly. A restart must never wipe participant data.
#   3. `exec` the production server, so it replaces the startup shell instead of
#      running as its child and `docker stop`'s SIGTERM reaches the server.
# PATH is set explicitly because prodserver spawns `otree timeoutsubprocess` by
# name and dies at boot if it is not resolvable.
CMD bash -c ' \
    set -euo pipefail; \
    export PATH="/usr/local/bin:$PATH"; \
    mkdir -p /app/data; \
    ln -sf /app/data/db.sqlite3 /app/db.sqlite3; \
    if [ "${RESET_DB:-0}" = "1" ] || [ ! -f /app/data/db.sqlite3 ]; then \
        rm -f /app/data/db.sqlite3; \
        otree resetdb --noinput; \
    fi; \
    exec otree prodserver 0.0.0.0:"${PORT:-8101}" \
'
