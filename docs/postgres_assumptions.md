# Recorded, not fixed: what still assumes sqlite

**Date:** 2026-08-14. **Author:** agent session, at Julian's instruction.
**Status:** open decisions, not defects awaiting a patch. Nothing here has been
changed in the code; it is deliberately separate from the two defects fixed the
same day (the Dockerfile boot guard and the predeploy database pin — both in
`DECISIONS.md`).

**This file is TRACKED, and it is here because a copied study inherits every gap
in it** — item 8 especially. If you are starting a study from this template,
this is the list of things the template does not yet do for you. `DECISIONS.md`
carries a short entry for each; this is the long form.

## How this list came about

The hosting review found `resetdb` running on every boot in `exp_pilots`'
`start.sh` and asked whether this template shared the defect. It did, in the
Dockerfile. Fixing it meant asking a broader question — **where else does this
codebase assume the database is a file?** — and the sweep found more than the
one thing. Two items were destructive and were fixed immediately; these five are
not destructive, so they are recorded rather than patched in a hurry.

They are related, and #8 is the one that matters. The others are tidy-ups; #8 is
a hole in the safety net.

**Update, same day:** item 6 (no Postgres driver in the image) was pulled OUT of
this list and fixed, after the converged `exp_pilots` fix (79d49c2) was relayed.
It should never have been recorded — see its entry below for why. Items 4, 5, 8
and 9 stand as decisions for Julian.

---

## 8. THE SIGNIFICANT ONE — there is no upgrade-path check for Postgres

**What is true.** Every safety mechanism this template has for "will the running
study survive being upgraded to this code?" runs on sqlite, and only on sqlite:

- `scripts/predeploy_check.sh` pins itself to a staged **sqlite** file, validates
  the database argument by its **sqlite magic header**, and proves its isolation
  with `PRAGMA database_list` — a sqlite-only statement. This is by design and
  documented in its header; it is not a bug.
- The documented way to obtain the input is
  `docker cp <container>:/app/data/db.sqlite3` — a file that does not exist under
  Postgres.
- `scripts/tests/otree_inprocess.py` and `scripts/tests/render_check.py` create throwaway sqlite
  databases. Every other suite is in-process or HTTP against sqlite.
- `_ai/live_data/db_generated_*.sqlite3` (local only — `_ai/` is gitignored; not in a clone), the fixture that makes upgrade mode
  meaningful, is a sqlite file.

**Why that is the real gap.** A study hosted on Railway, Heroku, Fly or any
managed platform runs on Postgres. So **the one backend a hosted study actually
uses is the one with no coverage at all.** A Postgres operator running the
pre-deploy gate the documented way lands in degraded mode — which is honest (it
says `THE UPGRADE PATH WAS NOT TESTED` in a banner you cannot miss) but empty:
they get the fresh-install checks and nothing about their own participants. The
two live outages this gate was built for — a participant-vars key old
participants never had, a session config frozen before a parameter existed — are
exactly the failures a fresh database cannot reproduce. On Postgres, nothing
reproduces them.

It is also the reason the two fixed defects survived as long as they did. Both
were destructive **only** against Postgres, and no test in this repo has ever
opened a Postgres connection, so nothing went red. The Dockerfile defect would
have been caught on day one by any check that booted the container against a
Postgres URL twice and asserted the data was still there.

**What closing it would require**, roughly in order of cost:

