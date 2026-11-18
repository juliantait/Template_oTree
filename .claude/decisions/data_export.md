# Decisions: Data download and export

Read when you touch Download data, the export columns, or participant field naming.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## The Download data result screen is a tick list, and the button is set up in code, 2026-11-05

**After using it for real, Julian asked for a confirmation you can scan:** "Data saved",
then one row per file, a green tick, the name and rows, the path small underneath. The
old screen said "All 3 files were written" with a sentence per file. The confirm step uses
the same rows and the same words. Its tick is grey, not green, because nothing has happened
yet and the principle is to claim only what was checked. The three descriptions of what each file holds went: the README has them.

**A skip and a failure both get a red X and must not read the same.** Julian asked for the
X on the expected skip so you can see what happened. So `data_download.file_state` keeps
two states: a skip is a red X on a plain row and the heading stays "Data saved"; a failure
is a white X on a red disc on a tinted row, in red words, and the heading changes ("Some
files were not saved", "Nothing was saved"). Collapsed, either a renamed `outro` reads "Data
saved" with a file missing, or every plain study reads as broken and people learn to
ignore the red. **The server decides the heading** (`result_heading`), not the page, so it
is one implementation and can be tested without a browser. In browser mode it never says
"saved", because the server cannot see a file land. A subfolder taken by a file is now a
failure on that row of the confirm step, not a box under a row with a tick on it, and the
main action counts only what can be saved.

**The missing payment columns are one yellow line in the PAYMENTS row,** in words: "Did not
exist in this data: Prolific ID, IBAN, BIC". The raw names are in its hover text only. It
lists everything missing, so a plain study also reads "total earned, Prolific ID conflict",
longer than Julian's example, because leaving out the amount would hide the one most worth
seeing.

**The button is set up in code, in `core/data_columns.py`, and nowhere else (Julian, after his lab
test).** He wants this behind the scenes, not a screen: no session config key, no box at
session creation, no dashboard control. Three things sit at the top of that file:
`DOWNLOAD_DATA_BUTTON`, `download_files` and `DOWNLOAD_HELPER`. **In `core/data_columns.py` and not
`settings.py`,** because that is where the file rules already live, so an author editing what
the button makes finds its switch beside it, and because `data_download` stays free of oTree
at import, which importing `settings` would end. Rejected: a key in `SESSION_CONFIG_DEFAULTS`,
which shows up as a box in the create-session screen, the very thing he does not want.

**The switch is on by default, and no helper means one raw file.** His reason: with no setup at
all it must still work and write the full export with the SENSITIVE tag, which does no harm.
So `DOWNLOAD_HELPER = None`, or that line deleted, gives exactly one row and one file, with no
X for files nobody asked for. The template sets the helper because its data has bank, BIC and
Prolific columns. **A plain study that keeps the template's helper still gets the earlier rule:**
a red X for ANONYMOUS and a PAYMENTS file with the participant code alone. Off means no button,
no CSS or script on the page, routes not installed, a refusal (404, not a 500) if the route exists
anyway, and nothing about `OTREE_DATA_FOLDER` at boot or in `launch_problems`.

**The helper runs with the read, under oTree's lock, not with the disk work.** It may read the
database, which needs committed data and is not safe once the lock has gone, and there it falls
under the same `no_autoflush` and rollback as the export, so a helper that says `.vars` by
mistake, or changes something, writes nothing. The price is that a slow helper holds up
participant pages; its docstring says so. Rejected: handing it a second, later read, which could
disagree with the rows.

**A helper that fails does not cost the raw file.** It gets a copy of the rows, so it cannot have
changed them; SENSITIVE is written from the original, and the failure gets its own red row (`OTHER
FILES`), so the heading says it. Its answer is used whole or not at all: half of a study's files
with no word about the rest is how a missing file goes unnoticed. Everything it returns is checked
first (`problem_with_files`), with a plain message naming the file and the problem, and a kind or
ending that could leave the folder is refused. Rejected: a helper's failure stopping the press,
because this is the rescue path.

**The wide export is not all the data.** It holds fields, `PARTICIPANT_FIELDS` and `SESSION_FIELDS`,
not what is only in `session.vars`, such as a chat log. The docstring says so and has the example,
reading `session._vars`, because `.vars` marks the row as changed on every read.

**The Micro 1 version is simpler, and that is fine.** `CREED_Helping/Micro 1 Experiment` has its own
`pit_market_live/download_data.py`: it computes `total_earned` itself and has no `split_export`. It
was tested at the lab through the launcher's folder and worked (Julian). Its button is switched off
in that repo now, by `DOWNLOAD_BUTTON_ON = false` in its admin report's script, and the route stays;
see that repo's CLAUDE.md. Nothing here depends on it, and the example of a computed total is the
same idea.

**Enforced:** `scripts/tests/download_data_test.py` sections M (a skip and a failure, the
heading), N (the switch) and O (no helper gives one file; the docstring's examples are extracted
and run, so they cannot go stale; raising and invalid helpers; no write while reading session
vars), and `scripts/tests/download_data_browser_check.py`, in a real browser on a real server.

---

## The dashboard's Download data button: one column list, no database writes, 2026-11-05

**What it is.** A button at the top right of `/experimenter_dashboard/<code>`
(`core/data_download.py`, two routes through `otree_routes`). One press, after a
confirmation listing every path: SENSITIVE (the wide export), ANONYMOUS, PAYMENTS,
each a plain CSV, all covering every session in the database. Julian downloads after
each session and keeps a folder where the files build up; he decided payments are
not limited to one session, and rejected zips because they mean unzipping and copying.

**`OTREE_DATA_FOLDER`, only from the environment.** Set: the server writes into
`<folder>/SENSITIVE`, `/ANONYMOUS`, `/PAYMENTS`. Unset, or hosted: browser downloads.
The base folder must exist and is never created, so a typo is an error naming it.
**A path inside a study folder is NOT refused** (Julian: up to people); the README
warns that bank details can then reach git. Rejected: a folder field on the confirm
step, because then a request chooses where a server writes.

**One column list, `core/data_columns.py`,** read by the button and by
`scripts/format_session_data.py`. The button needs no pandas, so it could not call the
script, and a second copy of "what makes a file anonymous" is exactly what CLAUDE.md
warns about. Moving the lists did not change what the script writes.

**ANONYMOUS also empties `participant.participant_extra`,** which the drop list does
not name. The real export showed why: a refused Prolific claim (`core/identity.py`) records the
refused ID in that JSON, so a drop list of ID columns alone leaves another person's ID
in the "anonymous" file, only in that rare case. `format_session_data.py` already
blanks the column, so the two tools agree. **Column kept, cells empty**, so the two
tools also have one shape.

**Studies that lack columns (Julian, 2026-11-05): SENSITIVE always; ANONYMOUS only if
there is something to remove; PAYMENTS with as many columns as exist.** With nothing to
remove, the file would be a raw copy that looks anonymised, which is misleading. All of
it is `data_columns.split_export`, a plain module, because Micro 1 reuses the design.
**Two list columns are not a reason to make the file, which goes beyond the literal
rule:** `participant.label` is in every oTree export, so taken literally the rule would
never fire; it counts only when some row has a label. `outro.1.player.earned` identifies
nobody, and an "anonymous" file differing only by that would mislead the same way.
Julian's example said "Only the raw file was written"; PAYMENTS always exists under his
rule 3, so the template's helper gives no anonymous file and the other two. **The confirm step
reads the export** so it can say all this before writing, at the same cost as a press,
paid only when an operator clicks. Rejected: guessing columns from the models, a second
implementation of what the export contains.

**A personal-looking column left over refuses the file, it does not get dropped.**
`ANON_DROP_COLUMNS` names exact columns, so a fork renaming `outro` would silently keep
`payment.1.player.bank` in ANONYMOUS. `data_columns.personal_columns_left` catches the
same field names at any app and round, plus `iban` and `prolific_id` spellings. Refused
rather than dropped automatically: then the button and the script would have two
different rules, and the person who renamed the app learns the list needs updating.
**No file because nothing to remove is correct; no file because of this is a failure.**
Kept apart in `skipped`, and on the screen (the next entry).

**The total is `outro.1.player.earned`, not `participant.payoff`.** Read from a real
export with `participation_fee=2`: earned 87.5, payoff 85.5, because payoff is stored as
earned minus the fee (ONE LEDGER, 2026-08-13). `earned` is show-up + rounds + bonus and
is the figure the participant's receipt shows; the export has no
`payoff_plus_participation_fee`.
**This column is the template's own.** A study not built from it has no `earned`, so its
PAYMENTS has no amount until its total is added to `PAYMENT_COLUMNS`.

**The export must not write, and left to itself it does.** oTree's `.vars` property
calls `self._vars.changed()` on every read (`otree/database.py`, 6.0.15), so
`get_rows_for_wide_csv` marks every participant and session as changed, its next query
autoflushes an UPDATE of each `_vars`, and the commit middleware commits them: every
row in the database rewritten, mid-session, by an export. **oTree's own `/ExportWide`
does this.** Here the read runs under `session.no_autoflush` and is then rolled back,
so no UPDATE is ever sent. Same values under the lock, so `/ExportWide` loses nothing
in practice, but "the export does not dirty a row" had to be made true, and a test that
only compared rows before and after did not notice: counting SQL statements did.

**The read holds oTree's global lock; the disk does not.** The lock has to cover the
read for committed data, as it does for `/ExportWide`. A folder on a network share or a
synced cloud folder can stall for a long time, and participant pages must not queue
behind that. The middleware releases the lock when the response starts, so the handlers
read first and write in the body of a `StreamingResponse`. If oTree changes that, the
files are written under the lock: slower, nothing lost. Rejected: asking for the
`/health` exemption (`exempt_from_global_lock`), which would read half-committed data.

**One algorithm for never overwriting, on every platform.** Temp file (mkstemp, owner
only) in the subfolder; `O_CREAT | O_EXCL` on the final name; `os.replace` onto that
placeholder. Rejected: `os.link` on POSIX and `os.rename` on Windows, each atomic and
with no placeholder, because the lab's machines run Windows, this is developed on
Linux, and a per-platform branch means the branch that matters never ran. The price: a
reader can see an empty file for an instant, never half a file. `os.replace` is retried
for about a second, because a Windows scanner can hold a new file open. **A number is
skipped if any of the three names has it**, so a set stays together. **One file failing
does not stop the others**: this is the rescue path, so the two that can be saved are,
and the screen says which is missing.

**Browser mode is one POST returning all three, turned into Blobs by the page,** and
not three GETs. So the three come from one read of the database (a participant finishing
between three requests would give three files that disagree), the CSRF check covers
them, nothing sensitive sits behind a GET, and the server has nothing to store. The
heading says only "Data sent to the browser". The visible links are the Blobs, and stop working
when the box closes, which releases them.

**Login and CSRF are checked here, whatever the environment says.** The dashboard opens
with `AUTH_LEVEL` unset, and AdminView skips CSRF under `OTREE_SKIP_CSRF`. These files
hold bank details, so `_Base` replaces AdminView's `dispatch` and uses only its
`_is_logged_in`. An error in either check answers 403.

**No exception text on the screen or in the log,** because one can quote a row:
`_log_failure` keeps the type and line numbers. OS errors are in plain words and hold a
path we built.

**Drift fails on the button, not at boot.** `install_download_route_or_note` never
raises; `otree.export` is looked up at press time; `launch_problems` reports both to
`prelaunch_check.py`, along with a folder that does not exist, because that typo should
be found before the session rather than at the end of it. `predeploy_check.py` keeps no
list of routes and was not changed.

**Light only.** The dashboard has one theme, so the panel has one, built from its
tokens and the quiz-mistakes overlay.

**The Lab Launcher sets the variable from 1.12.0,** in its own repository: Lab Settings
to show it, Advanced to select it and pick a folder.

**PAYMENTS carries `before.1.player.prolific_label_conflict` as a triage flag (Julian,
2026-11-05).** A refused Prolific claim keeps the typed ID in
`participant.participant_id_external`, so the ID on that row also belongs to someone
else, and someone paying from this file would not otherwise see it. The cell is the code
of the row that owns the ID. Printed only if the column exists (rule 3), and still on the
drop list, so never in ANONYMOUS. `FORMAT_PAYMENT_COLUMNS` was not asked to change and
does not have it.

**What ANONYMOUS still contains, on purpose (Julian, 2026-11-05).** "Anonymous" here means
without bank details, Prolific IDs, labels and the earned total, and no more. It still
has `outro.1.player.feedback` (free text, which can name someone), age and gender, the
device details (`participant.device_info`, `before.1.player.device_info_json`), the raw
telemetry, the tab-monitor and quiz logs, and `participant.code`, the link back to
SENSITIVE. **The two tools differ here, and that is his choice, not a missed line:**
`format_session_data.py` blanks the device blobs, the participant telemetry and those
logs, and the button does not. Feedback is blanked by neither: the script keeps it too,
unless the column averages over 1000 characters and its large-column sweep drops it. So
read the feedback before sharing either file.

**The Prolific ID stays empty rather than falling back to the label (Julian, 2026-11-05).**
`participant_id_external` is the ID the person confirmed, the value payment should use
(CODEBOOK). A label is unconfirmed, and in the lab it is a seat number. An empty cell
says truthfully that no ID was confirmed.

**No BOM (Julian, 2026-11-05).** SENSITIVE is byte for byte `/ExportWide`, which has none,
and all three files share one writer. A BOM also becomes part of the first column's name
in readers that do not strip it. The cost: Excel, opened by double click, can misread
non-English characters, for example in feedback. Import as UTF-8 there.

**The `participant.label` rule stays (Julian, 2026-11-05):** it counts as something to
remove only when some row has a label, for the reason given above.

**Enforced:** `scripts/tests/download_data_test.py`,
`scripts/tests/download_data_browser_check.py`, and the new section of
`scripts/tests/format_session_data_test.py` (no second copy of the list);
`prelaunch_check.download_problems`. **Not enforced:** nothing has run on real Windows;
`ntpath` tests the spelling of paths and `os.replace`'s retry is simulated. Postgres was checked by hand on this date (a press writes no row, by its own counters; `/ExportWide` does) and has no test here. Safari and
Firefox are not run. Rows in PAYMENTS for people who never reached the results page have
an empty total, on purpose; nothing checks anyone is paid.

---

## Participant tracking fields are named family-first, so an export groups by outcome — 2026-08-17

Decided by Julian. Every participant field about one outcome now shares that
outcome's prefix, so the columns sort into families instead of scattering: the
tab monitor's fields (`tab_monitor_disqualified`, `tab_monitor_focus_loss_count`,
`tab_monitor_focus_loss_count_outro`, `tab_monitor_focus_event_ids`,
`tab_monitor_focus_events`, `tab_monitor_focus_losses_missed_at_least`, joining
`tab_monitor_flag` / `tab_monitor_where` which already read this way);
comprehension's (`comprehension_failed_attempts`, `comprehension_reread_used`,
joining `comprehension_disqualified`); and the screen-out's `screenout_active`
(joining `screenout_cleared`, and the `screenout_cause` / `screenout_history`
keys already inside `participant_extra`). The shape is **family first, unit
last** — roughly `family_object_measure` — and it is written up in
`docs/conventions.md`.

