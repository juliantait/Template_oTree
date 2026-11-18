# Decisions: Repository layout and docs

Read when you move or rename a file or folder, change what is tracked, or edit the docs: where things live, how the repo root is found, what tracked docs and launchers are for.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## The decision log is split into topic files under `.claude/decisions/` — 2026-11-18

`.claude/DECISIONS.md` had grown to about 4,250 lines and 100 entries, and an
agent was told to read it before changing anything. Nobody reads 4,250 lines
for a CSS fix, so in practice it was read partly or not at all. It is now
`.claude/decisions/README.md` (what the log is, how to write an entry, and one
line per topic saying when to read it) plus 14 topic files. Every entry moved
verbatim to exactly one file, newest first within each; an entry that spans two
topics went where its *Enforced* line points. References across the repo point
at the topic file, and a `## ` heading is still the unit a comment quotes.

**The fork flow changed with it.** A forked study used to copy the stub over
`DECISIONS.md`, replacing the template's log. Now the template's topic files
stay (they still explain the code the study inherits) and the study's own
decisions go in `.claude/decisions/study.md`, started from
`.claude/decisions/_study_stub.md`; where a study decision overrides a template
one, `study.md` says so and names the entry.

- **Rejected: keeping one file with a table of contents.** The point is to make
  the relevant part small enough to actually read; a contents list in front of
  4,250 lines does not.
- **Rejected: splitting by date.** Nobody looks for a decision by when it was
  made; they look by what they are about to touch.
- **Rejected: a fork still replacing the template's log.** It left a study's
  agent with no reason for any inherited mechanism, which is the helpfulness
  failure this log exists to stop.

**Enforced:** nothing automated. The split was checked once for loss (every
entry heading and every non-blank body line accounted for). The README rule
(one file per entry, newest first) relies on whoever adds the next entry.

---

## Agent material lives in `.claude/`, the codebook in `docs/`, the preview launcher in `previews/`, 2026-11-18

Decided by Julian, for a clean root: human-facing docs in `docs/`, agent-facing
material in `.claude/`.

**What moved.** `CODEBOOK.md` to `docs/CODEBOOK.md`. `docs/agents/*.md` to
`.claude/reference/` (same names). The playbooks in `docs/skills_claude/` became
Claude Code skills, one folder each with a `SKILL.md` whose frontmatter says
when to use it (`.claude/skills/writing-task/` and so on; the index is
`.claude/skills/README.md`). This log and its stub moved to `.claude/DECISIONS.md`
and `.claude/DECISIONS_stub.md`; a fork now copies the stub over this file
instead of to the root. `Preview_Instructions.command` moved into `previews/`,
next to the output it writes.

**The launcher in a gitignored folder.** `.gitignore` ignores `/previews/*` and
re-includes the launcher by name, so it is the only tracked file there and every
output stays ignored. The 2026-08-14 rule still holds: generator code never goes
into `previews/`; only the launcher and its output do. The launcher finds the
repo root by walking up to `settings.py`, not by assuming its own folder.

**Docker.** `.claude/` is excluded in `.dockerignore`: nothing in it is needed
at run time. `docs/` still ships, as before.

**Rejected:** keeping the agent reference under `docs/` (it mixed two audiences
in the folder a researcher is told to read).
**Enforced:** `build_context_test` requires the `.claude` rule in
`.dockerignore`. Nothing checks that docs keep pointing at the new paths.

---

## The shared runtime modules live in `core/`; only `settings.py` stays at the root, 2026-11-17

Decided by Julian, for a cleaner root.

**What it is.** The twelve modules the apps and `settings.py` import (`buildinfo`,
`common`, `data_columns`, `data_download`, `dot_bi`, `experimenter_dashboard`,
`fee_guard`, `health`, `identity`, `otree_routes`, `participant_tab_monitor`,
`payoff_guard`) moved from the root into the package `core/`, imported as
`from core import common`. None of them was a standalone tool, so none went to
`scripts/`.

**Why it works.** oTree puts the project root on `sys.path`, so a package at the
root is as importable as a loose module was. The old docstrings said these files
"must stay at the project root"; what was actually required is that they be
importable from the root, which `core/` is. `scripts/` would not do: it is not a
package and not on the path at runtime. `settings.py` cannot move: oTree requires it.

**The trap the move had to avoid.** Three modules found the root as "my own
directory" (`buildinfo.APP_ROOT`, `payoff_guard._ROOT`, `fee_guard._ROOT`). In
`core/` that would have read the build stamp from `core/BUILD_INFO.json` and
scanned only `core/` for payoff and fee writes, with no error. They now take
`core.REPO_ROOT`, the same marker walk to `settings.py` as `scripts/tests/_repo.py`
(2026-08-16 entry). `core/` is a package, so the guards' package rule scans it.

