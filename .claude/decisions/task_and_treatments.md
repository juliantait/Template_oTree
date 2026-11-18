# Decisions: Task and treatments

Read when you swap or edit the task in `main`, the task pages, or treatment assignment.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

Cross-reference: "the monitored-by-default entry above" in the `TaskPage` entry is
in [`screening_and_integrity.md`](screening_and_integrity.md).

---

## The placeholder task is now a single-slider payoff elicitation, and the slider is a reusable component — 2026-08-18

Replaced the placeholder payoff-matrix stub (`main.GameStart` drew
`round_payoff = random.randint(1, 100)` in `before_next_page`) with a real
worked elicitation: **one slider by which the participant picks their own
payoff**, which becomes `round_payoff` and is what they are paid. It is the
reference example a future study copies, so it demonstrates the elicitation
conventions rather than inventing a throwaway game.

**What ships.** A reusable slider control — `_static/global/css/slider.css`
(`.slider-elicit`) + `_static/global/js/slider_elicit.js` — lifted from
`exp_pilots`' bet slider but STRIPPED of its two-step gating and clamped/blocked
half: one clean slider that picks a value. It sits inside a new shared framed
container, **`.elicitation`** (base.css), the box EVERY elicitation drops into —
distinct from `.panel` (quiet grey, secondary information) because it frames an
ACTIVE input region. A `.popover-anchor` "?" hint sits beside it. Specimens for
both the box and the slider are in `_static/global/html/template.html`.
`main.Player.slider_payoff_points` (int, `blank`, `0..100`) is the picked value;
`GameStart.before_next_page` copies it into `round_payoff`, and the last task
page still calls `finish_task_block` (payoff_vector + `task_done`) unchanged.

**Two behaviours lifted deliberately, and why they are not accidents.**
* **No starting value / no pre-positioned thumb.** The range carries no `value`
  attribute; the thumb is hidden until moved, and the JS strips the field's name
  on an untouched submit so it posts EMPTY. A pre-positioned thumb biases the
  answer toward wherever it sits — an untouched control that shows a number is a
  belief nobody stated. This is the whole reason there is no default; do not add
  one back.
* **No-JS safe.** With scripts blocked the thumb stays visible and the range is
  an ordinary usable control; the field is `blank=True` / `field_maybe_none`, so
  an empty submit stores 0 for the round and never 500s.

**Rejected:** porting the full two-step bet (a stable-or-growing choice gating a
bet clamped to half the scale) — far more mechanism than a placeholder needs,
and it teaches the wrong default to the next author. Kept the page NAMES
(`GameStart` / `payoff`) rather than renaming, to hold the test blast radius
down (the names live in `main_contract`, `predeploy_check`, and ~8 suites).

**Enforced:** `scripts/tests/slider_payoff_test.py` proves the chosen value
reaches `participant.payoff` (a high slider is paid that, not just show-up),
`task_done` is stamped, and an empty no-JS submit is safe;
`scripts/tests/payoff_ledger_test.py` / `full_journey_test.py` walk the slider
via `main_contract`; `render_check.py` measures the task page at three
viewports; `focus_trace_test.py`'s positive control asserts the slider renders.
The convention is written up in `.claude/skills/writing-task/SKILL.md`
("Elicitations — the shipped slider is the reference").

---

## Treatment randomisation moved from session creation to arrival, balanced on arrival — 2026-08-18

Treatment was dealt to EVERY participant in `before.creating_session` with
`itertools.cycle` — balanced by construction, but it spent a cell on anyone who
then declined consent or was screened out by the device gate. It now assigns a
cell only when a participant reaches the first instructions page
(`intro.instructing.get`), the latest safe point (instructions may themselves be
treatment-specific). Once the deck is no longer dealt at once `cycle` cannot hold
balance, so each arrival COUNTS the cells already taken in this session, takes the
LEAST-FILLED, and breaks ties AT RANDOM (a deterministic tie-break makes the next
cell guessable from the running order). Balance holds at every intermediate
moment, not merely once a session is full.

Assignments are PERMANENT: we balance who ARRIVED, not who finished. An abandoned
cell is never released or re-dealt, and a page refresh returns the cell already
held (idempotent). **Rejected / deferred (Julian):** balancing COMPLETERS
(releasing an abandoned cell so it can be re-dealt) is a real statistical choice a
multi-cell study may want; it is deliberately not done here and can be revisited
in `before/treatment_assignment.py`.

Count-and-assign is RACE-SAFE per session: two simultaneous arrivals would
otherwise both read the same least-filled cell and skew the balance. It runs under
a database row lock on the session row (`SELECT ... FOR UPDATE`), held to the
request's commit, so a second arrival blocks until the first has committed its
cell. The mechanism is a PLACEHOLDER a study swaps its real treatments into, but
the balance-on-arrival algorithm is real, not a stub.
**Enforced:** `before/treatment_assignment.py`;
`scripts/tests/treatment_assignment_test.py` (balanced arrivals, seeded-imbalance
compensation, and a declined / screened-out participant taking no cell).

---

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
