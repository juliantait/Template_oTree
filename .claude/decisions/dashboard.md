# Decisions: Experimenter dashboard

Read when you touch the experimenter dashboard (the monitor): its layout, pills, sorting, timeline, timer, or the admin Report tab.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## Monitor layout: `minmax(0,1fr)` tracks, a label-fitting ladder, one-line state cells — 2026-10-03

Styling pass on the experimenter monitor, approved by Julian once the timeline
became per-session (any number of steps, raw app names as labels).

- **Tracks are `minmax(0, 1fr)` in the header AND every row**, with a floor of
  44px per step on the grid. A bare `1fr` lets content set a track's minimum,
  so a long label or a "10 of 10" marker widened its own track and the header
  drifted up to 40px off the dots (already 6–12px on the stock six steps at
  ≤1152px). Do not "simplify" back to `1fr`; the floor exists because without
  any content minimum the auto table layout starved the timeline (23px tracks).
- **Labels are fitted, never allowed to move the grid:** `fitTimeline()` in the
  page JS tries none → tighter → smaller (.6rem) → two-line wrap (break after
  `_`) → stagger (alternate rows, two tracks wide) → stagger+wrap with ellipsis,
  and keeps the first rung where nothing overflows. The full label is always the
  cell's `title`. Chromium breaks at `<wbr>` even under `nowrap`, so the break
  points are hidden off the wrap rungs AND the fit test rejects a one-line rung
  that grew taller. **Rejected:** CSS-only fitting (container queries cannot know
  whether a label fits), and ellipsis as the first resort.
- **Narrow tracks (<60px) get a compact "2/10" marker**; full "2 of 10" otherwise.
- **State cells stay on one line:** the column shares now total 100% (they were
  104%, so the auto layout rescaled them and squeezed State beside a half-empty
  Earnings column). Where a cell would still wrap, the OUTCOME pill drops its
  words ("✓ finished" → "✓"), lossless because the row tint and marker say it
  too; condition pills never shorten. Rows have one minimum height (48px).
- **The stock screen at 1440px uses no rung** and is unchanged apart from the
  finished row's pills now sharing a line (and a ~15px shift from the 1% the
  label column gave up).

**Enforced by:** `scripts/tests/dashboard_timeline_render_check.py` (4–9 steps ×
1024/1152/1280/1440 px: alignment ±1px, equal tracks, cut labels only in the
≥7-steps-at-≤1152px corner and always with a tooltip, one-line two-pill cells,
one row height, no page scroll, stock 1440 on no rung; 70 of its checks fail
on the pre-pass CSS).

---

## The monitor's timeline is built per session from `app_sequence` — 2026-10-02

The experimenter monitor no longer has a fixed step list. Its steps are THIS
session's `app_sequence`, in order, then Done (`timeline_for_apps` in
`core/experimenter_dashboard.py`); the header cells, grid track count, connector inset
and the page's JS `STEPS` are all derived from that one per-session list, as they
used to be from `STEP_LABELS` at import. A fork that adds, renames or reorders an
app gets a correct monitor without editing the dashboard (Julian's request: the
old "update APP_STEPS by hand" rule was the thing forks forgot).

