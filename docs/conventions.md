# Conventions

The principles behind this template's participant-facing and experimental
screens. These are the *ideas* a screen must honour; the concrete rules that
enforce them live in the code, with a pointer under each principle. When a screen
looks or behaves oddly, check it against these first.

> Implementation detail is deliberately **not** repeated here — read the CSS/JS
> at the pointers for the exact selectors, values and mechanics. This file is the
> "why"; the code is the "how".

## Stability — nothing on screen may shift when states change

A participant should never see the page move under them. Anything that can appear,
disappear or change while a page is open must have its space reserved from the
start, so revealing or clearing it moves nothing else. The same rule covers
programmatic form changes: a script that fills a form must never let the
participant glimpse the controls being set before navigation.
*Where:* the `.reserve-height` utility and `.submit-veil` in
`_static/global/css/base.css`; the instructions Page counter is toggled with
`visibility` (space kept) in `_static/global/js/instructions.js`, and the
DEBUG skip veils the frame before submitting in `_static/global/js/quiz.js`.

## Layout — fill and centre the viewport, scroll only on overflow

A card that fits the viewport sits centred both vertically and horizontally, with
comfortable margins. A card taller than the viewport grows the page and scrolls
downward — it is never clipped, and short pages never collapse to a stub.
*Where:* `.experimental-screen` (`min-height: 100vh`, flex-centred, roomy
padding) and `.screen-card` (`min-height: 75vh` floor) in
`_static/global/css/base.css`.

## Typography — reading measure for prose, full width for controls

Running text is held to a comfortable reading measure (~62ch), centred as a
column in the wider card and justified, with titles flush-left against the text's
left edge. Controls, forms, tables and widgets are the opposite: they keep the
full card/band width and are **never** clamped to the reading measure. Wide
content scrolls inside its own container rather than forcing the page sideways.
*Where:* `--reading-measure` and the prose selectors in
`_static/global/css/base.css`; the block-level rules in
`_static/global/css/instructions.css`; `.table-scroll` in
`_static/global/css/results.css`.

## Testing affordances — DEBUG-gated, veiled, invisible in production

Screens carry tooling (skip buttons, auto-filled answers) to move through the
flow while testing. Every such affordance is gated on `settings.DEBUG`, submits
through the same validation a participant would, and never reaches the browser in
production — the correct answers are not even emitted outside DEBUG.
*Where:* `is_debug` gating in `intro/__init__.py`, the skip controls in
`intro/templates/instructing.html` and `intro/templates/quiz.html`, and the
muted `.skip-button` / `.debug-tools` styling in `_static/global/css/base.css`.

## Parameterisation — no design number hard-coded in flow logic

Quantities that define the study (round counts, number of paid rounds, bonuses,
fees) live in one place and are read from the session config; flow logic refers
to those, never to a bare literal, so a study is re-parameterised by editing
config, not by hunting through pages.
*Where:* `SESSION_CONFIG_DEFAULTS` in `settings.py`, read via `session.config`
in the apps and derived into `C.NUM_ROUNDS` in `main/__init__.py`.

## Reading participant fields — always `participant.vars.get`, never `getattr`

Never read a participant field with `getattr(participant, name, default)`.
oTree's participant-vars descriptor raises **`KeyError`** — not
`AttributeError` — for a field that has not been set yet, so the `getattr`
default does **not** protect you and the page 500s. This caused a live outage.
Always use `participant.vars.get(name, default)` (or the `common.pvar` helper).
The same trap breaks `hasattr(participant, name)`: it lets the `KeyError`
propagate. Fields you might read before they are written must be initialised at
session creation (`common.init_participant`) or read defensively with `.vars.get`.
*Where:* `common.pvar` / `common.init_participant`; every participant read in
`before`, `intro`, `main`, `outro`.

## Naming participant fields — family first, unit last, so an export groups by outcome

Name a participant tracking field **family first, unit last** — roughly
`family_object_measure`, with an optional unit suffix (`_ms`, `_count`,
`_outro`). Every field about one outcome shares that outcome's prefix, so when
the fields are read as export columns they sort into families instead of
scattering the same instrument across the alphabet. The tab monitor's fields all
begin `tab_monitor_` (`tab_monitor_disqualified`, `tab_monitor_focus_loss_count`,
`tab_monitor_focus_loss_count_outro`, `tab_monitor_focus_event_ids`,
`tab_monitor_focus_events`, `tab_monitor_focus_losses_missed_at_least`,
`tab_monitor_flag`, `tab_monitor_where`); comprehension's begin `comprehension_`
(`comprehension_failed_attempts`, `comprehension_reread_used`,
`comprehension_disqualified`); the screen-out's begin `screenout_`
(`screenout_active`, `screenout_cleared`, plus the `screenout_cause` /
`screenout_history` keys inside `participant_extra`). Prefer a name that says the
mechanism it measures over one that borrows the participant-facing cover story:
the AI-safety agreement's disqualification is stored as `tab_monitor_disqualified`
because the data should name the tab-switch monitor, even though the participant
never reads those words.

