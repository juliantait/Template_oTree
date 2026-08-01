# Template vs. pilot: what `exp_pilots` inherited, improved, and lost

Comparison of the fresh `oTree-Template` snapshot (`_ai/template_snapshot/`) against `exp_pilots/`, the calibration pilot built from it and heavily evolved during the coconut-island design. No code was changed in either folder; this is a read-only audit with file/line references.

The two share the same skeleton: a four-app sequence (`before -> intro -> main -> outro`), a shared static shell (`_static/global/...`), and the DEBUG-gated tooling conventions. The pilot then replaced the placeholder Stag Hunt game with the real belief-elicitation task, added deployment and test machinery, and rebuilt the CSS into a documented design system. Headline: **both flagged "lost" conventions are in fact intact** (the `min-height: 75vh` card floor and the payoff-by-round table), and most divergences are improvements worth back-porting.

---

## 1. Inherited and still matching

These template conventions survived the evolution and still behave the same way.

- **Four-app page flow.** `before -> intro -> main -> outro` in both (`settings.py` SESSION_CONFIGS). App-internal page order was reworked (real task vs. placeholder), but the top-level architecture is unchanged.
- **DEBUG-gated skip buttons, intro only.** The template gates skip controls on `settings.DEBUG` and only in the intro app (`_ai/template_snapshot/intro/__init__.py:75,121,130`; `is_debug` -> `instructing`/`quiz`). The pilot preserves exactly this: `from settings import DEBUG` passed as `dev_skip` to both pages (`exp_pilots/intro/__init__.py:129,170`), with correct answers exposed only under DEBUG (`:171-173`). `before`/`main`/`outro` carry no skip in either. The buttons were renamed (`is_debug`->`dev_skip`, `quiz_solutions_json`->`dev_skip_answers`) and restyled but are functionally identical, still DEBUG-only, never reaching participants.
- **Skip submits through real validation.** Both fill the *correct* answers and submit through the normal path, so a skipped quiz records zero failed attempts (bonus-eligible, like a correct human). The pilot documents this explicitly (`exp_pilots/intro/__init__.py:143-161`).
- **`.screen-card { min-height: 75vh }` content-card floor.** Present on the same selector in both: template `base.css:65`, pilot `base.css:117`. The pilot adds a comment (`base.css:93-96,115-116`) naming it "the oTree-template convention." Not lost.
- **Payoff-by-round results table.** The template's collapsible Round/Payoff table (`_ai/template_snapshot/outro/Results.html:34-69`, paid rows flagged `selected-row`) is reproduced and expanded in the pilot (see 3). Not lost.
- **`verify_quiz` escape hatch.** Config flag that lets a quiz be clicked through; kept in the pilot (`exp_pilots/intro/__init__.py:153`, config `pilot_test` sets it `False`).
- **Byte-identical shell pieces.** `_static/global/html/template.html`, `logo_section.html`, `welcome_header.html`, and `_static/global/css/demographics.css` are unchanged from the template.
- **oTree scaffolding constants.** `SESSION_FIELDS=[]`, `LANGUAGE_CODE='en'`, `USE_POINTS=False`, `INSTALLED_APPS=['otree']`, empty `DEMO_PAGE_INTRO_HTML` all carried over.

Note on PRELAUNCH machinery: the **template has none** (only a passive comment about not hardcoding DEBUG, `settings.py:46-49`). The pilot's prelaunch check is therefore a pilot invention, not an inheritance (see 2).

---

## 2. Diverged, and the divergence is an improvement (back-port candidates)

Concrete gains in the pilot that the template would benefit from.

### Settings / launch safety
- **Machine-checked prelaunch banner.** `exp_pilots/settings.py` prints a DEBUG/skip status line on every start (`:268-269`) and runs `_check_prelaunch()` (`:266-297`, called at import) that compares live config against `PRELAUNCH_REQUIRED` (`:43-45`) and prints a bordered "MUST BE" banner if anything is off. The template has nothing comparable. **Caveat before treating this as complete:** the machine check currently enforces only `rounds_per_block`. The other launch requirements the top comment lists (`cc_code`, `noconsent_code`, `OTREE_PRODUCTION`) are *not* in `PRELAUNCH_REQUIRED`; the codes only have placeholder defaults `'REPLACE_CC'`/`'REPLACE_NC'` (`:137-143`) with no assert. If the intent is a real guardrail, those belong in the checked dict too.
- **Full design parameterisation.** `DESIGN_DEFAULTS` (`settings.py:76-133`) holds every design quantity (DGP, x-design, role sizes, rounds, payments, timing) with per-field rationale, spread into every config and `SESSION_CONFIG_DEFAULTS`. The template has zero design parameters.
- **Explicit production gating.** `OTREE_PRODUCTION` env read -> `DEBUG = not OTREE_PRODUCTION` (`settings.py:220-229`), documented. Template relies implicitly on oTree deriving DEBUG.
- **Runs out of the box.** SQLite fallback with Postgres only when `DB_NAME` is set (`:243-255`); dev `admin`/`admin` and a dev `SECRET_KEY` (`:239-240,257`). Template hardcodes Postgres and leaves credentials empty.
- **Richer, documented participant fields** (`:195-208`, 10 fields covering treatment cell + flow state) vs. the template's 3.

