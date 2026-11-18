# Scripts, build and deploy

*Read this when you run or change a script in scripts/, build the Docker image, or deploy.*

## Deploying

`scripts/predeploy_check.sh` boots a candidate build against a **copy of the live
database**, drives an existing mid-flow participant plus a fresh one plus a no-JS
submit, and fails on any 5xx. Run it before every deploy: a fresh install cannot
detect a broken upgrade path.

Run with no database argument (the template's own case — there is no live data
yet) it runs the fresh-install checks only and reports the upgrade path **NOT
TESTED**; that is never a pass for a study that has live sessions, and
`--require-db` turns it into a failure. It does not replace
`scripts/prelaunch_check.py`, which is the static config guard (placeholder
completion codes, DEBUG still on, testing loosenings) — run both.

## Two gates: pre-launch and pre-deploy (they check different things)

|  | `scripts/prelaunch_check.py` | `scripts/predeploy_check.sh` |
|---|---|---|
| **Asks** | is this *configuration* safe to launch? | will the *running study* survive being upgraded to this code? |
| **Kind** | static, config only, no server, instant | dynamic: boots a real `otree prodserver` and drives real HTTP |
| **Catches** | `REPLACE_*` completion codes, `DEBUG` still on, `quiz_verify=False` left in, `OTREE_AUTH_LEVEL` not locked to `STUDY`, a **drifted experimenter dashboard** (renamed `URL_BASE`, a `vars_for_admin_report` that raises, routes that fail to install) | a page that 500s for a participant whose state predates the new code; a missing DB column; a page that 500s with JS-produced hidden fields empty |
| **Run it** | in the target environment, before opening a study to participants | before every deploy that lands on a database with participants in it |

Neither replaces the other: pre-launch cannot detect a broken upgrade path, and
pre-deploy cannot tell you the completion codes are still placeholders.

### Before a deploy: `scripts/predeploy_check.sh`

> ## ⚠️ DEPLOYING THE 2026-08-12 BUILD NEEDS `otree resetdb` — NOT JUST RETIRING SESSIONS
>
> **Read this before deploying this code over any database that predates
> 2026-08-12.** Retiring the in-flight sessions is NOT enough on its own: the
> old rows stay in the database, and the SCHEMA is what has changed.
>
> This build carries a **schema change on top of a page-sequence change**, and
> **oTree has no migrations**:
>
> - `before.Player.prolific_label_conflict` is a real `models.StringField`
>   (`before/__init__.py`) that older databases do not have. **A missing column
>   500s every page that loads that model** — which, since it is on the entry
>   app's Player, is every page a participant sees. Not a degraded feature: a
>   dead study.
> - Six columns were **removed** the same day (`intro.Player.participant_label`,
>   `skiptoquiz`; `outro.Player.selected_round1`, `selected_round2`, `pay1`,
>   `pay2` — see docs/CODEBOOK.md). Leftover columns in an old database are harmless
>   to reads, but they mean the file no longer matches the models either.
> - The **page sequence changed, in both `before` and `intro`**: the
>   tab-monitor agreement page (`TabMonitorAgree`) moved OUT of the end of `intro`
>   and INTO `before`, after the id confirmation, so that the monitor is armed
>   before the instructions and the quiz rather than after them. oTree stores a
>   participant's position as an INDEX into the whole sequence, so every index
>   past the insertion point now names a different page: a participant who was
>   on the quiz would resume somewhere else entirely. This is the case
>   CLAUDE.md's rule covers — **a rounds or page-sequence change must never be
>   deployed over live sessions** — which is why retiring in-flight
>   participants is necessary here as well, and why `resetdb` is the clean
>   answer rather than a hand-migration.
>
> **What to do:** deploy onto a **fresh database** — `otree resetdb` (in
> Docker, `RESET_DB=1` on the container, see the Docker section). That **wipes
> all data**, so export first (`scripts/export_data.py`) and treat every
> participant in the old database as finished.
>
> **The only alternative**, if data must be preserved, is to add the missing
> column by hand before deploying and accept that everyone mid-flow is stranded
> by the sequence change anyway:
>
> ```sql
> ALTER TABLE before_player ADD COLUMN prolific_label_conflict VARCHAR(10000);
> ```
>
> Either way, run `scripts/predeploy_check.sh /tmp/db_live_copy.sqlite3`
> afterwards: it fails with `SCHEMA MISMATCH: COLUMN … is missing` and names the
> column, which is exactly the failure this box exists to stop you meeting in
> production. **A template copied fresh has no live database and none of this
> applies** — it is only about upgrading a study that already has participants.

