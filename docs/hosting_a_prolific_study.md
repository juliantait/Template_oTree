# Hosting an online (Prolific) study — reference, not machinery

**Scope limit, stated first because it is the point of this file.**

- Managed hosting is relevant **only to an online study**, in practice a Prolific
  one. **A lab study needs none of it** — it runs on the lab machine or a local
  server, and nothing on this page applies.
- **This repository deliberately contains no deployment architecture.** No
  Railway config, no `railway.json`, no Procfile, no deploy scripts, no CI, no
  provider account settings. Nothing here makes the repo deployable, and that is
  a decision, not an omission (`DECISIONS.md`).
- This page is a **written record of what such a deploy needs**, so it can be
  looked up and implemented if and when somebody chooses to. If you find yourself
  turning it into a config file, that is the line — stop, and raise it instead.

The one thing that IS in the image is data safety, and it is there for a
different reason. See "What is already in the image, and why" below.

## What a hosted Prolific deploy needs

1. **A container host that builds the existing `Dockerfile`.** The image is
   self-contained: a pinned oTree, the code, and a Postgres driver. Nothing in it
   is provider-specific, which is what keeps this repo portable.
2. **A managed Postgres**, and its connection string handed to the container as
   `DATABASE_URL`. Do not run an online study on the sqlite file: on a managed
   platform the container filesystem is usually ephemeral, so the file — and
   every participant in it — disappears on the next restart.
3. **The environment variables that make it a real study**, none of which are
   baked into the image on purpose:
   - `OTREE_PRODUCTION=1` — turns DEBUG off. Without it, participants get skip
     buttons and visible quiz answers.
   - `OTREE_AUTH_LEVEL=STUDY` plus `OTREE_ADMIN_PASSWORD` and `OTREE_REST_KEY` —
     otherwise the admin and `/demo` are open to anyone who finds the URL.
   - `OTREE_SECRET_KEY` — the dev fallback must not survive contact with the
     internet.
   - `PORT` if the platform assigns one.
4. **An HTTPS domain**, which managed platforms provide. The image already trusts
   the proxy's `X-Forwarded-Proto` (`FORWARDED_ALLOW_IPS=*`); without that oTree
   builds `http://` links on an `https://` site and redirects and assets break.
5. **The Prolific wiring** — study URL, completion codes, and the return URL for
   a screened-out participant — which is study configuration, not hosting. It is
   in `prolific/Prolific_running.md` and guarded by
   `scripts/prelaunch_check.py`.
6. **A deploy that maps to an exact commit**, so you can say which code a given
   participant saw. A private repo holding only the experiment is the usual
   shape; the research monorepo need never be visible to the host.

## What `DATABASE_URL` and the Postgres driver are for

`DATABASE_URL` is the **only** thing that chooses the database backend. oTree 6
reads it directly (`os.getenv('DATABASE_URL', 'sqlite:///db.sqlite3')`); unset
means the sqlite file. The `DB_NAME`/`DB_HOST` block in `settings.py` looks like
it selects Postgres and **does not** — oTree 6 dropped Django and never reads
`DATABASES`. Setting those and expecting Postgres gets you sqlite, silently
(`postgres_assumptions.md`).

`psycopg2-binary` is the driver that lets Python speak to Postgres at all.
`pip install otree` ships no database driver beyond sqlite's standard-library
module, so without it every Postgres URL fails at connection time.

## What the boot guard protects against

The container will not initialise a database that already has tables in it. That
sounds obvious; it was not. The guard used to ask "is there a sqlite file?" as a
proxy for "is this database new?" — a proxy that is only true when the database
IS that file. Pointed at a managed Postgres, the file never exists, so the
condition was true on every boot and `otree resetdb` — which drops every table it
finds — ran against the live database on **every container restart**, silently,
with no error in the log. On a platform with an ephemeral filesystem that is
total data loss on every restart, discovered after a session.

It now asks the real question — *does this database already contain oTree's
tables?* — through oTree's own engine and oTree's own table names, so it means
the same thing on sqlite and Postgres. Behaviour worth knowing before your first
deploy:

- An **empty** database is initialised. A database with oTree's tables is left
  alone, restart after restart.
- A database that **does not answer yet** is retried for about a minute
  (`DB_WAIT_ATTEMPTS` × `DB_WAIT_SECONDS`, default 30 × 2s) — a managed Postgres
  is often not accepting connections at the instant the container starts.
- If it still cannot tell, **the container refuses to start** rather than
  initialising. That is deliberate: "I cannot see the database" and "the database
  is empty" are different answers, and treating the first as the second is what
  destroys data. A container that will not start is a line in the logs; a
  container that wipes a live study is a lost session.
- `RESET_DB=1` is the only deliberate wipe, on any backend.

So a refusal to boot is usually your connection string, not your build.

## Caveats we could not test

Stated plainly because someone will hit them on a first deploy and should know
they were never exercised. The Postgres work was verified against a **local**
PostgreSQL 16 over plain TCP:

- **TLS (`?sslmode=require`)** — most managed providers require it. Untested
  here. If it is misconfigured the probe cannot connect, so the container refuses
  to boot; it fails toward refusing, not toward wiping.
- **Connection poolers** (PgBouncer and the like, which several platforms put in
  front of Postgres by default). Untested, and the likeliest of these to behave
  differently — a pooler can refuse or rewrite a connection, and in transaction
  pooling mode it can break assumptions a long-lived engine makes. If a deploy
  behaves oddly, try the direct connection string before anything else.
- **Docker itself was never run** in the work that produced the guard: no image
  build, no container boot. The startup command was executed directly with paths
  rewritten, and syntax-checked as the shell would parse it.
- **The `psycopg2-binary` pin was never installed in an image build**, only in a
  virtualenv alongside the same oTree version.

## The gap to know about before a hosted launch

**There is no upgrade-path check for a Postgres deployment.**
`scripts/predeploy_check.sh` — the gate that catches "this new build breaks for
participants who started before it" — is sqlite-only by design, and the
documented way to feed it a database (`docker cp` the sqlite file) does not exist
on Postgres. A hosted study is currently deployed without that gate. It is
honest about it (it reports `THE UPGRADE PATH WAS NOT TESTED`) but it cannot
cover you. `postgres_assumptions.md` has the full item and what closing it would
take; the short version is a container boot test first, then a Postgres fixture,
then a `pg_dump`-into-a-throwaway-database mode for the check.

Until that exists, the practical mitigation for an online study is the one oTree
forces anyway: **do not deploy new code over a running session.** Let the session
finish, deploy, then open the next one.

## What is already in the image, and why

`psycopg2-binary` and the Postgres-aware boot guard are in the image **for data
safety on any managed backend — not because Railway or any other provider has
been adopted.** They are there because the moment somebody points `DATABASE_URL`
at a managed database, the old file-existence guard would have destroyed it, and
because a guard that cannot connect refuses to boot — so shipping the guard
without the driver would have meant every Postgres deploy failing at 100% while
looking like a database problem. Both are about not losing participant data. They
commit this template to nothing.

## Prior art

One real deploy has been done from a project built on this template (Railway,
2026-08-14). The step-by-step — deploy-repo export, the dashboard steps, the
environment variables set in practice — was written up as
`skills_claude/hosting_railway.md`. **That file is untracked**, so it is on the
machine that made it and not in a copy of this template. If a hosted deploy is
going to happen more than once, that write-up is the thing to bring in here and
generalise; this page is the durable part.
