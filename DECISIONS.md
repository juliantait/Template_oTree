# Decisions

The procedural and design decisions behind this template, in one place. Each
entry: the decision, the date it was settled, why (the concrete failure or
argument that drove it), what was rejected where an alternative was genuinely
considered, and — the field that matters most — **where it is enforced**: the
test, guard or CSS rule that holds it in place, or a plain admission that
nothing does and it relies on people remembering. Newest first. Entries are
deliberately short; code comments and the linked working documents hold the full
working.

---

## The tab monitor is named the tab monitor everywhere in the code and data — the "AI-safety" name survives only in the participant's agreement — 2026-08-17

Decided by Julian. The integrity module that watches whether the study tab
loses focus was called the "AI-safety" monitor in much of the code and docs —
the class `AISafetyAgree`, the script `ai_safety_monitor.js`, the js_vars key
`AI_SAFETY_CONFIG`, the `sessionStorage.aiSafetyAgreed` handshake, the stage
value `ai_safety_agreed`, and a scatter of comments and prose. **That name
overclaims: the mechanism detects a tab losing focus, not AI use.** So the
mechanism is now named the *tab monitor* wherever the code or docs NAME or
DOCUMENT it: `AISafetyAgree` → `TabMonitorAgree`, `ai_safety_monitor.js` →
`tab_monitor.js` (snake_case, matching `quiz.js`/`global.js`), the config and
handshake identifiers → `TAB_MONITOR_CONFIG` / `tabMonitorAgreed`, and the stage
value → `tab_monitor_agreed`.

**What deliberately did NOT change: the participant-facing copy.** The agreement
page still asks the participant not to switch to other tabs "(including AI
assistants)" and still frames the promise as an AI-safety agreement — because
that is the agreement the participant is actually making about how they take
part, not a description of the mechanism. The mechanism naming and the study
framing are two different things, and only the first overclaimed.

**The stage value was changed even though stage values are frozen** (`common.py`
STAGE_* block). The freeze protects LIVE studies whose exports are keyed on the
old spelling; this template has no data, a running study carries its own copy of
the code, and pushing a template change over a live session is forbidden
elsewhere. The export key is documentation too, and `ai_safety_agreed`
overclaimed in the data exactly as the prose did. The freeze rule still stands
for every other value; this is the one documented exception, recorded at the
definition so it does not read as an accident.

**Rejected:** renaming the participant copy too (that is the study framing, not a
description of the mechanism — the same line drawn for `tab_monitor_disqualified`
on 2026-08-12, see below); keeping the stage value frozen (it documents the same
overclaim in the export). **Enforced:** nothing at boot — held by this entry, the
frozen-values note in `common.py`, the CODEBOOK stage table, and the test suites
(`dashboard_test`, `task_page_test`, `tab_monitor_detail_test`, `full_journey_test`,
`gated_flow_test`) which reference the class and stamp and go red on a half-done
rename.

## The quiz-mistakes panel is on-demand, first-attempt-only, and reads only what already exists — 2026-08-17

Decided by Julian; design in `_ai/quiz_mistakes_spec.md` and the approved mock
`_ai/quiz_mistakes_mock.html` (both local only, `_ai/` is gitignored). The
dashboard gains an on-demand panel — a quiet ⓘ in the Quiz column header — that
shows what people got wrong in the comprehension quiz and what they answered
instead. It reads entirely from `intro.Player.quiz_attempt_log`, the per-round
record already written by `intro.log_quiz_attempt`: **no new tracking, no
participant field, no schema change.**

The load-bearing choices, each of which had a wrong alternative:

- **On demand from its OWN route, never on the 2-second poll.** The main poll is
  deliberately a cheap walk of one session's rows under oTree's global commit
  lock; this parses a JSON log per participant and aggregates across attempts, a
  cost that grows with *attempts*. Putting that on every tick would lengthen
  every hold of the lock and delay participant pages, for reference data nobody
  watches second-by-second. *Rejected:* folding it into `/data`.
- **The headline is the FIRST attempt only** (`n == 1`). Later attempts are
  contaminated by guessing; they are kept underneath (the per-participant
  expander) but never feed the rates or the chosen-option counts. *Rejected:*
  pooling all attempts, which would make a hard item look learnable purely
  because people eventually guessed it.
- **The two passes are never pooled.** Round 1 is the first pass, round 2 the
  lab re-read pass; because the log is a per-round column they separate for
  free. Pooling them would answer a different question with one number.
- **Correctness comes from the stored `wrong` list, never recomputed** against
  today's `quiz_items` (which change between studies and sessions); `answers` is
  used only to recover the chosen option text, shown verbatim and escaped.
- **Blank admin-advance submissions are excluded and the count stated.** An
  all-blank submission is what oTree posts for *advance slowest participants*
  (the same mechanism `_quiz_outcome_map` documents), not a participant's
  answers; a blank first attempt drops that participant from the headline and
  into the excluded tally, rather than being promoted to "first attempt".
- **Degrades one level tighter than the dashboard's rule 2**: a bug here costs
  the panel, never the table. It is a separate route and a separate fetch, so a
  raising builder returns `ok:false`, a missing/renamed `intro` app returns
  `available:false` (a single "no data" message, not an error), and one corrupt
  log renders that participant "unreadable" while every other participant still
  aggregates.
- **Escape-dismissible, styled from the dashboard's own tokens** (the mock's
  tints carried over so it reads as the same control room), reusing `.th-info`
  for the trigger and adding no colour outside the palette.

**Enforced:** `scripts/tests/dashboard_test.py` §F drives the `/quiz_mistakes`
endpoint over real HTTP (real content, the two passes unpooled, blank excluded +
counted, the three degradations, and the answer text carried for escaping);
`scripts/tests/dashboard_render_check.py` opens the panel in real Chromium and
measures that a hostile answer is escaped into the DOM (injecting no element),
the passes render side by side, the exclusion note states its count, later
attempts expand, and Escape closes it. The monitor site-preview is regenerated
from this file (`scripts/site_previews/`).

## The summary strip is two merged pills over ONE finished population, and shows nothing until someone finishes — 2026-08-17

Decided by Julian. The strip below the table gains a **time** pill in the same
shape as the merged **earnings** pill: one item labelled `time` with two
subsections, **avg intro** (mean time in the intro app) and **avg completion**
(mean time for the whole run, the *first* stamp to the *finished* stamp, read
from `participant.stage_timestamps` whose `common.STAGE_*` keys are frozen
values). Both figures are summed **server-side** in `_time_summary`, exactly as
`_earnings_total` sums the earnings, and never re-derived in the client — the
one-number-in-one-place discipline the whole dashboard is built on.

The load-bearing choices:

- **Both subsections are over FINISHED participants only — one population,
  stated once.** This is Julian's explicit call and is *not* to be reopened: the
  strip is an at-a-glance operator impression, not an analysis statistic, so it
  carries one denominator and no per-subsection population wording. The
  consequence, handled honestly: the pre-existing **avg intro time** item, which
  averaged over everyone *past intro*, is now finished-only and **merged into
  this pill** — it stops being its own item, matched to the earnings population
  it sits beside. *Rejected:* keeping intro time over the wider "past intro"
  population, which would have put two different denominators side by side again
  — the very thing merging the earnings pill removed.
- **Early in a session it is NO PILL AT ALL.** Nobody has finished, so both
  means are undefined; `_time_summary` returns `n=0` and the client shows
  nothing — never `0:00`, never an empty shell — exactly as the earnings pill
  already degrades. A participant is counted only once they carry a
  `STAGE_FINISHED` stamp *and* both durations are computable, so a missing stamp
  drops them from BOTH means together and the single denominator stays honest.
- **Same rules as everything else on this screen:** read-only (it reads
  `pp._vars`, never `.vars`, and assigns nothing), degrades to `n=0` rather than
  raising, adds no colour outside the palette (the subsections reuse `.pill`),
  and survives the narrow viewport the render check drives.

**Enforced:** `scripts/tests/dashboard_test.py` §D asserts `time_summary` covers
exactly the finished participants (one shared denominator with the finished
rows), both means present with completion ≥ intro, and the `n=0` no-pill
degradation paired with earnings; §D7 asserts the served page ships the merged
`time` pill markup reading `data.time_summary`. `scripts/tests/dashboard_render_check.py`
measures the two merged pills side by side over the same `of 2 finished`
population, that the old "past intro" item is gone, and that nothing clips or
scrolls. The monitor site-preview is regenerated from `experimenter_dashboard.py`
(`scripts/site_previews/`).

## The dashboard may fail a LAUNCH loudly, but never a running session silently — 2026-08-17

Decided by Julian, from the empirical blast-radius study
(`_ai/dashboard_blast_radius.md` — local only, `_ai/` is gitignored — which broke
the experimenter dashboard five ways against a real oTree and recorded what each
did to oTree's own admin pages). **The governing rule: failing at LAUNCH is
acceptable, because whoever is setting the study up sees the error and fixes it;
failing LATER is not, because a study that boots clean and then dies when an
operator clicks the admin Report tab mid-session costs a session.** A boot-time
failure is therefore NOT to be softened into a silent one.

**What was fixed — the one gap that boots clean and fails later (scenario 4).**
`URL_BASE` renamed consistently *inside* `experimenter_dashboard.py` while the
cross-file read in `outro.vars_for_admin_report` is missed. The boot succeeds; the
first click on oTree's own Report tab (which oTree calls **unguarded**,
`AdminReport.get_context_data`) then 500s on the `AttributeError`. Fixed in **both
directions**: at RUNTIME, `vars_for_admin_report`'s `except ImportError` is widened
to `except Exception`, so *any* failure reading the constant falls back to the
literal `/experimenter_dashboard` URL instead of 500ing — its docstring, which had
argued the import was the only thing that could fail, is corrected because the
study proved otherwise. At LAUNCH, `scripts/prelaunch_check.py` gains a
`dashboard_problems()` section (module imports, `URL_BASE` exists,
`vars_for_admin_report` returns a plausible URL without raising, routes install),
so the rename is caught before launch rather than by a curious click three hours
in. The two are complementary: the runtime fallback stops the 500, `URL_BASE
exists` stops the stale link ever shipping.

**What was deliberately LEFT failing at boot.** An earlier instinct was to wrap
the `import experimenter_dashboard` trailer at the end of `outro/__init__.py` in a
`try/except` so a module-level error there (scenario 3), or a wholly missing
`URL_BASE` definition, would fail soft. **Rejected on Julian's rule:** a genuine
import-time error in the dashboard module is a code breakage the person launching
must see and fix, and softening it to a silent 404 is exactly the later-invisible
failure the rule forbids. The bare `import experimenter_dashboard` stays
unguarded, and it stays the LAST lines of the LAST app module for the reason
already documented there.

**The one boot-time defect that WAS fixed — a reporter that fails on what it
reports (scenario 4′).** `install_dashboard_route_or_note` builds its "NOT
INSTALLED" message with an f-string that interpolated `{URL_BASE}` — so when
`URL_BASE` is the missing symbol, the handler raised a SECOND `NameError` while
formatting the message meant to reassure the reader, and that escaped the
unguarded call site and killed the boot. This is not the same as scenario 3: the
message must never depend on the symbol that may be the very thing missing. The
messages now use the literal `/experimenter_dashboard` (the same string `URL_BASE`
holds and the same fallback `vars_for_admin_report` trusts); the sibling
`note_admin_tab_problems` was hardened the same way. A failure-reporter that can
fail on the thing it reports is no reporter — fixing it lets an install failure be
*reported and swallowed as designed* rather than double-faulting the boot.