- **Step ids are app names** (`before`, `main`, `outro`), not the old phase words
  (`entry`, `task`, `questionnaire`). The /data row's `step` changed accordingly;
  the screen does not. Kept: `instructions`/`quiz` (intro's page split) and `done`.
- **Apps declare their own presentation, optionally, on `C`:** `MONITOR_LABEL`
  (else the raw app name — unprettified on purpose, a standing prompt to declare
  one), `MONITOR_ROUNDS` (`fraction`/`number`/`hidden`; default `fraction` for a
  multi-round app, `hidden` for a single-round one) and `MONITOR_ROUNDS_CONFIG`
  (a session-config key capping the total — `main` uses
  `num_experimental_rounds`, so the operator's "x of N" equals the participant's
  progress strip). **intro is `number` on purpose:** "1 of 2" would read as half
  done to everyone on their first pass, when round 2 is only the lab re-read.
- **The page-name split stays hardcoded** (`PAGE_SPLIT_STEPS`, one entry: intro
  → Instructions, Quiz). It is the one placement no app-level fact can express.
- **Stall threshold per app:** `DASHBOARD_STALL_SECONDS_<APP>`, else `_DEFAULT`.
  **`DASHBOARD_STALL_SECONDS_TASK` still governs `main`** (a legacy alias in
  `LEGACY_STALL_SETTINGS`) so existing settings files keep working — do not
  rename it to `_MAIN` in settings.py thinking it is dead; either name works and
  `_MAIN` wins. Not a pattern to extend.
- **intro's and outro's phase clocks apply only when their usual predecessor
  (`before`, `main`) is immediately before them in the session**
  (`PHASE_CLOCK_APPS`). Both clocks start at a stamp the previous app writes; an
  app inserted in between would be billed to the phase and turn every arriving
  row amber. Otherwise page time, the default for every app.
- **Unmapped stays loud.** A participant whose app is not in their session's own
  `app_sequence` is still the violet "not on the timeline" row, never placed
  somewhere plausible — rare now, which is exactly why it must stay visible.
- **A terminal tab-monitor DQ is placed by the page of the disqualifying focus
  loss** (server-recorded, `region == 'task'` only) as well as by the stage
  stamps, so a DQ in `main` is not drawn on an app inserted after the quiz.
- **Name-bound lookups remain** (earnings/Non-SEPA from `outro`, quiz cell and
  panel and intro timer from `intro`, treatments from `before`, `task_done` from
  `main`): `NAME_BOUND_APPS` lists them, and `note_timeline_problems` warns at
  launch (logged and printed, never raised) for any config missing one.
- **Rejected:** keeping APP_STEPS as an override layer over the derived timeline
  — two sources for "where is this app" is the inverted collapsed-distinction
  rule; and deriving labels by prettifying app names, which would hide the gap a
  declared label closes.
- **Known residual (not introduced here):** at 1152px the header labels already
  overflow their tracks on the stock six steps; a seventh step makes the same
  drift visible at 1280px. Row tracks stay equal.

**Enforced by:** `scripts/tests/dashboard_timeline_test.py` (inserted app,
labels, intro number, main capped fraction, per-app stall, unmapped, terminal
placement, launch warning — run against the old module it fails on every new
behaviour; its main x/N and unknown-app checks are regression guards),
`dashboard_test.py` §D6 (per-session derivation of all four), and the site
preview built through `page_template_for_steps`.

---

## The dashboard columns are click-to-sort — client-side, and the timeline is NOT one — 2026-08-25

Every data column header now sorts the table on click, toggling ascending /
descending with a ▲/▼ marker on the active column. The choices worth recording:

- **Five columns sort; the TIMELINE does not.** Participant (`label`), Quiz
  (`quiz`), Time (`time` — total, falling back to intro), Earnings (`earnings`)
  and State (`state`) each carry a `data-sort` key and the `sortable` class. The
  timeline column is deliberately left alone: it is a per-row complete/advance
  ACTION, not a value, and turning it into a sort key would overload the one
  column an operator clicks to DO something. *Enforced:* `dashboard_render_check.py` (`check_sort`)
  asserts the timeline th has no `data-sort`/`sortable`, that clicking it leaves
  the order untouched, and that it paints no arrow.
- **Sorting is CLIENT-SIDE, and re-applied after every refresh.** The rows
  already live in the page (the poll ships JSON, `renderRow` paints it), so
  `cmpRows` sorts them in the browser — it therefore works identically embedded
  in the oTree tab and standalone, with no round-trip. `repaint()` re-applies the
  chosen `sortKey`/`sortDir` on every 2s tick, so a sort SURVIVES the auto-refresh
  instead of snapping back to the server order. The default `sortKey` is `state`
  (see "The monitor defaults to the state sort"); should the operator ever clear
  it there is no active key and the server's natural-name order (see row-order
  entry) is left untouched.
- **The State sort's order is active → done → dq → waiting** (`statusRank`):
  active/live rows first (the people who need watching), then finished, then any
  terminal/disqualified state, then not-arrived. DQ is tested BEFORE finished
  because a terminal row can be finished-shaped. The rank uses the SAME three
  outcome flags the row tint uses, so the grouping the eye sees (amber/green/red)
  and the sort can never disagree.
