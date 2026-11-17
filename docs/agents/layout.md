# Repository layout and app timeline

*Read this when you need to know where something lives or which app does what.*

## App Timeline
- before (welcome + consent; online: external-ID + device capture)
- intro (instructions + quiz; optional tab-monitor arming page)
- main (experimental game; optional tab monitor + passive capture)
- outro (endings: normal / disqualified / no-consent; demographics + payment; optional pilot feedback)

## Repository layout
The project root holds the four oTree apps plus a small set of top-level items:

| Item | What it's for |
| --- | --- |
| `before/` `intro/` `main/` `outro/` | the four oTree apps, run in this order (see App Timeline). `intro/` also holds `generate_instructions_preview.py`. |
| `_static/` | shared CSS/JS/HTML/images (the design system and `template.html`). |
| `scripts/` | operational scripts: `start.sh`, `prelaunch_check.py` (config guard), `predeploy_check.sh`/`.py` (upgrade gate), `export_data.py`, `format_session_data.py`, `set_up_otree.bat`. |
| `scripts/tests/` | HTTP-driven flow tests, escaping/frozen-config regressions, and the browser render check (see "Testing"). |
| `scripts/site_previews/` | builds the six self-contained screen previews the academic website embeds, from the live template (`build_site_previews.py`), plus the measured check that they render uncut and at one shared scale (`check_site_previews.py`). Five are participant screens built from `bodies/`; the sixth is the experimenter monitor, which is rendered by the dashboard's own JavaScript over the invented session in `monitor_session.py` and then frozen, so that step needs Playwright. Output lands in gitignored `_ai/site_previews/`. Re-run after changing `_static/global/css/` — or, for the monitor, `core/experimenter_dashboard.py`. |
| `docs/` | **the tracked reference a copied study inherits** — start at `docs/README.md`. Hosting an online study, running one on Prolific, the design principles (`conventions.md`), the headless-Chromium recipe the render checks need, the open Postgres gaps, a group-matching reference implementation, and the experimenter-dashboard brief as it was specified. |
| `docs/agents/` | the detailed reference by topic, split out of the old README and CLAUDE.md: setup, layout, editing a study, parameters, entry and identity, participant flow, payments, dashboard, testing, build and deploy, styling, bug patterns. Indexed from `CLAUDE.md`. |
| `docs/skills_claude/` | authoring playbooks for an agent working ON the template: writing the task, instructions, quiz, tests, and the Railway hosting procedure. Index: `docs/skills_claude/README.md`. |
| `_templates/` | templates rendered OUTSIDE oTree's page system. Currently `room_welcome.html`, the styled room entry gate (see "The room welcome gate"). |
| `settings.py` | oTree settings: session configs, recruitment profiles, feature flags, completion codes. |
| `core/` | the shared runtime modules the apps and `settings.py` import (`from core import common`). oTree puts the project root on `sys.path`, so `core` is importable everywhere; only `settings.py` must sit at the root. One line each below. |
| `core/common.py` | shared, oTree-free helpers used by every app. |
| `core/identity.py` | participant-label identity: one row per external id, and the guard that stops a duplicate label 500-ing at entry. |
| `core/fee_guard.py` | the BOOT guard that refuses to start a build whose session configs (or app source) set oTree's built-in `participation_fee` to anything but 0. One payment ledger: see "Paying participants". Called from `before/__init__.py` beside the payoff guard. |
| `core/payoff_guard.py` | the BOOT guard that refuses to start a build whose app modules write oTree's per-round `player.payoff`. Called from `before/__init__.py`. It exists because the alternative — `AUTO_TABULATE_PAYOFFS=False` making oTree's setter raise — fires inside a participant's request, so on a live upgrade it is a dead page mid-round rather than a data error. |
| `core/experimenter_dashboard.py` | the live operator view at `/experimenter_dashboard` (see "Experimenter dashboard"). |
| `core/data_download.py` | the dashboard's **Download data** button: plain CSV files from one press (see "Download data" under "Experimenter dashboard"). |
| `core/data_columns.py` | what the Download data button makes, set in code: the switch `DOWNLOAD_DATA_BUTTON`, the function `download_files`, then the column lists and the template's rules, in one plain module (no oTree, no pandas, no web code). `scripts/format_session_data.py` uses the lists only. |
| `core/buildinfo.py` | reads the build stamp (`BUILD_INFO.json`, written at the root by `scripts/write_build_info.py`) and gives each participant their `build_sha`. |
| `core/dot_bi.py` | the dot-counting bot-detection challenge (with `_static/global/js/dot_bi.js`). |
| `core/health.py` | the unauthenticated `/health` route a deploy gate reads. |
| `core/otree_routes.py` | the one implementation that appends extra routes (dashboard, /health, Download data) to oTree's app. |
| `core/participant_tab_monitor.py` | the participant-side tab-monitor page bases and their boot guard. |
| `README.md` `CLAUDE.md` `DECISIONS.md` `docs/conventions.md` `CODEBOOK.md` | the five top-level documents: short human entry point, rules for agents (with the `docs/agents/` topic index), decision record, design principles, data codebook. |
| `Preview_Instructions.command` | double-clickable (macOS): view the instructions as a coauthor would, with **no terminal** — see "Collaborating on the instructions flow". |
| `TODO.md` | pending work. **Gitignored — local only, not in a copy.** |
| `MACMINI_HOSTING.md` | private Mac mini hosting runbook (gitignored — kept local). |
| dotfiles | `.gitignore`, `.gitattributes`, etc. |

Not tracked in git: `_ai/` (agent scaffolding — pilot snapshots, performance reviews, audits), `previews/` (regenerable instruction previews), `TODO.md`, `MACMINI_HOSTING.md`, the SQLite DB, `__pycache__`, and OS cruft. Reference material a copied study genuinely needs is tracked in **`docs/`** instead — start at `docs/README.md` if you are running a study rather than editing the template.

## Pages by app (edit guidance)
- before
  - `before/startpage.html`: waiting page while participants take a seat; experimenter must move participants beyond; usually leave as-is unless you need different holding text.
  - `before/welcome+consent.html`: welcome and consent; should be edited to match your approved consent language.
- intro
  - `intro/instructions_text.html`: only file to edit for instructions; each `<div class="instruction-block">` you add here is displayed as its own page automatically.
  - `intro/quiz_items.py`: edit questions, choices, and correct answers; updates flow into the quiz automatically.
  - `intro/templates/` (`instructing.html`, `quiz.html`): template shells; typically do not edit.
- main
  - `main/`: This folder contains the core logic and code for your experimental task. Place the main game code, task logic, and any files that control the experiment's core flow here.
- outro
  - `outro/Results.html`: built-in results summary showing per-round payoffs and total payment; generally leave untouched. To update how payment is calculated, edit the function in `outro/payment_rule.py`.
  - `outro/Demographics.html`: collects and verifies IBAN numbers and other basic demographic questions; edit here if you need to change the questionnaire.