**Rejected:** wrapping the outro import to fail soft (softens scenarios 3/4′ into
silent 404s — against the rule); leaving `except ImportError` and calling the
Report-tab 500 "narrow, one tab" (an operator loses a live monitoring surface
mid-session for a rename a launch guard can catch); a boot-time assert on the
dashboard (identity's discipline is right for a participant 500, wrong for an
operator convenience — the module's own first rule). **Enforced:**
`scripts/tests/dashboard_test.py` §D9 drives `/AdminReport` over real HTTP with
`URL_BASE` deleted and asserts the tab renders (200 + a working link, not merely
"< 500"), asserts the install reporter returns `drift` without raising when
`URL_BASE` is absent, and §D10 asserts `prelaunch_check.dashboard_problems()` is
clean on the healthy template and reports a `URL_BASE` problem when the constant
is renamed away — each paired with its positive control (CLAUDE.md: never assert
an absence without the matching presence).

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
this entry, and the field lists in `settings.PARTICIPANT_FIELDS` and `CODEBOOK.md`
being the single documented source. The suites that touch these fields
(`dashboard_test`, `task_page_test`, `identity_test`, `tab_monitor_detail_test`,
`full_journey_test`, `screenout_softwall_test`) go red on a half-done rename.

## The single oTree room was renamed `experiment` → `study`, so the URL reads `/room/study` — 2026-08-17

Decided by Julian. The participant-facing room URL is the one bit of plumbing a
participant actually sees (it goes in the Prolific study link and on printed lab
sheets), so its name should be neutral — not `experiment`, which reads as jargon,
and deliberately not anything that commits the URL to a lab or an online framing.
`study` is the right neutral word for both: it is what Prolific already calls the
thing, and a lab participant reading `/room/study` is not misled either. The
display name moved in step: `Experimental Session` → `Study Session`.

There is still exactly **ONE** room. This is the whole point — the same room
serves both study types (`prolific` and `lab`); the study type is one of the
three orthogonal controls resolved in `settings.py`, and it is not the room's job
to encode it. A second room for lab-vs-Prolific would duplicate the room-welcome
gate and the start.sh binding for a distinction the config already draws.

**Practical consequence — matters for a deployed study, not for this template:**
a room is bound to a name, so any session already bound to `/room/experiment`,
and any bookmarked or printed `/room/experiment` link, stops resolving the moment
the name changes. For this template there is no live session and no circulated
link, so the rename is free; for a study already in the field it would strand
participants and must not be done mid-run. **Rejected:** two rooms (defeats the
one-room-serves-both design); keeping `experiment` (leaks jargon into the one
URL a participant sees). **Enforced:** `settings.ROOMS`; the room tests bind to
`study` (`room_gate_test`, `identity_test`, `full_journey_test`,
`render_check`), so a half-done rename fails to bind a session and goes red.

## `monitoring.py` was renamed to `participant_tab_monitor.py` — the old name collided with the operator monitor — 2026-08-17

A pure rename, decided by Julian, recorded because the old name was actively
misleading and someone could later "fix" it back. The module holds the
PARTICIPANT-side tab-monitor page wiring — the `MonitoredPage` /
`OutroMonitoredPage` bases that arm each page against tab-switching, plus the
`assert_monitored_page_sequence` boot guard. But "monitoring" also names the
OPERATOR's job: `experimenter_dashboard.py` is the live session monitor the
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
it — oTree requires that, and `common.py` records that it can never move. The
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

## The screen-out exit says it is FINAL, because the code that frees the place forecloses the return — 2026-08-15

Decided by Julian, the same day as the per-population completion codes, and it
is the consequence of that decision rather than a separate one.

**What forced it.** The soft wall was designed around a re-decidable verdict: a
participant turned away at entry is HELD on `before.welcome`, the page's primary
ask is "switch to an accepted device and come back", and returning on an
accepted device before consent CLEARS the screen-out. The reversal recorded
above gave the screen-out its own completion code, chosen because an open
submission is limbo — it occupies a place and tells Prolific nothing. But a
completion code RETURNS the submission, and a returned submission can never be
retaken. **So for anybody who presses the exit, the route the page invites them
to take is gone.** Freeing the place was judged the better trade; being silent
about what it costs the participant was not.

**What the page now says**, in the `show_return_link` branch of
`before/screened_out.html`: *"Once you return it you cannot take part again,
even on an accepted device."* It replaces *"Once you do this you will not be
able to take part later"* — true, but on this page it reads as "not later
today", three inches under an invitation to come back on a different device.
The new sentence names the route it closes.

**What was deliberately NOT done.** It is one sentence in the page's existing
register, not a warning banner, and the control is untouched: it stays
`.exit-button`, never `.next-button`, because `global.js` Enter-clicks the first
`.next-button` on a page and an irreversible exit must not be one keystroke
away. The primary ask is still switching device, and the switch-device branch
still says *"Do not press the button below."*

**The honest statement of what survives.** The soft wall still exists and still
clears on an accepted device before consent — but only for somebody who has NOT
taken the exit. Those are now two different populations and the page has to be
readable by both.
**Enforced:** `scripts/tests/screenout_softwall_test.py` asserts the accepted-device
clause specifically (not merely that some permanence wording exists, which the
old sentence would also have satisfied), that the control carries
`.exit-button`, and that the way out is a real `<a href>` needing no script;
`scripts/tests/render_check.py` asserts the switch-device branch's "Do not press the
button below".

## The website's screen previews are GENERATED from the template, not drawn — 2026-08-15

Decided by Julian. The academic site shows several screens of the study (welcome
lab, consent lab, instructions, a decision screen, results lab; the experimenter
monitor was added 2026-08-16, see below). They used to be hand-written
one-off HTML snapshots, and by August they no longer looked anything like the
template.

**The failure is not that they were wrong; it is that nothing could tell.** A
snapshot has no relationship to the CSS it imitates, so when a shared component
moved, the snapshot went on rendering perfectly — just as a picture of an older
study. No error, no failing test, no visible symptom: the same silent-drift
shape as the client-side traps in `CLAUDE.md`. So the previews are now DERIVED —
`scripts/site_previews/build_site_previews.py` inlines `_static/global/css/` **verbatim**
(the stylesheets are never re-typed) and embeds the logos as data URIs, giving
one standalone file per screen with no external reference of any kind, because
they load in an iframe on a static site with no access to this repo.

**Source is tracked; output is not.** The script and
`scripts/site_previews/bodies/` are in the repo; the built files land in
gitignored `_ai/site_previews/`. A generator living in `_ai/` would die with the
container and the next person would hand-write another one-off — which is the
defect, restored.

**The screen is drawn on a fixed 1920x1080 canvas inside a nested `srcdoc`
frame**, scaled to the iframe by `calc(100vw / 1920px)` (a length over a length
is a number; no script, so it survives scripts being blocked). The frame is not
decoration: the template sizes itself in viewport units — the card is `88vh` and
`base.css` tightens its rhythm below 820px of height — so "what the template
looks like" is only defined at a given screen size, and rendered raw a small
iframe would be a different, clipped layout from a large one. Inside the nested
context those units resolve as they do for a participant on a 1080p display.

**Two honest departures, stated in the artefacts themselves** rather than only
in the hand-off message the files outlive: the decision screen is INVENTED (this
template ships no game screen — `main/game.html` is a placeholder — so it is
built only from real components, and must not be copied back into `main/`), and
the results screen is TRIMMED (the real page is the longest in the study and
genuinely scrolls inside its card; with the payoff table open it does not fit
16:9 at any size, so the greeting line is dropped and a short session shown).
**Enforced:** `scripts/site_previews/check_site_previews.py` — measured in headless Chromium
at four 16:9 sizes with JavaScript on and off: no external request, the canvas
viewport is the one composed for, no cut-off scroll region, the card fills, and
the lab screens name Prolific in no **rendered** text (asserted on `innerText`,
paired with a minimum-text assertion, because an absence check alone passes
against a blank page). Re-running after a CSS change is enforced by nothing —
it is a note in `CLAUDE.md`'s styling section and in `previews/SUMMARY.md`.

## The monitor preview is RENDERED BY THE DASHBOARD AND FROZEN, not hand-written — 2026-08-16

Requested by Julian: put the experimenter monitor on the academic site as a
sixth preview, same 1920x1080 canvas as the others.

**It could not be built like the other five, and the reason is worth keeping.**
Every participant preview is a hand-written body in
`scripts/site_previews/bodies/` composed of real shipped components, with the
real stylesheets inlined. The monitor has no body to write: `experimenter_dashboard.py`
serves a shell whose `<tbody>` says `Waiting for first data…`, and every row,
timeline marker, pill and quiz cell is built by that file's own `renderRow` /
`stateHTML` / `timelineHTML` in JavaScript from the poll's JSON. Hand-writing
those rows would have been **a second implementation of renderRow** — the
inverted collapsed-distinction rule in `CLAUDE.md`, and the drift would have
been invisible: a pill that changed shape in the dashboard would go on looking
right in the preview forever.

**So the build runs the real page.** `build_monitor` imports `_PAGE_HTML`
(stylesheet, script, header cells and step list all already resolved from
`STEP_LABELS`), inlines base.css in place of the `<link>`, stubs `fetch` to
return the invented session in `scripts/site_previews/monitor_session.py`, loads
it in headless Chromium, waits for the poll to paint, and **freezes the DOM with
every `<script>` stripped**. The output is markup the dashboard itself produced,
needing no server and no JavaScript — which is what earns it the same
scripts-disabled guarantee the other five have for free. The cost, stated: this
one screen makes the generator depend on Playwright at build time (the five
participant screens still build on the standard library alone).

**It is a LAB session, and that is why it shows no "ended early" rows.** All
four terminal states need a module `RECRUITMENT_PROFILES['lab']` switches off —
`device_capture` (📵 screened out), `explicit_consent` (✋ declined), `comprehension_dq`
(❌), `tab_monitor` (👀) — so a real lab monitor never shows one. Putting them on
anyway would repeat the exact error that once shipped a consent preview with a
radio button no lab participant has ever seen. The built file says this in its
own header, because an absence on a picture reads as a missing feature.

**The data is invented and the file is public**: seat numbers, no Prolific IDs
(a Prolific row's label IS the platform ID), no completion codes, no contact or
bank details — the screen has no column for any of those.

**Enforced:** `check_site_previews.py` asserts the frozen page has the expected
row count (imported from the fixture, not typed) and at least one of each mark
the fixture exists to demonstrate — the timeline markers, the done tick, green
finished rows, amber stalled rows, dimmed not-arrived rows, all four quiz-cell
states, the earnings and live-timer pills, the Non-SEPA pill, the code fallback
and the averages strip. Without that, the way this preview fails is a freeze
caught before the paint: an empty or half-drawn table, which trips no geometry
check and is indistinguishable from a working one at thumbnail size.

**Known and accepted: it is not readable at grid-thumbnail size.** Measured
2026-08-16, apparent text in a two-up 590px tile is 3.3–5.7px; at a 1280px tile
the smallest labels are 7.3px. The screen reads as *shape* — a session table
with colour-coded rows — rather than as data at anything below full size. It is
the one preview whose value IS the data, so it wants a full-width tile or a
link to the full-size render; that is a website decision, left to Julian.

## One canvas for every preview, and the empty space on the short screens is accepted — 2026-08-16

Decided by Julian, reversing a change made the day before. `consent_lab.html`
had been moved to a **1152x648** canvas while the other screens stayed on
1920x1080. The reason was real: the shipped lab consent copy is genuinely short
(242px of content against ~700px for an instructions step) and floated in a
white void, and because `base.css` caps type at 19px from roughly 800px of width
upward, a smaller canvas shrinks the 88vh card while the text stays put — so the
copy fills more of it.

**What that missed is that the screens are shown side by side.** A tile scales
its canvas by `tile_width / canvas_width`, so the smaller canvas was scaled UP
1920/1152 = **1.67x** more than its neighbours: the same tile size, half again
the apparent text size. Julian saw it in the grid and chose the void. So the
canvas is now ONE constant for every screen, and **the empty space on the short
screens is the accepted outcome** — the shipped consent page really is that
short, and consistent scale across the grid matters more than a filled frame.

**The rejected alternative is the important half:** do *not* pad or lengthen the
consent copy to fill the frame. This preview goes on the website as what the
template produces, so it carries the literal shipped copy — a fuller consent
page here would be a picture of a study nobody ran, and a disclaimer in a file
header is invisible to somebody looking at the picture. (Same reasoning as the
INVENTED/TRIMMED notes on the entry above; those two departures are stated on
the artefacts because they could not be avoided. This one can be, so it is.)

**Why a constant and not a table of overrides that happen to agree:** the
uniformity *is* the decision, so it is expressed as something that cannot vary.
`check_site_previews.py` **imports** the constant rather than restating it —
one fact, one place, per `CLAUDE.md`'s two-implementations rule.

**Enforced:** `scripts/site_previews/check_site_previews.py` now also measures
the scale factor each tile applies and fails if the screens disagree by more
than 0.005. No per-screen assertion could catch this — every screen filled its
own tile perfectly on either canvas; the fault existed only *between* them.
Measured 2026-08-16 at four 16:9 sizes: all five screens report canvas
1920x1080 and identical scales (1.000 / 0.667 / 0.500 / 0.375), and the consent
screen renders complete with overflow +0 and its card inside the canvas.

## Every ending population gets its own completion code — 2026-08-15

Decided by Julian. Five endings, five codes, one per population:

| key | population | Prolific action |
|---|---|---|
| `prolific_cc_code` | completed | **auto-approve** |
| `prolific_noconsent_code` | declined consent | request return |
| `prolific_dq_quiz_code` | comprehension DQ | request return |
| `prolific_dq_tab_code` | tab-monitor DQ | request return |
| `prolific_device_code` | device screen-out | request return |

**Why not one shared `DQ-` code, which is what this replaces.** A shared code
**collapses two populations irreversibly, on a system we do not own.** Once a
comprehension failure and a tab-monitor ejection have both submitted under one
code, Prolific's submission list cannot tell them apart and nothing downstream
recovers it — not an export, not a rerun, not a support ticket. This is the
collapsed-distinction rule applied to a third party: the usual version of that
rule costs a debugging session, and this version cannot be fixed at all, which
is why it had to be got right before a launch rather than after one.

**THIS REVERSES the codeless screen-out** recorded on 2026-08-12 (marked
SUPERSEDED above, with its reasoning preserved). That decision was right that a
completion code closes a submission and a returned submission cannot be retaken.
It was wrong that leaving the submission open was therefore kind: a bare
researcher URL leaves it in limbo, occupying a place, telling Prolific nothing.
A **REQUEST_RETURN** code is a different instrument — it prompts the participant
to return the submission, which frees the place. So the screened-out exit is now
`prolific_device_code` rendered as a full completion URL, and the
`prolific_screenout_return_url` setting is gone: a URL that embeds a code, plus
a code key, is one value in two places and they drift.

**Rejected:** keeping `prolific_screenout_return_url` alongside the new code as
an override. Two sources for one value is the defect this repo has spent the
week removing.

**THE HAZARD THE SPLIT CREATES, AND THE RULE THAT CLOSES IT** (bossman-52, same
day). Splitting the DQ code invents a failure mode that could not exist while one
code served both populations: **if the displayed reason text and the completion
code are derived independently, they can silently disagree** — a comprehension
failure reads the quiz explanation and carries the TAB code back to Prolific. No
error, normal-looking data, and the population distinction corrupted at exactly
the point it was created to exist, findable only by reconciling submissions by
hand. **So the message and the code must come from ONE read of the cause.**

Verified today, and it is the safe shape already: `outro.dq_cause` is the only
implementation (`outro/__init__.py:51`); `Ended.vars_for_template` passes
`dq_cause=dq_cause(player)` and `outro/Ended.html` branches on that variable;
`completion_link` does `cause = dq_cause(player)`. No template reads
`tab_monitor_disqualified` or `comprehension_disqualified` directly — checked
across every `.html` in the repo. Two calls to one deterministic function in one
request cannot disagree; two implementations could, which is why the invariant is
written on `dq_cause` itself. **The next reader will see two calls and want to
refactor one away — that is the thing not to do.**

**Enforced, and each part separately verified:**

- `settings.PROLIFIC_CODE_KEYS` is the ONE enumeration; `_prelaunch_problems`
  iterates it rather than keeping a copy, so a sixth ending cannot ship
  unguarded. **Mutation-tested key by key**: with the other four set to
  plausible real codes, leaving each one placeholder in turn is named by the
  check — and only that one (no false positives). The old three-key enumeration
  would have shipped the two new codes completely unguarded while reporting
  clean, which is the trap this template keeps meeting.
- The frozen-session audit needs no enumeration: it walks every key in the
  current config, so the new keys are covered the moment they exist.
- `scripts/tests/completion_codes_test.py` — **one browser-driven journey per ending**,
  each asserting it carries ITS OWN code and NOT the other four. 30 checks, all
  passing. The absence half is the point: a disqualified participant who can
  read the COMPLETED code out of page source can self-approve and be paid, so
  every path checks all four others, and the codes are injected per page rather
  than bundled into the template context.
- `scripts/tests/render_check.py` leg AD asserted the screen-out carried NO code; that
  expectation is now reversed to assert it carries the DEVICE code and none of
  the other four.
- Two test-construction faults were found and fixed while writing the above,
  both worth knowing because they would have produced false confidence: a walker
  using the default `python-requests` User-Agent is classified `unknown` and is
  SCREENED OUT by `allowed_devices=['computer']`, and setting a DQ flag on a
  participant still at the consent page does not put them on their ending. In
  both cases the code assertions passed against the wrong page until the journey
  itself was asserted.

## `participation_fee` ships 0, and a boot guard holds it there — 2026-08-14

Decided by Julian. oTree's built-in `participation_fee` is a SECOND payment
channel: it is not part of `participant.payoff`, it is added on top of it by
`Session._get_payoff_plus_participation_fee` (otree/models/session.py:242-248),
which feeds the admin Payments page (`otree/views/admin.py:274`,
`templates/otree/SessionPayments.html:46`) and the MTurk payment table. It does
NOT reach the CSV export — verified against 6.0.15, the participant column list
ends at `payoff` (`otree/export.py:76-96`) — so a fee is invisible in the data
and visible only where a human reads off what to pay, which is worse. This template keeps **one payment ledger** — the base is
`showup`, which `outro.compute_final_payoff` folds into `participant.payoff` with
the bonus, so the admin figure equals the amount actually owed. A non-zero fee
splits that across two numbers computed by different code in different places,
which is the condition the single-ledger decision exists to prevent.

**Why a guard and not just a zero in the config.** A zero in a config is a
convention, and an unenforced convention in a template drifts the first time
somebody copies it. `participation_fee` is a standard oTree knob that the
official docs and tutorials set; a researcher starting from this template will
meet it there and set it in good faith, with no error to say the payment record
has quietly split. This repo has already had one convention-only rule turn out to
be nothing (three documents calling oTree's `player.payoff` raise "enforcement"
when it fires inside a participant's request).

**Boot, never request time** — the `payoff_guard.py` precedent, and the reason is
the same: oTree has no migrations, so an upgrade under live sessions is how every
study built from this template is actually deployed, and a check that fires in a
request is a dead page for whoever is mid-study. `fee_guard.py` is called from
`before/__init__.py` beside the other two boot guards.

**THE KNOWN COST, ACCEPTED WITH EYES OPEN.** A study copied from this template
that already sets a `participation_fee` **will refuse to boot** until the money
is moved into the ledger (into `showup`, or into `outro`'s `earned`). A real cost
paid by a real person — and the trade is deliberate: the alternative is a study
that runs happily with a payment record that is wrong in a way nobody notices
until payout, when somebody is underpaid.

**What it does NOT catch — a boot SOURCE scan cannot see a running session.**
oTree's `SessionEditPropertiesForm` (otree/views/admin.py:212) exposes
`participation_fee` as an editable field on a LIVE session, and `form_valid`
(admin.py:255-261) writes it into `session.config`, a DATABASE COLUMN on the
session row (`Column(_PickleField)`, models/session.py:35). The value lives in
data, so **no restart will ever catch it** — the guard passes while the session
carries a fee. Verified against 6.0.15, and measured: the ledger stayed at
€10.00 while the Payments figure moved to €13.00.

**Policing that is deliberately out of scope** (Julian + the hosting review): an
operator editing a live session is an operator action and is trusted. A
dashboard warning was proposed, costed, and CANCELLED. What was required instead
is that it be visible rather than silently clean — and it already is, for free,
because `predeploy_check`'s frozen-config audit reads the session ROWS rather
than the source and reports it as a plain value difference (`frozen 3.00cu vs
current setting 0.0`, confirmed on a real edited session). Check the artifact,
not the recipe; this guard is the recipe half and must never be written up as
more than that.

**Rejected:** relying on `AUTO_TABULATE_PAYOFFS`-style enforcement from oTree
(there is none for this field), and a runtime check in `outro` (same dead-page
trade the payoff guard exists to avoid).

**Enforced:** `fee_guard.assert_participation_fee_is_zero()`, called at boot from
`before/__init__.py`. Two halves: the RESOLVED configs (`SESSION_CONFIG_DEFAULTS`
must carry an explicit 0; a per-config entry may omit the key but must not set a
fee) and an AST scan of app packages and shared root modules for
`participation_fee` written as anything but a literal 0 — assignment, attribute,
`config['participation_fee']`, a `dict(participation_fee=…)` keyword, or a dict
literal. The scanned file list comes from `payoff_guard.files_to_scan`, not a
second copy of the rule, so the two guards cannot disagree about which
directories are apps. Verified 2026-08-14: the template boots clean (15 files
scanned); a fee in the defaults, an absent key, and a per-config override each
refuse the boot; a config omitting the key inherits correctly; all seven source
shapes fire and a literal 0, a `0.00` keyword and a *read* of the key do not.
Proven end to end with `otree resetdb` — the shipped template exits 0, and with
`participation_fee=2.50` the boot fails with the guard's message.

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
rather than the terms we built it in — and `hosting_a_prolific_study.md`.

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

## The predeploy check decides which database it touches in ONE place, and proves it before anything destructive — 2026-08-14

Found by the same sweep as the entry below, and fixed on Julian's instruction
before either was committed. `scripts/predeploy_check.sh` ran its degraded-mode
`otree resetdb --noinput` in a subshell that **inherited the environment**; the
line pinning the run to its own staged sqlite copy — `export
DATABASE_URL="sqlite:///$WORKDIR/app/db.sqlite3"` — sat *after* that branch. So
an operator with a live `DATABASE_URL=postgres://…` exported (the normal state of
a deploy shell) running the documented no-argument check had their live database
dropped and recreated, after which the run proceeded happily against the staged
sqlite file and **reported PASS**. Verified end to end before the fix: a seeded
session row went 1 → 0 and the gate exited 0 with `RESULT: PASS (DEGRADED)`.

**The severity is about where it sat, not just what it did.** This is the tool
whose entire purpose is preventing data loss before a deploy, it is destructive
in its *documented* mode, and the database it destroys is by construction the one
you are about to deploy to. The only thing standing between a Postgres operator
and this was whether `psycopg2` was importable — and a working Postgres
deployment necessarily has it.

**Root cause is the mirrored rule in CLAUDE.md — one concept, two
implementations.** "Which database does this check touch?" was answered twice:
by the shell (inherits ambient env, pins later) and by the helper, which never
set `DATABASE_URL` at all and relied on `os.chdir` — a lever that works *for
sqlite only*, since oTree ignores the path in a sqlite `DATABASE_URL` but honours
a Postgres one completely. Against an inherited Postgres URL the chdir lever is
inert. Two deciders, and their disagreement was destructive rather than merely
confusing.

**The decision:** one place decides, and the proof covers every decider.
`pin_database_url()` forces the URL onto the staged copy and **refuses** a
disagreeing one (a non-sqlite URL, or a sqlite URL naming a different file)
instead of overriding it silently — silence would hide an operator who believes
they are exercising their Postgres. `assert_engine_on()` then interrogates the
engine oTree actually built and hard-fails unless it resolves to the staged file:
declaration, then measurement, because for sqlite the environment variable is
only a statement of intent and the cwd is what binds. The shell pins immediately
after staging, **before any branch can run a destructive command**, and calls the
**same** proof through `predeploy_check.py --assert-engine-on` before its
`resetdb`. The helper pins and proves for itself too, because it is documented as
directly runnable.

**Rejected:** just moving the export above the branch. It fixes this instance and
leaves the second decider in the helper, and it leaves the proof covering only
one of the two — which is how this survived in the first place. A proof that
covers one decider is an invitation for the other to grow back at the next edit.

**Enforced:** `predeploy_check.py --assert-engine-on`, called by the shell before
its destructive step and by `check_boot` for itself — one function, two callers,
so the two processes cannot be proved against different rules. Demonstrated on
2026-08-14 against a real PostgreSQL 16: the pre-fix scenario destroyed a seeded
row and passed; post-fix the identical run leaves the row intact (`MUSTSURVIVE`,
22 tables) and still passes on its staged copy. The regression this is meant to
survive was simulated directly — the pin deleted, the proof left in place — and
the proof caught it: exit 2, `nothing was written`, live data untouched. Both
sqlite paths re-verified unchanged (upgrade mode with the `_ai/live_data/` (local only — `_ai/` is gitignored; not in a clone)
fixture: boot, schema, resume, fresh, no-JS and log-scan all pass, with 2b's
pre-existing frozen-config failure unaffected; degraded mode: PASS).

## Boot initialisation is decided by inspecting the database, not by a sqlite file — 2026-08-14

Found by the hosting review, which caught the same defect in `exp_pilots`'
`start.sh` and asked whether this template shared it. It did. The container's
CMD initialised on `[ "${RESET_DB:-0}" = "1" ] || [ ! -f /app/data/db.sqlite3 ]`
— **file existence as a proxy for "is this database new?"**. The proxy is only
equivalent to the real question when the database IS that file. Point
`DATABASE_URL` at a managed Postgres and the sqlite file never exists, so the
condition is true on every boot and `otree resetdb` runs against the Postgres on
every container restart. `otree/cli/resetdb.py` does `old_meta.reflect(bind);
old_meta.drop_all(bind)` — it drops whatever it finds, on whatever backend — so
that is a silent total wipe with no error in the log, discovered after a
session. On Railway/Heroku/Fly (ephemeral container filesystem, no volume) it
recurs on **every** restart; with a `-v <study>-db:/app/data` volume it fires on
the first boot and is then masked by an accident (below), which is worse, not
better, because the exposure comes back the day the volume is recreated.

**The proxy was not sound for sqlite either**, which is the part that makes
"just fix the condition" the wrong fix. Importing `otree.database` executes
`sqlite_disk_conn = sqlite3.connect('db.sqlite3')` at module scope —
unconditionally, *including when `DATABASE_URL` points at Postgres* — which
creates a **zero-byte file**. A zero-byte `db.sqlite3` is a file that exists and
a database that was never initialised; `-f` cannot tell those apart, so the old
guard would also skip initialisation and leave the server running against a
table-less database.

**The decision:** the guard asks the question it actually means — *does the
database oTree will connect to already contain oTree's tables?* — via
`scripts/db_state.py`, which uses **oTree's own engine** (`otree.database.engine`,
built from `DATABASE_URL` by the same code path the server uses, so it cannot
inspect a different database from the one the study runs on) and **oTree's own
table names** (`AnyModel.metadata`, not a hardcoded `otree_participant`, which
would be a second implementation of "what oTree's tables are called" and would
drift the day oTree renames one). Backend-agnostic by construction: the same
question has the same meaning on sqlite, Postgres and anything else SQLAlchemy
reaches. `RESET_DB=1` is unchanged and does not consult the probe.

**Four situations kept apart** (the collapsed-distinction rule; collapsing any
pair of them is how this class of bug destroys data): *no tables at all* →
initialise; *oTree's tables present* → keep; *tables present but none of them
oTree's* → refuse (resetdb would `drop_all()` somebody else's schema, or an
oTree database whose version named its tables differently); *cannot determine* —
unreachable database, missing driver, empty model registry, in-memory engine →
refuse. "I cannot see the database" is not "the database is empty": an
unreachable Postgres must never read as brand new. Both refusals stop the boot
non-zero and loudly. That bias is deliberate — a container that refuses to start
is a page in the log; a container that wipes a live study is a lost session.

**Rejected:** patching the condition to also test for a Postgres URL. It keeps
file existence as the sqlite answer (still wrong, see the zero-byte case) and
makes the guard a list of backends to remember, which is the shape that produced
this bug.

**WHAT THE GUARD IS ACTUALLY FOR — and it is not creating tables.** Relayed from
the `exp_pilots` fix (79d49c2) and verified here against otree 6.0.15: oTree
builds its own schema on every start. `otree.main.setup()` calls `init_orm()`,
which ends in `AnyModel.metadata.create_all(engine)` (otree/database.py:369), and
`create_all` is checkfirst-by-default — it adds missing tables and never drops or
alters an existing one. So `resetdb`-on-fresh is belt and braces; the server
would have built the schema anyway. The guard's only real job is NEGATIVE: to
stop `resetdb` running against a database that has data in it. That reframing is
load-bearing for the failure path — refusing to boot forfeits nothing the server
needed, because an unreachable database would have failed `create_all` too.

**Converged with the `exp_pilots` fix (79d49c2), which was written independently
against the same defect.** Three of its findings were taken:

- **The driver is part of this fix, not a follow-up.** `pip install otree` ships
  no Postgres driver, so without `psycopg2-binary` in the image the probe cannot
  connect, lands in the unanswerable branch and refuses to boot — a guard whose
  safe direction is triggered by our own missing dependency would fail 100% of
  Postgres deploys while looking like a database problem. Pinned to 2.9.12 to
  match. This had been written down as a "record, decide later" item; that was
  wrong, and the correction came from comparing against the other fix.
- **Waiting is not weakening.** A managed Postgres is very often not accepting
  connections at container start. The probe now retries a non-answering database
  (`DB_WAIT_ATTEMPTS` x `DB_WAIT_SECONDS`, default 30 x 2s) before calling it
  unanswerable, so refusal is the verdict after waiting rather than the first
  answer. Without it the guard converts every normal cold start into a failed
  deploy — which is how a safety mechanism gets switched off for being annoying.
  Only "did not answer" is retried; a missing driver, an empty registry, an
  in-memory engine or a foreign schema are answers already and fail at once
  (measured: 0s vs the full wait).
- **No password ever reaches a log.** Fatal banners render the URL through
  `repr(engine.url)` (SQLAlchemy 1.3 masks the password there; `str()` does not)
  plus a regex scrub of any `scheme://user:pw@` in driver messages and a literal
  replacement of the password read from `DATABASE_URL`.

Their fourth point — resolve the URL exactly as oTree does (`os.getenv` with the
`sqlite:///db.sqlite3` fallback, forcing sqlite paths back to the relative
`db.sqlite3` because oTree ignores the path) — **is satisfied here by
construction rather than by copying the rule**: this probe does not resolve a URL
at all, it imports `otree.database.engine`, the very object the server uses. A
second resolution is exactly the one-concept-two-implementations shape that would
drift, and with the same destructive consequence (bless one database, wipe
another). Demonstrated: with an initialised database in the CWD and
`DATABASE_URL` naming a *different, empty* sqlite file, the probe answers
`already-initialised` — it follows the CWD file, precisely as oTree does. The
corollary is that the probe must run with the server's CWD, which the CMD does.

**Also taken:** under `RESET_DB=1` the sqlite file is deleted only when the
backend is actually sqlite (`case "${DATABASE_URL:-sqlite}"`), since on a managed
database `resetdb` does its own dropping and deleting a stray file there would be
theatre. `RESET_DB=1` remains the only deliberate wipe path on any backend.

**Enforced:** nothing in CI — say so plainly. `scripts/predeploy_check.sh` is
sqlite-only by design (documented in its header: oTree ignores the path in a
sqlite `DATABASE_URL`, so isolation is achieved by CWD), no suite runs against
Postgres, and none of them boot the container, so **no automated check in this
repo would have caught the original defect or would catch its return.** What
exists instead is a manual proof, run on 2026-08-14 against a real PostgreSQL 16
(installed without root — recipe in the agent memory note `postgres-without-root`)
and a real sqlite database, driving the **actual CMD text extracted from the
Dockerfile** rather than a paraphrase:

| case | sqlite | Postgres |
|---|---|---|
| fresh/empty database → initialise | yes | yes (22 tables) |
| existing database → keep, data intact across restarts | yes | yes (3 restarts) |
| **the old condition**, same sequence | n/a | **row gone after 1 restart** |
| zero-byte `db.sqlite3` → initialise | yes | n/a |
| **dropped column preserved, NOT restored** | yes | yes |
| late-starting database (down at boot, up 14s later) | n/a | **waited 14s, then kept the data** |
| unreachable database → refuse, exit 1, nothing modified | n/a | yes (after the wait) |
| missing driver → refuse **immediately** (0s, no pointless retries) | n/a | yes |
| foreign (non-oTree) schema → refuse, schema untouched | n/a | yes |
| `RESET_DB=1` → full rebuild (dropped column comes back) | yes | yes |
| sqlite URL naming another file → follows CWD, as oTree does | yes | n/a |

The dropped-column case is the sharpest of these: a column removed by hand stays
removed after boot, which is direct evidence that no `resetdb` ran — and it still
boots, because oTree's own `create_all` does not repair columns either.

Two things remain UNVERIFIED and should not be read as covered: **Docker itself
was never run** (no image build, no real container boot, no `COPY` of
`scripts/db_state.py` — the CMD body was extracted and executed with `/app`
rewritten, and syntax-checked as `sh -c "bash -c '…'"`), and **no managed
provider was exercised** — the Postgres was local TCP with trust auth, so TLS
(`sslmode=require`) and connection-pooler behaviour are reasoned about, not
tested. The pooler case is the one most likely to behave differently, and it
fails toward refusal rather than toward wiping.

The Dockerfile comment states what the guard asks, why file existence was wrong,
and why the failure path refuses rather than initialises — because the condition
looks redundant next to a `-f` test and invites being simplified back, and
because a refusal invites being made permissive.

## A Postgres deployment has NO upgrade-path check — recorded as an open gap, not closed — 2026-08-14

Recorded on Julian's instruction while fixing the two Postgres data-loss defects
above, because **this is the gap behind both of them** and every study copied
from this template inherits it.

Everything this template has for "will the running study survive being upgraded
to this code?" runs on sqlite, and only on sqlite. `scripts/predeploy_check.sh`
pins itself to a staged **sqlite** file, validates its input by the sqlite magic
header, and proves its isolation with `PRAGMA database_list` — all sqlite-only,
all by design and documented in its header. The documented way to obtain its
input is `docker cp <container>:/app/data/db.sqlite3`, a file that does not exist
under Postgres. Every suite is likewise sqlite (`scripts/tests/otree_inprocess.py`,
`scripts/tests/render_check.py`), as is the `_ai/live_data/` fixture (local only — `_ai/` is gitignored; not in a clone) that makes upgrade
mode meaningful.

**So the one backend a hosted study actually uses is the one with no coverage at
all.** A study on Railway/Heroku/Fly runs on Postgres; its operator runs the
pre-deploy gate the documented way, lands in degraded mode — honest (it shouts
`THE UPGRADE PATH WAS NOT TESTED`) but empty — and deploys onto live participants
with the fresh-install checks only. The two outages this gate exists for (a
participant-vars key old participants never had; a session config frozen before a
parameter existed) are precisely what a fresh database cannot reproduce.

It is also **why both defects above survived**: each was destructive only against
Postgres, and no test in this repo has ever opened a Postgres connection, so
nothing went red.

**Closing it, in order:** (1) a **container boot test** — boot the image against
a Postgres URL, write a row, restart, assert the row survives. Smallest, highest
value, and the direct regression test for the defect that started this; it needs
Docker. (2) a **Postgres fixture** for the suites — a real server, which needs no
root (recipe: the agent memory note `postgres-without-root`), plus the driver,
now in the image. (3) a **Postgres mode for `predeploy_check.sh`**: the isolation
model changes shape rather than gaining a branch — `pg_dump` the live database
and restore into a **throwaway database**, the live-refusal guard becomes "the
target must not be the live database name", and `PRAGMA database_list` becomes
`SELECT current_database()`. That proof is now behind one function
(`assert_engine_on`), so it is one place to extend, not two.

**Enforced: NOTHING.** No test, no gate, no banner tells an operator that their
Postgres deployment is being upgraded without an upgrade check. The README's
Docker section now says so in words, which is the only thing standing here.
Working detail: `docs/postgres_assumptions.md`.

## `DB_NAME` in settings.py does not select Postgres — oTree 6 never reads `DATABASES` — 2026-08-14

`settings.py` sets `DATABASES = {...postgresql...}` when `DB_NAME` is in the
environment and a sqlite `DATABASES` otherwise. **oTree 6 never reads
`DATABASES`** — verified: zero references to the name anywhere in the installed
`otree` package (6.0.15). oTree 5 dropped Django; the backend is chosen solely by
`DATABASE_URL`. The block is a Django-era leftover that reads like a working
control, so somebody setting `DB_NAME`/`DB_USER`/`DB_HOST` expecting Postgres
silently gets sqlite. Same defect class as the two fixed above — a control whose
apparent meaning and real effect differ — but not destructive, so it is recorded
rather than changed in a hurry.

**Options for whoever settles it:** delete the block (simplest, matches how oTree
works); or keep the `DB_*` names as a convenience and have them **construct**
`DATABASE_URL` when it is not already set, so the documented knobs actually do
something. Either way the block needs a comment saying `DATABASES` is not
consulted, or the next reader will "restore" it.

**Enforced:** nothing. No check compares the configured backend against the one
actually in use. Detail: `docs/postgres_assumptions.md` item 4.

## The README documents that inert `DB_NAME` mechanism as if it worked — 2026-08-14

`README.md` ("Running the template") says Postgres is not needed *unless you set
`DB_NAME`*, and lists `DB_*` among the values to set via env in production. Both
halves teach the mechanism the entry above shows is dead. Recorded separately
because it is a second place to change, and changing the code without the prose
leaves the same wrong instruction in the file people actually read.

**Enforced:** nothing — prose is not tested. Fix it in the same change as the
entry above, whichever way that goes.

## A wrong-backend engine is reported as "the app failed to boot" — 2026-08-14

`check_boot` in `scripts/predeploy_check.py` wraps the in-process import and the
engine proof in one `try/except Exception` and reports any failure as *"the app
failed to boot against the database"*. A wrong **backend** is not a broken build,
and reading it as one sends the next person to debug their app instead of their
environment. The shared-`except` shape this codebase warns about, in its mild
form: nothing is destroyed, only misattributed.

**Partly addressed as a side effect of the predeploy fix:** `assert_engine_on()`
now names the backend explicitly ("oTree built a `postgresql` engine, not
sqlite") and `check_boot` re-raises `SystemExit`, so that case reports itself
accurately. What remains is the general shape — every other import-time failure
still collapses into one message.

**Enforced:** nothing. Worth splitting if that file is being edited anyway; not
worth a change on its own. Detail: `docs/postgres_assumptions.md` item 9.

## Ended.html carries no screen-out copy — deleted as unreachable, with the unreachability enforced — 2026-08-14

Decided by Julian (before-review N4), choosing deletion over the reviewer's
keep-both recommendation. The `reason == 'screened_out'` block in
`outro/Ended.html` — the four device-cause branches and the screened-out
title — duplicated `before/screened_out.html`'s live copy for a participant
who can never arrive: the soft wall holds a screened-out participant at the
entry page's own index precisely because oTree only moves forward, so walking
them to an outro ending would make the verdict un-liftable. A duplicate that
never renders can only drift from the copy that does.

**The deletion was not made on the unreachability claim alone.** This repo
has been bitten by untested claims (the 2026-08-13 monitor-coverage entry
below: four documents asserting something untrue), so the claim was made
ENFORCED in the same change: `scripts/tests/screenout_softwall_test.py` scenario 9
hammers a screened-out participant with forced submits and a direct
`/outro/Ended/` URL and requires every response to re-serve the held page.
If routing ever changes, the test goes red before a participant reads the
wrong page. Two second-line defences remain for that hypothetical future
gate: Ended's neutral else-fallback ("The study has ended for you") says
nothing false, and the shared footer include still picks the CODELESS exit
for `reason == 'screened_out'`, so their submission would stay open.

**What deliberately stayed:** `outro.was_screened_out` — a DIFFERENT
mechanism that looks related and is not. It is what keeps a screened-out
participant out of `is_completer`, so no future gate can hand them a
completion code; deleting it with the template branch would have been the
over-pull this entry exists to warn against. `Ended.vars_for_template`'s
`common.screenout_vars` spread also stays: the footer reads
`prolific_screenout_return_url` from it.

**Record check, done with the change:** no document claims the screen-out
exit code is written when the participant clicks the return link — it is
written at DECISION time (`common.set_screened_out`: a closed tab still
exports as screened out, not abandoned), and `set_screened_out`'s docstring,
the softwall test header and the footer include all state it correctly.

**Enforced:** `scripts/tests/screenout_softwall_test.py` scenario 9 (the deletion
guard); the header note in `outro/Ended.html` points at it.

## Explicit consent is its own flag (`explicit_consent`), split from `prolific_completion_redirects` — 2026-08-14

Decided by Julian, from the before-app review. Whether the consent page asks
an explicit question (required unticked radio, no-consent routed to exit code
-1) or states that continuing is consent was decided by
`prolific_completion_redirects` — which, read literally, said "if we hold a
completion code, consent must be an affirmative act". **Whether consent is
EXPLICIT is an ethics decision; holding a completion code is platform
plumbing.** The conflation is the same defect class as the screened-out
dead end of 2026-08-13 (one flag doing a second, unrelated job), caught this
time before it cost a participant.

The split: `explicit_consent` defaults **ON** in `SESSION_CONFIG_DEFAULTS` —
the one shipped flag that is deliberately not off-by-default, because a study
should have to OPT OUT of asking for consent — and the **lab profile resolves
it OFF** (implicit consent by continuing; there is an experimenter in the
room). That preserves the pre-split behaviour of both shipped profiles
exactly: prolific keeps the radio, the lab keeps implicit consent. The
prolific profile deliberately does NOT list the key (it falls through to the
baseline ON): explicit consent is the default, not a Prolific feature.

The audit for a second conflation found none: every other use of
`prolific_completion_redirects` (the outro return footers, the Ended/Results
"Back to Prolific" branches, the dashboard's awaiting-return pill, the
return-click stamp) is genuinely about the completion-code redirect. One
consequence is newly constructable and deliberate: `explicit_consent` on with
redirects off produces a decliner whose ending has no return button —
`outro/Ended.html`'s neutral fallback covers them.

A frozen session predating the flag reads it as OFF (`common.flag`'s
missing-module rule) — the radio would silently vanish for that session's
future entrants, which is why the predeploy frozen-config audit reporting the
missing key matters: the remedy is to recreate the session.

**Rejected:** deciding at runtime from `recruitment` (the consent page asking
"am I a lab study?") — profiles resolve to explicit config values at import
precisely so behaviour is never re-derived silently; and keeping the old
wiring with a comment — the rename made the misreading legible, a comment
would only apologise for it.

**Enforced:** `scripts/tests/explicit_consent_test.py` (radio present+required when
on, absent with implicit copy when off, in BOTH recruitment profiles — flag
decides mechanics, recruitment decides copy — plus the resolved values on
both shipped configs); `explicit_consent` in `scripts/tests/frozen_config_test.py`'s
STRIPPED list pins the frozen-session behaviour.

## One short-viewport rhythm for every `.stacked-form` option row — a leak ratified into the rule — 2026-08-14

The consent-fold block (`@media (max-height: 820px)` in base.css, 2026-08-13)
tightened option rows via `.stacked-form .mc-option / .form-check` while its
comment claimed consent-only scope — but the quiz and demographics stack their
options in `.stacked-form` directly (the "different wrapper" the comment cited
never existed), so both pages were retuned from day one. **Discovered through
a geometry-baseline diff, not by design** — the fold work never ran
`--update-baseline`, so the first `--diff` afterwards surfaced ~130 moved
measurements (quiz card −125px, demographics −59px at short viewports), which
were first mis-attributed to environment drift and then pinned by a CSSOM
toggle: deleting the one media rule sprang the rows back to the baseline's
values on both pages, while a rule audit proved the concurrently-added
tabmonitor.css matches nothing there. The log records the route because that
is how it actually happened.
**Julian's ruling: make the rule the intent.** One component, one rule,
everywhere — a component that tightens on short viewports on one page but not
another is the same mixing-and-matching the logo-strip principle forbids. The
shipped behaviour stands, the adopted baseline stands, and the earlier
"one page's shortfall must not silently retune every choice" scoping intent
is ABANDONED, on purpose, with the reversal recorded at the block itself.
Judged on screenshots before ratifying, not on the principle alone: rows stay
over the 44px touch floor, nothing cramped, quiz and demographics
neutral-to-better on short screens.
**Rejected:** re-scoping the rule to the consent group (a dedicated class) —
it would honour the written intent by making the same control obey two
rhythms, which is the defect class, not the fix.
**Enforced:** the rewritten comment at the block (base.css) states the
everywhere-rule and forbids re-scoping without a new decision;
`scripts/tests/geometry_baseline.json` pins the shared rhythm at all three viewports;
the affordance and touch-target legs of `scripts/tests/render_check.py` assert the
pages still behave.

## The tab monitor is monitored-by-default after the agreement page — and the claim preceded the behaviour — 2026-08-13

Whole-app review B1, decided by Julian. **First, the record correction this
entry exists to hold: from 2026-08-12 to 2026-08-13 four places (this file's
armed-before-the-quiz entry, README's Prolific flow diagram, the
`TabMonitorAgree` docstring, `intro/__init__.py`'s closing comment) stated that
the instructions and the quiz were monitored, and they were not.** The
agreement page had moved but no monitor wiring existed in `intro` — no
live_method, no js_vars, no script — so the very check the move was made to
protect stayed unwatched, with nothing anywhere to say so (the enforcement
test pinned page ORDER, not coverage). The gap was found by asking where one
concept — "a monitored page" — had two implementations, and it is recorded
here because a claim that quietly becomes true later is exactly the kind of
thing a future auditor must be able to date.

**What closed it — an INVERSION, not page-by-page opt-in** (Julian's rule):
everything after `before.TabMonitorAgree` is monitored BY DEFAULT
(`participant_tab_monitor.MonitoredPage`, generalising TaskPage's J2 reasoning), and a
page can only be unmonitored by asking (`monitored = False`, one switch that
disarms all the wiring together — never `js_vars = None`, which 500s at
render because oTree calls js_vars unconditionally). The four pieces travel
as one: live_method and js_vars from the base class; script and stylesheet
through `css_bundle.html` (self-gating on `session.config.tab_monitor` and on
the page's own js_vars), so there is no per-template include left to forget —
a per-template include is how the gap happened. The client lost its
threshold-defaults fallback (a second copy of SESSION_CONFIG_DEFAULTS kept in
sync by a comment) and its `/outro/` path check (a second spelling of "which
pages are monitored"): the server's js_vars are now the one authority.
`intro.intro_page_visible` gates on the new `common.removed_from_study` belt
(one membership list for every removal mechanism, used by main too), so a
mid-quiz disqualification's reload lands on the ending.

**THE PHASE ASYMMETRY — same monitor, same counting, different consequence
(Julian): intro + main EJECT at the threshold; the outro RECORDS ONLY and
never ejects.** By the outro the task is over and the data already collected,
so disqualifying somebody who has completed the whole study — for tabbing
away while typing bank details, or to fetch their Prolific tab — would cost a
real participant for no benefit. Outro violations land in their OWN column
(`tab_monitor_focus_loss_count_outro`), so a completed-with-violations participant is
distinguishable from a nearly-ejected one (`tab_monitor_focus_loss_count` keeps meaning
"how close to disqualification"); the dedup set is shared so no event counts
twice. The client is told its phase (`ejects: false`) and shows no overlay
and no warning modal in the outro — the modal's threat would be a lie there.
The asymmetry is stated, with its why, at every site that could read as
inconsistent: `common._apply_focus_loss`, `participant_tab_monitor.py`, the top of
`outro/__init__.py`, settings' integrity block, README (section + diagram),
CODEBOOK ("Tab-monitor violation counts"), docs/conventions.md.
**Rejected:** page-by-page opt-in (the model that produced the gap — a
checklist cannot make forgetting impossible); ejecting in the outro
(cost-without-benefit above, plus a mechanical trap: `Ended` sits FIRST in
outro's sequence, so a mid-outro ejection has no ending page ahead of it to
land on); and a client-side warning without counting or counting with the
old threatening modal in the outro (each a new collapsed distinction).
**Enforced:** `participant_tab_monitor.assert_monitored_page_sequence` runs at IMPORT at
the bottom of `intro`, `main` and `outro` and refuses to BOOT over a page
that is neither monitored nor explicitly opted out — you can only get an
unmonitored page by asking for one. `scripts/tests/task_page_test.py` (reworked)
pins the bindings by identity, the quiz page's served monitor config
end-to-end, the record-only outro (violations past the threshold disqualify
nobody and stay in their own column), the Results dispatcher (one live
channel, both message types), and the checker refusing a dodger.

## One guard policy for a config-read money value: fail loudly — 2026-08-13

Whole-app review B4, decided by Julian. `showup` / `quiz_bonus` were read two
ways: the promise side (consent, instructions) guarded with `or 0`, the
payment side (`outro.compute_final_payoff`) bare. For a config holding None
that split is the worst arrangement — the participant is silently promised
€0.00 and the crash still happens, at the payment page. The `or 0` guards are
gone; every side now reads bare and fails loudly at the first page that
renders the value. **This has a behavioural implication, stated plainly
because the decision was taken assuming it did not: a degenerate config that
used to render a silent €0.00 promise now errors instead.** Loud is chosen
because silently promising somebody nothing is the worse outcome — the same
reasoning `compute_final_payoff` already carried ("failing loudly beats
recording the wrong number quietly"). No shipped or frozen config is
affected: `common.cfg` falls back to the shipped numeric default for a
MISSING key; only an explicit None ever hit either path.
**Enforced:** nothing structural — the policy is one line of comment at each
former guard site (`before.welcome.vars_for_template`,
`intro.instructions_context`), and the loudness is the absence of the guard.

## The two-accessor question is CLOSED across the flow — 2026-08-13

Chased across three separate reviews (before N3 → whole-app B2 → this
implementation), and recorded here so nobody re-opens it: **every reader of
the study type now goes through `common.is_lab` / `common.is_prolific` /
`common.recruitment`.** The last holdout was `before.startpage.is_displayed`'s
raw `config.get('recruitment') == 'lab'`, which on a session frozen before
the key existed evaluated `None == 'lab'` → False — silently dropping the lab
hold screen while the consent page one index later rendered lab copy through
`is_lab`'s fallback: one participant, one question, two answers, one page
apart. Behaviour change is confined to that frozen-config case (the hold
screen now appears, which is what the neighbouring pages already assumed);
blast radius today is zero — no live sessions, the same window the
`prolific_` rename used.
**Enforced:** `grep "config.get('recruitment')"` returns nothing outside
`common.py`; `scripts/tests/copy_routing_test.py` pins the single-implementation rule
the accessor carries.

## Task pages inherit their wiring from `TaskPage` — the template's one use of page inheritance — 2026-08-13

> **SUPERSEDED IN PART, same day — see the monitored-by-default entry above.**
> The J2 reasoning held and GENERALISED: the monitor wiring moved up into
> `participant_tab_monitor.MonitoredPage`, which every page after the agreement screen now
> subclasses, so page inheritance is no longer "used nowhere else" — it is the
> rule for three of the four apps, for exactly the reason this entry gives.
> TaskPage survives as the task-specific layer (round gating + progress vars)
> on top of that base. The monitor contract itself is still untouched.

Review item J2, approved with Julian's reasoning (recorded at the class, which
is where the next reader meets the indirection): a task page that is SILENTLY
NOT ARMED for the tab monitor is worse than the cost of a base class —
forgetting the wiring produces no error, only monitoring that never fires,
discovered from the data. `main.TaskPage` carries `is_displayed` /
`live_method` / `js_vars` / the base template vars; `GameStart` and `payoff`
subclass it; the two repeated template blocks became includes
(`task_progress_strip.html`, `tabmonitor_assets.html`). THE MONITOR CONTRACT
IS UNTOUCHED — same bindings, names and thresholds; only who types them
changed. Two gotchas live in the docstring: oTree resolves page attributes at
IMPORT, so unbinding needs an explicit override, never an omission; and
subclass, never copy, or the drift returns. Page inheritance is used nowhere
else in the template, deliberately.
**Rejected:** staying explicit-per-page with a checklist — the checklist
cannot make forgetting impossible, and the failure it guards is silent.
**Enforced:** `scripts/tests/task_page_test.py` — structurally (an empty-bodied
subclass is fully armed; identity of the bindings, not lookalikes) and
end-to-end (the served page carries the monitor config; the inherited
live_method counts a violation), plus the unbind-by-override gotcha proven in
both directions.

## The dashboard's admin "Report" tab rides oTree's supported extension point, as a layer over the standalone URL — 2026-08-13

Julian promoted the TODO investigation to a build. The investigation's answer:
oTree 6.0.15 has a first-class extension point — at session creation,
`Session._set_admin_report_app_names` (otree/models/session.py:250) scans each
app for `<app>/admin_report.html`; oTree's OWN session tab bar
(otree/templates/otree/Session.html:84) renders a "Report" tab when found; the
`AdminReport` view (otree/views/admin.py:482) renders our template with
optional `vars_for_admin_report`. So the tab (`outro/admin_report.html`,
embedding the dashboard in an iframe with an open-standalone link) depends on
a documented feature, not on oTree's page structure. **The standalone URL is
the primary surface and works unchanged with the tab deleted or broken** —
built that way round deliberately. `vars_for_admin_report` is internally
defensive (oTree calls it unguarded) and catches ONLY the import, with a
literal fallback URL as the belt.
`experimenter_dashboard.note_admin_tab_problems` applies the identity.py
discipline to the one silent failure mode: quiet when oTree is legitimately
absent, LOUD (logged, never raised) when the admin-report symbols or the
template lookup have drifted — because drift here means the tab quietly stops
appearing. Known limitation: sessions created before the template shipped
carry no tab (the scan is frozen into the session row).
**Rejected:** injecting into oTree's admin page structure (templating over /
DOM patching) — far more upgrade-exposed than our routing-level install, and
unnecessary given the supported point.
**Enforced:** `scripts/tests/dashboard_test.py` §D9 — the tab appears in oTree's own
tab bar, the standalone URL works with it present, a broken dashboard leaves
the admin pages serving, a broken import leaves the tab serving via the
fallback, and the drift check reports ok against the installed oTree.

## One payment ledger: per-round `player.payoff` is not used, `participant.payoff` is written once from `earned` — 2026-08-13

Review item J1 (Julian; sub-decision also his). The underlying conflation:
oTree automatically sums `player.payoff` across rounds into
`participant.payoff`, but this template pays only `num_rewarded` randomly
selected rounds — the per-round result and the amount paid are different
things, and the auto-sum is a total nobody is paid. So the game records each
round in its own `main.Player.round_payoff`; the template pays from
`participant.payoff_vector`; and oTree's `participant.payoff` gets exactly ONE
entry — `earned` (less `participation_fee`, de-converted when `USE_POINTS` is
on), written when the results page computes payment — so the admin Payments
page shows the figure the participant was shown, and there is nothing left to
disagree. `AUTO_TABULATE_PAYOFFS=False` also removes oTree's per-round payoff
column from the export (deliberately absent, not accidentally empty — no data
lost, every round is in `round_payoff` and `payoff_vector`; CODEBOOK "The
payment record").
Facts established before shipping: nothing in oTree 6.0.15 recomputes
`participant.payoff` after that write (the `player.payoff` setter's delta is
the only other writer), and nothing in the template or its tests read the
per-round column except the placeholder itself.
**Rejected:** zeroing `participant.payoff` so the admin page is obviously
wrong (option 1 — Julian chose agreement over conspicuous wrongness); and
keeping the per-round writes while overwriting the total at the end, which
leaves a round column summing to a number nobody was paid.

### AMENDED 2026-08-14 — the raise was never the enforcement, and it lands on a participant

**Caught by the exp_pilots bossman**, verified against the installed oTree
before acting: this entry, `settings.py`, `main/__init__.py`,
`outro/__init__.py`, `CODEBOOK.md` and `docs/skills_claude/writing_task.md` all
said `AUTO_TABULATE_PAYOFFS=False` "makes the old habit RAISE rather than
drift back silently" — presenting a **participant-facing crash as a safety
feature**. The setter is oTree's own (`otree/models/player.py:41-46`), it
cannot be removed, and it fires **at participant request time, on a page,
mid-round**. oTree has no migrations, so the realistic failure is an upgrade
under live sessions: a new build introduces a `player.payoff` write and the
first person mid-round to reach it gets a DEAD PAGE. The flag alone therefore
converts a CONDITIONAL data problem (one ledger drifting into two) into a
CERTAIN outage for whoever is part-way through — the same trade this repo has
already refused twice, in `install_duplicate_label_guard` (the early install
must fail quietly) and in `assert_duplicate_label_guard` (deliberately not on
the entry path). It was missed here for the reason it is always missed: **a
raise feels like the strict, careful option.**

The raise stays — it is oTree's, and it is the floor. What changed is that the
failure is now caught **earlier, at boot**, where loud is what loud should
mean for a server: `payoff_guard.assert_no_player_payoff_writes()`, called
from `before/__init__.py` beside the identity assert, refuses to START a build
whose app modules write `player.payoff`. The operator sees it at deploy time
while the old build is still serving; the participant never sees it.

**TWO CHECKS, DELIBERATELY, because their blind spots are disjoint** — the
judgement call the review left open. The boot scan parses app SOURCE with
`ast`, so it covers every syntactic write whether or not any test walks that
line, and it cannot be fooled by the six files that discuss `player.payoff` in
prose (a regex would refuse to boot over this very paragraph); it is blind to
indirection. The runtime test walks a real journey and asserts the underlying
`_payoff` column is still 0 on every round row, which catches indirection; it
is blind to code no walk reaches. Neither alone is sufficient, so both ship.
`participant.payoff` and `player.payoff` are two fields sharing a name, and
the scan tests the base expression explicitly rather than the attribute — the
collapsed-distinction rule, since a name-only check would refuse to boot over
`outro.compute_final_payoff`, the one write the decision exists to protect.
**Rejected:** a launch-gate-only check (`scripts/prelaunch_check.py`), which a
deploy can skip — the whole point is that the server will not come up; and
`import`-and-introspect instead of parsing, which would execute
`intro/generate_instructions_preview.py` and its browser driver at boot.
**Enforced:** `payoff_guard.py`; `scripts/tests/payoff_ledger_test.py` §7 (a walked
journey leaves every round row's `_payoff` at 0) and §8 (the guard catches six
write forms including `setattr` with a literal name, refuses a synthetic build
naming file and line, does NOT fire on the participant write or on prose,
declares its `setattr`-with-computed-name blind spot, and reports an
unparseable module as "cannot answer" rather than as a payoff write).

**Enforced:** `scripts/tests/payoff_ledger_test.py` (the two figures agree on the
admin page itself; the value survives re-renders; oTree's setter does raise;
the export column is absent while `round_payoff` is present) — plus the boot
guard above.

## A payment total is not a payment instruction: every component paid outside oTree must still be represented inside it — 2026-08-14

**Caught by the exp_pilots bossman**, and it is the natural blind spot of the
one-payment-ledger decision above: that decision made the total CORRECT and
made both ledgers AGREE on it, and stopped there. Our admin Payments figure is
one undifferentiated number — full `earned` into `participant.payoff`,
`participation_fee` shipped 0.00 — so it covers base plus bonus at once. **On
Prolific those components are paid through DIFFERENT MECHANISMS**: the base as
the study reward, the bonus through the bonus payment flow. A single total,
however correct, is therefore NOT ACTIONABLE — whoever pays needs the **bonus
figure on its own**, and that is the number that must survive intact.

THE RULE, in the reviewer's words:

> **ANY PAYMENT COMPONENT PAID OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE
> OTREE, OR THE ADMIN PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A
> TOTAL.**

**Corollary:** on Prolific the components are paid by different mechanisms, so
the total alone is not enough — the bonus must be separately visible.

THE TWO SHAPES, WHICH LOOK LIKE OPPOSITES AND ARE THE SAME DEFECT. Ours is
**complete but not itemised**: everything is inside oTree, the total is right,
and the payer cannot read the bonus off it. The reviewer's own study was
**itemised but incomplete**: components kept apart, but the base never entered
oTree at all, so its "total" was a partial figure wearing a total's name.
Neither has the property that matters, which is **itemisation of a complete
set** — and framing them as opposites is what let both ship.

WHY THE EXISTING TEST DID NOT CATCH IT — the part worth remembering. §1 pins
that the total is correct and that the two ledgers agree on it. **A study can
get the total right while making the actionable number unreadable**, and a
test written against the total cannot see that. This is the collapsed-
distinction rule in the measurement rather than in the code: "the payment is
correct" and "the payment is payable" were one assertion.

**DONE NOW (safe, and independent of the open config decision):**
`scripts/tests/payoff_ledger_test.py` §9 walks a *prolific* session and asserts the
BONUS IN ISOLATION as well as the total — each component recorded on its own,
the three reconstructing `earned` with zero residue, the bonus
(`selected_sum + quiz_bonus_awarded`) derived from the stored components
rather than as `total − base` (which would be right by construction and prove
nothing), both halves separately readable, and the components present as their
own export columns. It also records the admin-page state as a **measured gap**.

**THE CONCRETE FIGURES THIS DECISION IS BEING MADE AGAINST**, so nobody reading
it later has to reconstruct what the admin page actually showed. One real
walked Prolific completer (participant `240pbcpa`, config `prolific`, 10 rounds,
`num_rewarded=2`, exit code 1), measured 2026-08-14, all figures EUR:

| Figure | Source | Value |
| --- | --- | --- |
| base / show-up | `showup` (session config) | **2.50** |
| selected rounds | `outro.Player.selected_sum` (r10 → 45.00, r6 → 98.00) | **143.00** |
| quiz bonus | `outro.Player.quiz_bonus_awarded` | **5.00** |
| **total earned** | `outro.Player.earned` — the three above, residue exactly 0 | **150.50** |
| `participant.payoff` | written once by `compute_final_payoff` | **150.50** |
| `participation_fee` | session config, as shipped | **0.00** |
| **admin Payments figure** | `payoff_plus_participation_fee()` | **150.50** |

The selected-rounds component is randomly drawn, so it and every total below it
vary per run (other runs measured 125.00 and 140.00); **base, quiz bonus and
`participation_fee` are fixed, and the SHAPE is invariant** — the admin figure
always equals `earned`, because `participation_fee` is 0.00 and the whole of
`earned` goes into `participant.payoff`.

**WHAT THE PAYER NEEDS IS TWO NUMBERS, AND THE ADMIN PAGE SHOWS NEITHER** — it
shows their sum. Study reward, set on the Prolific study: **2.50** (the base
alone). Bonus payment, entered in the bonus flow: **148.00** (selected rounds +
quiz bonus). Pasting the admin's 150.50 into the bonus flow pays 148.00 of
correct bonus plus 2.50 that Prolific has ALREADY paid as the study reward: the
participant is overpaid by exactly the base, and the error is invisible because
the total was right all along.

**THE MEASURED EVIDENCE**, fetched from oTree's own `/SessionPayments` for that
session: **€150.50 PRESENT. €148.00 (the bonus) ABSENT. €2.50 (the base)
ABSENT.** That is the itemisation argument in one line — the page carries the
total and neither component.

(Matched CURRENCY-PREFIXED, never as a bare number: `150.50` contains `2.50`, so
a substring search reported the base as present on a page that never mentions
it. See the comment at that check — a bare search makes both negative
assertions unable to fail, which is the same defect class as the total-only test
this whole entry is about.)

**DELIBERATELY NOT DONE YET:** changing `participation_fee` or how
`participant.payoff` is composed — that is an open decision with Julian, and it
changes what the exported columns MEAN, which is not something to do as a side
effect of adding a test.
**Rejected:** asserting only that the components exist, without asserting they
sum to `earned` — a component nobody can reconcile is a number, not an
itemisation; and deriving the bonus as `total − base` in the test, which passes
whatever the data says.
**Enforced:** `scripts/tests/payoff_ledger_test.py` §9; the rule is stated in
README "Paying participants — the itemisation rule" and in CODEBOOK "THE
ITEMISATION RULE".

## The end-of-page cookie reset is gone — 2026-08-13

`clearAllCookies` (run on load by the payoff, Ended and Results pages) was
removed with its three call sites and its helper — Julian: no longer needed.
It cleared every path=/ cookie each round and at the endings, including an
admin's own session cookie when previewing; oTree identifies participants by
URL code, not cookies, so nothing participant-facing depended on it. The other
dead cookie helpers an earlier review flagged (getCookie, setCookie,
printCookies, cl) were already gone. Do not re-add a cookie sweep without a
stated reason — the last one ran for years with nobody able to say what it was
for, which is why the review flagged it.
**Enforced:** nothing but grep — there is no cookie code left to guard.

## The dashboard summary strip: earnings is ONE pill carrying avg AND total; the total summed server-side over finished participants — 2026-08-17

Requested by Julian, from the live page. The payment picture lives on the one
dashboard tab, so nobody opens oTree's own Payments page to see what a running
session is paying out. The `dash-summary` strip beneath the table
(`experimenter_dashboard.py`) has TWO items: **avg intro time**, and a single
**earnings** pill carrying an **avg** and a **total** subsection.

**Why ONE earnings pill, not two items.** avg and total run over the *same*
population — FINISHED participants, the only ones with an `earned` figure — so
two separate items sitting side by side read as two different denominators,
which they were not. Merged, the population is stated ONCE (`of N finished`) and
its count carried once. The avg/total subsections are labelled in words inside
the pill so a reader tells them apart at a glance, without a tooltip — the whole
point of merging them. (It briefly WAS two items: a client-side `avg earnings`
mean beside a server-side `total payments` pill; this supersedes that.)

**The total summed SERVER-SIDE, and the avg derived from it — one source.** The
total is `_earnings_total(ctx['earnings'])`, the sum of the exact `earned`
figures `_earnings_map` already fills the row cells with, shipped as
`earnings_total` and merely *rendered* by `summaryHTML`; it is NOT re-added in
the client. The avg is that one server figure over its count (`total / n`), NOT
a second client-side sum of the cells. So neither subsection can disagree with
the other, nor with the column they aggregate — the collapsed-distinction trap
the timing pill is built to avoid (`_stall_elapsed`: one number for the value
shown and the value judged). The MERGE STRENGTHENED this: the old separate `avg
earnings` pill computed the mean a *second* way (client-side `mean(money)`),
which was exactly the one-concept-two-implementations drift `CLAUDE.md` warns
of; there is now one implementation.

**Degrades to nothing.** Gated on `earnings_total.total` being present, so the
whole pill is shown in full or not at all — any failure gives `total=None` and
no pill, never a raise, never a dead dashboard, like the earnings read it draws
on.

**The intro-time item stays SEPARATE** because it averages a DIFFERENT
population (everyone PAST intro, whose measurement is complete even mid-task),
and its wording (`past intro`) is kept deliberately distinct from the earnings
item's (`finished`) now that they sit next to each other. **Also rejected:** a
`participation_fee` line — the template holds `participation_fee` at zero on
purpose (the fee guard), and there is no second ledger to add up. **Not added:**
any `stopped_at` field or new participant variable (Julian ruled that out); the
pill reads only what `_earnings_map` already read.

**Enforced:** `scripts/tests/dashboard_test.py` §D — `earnings_total.n` counts
exactly the rows that have an earnings figure and `earnings_total.total` equals
their sum, and §D7 asserts the served page ships the pill reading
`data.earnings_total` rather than re-summing cells. `dashboard_render_check.py`
measures the strip in a real browser: TWO items, the earnings pill naming BOTH
its avg and total subsections and stating its `finished` population exactly once,
distinct from the intro item's `past intro`. The website monitor preview
exercises `summaryHTML` when it freezes the real page (its payload now ships
`earnings_total`), so a broken or vanished pill fails the paint that
`check_site_previews.py` guards.

## The dashboard header dropped its standalone participant count — the "X of Y arrived" segment already carries the total — 2026-08-17

Requested by Julian, from the live page. The header read `N participants · 👤 X
of Y arrived · …`, and `Y` is that same `N` (`data.rows.length` — every
participant row), so the total was stated twice in one line. Removed the leading
`N participants ·`; the `👤 X of Y arrived` segment is now the ONE place the
total lives. Verified before cutting that `Y` really is the total (it is
`n`), rather than, say, an arrived-only figure that would have made the leading
count non-redundant. No participant variable and no data changed — this is
purely the header string in `repaint`. `scripts/tests/dashboard_test.py` still
asserts the arrival segment ships (`👤` and `arrived` in the page), which is the
surviving carrier of the total.

## The dashboard's state column is a collection of pills, and conditions survive outcomes — 2026-08-13

Two kinds accumulate in one cell (Julian): OUTCOME pills (a terminal state, or
the finished tick) and CONDITION pills (Non-SEPA, the timing warning, the
tab-monitor count while it climbs, the missing return click). A finished row
KEEPS its condition pills — finishing does not make a condition go away.

**ROW TINT IS OUTCOME, PILLS ARE CONDITIONS** (Julian, same day, second pass).
The row tint is one consistent outcome signal: green finished, red ended
early, amber stalled, untinted still going — mutually exclusive by
construction, so no precedence. A condition NEVER touches the row: the
finished non-SEPA participant keeps the green row AND the red pill; turning
that row red would collapse the two channels back into one. The green is
deliberately lighter than the green pills' own background so the row does not
go monotone. The amber tint's second job stands: across-the-room salience,
with the pill carrying the facts.
**Rejected:** one state per row (the original design); and, briefly, no
finished tint at all (superseded — the tint was re-added as the outcome
CHANNEL once the channel rule made "green row + red pill" coherent rather
than contradictory).
**Enforced:** `scripts/tests/dashboard_test.py` §D7/§D8;
`scripts/tests/dashboard_render_check.py` `check_pills` measures one row carrying the
finished tick and the Non-SEPA pill together, that the finished tint is
distinct from the amber and from the pills' own background, and that the red
pill stays white-on-red against the green row.

## The Non-SEPA pill: lab only, `sepa == 0` only, and no yellow state — 2026-08-13

Three deliberate narrowings, all Julian's: NULL `sepa` (the check never ran —
every Prolific row) is NO pill, never a flag; a non-Dutch but in-SEPA account
is NO pill (only non-SEPA is flagged — there is no yellow payment state); and
even a hand-edited `sepa=0` in a Prolific session shows nothing, because
payment there goes through the platform and the pill would send the operator
chasing a form that does not exist.
**Enforced:** `experimenter_dashboard._non_sepa_ids` (the one predicate);
`scripts/tests/dashboard_test.py` §D7 pins all three narrowings.

## The BIC requirement and the Non-SEPA flag are two predicates, not one — 2026-08-13

The lab bank form demands a BIC for ANY non-Dutch IBAN (in-SEPA or not;
non-empty is the whole requirement — no format validation, because a rejected
valid-but-unusual BIC strands a participant on the page that pays them). The
dashboard pill fires on non-SEPA ONLY. A German IBAN therefore needs a BIC and
gets no pill. Both read the country through `outro.iban_country_code` — one
implementation of "which country", two questions on top of it (the inverted
collapsed-distinction rule, applied in the direction that keeps the questions
apart and the mechanism shared).
**Rejected:** one combined predicate — it would either flag every German
account or let a US account through without a BIC.
**Enforced:** `scripts/tests/bank_details_test.py` pins both halves of the asymmetry,
next to each other.

## The timing warning shows the number the threshold judged — per phase — 2026-08-13

The stall verdict and the pill display are ONE value (`_stall_elapsed`), and it
is measured per phase to match what each threshold MEANS in settings.py: entry
on the current page (a block-level 60s would flag every careful consent
reader), intro on the whole app since `left_before_app` (per-page under-fired:
7 minutes on each half never tripped 480s), task per round (the threshold's own
definition), questionnaire since `task_done`. Falls back to page time where a
stamp is missing (mid-flow deploys).
**Rejected:** page-time detection with a phase-labelled display — the pill
would name a phase the verdict never measured.
**Enforced:** `scripts/tests/dashboard_test.py` §D3 (page-ageing alone must NOT trip
the intro phase; stamp-ageing must); the render check asserts the pill text.

## The return click is best-effort instrumentation, and the pill is gated on the button existing — 2026-08-13

"Finished here but never clicked Back to Prolific" is flagged ONLY when
`prolific_completion_redirects` is on — with no redirect there is nothing to
click, and the flag would fire on every lab participant forever (Julian's
critical condition; the gate comment in `_participant_row` is load-bearing).
The click stamp (`prolific_return_clicked`) rides the Results page's live
socket just before navigation, so it can be lost — absence means "no click
RECORDED", and the pill is a prompt to look, never a verdict. A grace period
(`DASHBOARD_RETURN_GRACE_SECONDS`) stops it firing on completers still reading
their receipt.
**Rejected:** routing the exit link through a stamping redirect — exact and
JS-free, but it puts instrumentation INSIDE the one path every completer
needs, and instrumentation must never be able to break a page (CLAUDE.md); the
link stays a plain href that works with the whole mechanism dead.
**Enforced:** `outro.results_live_method` (gated the same way);
`scripts/tests/dashboard_test.py` §D8 pins the gate from both sides; CODEBOOK.md
documents the stamp's best-effort nature.

## The shipped quiz items are machinery placeholders, not model items — 2026-08-13

Deliberately trivial ("What is ice when it melts?"), because they exist to
exercise the quiz machinery — wrong answers, retries, the attempt log, the
thresholds — and are replaced wholesale by every real study.
**Rejected:** shipping an exemplary Stag Hunt comprehension item. It would read
as content to keep, and the previous item ("If you fail the quiz twice…") also
hard-coded the failure threshold into participant copy and described behaviour
the shipped config doesn't produce.
**Enforced:** the comment atop `intro/quiz_items.py`;
`scripts/tests/example_quiz_content_test.py` §3 pins the placeholders and is designed
to fail when a study writes its own items, forcing the test to be rewritten
with them (see `docs/skills_claude/writing_quiz.md` for what real items look like).

## The quiz-bonus rule is stated in two places, deliberately — 2026-08-13

Once in the payment overview (`intro/instructions_text.html`), once as the
reminder directly before the quiz (`intro/prequiz_text.html`), both now naming
*which* quiz ("every quiz question on the instructions").
**Rejected:** stating it once — the pre-quiz reminder is worth the duplication.
**Enforced:** nothing. Two cross-referencing comments ("if the rule changes,
edit BOTH") rely on the next editor reading them.

## Missing completion codes degrade to `REPLACE_CC`, never to `None` — 2026-08-13

`outro.completion_link` reads codes through the safe accessor, so a session
frozen before a code existed builds the shipped `REPLACE_CC` placeholder into
the URL. Chosen *because* it produces the same symptom as the already-known
failure "nobody replaced the placeholder": anyone seeing `REPLACE_CC` knows
instantly what it means and what to do, while `?cc=None` looks like a bug of
ours and tells the operator nothing.
**Enforced:** `outro.completion_link` (reasoning in its docstring); pinned by
`scripts/tests/frozen_config_test.py`.

## The config-drift check has two severities, so it stays trustworthy — 2026-08-13

The pre-deploy audit of frozen session configs FAILS on exactly two things —
a key missing from a frozen config, and a surviving `REPLACE_*` placeholder —
and merely *reports* every other difference.
**Rejected:** failing on any difference. A session legitimately runs older
thresholds and `static_version` changes on nearly every deploy, so an
all-differences failure fires every time, gets ignored within a fortnight, and
then catches nothing — including the real cases.
**Enforced:** `scripts/predeploy_check.py` (`audit_frozen_session_configs`);
its docstring carries the warning not to promote diffs to failures.

## The logo footer is a rule, not a per-page arrangement — and yields first — 2026-08-13

The logo strip sits at the bottom of the white card, below its divider,
identically on every page that shows it — enforced structurally (`order: 999`,
`margin-top: auto`) so a template that includes it in the wrong place still
renders it right. Because it is decoration, it is the first thing to shrink
when vertical space runs short (mark height drops at the short-viewport
breakpoint).
**Rejected:** each template getting the markup order right — a new page copies
whichever page its author happened to open.
**Enforced:** the LOGO FOOTER RULE block in `_static/global/css/base.css`;
logo geometry is in `scripts/tests/geometry_baseline.json`.

## Styling is shared components, never page-local patches — 2026-08-13

A page template composes named classes from `_static/global/css/`; no inline
`style=`, no one-off rule to fix a single page, and every new component gets an
INTENTION comment plus a specimen in `_static/global/html/template.html`.
Driven by three real bugs of the same shape: a class referenced by three
templates and defined nowhere, one concept carrying two widths, and an inline
`height` beating the component's own rule. Genuine one-screen exceptions are
marked `EXCEPTION` with the reason.
**Enforced:** the Styling section of `CLAUDE.md`; layout drift is caught by
`scripts/tests/render_check.py` against the geometry baseline. The no-inline-style rule
itself relies on review. Full working: `_ai/css_divergence_report.md` (local only — `_ai/` is gitignored; not in a clone).

## "Flags decide mechanics, `recruitment` decides copy" — 2026-08-13

Every sentence a participant reads that names the platform, the room, or how to
reach a human branches on `recruitment`; module flags answer only "does the
machinery exist". Driven by a found dead end: the consent page inferred
"Prolific" from one flag, the screen-out page from another, and a
friend-test config told a participant to seek help through Prolific and then
gave them no way out at all — no error, no failing test.
**Rejected:** letting whichever flag is nearest stand in for the study type.
**Enforced:** `common.is_lab` / `common.is_prolific` are the only two
implementations; `scripts/tests/copy_routing_test.py` asserts the impossibility;
`settings._prelaunch_problems` refuses the config combination that created the
dead end.

## Completion fires when the results page loads — identically in both variants — 2026-08-12

`exit_code` becomes `finished` in `Results.vars_for_template`, not on the
"Back to Prolific" click. This reversed an earlier request, and the principle
behind the reversal outranks the detail: **lab and Prolific diverge only where
genuinely essential**, because every divergence can be true in one variant and
quietly wrong in the other, forever. A participant who closes the tab without
clicking has still finished; the click is Prolific's concern, not the data's.
**Enforced:** `outro/__init__.py` (`Results.vars_for_template`, idempotent);
`scripts/tests/full_journey_test.py` asserts exit code 1 at Results. The
minimal-divergence principle itself has no guard — the caller-list warning on
`common.is_lab` and review are what hold it.

## ~~A screened-out Prolific participant gets a codeless link back~~ — 2026-08-12, SUPERSEDED 2026-08-15

The way off the screen-out page is a plain link with **no completion code**,
because submitting a code closes the Prolific submission, and a returned
submission can never be retaken — which forecloses exactly what the page asks
("come back on a computer"). The old `error_code`/`REPLACE_ERR` pair was
removed for this reason and must not come back. Corollary (2026-08-13): being a
Prolific study and offering a screened-out exit are the same commitment, so the
dependency is enforced, not documented.
**Enforced:** the no-screened-out-code note in `settings.py`;
`settings._prelaunch_problems` refuses a `recruitment='prolific'` config with a
blank or unreplaced `prolific_screenout_return_url`;
`scripts/tests/copy_routing_test.py` walks the codeless way out end to end.

> **SUPERSEDED 2026-08-15 by "Every ending population gets its own completion
> code" (below/newest).** The reasoning above is kept, not deleted, because a
> reader who meets the codeless design in an older study — or who reasons their
> way back to it — should be able to see that it was reconsidered and why,
> rather than find it silently gone.
>
> **What it got right:** submitting a completion code does close a Prolific
> submission, and a returned submission cannot be retaken. That is still true.
>
> **What it got wrong:** it treated "leave the submission open" as the kind
> outcome. In practice a bare researcher URL leaves the submission sitting in
> LIMBO — the participant has been turned away, cannot continue, and nothing
> tells Prolific anything; the place stays occupied until it times out. A
> Prolific REQUEST_RETURN code is not the same instrument as a completion code:
> it actively PROMPTS the participant to return the submission, which is the
> outcome that frees the place and ends the ambiguity. The screened-out exit is
> now `prolific_device_code` used as a full completion URL, and
> `prolific_screenout_return_url` is gone as a setting.

## The screen-out return URL ships as a placeholder, not a working default — 2026-08-12

It used to ship as `https://app.prolific.com/`, which works — and that is the
problem: **a plausible default never gets checked**, and the person who
discovers it was wrong for this study is a participant already turned away.
**Enforced:** the `REPLACE_*` family is flagged by the prelaunch banner and by
the pre-deploy frozen-config audit's PLACEHOLDER severity.

## The device screen-out is a soft wall, clearable before consent only — 2026-08-12

A screened participant is HELD on the entry page (not walked to an ending oTree
could never bring them back from), and a later pre-consent request from an
accepted device clears the screen-out; exit code `-4` is the one code that can
revert. After consent the check never applies again. The state is reset, the
history never is — "how many did the gate turn away" is counted from
`screenout_history`, not the exit code.
**Rejected:** routing to a proper ending page (irreversible in oTree), and a
write-once `-4` (would leave genuine finishers recorded as screened out).
**Enforced:** `scripts/tests/screenout_softwall_test.py`; the consent boundary is the
durable `participant.consent_submitted` fact, not a page index. Full working:
`_ai/screenout_softwall_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The clear predicate is exactly the entry-allow predicate minus `undetermined` — 2026-08-12

If clearing allowed *more* than entry, a screen-out could be lifted by a device
that would not have been let in; if *less*, the page tells someone switching
will work when for them it cannot (the reference implementation had this bug:
its `unknown` never cleared, stranding privacy-proxy laptops). `undetermined`
is the single carve-out — no usable header is not a device, and treating it as
a clear would let anyone lift their own screen-out by sending no User-Agent.
**Enforced:** `common.device_clears_screenout` (explicit membership, so
`undetermined` cannot satisfy it whatever a config says);
`scripts/tests/screenout_softwall_test.py` §8 states the two asymmetric assertions side
by side.

## `unknown` and `undetermined` are different states — 2026-08-12

A User-Agent that parsed and matched nothing (`unknown`) is a device type a
study may accept or reject like any other; no usable header at all
(`undetermined`) is *not a device type* and must always be allowed. Collapsed,
a study rejecting `unknown` starts ejecting laptops behind privacy proxies.
This is the model case of the collapsed-distinction rule in `CLAUDE.md`.
**Enforced:** `common.classify_device`; `scripts/tests/device_gate_test.py`, which is
deliberately weighted toward false positives (browsers that must NOT be
screened). Full working: `_ai/device_allowlist_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The lab comprehension rule is help, not ejection — unlimited attempts — 2026-08-12

Online, crossing the failure threshold disqualifies (`comprehension_dq`); in
the lab the same threshold *starts the study helping*: the one-time re-read
offer (if `quiz_reread` is on), then a dismissible "raise your hand" notice,
escalating at twice the threshold — and the participant may keep trying
forever. The notice is keyed on the threshold and the study type, NOT the
module, so a lab session with `quiz_reread` off still calls the experimenter.
The notice deliberately does not say "you can keep trying" — some participants
should raise a hand instead of brute-forcing radio items.
**Rejected:** disqualification in the lab (there is a human in the room), and
keying the notice on the module (left a module-off lab session with no help at
all).
**Enforced:** `scripts/tests/gated_flow_test.py` (lab-reread and prolific-dq
scenarios); the prelaunch check refuses `comprehension_dq` in a lab config;
attempts proven uncapped by `scripts/tests/quiz_attempt_log_test.py`. Full working:
`_ai/lab_comprehension_proposal.md` (local only — `_ai/` is gitignored; not in a clone).

## Every graded quiz submission is logged — uncapped, and unable to break the page — 2026-08-12

`quiz_attempt_log` records what was answered and what was wrong *as judged at
the time* (never re-graded — the item set changes between studies), with no cap
on entries, and the whole write is wrapped so instrumentation can never cost a
participant their page.
**Enforced:** `intro.log_quiz_attempt` (never raises);
`scripts/tests/quiz_attempt_log_test.py` proves 25 attempts stored and the page still
standing.

## The tab monitor is armed before the instructions and quiz, not after — 2026-08-12

> **CORRECTED 2026-08-13 — see the monitored-by-default entry above.** This
> entry implied the move made the instructions and quiz monitored. It did
> not: only the AGREEMENT moved; no monitor wiring existed in `intro`, so the
> quiz stayed unwatched for a day while four documents said otherwise. The
> enforcement below pinned page ORDER, never coverage — which is how the gap
> survived its own test. Coverage is now real, and enforced at boot.

The agreement page moved from the end of `intro` to `before`: armed after the
quiz, the very check that gates entry was unmonitored — a participant could
consult an AI assistant during it, which is exactly what the page warns
against.
**Enforced:** the page lives in `before.TabMonitorAgree`; a comment in
`intro/__init__.py` forbids moving it back; `scripts/tests/gated_flow_test.py` asserts
the agreement is not after the quiz.

## Participant identity is decided in one place — 2026-08-12

"Is this the same participant id?" was answered twice — label comparison in
Python (case-folded) and row lookup in SQL (collation-dependent) — so a
returning `ABC123` took a fresh row against a stored `abc123`, and behaviour
differed between sqlite (dev) and postgres (production). One implementation,
called by both.
**Enforced:** `identity.py`; `scripts/tests/identity_test.py`. This bug pattern is
generalised as the inverted collapsed-distinction rule in `CLAUDE.md`.

## The layout geometry baseline is committed, so intentional change is reviewable — 2026-08-12

`scripts/tests/render_check.py` measures element geometry at three viewports;
`scripts/tests/geometry_baseline.json` is committed **on purpose** (to `scripts/tests/`, not
gitignored `_ai/`) so an intentional layout change shows up as a reviewable
diff of that file, and an unintentional one fails `--diff`. Layout failures
produce no error otherwise — nothing 500s while the participant gets a broken
page.
**Enforced:** `render_check.py --diff` exits non-zero on movement beyond ±3px;
adopting a change requires `--update-baseline` and reading the diff.

## Three orthogonal controls; profiles resolve to explicit config keys at import — 2026-08-10

Study type, DEBUG (env-driven, so production can never ship skip controls), and
the pilot feedback form are independent axes; there is no "testing" study type
— testing loosenings are a reversible override honoured only under DEBUG. A
recruitment profile is rewritten into explicit per-config keys at import, so
the admin shows exactly what a session ran with and a profile can never change
behaviour silently at runtime.
**Rejected:** a `testing` study type (collapses two axes and lets loosenings
ship), and profiles consulted at runtime (invisible in the admin, mutable under
running sessions).
**Enforced:** `settings.resolve_recruitment_profile`;
`scripts/tests/frozen_config_test.py`; DEBUG derived from `OTREE_PRODUCTION` presence.

## Exit codes: initialised at creation, `0` means "never reached an ending" — 2026-08-07 (ported from the pilot)

Every participant carries `exit_code` from session creation, so no export row
is ever blank; `0` is *abandoned* — created but never reached any ending — and
is distinct from every deliberate outcome, each of which has its own code
(screened-out is `-4`, not `0`: you must be able to tell the gate's work from a
closed tab). A code nothing records is a lie in the export, so
reserved-but-unwired codes are deleted, not documented (`timed_out`, removed
2026-08-10).
**Enforced:** `common.init_participant`; the codes table in `CODEBOOK.md`;
tests assert on numeric codes rather than ending copy
(`full_journey_test`, `device_gate_test`).

## Participant and config reads go through safe accessors, always — 2026-08-07 (ported from the pilot)

`participant.vars.get(...)` (never `getattr` — the vars descriptor raises
`KeyError`, which the getattr default does not catch: a live outage), and
`common.cfg(...)` (never `config[...]` — a session config is frozen at
creation, so later-added parameters are absent for running sessions: also a
live outage). `common.flag` is the deliberate exception: a module flag missing
from a frozen config means the module post-dates the session and must read as
OFF.
**Enforced:** `common.pvar` / `common.cfg` / `common.flag`;
`scripts/tests/frozen_config_test.py` strips keys and walks; the rules are in
`CLAUDE.md`'s correctness list.

## A test that cannot fail is not evidence — standing principle

Bot tests passing is not evidence a browser works (three pilot outages went
green under bots); a content test loosened until it survives a content change
was never testing the content; a drift check that fails on everything gets
ignored and then catches nothing (see the two-severity entry above). Every
check must correspond to a participant it could save.
**Enforced:** as method, in `docs/skills_claude/writing_tests.md` (real HTTP, no-JS
submits, phone User-Agents, visible-text assertions, measured rendering);
structurally, nowhere — this one is held by review and by the suites being the
shape they are.
