# Hosting an oTree study on Railway

Verified workflow, first used for `Experts/exp_pilots` on 2026-08-14 (live at
`exp-pilots-production.up.railway.app`). Audience: bossman or any agent putting an
oTree project from this template onto Railway. Update this file when the workflow
improves.

> **Scope of this file: the Railway PROCEDURE — tokens, CLI, GraphQL, the deploy
> repo, study day.** What a hosted deploy needs in general, what `DATABASE_URL`
> and the boot guard do, the TLS/pooler caveats, and the gap that there is no
> upgrade-path check for Postgres are in `docs/hosting_a_prolific_study.md`,
> which is written for the researcher rather than the agent. Do not restate that
> file here; fix it there and link.
>
> **Two notes where this file describes `exp_pilots`, not this template:** the
> resetdb guard lives in `exp_pilots`' `start.sh`, whereas in this template it is
> the Dockerfile `CMD` calling `scripts/db_state.py`; and this template's
> `scripts/start.sh` is a HOST-SIDE room-binding script run against an already
> running server — it is not invoked at container boot and does not handle
> `PORT`. `PORT` is honoured by the Dockerfile `CMD`.

## Why Railway

Managed host, ~$5–10 for a whole ~160-participant study (Hobby plan, usage-billed).
Reads the project's existing `Dockerfile` directly, one-click managed Postgres,
automatic HTTPS domain, browser dashboard with logs + restart. Full comparison of
alternatives: `Experts/reports/hosting_options.md` (local only — a document in the
research monorepo this template was extracted from; not in a copied study).
TreeHost is the zero-devops alternative (zip upload, free tier) but has no
CLI/API — dashboard only.

## The shape

1. **Dedicated deploy repo** — a private GitHub repo holding ONLY the experiment,
   made with `git subtree split` so it keeps the experiment's real commit history:
   ```sh
   cd <monorepo>            # e.g. Experts/
   git subtree split --prefix=<app_folder> -b <app>-export
   git push https://github.com/<your-account-or-org>/<deploy-repo>.git <app>-export:main
   ```
   Re-run both commands after every commit that should deploy (delete the branch
   first: `git branch -D <app>-export`). The deploy repo is a derived export —
   never develop against it. Rationale: Railway (a third party) never sees the
   research monorepo, and every deploy maps to an exact commit.
2. **Railway project** — Julian creates it in the dashboard (account, card,
   Hobby plan) and adds the Postgres there (`New -> Database -> PostgreSQL`;
   ONE, not two). Databases cannot be created with a project token.
3. **Project token** — the account owner creates it in the dashboard:
   project -> Settings -> Tokens. **Keep it OUTSIDE this repository** — a file
   in a gitignored directory, or your OS keychain. Where exactly is
   site-specific and deliberately not recorded here: this file is tracked and
   ships with every copy of the template, and a durable, precise pointer to
   where an API token lives is useless to any legitimate reader (who has their
   own token, on their own machine) and useful to nobody else you would want
   reading it. Never commit the token itself.

   It is PROJECT-scoped: env var `RAILWAY_TOKEN` (account tokens use
   `RAILWAY_API_TOKEN` instead). A small wrapper script that exports the token
   and calls the CLI keeps it off your shell history and out of every command;
   put that wrapper outside the repo too. Install the CLI without root by
   pointing npm at a prefix you own:
   `npm config set prefix <a-dir-you-own> && npm i -g @railway/cli`.

## What works with a project token, and how

| Action | Route |
|---|---|
| Deploy code | CLI: `railway up --service <name> --detach` from a clean clone of the deploy repo. Julian's decision (2026-08-14): keep this manual — no GitHub auto-deploy; the live study only changes on an explicit deploy |
| Check deploy status | GraphQL `deployments` query |
| Create the app service | GraphQL `serviceCreate` (CLI `add` fails with project tokens) |
| Set env vars | GraphQL `variableCollectionUpsert` (CLI `variables` unusable) |
| Public domain | GraphQL `serviceDomainCreate` -> `<service>-production.up.railway.app` |
| Restart | GraphQL `deploymentRestart(id)` |
| RAM/CPU metrics | GraphQL `metrics(serviceId, startDate, measurements: [MEMORY_USAGE_GB, CPU_USAGE])` |

GraphQL endpoint: `https://backboard.railway.app/graphql/v2`, header
`Project-Access-Token: <token>`, POST a `{"query": ..., "variables": ...}` JSON
payload **with curl** — python urllib gets Cloudflare 403 (error 1010). Pattern:
write the payload to a JSON file, post it with a small curl script. IDs needed in
payloads (projectId, environmentId, serviceId) come from `railway status` and the
`serviceCreate`/deploy responses.

## Env vars for the app service

```
OTREE_AUTH_LEVEL=STUDY
OTREE_ADMIN_PASSWORD=<strong password>
OTREE_SECRET_KEY=<random>
OTREE_REST_KEY=<random>          # start.sh uses it to verify/bind the room session
DATABASE_URL=${{Postgres.DATABASE_URL}}   # reference variable, never paste creds
OTREE_PRODUCTION=1               # debug off; omit during smoke tests to keep skip buttons
```
Never set `RESET_DB` as a standing variable. `PORT` is injected by Railway and
`start.sh` honours it. `FORWARDED_ALLOW_IPS=*` is already in the template
Dockerfile (needed behind any TLS proxy).

## Hard-won gotchas

- **The resetdb wipe trap.** start.sh's old guard reset the DB when the sqlite
  file was missing — with `DATABASE_URL` set that file never exists, so every
  boot wiped Postgres. Fixed 2026-08-14 (Experts `79d49c2`; this template's
  `9d14738`): reset only on explicit `RESET_DB=1` or a database with no `otree_*`
  tables; fail loud when the DB is unreachable. Any project built from an older
  template snapshot MUST take this fix before Postgres hosting.
  Two refinements in this template's version, worth knowing at a first deploy:
  a database holding tables that are NOT oTree's is REFUSED rather than reset
  (it is somebody else's schema), and an unreachable database is retried for
  ~60s before the boot is refused, because a managed Postgres frequently is not
  accepting connections at the instant the container starts.
- **Postgres driver.** The Dockerfile needs `psycopg2-binary` alongside otree,
  or the app dies on connect. **Already done in this template** (pinned
  `psycopg2-binary==2.9.12`); the note stands for any project on an older
  snapshot.
- **`railway up` can transiently 500** ("Failed to upload", deployment shows
  FAILED with no build attached). Just retry after ~45s; it clears.
- **Variable changes trigger their own redeploy** — set vars, then confirm the
  new deployment reaches SUCCESS before judging anything.
- **Session binding**: start.sh binds the configured session to the room at boot
  (fail-loud). Verify with the REST API:
  `curl -H "otree-rest-key: <key>" https://<domain>/api/rooms`.

## The crash rehearsal (do this before any paid run)

1. Note the bound `session_code` from `/api/rooms`.
2. `deploymentRestart` the live deployment.
3. Confirm the SAME session code afterwards. Same code = data survives restarts.

## Study day

Participant link: `https://<domain>/room/<room_name>?participant_label={{%PROLIFIC_PID%}}`.
Real Prolific completion codes must be committed in settings before launch (the
boot banner lists what is still placeholder). Export data periodically from the
admin panel during the run. After the study: export, then delete the app service
(keep Postgres briefly if the data should stay live, then delete it too).
