# exp_pilots — UI/UX batch summary

Combined record of a single working session on the calibration pilot
(`exp_pilots/`). Every task below was verified with `otree test pilot_test`;
nothing was committed or deployed. Final test result at the bottom.

---

## 1. Instructions wording — charts, not rounds
**File:** `intro/instructions_text.html`

- Totals line rewritten to:
  *"In total, you will see **{{ num_rounds }} charts**, in {{ num_blocks }}
  parts of {{ rounds_per_block }} charts."*
- Deleted the sentence *"The number of years with surviving records changes
  between the parts."* — participants must not be pre-told what differs across
  the parts.
- Swept every participant-facing file for other pre-announcements of
  cross-part differences: that sentence was the only one.
  `main/block_start.html` (the wanted in-the-moment transition message) left
  exactly as is.

## 2. Instruction-page layout restyle
**File:** `_static/global/css/instructions.css`

- Centered the instruction column in the wide shared card:
  `.instructions { max-width: 62ch; margin-inline: auto }` — keeps the current
  reading width, just centered.
- Body copy justified: `.instruction-block > p, > ul, > ol { text-align:
  justify }` (direct children only, so the embedded practice-bet widget's own
  text is untouched).
- Step title (`h2`) sits inside the centered column, left-aligned flush with
  the text block's left edge (NOT centered on the page).
- Scoped to `.instructions` / `.instruction-block`, used only by
  `intro/templates/instructing.html`, so task/quiz/welcome/results screens are
  unaffected.

## 3. Stable/Growing label sizing in the bet widget
**File:** `_static/global/css/allocation.css`

- `.alloc-name` (the "Growing"/"Stable" word): `.78em` → `1.02em`.
- `.alloc-num` (live points number): `clamp(20px,1.8vw,26px)` →
  `clamp(27px,2.5vw,35px)`.
- `.alloc-unit` ("points"): left small, as requested.
- `white-space: nowrap` + vertical stacking preserved, so the layout holds at
  the 0/100 and 100/0 slider extremes and on narrow screens. Shared with the
  real task screen (intended for consistency).

## 4. Quiz-page restyle
**Files:** `intro/templates/quiz.html`, `_static/global/css/quiz.css`

- Removed the grey eyebrow "Comprehension check"; the page title is now simply
  **"Quiz"** (intro line *"Answer all of the questions below before starting."*
  kept).
- Added a `quiz-card` class and centered the header, content, dev-bar and Next
  button to the same `62ch` measure as the instruction pages, so the quiz no
  longer sprawls across the wide card and shares the app's design language.
- Quiz mechanics, question markup, numbering and the instructions-recap left
  untouched. Scoped via `.quiz-card`, so no other page is affected.

## 5. 50/50 bet default
**Files:** `main/widget_allocation.html`, `main/__init__.py`, `intro/__init__.py`

- Renamed the widget's starting-split vars `prior_pos_pct`/`prior_stable_pct`
  → `start_pos_pct`/`start_stable_pct` and set them to **50/50** in both
  providers (the real task screen and the instructions practice demo).
- The handle now opens centered with both sides equal, decoupled from the
  20/80 prior.
- **Behavioural note:** because the range input's default value is the start
  split, **an untouched submission now records a 50/50 allocation** (previously
  it recorded the 20/80 prior). Documented in the widget's template comment.

## 6. Min-height floor restored on all pages
**File:** `_static/global/css/base.css`

- `.screen-card` now carries `min-height: 75vh` (the oTree-template
  convention), so no page collapses to a stubby content height.
- Long pages (e.g. results) grow past the floor and scroll normally.
- Updated the neighbouring comments, which had previously documented the
  card as deliberately *not* forced to 75vh.

## 7. Results page rework
**Files:** `outro/results.html`, `outro/__init__.py`,
`_static/global/css/results.css`

- **"Your payment"** section: the earnings headline + composition breakdown
  (base payment + quiz bonus if any + bonus from decisions + total) wrapped in
  `.payment-summary` and capped at **340px** — a narrow receipt, no longer
  full width.
- **"All results"** subsection (`h3`) with the description *"The computer
  picked 2 of your rounds at random to count for payment."*, followed by a
  table of **all 24 rounds** shown directly (not collapsed): one row per round
  with round number, your allocation (`N Growing · M Stable`), island actual
  type (Stable/Growing) and outcome. The **2 paid rounds are highlighted**
  (accent-soft row tint, left accent bar, and a blue "paid" pill); non-paid
  rounds show a dash.
