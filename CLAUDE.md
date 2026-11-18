# oTree-Template: rules for agents working in this template

This is an oTree 6 study template (four apps: `before` → `intro` → `main` → `outro`)
that researchers copy to start new experiments, for a physical lab or for Prolific.
A mistake here propagates to every study built from it. This file holds what you
need on every task: the hard rules, where things live, how to run the checks, and
an index of topic files in `.claude/reference/` to read when a task touches that topic.

## Read before changing anything

- **`.claude/DECISIONS.md` records why things are the way they are**: each decision, its
  reasoning, the rejected alternative and *where it is enforced* (or an
  admission that nothing enforces it). Read it before
  changing anything that looks wrong, and add to it in the same change that makes a
  decision someone could later mistake for an accident. Most apparent redundancy
  here is load-bearing. The failure mode it defends against is **helpfulness**: a
  missing config value reads as an unfinished port, inert code reads as dead weight,
  a constant only coherent at one value reads as a tunable knob, and a competent
  agent "corrects" each one. The reason, written down, is what stops that.
- **On a forked study, `.claude/DECISIONS.md` is fresh**: the fork starts its own log from
  `.claude/DECISIONS_stub.md` (step 0 in `.claude/reference/editing_a_study.md`). Keep
  reading it and adding to it exactly as above.
- **`docs/CODEBOOK.md` opens with an Analyst quick start, and a fork fills it in**: its
  own primary outcomes, exclusions and pooling caveats, and its study fields in the
  primary tier (PROMPT boxes mark the spots), in the same change that swaps the
  task in `main`.
- `docs/conventions.md` holds the design principles; `docs/README.md` is the
  researcher's operating guide; `README.md` is the short human entry point.

## The three orthogonal controls

Everything a participant experiences is decided by three **independent** axes at the
top of `settings.py`:

1. **Study type**: `prolific` or `lab`. Recruitment plumbing only: ID capture,
   completion-code redirects and the integrity modules for Prolific; bank details
   and demographics for lab.
2. **Debug**: driven by the environment (`OTREE_PRODUCTION` unset means debug on),
   so production can never ship skip controls. It must be possible to debug a
   *Prolific-configured* study with all its modules on.
3. **Pilot feedback form**: its own flag, on for a pilot or friend test, off for the
   real run.

A profile resolves into **explicit** config values at import, so the admin shows
exactly what a session ran with; a profile must never change behaviour silently at
runtime. Testing switches are a **reversible override layer**: turning testing off
must return every gate to the real study behaviour with nothing left changed.
Details: `.claude/reference/parameters.md`.

## Correctness rules (each shipped a live bug in the pilot this template feeds)

- **Never `getattr(participant, 'field', default)`**: the vars descriptor raises
  `KeyError`, which the default does not catch. Use `participant.vars.get(...)`.
- **Never `session.config['name']`**: the config is frozen at session creation, so
  parameters added later are missing for running sessions. Use the safe accessor
  (`common.cfg`).
- **Never read a nullable model field bare**: use `field_maybe_none`.
- **Render telemetry as explicit hidden inputs**: oTree auto-renders any unplaced
  form field as a visible labelled box.
- **Escape participant- and URL-supplied values**: the templates do not
  auto-escape; this caused a reflected XSS.
- **Instrumentation must never break a page**: wrap all capture defensively.
- **`NUM_ROUNDS` is fixed at import.** A config may run fewer rounds, never more,
  and a rounds or page-sequence change must never be deployed over live sessions.
- **Find the repo root by walking up to `settings.py`** (`core.REPO_ROOT`,
  `scripts/tests/_repo.py`), never by counting directories.
- **Style with shared components** in `_static/global/css/`; no inline `style=`, no
  page-local patches. Exceptions are marked `EXCEPTION` with the reason.
- **When two different situations reach identical code, or one concept has two
  implementations, that is where the bug lives.** Keep them apart and say why at
  the split. Worked examples: `.claude/reference/bug_patterns.md`.

## Where things live