It tests the **upgrade**, not the install. Two live outages in the pilot study
this template was distilled from had the same root cause: the new code was only
ever tested against a **fresh** database, but both failures could only happen to
a participant whose state **predated** the change —

- a **participant-vars key** old participants never had (and note
  `getattr(participant, 'k', default)` does *not* save you: oTree's vars
  descriptor raises `KeyError`, which the getattr default does not catch), and
- a **session config frozen** before a parameter existed, so
  `session.config['new_param']` raises `KeyError` for every already-running
  session.

A fresh session cannot reproduce either, so bots and fresh-DB HTTP tests are
structurally blind to the whole class. It catches a **third** kind as well: a
MODEL COLUMN this build adds that the live database does not have. oTree has no
migrations, so that is a hard stop until the column is added by hand — see
"Adding a model field to a running study" below.

> **Adding a model field to a running study.** A new `models.*Field` on any
> `Player`/`Group`/`Subsession` is a schema change, and `otree resetdb` (oTree's
> only built-in answer) **wipes the data**. On a live SQLite database, add the
> column instead — for example, the column this template's identity work adds:
>
> ```sql
> ALTER TABLE before_player ADD COLUMN prolific_label_conflict VARCHAR(10000);
> ```
>
> Then re-run `predeploy_check.sh` against the migrated copy and deploy only if
> it passes. (Measured on this change: without the ALTER, checks 2, 4, 5 and 6
> fail and the log names the missing column; with it, all eight pass, including
> resuming a mid-flow participant whose vars predate the new participant fields.
> Participant FIELDS — `screenout_cleared`, `consent_submitted` — need no
> migration at all: they live in the pickled vars blob and read back as their
> default through `participant.vars.get`.) This script boots the candidate build
against a copy of the live database and drives, over real HTTP: an **existing
mid-flow participant** several pages forward, a **fresh participant** entry to
end for a lab-configured *and* a prolific-configured session, and a **no-JS
participant** whose JS-produced hidden fields all post empty — then greps the
server log for 5xx, tracebacks, `KeyError` and `TypeError`. Non-zero exit on any
failure, so it can gate a deploy.

```bash
# with live data (what you run before a real deploy):
docker cp <container>:/app/data/db.sqlite3 /tmp/db_live_copy.sqlite3
scripts/predeploy_check.sh /tmp/db_live_copy.sqlite3

# no live data yet (this template, or a study before its first session):
scripts/predeploy_check.sh                 # DEGRADED: fresh-install checks only
scripts/predeploy_check.sh --require-db    # ... and fail rather than pass degraded

scripts/predeploy_check.sh /tmp/db_live_copy.sqlite3 /path/to/candidate-build
```

**Degraded mode.** With no database copy there is nothing to upgrade *from*, so
the upgrade-path checks report **NOT TESTED** (never PASS) and the summary says
`THE UPGRADE PATH WAS NOT TESTED` in a banner you cannot miss. Use
`--require-db` (or `PREDEPLOY_REQUIRE_DB=1`) in a pipeline for a study that has
live sessions, so a missing database copy fails the deploy instead of quietly
passing.

**The live database is never touched.** The script refuses live-looking paths
outright, then works on its own private temp copy of whatever file it is given,
so even the snapshot you hand it is never modified. Name your study's live
volume or host path in `PREDEPLOY_LIVE_MARKERS` (comma-separated substrings) to
extend that refusal. Other knobs: `PREDEPLOY_PYTHON` (interpreter that has oTree
installed), `--configs a,b` (which session configs to drive), `--debug` (drive
with DEBUG on; the default is the production shape), `--keep` (keep the temp
workdir on success), `PREDEPLOY_END_PAGES` / `PREDEPLOY_RESUME_PAGES` (teach it
about end pages and resume-preference pages a study adds).