- **A missing value sorts as -1 (smallest).** No quiz / no earnings / no clock →
  a not-yet-reached row sinks to the bottom in descending order, which is where
  "hasn't got there yet" belongs when ranking by most-of-X.
- **Natural order is duplicated in JS, and must agree with the server.**
  `naturalCompare` is the client twin of `natural_label_key` (digits as numbers,
  before text, case-folded) — the `a2 … a10` seat case is the one that exposes a
  plain-string regression, exactly as the server comment warns. One concept, two
  implementations that are tested to match.
- **A click on a header's `.th-info` icon is NOT a sort.** The Quiz header's ⓘ
  opens the mistakes panel and the State header's ⓘ is the threshold legend; the
  sort handler bails when the click landed on a `.th-info`, so those keep their
  own behaviour. (An operator sorts by clicking the column NAME.)

*Enforced:* `scripts/tests/dashboard_render_check.py` (`check_sort`) drives real Chromium over the
render check's 13-row diverse session, and for each sortable column asserts the
rendered order matches the intended key ascending then descending, the ▲/▼ sits
on exactly the active column, the State buckets come out `active→done→dq→waiting`,
the sort holds across an auto-refresh tick, and the whole thing works INSIDE a
100dvh iframe. the render check's geometry legs (equal step spacing, overview-above-table,
no horizontal scroll, no clipped cell at 1152px) and the site-preview check
still pass, so the added header markup did not disturb the timeline's spacing.

---

## The monitor DEFAULTS to the state sort — 2026-08-29

The client `sortKey` initialises to `state` (not `null`), so the dashboard loads
already grouped by `statusRank` ascending: the ACTIVE rows first (arrived, still
going — stalls and quiz warnings mixed in among them — sorted by name within the
group), then FINISHED, then the terminal/DQ RED rows (screen-out, declined,
comprehension DQ, tab-monitor DQ), then NOT-ARRIVED at the bottom, then error.
The State column shows its ▲ (ascending) indicator on the very first paint —
`repaint()` calls `updateSortIndicators()` unconditionally, and with a non-null
default key the indicator and `aria-sort` are set before any click.

Julian wants the red/terminal rows grouped and the not-arrived rows pushed to the
bottom the moment the page opens, rather than after a click — those are the rows
an operator scans for at a glance, and the old default buried them among the
active rows in name order. `statusRank` is UNCHANGED (finished/done stays rank 1,
sitting just under the active rows); only the initial `sortKey` moved.

Name order is still one click away on the Participant header, which restores the
server's natural-name order exactly.

*Rejected:* the old name-order default (`sortKey = null`, leave the server's
natural-name order). It read down the room alphabetically but scattered the
terminal and not-arrived rows through the list, so the states an operator most
needs to spot were the ones the load order did nothing to surface.

*Enforced:* `scripts/tests/dashboard_render_check.py` — `check_row_order` now
clicks the Participant header to isolate the natural-name sort (the default is no
longer name order), and `check_sort` asserts the state grouping; the built
website monitor preview (`_ai/site_previews/monitor.html`) is frozen in this
default order with the ▲ on the State column.

---

## The dashboard summary and table header are STICKY — a fixed-height column, not a scrolling page — 2026-08-25

The experimenter dashboard used to scroll as one document: past a screenful of
participants the summary block (`#overview`) and the table's column-header row
both scrolled out of sight, so an operator reading a row at the bottom of a full
lab could no longer see which column was which nor the session totals. Now the
summary and the header row stay pinned and ONLY the participant rows scroll under
them. The choices that read as arbitrary without the reasoning:

- **A fixed-height flex column, not viewport-relative sticky.** `body` is
  `height: 100dvh; display: flex; flex-direction: column; overflow: hidden`; the
  overview is `flex: 0 0 auto` at the top and the table lives in a new
  `.dash-scroll` (`flex: 1 1 auto; min-height: 0; overflow: auto`) — the one
  element on the page that scrolls. The header pins with `thead th { position:
  sticky; top: 0 }` **relative to `.dash-scroll`, not the window**. *Rejected:*
  `position: sticky; top: 0` on the overview plus `top: <overview height>` on the
  header against the page's own scroll. That needs a hard-coded offset equal to
  the overview's height, and the overview's height is variable (the four pills
  wrap at narrow widths), so the header would overlap or gap the moment the pills
  rewrapped. Pinning inside our own scroll container needs no offset at all.