**Rejected:** leaving the modules at the root (a cluttered root for a template
people copy); an import shim at the root (two names for one module, the
one-concept-two-implementations defect).
**Enforced:** the full suite (`payoff_ledger_test` asserts `core/common.py` is
scanned; `build_context_test` asserts excluding `core/common.py` from the image
breaks the build check; `build_provenance_test` reads the stamp from the root).
Forks that pull from the template need the same import change in their own apps.

---

## `monitoring.py` was renamed to `core/participant_tab_monitor.py` — the old name collided with the operator monitor — 2026-08-17

A pure rename, decided by Julian, recorded because the old name was actively
misleading and someone could later "fix" it back. The module holds the
PARTICIPANT-side tab-monitor page wiring — the `MonitoredPage` /
`OutroMonitoredPage` bases that arm each page against tab-switching, plus the
`assert_monitored_page_sequence` boot guard. But "monitoring" also names the
OPERATOR's job: `core/experimenter_dashboard.py` is the live session monitor the
experimenter watches, the previews call it "the experimenter monitor", and
`docs/` and `TODO.md` discuss "the monitor" meaning that screen. One word for
two unrelated things is the collapsed-distinction rule wearing a filename — a
reader chasing "the monitor" could not tell which was meant, and the two
concepts have nothing to do with each other. `participant_tab_monitor` says
exactly which monitor and for whom.

Only the MODULE name changed. The class names (`MonitoredPage`,
`OutroMonitoredPage`) and every function (`focus_live_method`,
`monitor_js_vars`, `assert_monitored_page_sequence`, …) are untouched — they
were never ambiguous, and renaming them would have churned the whole
tab-monitor contract for nothing. English prose about "monitoring" as a
concept, and every reference to the experimenter/operator monitor, was left
alone; only mentions that name the FILE or the import symbol were changed.
**Rejected:** renaming the classes too (needless blast radius); leaving the
name (the ambiguity is real and this template is copied, so it propagates).
**Enforced:** nothing structural — a rename needs none — but `git grep -i
monitoring` returns only concept/operator uses, and the apps still import (so
`participant_tab_monitor.assert_monitored_page_sequence` still fires at boot);
`scripts/tests/task_page_test.py` imports the module under its new name and
passes.

---

## The repo root is found by walking up to `settings.py`, never by counting directories — 2026-08-16

Decided by Julian, on the evidence of the restructure that same day.

**What it cost.** Nineteen files each answered "where is the project root?" by
counting levels up from their own location, in four different spellings —
`os.path.dirname(os.path.dirname(__file__))`, `dirname(_TESTS_DIR)`,
`Path(__file__).parent.parent`, `__file__.rsplit('/', 2)[0]`. Moving `tests/`
to `scripts/tests/` made **all nineteen wrong at once**: eighteen were silently
one level short, and the nineteenth — the `rsplit` spelling — hid from the sweep
that fixed the other eighteen and surfaced only as `ModuleNotFoundError: No
module named 'settings'` on the first full-suite run. One concept, nineteen
implementations, each encoding how deep it happened to sit.

**The fix is one implementation, in `scripts/tests/_repo.py`**, exporting
`REPO_ROOT` and putting it on `sys.path` on import. Every suite and every tool
in `scripts/` now imports it; no depth-to-root count survives anywhere.

**Why a MARKER WALK and not a corrected count.** A count is only right for the
layout it was written against, so fixing the number just re-arms the trap for
the next move. What actually *defines* this root is that `settings.py` sits in
it — oTree requires that, and `core/common.py` records that it can never move. The
helper walks up from `__file__` until it finds that marker: correct at any
depth, from any working directory, with nobody needing to remember a number. It
also resolves correctly from a **staged copy** of the repo, which is how the
HTTP suites run.

**The bootstrap is deliberately depth-free too.** A file puts its OWN directory
on `sys.path` (zero levels — stable under any move) and imports `_repo` from
there. The two tools outside `scripts/tests/` reference it as a child
(`prelaunch_check.py`) or a sibling (`scripts/site_previews/*`) — facts about
`scripts/` itself, not assumptions about how far the root is.

**Rejected:** correcting the nineteen counts and moving on. That is what was
done first, and it is why the nineteenth was found by a failing run rather than
by the sweep.
**Enforced:** by construction (there is nothing left to count) and by a mutation
check: with `scripts/tests/` moved one and then two levels deeper, both old
spellings resolve to the wrong directory (`scripts/deeper`, `scripts/`) while
the helper still returns the true root and the suites still pass. Re-run that
check after any future move: it is three lines and it is the only thing that
proves the helper solves the problem rather than re-encoding it.