## Scripts (`scripts/`)
- `scripts/start.sh` : bind a session to the lab room on boot, **reusing** an
  already-bound session instead of creating a new one each time (which would
  strand in-progress participants). Authenticates REST calls with
  `OTREE_REST_KEY` when `OTREE_AUTH_LEVEL=STUDY`; fails loudly rather than
  leaving the room unbound.

  > **CREED lab sessions are started with a separate tool, the oTree Lab
  > Launcher** — a small pywebview app that lives in its own private repository
  > (forkable on request) and is **not part of this template**. The experimenter
  > picks a lab and its seats; the launcher sets the launch environment
  > (Postgres database, admin login, production mode, the room's seat list, and
  > the lab session number, which lands in the export as
  > `session.config.lab_session`),
  > starts `otree prodserver`, and can append its oTree lab support block —
  > already shipped at the end of `settings.py` — to any project's `settings.py`
  > so the study redirects into the lab while staying completely inert unless the
  > launcher is running. The launcher's code is not in this repo; only the
  > support block it targets is.
- `scripts/prelaunch_check.py` : the machine-checked **pre-launch** guard as a
  standalone command (non-zero exit on any testing/placeholder value). Run it in
  the target environment, e.g. `OTREE_PRODUCTION=1 python scripts/prelaunch_check.py`.
- `scripts/predeploy_check.sh` (+ `predeploy_check.py`) : the **pre-deploy
  upgrade** gate. Boots the candidate build against a *copy* of the live database
  and drives real participants over real HTTP. See "Before a deploy" above.
- `scripts/export_data.py` : downloads `/ExportWide` and `/ExportPageTimes` over
  an authenticated admin HTTP session. NB: exporting against a database whose
  schema predates the running code returns HTTP 500 — the script says so
  explicitly instead of writing a truncated file.
- `scripts/format_session_data.py` : turns raw SENSITIVE data into i) csv for
  payment, ii) csv with anonymised experiment data, and iii) optionally a draft
  email with the anonymised file attached (recipient configurable via `--email`
  or `$SESSION_DATA_EMAIL`). Rows stay as exported, one per participant; this
  script does not reshape. The conversion to long data is the R helper
  `scripts/helper/otree.R` in Template_Analysis, also offered as
  `otree-wide-to-long.R` on the academic site. `session.config.lab_session` is
  kept verbatim as text. For the usual case, three files after each session, the
  dashboard's **Download data** button does it without pandas, and both use the one
  column list in `core/data_columns.py`.
- `scripts/set_up_otree.bat` : starts oTree on the experimenter's Windows PC in
  the lab.
  It ships `CHANGE_ME_*` placeholders (database name/user/password, admin
  password, `LAB_SERVER_IP`): fill them in locally on the lab PC and never
  commit the real values (the repository is public).
- `scripts/tests/` : HTTP-driven flow tests, escaping and frozen-config regression
  tests, and a measured browser render check (see [testing.md](testing.md)).

> **The shared modules live in `core/`, not `scripts/`.** The apps do
> `from core import common`, and oTree puts the project root (not `scripts/`) on
> `sys.path`; `core/` is a package there, while `scripts/` is not on the path at
> runtime. Only `settings.py` must stay at the root.

## Docker (build and run the container)
The root `Dockerfile` builds a self-contained image that serves the study, so
every study copied from this template inherits one. It bakes in nothing but
Python 3.12, a pinned oTree and the code: **no database is in the image** — with
the default (sqlite) configuration the container creates `/app/data/db.sqlite3`
on first boot and keeps it across restarts, so mount that directory as a volume
if the data matters.