- `settings.py`: session configs, recruitment profiles, flags, completion codes. Must stay at the root (oTree requires it).
- `before/` `intro/` `main/` `outro/`: the four apps. The game goes in `main/`; `intro` describes it.
- `core/`: shared runtime modules, imported as `from core import common`. `common` (helpers, `cfg`), `identity` (one row per participant id), `payoff_guard` / `fee_guard` (boot guards), `experimenter_dashboard`, `data_download` / `data_columns` (Download data), `health` (`/health`), `otree_routes`, `participant_tab_monitor`, `dot_bi`, `buildinfo`.
- `scripts/`: `prelaunch_check.py`, `predeploy_check.sh`/`.py`, `verify_deploy.py`, `write_build_info.py`, `db_state.py`, `export_data.py`, `format_session_data.py`, `start.sh`, `set_up_otree.bat`, `site_previews/`.
- `scripts/tests/`: the suites; `_repo.py` puts the root on `sys.path`.
- `_static/global/`: CSS, JS, images, and `_static/global/html/template.html` (component specimens). `_templates/`: the room welcome gate.
- `docs/`: researcher guides (hosting, Prolific, Postgres, conventions) and `CODEBOOK.md`.
- `.claude/`: agent material, tracked but kept out of the Docker image. `DECISIONS.md` and `DECISIONS_stub.md`; `reference/` (the topic index below); `skills/` (authoring playbooks as Claude Code skills, index `skills/README.md`).
- `previews/`: instruction preview output; only `Preview_Instructions.command` (the double-click launcher) is tracked there.
- Not tracked: `_ai/` (agent scaffolding), the rest of `previews/`, `TODO.md`, `todo.json`, `.claude/settings.local.json`, `MACMINI_HOSTING.md`, the SQLite DB.

Full table: `.claude/reference/layout.md`.

## Running the checks

- Environment: `pip install otree==6.0.15` (study); `requests pillow playwright` + `playwright install chromium` (tests); `pandas` (data formatting). Details: `.claude/reference/setup.md`.
- **HTTP suites** (`full_journey_test`, `http_flow_test`, `gated_flow_test`, `device_gate_test`, `screenout_softwall_test`, `copy_routing_test`, `device_capture_js_test`, `bot_render_check`): start `OTREE_ADMIN_PASSWORD=admin otree devserver 8000` on a **throwaway** database, then `python scripts/tests/<suite>.py http://localhost:8000`.
- **Everything else in `scripts/tests/`** boots oTree in-process or starts its own server: `python scripts/tests/<suite>.py`. Render checks need headless Chromium (`docs/headless_chromium_recipe.md`).
- **Before a launch**: `python3 scripts/prelaunch_check.py` (static config guard; fails on placeholder codes and DEBUG on, as shipped).
- **Before a deploy**: `scripts/predeploy_check.sh <copy-of-live-db>`; with no database it reports the upgrade path NOT TESTED, never a pass. Use `--require-db` for a study with participants.
- **Bot tests are not evidence**: the apps ship no `tests.py`, and bots never issue an HTTP POST or render a page. Drive real pages, include a no-JS submit, and never assert an absence without the matching presence.
- After touching `_static/global/css/` or the dashboard's stylesheet or `renderRow`, re-run `scripts/site_previews/build_site_previews.py` and `check_site_previews.py`.

## Topic index (`.claude/reference/`)

- [`setup.md`](.claude/reference/setup.md): read when you install, run locally, or choose a database backend.
- [`layout.md`](.claude/reference/layout.md): read when you need the full repository table, the app timeline, or per-app page guidance.
- [`editing_a_study.md`](.claude/reference/editing_a_study.md): read when you start a study from the template (the ordered walkthrough), rebrand it, or set notification tiers.
- [`parameters.md`](.claude/reference/parameters.md): read when you add or change a session-config parameter, a recruitment profile, or the screen lock.
- [`entry_and_identity.md`](.claude/reference/entry_and_identity.md): read when you touch the device check, the room welcome gate, room binding, or participant labels.
- [`participant_flow.md`](.claude/reference/participant_flow.md): read when you change the page sequence, endings, exit or completion codes, or Prolific behaviour.
- [`payments.md`](.claude/reference/payments.md): read when you touch payoffs, the payment rule, the Results receipt, or payment exports.
- [`dashboard.md`](.claude/reference/dashboard.md): read when you touch the experimenter dashboard or Download data, or add, rename or split an app.
- [`testing.md`](.claude/reference/testing.md): read before writing, editing or running any test (the testing standard and what each check is evidence of).
- [`build_and_deploy.md`](.claude/reference/build_and_deploy.md): read when you run or change a script, the two launch gates, the Docker image, or hosting.
- [`styling.md`](.claude/reference/styling.md): read before changing CSS, templates or page layout.
- [`bug_patterns.md`](.claude/reference/bug_patterns.md): read when you audit or review code, or add an `except`, a predicate or a second implementation.

Also: the skills in `.claude/skills/` (index `.claude/skills/README.md`: writing the task, instructions, quiz, consent, tests; hosting a Prolific study; `writing-tests` before any test), `docs/hosting_railway.md`, `docs/running_on_prolific.md`, `docs/postgres_assumptions.md`, `docs/CODEBOOK.md`.
