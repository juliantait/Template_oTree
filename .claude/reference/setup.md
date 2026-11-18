# Setting up and running locally

*Read this when you install the template, run it locally, or pick a database backend.*

## Setting up (once)

Python 3.9+ and one `pip install`. **Install only the group you need** — running
a study does not require the browser-test stack.

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 1. RUN A STUDY — the only group most people need.
pip install otree==6.0.15
otree devserver                      # then http://localhost:8000/demo

# 2. PREVIEW THE INSTRUCTIONS without running a session
pip install jinja2 playwright
playwright install chromium          # only needed for the PDF; the HTML works without it

# 3. RUN THE TESTS (HTTP suites, and the measured render checks)
pip install requests pillow playwright
playwright install chromium

# 4. FORMAT EXPORTED DATA (scripts/format_session_data.py)
pip install pandas

# 5. RUN AGAINST POSTGRES outside Docker (the image already has it)
pip install psycopg2-binary==2.9.12
```

**Why these and no others.** `otree==6.0.15` brings SQLAlchemy, Starlette,
uvicorn and WTForms with it, so the study itself needs nothing else. The four
extra groups are tooling: `jinja2` for the preview generator, `playwright` +
`pillow` for the browser render checks, `requests` for the HTTP-driven test
suites, `pandas` for the one data-formatting script. `otree` and
`psycopg2-binary` are pinned to exactly what the `Dockerfile` installs, so local
and container agree; the tooling is left unpinned because it is not the study.

**One known noise:** installing `jinja2` upgrades `markupsafe` past the version
`otree==6.0.15` pins, and pip prints a dependency-conflict warning. It is a
warning, not a break — the full test suite passes with the upgraded package. If
you would rather keep pip quiet, install `jinja2==2.11.3`.

**Do NOT run `otree resetdb` first.** `otree devserver` creates its own database;
`resetdb` is for the deploy path (see Docker). Running `resetdb` and then
`devserver` on the same tree makes the server refuse to start with *"oTree has
been updated. Please delete your database (db.sqlite3)"* — `resetdb` writes the
tables without the sqlite `user_version` stamp that devserver's in-memory loader
checks, so it reads as a version mismatch. It is not one. **The fix is to delete
`db.sqlite3` and just run `otree devserver`.**

On a machine without root, headless Chromium needs nine unpacked system
libraries — the whole recipe is `docs/headless_chromium_recipe.md`.

## Running the template
It runs out of the box with no setup: `otree devserver` uses a local SQLite file,
and dev admin credentials default
to `admin`/`admin`. Set real values via env in production (`OTREE_ADMIN_USERNAME`,
`OTREE_ADMIN_PASSWORD`, `OTREE_SECRET_KEY`). `DEBUG` is derived by oTree
from `OTREE_PRODUCTION` — never hardcode it.

**The database backend is chosen by `DATABASE_URL` and nothing else.** Unset
means the local SQLite file. The `DB_NAME`/`DB_HOST` block in `settings.py`
*looks* like it selects Postgres and does not — oTree 6 dropped Django and never
reads `DATABASES`, so setting those gets you SQLite, silently. Recorded, with the
options for fixing it, in `docs/postgres_assumptions.md` (item 4).