The boot guard initialises the database **only when it has no tables yet**, and
it establishes that by inspecting the database oTree will connect to
(`scripts/db_state.py`), not by looking for a sqlite file — so it is correct
under `DATABASE_URL=postgres://…` too. A database that is not answering yet — the
normal state of a managed Postgres at container start — is retried for a minute
(`DB_WAIT_ATTEMPTS` × `DB_WAIT_SECONDS`, default 30 × 2s) before the guard gives
up; it then refuses to start, loudly and without touching anything, as it also
does when the target database holds a schema that is not oTree's. The image ships
`psycopg2-binary`, so `DATABASE_URL=postgres://…` works out of the box. Why the
old file-existence check was a data-loss bug on any managed Postgres:
`.claude/decisions/build_and_deploy.md`, "Boot initialisation is decided by inspecting the database, not
by a sqlite file".

Note what the guard is *not* doing: oTree creates its own missing tables on every
start (`create_all`), so the initialise branch is belt and braces. The guard
exists to stop `resetdb` — which drops everything — from running against a
database that has participants in it.

**There is no upgrade-path check for a Postgres deployment.**
`scripts/predeploy_check.sh` is sqlite-only by design, so a study hosted on
managed Postgres is currently deployed without the gate described under
[Before a deploy](#before-a-deploy-scriptspredeploy_checksh). See
`docs/postgres_assumptions.md`.

```bash
docker build -t otree-template .

docker run -d --name otree-template --restart unless-stopped \
  -p 8101:8101 \
  -v otree-template-db:/app/data \
  -e OTREE_PRODUCTION=1 \
  -e OTREE_AUTH_LEVEL=STUDY \
  -e OTREE_REST_KEY=<rest-key> \
  -e OTREE_ADMIN_PASSWORD=<password> \
  otree-template
```

Then open `http://localhost:8101/` (admin) or `/demo`. Port **8101** is the
standing test-hosting convention below; keep it unless you have a reason not to.
To bind a session to the `study` room, run the host-side script against the
container: `OTREE_BASE_URL=http://localhost:8101 scripts/start.sh`.

Environment variables that matter:

- **`OTREE_PRODUCTION`** — set it to `1` for anything a participant touches.
  Unset means DEBUG: skip controls and quiz solutions in the browser. It is the
  DEBUG axis, so it is deliberately *not* baked into the image — a clickthrough
  and a real run are the same image, one flag apart.
- **`OTREE_AUTH_LEVEL`** — `STUDY` locks `/demo` and the admin panel behind the
  login and turns on REST authentication. Unset is wide open: fine on localhost,
  never once the container is reachable from outside.
- **`OTREE_REST_KEY`** — required once `OTREE_AUTH_LEVEL=STUDY`: the value REST
  calls must send as the `otree-rest-key` header. `scripts/start.sh` reads the
  same variable, and refuses to run without it under `STUDY`.
- **`OTREE_ADMIN_PASSWORD`** (with `OTREE_ADMIN_USERNAME`, default `admin`) — the
  admin login. The dev fallback is `admin`/`admin`, so set a real one on anything
  exposed. `OTREE_SECRET_KEY` has a dev fallback too and deserves the same.

`FORWARDED_ALLOW_IPS=*` is baked into the image on purpose: behind a
TLS-terminating proxy, uvicorn must trust `X-Forwarded-Proto` or it builds
absolute `http://` links on an `https://` site and they break. The other two
knobs are `PORT` (default `8101`) and `RESET_DB=1`, which wipes the database at
boot — necessary after a schema change, and it strands anyone mid-run, so never
pass it casually. **The 2026-08-12 build IS such a schema change** (a new
`before.Player` column plus a page-sequence change): deploying it over an older
database needs `RESET_DB=1` — or a hand-added column — or every participant
page 500s. See the warning box under
[Before a deploy](#before-a-deploy-scriptspredeploy_checksh).

## Hosting an oTree experiment on your own machine
See [`docs/hosting_local.md`](../../docs/hosting_local.md) for self-hosting on hardware you control (a lab PC, a server, an always-on Mac): the Docker container, a Cloudflare Tunnel or Tailscale Funnel in front of it, binding the room, backups, and the gotchas. Managed hosting is in [`docs/hosting_railway.md`](../../docs/hosting_railway.md).