### Page-flow code
- **Parameterised round/instruction counts.** The pilot derives quantities from config instead of hardcoding: `NUM_ROUNDS = num_blocks * rounds_per_block` with validating helpers (`main/__init__.py:22-35`), progress `progress_pct` (`:202`), instruction figures (island counts, growth, noise table) computed in `vars_for_template` (`intro/__init__.py:83-112`). The template uses flat constants and hardcoded Stag Hunt values.
- **Config guardrails.** `creating_session` raises a clear `ValueError` if a config implies more rounds than were imported and skips pages for shorter configs (`main/__init__.py:81-90`); `_num_blocks` raises on inconsistent role-size lists (`:22-26`). No template equivalent.
- **Clean, oTree-free module split.** `main/scoring.py` (Hossain-Okui binarised quadratic rule, `:1-45`) and `main/stimulus.py` (DGP + SVG) import no oTree, so `verify_randomisation.py` can reuse them. The template inlines a `random.randint` payoff and carries an entirely commented-out `group_matching.py`.
- **Idempotent payment.** Results computes the paid draw once and caches it (`outro/__init__.py:76`), so re-rendering never redraws the paid rounds.
- **No-consent short-circuit.** `before/__init__.py:71-93` routes decliners past every remaining app via `app_after_this_page`, guaranteeing non-consenters never reach the task. Cleaner than anything in the template.
- **Analysis-integrity discipline.** Records both displayed integers and raw draws, and computes every derived statistic from the displayed integers (`main/__init__.py:60-63`, `stimulus.py`). No template analogue; a good lesson even if not literally portable.

### Bot tests (entirely new; template has none)
Four `PlayerBot` suites give end-to-end coverage:
- `before/tests.py` (`:1-30`): consent branching (id 2 declines) + asserts treatment assignment fired at session creation.
- `intro/tests.py` (`:1-25`): submits a deliberately wrong quiz attempt via `SubmissionMustFail`, asserts `failed_attempts == 1`, then submits correct.
- `main/tests.py` (`:1-58`): stimulus invariants (`n_points`, `xy_data` lengths, `true_beta`), the displayed-integer contract (`y == int(round(y_raw))`), and the derived-stats-from-displayed-integers invariant (recomputes slope/LLR/posterior, asserts match `<1e-12`).
- `outro/tests.py` (`:1-41`): task-record completeness, paid-rounds draw (exactly `n_paid`, all distinct, in range), and earnings arithmetic with an upper bound.

The generic scaffolding (consent-routing bot, quiz wrong-then-right bot, payment/earnings bot) is directly back-portable; the `main` stimulus test is pilot-specific and would need a template analogue.

### CSS / UX
The pilot rebuilt `base.css` into a documented design-token system (233 -> 392 lines). Genuinely reusable improvements the template lacks:
- `:focus-visible` outlines never removed (`base.css:214-218`).
- `@media (prefers-reduced-motion: reduce)` kill-switch (`:389-391`).
- `@media (max-width:520px)` phone rules; touch-sized (30px) range-slider thumbs with `aria-valuetext`.
- `.otree-body.container` chrome reset that neutralizes Bootstrap width caps (`:79-90`).
- Fluid `clamp()` sizing throughout instead of fixed px.
- `.table-scroll { overflow-x:auto }` (`results.css:44`), matching the house "wide tables scroll in their own container" convention.
- Selectable-card form controls via `.form-check:has(input:checked)` (`base.css:238-283`).
- New elicitation UX (`allocation.css`, `js/elicit.js`): one shared, accessible, network-free bet widget used by both the real task and the instructions-page practice demo, so they cannot drift.