**The one sanctioned exemption is the `t_` timestamp prefix**, a namespace of its
own that marks a field as a measured time and is not folded into an outcome
family.

**This is a CONVENTION, not a rule, and it is deliberately NOT enforced** — there
is no import-time or boot-time check that field names match the pattern, and that
absence is a considered exception to this template's habit of enforcing invariants
at boot (see `prelaunch_check.py`, the frozen-config guard, the exit-code table).
A study copied from this template may reasonably want different field names for
its own outcomes, and a boot check would turn that ordinary choice into a failure
to work around. Read the missing check as intentional, not as an oversight. The
full reasoning is in `DECISIONS.md` ("Participant tracking fields are named
family-first").

*Where:* `settings.PARTICIPANT_FIELDS` (the single central list, with a
description block) and `CODEBOOK.md` are the documented source of the field
names; nothing enforces the pattern by design.

## Feature flags and recruitment profiles — resolved once, visible, never silent

Three independent axes (top of `settings.py`) determine what a participant
experiences: **study type** (`recruitment`: `prolific` | `lab`), **DEBUG**
(env-driven; all dev loosenings, including `verify_quiz=False`, are honoured
only under DEBUG), and the **pilot feedback form** (`pilot_feedback`). None of
them implies another; there is no `testing` study type.

Every optional module is one feature flag in `SESSION_CONFIG_DEFAULTS`, shipped
**OFF**. The `recruitment` profile is a
named bundle of flag values; at import `resolve_recruitment_profile()` writes the
bundle's values into each session config as **explicit keys**, so the admin
session-configuration view shows exactly what the session ran with. A profile
therefore never changes behaviour silently at runtime — resolving it is a
one-time, visible rewrite; runtime code only reads the resolved explicit flags.
An explicit per-config value always overrides the profile.
*Where:* `RECRUITMENT_PROFILES`, `resolve_recruitment_profile`,
`SESSION_CONFIG_DEFAULTS` in `settings.py`. `C.NUM_ROUNDS` is **fixed at import**
(oTree builds its round tables from it): a config may run FEWER rounds, never
more (`main.creating_session` raises otherwise).

## Flags decide mechanics, `recruitment` decides copy

A module flag answers *"do we have the machinery to do this?"* —
`prolific_completion_redirects` means a completion code exists to send somebody back
with, `prolific_capture_participant_id` means a platform id is collected. **Neither means
"this participant is on Prolific", and neither may stand in for it.** Where the
participant *is* — alone on a platform, or in a room with an experimenter — is
`recruitment`, and **every sentence they read that names the platform, or the
room, or how to reach a human, branches on that**. Only the machinery itself
(does a link exist? is there a field to fill?) branches on a flag.

The rule is written down because breaking it is silent. When the consent page
inferred "Prolific" from `prolific_capture_participant_id` while the screen-out page next
door inferred it from `prolific_completion_redirects`, a `recruitment='prolific'` session
with `prolific_completion_redirects` off told a participant to contact the researchers
*through Prolific* and then served them a screen-out page with **no way out at
all** — a dead end that produced no error and failed no test. A page that must
say something to everybody needs a branch for everybody, ending in a neutral
fallback, not a chain of flags that can all be false.

**But this rule is the reasoning, not the mechanism.** Where a study type
*obliges* something, the obligation is enforced rather than documented, because
a rule written in prose is one somebody can still configure their way past. The
worked case: a Prolific participant has no experimenter to ask, so **a Prolific
study must offer a screened-out participant an exit** — being one and offering
one are the same commitment. That dependency is therefore enforced in
`settings._prelaunch_problems`, which refuses a `recruitment='prolific'` config
whose `prolific_screenout_return_url` is blank or unreplaced. The broken combination
cannot reach a participant, so the copy branch that would have had to apologise
for it is a runtime belt, not the fix.
*Where:* `common.is_lab` / `common.is_prolific` (the only two implementations,
read through `common.cfg`); the routing note at the top of `before/__init__.py`;
the guard in `settings._prelaunch_problems`; `scripts/tests/copy_routing_test.py`, which
asserts the impossibility and not merely the routing.

## Hidden-field measurement — on the page's own form, tolerant of empty

Client-captured data (device info, time-on-page, the tab monitor's arming) rides
on the page's OWN form as hidden fields, submitted in the same POST — never a
side request. Every such field is `blank=True` and read with `field_maybe_none`,
because JS may be disabled or blocked and the field then arrives EMPTY; an empty
submission must be stored, never 500. There is a test for exactly this.
*Where:* `before` (device capture), `main` (`client_ms` passive capture);
`_static/global/js/device_capture.js`; `scripts/tests/`.

## Numeric exit codes — initialised at creation so no export row is blank

Every participant carries `exit_code`, set to 0 (abandoned) at session creation
and raised to 1 on a clean finish or a negative reason on early exit. The
integrity modules, the no-consent short-circuit and the entry screen-out gate
set the reason; the ending screen reads it to pick the Prolific completion code.
ONE EXCEPTION, and it is deliberate: the entry screen-out's `-4` is reversible
while the participant is still pre-consent (the soft wall), so it is the one
code that is not write-once. The reversal is conditional — a value is only
reverted if it still holds what the screen-out put there — and it never touches
the audit history, which is what "how many were turned away" is counted from.
Every code in the table must be **set by real code** — a code that nothing
records is a lie in the export, so a reserved-but-unwired code gets deleted, not
documented. See `settings.EXIT_CODES` and the CODEBOOK.md exit-code table.

## Modules (all OFF by default)

- **prolific_capture_participant_id** — capture an external (Prolific) ID at entry (`before`).
- **prolific_completion_redirects** — explicit consent + "Back to Prolific" endings keyed
  by exit code (`before`, `outro`).
- **tab_monitor** — server-authoritative tab-switch / AI-safety monitor: an
  arming page (`before.AISafetyAgree`), a live handler counting deduped
  violations, and a disqualified ending. **Every page after the arming page is
  monitored BY DEFAULT** (`participant_tab_monitor.MonitoredPage`; a page opts out only by
  saying `monitored = False`), with one deliberate asymmetry — same monitor,
  same counting, different consequence by phase: during the instructions,
  quiz and task, violations eject at the threshold
  (`common.focus_live_method` → exit code `-3`); during the **outro they are
  recorded only** (`common.focus_live_method_outro` →
  `tab_monitor_focus_loss_count_outro`) and never eject, because by then the task is over
  and the data collected — disqualifying a completer would cost a real
  participant for no benefit. Thresholds are config values; the client JS
  reads them via `js_vars` and shows no warnings in the record-only phase.
- **comprehension_dq** — disqualify after `comprehension_max_failures` wrong quiz
  attempts, routing to the ending (`intro`). The online (Prolific) rule. **Not
  supported in the lab** (with `tab_monitor`; the pre-launch check fails on it).
- **quiz_reread** — the lab rule for the same threshold: offer ONE re-read pass
  through the instructions (intro round 2, consumed on entry, not on offer);
  once spent, further failures show a dismissible "raise your hand" notice and
  the participant may keep trying — no disqualification (`intro`). The notice
  itself is NOT part of this module: it is keyed on the threshold and the study
  type, so a lab session with `quiz_reread` off still calls the experimenter.
- **passive_capture** — hidden-field time-on-page on the task form (`main`).
- **device_capture** — device/screen JSON at entry, measurement only (`before`);
  the `is_mobile` field it fills blocks nobody.
- **allowed_devices** — the entry DEVICE ALLOW-LIST, and a SOFT WALL: the device
  types a study accepts, from `phone`, `tablet`, `computer`, `unknown` (not part
  of any recruitment profile, so choosing `prolific` never narrows it). The
  entry request's User-Agent is classified server-side BEFORE the consent page
  renders (`before.welcome.get`); a device whose type is not listed never sees
  consent — it is HELD on that same page index, which serves
  `before/screened_out.html` instead, and records exit code `-4` with the
  DETECTED TYPE as its screen-out cause. Held rather than walked to an ending
  because the verdict must stay re-decidable: a later PRE-CONSENT request from
  an accepted device CLEARS it (oTree only moves forward, so a participant sent
  to an ending could never come back to consent). After consent the check never
  applies again. The way out carries NO completion code, so their submission
  stays open. Shipped permitting all four types, so by default the check does
  nothing — no participant-visible effect of any kind. `computer` covers laptops
  and desktops alike (a browser cannot distinguish them, so there is no `laptop`
  type); `unknown` is a real User-Agent that matches nothing, and is admitted or
  excluded like any other type — while NO usable User-Agent at all is not a type
  and always allows. Full reference: "The device check" in README.md.
- **collect_bank_details** — lab IBAN/BIC/SEPA payment collection (`outro`).
- **collect_demographics** — explicit demographics questionnaire (`outro`); off
  for Prolific, which supplies demographics in its own export.
- **pilot_feedback** — free-text feedback page before the results (`outro`);
  its own axis: on for pilots/friend tests, off for the real run, independent
  of study type and DEBUG.
