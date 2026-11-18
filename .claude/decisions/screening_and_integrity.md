# Decisions: Screening and integrity

Read when you touch the tab monitor, the focus trace, or bot and inattention detection.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## AI-bot & inattentive-participant detection — the two-bucket build — 2026-09-08

Built from `_ai/ai_bot_detection_spec.md` (design settled by Julian 2026-09-07).
Adds a detection layer that distinguishes "a bot arrived" from the existing
tab-monitor / comprehension / device gates, keeps it invisible in the lab, and
can be disarmed for the AI bots we run to test our own studies. The design rests
on an **A/B split**, and every piece below is placed to keep that split coherent.

- **Two orthogonal new controls, not one.** `bot_detection` is the MODULE flag
  (bucket A on/off), resolved ON in the prolific profile and absent/OFF in the
  lab, read via raw `common.flag` (missing ⇒ off). `bot_detection_armed` is a
  **fourth independent axis** in `SESSION_CONFIG_DEFAULTS` (default `True`),
  **not** in any recruitment profile and **not** tied to DEBUG or study type,
  read via `common.cfg` (missing ⇒ armed, the safe direction). *Why two, kept
  apart:* the module can be present-but-not-ejecting so our AI testers run the
  gates and record verdicts without being screened out — and that has to work in
  **study mode** (`OTREE_PRODUCTION=1`), which is exactly when a DEBUG- or
  study-type-tied switch would be unreachable. Enforced: `common.bot_detection_active`
  (module runs) vs `common.bot_detection_armed` (and ejects); the fourth-axis
  header in `settings.py`; `scripts/tests/bot_detection_test.py` §3.

- **A disarmed launch LOUD-FAILS but is OVERRIDABLE — the tension is the point.**
  Because the switch is reachable in production, `settings._prelaunch_problems`
  makes `bot_detection_armed=False` a hard-stop (so `scripts/prelaunch_check.py`
  exits non-zero and the boot banner prints it in the `####` block), for ANY
  recruitment and regardless of DEBUG. It is deliberately waivable by an explicit
  `ALLOW_DISARMED_BOT_DETECTION=1`, which turns the failure into a printed,
  acknowledged waiver line (`_disarmed_waiver_line`, shared by the banner and the
  script). *Rejected:* softening to an advisory (a forgotten disarm would ship a
  wide-open study) and hardening to unskippable (a disarmed study-mode bot run
  must be possible on purpose). Enforced: `bot_detection_test.py` §7 pins all
  three cases.

- **Two ejectors, both GENTLE, one shared ending.** The welcome decoy honeypot
  (A1, `before.welcome`) and the DOT-BI visual gate (A2, `before.DotBiGate`) both
  set exit `-5 bot_return`, split by `participant.bot_detection_cause` ∈
  {`honeypot_welcome`, `dot_bi`}, and route to ONE non-accusatory
  `outro.NeutralReturn` screen (prominent RETURN button, "no penalty" wording,
  never revealing the mechanism). *Why gentle, not a DQ:* a real human can trip
  either (a password manager ticking a hidden control; a `prefers-reduced-motion`
  reader who genuinely cannot solve a motion challenge), so it must never accuse
  — the false-positive class and the gentle handling are tied. The collapsed-
  distinction rule is satisfied by the CAUSE (two populations, one code), and
  `-5`/`-6` are kept apart from the punitive `-2`/`-3`. Enforced:
  `common.is_neutral_return` (one predicate read by the routing belt and the
  page), `Ended.is_displayed` narrowed to cede these, `bot_detection_test.py`
  §1/§1b.

- **No-JavaScript at DOT-BI is its OWN code (`-6 no_javascript`), and the
  off-switch does not touch it.** JS-capability is not a bot signal, so it gets a
  separate neutral code and its own return code, but the same gentle screen. It
  fires whenever the module is active and JS did not run — armed or disarmed —
  because a disarmed session still owes a JS-less participant the friendly return.
  The DOT-BI page is progressive-enhancement: challenge hidden by default (static
  CSS), `dot_bi.js` reveals it and sets a "JS ran" flag; its absence at submit is
  how the server routes to `-6`. Enforced: `bot_detection_test.py` §2;
  `before.DotBiGate.before_next_page`.