The DEBUG skip styling was deliberately flipped from quiet grey `.debug-tools`/`.skip-button` to a loud amber `.dev-bar` (`base.css:352-378`): a philosophy change (impossible-to-miss tooling), still DEBUG-only.

---

## 3. Diverged, where a template convention was lost or weakened

Verified against the two known examples plus what the read surfaced.

- **Payoff-by-round table: re-added and improved, minus the accordion.** The pilot's table (`outro/results.html:46-81`) reproduces the template's "list every round, flag the paid ones" pattern and expands it from 2 columns (Round, Payoff) to 4 (Round, Your allocation, Island type, Outcome), backed by `task_records` + cached `payment_detail` (`outro/__init__.py:71-115`), plus a payment-composition summary the template renders only as prose. The one template feature not carried over is the **collapsible toggle** (button + `aria-expanded` + JS in `Results.html:34-101`); the pilot table is always expanded. Minor, arguably fine for a 24-row table, but the keyboard-accessible collapse is a lost affordance if long tables recur.
- **`min-height: 75vh` card floor: intact, no action.** Confirmed present in both (`base.css:65` template, `:117` pilot). Listed here only to close the loop: it was re-added correctly and now matches the template.
- **Re-read-instructions loop dropped.** The template lets a participant request a re-read (`redoinstructions` field) and bounces them back to the instructions app (`intro/__init__.py:90-91,133-135`; quiz.html attempt-gated "Re-read Instruction" button). The pilot removed this entirely in favor of an always-open inline `<details class="quiz-recap">` accordion that includes the instructions text (`quiz.html:21-27`). Reasonable for single-page instructions, but the explicit attempt-gated re-read affordance is gone.
- **Two-strike escalation message flattened.** The template escalates wording after 2 failures ("Try re-reading the instructions", `intro/__init__.py:112-115`); the pilot uses one flat message regardless of attempt count (`:160-161`). Minor lost nuance.
- **Defensive payoff parsing dropped.** The template's `extract_round_payoffs` tolerates nested structures and missing-value sentinels (`outro/__init__.py:63-89`); the pilot assumes a clean `task_records` list of dicts (`payment_rule.py`). Fine because the pilot owns its data shape, but the robustness convention is gone.
- **Orphaned dead assets.** `demographics.css` (byte-identical but no longer imported by `style.css`) and `_static/global/js/quiz.js` (no longer referenced by the rewritten `quiz.html`) are dead in the pilot. Not a behavior regression; a cleanup item.

---

## 4. Verdict: how to resolve each remaining difference

| Difference | Direction |
|---|---|
| Machine-checked prelaunch banner | **Back-port to template** as a reusable pattern; while doing so, add `cc_code`/`noconsent_code`/`OTREE_PRODUCTION` to `PRELAUNCH_REQUIRED` so the pilot's own guard is complete, not just `rounds_per_block`. |
| Design parameterisation (`DESIGN_DEFAULTS`, derived round counts, config guards) | **Back-port to template.** Turns the template into a parameterised base rather than a hardcoded example. |
| Out-of-the-box settings (SQLite fallback, dev creds, explicit `OTREE_PRODUCTION` gating) | **Back-port to template.** Pure ergonomics win, no downside. |
| Bot test suite | **Back-port the generic bots** (consent, quiz, payment/earnings) to the template; leave the coconut-specific `main` stimulus test in the pilot, add a template-appropriate stimulus analogue. |
| CSS a11y/responsive (`:focus-visible`, `prefers-reduced-motion`, mobile breakpoint, `.otree-body` reset, `.table-scroll`, fluid `clamp()`) | **Back-port to template.** These are project-agnostic and strictly better. |
| Shared elicit widget / `allocation.css` | **Keep pilot-only.** Study-specific UX; not template material. |
| Results table accordion collapse | **Restore in pilot** only if long results tables are expected; otherwise leave expanded. Low priority. |
| Re-read-instructions loop + two-strike escalation | **Decide, then align.** If the design wants an explicit re-read affordance, restore a lightweight version in the pilot; if the inline accordion is the chosen replacement, back-port *that* to the template so the convention is consistent. |
| Defensive payoff parsing | **Leave as-is** in the pilot (owns its data); keep the tolerant parser as the template default. |
| Orphaned `demographics.css` / `quiz.js` | **Clean up in pilot:** delete or stop shipping the unreferenced files. |
| `.screen-card` 75vh floor | **No action.** Already matching. |
