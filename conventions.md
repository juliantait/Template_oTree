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
in `intro/__init__.py` and derived into `C.NUM_ROUNDS` in `main/__init__.py`.
