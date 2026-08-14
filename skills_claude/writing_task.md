# Skill: writing the task (swapping the game)

Read this whole file before replacing the shipped placeholder game. The
deliverable is your study's game in `main/` — pages, models, templates — plus
an update at every site that still carries placeholder content, all of which
are listed below so nothing is left to grep-and-hope.

## Overriding principle

> **THE GAME BELONGS IN `main`. `intro` DESCRIBES it — and description comes
> AFTER the thing described exists.**

Do not be misled by the shipped template: there is visibly more Stag Hunt in
`intro` (a worked instructions example, payoff constants, a placeholder quiz)
than in `main`, whose only game-specific line is one random payoff draw. That
is an ARTEFACT OF THE PLACEHOLDER, not a pattern to copy: the template needed
something concrete for the instructions machinery to describe without wiring
up a complicated game in `main` that no real study would keep. A real study
builds the game in `main` first and then writes `intro` to match it. Writing
the description before the thing it describes is backwards.

## The order of work

1. **Decide the audience** — lab or Prolific — and set the recruitment
   settings that follow (`recruitment` profile, the module flags, completion
   codes). See `settings.py`'s three-axes header and
   `writing_welcome_consent.md` for the entry pages.
2. **Build the GAME in `main/`.** Pages subclass `TaskPage`; your last page
   calls `finish_task_block`. Details below.
3. **Fix `intro` to MATCH what you actually built**: the instructions
   (`writing_instructions.md`), the quiz items (`writing_quiz.md`), the
   worked example and its constants. One vocabulary across all of them.
4. **The `outro` work that is still required**: the payment rule
   (`outro/payment_rule.py`) and whatever your study needs at the end
   (the Results receipt renders what `compute_final_payoff` computes).

## ⚠️ THE SINGLE MOST IMPORTANT RULE ⚠️

> **SUBCLASS `TaskPage`; NEVER copy its attributes into a new page class, and
> NEVER rewrite the machinery you inherit.**

Most of `main/__init__.py` is not your problem — it is template machinery a
new game inherits by subclassing, and helpfully "simplifying" it is how a
study breaks silently. What you inherit:

- **The monitoring wiring** (`monitoring.MonitoredPage`, which `TaskPage`
  subclasses): every page after the agreement screen is tab-monitored BY
  DEFAULT; a page opts out only explicitly (`monitored = False`). A page that
  dodges the rule refuses to BOOT (`assert_monitored_page_sequence`).
- **The round loop**: `C.NUM_ROUNDS` (fixed at import — a config may run
  FEWER rounds via `num_experimental_rounds`, never more), `rounds_for`,
  `is_active_round`, and `task_page_visible` (round capping + the
  removed-from-study belt). `TaskPage.is_displayed` is already this.
- **The progress strip**: `progress_vars` / `task_template_vars` feed the
  header include `_static/global/html/task_progress_strip.html`. A page that
  overrides `vars_for_template` SPREADS `task_template_vars(self)` in rather
  than retyping keys (see the shipped `GameStart`).