---

## Tracked docs are for whoever runs a study; `_ai/` stays local and is marked as such — 2026-08-14

Decided by Julian, after the sweep for the entry below found that tracked
documentation pointed into gitignored `_ai/` about fifteen times — nine in
`DECISIONS.md`, five in `README.md`, one in `CLAUDE.md`. Nothing under `_ai/` is
tracked (`git ls-files _ai/` returns nothing), so **every one of those was a dead
link in a clone**, including the recipe `CLAUDE.md` sends every agent to before
running a render check. A template whose first-read files point at absent
documents teaches the copy to distrust its own instructions.

**The test applied** is not "is this useful?" and not even "does a copy need
it?", but **"does a person running a study need it?"**. That reframing is what
made the split easy: an audit of how the dashboard was built is scaffolding no
matter how good it is; a recipe for running the render check without root is
something a researcher needs on day one.

**Three files moved to a new tracked `docs/`**: `headless_chromium_recipe.md`
(eight tracked references, and without it a copy cannot run the measured render
checks this template calls the only evidence a layout change works),
`postgres_assumptions.md` (item 8 is a gap every copy inherits), and
`group_matching_reference.py` (`main/__init__.py` tells whoever implements group
matching to read it first). Two were written into `docs/`: a researcher-facing
`README.md` — the front door, in the terms somebody running a study thinks in
rather than the terms we built it in — and a researcher-facing hosting reference
(its content was later merged into `hosting_railway.md`).

**Everything else stayed in `_ai/` and every reference to it now carries `local
only — _ai/ is gitignored; not in a clone`**, in one style, so a reader can tell
a deliberate absence from a missing file at a glance. `_ai/render_check/` and
`_ai/dashboard_render/` were deliberately NOT marked: they are output directories
created by running the checks, not documents to read, and marking them would
teach the reader that the tool is broken.

**Why `docs/` rather than the repo root or `docs/skills_claude/`.** The root already
carries the six documents everybody is told to read; adding second-tier reference
beside them makes the first tier harder to see. `docs/skills_claude/` is method
material addressed to an agent working ON the template, which is a different
audience from a researcher running a study. `docs/README.md` states the rule for
what may be added, so the next person has a test rather than a habit.

**Also settled, same theme — what belongs in a template at all.** Two
double-clickable macOS launchers were sitting untracked in the tree, having been
deliberately removed from the repo once already (`eb026e3`, 2026-07-23).
`GitHub_sync.command` is Julian's own sync convenience: kept on disk, added to
`.gitignore` by name rather than as `*.command`, so a launcher that IS template
material would still have to be ignored on purpose.

---

## `Preview_Instructions.command` is tracked — deliberately reversing `eb026e3` — 2026-08-14

Decided by Julian. `eb026e3` ("Remove local macOS launcher scripts from the
template", 2026-07-23) removed both `.command` launchers as personal tooling.
That was right for the file it removed and wrong as a permanent rule, and the
distinction is what the reversal turns on: **the launcher `eb026e3` removed drove
a stale copy of the generator; a launcher that drives the MAINTAINED generator is
template material.**

The removed one ran `previews/generate_instructions_preview.py` — a copy frozen
on 2026-05-28 inside the gitignored `previews/` OUTPUT directory, eleven lines
behind `intro/generate_instructions_preview.py` and writing the same filenames.
Double-clicking it silently replaced current previews with three-month-old
output. Deleting that was correct.

**What makes the rebuilt one travel:** every study copied from this template has
instructions, and the maintained generator is the only way to read them without
running a session — but it needs a command line, and *"I do not want to open a
terminal"* is a real requirement, not a preference to be argued with. A copied
study should not lose the no-terminal route. So the launcher is tracked, points
at `intro/`, resolves everything from its own `$SCRIPT_DIR` (no path from this
checkout), passes `--config .preview_state.json` when saved settings exist (the
generator otherwise opens a form and waits, which from a double-click looks like
a hang), and opens the interactive preview when it finishes.

**One thing it does NOT do, learned by measurement:** treat the generator's exit
code as the verdict. With no browser binary installed the generator writes both
HTML files correctly and still exits 1, because the PDF step failed. The launcher
therefore decides on WHAT EXISTS and reports the exit code only when nothing was
produced — otherwise it would tell somebody their previews were broken while they
sat there complete. (Found by dry-running it; the first draft had the bug.)

**Enforced:** nothing automated. The launcher carries a comment saying never to
point it into `previews/`, and the stale copy that caused the original problem is
still sitting in that gitignored directory for whoever looks there first.

**Enforced:** nothing automated — no check fails when a tracked file gains a link
into `_ai/`. `docs/README.md` carries the rule and the marking convention; that
is all that holds it.