- **Why this survives BOTH embeddings** (the brief). Standalone, the body's
  viewport is the window; in the oTree Report tab the page is inside a `100dvh`
  iframe (`outro/admin_report.html`), so the body's viewport is the iframe. In
  both the body has a definite height to split between the pinned overview and the
  scroll area, and the header sticks to `.dash-scroll` — not to whatever is
  scrolling around us — so it does not matter which frame owns the scroll.
- **`min-height: 0` on `.dash-scroll` is load-bearing, not tidiness.** A flex
  child will not shrink below its content's height without it, so the full table
  would push `body` past `100dvh` and the whole page would scroll again, defeating
  the sticky. Do not remove it.
- **The header underline is a `box-shadow`, not `border-bottom`.** The table is
  `border-collapse: collapse`, whose cell borders belong to the table's own
  collapsed border box and scroll away from a sticky `th` in several engines — so
  a `border-bottom` underline would vanish on scroll. A `box-shadow` is painted as
  part of the `th` and rides pinned with it. The card frame (border, radius,
  shadow) moved from `table.dash` onto `.dash-scroll` for the same reason: the
  table's own top border must not scroll out from under the pinned header.

*Enforced:* `scripts/tests/dashboard_render_check.py` (`check_sticky`) drives real Chromium at a
short viewport in BOTH contexts (standalone, and inside a `100dvh` iframe),
scrolls `.dash-scroll`, and asserts the summary top and header top do NOT move,
the header stays pinned to the container top, the first row DOES move up, and the
page/body never scrolls — each a presence check, never absence-only. The existing
the render check's geometry legs (overview-sits-above-table, equal step
spacing, no horizontal scroll, no clipped cell at 1152px) still pass, and
`check_site_previews.py` confirms the frozen `monitor.html` still fits its canvas
with no overflow.

---

## The dashboard timer's TOTAL pill, the stale-data banner's age, and the tab embed's height — 2026-08-23

Three operator-facing improvements to the experimenter dashboard, each with a
choice that reads as arbitrary unless the reasoning is written down.

### The TOTAL-time pill: where the clock starts and stops

Pill 2 of the per-participant timer (`_total_seconds`) is "time since they
started", intro included and still counting — the companion to the INTRO pill,
which freezes at the intro boundary. The choices that are not free:

- **Starts at the FIRST stage stamp (`min`), not at arrival.** Nothing writes an
  arrival timestamp into `stage_timestamps`, and the brief was to start from what
  is already recorded, not invent state. `min` is also the anchor the overview
  EXPERIMENT figure already uses, and it is always <= the intro start (the intro
  start is itself one of the stamps), so **total >= intro on every row** — pill 2
  can never read shorter than pill 1.
- **Stops at the FINISHED stamp for a finisher, not the last stamp.** So the
  frozen total equals that participant's contribution to the overview EXPERIMENT
  average to the second, and a later `prolific_return_clicked` (receipt-reading
  time) is not billed to the study.
- **Stops at the LAST stamp (`max`) for a terminal row.** A screen-out /
  comprehension DQ / tab-monitor DQ has no `finished` stamp and there is no
  dedicated ejection-moment stamp, so the last completed stage is the closest
  evidence of when they left. **Known, deliberate limitation:** a tab-monitor DQ
  can fire on a page whose stage was never stamped, so this can UNDER-count that
  final page. It never over-counts and never claims time we cannot see — the
  honest failure direction. **Rejected:** `pp._last_page_timestamp` for the
  terminal stop, which points at the ENDING page (after ejection) and would
  over-count. *Enforced:* `scripts/tests/dashboard_total_time_test.py` (each
  start/stop case, the invariant, and the receipt-click exclusion), proven red by
  a negative control that starts the clock at `max`.

### The stale-data banner counts the age up on the client