The old names named the *measure* and lost the family: `focus_loss_count`,
`failed_attempts`, `screened_out` each sat alone in the export next to unrelated
columns, and a reader could not see at a glance that six columns were all one
instrument. The rename is deliberately **data-facing and complete** — a
half-renamed field is a `KeyError` at runtime, not an import error, because
`participant.vars` is a string-keyed store — so it reached every read and write
across the apps, the guards, the dashboard, the templates, the JS, the tests and
the docs, verified by grepping each old name to zero.

**`tab_monitor_disqualified` is the one rename that crosses the cover story.**
The field was `ai_safety_disqualified` because the participant-facing framing is
an "AI-safety" agreement; the data should name the *mechanism* (a tab-switch
monitor), so the column is `tab_monitor_*` like its siblings. The framing itself
did **not** move: the `AISafetyAgree` page, `_static/global/js/ai_safety_monitor.js`,
and every word a participant reads stay exactly as they were. Only the data name
changed. (Those two code symbols — the page class and the script — WERE later
renamed to `TabMonitorAgree` and `tab_monitor.js` on 2026-08-17, when the code and
docs were made to name the mechanism the tab monitor throughout; see that entry.
The participant copy still did not move then either.)

**This is a CONVENTION, not a rule, and there is deliberately no import-time or
boot-time check that enforces it** — a considered exception to this template's
habit of enforcing invariants at boot (`prelaunch_check.py`, the frozen-config
guard, the exit-code table). A study copied from this template may reasonably
want different field names for its own outcomes, and a boot check would turn that
ordinary choice into a failure to work around. The absence of a check is the
decision, not an oversight. **Rejected:** keeping the measure-first names (the
export does not group, and the tab-monitor family is invisible); renaming the
participant-facing AI-safety wording too (that is the study framing, not data);
adding a boot check that field names match the pattern (wrong for a copied
study). **Enforced:** nothing at boot, by design — held by `docs/conventions.md`,
this entry, and the field lists in `settings.PARTICIPANT_FIELDS` and `docs/CODEBOOK.md`
being the single documented source. The suites that touch these fields
(`dashboard_test`, `task_page_test`, `identity_test`, `tab_monitor_detail_test`,
`full_journey_test`, `screenout_softwall_test`) go red on a half-done rename.
