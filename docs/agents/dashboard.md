# Experimenter dashboard and Download data

*Read this when you touch core/experimenter_dashboard.py, core/data_download.py, core/data_columns.py, or add/rename/split an app.*

## Experimenter dashboard

A live, **read-only** view of a running session for whoever is supervising it —
the experimenter in the room for a lab session, whoever is watching the study run
on Prolific. It is served **in-process** by oTree itself
(`core/experimenter_dashboard.py`, design notes in `_ai/dashboard_notes.md` — local only — `_ai/` is gitignored; not in a clone), not as a
separate service:

- `/experimenter_dashboard` — pick a session;
- `/experimenter_dashboard/<session_code>` — the dashboard.

One row per participant, keyed on `participant.label` (the seat number in the lab,
the Prolific ID online; the participant code, dimmed, until a label exists). Each
row carries a timeline built **from that session's own `app_sequence`** — one
step per app, `intro` split into Instructions and Quiz, then Done; for the
shipped apps **Entry → Instructions → Quiz → Task → Questionnaire → Done** — with
the marker on the current step, carrying the round inside a multi-round app
("2 of 10" in the task, "2" on the intro's re-read pass). A study that adds or
renames an app needs no dashboard edit: an app may declare `C.MONITOR_LABEL`,
`C.MONITOR_ROUNDS` and `C.MONITOR_ROUNDS_CONFIG` (CLAUDE.md, "Adding, renaming or
splitting apps"). Then the quiz-attempts cell (white
→ filling → red at `quiz_comprehension_max_failures` → green with the attempt count
once passed, so `1` means passed first time), time on the instructions, earnings
once known, and a state cell. A terminal state **overrides the marker** with an
emoji at the step the participant had reached: 📵 screened out, ✋ declined
consent, ❌ comprehension DQ, 👀 tab-monitor DQ. A row turns **amber** after too
long on one page, and rows that never arrived are dimmed with a header toggle to
hide them. It repaints on a poll with a **2-second floor**.

**Access is oTree's own admin login, which means it is exactly as protected as
`OTREE_AUTH_LEVEL` makes it.** The dashboard reuses `AdminView`'s login check
rather than inventing one (and is deliberately stricter than oTree in one respect:
it also requires a login under `AUTH_LEVEL=DEMO`, which leaves oTree's own
SessionMonitor open). With `OTREE_AUTH_LEVEL` **unset** there is no login on any
admin page, this one included — so `scripts/prelaunch_check.py` fails a launch
that has not set it to `STUDY`. This page shows earnings and per-participant
conduct; treat it like the data exports.

**A broken dashboard may fail a LAUNCH loudly, but never a running session
silently** (DECISIONS.md, 2026-08-17). A bug inside a row degrades to an error
row, a bug in a handler to the error panel, and a failed route install to a 404 —
never a participant 500 (that is the module's first rule). The one drift that used
to boot clean and then 500 oTree's own admin **Report tab** mid-session — the
dashboard's `URL_BASE` renamed while the cross-file read in
`outro.vars_for_admin_report` was missed — is now guarded in both directions: at
runtime that read falls back to the literal URL rather than 500ing the tab, and
`scripts/prelaunch_check.py` fails the launch when the constant has drifted, so it
is caught while it can still be fixed. A genuine import-time error in the module
is *deliberately* left to fail the boot: whoever is launching sees it and fixes
it, which is the whole point of failing at launch rather than mid-session.

**The settings, all read at request time** (so tuning them needs only a server
restart, and deleting any line falls back to the same default). They are
module-level settings rather than session-config parameters on purpose:
operator-screen behaviour must not appear in the admin's session-config view or
in the experimental record.

**The amber threshold is PER PHASE**, because "too long" on the consent page and
"too long" reading the instructions differ by an order of magnitude and one
number could not be right for both — set it low enough for entry and every
reader turns amber; high enough for the instructions and nobody stuck at entry
is ever flagged. Both failures are silent, and the operator simply learns to
ignore the colour.

A phase is an APP: the setting for app `x` is `DASHBOARD_STALL_SECONDS_X`
(uppercased), so a new app gets its own line by naming it.

| setting | default | governs |
|---|---|---|
| `DASHBOARD_STALL_SECONDS_BEFORE` | 60 | the entry block (startpage, consent, ID, tab-monitor) |
| `DASHBOARD_STALL_SECONDS_INTRO` | 480 | the whole `intro` app — instructions and quiz share one |
| `DASHBOARD_STALL_SECONDS_TASK` | 180 | ONE task round in `main` (its legacy name; `..._MAIN` also works and wins) |
| `DASHBOARD_STALL_SECONDS_OUTRO` | 300 | the outro, before being marked complete |
| `DASHBOARD_STALL_SECONDS_DEFAULT` | 300 | any app without its own line (judged on time on the current page) |
| `DASHBOARD_POLL_SECONDS` | 2 | poll interval; 2 is also a floor, enforced server-side |

The thresholds in force are **shown on the page itself**: the ⓘ in the **State**
column header lists one per app in the session, read from these settings on every poll, so an
operator can see what counts as too long without opening `settings.py`. An amber
row additionally names the limit it tripped.

**The two summary items at the foot are each one merged pill, and both run over
the *same* population — *finished* participants (`of N finished`, stated once).**
This is a deliberate simplification (Julian, 2026-08-17): the strip is an
at-a-glance operator impression, not an analysis statistic, so there is one
denominator per pill and nothing to disambiguate.

**time** carries an **avg intro** and an **avg completion** subsection. avg intro
is the mean time in the intro app; avg completion is the mean time for the whole
run, the first stamp to the finished stamp — both read from each finished
participant's `stage_timestamps` (whose `common.STAGE_*` keys are frozen values)
and both computed **server-side**, never re-derived in the browser. Because the
population is the finished set, every value is a *completed* measurement, so the
mean never drifts on its own between polls. (Until 2026-08-17, avg intro time was
its own item averaging everyone *past intro*; it is now finished-only and merged
here, matched to the earnings population.)

**earnings** is one item carrying an **avg** and a **total** subsection, both over
*finished* participants only — `earned` does not exist until the results page
computes it. The **total** is summed **server-side** from the same earnings read
the row cells come from — not re-added in the browser — so it can never disagree
with the column it totals; the **avg** is that one server figure over its count,
not a second sum of the cells, so the two subsections cannot disagree either. So
the one dashboard tab carries the payment picture and nobody has to open oTree's
own Payments page. There is no `participation_fee` line — the template keeps that
fee at zero (one payment ledger; see the fee guard).

Both pills **degrade to no pill at all** early in a session, when nobody has
finished — never a `0:00` or an empty shell. Each appears only once its finished
population is non-empty.

**What people got wrong on the quiz** is an on-demand panel, opened from a quiet
ⓘ in the **Quiz** column header (the same `.th-info` affordance the State header
uses, inert until clicked). It reads entirely from data that already exists —
`intro.Player.quiz_attempt_log`, the per-round record of every graded submission
— so there is **no new tracking and no schema change**. It is fetched from its
**own route** (`/experimenter_dashboard/<code>/quiz_mistakes`) by **one fetch**
when the operator opens it, and **never rides the 2-second poll**: the panel
parses a JSON log per participant and aggregates across attempts, a cost that
grows with attempts rather than rows, and that must not lengthen every hold of
oTree's global commit lock for data nobody is watching second-by-second. Because
it is a separate route and a separate fetch, a bug in it costs the panel and
never the table (its own rule 2, one level tighter): a raising builder returns
`ok:false` and the panel shows an error strip; a missing or renamed `intro`
app degrades to a single "no data" message; **one** corrupt participant log
renders that participant "unreadable" and drops them from the counts while every
other participant still aggregates.

What it shows, all computed **server-side** so the panel and the table cannot
disagree, and every value **escaped at render** (the templates here do not
auto-escape — a reflected XSS happened once): the **first attempt only** is the
headline (later attempts are contaminated by guessing — kept underneath, never
fed into the rates), the actual **chosen option text** with **how many chose
it** worst-item-first, the **first pass and the post-re-read second pass kept
separate** (round 1 vs round 2 — the log is a per-round column, so the two are
separated for free and must never be pooled), and **blank admin-advance
submissions excluded with their count stated** (an all-blank submission is what
oTree posts for *advance slowest participants*, not a participant's answers).
Scope is both the session-level aggregate and the per-participant detail. The
panel is Escape-dismissible, styled from the dashboard's own tokens. Its look is
the approved mock (`_ai/quiz_mistakes_mock.html`, local only); the reasoning is
in DECISIONS.md (2026-08-17).

**Adding a column** is three marked places and nothing else — compute the value
in `_participant_row` (`ADD A COLUMN HERE`), add a `<th>` to `_COLGROUP_HTML`,
add the cell branch in `renderRow` (`ADD A COLUMN HERE (render)`). **Adding an
APP** needs nothing here: the timeline is the session's `app_sequence`. A
participant in an app that is NOT in their session's sequence is shown as `⁉️ app
"x" not on the timeline` with no marker, rather than being silently placed at
Entry, and a config missing an app the monitor reads by name (`outro`, `intro`,
`before`, `main`) gets a `MONITOR WARNING` in the server log at launch.

### Download data

**One press of the button at the top right of the dashboard gives plain CSV files, in
the template three of them, never a zip.** All cover **every session in the database**, whichever
session is on the screen, so they build up in a folder you then send or upload.

| File | What it holds | Example name |
| --- | --- | --- |
| **SENSITIVE** | always: oTree's raw wide export, unchanged, byte for byte what `/ExportWide` gives | `EXP_217_05-11-2026_SENSITIVE.csv` |
| **ANONYMOUS** | the same, minus the columns in `data_columns.ANON_DROP_COLUMNS`, and with `participant.participant_extra` emptied. **Only if there is something to remove** (below) | `EXP_217_05-11-2026.csv` |
| **PAYMENTS** | as many as exist, in this order: `participant.code`, the Prolific ID (`participant.participant_id_external`), IBAN (`outro.1.player.bank`), BIC (`outro.1.player.bic`), total (`outro.1.player.earned`), Prolific ID conflict (`before.1.player.prolific_label_conflict`) | `EXP_217_05-11-2026_PAYMENTS.csv` |

The name's number is `session.config.lab_session` of the session being viewed, made
safe for a file name (`217 b` becomes `217-b`), and left out when there is none:
`EXP_05-11-2026_SENSITIVE.csv`. The date is today's on the machine running the
server. `outro.1.player.earned` is the total: show-up fee + selected rounds + quiz
bonus. A PAYMENTS row has either a Prolific ID or an IBAN, and an empty total means
that participant never reached the results page. The conflict column is empty, normally.
If it is set, that person's Prolific ID claim was refused, so the ID on the row also
belongs to someone else, and the cell is the participant code of the other row: look at
both before paying either.

**Where the files go is set by the environment variable `OTREE_DATA_FOLDER`,** on
the machine running the server, and from nowhere else; no request can choose it.

- **Set:** the server writes straight into `<folder>/SENSITIVE/`,
  `<folder>/ANONYMOUS/` and `<folder>/PAYMENTS/`, which it creates when missing and
  reuses when present. The folder itself must exist already, so a typo gives an
  error naming it rather than a new folder somewhere else. Give a full path. The
  check at launch (`scripts/prelaunch_check.py`) and the server's start both say so
  if it does not exist.
  ```bash
  export OTREE_DATA_FOLDER="$HOME/Data/my_study"      # macOS, Linux
  set OTREE_DATA_FOLDER=C:\Users\me\Data\my_study     # Windows batch file or cmd, no # part
  ```
  **Think about where it points. If the folder is inside a study's git repository,
  or a synced folder, bank details can end up in git history or in the cloud.** The
  button does not refuse that; it is up to you. Add the folder to `.gitignore` if it
  lives in a repository.
- **Not set, or a hosted server:** the browser gets three separate downloads. Your
  browser may ask whether to allow multiple downloads: say yes. A visible link for
  each file stays on the screen as a fallback, until you close the box. The heading
  says "Data sent to the browser" and no more, because the server cannot see whether
  they arrived. The server keeps no copy anywhere.

**The oTree Lab Launcher sets it from 1.12.0.** Turn on `OTREE_DATA_FOLDER` in Lab
Settings to show it, then select it in Advanced and pick a folder. With an older
launcher, set the variable yourself where the server starts.

**It confirms first and never overwrites.** The confirm step lists every path. A
second press the same day gets `_2` on all the names (`EXP_217_05-11-2026_2.csv`),
so a set stays together; two tabs or a double click cannot share a name. Files are
written whole under a temp name and then moved. If one file cannot be written the
others still are.

**What the screen says afterwards.** The heading is "Data saved", and one row per file:

- **A green tick:** the name, the rows and the path. `SENSITIVE (21 rows)`.
- **A red X on a plain row:** no file, and that is right for this data. `ANONYMOUS: no
  IBAN, BIC or Prolific columns in this data`. The heading stays "Data saved".
- **A white X on a red disc, on a red row:** a real failure, with its reason. `PAYMENTS
  not saved: no permission to write there`. The heading becomes "Some files were not
  saved", or "Nothing was saved". In browser mode: "Some files were not sent", "Nothing
  was sent".
- **A yellow warning inside the PAYMENTS row:** `Did not exist in this data: Prolific ID,
  IBAN, BIC`. Hover over it for the raw column names.

**Who can press it:** it always needs oTree's admin login, even with
`OTREE_AUTH_LEVEL` unset, when the rest of the admin is open, and writing needs
oTree's CSRF token. Nothing participant-related goes in logs or error text. It runs
on a plain oTree install, without pandas. It never writes to the database, and the
disk work happens outside oTree's global lock, so a slow folder does not hold up
participants. Reasons, and what oTree's own export does here, are in DECISIONS.md
(2026-11-05).

**Things the ANONYMOUS file still holds:** `participant.code`, which links back to the
SENSITIVE file; free text such as `outro.1.player.feedback`, where a participant can
type anything; and device details such as `participant.device_info` (screen, browser),
which `format_session_data.py` blanks and this file keeps. Read those before sharing it
widely.

**A study that lacks some of these columns** (one not built from this template, say).
The rules are all in `core/data_columns.py`, plain and readable on its own, and the confirm
step says the outcome before anything is written:

- **No anonymous file if there is nothing to remove.** With none of the personal
  columns in the export, it would be a copy of the raw data that looks anonymised. The
  screen shows a red X and why; that is not a failure. Two list columns do not count as a reason:
  `participant.label`, in every oTree export, counts only if some row has a label; and
  `outro.1.player.earned` identifies nobody.
- **PAYMENTS has the columns that exist,** in the same order, and the yellow warning
  names the ones that do not. The participant code alone still counts as a file. A column that
  exists and is empty is normal.
- **A column that looks personal but is not on the list** (`payment.1.player.bank` after
  renaming `outro`, or an `iban` field) refuses the ANONYMOUS file, as a failure naming
  the column. Add it to the list in `core/data_columns.py`.

**Setting it up for your study: in `core/data_columns.py`, and nowhere else.** There is no
session config key, no box when creating a session, and no setting on any screen,
because Julian wants this behind the scenes. All of it is at the top of that file, and
the docstring of `download_files` says what it can do, with worked examples:

- **`DOWNLOAD_DATA_BUTTON = True`** is the switch, on by default. `False`: no button,
  the routes refuse, and nothing warns about `OTREE_DATA_FOLDER` at boot or in the launch
  check.
- **`download_files(rows)`** takes oTree's wide rows and returns the files: for each its
  `kind` (the subfolder and the name on screen), `table`, and optionally `ending` and
  `note`. The template's version is `split_export`, the rules above. Add a computed
  column such as a total, drop a file, or add one by app.
- **`DOWNLOAD_HELPER = download_files`** is the line that uses it. **Delete it, or set it
  to `None`, and one press makes exactly one file: SENSITIVE, the raw export,** with one
  tick and no X for files nobody asked for. So a study with no setup still gets its data,
  and no harm done. A study not built on the template's bank, BIC and Prolific columns
  will usually want this. If it keeps the template's helper, it gets the rules above: a
  red X for ANONYMOUS and a PAYMENTS file with the participant code alone.

**The wide export does not hold everything.** It has the fields, `PARTICIPANT_FIELDS` and
`SESSION_FIELDS`. What a study keeps only in `session.vars` or `participant.vars`, a chat
log say, is in no file unless its helper adds it; the docstring has the example. Read
them as `session._vars`, because oTree's `.vars` marks the row as changed on every read.

Whatever a helper returns takes the same path as the template's files: confirmed first,
never overwriting, one set number, every file reported. **A helper that raises or returns
something unusable does not cost you the raw file:** SENSITIVE is still saved, and a red
row names the problem. It runs under oTree's global lock, so keep it quick. A study's own
file carries what the study put in it, and the personal-column check covers ANONYMOUS
only.

**The total column belongs to the template.** A study not built from it has no
`outro.1.player.earned`, so its PAYMENTS file has no amount until its own total column is
added to `PAYMENT_COLUMNS`. oTree's built-in `participant.payoff` is in every export but
leaves out `participation_fee`.

## Adding, renaming or splitting apps: the experimenter monitor follows

The monitor's timeline is built **per session from its `app_sequence`** (one
step per app, in order, then Done), so adding, renaming or reordering an app
needs no dashboard edit. What a fork may set, all optional, on the app's `C`:

- **`MONITOR_LABEL`** — the step's header (absent: the raw app name).
- **`MONITOR_ROUNDS`** — the marker inside the app: `'fraction'` ("2 of 10"),
  `'number'` ("2") or `'hidden'`. Absent: `fraction` over `C.NUM_ROUNDS` for a
  multi-round app, `hidden` for a single-round one.
- **`MONITOR_ROUNDS_CONFIG`** — a session-config key capping that total, for an
  app that runs fewer rounds than it imports (`main`: `num_experimental_rounds`).
- The amber threshold: **`DASHBOARD_STALL_SECONDS_<APP>`** in `settings.py`
  (else `_DEFAULT`; `main` also reads its legacy `_TASK`).

Long labels and many steps need nothing either: the header fits itself
(`fitTimeline`, see DECISIONS.md 2026-10-03) and stays aligned with the dots;
`scripts/tests/dashboard_timeline_render_check.py` measures it for 4–9 steps.

**To split an app into several steps by page name** (as `intro` is split into
Instructions and Quiz), add one entry to `PAGE_SPLIT_STEPS` in
`core/experimenter_dashboard.py`: `'app': (('step_id', 'Label', ('PageA', 'PageB')),
...)`. A page listed nowhere sits on the app's first sub-step — list every page
after the first sub-step, or the marker appears to move backwards.

**Still bound to the template's app NAMES** (`NAME_BOUND_APPS`): earnings and
Non-SEPA (`outro`), quiz cell, quiz-mistakes panel and intro timer (`intro`),
treatment pill (`before`), terminal placement after the task (`main`'s
`task_done`). Renaming one blanks those pills (wrapped, never an error); the
server prints a `MONITOR WARNING` at launch naming them. A participant in an app
not in their session's sequence still gets the loud "⁉️ not on the timeline"
row. Then check the monitor against a real session with participants in every
app.