A failing refresh now names WHEN the last good data is from and HOW LONG AGO,
with the age climbing second by second, so a blip and a dead server look
different at a glance. The age is measured from the CLIENT clock at the last good
load (`lastGoodAtMs`) — the same base clock the live timer pills tick from — so
both are immune to server/browser skew, and a 1-second UI tick, separate from the
2-second data poll, keeps the age (and the live pills) moving while no data is
arriving. *Enforced:* `scripts/tests/dashboard_timer_banner_test.py` measures the
age and a live pill at two times and asserts they moved (never an absence-only
check), proven red by controls that drop the time/age and that drop `data-live`.

### The tab embed fills the viewport (100dvh), block, border-box

`outro/admin_report.html`'s iframe went from `78vh` to `100dvh`, `display: block`,
`box-sizing: border-box`. At 78vh the whole Report page fit one viewport, so
nothing scrolled: oTree's chrome (navbar, tab bar, the app_name/round_number
form) was stuck at the top and a strip sat below the embed. A full-viewport iframe
makes the page taller than the window, so the chrome scrolls away and the
dashboard owns the screen; `display: block` removes the inline-descender
"leftover row"; `border-box` keeps the 1px border inside the 100dvh so it fills
exactly rather than overshooting by 2px. **The dashboard's own timeline column
widened 46% -> 48%** at the same time, because the second time pill took width the
header's long step labels needed to stay equally spaced (it fails
`dashboard_render_check` at 1280px otherwise). *Enforced:*
`scripts/tests/dashboard_embed_height_test.py` at three viewport heights and the
existing `dashboard_render_check` header-spacing assertion; the height test is
proven red by a control reverting to `78vh`/inline.

---

## The monitor HIDES not-arrived rows by default, and says how many it is hiding — 2026-08-21

The dashboard shipped with a `hide not-arrived rows` checkbox, unticked, so an
operator opening a 24-seat lab session before anyone walked in got 24 grey rows
with nobody in any of them, and had to find a control to make the screen say
what the room said. The control is now inverted: **`show not-arrived rows`,
unticked on load**, so the default view is the room as it actually is and the
box REVEALS rather than hides.

**One arrival predicate, and it is the server's.** The filter reads
`row.entry_only` — the value `_participant_row` already computes from
`participant.visited`, the same source as the `arrived` field and the row-dim
class. It is deliberately NOT re-derived client-side as `!row.arrived`, which
would put a second implementation of "has this participant arrived" in the
browser, free to drift from the server's (CLAUDE.md's inverted rule). Reusing
it also inherits a guard `!arrived` does not have: a TERMINAL row is never
`entry_only`, so a screen-out or a declined consent can never be hidden by this
control even though nobody ever "arrived".

**Hiding rows must never make the room look smaller.** The header ratio is over
`data.rows.length`, the UNFILTERED total, so it still reads "5 of 6 arrived";
beside it, whenever anything is hidden, sits `1 not arrived, hidden`. That count
is a SUBTRACTION of what the filter removed, not a second count of the same
thing, so the number and the table cannot disagree. And the empty table — the
legitimate state before the first arrival — now says *why* it is empty and how
to see the rest, because "No rows to show." on a full session reads as a broken
dashboard.

**Where it is enforced.** `scripts/tests/dashboard_render_check.py` asserts BOTH
directions in a real browser on NAMED rows: unticked, the never-arrived
participant is absent AND an arrived one is present (an absence alone is equally
true of a table that failed to paint); ticked, the never-arrived one appears and
the arrived one is still there; plus the header's two claims in each state.
`scripts/tests/dashboard_test.py` D asserts the shipped default server-side —
the box exists AND carries no `checked`. Three other browser legs (the 13-row
overview, the row-order sort, the quiz-mistakes panel) stage participants who
never arrive, so they now tick the box through one shared helper.

**The website preview had to be told too.** `build_site_previews.build_monitor`
ticks the box before freezing the page, because that screen exists to show every
state the monitor can display and `check_site_previews.py` asserts the dimmed
never-arrived row is in it. Without that the build fails loudly on its row-count
wait rather than shipping a preview quietly missing a state — which is the
behaviour we want from it.