- **The payoff plumbing**: per-round results go in `Player.round_payoff` —
  NEVER `player.payoff`, which RAISES here (`AUTO_TABULATE_PAYOFFS=False`).
  oTree auto-sums `player.payoff` across rounds, but only `num_rewarded`
  rounds are paid, so that sum is a figure nobody is paid; kept apart, the
  earned figure in oTree's admin matches the `earned` computed at the end
  (one ledger, see the field's comment). `finish_task_block` collects the
  vector and stamps `task_done`; `outro.compute_final_payoff` pays from it
  using `outro/payment_rule.py` and `MISSING_PAYOFF_SENTINELS`.
- **The stage stamps** (`common.stamp_stage`) — the dashboard and export read
  them; `finish_task_block` writes the task's own.
- **The spare columns** (`spare_str_1/2`) — never rename in place; the
  repurpose convention is in `CODEBOOK.md`.
- **The hidden-field rules**: JS-filled fields (the `client_ms` pattern in
  `main/game.html`) are `blank=True`, rendered as EXPLICIT hidden inputs, read
  with `field_maybe_none`, and must tolerate arriving empty (no-JS submit).

**The two duties every replacement keeps** (each fails SILENTLY if dropped —
wrong payments, no error anywhere):

1. every task page **subclasses `TaskPage`**;
2. the **last** task page's `before_next_page` **calls
   `finish_task_block(player)`** — one line; its docstring explains what
   breaks without it.

## The manifest: what to update once the game exists

Every site that carries placeholder content or names the placeholder pages.
Work through it top to bottom; the intro/outro entries are what step 3 and
step 4 update to match the game you built in step 2.

**`main/` — the game itself (step 2):**

- `main/__init__.py` — replace `GameStart` and `payoff` (the stub classes
  under `# INSERT YOUR GAME PAGES HERE`) and the one game-specific line,
  `player.round_payoff = random.randint(1, 100)`. Add your fields to
  `Player`. Keep everything listed under "what you inherit".
- `main/game.html`, `main/payoff.html` — stub templates ("Here's your game").
  Compose shared components (`conventions.md`, the styling rule in
  `CLAUDE.md`); keep the progress-strip include and the passive-capture
  hidden-field pattern.
- Group matching: the template ships NONE. Reference shape (not a block to
  uncomment): `_ai/group_matching_reference.py`; the open design questions
  are in `TODO.md` under "Group matching".

**`tests/main_contract.py` — in the SAME change as `main/`:**
the ONE module holding the task-page NAMES (`TASK_PAGES`) and per-page form
PAYLOADS (`task_page_submits`) for the whole suite. Update it when you rename
pages or change their forms — a missed test site then becomes an ImportError
or a loud red, not a test quietly walking pages that no longer exist.
(`scripts/predeploy_check.py`'s `RESUME_PREFERENCE` also names the pages;
update it with the contract — it tolerates unknown names by design.)

**`intro/` — description, AFTER the game exists (step 3):**

- `intro/instructions_text.html` — the worked Stag Hunt instructions, whole
  cloth. Method: `writing_instructions.md`.
- `intro/__init__.py` — `C.STAG_PAYOFF` / `C.HARE_PAYOFF` / `C.STAG_ALONE`
  and the keys `instructions_context` passes for them (`stag_payoff` …):
  replace with your study's own numbers/keys. The builder itself
  (one dict, two pages) stays.
- `intro/quiz_items.py` — the placeholder quiz ("Did you read and understand
  …") exists to exercise the machinery, not to be kept. Method:
  `writing_quiz.md`.
- Regenerate previews: `intro/generate_instructions_preview.py --config
  .preview_state.json`.

**`settings.py`:**

- `num_experimental_rounds` (this fixes `C.NUM_ROUNDS` at import),
  `num_rewarded`, `showup`, `quiz_bonus` — your study's real quantities.
- `DASHBOARD_STALL_SECONDS_TASK` — per single round; RAISE it if your task
  page runs longer than the placeholder's seconds (its comment reasons from
  the Stag Hunt).

**`before/treatment_assignment.py`** — if your design has treatments:
assignment happens at session creation; `intro`'s `{% if treatment %}`
conditionals and `instructions_context['treatment']` read the result.

**`outro/` (step 4):**

- `outro/payment_rule.py` — `select_random_payouts` is the shipped rule
  (pay `num_rewarded` random rounds). Change the rule here; the participant-
  facing description of it lives in the instructions (factual wording only —
  see `writing_instructions.md`'s Payment section).
- `outro/Results.html` renders the receipt from `compute_final_payoff`'s
  figures; if your payment structure adds lines, both move together.

**Tests with game knowledge beyond the contract:**

- `tests/example_quiz_content_test.py` — a MODEL, written against the
  placeholder quiz: copy it, keep the shape, rewrite the expectations
  (its own header says how).
- `tests/render_check.py` — after any task-template change, re-run; the card
  floor is DERIVED from the task screen (leg Q says re-derive if it fails)
  and layout moves need `--update-baseline` (see `writing_tests.md`).
- The suites that walk the flow by page name (`full_journey_test`,
  `frozen_config_test`, `xss_escaping_test`, `dashboard_test`,
  `payoff_ledger_test`, `bank_details_test`, `dashboard_render_check`,
  `render_check`) read the contract module — they follow your update to
  `main_contract.py`; run them rather than editing them.
  (`http_flow_test` and `gated_flow_test` walk generically and need nothing.)

## Checklist before you finish

- [ ] Audience decided first; game built in `main` second; `intro` rewritten
      to match it third; `outro` payment rule last.
- [ ] Every task page subclasses `TaskPage`; nothing copied out of it.
- [ ] The last task page's `before_next_page` calls `finish_task_block`.
- [ ] Per-round results in `round_payoff` (or your own field feeding the
      vector) — nothing writes `player.payoff`.
- [ ] `tests/main_contract.py` updated in the same change as any page rename
      or form change; `RESUME_PREFERENCE` updated with it.
- [ ] Intro constants, instructions and quiz describe the game you actually
      built, in one vocabulary; previews regenerated.
- [ ] `DASHBOARD_STALL_SECONDS_TASK` re-checked against your round length.
- [ ] JS-filled hidden fields: explicit inputs, `blank=True`,
      `field_maybe_none`, in the no-JS empty-post list (`writing_tests.md`).
- [ ] The suite run end to end (`full_journey_test` at the real round count),
      plus a render check with the baseline updated intentionally.
