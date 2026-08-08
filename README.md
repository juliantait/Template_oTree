# oTree-Template
 This is a template for oTree experimental apps useful for running experiments in the lab. See `template.html` for an example of the pre-coded design and how to use it.

## App Timeline
- before (welcome + consent; online: external-ID + device capture)
- intro (instructions + quiz; optional AI-safety arming page)
- main (experimental game; optional tab monitor + passive capture)
- outro (endings: normal / disqualified / no-consent; demographics + payment)

## Repository layout
The project root holds the four oTree apps plus a small set of top-level items:

| Item | What it's for |
| --- | --- |
| `before/` `intro/` `main/` `outro/` | the four oTree apps, run in this order (see App Timeline). `intro/` also holds `generate_instructions_preview.py`. |
| `_static/` | shared CSS/JS/HTML/images (the design system and `template.html`). |
| `scripts/` | operational scripts: `start.sh`, `prelaunch_check.py`, `export_data.py`, `format_session_data.py`, `set_up_otree.bat`. |
| `tests/` | HTTP-driven flow tests (see "Testing"). |
| `prolific/` | Prolific operational guide (`Prolific_running.md`). |
| `skills_claude/` | authoring playbooks (e.g. writing instructions). |
| `settings.py` | oTree settings: session configs, recruitment profiles, feature flags, completion codes. |
| `common.py` | shared, oTree-free helpers — **must stay at the project root** (every app does `import common`). |
| `README.md` `conventions.md` `CODEBOOK.md` `TODO.md` | project docs: overview, design principles, field/exit-code reference, and pending work. |
| `MACMINI_HOSTING.md` | private Mac mini hosting runbook (gitignored — kept local). |
| dotfiles | `.gitignore`, `.gitattributes`, etc. |

Not tracked in git: `_ai/` (agent scaffolding — pilot snapshots, performance reviews), `previews/` (regenerable instruction previews), the SQLite DB, `__pycache__`, and OS cruft.

## Running the template
It runs out of the box with no setup: `otree devserver` uses a local SQLite file
(no Postgres needed unless you set `DB_NAME`), and dev admin credentials default
to `admin`/`admin`. Set real values via env in production (`OTREE_ADMIN_USERNAME`,
`OTREE_ADMIN_PASSWORD`, `OTREE_SECRET_KEY`, `DB_*`). `DEBUG` is derived by oTree
from `OTREE_PRODUCTION` — never hardcode it.

## How to use and edit this template
- Instructions content: edit `intro/instructions_text.html`. Each `<div class="instruction-block">` is shown as one page to participants. Add, edit, or reorder blocks there to change the instruction pages.
- Quiz questions: edit `intro/quiz_items.py`. Define `QUIZ_ITEMS` entries with `field`, `prompt`, `choices`, and `answer`. The intro quiz reads directly from this file.
- Treatment assignment: edit `before/treatment_assignment.py`. Treatments are assigned when the session is created (via `creating_session` in the `before` app). Adjust `assign_treatments` to set the treatment groups you need.
- Experimental Payoff: edit `outro/payment_rule.py` to determine how participants are actually paid. The logic inside this file controls which rounds and payoffs are selected for payment at the end.

## Parameter scheme (read `conventions.md` and `settings.py` first)
Everything optional is one **feature flag** in `SESSION_CONFIG_DEFAULTS`, shipped
**OFF**. A `recruitment` profile (`prolific` | `lab` | `testing`) is a named
bundle of flag values that is **resolved into explicit config keys at import**,
so the admin session-config view shows exactly what a session will run with. An
explicit per-config flag always overrides the profile.

- `prolific` — external-ID capture, completion-code redirects, tab monitor,
  comprehension disqualification, passive + device capture. Paid on-platform.
- `lab` — no Prolific plumbing, no tab monitor; collects bank details for
  transfer.
- `testing` — everything off, quiz validation loosened for quick clickthrough.

Modules (all off by default): `capture_participant_id`, `completion_redirects`,
`tab_monitor`, `comprehension_dq`, `passive_capture`, `device_capture`,
`collect_bank_details`. Thresholds (`comprehension_max_failures`,
`tab_monitor_*`) and Prolific codes (`cc_code`, `noconsent_code`, `dq_code`,
`error_code`) are config values too. Each participant records a numeric
`exit_code` (see `CODEBOOK.md`). `C.NUM_ROUNDS` is fixed at import — a config may
run fewer rounds, never more.

Every participant field, exit code, stage timestamp and future-proofing spare
column is documented in **`CODEBOOK.md`** (including the repurpose convention for
spares: never rename in place).

## Collaborating on the instructions flow with others?
You can share the instructions with coauthors who don't have the codebase installed. The generator lives in the intro app it previews: run `python3 intro/generate_instructions_preview.py` (from the project root) to produce three self-contained files in a gitignored `previews/` output dir it creates on demand: a long stacked HTML (every block on one page), an interactive single-page HTML (one block at a time, with a floating treatment switcher), and a PDF rendition. All three are fully self-contained — no external dependencies, no internet — so you can email them or drop them into a doc and they'll render the same anywhere. The interactive HTML lets coauthors click through the instructions exactly as participants would and flip between treatments live via the corner buttons; the PDF is good for printing or marking up on paper. The generated files are regenerable and never tracked in git.

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
  - `outro/Demographics.html`: collects and verifies IVAN numbers and other basic demographic questions; edit here if you need to change the questionnaire.

