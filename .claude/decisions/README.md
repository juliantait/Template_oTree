# Decisions

The procedural and design decisions behind this template, in one place. Each
entry: the decision, the date it was settled, why (the concrete failure or
argument that drove it), what was rejected where an alternative was genuinely
considered, and — the field that matters most — **where it is enforced**: the
test, guard or CSS rule that holds it in place, or a plain admission that
nothing does and it relies on people remembering. Newest first. Entries are
deliberately short; code comments and the linked working documents hold the full
working.

The log is split by topic so you read only the part you need: read this file,
then the topic file for what you are touching. Until 2026-11-18 it was one file,
`.claude/DECISIONS.md`; a code comment or old commit that names that file means
the topic file below holding the entry it quotes.

## Writing an entry

- **Record the decision in the same change that makes it.** A reason written a
  week later is half-remembered; one never written is a bug waiting for the next
  helpful hand. The failure mode this log defends against is **helpfulness**: a
  missing config value reads as an unfinished port, inert code reads as dead
  weight, a constant only coherent at one value reads as a tunable knob, and a
  competent agent "corrects" each one.
- **Format:** `## <the decision, phrased as the choice made> — <YYYY-MM-DD>`, then
  what was decided, why, the alternative rejected, and **Enforced:** (the test,
  guard or rule that holds it, or an honest "nothing enforces this").
- **Where:** put it at the top of the one topic file it belongs to (newest
  first). An entry that spans two topics goes where its *Enforced* line points;
  add a one-line cross-reference in the other file only if a reader of that file
  would otherwise miss it. A decision that fits no topic file may start a new
  one; add it to the index below.
- **Reversing a decision:** keep the old entry, strike its title through
  (`~~...~~`) with `SUPERSEDED <date>`, and write the new entry above it.
- **A study forked from this template** writes its own decisions in
  `study.md` here, started from `_study_stub.md` (step 0 in
  `.claude/reference/editing_a_study.md`); the template's topic files stay, as
  the reasons behind the code the study inherits.

## Topic files

- [`study.md`](study.md) (forked studies only): the study's own decisions. On a fork, read it first.
- [`repository_and_docs.md`](repository_and_docs.md): read when you move or rename a file or folder, change what is tracked (the double-click launchers included), or edit the docs.
- [`settings_and_parameters.md`](settings_and_parameters.md): read when you change `settings.py`: the three controls, recruitment profiles, session-config keys, the safe accessors, or the oTree lab block (the Lab Launcher's block at the end).
- [`entry_and_identity.md`](entry_and_identity.md): read when you touch the room, the device check and its screen-out, or how a participant is identified.
- [`participant_flow.md`](participant_flow.md): read when you change the page sequence, consent, an ending, exit codes, completion codes or the Prolific redirects.
- [`task_and_treatments.md`](task_and_treatments.md): read when you swap or edit the task in `main`, the task pages, or treatment assignment.
- [`quiz_and_instructions.md`](quiz_and_instructions.md): read when you touch the comprehension quiz, its attempts rule, its logging, or the quiz bonus.
- [`payments.md`](payments.md): read when you touch payoffs, the payment ledger, the participation fee, money read from config, or bank details.
- [`screening_and_integrity.md`](screening_and_integrity.md): read when you touch the tab monitor, the focus trace, or bot and inattention detection.
- [`dashboard.md`](dashboard.md): read when you touch the experimenter dashboard (the monitor) or its admin Report tab.
- [`data_export.md`](data_export.md): read when you touch Download data, the export columns, or participant field naming.
- [`styling_and_ui.md`](styling_and_ui.md): read before changing CSS, templates, page layout, popups, button rows, the Enter key or the screen lock.
- [`previews.md`](previews.md): read when you touch the instructions preview or the website screen previews.
- [`testing.md`](testing.md): read before writing or changing a test, the geometry baseline or the asset manifest.
- [`build_and_deploy.md`](build_and_deploy.md): read when you touch the Docker image, `/health`, build provenance, `start.sh`, the predeploy check, boot initialisation or the database backend.