- **DOT-BI answer served under an OPAQUE id; graded server-side; never leaks.**
  The upstream repo encodes the answer only in the filename stem, so a subset of
  15 variants is vendored under opaque ids (`_static/global/img/dot_bi/dotbi_NN.gif`,
  ~37 MB, GIFs unaltered) and the id→answer map lives in `core/dot_bi.py`, server-side,
  never under `_static/` and never sent to the client. *Format choice:* kept the
  original GIFs, NOT re-encoded — lossy compression of the random-noise texture
  can destroy the concealment and human-solvability could not be verified here,
  so per the spec we keep GIFs and ship fewer. MIT LICENSE + ATTRIBUTION retained
  beside the variants. Enforced: `bot_detection_test.py` §5 (answer/number/filename
  absent from the page; opaque id is the media reference).

- **Bucket B is record-only and recorded EVERYWHERE, including the lab.** The
  results-stage "Completed" checkbox honeypot (decoy label / truthful field name
  `honeypot_results_failed`) and the welcome/quiz behaviour capture
  (`telemetry_welcome`/`telemetry_quiz`, one shared `telemetry_capture.js`
  re-authored from the Mission Possible tracker approach) never eject and keep
  recording even when the off-switch is on. *The results checkbox lives ON the
  terminal `Results` page as a LIVE-DATA field, not a form-submit field (Julian,
  2026-09-08).* `Results` is terminal — its no-JS completion link is a real `<a>`
  (heavily pinned, render_check leg AF), and a form submit there would send the
  participant to oTree's `OutOfRangeNotification` with no way back to Prolific
  (verified in the oTree source). So the checkbox pushes its state over the
  **live socket** — the SAME channel as the tab-monitor `live_method`
  (`outro.results_live_method` delegates to it) — with NO extra screen and the
  terminal page fully intact. THE DEFAULT IS THE TRIP: reaching `Results` records
  `10`, and only a socket-pushed TICK records `0` (compliant); a no-JS human
  stays at the default `10`, which is fine for a record-only end-stage honeypot
  since a no-JS bot is already stopped at the DOT-BI gate. Init stays `0` so a
  NON-completer who never reached `Results` reads `0` ("complied OR never
  reached", disambiguated by `exit_code`). An earlier build used a standalone
  `CompletionCheck` page before `Results`; it was removed because it added a
  screen and Julian wanted the checkbox on `Results` with the link untouched. The
  derived AI-likelihood flags are computed EX-POST in
  `scripts/format_session_data.py` (thresholds 75 ms / 50 chars, re-tunable in
  one place), which then blanks the raw JSON in the analysis-ready export.
  Enforced: `bot_detection_test.py` §4/§6 (incl. a direct `results_live_method`
  record-logic check), `bot_render_check.py` (checkbox visible + link intact on
  Results), `scripts/tests/telemetry_derivation_test.py`.

- **The prolific profile now ships the gates armed, so every prolific-completing
  walker must pass them.** The DOT-BI answer is computed the server's way in ONE
  shared test helper (`scripts/tests/bot_walker.py`, `dot_bi` loaded by path, the
  participant code as the variant seed) and the welcome decoy is passed by leaving
  its checkbox untouched. A real bot has neither the repo module nor the
  participant seed, so the test's ability to solve the gate is a property of the
  harness, not a leak. `frozen_config_test`'s `STRIPPED` list gained the new keys.

---

## Passive focus trace ported alongside the tab monitor, as a separate observer — 2026-08-18

Ported the passive focus/multitasking trace from `exp_pilots` (which forked from
this template) as NET-NEW per-page MEASUREMENT, added ALONGSIDE the existing tab
monitor and never on top of it. The template already logs a rich tab-monitor
event log and DISQUALIFIES on long departures; what it lacked is a passive,
per-page record of how much time the page spent unfocused/hidden and how many
times the participant left — as measurement, not enforcement.

**What it is.** A new browser file `_static/global/js/focus_trace.js` and two
per-round `main.Player` columns, gated by a new telemetry flag. Both columns are
`blank=True`, filled by hidden inputs on the task page's own form (the
`client_ms` mechanism, never a side request), and read with `field_maybe_none`.

