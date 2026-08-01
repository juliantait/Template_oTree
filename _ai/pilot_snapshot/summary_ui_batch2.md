# exp_pilots — UI/UX batch 2 summary

Second working session on the calibration pilot (`exp_pilots/`), following
`_ai/summary_ui_batch.md`. Every task below was verified with
`otree test pilot_test`; nothing was committed or deployed. Final test result at
the bottom.

---

## 0. CORRECTION — revert the 50/50 slider start (was a misunderstanding)
**Files:** `settings.py`, `main/stimulus.py`, `main/__init__.py`,
`intro/__init__.py`, `main/widget_allocation.html`

Batch 1 moved the allocation slider's opening value to a flat 50/50. That was
wrong: Julian's "50/50" referred to the **page layout** (see task 2), not the
slider value. Reverted, and made the start value a session-config parameter.

- New `DESIGN_DEFAULTS['slider_start']` in `settings.py` — POINTS ON GROWING
  (0–100); Stable starts at `100 − this`. **Default `None` opens the control AT
  THE PRIOR** — `round(prior_growing × 100)`, i.e. **20 Growing / 80 Stable**
  with the default 800/200 prior. Set an explicit integer to override per config.
- Single source of truth `stimulus.slider_start_pcts(cfg)` returns
  `(pos_pct, stable_pct)`; both the real task screen and the instructions
  practice demo call it, so they can never disagree. `None → prior`; the value is
  clamped to `[0, 100]`.
- `main/__init__.py` and `intro/__init__.py` now compute the split from the
  helper instead of the hard-coded `50/50`.
- Widget template comment updated: an untouched submission records **this
  starting split** (the prior by default), no longer 50/50.
- Verified: `slider_start_pcts({'prior':[0.8,0.2]}) → (20, 80)`; explicit `50 →
  (50,50)`; `0 → (0,100)`; `130 → (100,0)` (clamped).

## 1. Task screen — a true half-and-half split, chart fills its half
**File:** `_static/global/css/allocation.css`

- `.task-layout` grid `minmax(0,1fr) minmax(0,2fr)` (chart ⅓ / bet ⅔) →
  **`1fr 1fr`**: chart LEFT 50%, bet card RIGHT 50%.
- The chart was floating at a fixed cap inside its column. Added
  `.task-card .stimulus-plot { max-width: none; margin: 0 }` to **lift the shared
  720px cap and centring gutter**, so the SVG now fills its whole half (still
  scales, never stretches — its own viewBox governs aspect ratio).
- Collapses to single-column (chart on top) under 760px, unchanged.

## 2. Lock note — reserve its height so the bet card never jumps
**Files:** `_static/global/css/allocation.css`, `main/allocation_screen.html`

The "Look at the chart, unlocking in Ns" pill used the `hidden` attribute, so
when it vanished at unlock the bet card below shifted up.

- `.view-lock-note` is now hidden with **`visibility` (not `display`)**: default
  `visibility: hidden`, shown via a `.is-visible` class. Its box height is
  reserved for the whole locked+unlocked lifetime, so nothing moves when it
  clears.
- JS (`allocation_screen.html`): on lock start it enters layout once
  (`note.hidden = false`) and adds `.is-visible`; at unlock it only **removes
  `.is-visible`** (keeps the reserved box) instead of re-setting `hidden`.
- When there is no lock at all (`min_view_seconds = 0`) the pill stays `hidden`
  (out of flow) — no dead gap, and no jump is possible since it never shows.

## 3. Buttons — centered and pushed to the foot of the card
**File:** `_static/global/css/base.css`

- `.button-row` `justify-content: flex-end` → **`center`** (the primary forward
  button — Next / Start / Back to Prolific — is now horizontally centered).
- `.screen-card > .button-row { margin-top: auto }` pushes the card's own action
  row to the **bottom** of the card, so the flex column fills the default card
  height with content up top and the action near the foot. Scoped to DIRECT
  children, so the task screen's nested "Next island" (inside `.task-elicit`)
  keeps its tight rhythm.

## 4. Card centering — vertical + horizontal, roomier margins, scroll on overflow
**File:** `_static/global/css/base.css`

- `.experimental-screen` now `align-items: center` + `min-height: 100vh`: a card
  that does not need to scroll is centered **both ways** in the viewport.
- Padding widened to `clamp(28px,4.5vw,64px)` top/bottom (was `clamp(6px…12px)`
  top) for a **slightly wider top margin** — the top and sides no longer look
  cramped.
- Uses `min-height` (not `height`): a card taller than the viewport simply grows
  the page and scrolls downward, fully reachable, never clipped.

## 5. Welcome screen — the instruction pages' centered + justified treatment
**Files:** `before/welcome_consent.html`, `_static/global/css/base.css`

The welcome screen had neither centering nor justification.

- Added `welcome-card` class. The header (eyebrow + "Welcome") and the running
  paragraphs/panel now **narrow to the 62ch reading measure and center** in the
  wide card; body text is **justified**; the heading sits flush-left with the
  text.
- CENTERING CAVEAT honored: the consent form, its option cards and the Next
  button are **not** clamped — they keep full width (the button-row is
  centered/bottom-anchored by the shared rules above).

## 6. Quiz page title on the pre-quiz instruction page
**File:** `intro/prequiz_text.html`

- The last instruction page ("You will next see a short quiz…") now carries an
  `<h2>Quiz</h2>` title, styled by `.instruction-block > h2` exactly like the
  other pages' titles (Instructions / The setting / Your task / Your bet). This
  block only appears in the instruction pager (not in the quiz-page recap, which
  includes `instructions_text.html` only), so the title shows exactly once.

## 7. Centering caveat on the instruction pages — text narrows, components don't
**File:** `_static/global/css/instructions.css`

The old `.instructions { max-width: 62ch }` shrank **everything** — the practice
bet widget and the Back/Next pager included — to the reading measure.

- `.instructions` is now a **comfortable centered content band**
  (`max-width: 720px`, wide enough for the widget to reach its natural 640px size
  and for the pager to breathe), NOT the reading measure.
- Only the **running text** narrows further: `.instruction-block > h2, > h3,
  > p, > ul, > ol, > .panel` get `max-width: 62ch; margin-inline: auto` (p/ul/ol
  also justified). Title left-aligned flush with the body's left edge.
- The practice widget (`.elicit`, its own 640px centered cap), the worked-example
  figures (`.instruction-figure`) and the Back/Next controls are **not** in the
  reading-measure selector, so they keep their full band width.
- Reconciled the later margin shorthands (`> h2`, `> h3`, `> ul/ol`, `> .panel`)
  from `margin: 0 0 …` to `margin: 0 auto …` so they preserve the centered
  measure instead of resetting the inline margins to zero.

---

## Final test result

`otree test pilot_test` → **Bots completed session** (full flow: consent →
instructions → 5-item quiz → 24 rounds → results), no errors or tracebacks. The
pre-launch banner still correctly flags the four testing values
(`rounds_per_block`, both placeholder Prolific codes, DEBUG on).

## Notes / out of scope
- `slider_start` was added to `DESIGN_DEFAULTS`, so it is **not** a pre-launch
  checklist item — `None` (the prior) is a valid production default. It appears
  in every config via the `**DESIGN_DEFAULTS` spread; override per config if a
  different opening split is ever wanted.
- The generated instruction previews (`instructions_preview.html`,
  `preview_flow.html`) are rebuilt from the template's preview script; not
  hand-edited this session.
- CSS-only visual changes (tasks 1–5, 7) are not exercised by bot tests, which
  validate flow/server rendering; they were reasoned through against the shared
  design system in `base.css`.