- Backend: `outro/__init__.py` now builds an `all_rounds` list from
  `participant.task_records` overlaid with the persisted paid-round detail
  (`won`/`payoff`). The one-time paid-round draw and the payment totals are
  unchanged.
- The "Thank you / all done" ending and the "Back to Prolific" button kept
  as-is.

## 8. Fifth quiz item — independence
**File:** `intro/quiz_items.py`

- Restored `quiz_independence`: *"What does the island you have just judged
  tell you about the next one?"* → answer **"Nothing about the next island"**
  (distractors: same type / different type). Coconut-framed, bare parallel
  options, same cannot-proceed mechanic.
- Fields, form fields and dev-skip answers generate dynamically from
  `QUIZ_ITEMS`, so no other code needed changing.
- This is legitimate comprehension (the OPPOSITE of the banned
  "more records = easier" priming hint), and the independence fact is already
  stated in the instructions. Updated the project memory note that had recorded
  the quiz as having four items.

## 9. Duration estimate → around 10 minutes
**File:** `before/welcome_consent.html`

- *"This study takes roughly 15–20 minutes"* → *"This study takes **around 10
  minutes**"*.

## 10. Reread auto-fill flash — findings + fix
**Files:** `_static/global/js/global.js`, `_static/global/css/base.css`,
`intro/templates/quiz.html`, `_static/global/js/quiz.js`

**Findings (investigation first):**
- The participant-facing **"Re-read the instructions"** control is an inline
  `<details>` expander in `quiz.html` — it neither fills radios nor navigates,
  so it produces **no flash**.
- `quiz.js`'s `redoInstructions` (the oTree-template reread-route-back that
  fills radios) is **dead code — never loaded** by any pilot template.
- The one reproducible flash is the **DEBUG-only skip-quiz button**: it checked
  the radios synchronously then `form.submit()`, and because the page stays
  visible during the navigation round-trip, the just-checked radios are what
  flashed. (Participants never see it — it is production-gated — but it is the
  real "same trick" instance.)

**Fix (freeze-the-frame, centralized):**
- Added `submitFormBehindVeil(form, fill)` to `global.js`: it drops an opaque
  full-page `.submit-veil` in the **same synchronous task** as the fill +
  submit, so no intermediate frame renders and the veil is all that shows
  during navigation.
- Added the `.submit-veil` style to `base.css`.
- Rewired the skip-quiz button through the helper (and disabled it on click to
  prevent double-submit).
- Left the dead `quiz.js` logic intact but added a comment pointing any future
  wiring of the route-back reread at the same helper, so "the same trick"
  cannot reintroduce the flash.

## 11. Prelaunch guard hardened
**File:** `settings.py`

- `_check_prelaunch()` previously machine-checked only `rounds_per_block`.
  Extended it — same MUST-BE banner style, same default-vs-config-override
  reporting — to also flag:
  - **placeholder Prolific codes**: any `cc_code`/`noconsent_code` still equal
    to a `REPLACE_*` sentinel (new `PROLIFIC_CODE_PLACEHOLDERS` constant), and
  - **DEBUG still on**: `DEBUG (set OTREE_PRODUCTION=1): currently True, MUST BE
    False`.
- Updated the "BEFORE REAL LAUNCH" doc block to describe all three checks. The
  CLEAN message now requires all of them fixed before it prints.
- Verified banner output (test container: testing config, DEBUG on, placeholder
  codes):

  ```
  ##    rounds_per_block: currently 3, MUST BE 8 for the real study
  ##    cc_code: currently 'REPLACE_CC', MUST BE 'a real Prolific completion code (not a REPLACE_* placeholder)' for the real study
  ##    noconsent_code: currently 'REPLACE_NC', MUST BE 'a real Prolific completion code (not a REPLACE_* placeholder)' for the real study
  ##    DEBUG (set OTREE_PRODUCTION=1): currently True, MUST BE False for the real study
  ```

---

## Final test result

`otree test pilot_test` → **Bots completed session** (full flow: consent →
instructions → 5-item quiz → 24 rounds → results), no errors or tracebacks.

## Out of scope / worth flagging
- `LaTeX/pilot_design.tex` quiz list still shows four items — add
  `quiz_independence` there if the design doc should match the running app.
- The generated instruction previews (`exp_pilots/instructions_preview.html`,
  `preview_flow.html`) are rebuilt from the template's preview script; they were
  not hand-edited this session.