**Naming (proposed for Julian to confirm).** The bare `exp_pilots` names collide
here — `focus_loss_count` reads as a sibling of the template's
`tab_monitor_focus_loss_count`, which means a *different* thing — so the trace
takes its own non-colliding `focus_trace_` family:
* flag: **`telemetry_focus_trace`** (telemetry family; ON in the prolific
  profile, OFF in lab, like `telemetry_passive_capture` / `_device_capture`);
* columns: **`focus_trace_departures`** (was `focus_loss_count`) and
  **`focus_trace_unfocused_ms`** (was `focus_unfocused_ms`);
* hidden-input ids match the column names; the JS is its own static file.

**The separate-observer guarantee (the load-bearing part).** `tab_monitor.js` /
`tab_monitor.py` are UNCHANGED. `focus_trace.js` adds only its own DOM listeners
(`blur`, `focus`, `visibilitychange`, `mousedown`), keeps only its own state,
and NEVER calls `preventDefault`, NEVER calls `liveSend`, NEVER reads or writes
any tab-monitor variable, and NEVER disqualifies. DOM listeners are additive, so
two independent listeners on the same event cannot interfere. It is a NO-OP on
any page without its hidden inputs, and the whole body is wrapped so
instrumentation can never break a page. This is deliberately the same design
`exp_pilots` used, and for the same reason: the cost of entangling measurement
with the disqualification path is a participant wrongly ejected (or wrongly not).

**Verified against the exp_pilots CLAIMS, not the docs.** A real-Chromium check
drives synthetic `blur`/`visibilitychange`/`mousedown` at the actual JS and
confirms: one departure counts once however the browser reports it (blur +
visibilitychange dedupe via the open-interval guard); a blur within 300 ms of a
mousedown is ignored; the unfocused ms include an interval still open at submit;
a clean page posts 0 / 0.0. And that the trace ARRIVES in `main.Player`
end-to-end, independent of the tab monitor (positive trace, zero violations).

**Rejected — storing in the participant JSON bucket to dodge the schema change.**
It would have kept the upgrade path hot-deployable, but it breaks parity with
the sibling `client_ms` telemetry (a real `main.Player` column) and with
`exp_pilots` (per-round `main.Player` fields), and the per-round export wants
real columns. So the trace is two real columns, and the schema-change cost is
accepted and documented (below).

**Enforced:** `scripts/tests/focus_trace_test.py` (wiring both ways, arrival,
no-JS safety, independence from the tab monitor incl. a source-level check that
`focus_trace.js` names no tab-monitor symbol, and the exp_pilots claims in a real
browser); `scripts/tests/http_flow_test.py` and `frozen_config_test.py` extended
for the two new fields; `docs/CODEBOOK.md` ("Passive focus trace").

**Schema-change consequence (the same rule as `round_payoff`).** This appends
two `main.Player` columns, and oTree's `create_all` never ALTERs an existing
table, so deploying it over a database that predates the columns 500s on every
page that loads the model — it needs `otree resetdb`, exactly like every prior
added column (docs/CODEBOOK.md deploy note). The template has no live data, so this is
free here; a STUDY already running must add the trace at a reset boundary, never
hot over live sessions (the CLAUDE.md rule on schema changes). The local
predeploy fixture (`_ai/live_data/`, gitignored) was regenerated on the current
schema so `predeploy_check.sh` upgrade mode returns to its documented 8/9
baseline (only the deliberate REPLACE_* completion-code check fails).

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

**The stage value was changed even though stage values are frozen** (`core/common.py`
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
frozen-values note in `core/common.py`, the CODEBOOK stage table, and the test suites
(`dashboard_test`, `task_page_test`, `tab_monitor_detail_test`, `full_journey_test`,
`gated_flow_test`) which reference the class and stamp and go red on a half-done
rename.

---

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
inconsistent: `common._apply_focus_loss`, `core/participant_tab_monitor.py`, the top of
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

---

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