1. **A Postgres fixture the suites can run against.** Not conceptually hard —
   this machine ran a real PostgreSQL 16 with no root at all (private apt root,
   `dpkg-deb -x` into a sysroot; recipe in the agent memory note
   `postgres-without-root`), which is how both fixes were proven. In CI it is a
   service container. Cost: an afternoon. The driver is no longer a blocker —
   `psycopg2-binary` is in the image as of the same day (see #6), and the test
   environment needs it installed too.
2. **Teach `predeploy_check.sh` a Postgres mode.** The isolation model has to
   change shape, not just gain a branch: for sqlite, isolation is "copy the file
   and chdir". For Postgres the equivalent is `pg_dump` the live database and
   restore it into a **throwaway database** (or a throwaway schema), then point
   the check at that. The refusal-to-touch-live guard becomes "the target must
   not be the live database name", and the `PRAGMA database_list` proof becomes
   `SELECT current_database()`. That proof is now behind one function
   (`assert_engine_on`), so this is one place to extend, not two.
3. **A container boot test.** The highest value per line, and it needs Docker,
   which the agent session could not run: boot the image against a Postgres URL,
   write a row, restart the container, assert the row survives. That single test
   is the direct regression test for the defect that started all of this. It
   would also have caught it originally.
4. **A generated Postgres fixture** equivalent to `_ai/live_data/` (local only — `_ai/` is gitignored; not in a clone), so upgrade
   mode has live-shaped data to audit on that backend too.

**My recommendation.** Do 3 first — it is small, it directly guards the thing
that nearly cost a study, and it needs no changes to the check's design. Then 1
and 2 together when a study is actually going to be hosted on Postgres. Until
then, the honest operating rule is: **this template's deploy gate covers sqlite
deployments; a Postgres deployment is being upgraded without an upgrade check,
and the operator should know that.** Worth stating in the README's Docker
section in exactly those words.

---

## 4. `settings.py` selects Postgres through a mechanism oTree 6 does not read

`settings.py:743-762` does:

```python
if os.environ.get('DB_NAME'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql_psycopg2', ...}}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', ...}}
```

**oTree 6 never reads `DATABASES`.** Verified: zero references to the name
anywhere in the installed `otree` package (6.0.15). oTree 5 dropped Django; the
backend is chosen solely by the `DATABASE_URL` environment variable. So this
block is inert — a Django-era leftover that reads like a working control.

**Consequence:** somebody who sets `DB_NAME`/`DB_USER`/`DB_HOST` expecting
Postgres silently gets sqlite. Not data loss, but a config that lies, and a
believable route into thinking a study is on Postgres when it is on a file
inside the container. It is the same defect class as the two that were fixed —
a control whose apparent meaning and real effect differ — just not destructive.

**Options:** (a) delete the block and let `DATABASE_URL` be the only answer
(simplest, and matches how oTree works); (b) keep the `DB_*` variables as a
convenience and have them **construct** `DATABASE_URL` when it is not already
set, so the documented knobs actually work; (c) leave it and document it as
dead. I would take (b) if `DB_*` is in anyone's muscle memory, else (a). Either
way it needs a comment saying `DATABASES` is not consulted, or it will be
"restored" by the next reader.

## 5. `README.md:35` documents #4 as if it worked

> "`otree devserver` uses a local SQLite file (no Postgres needed unless you set
> `DB_NAME`) … Set real values via env in production (`OTREE_ADMIN_USERNAME`,
> `OTREE_ADMIN_PASSWORD`, `OTREE_SECRET_KEY`, `DB_*`)."

Both halves teach the inert mechanism from #4. Fix with #4, in the same change —
whichever way #4 goes, this sentence changes with it. (The README's Docker
section was already updated to name `DATABASE_URL` as the real control.)

## 6. ~~The image ships no Postgres driver~~ — FIXED, this was never a record item

**Superseded 2026-08-14, the same day, on Julian's instruction after the
`exp_pilots` fix (79d49c2) was relayed.** `psycopg2-binary==2.9.12` is now
installed in the Dockerfile.

Recording this rather than deleting it, because the misjudgement is the useful
part. I filed it as "a decision, not a fix — it puts a driver into every study's
image". That reasoning ignored the interaction with the guard I had just written:
with no driver, the probe cannot connect, so it lands in the unanswerable branch
and **refuses to boot**. Shipping that combination would have meant a guard whose
safe direction is triggered by our own missing dependency — every Postgres deploy
failing 100% of the time, presenting as a database problem. The fix and the
"optional" dependency were not independent, and I assessed them as if they were.

The general lesson for this file: an item is only safely *recorded* if it cannot
interact with what was *fixed*. Check that before filing the next one.

## 9. A wrong-backend engine is reported as "the app failed to boot"

`check_boot` in `predeploy_check.py` wraps the in-process import and the engine
proof in one `try/except Exception`, and reports any failure as *"the app failed
to boot against the database"*. A wrong **backend** is not a broken build, and
reading it as one sends the next person to debug their app instead of their
environment. This is the shared-`except` shape CLAUDE.md warns about, in its
mild form: nothing is destroyed, only misattributed.

**Partly addressed already, as a side effect of the fix:** `assert_engine_on()`
now checks the backend explicitly and exits with its own message ("oTree built a
`postgresql` engine, not sqlite"), and `check_boot` re-raises `SystemExit`, so
that particular case now reports itself accurately. What remains is the general
shape — every other import-time failure still collapses into one message. Worth
splitting if the file is being edited anyway; not worth a change on its own.

---

## Not on this list, checked and clean

- `scripts/tests/otree_inprocess.py:134`, `scripts/tests/render_check.py:102` — both **override**
  `DATABASE_URL` before importing oTree and chdir into a temp dir. Safe even
  when a live Postgres URL is exported in the shell.
- `has_otree()` in `predeploy_check.sh` — `import otree` alone creates no file
  and opens no connection (only `otree.database` does). Verified.
- `.gitignore` / `.dockerignore` sqlite patterns — a stray zero-byte
  `db.sqlite3` under Postgres is harmless.
- No raw SQL anywhere in the app code, so no backend-specific query syntax.
  (The one place identity is compared, `identity.py`, was already moved out of
  SQL and into Python for exactly this reason — see `DECISIONS.md`, 2026-08-12.)
- `scripts/set_up_otree.bat`, `MACMINI_HOSTING.md` — host-side dev docs, no
  runtime effect.