---

## The monitor's endings are GENERATED from the exit-code table, and an unknown code fails PREMATURE — 2026-08-19

The dashboard used to enumerate the four terminal states in a hard-coded map
(`TERMINAL_STATES`) plus a four-branch `if/elif` in `_participant_row`. A study
adding its own exit code got **nothing** from it: no pill, no timeline marker, no
count — and because the row had run past the last page index it was counted as
**FINISHED**, inflating the finished total and the earnings and time denominators
with it. Invisible, and flattering.

Now `settings.EXIT_CODES` (which codes exist) and `settings.EXIT_CODE_META`
(label / emoji / kind / when, all optional) drive everything, so a fork gets the
operator view by editing the dict it is already editing. **Two tables rather than
one** because `EXIT_CODES` is read as `EXIT_CODES['finished'] -> int` in four
apps, `common`, `core/identity.py` and the tests; giving its values a richer shape
would break every call site.

**An undeclared code counts as PREMATURE, and the direction is the decision.**
Defaulting to a normal finish would silently inflate FINISHED and both averages'
denominators — every number reading better than reality with nothing on screen
looking wrong. Premature errs pessimistically and *visibly*: a red, emoji-less
pill naming the code somebody forgot to declare. Rejected: defaulting to
finished; inventing a placeholder emoji (it would make an undeclared code look
styled — the gap is the signal); and guessing which ended-early group it belongs
to (it gets its own *unclassified* count instead).
**Enforced:** `experimenter_dashboard.ending_label/emoji/kind/when` and
`codes_of_kind`; `settings._prelaunch_problems` fails on a meta entry with no
matching code (a typo) but **never** on a code with no meta (that is the promise);
`scripts/tests/dashboard_test.py` section G2 drives an unknown `-97` end to end
and asserts it is not finished, keeps no emoji, lands in *unclassified* and does
not break the partition.

---

## The overview block: one header ratio, four condensed pills, colour on values only — 2026-08-19

The top of the monitor is now one section: a header row (study, session chip,
`x of y arrived`) and four pills — Treatments, Participants, Earnings, Time.
The averages strip under the table is **deleted**, not emptied.

**The header carries exactly one count, and it is a ratio.** `finished`,
`ended early`, `in progress` and `stalled` all moved into the Participants pill,
because every one of them was a **subset** of a count it sat beside
(arrived ⊇ in progress ⊇ stalled) while a comma-separated list at one weight is
the visual grammar of *siblings*. A ratio explains its own relationship; the pill
explains the split, and its three buckets sum to the arrival count.

**Stalled renders nested inside in-progress**, in parentheses, in amber, at 4px
against 12px between siblings — three redundant cues, none of them a glyph that
could come out as tofu. It is a condition on a subset, not a fourth outcome.

**THE COLOUR RULE: the container is neutral; colour belongs to values, and only
where it carries a meaning this screen already uses** (green = completed or
money, red = ended early, amber = stalled, neutral = a count with no valence).
A tinted frame spends the colour before the eye reaches the number, and put
*finished* participants inside a red object. Corollary: never a colour on a
frame, title, key or label. Rejected: the earlier one-hue-per-pill scheme.
**Enforced:** `scripts/tests/dashboard_render_check.py` measures four pills on one
row at equal height, every pill frame the same neutral, stalled nested and not a
sibling, and the header census carrying the ratio and nothing else;
`scripts/site_previews/check_site_previews.py` requires all four pills by name.

---

## Pill alignment is BASELINE with a fixed pixel line box — 2026-08-19

Mixing `align-items: center` on a pill with `align-items: baseline` inside its
value groups put the tiny keys **2.08px** below the pill names (measured). Type
of different sizes lines up on its **baseline**, not on its box centre — a box
centre is a property of the line box, not of the glyphs, so a centre-alignment
check is the wrong metric and *fails on correct output*. Baseline alone was not
enough either: line-box height scales with font size, so three type sizes gave
pills 32.5 / 34.5 / 38.5px tall. Hence `line-height` in **pixels** on every leaf
and an explicit pill height, so no single inner chip can resize its family.
**Enforced:** `dashboard_render_check` measures the true text baseline with a
zero-size inline-block probe and requires ≤0.5px across every leaf of all four
pills, plus equal pill heights.

