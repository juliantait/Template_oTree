# Hosting an oTree study on Railway

Verified workflow, first used for `Experts/exp_pilots` on 2026-08-14 (live at
`exp-pilots-production.up.railway.app`). Audience: bossman or any agent putting an
oTree project from this template onto Railway. Update this file when the workflow
improves. Companion for the recruitment side:
[`hosting_prolific.md`](./hosting_prolific.md).

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

## Agent autonomy: what the token gets you and where a human is unavoidable

With a project token **and an already-created project**, an agent can go end to
end on its own: deploy the code, create the service, set env vars, generate the
public domain, bind the session, and run the crash rehearsal. It **cannot** create
the project or the Postgres (account owner, in the dashboard), and cannot do the
custom-domain Cloudflare DNS step (a human, and only if a custom domain is chosen;
the generated domain avoids it). See the `HUMAN STEP` markers below.

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

GraphQL endpoint: `https://backboard.railway.app/graphql/v2` (the
`backboard.railway.com` host is an equivalent alias that serves the identical API
and also works, and is what the tool-guide source used, so either is fine if you
meet `.com` in the wild), header
`Project-Access-Token: <token>`, POST a `{"query": ..., "variables": ...}` JSON
payload **with curl** — python urllib gets Cloudflare 403 (error 1010). Pattern:
write the payload to a JSON file, post it with a small curl script. IDs needed in
payloads (projectId, environmentId, serviceId) come from `railway status` and the
`serviceCreate`/deploy responses.

## What a project token CANNOT do (so you attempt, then verify)

A project token is scoped to one project's services. Three operations you might
reach for return **`Not Authorized`**, and the point is the consequence, not the
list:

- `serviceUpdate` (renaming a service).
- `serviceDomainAvailable` (checking whether a domain name is free).
- creating a new **project** (and anything touching the account or another
  project).

Those need an **account token**, which is an account-owner operation in the
dashboard, not something a project token can do:

> **HUMAN STEP (no API for a project token).** Creating the project, and any
> account-scoped action, is done by the account owner in the Railway dashboard.
> A fresh agent cannot self-serve these with the project token it was handed.

The one that bites is `serviceDomainAvailable`. **You cannot check a name is free
before taking it,** so the workflow is never check-then-act. It is always
**attempt, then verify** (next section).

## Attempt, then verify: every Railway mutation

**A Railway mutation's return value is not evidence it did anything.** The proven
case: `serviceDomainUpdate` **returns `true` even when the requested name is
already taken and nothing changes.** A create can likewise report success against
a name you do not actually hold.

So make this a rule for every state-changing call, not just domains:

1. Run the mutation.
2. **Re-query the real state**, e.g. `domains { serviceDomains { domain } }`,
   or the `deployments`/`variables` query for what you changed.
3. **Curl the host** for a `200` where a domain or deploy is involved.

Never trust the mutation's own boolean. This is the same discipline as
"Verifying a deploy actually shipped" below and the crash rehearsal: a green
signal from the API is a claim, not a fact, and the only fact is the re-queried
state and the live host answering.

## Domains

- Generated domains are a **single label**: `<service>-production.up.railway.app`
  works, but `a.b.up.railway.app` fails TLS, because the wildcard cert covers one
  level only. Do not build a two-label generated host.
- `serviceDomainCreate` / `serviceDomainUpdate` are attempt-then-verify (above):
  re-query `serviceDomains` and curl the host, do not trust the return.
- **Custom domain:** Railway's cert issuance **fails while Cloudflare proxies the
  record.** Add the DNS record **grey-clouded (proxy off, DNS-only)**, let the
  cert issue, then turn the proxy back on if you want it (Cloudflare SSL mode must
  be **Full (strict)**).

  > **HUMAN STEP (no API).** The DNS record and its grey-cloud/orange-cloud
  > toggle live in the DNS provider's dashboard (Cloudflare), not in Railway. A
  > custom-domain deploy stalls here silently (the cert simply never issues)
  > unless a person sets the record DNS-only until it lands.

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

## Deploy ORDER for a schema-changing build (order is load-bearing)

When a build changes the database schema (a rounds change, a new model field, a
page-sequence change), the reset must land **before** the new code boots, not
after. Deploying the code first guarantees one boot against an incompatible
database: the container dies, **Railway emails the account owner "Deploy
Crashed"**, and the app **502s** until the reset lands. Correct order:

1. `variableUpsert` `RESET_DB=1`.
2. `railway up`. The new build's **first** boot already resets, so it never
   meets the incompatible schema.
3. `variableDelete` `RESET_DB`.
4. Redeploy.

**Step 3 is not optional.** Railway restarts containers on its own, and a restart
with `RESET_DB` still set **destroys collected data**. Deleting the variable is
what stops the next spontaneous restart from wiping a live study.

Two guardrails from `CLAUDE.md` still bind here: `RESET_DB=1` is the **only**
deliberate wipe (the boot guard leaves a populated database alone otherwise), and
**`NUM_ROUNDS` is fixed at import, and a rounds or page-sequence change must never
be deployed over a live session at all.** A schema-changing deploy is for a study
between sessions, never one mid-flight.

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
boot banner lists what is still placeholder).

**Launch sequence — order is load-bearing:** codes committed → deploy → **bind a
FRESH session**. A session's config is frozen at creation, so any session created
before the codes commit keeps the placeholder frozen inside it: its completers
get sent to `cc=<placeholder>` unpaid while the boot banner reads clean (it only
inspects today's settings). Never reuse a pre-codes session, however tempting.
Note the boot-time room bind only verifies an existing binding — it will not
replace one — so binding the fresh session is an explicit manual step; verify via
`/api/rooms` that the bound `session_code` is NEW. `screenout_return_url` is a
plain URL, not a code: it must be ABSOLUTE (`https://…`) — a relative value
silently loops screened-out phones back into the study (found by live fuzzing
2026-08-14). Export data periodically from the
admin panel during the run. After the study: export, then delete the app service
(keep Postgres briefly if the data should stay live, then delete it too).