## Scripts (`scripts/`)
- `scripts/start.sh` : bind a session to the lab room on boot, **reusing** an
  already-bound session instead of creating a new one each time (which would
  strand in-progress participants). Authenticates REST calls with
  `OTREE_REST_KEY` when `OTREE_AUTH_LEVEL=STUDY`; fails loudly rather than
  leaving the room unbound.
- `scripts/prelaunch_check.py` : the machine-checked pre-launch guard as a
  standalone command (non-zero exit on any testing/placeholder value). Run it in
  the target environment, e.g. `OTREE_PRODUCTION=1 python scripts/prelaunch_check.py`.
- `scripts/export_data.py` : downloads `/ExportWide` and `/ExportPageTimes` over
  an authenticated admin HTTP session. NB: exporting against a database whose
  schema predates the running code returns HTTP 500 — the script says so
  explicitly instead of writing a truncated file.
- `scripts/format_session_data.py` : turns raw SENSITIVE data into i) csv for
  payment, ii) csv with anonymised experiment data, and iii) optionally a draft
  email with the anonymised file attached (recipient configurable via `--email`
  or `$SESSION_DATA_EMAIL`).
- `scripts/set_up_otree.bat` : starts oTree on the experimenter's Windows PC in
  the lab.
- `tests/` : HTTP-driven flow tests (see "Testing" below).

> **`common.py` stays at the project root** — it is *not* in `scripts/`. All four
> apps do a top-level `import common`, and oTree puts the project root (not
> `scripts/`) on `sys.path`, so moving it would break every app's import.

## Testing
Bots alone are not sufficient here: several pages rely on JavaScript-produced
hidden fields, and the template must not 500 when those arrive **empty** (JS
disabled/blocked). `tests/http_flow_test.py` boots nothing itself — point it at a
running server on a throwaway database and it drives each config's form pages
over real HTTP, including a POST with the hidden fields deliberately empty, and
asserts no 500s. See the header of that file for usage.

## Attribution (oTree)
The "powered by oTree" badge is hidden (see `_static/global/css/base.css`). The
oTree licence is satisfied by **citing the oTree paper** in any write-up, not by
the badge: Chen, D. L., Schonger, M., & Wickens, C. (2016). oTree — An
open-source platform for laboratory, online, and field experiments. *Journal of
Behavioral and Experimental Finance*, 9, 88–97.

## Running online on Prolific
Prolific support is **built in** — there is no manual wiring to do. Select the
`prolific` recruitment profile (set `recruitment='prolific'` on your session
config, as the shipped `prolific` config does) and the profile resolves the
relevant feature flags into explicit config keys at import (see the "Parameter
scheme" section and `settings.py`). That bundle turns on:

- **`capture_participant_id`** — captures the external Prolific participant ID at
  entry (stored in the `participant_id_external` field).
- **`completion_redirects`** — routes each ending to Prolific with the matching
  completion code: normal completion, declined consent (no-consent), and
  disqualification (comprehension / tab monitor), plus screen-out / inactivity.
- the **integrity modules** — `tab_monitor`, `comprehension_dq`, plus
  `passive_capture` and `device_capture`.

**Completion codes** are config values, set in `settings.py`: the
`SESSION_CONFIG_DEFAULTS` placeholders `cc_code` (normal), `noconsent_code`
(declined consent), `dq_code` (disqualified) and `error_code` (screen-out /
inactivity) — replace the `REPLACE_*` values, or override them per-config on your
`prolific` session config. The prelaunch check refuses to run online while any
code is still a `REPLACE_*` placeholder.

For the operational walkthrough — creating the Prolific study, wiring the URLs,
and the finish-screen routing in practice — see **`prolific/Prolific_running.md`**.

## Hosting an oTree experiment online (Mac mini)
See `MACMINI_HOSTING.md` for the full self-contained guide: how the Mac mini serves an oTree experiment (Docker container + Cloudflare Tunnel subdomain), the problems we hit and how we solved them, and a step-by-step recipe to deploy a brand-new experiment. That file is gitignored (it holds private infra details) so it stays local only.

**Test oTree hosting convention:** every test oTree on the Mac mini runs as a Docker container on the fixed **port 8101** (env `FORWARDED_ALLOW_IPS=*`), exposed on the tailnet via `tailscale serve --bg --https=8443 http://localhost:8101`. To put a new experiment on the test server, stop/remove the old container and `docker run` the new image on the same port 8101. Reusing 8101 keeps the tailscale serve mapping and the Dock apps working untouched. See the "Test oTree hosting convention" section in `MACMINI_HOSTING.md` for the full standing convention every future test oTree must follow.

## Template HTML Layout
The file [`_static/global/html/template.html`](./_static/global/html/template.html) serves as the core visual template for most experimental pages. It is located in the `_static/global/html/` directory of your project. This template demonstrates and defines how all of the pre-defined CSS sections will look and behave, providing a live preview of your main screen layout.

- **Header Section**: Shows how the experimental screen header appears, including the title and subtitle, styled using the shared CSS (`global/style.css` and the imports in that file).
- **Main Content Area**: Contains a section for page headings and standard paragraph text, both vertically and horizontally centered within a card. This section uses classes such as `.experimental-content`, `.section-title`, and `.section-text` to illustrate their styling.
- **Navigation Buttons**: Displays the "Back" and "Next" buttons with their associated styles (`.button-row`, `.next-button`).
- **Logos Section**: Includes a common logos area displayed at the bottom of the intro and outro screens.

By editing or viewing this file in your browser, you can see how the different visual building blocks (as defined in the referenced CSS) are applied. When creating new pages, structure your content to fit inside this card layout by extending or including this template, ensuring consistency across experimental screens.