---

## The two time averages have DIFFERENT denominators — 2026-08-19

INTRO time is over everyone whose intro time is **settled** (a `quiz_done` stamp,
out of the intro block); EXPERIMENT time is over whole-study **finishers**. This
**reverses** the single shared population settled on 2026-08-17, deliberately and
by the person who set it. Intro-over-finishers was a much smaller set arriving
much later — roughly a third of the people who actually have an intro time, and
nothing at all until somebody completed the entire study. The experiment
denominator is *forced*, not chosen: a first-stamp-to-finished duration cannot
exist for anybody else. "Settled" is not a new definition — `_intro_seconds`
already computes it, so there is no second stopwatch.
**Enforced:** `_time_summary` returns `intro_n` / `experiment_n` separately;
`dashboard_test.py` asserts the intro population contains the finished one and
that the two differ; `dashboard_render_check` asserts the rendered pill prints
two different denominators.

---

## The waiting-for pill ships INERT, and is tested anyway — 2026-08-19

The monitor renders a "waiting for <label>" pill in the State cell, shown only
while a participant is actually blocked on somebody. **This template has no wait
pages**, so nothing writes `participant.vars['waiting_for']` and the pill never
appears in a real run here. That is deliberate, not an oversight, and it is
recorded so nobody deletes it as dead code or reads the empty cells as a bug: a
fork adding group matching gets the operator view without building one.

Wiring that is never exercised is wiring nobody knows works — the
`ai_safety_monitor.js` case in CLAUDE.md was exactly a feature that looked
configured and silently refused to run. So the path is **tested against the shape
a real wait page would produce**: a planted `waiting_for` renders the pill with
the participant's LABEL, an unresolvable id renders `?` rather than vanishing, a
duplicated label is disambiguated with the code, and a finished participant shows
nothing even with a stale value — each paired with the absence check, per the
rule that an absence alone tests nothing. Names resolve through
`displayed_name`, the one implementation, and uniqueness through
`identity.normalise_label`, so the pill cannot name somebody differently from the
row above it.
**Enforced:** `dashboard_test.py` section G3; `_waiting_for`'s docstring.

---

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

---

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
scrolls. The monitor site-preview is regenerated from `core/experimenter_dashboard.py`
(`scripts/site_previews/`).

---

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
`URL_BASE` renamed consistently *inside* `core/experimenter_dashboard.py` while the
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
the `from core import experimenter_dashboard` trailer at the end of `outro/__init__.py` in a
`try/except` so a module-level error there (scenario 3), or a wholly missing
`URL_BASE` definition, would fail soft. **Rejected on Julian's rule:** a genuine
import-time error in the dashboard module is a code breakage the person launching
must see and fix, and softening it to a silent 404 is exactly the later-invisible
failure the rule forbids. The bare `from core import experimenter_dashboard` stays
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
`experimenter_dashboard.note_admin_tab_problems` applies the core/identity.py
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

---

## The dashboard summary strip: earnings is ONE pill carrying avg AND total; the total summed server-side over finished participants — 2026-08-17

Requested by Julian, from the live page. The payment picture lives on the one
dashboard tab, so nobody opens oTree's own Payments page to see what a running
session is paying out. The `dash-summary` strip beneath the table
(`core/experimenter_dashboard.py`) has TWO items: **avg intro time**, and a single
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

---

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

---

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

---

## The Non-SEPA pill: lab only, `sepa == 0` only, and no yellow state — 2026-08-13

Three deliberate narrowings, all Julian's: NULL `sepa` (the check never ran —
every Prolific row) is NO pill, never a flag; a non-Dutch but in-SEPA account
is NO pill (only non-SEPA is flagged — there is no yellow payment state); and
even a hand-edited `sepa=0` in a Prolific session shows nothing, because
payment there goes through the platform and the pill would send the operator
chasing a form that does not exist.
**Enforced:** `experimenter_dashboard._non_sepa_ids` (the one predicate);
`scripts/tests/dashboard_test.py` §D7 pins all three narrowings.

---

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
