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

## Hidden-field measurement — on the page's own form, tolerant of empty

Client-captured data (device info, time-on-page, the tab monitor's arming) rides
on the page's OWN form as hidden fields, submitted in the same POST — never a
side request. Every such field is `blank=True` and read with `field_maybe_none`,
because JS may be disabled or blocked and the field then arrives EMPTY; an empty
submission must be stored, never 500. There is a test for exactly this.
*Where:* `before` (device capture), `main` (`client_ms` passive capture);
`_static/global/js/device_capture.js`; `tests/`.

## Numeric exit codes — initialised at creation so no export row is blank

Every participant carries `exit_code`, set to 0 (abandoned) at session creation
and raised to 1 on a clean finish or a negative reason on early exit. The
integrity modules, the no-consent short-circuit and the entry screen-out gate
set the reason; the ending screen reads it to pick the Prolific completion code.
Every code in the table must be **set by real code** — a code that nothing
records is a lie in the export, so a reserved-but-unwired code gets deleted, not
documented. See `settings.EXIT_CODES` and the CODEBOOK.md exit-code table.

## Modules (all OFF by default)

- **capture_participant_id** — capture an external (Prolific) ID at entry (`before`).
- **completion_redirects** — explicit consent + "Back to Prolific" endings keyed
  by exit code (`before`, `outro`).
- **tab_monitor** — server-authoritative tab-switch / AI-safety monitor: an
  arming page (`intro`), a live handler counting deduped violations
  (`common.focus_live_method`) bound to the task pages, and a disqualified
  ending. Thresholds are config values; the client JS reads them via `js_vars`.
- **comprehension_dq** — disqualify after `comprehension_max_failures` wrong quiz
  attempts, routing to the ending (`intro`). The online (Prolific) rule.
- **quiz_reread** — the lab rule for the same threshold: offer ONE re-read pass
  through the instructions (intro round 2, consumed on entry, not on offer);
  once spent, further failures show a dismissible "raise your hand" notice and
  the participant may keep trying — no disqualification (`intro`).
- **passive_capture** — hidden-field time-on-page on the task form (`main`).
- **device_capture** — device/screen JSON at entry, measurement only (`before`);
  the `is_mobile` field it fills blocks nobody.
- **mobile_screenout** — `0`/`1` option (not part of any recruitment profile, so
  choosing `prolific` never turns it on). At `1`, the entry request's User-Agent
  is checked server-side BEFORE the consent page renders (`before.welcome.get`);
  a phone never sees consent, records exit code `-4` and is walked straight to
  the outro ending (`error_code` on Prolific). At `0` the check does nothing —
  no participant-visible effect of any kind.
- **collect_bank_details** — lab IBAN/BIC/SEPA payment collection (`outro`).
- **collect_demographics** — explicit demographics questionnaire (`outro`); off
  for Prolific, which supplies demographics in its own export.
- **pilot_feedback** — free-text feedback page before the results (`outro`);
  its own axis: on for pilots/friend tests, off for the real run, independent
  of study type and DEBUG.
