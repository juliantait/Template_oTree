# Hosting an oTree study on Railway

Verified workflow, first used for `Experts/exp_pilots` on 2026-08-14 (live at
`exp-pilots-production.up.railway.app`). Audience: bossman or any agent putting an
oTree project from this template onto Railway. Update this file when the workflow
improves.

## Why Railway

Managed host, ~$5–10 for a whole ~160-participant study (Hobby plan, usage-billed).
Reads the project's existing `Dockerfile` directly, one-click managed Postgres,
automatic HTTPS domain, browser dashboard with logs + restart. Full comparison of
alternatives: `Experts/reports/hosting_options.md`. TreeHost is the zero-devops
alternative (zip upload, free tier) but has no CLI/API — dashboard only.

## The shape

1. **Dedicated deploy repo** — a private GitHub repo holding ONLY the experiment,
   made with `git subtree split` so it keeps the experiment's real commit history:
   ```sh
   cd <monorepo>            # e.g. Experts/
   git subtree split --prefix=<app_folder> -b <app>-export
   git push https://github.com/juliantait/<repo>.git <app>-export:main
   ```
   Re-run both commands after every commit that should deploy (delete the branch
   first: `git branch -D <app>-export`). The deploy repo is a derived export —
   never develop against it. Rationale: Railway (a third party) never sees the
   research monorepo, and every deploy maps to an exact commit.
2. **Railway project** — Julian creates it in the dashboard (account, card,
   Hobby plan) and adds the Postgres there (`New -> Database -> PostgreSQL`;
   ONE, not two). Databases cannot be created with a project token.
3. **Project token** — Julian: dashboard -> project -> Settings -> Tokens.
   Saved at `MacMini/railway-token.txt` (gitignored). It is PROJECT-scoped:
   env var `RAILWAY_TOKEN` (account tokens use `RAILWAY_API_TOKEN` instead).
   Bossman wrapper: `/home/dev/bin-railway.sh` (exports the token, calls the CLI
   from `/home/dev/.npm-global/bin/railway`; install via
   `npm config set prefix /home/dev/.npm-global && npm i -g @railway/cli`).

## What works with a project token, and how

| Action | Route |
|---|---|
| Deploy code | CLI: `railway up --service <name> --detach` from a clean clone of the deploy repo |
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
  boot wiped Postgres. Fixed 2026-08-14 (Experts `79d49c2`, same shape in this
  template): reset only on explicit `RESET_DB=1` or a database with no `otree_*`
  tables; fail loud when the DB is unreachable. Any project built from an older
  template snapshot MUST take this fix before Postgres hosting.
- **Postgres driver.** The Dockerfile needs `psycopg2-binary` alongside otree,
  or the app dies on connect.
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
