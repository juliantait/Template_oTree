# Decisions

The procedural and design decisions behind this template, in one place. Each
entry: the decision, the date it was settled, why (the concrete failure or
argument that drove it), what was rejected where an alternative was genuinely
considered, and — the field that matters most — **where it is enforced**: the
test, guard or CSS rule that holds it in place, or a plain admission that
nothing does and it relies on people remembering. Newest first. Entries are
deliberately short; code comments and the linked working documents hold the full
working.

---

## The CREED lab block is EXTENDED to the launcher block's full behaviour — DATABASES, ADMIN_PASSWORD, AUTH_LEVEL and DEBUG, each env-gated — 2026-09-10

The CREED Lab Launcher now appends a larger self-documenting block to a project's
`settings.py`: one that re-asserts from the environment *everything* a lab run
needs, so it overrides anything hardcoded above and stays inert without the
launcher's variables. This template carried only the SMALLER version (ROOMS +
`participant_label_file` + `ADMIN_USERNAME`, the 2026-09-01 entry below). It is
brought up to the same behaviour so a study forked from here is protected the
same way the launcher would protect a hand-written project — CREED-lab-ready with
nothing to paste.

- **Four overrides added, each guarded by the ONE variable it needs.** `DATABASES`
  rebuilt as Postgres from the `DB_*` variables, gated on `DB_NAME`, so it wins
  over a hardcoded `DATABASES`; `ADMIN_PASSWORD` from `OTREE_ADMIN_PASSWORD`,
  gated on that var; `AUTH_LEVEL` from `OTREE_AUTH_LEVEL`, gated on that var; and
  `DEBUG` re-derived from `OTREE_PRODUCTION`, gated on that var, so a fork that
  hardcoded `DEBUG = True` cannot ship debug pages (skip buttons, quiz solutions)
  into a lab session. With NO lab environment set, every guard is false and the
  file resolves byte-for-byte as before.
- **In THIS template the overrides are REDUNDANT — and that redundancy is exactly
  why the block stays inert.** The template already env-derives `DATABASES`,
  `ADMIN_PASSWORD` and `DEBUG` higher up (from the same variables, with the same
  defaults), so each override reproduces the value the base code already produced.
  That is precisely what keeps `creed_lab_block_test.py`'s differential green: the
  block-present and block-absent runs resolve identically. The fork PROTECTION is
  the point — a fork is free to hardcode any of these to a literal, and then the
  launcher's box for it would silently do nothing without the override sitting
  after the project's own assignment. Do not "tidy" them as duplication; this is
  the same "helpfulness" failure the `ADMIN_USERNAME` duplication defends against
  (see the 2026-09-01 entry, whose argument now applies to each of these keys).
- **`AUTH_LEVEL` is genuinely new to `settings.py`.** The template never set it —
  oTree reads `OTREE_AUTH_LEVEL` from the environment itself
  (`otree/settings.py`), which is why `scripts/prelaunch_check.py` reads the env
  rather than the setting. Assigning it here to the same env value is consistent,
  not a change, and it is deliberately absent from the differential's `COMPARED`
  set, so it neither helps nor breaks that test — it is the one override with no
  base value to match, and it simply mirrors what oTree already derives.
- **The marker line is kept VERBATIM; the banner is added as comments under it.**
  The task asked for an unmissable opening banner; the `# === CREED lab support
  (paste at the END of settings.py) ===` line is how the launcher DETECTS opt-in
  (a text match) and is pinned character-for-character by
  `creed_lab_block_test.py` §1, so it must not be reflowed into a new banner. The
  banner wording ("appended by the CREED lab launcher … TO REMOVE delete
  everything from the marker line above to the END of the file … safe to leave in
  permanently") is carried in the comment lines immediately below the marker,
  which are cut with the block and have no behavioural effect.
- **Rejected: rebuilding `DATABASES` from `DATABASE_URL`** (which the bat also
  exports). Parsing the URL would produce a `DATABASES` dict of a different shape
  than the template's own `DB_*` Postgres branch, so the block-present and
  block-absent runs would DIFFER and the differential would go red — a false
  alarm hiding a real question. The task and the base code both use `DB_*`, so the
  override matches the base exactly. **Also rejected: renaming the marker into the
  new banner** (breaks launcher detection and §1) and **dropping the guards to
  assign unconditionally** (a fork with no lab environment would then have its
  `DATABASES`/`DEBUG` silently reset at import).

**Enforced:** `scripts/tests/creed_lab_block_test.py` — `DATABASES`,
`ADMIN_PASSWORD` and `DEBUG` are already in its `COMPARED` set, so the differential
now covers the three new env-derived overrides for free, under BOTH the bare
environment (§3) and the exact `set_up_otree.bat` environment (§4, which sets
`DB_NAME`, `OTREE_ADMIN_PASSWORD`, `OTREE_PRODUCTION` and `OTREE_AUTH_LEVEL`), and
§4 additionally asserts the Postgres engine, the database name, `ADMIN_PASSWORD`
and `DEBUG=False` absolutely. `AUTH_LEVEL` is not compared (no base value to match).
`scripts/prelaunch_check.py`, `scripts/tests/frozen_config_test.py` and
`scripts/tests/room_gate_test.py` stay green. **NOT enforced, honestly:** as with
the 2026-09-01 entry, nothing here exercises the real launcher — the contract
tested is the block's behaviour under the variables the launcher is documented to
export, not that the launcher exports them, and the block body is not pinned
byte-for-byte.

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
  ~37 MB, GIFs unaltered) and the id→answer map lives in `dot_bi.py`, server-side,
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

## The CREED lab block is CARRIED in `settings.py`, verbatim and last — the seat list is never hardcoded — 2026-09-01

The CREED Lab Launcher (a GUI app, outside this repo) replaces the hand-edited
`scripts/set_up_otree.bat` that lab staff run today. Each lab computer opens a
desktop shortcut at the oTree ROOM carrying that machine's seat label
(`/room/study?participant_label=B3`), and the admin page only shows the per-seat
present/absent board when the room has a `participant_label_file`. The launcher
writes that seat file into ITS OWN config directory and exports two variables —
`CREED_LABEL_FILE` (absolute path) and `CREED_ROOM_NAME` (default `study`). It
never writes a file into a project. A project opts in by carrying one marked
block at the END of `settings.py`, which this template now does, so a study
forked from here is CREED-lab ready with nothing to paste.

- **The block is carried VERBATIM, both marker lines intact, and the delivery
  vehicle was deleted.** `# === CREED lab support (paste at the END of
  settings.py) ===` … `# === end CREED lab support ===` is how the launcher
  detects that a project has opted in — a **text match**, not an import and not
  a config key. So reflowing a marker, renaming it, or wrapping the block in
  anything is not cosmetic: it makes the launcher believe this project never
  opted in, and the only symptom is a lab session whose board is empty. The
  block arrived as a top-level `creed_lab_block.py`; that file is a delivery
  vehicle, not code this project runs, and a stray second copy of the block is
  exactly the one-concept-two-implementations shape this file exists to prevent,
  so it was removed in the same change.
- **It APPENDS, and it MUTATES the room dict in place — it never reassigns
  `ROOMS`.** This template's single room carries `welcome_page`
  (`_templates/room_welcome.html`, the styled room gate — see the 2026-08-17
  entry on the `experiment` → `study` rename) and `display_name`. A block that
  ended `ROOMS = [dict(name=…, participant_label_file=…)]` would resolve
  perfectly, raise nothing, fail no test, and drop both keys — the participant's
  first screen silently reverts to oTree's bare framework interstitial. In-place
  mutation keeps every key the project set, whatever they are, which is what
  makes the block safe to carry into a study whose room this template has never
  seen. The corollary is that POSITION is load-bearing in both directions: the
  block must come after the project's `ROOMS` (or there is nothing to mutate),
  and **nothing may assign `ROOMS` after the block** (that assignment wins, and
  deletes the room the launcher just configured, again with no error).
- **The duplicate `ADMIN_USERNAME` is deliberate. Do not "tidy" either one.**
  `settings.py:1104` sets it from `OTREE_ADMIN_USERNAME`; the block sets it
  again at the end, falling back to whatever was already defined. Under this
  template the two resolve to the same value in every environment — that is
  measured, not assumed. Both stay: the block's line is the only reason the
  launcher's admin-username box does anything in a project that hardcodes
  `ADMIN_USERNAME` to a literal (oTree reads the admin PASSWORD from the
  environment but not the username), and it must sit after the project's own
  assignment or the project's would win. Deleting the template's line instead
  would make a block a study is free to remove the sole source of the
  template's own credentials. This is precisely the "helpfulness" failure
  CLAUDE.md opens with: the redundancy reads as an unfinished merge and is not.
- **Rejected: hardcoding the CREED seat lists into `settings.py`.** Tempting,
  because it needs no launcher and no environment variable. But which seats
  exist — and which machines are broken this week — is a fact about the LAB,
  not about a study, and a hardcoded list makes every study forked from this
  template carry its own copy. They then go stale **independently and
  invisibly**: nothing errors, the board simply stops matching the room, and it
  is noticed on the day of a session. One seat file, owned by the launcher and
  passed by path, is the single implementation. The project owns nothing.
- **`room_gate_test.py` §3b's synthetic configuration is now the REAL lab
  configuration.** That check builds a room WITH a `participant_label_file` by
  hand, because without one a native GET submit strips the id and its
  auto-submit loop cannot happen — it says so in its own docstring, and it says
  the dangerous configuration is what "a copied study that adds a labels file"
  would land in. Under the launcher that is no longer hypothetical: a CREED lab
  run is always that configuration. §3b is therefore load-bearing for the lab,
  not a defensive extra, and must not be simplified away on the grounds that
  the template ships no labels file.

**Enforced:** `scripts/tests/creed_lab_block_test.py`, 91 checks, no server and
no browser. Its method is a **differential**, not a remembered baseline: each
scenario executes `settings.py`'s source text in a child process twice under a
byte-identical environment — once as shipped, once with everything from the
start marker cut away — and requires `ROOMS`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `DEBUG`, `DATABASES` and `SECRET_KEY` to be equal. A child
process because `settings.py` is import-once and its values are decided by the
environment at import; a differential because a committed "this is what ROOMS
looked like" literal answers the wrong question and goes stale the first time a
study edits its room. §1 pins the markers and that the block is genuinely last;
§2 pins from the AST that nothing binds `ROOMS` after the block, and compares
the executed `ROOMS` against the `ROOMS = [...]` literal evaluated alone, which
catches a MUTATION an assignment scan cannot see; §3 runs the CREED variables
absent; **§4 is the backwards-compatibility guarantee** — it runs the exact
environment `scripts/set_up_otree.bat` exports, **read out of the bat file
rather than retyped**, so `DATABASES`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
`DEBUG` and `ROOMS` are proved identical for the workflow the lab uses today;
§5 proves an ACTIVE block adds exactly one key to the room and changes or
removes none, asserted as a key-by-key diff; §6 pins the `study` default and
that a launcher pointed at a different room name leaves the `study` room alone;
§7 aims squarely at `ADMIN_USERNAME`, the one name both assignments write.
The suite was mutation-checked when it was written: reassigning `ROOMS` instead
of mutating, removing the environment guard, and appending `ROOMS = []` after
the block each turn it red on the checks that name that failure.

**NOT enforced, honestly:** nothing here exercises the actual launcher, which is
not in this repository — the contract tested is the block's behaviour under the
variables the launcher is documented to export, not that the launcher exports
them. The block's BODY is not pinned byte-for-byte against a copy of the
delivered file either (deleting that copy was the point), so an edit inside the
markers is caught by the behavioural checks above and not by a checksum. And as
everywhere in this repo, nothing runs the suite for you.

## Prolific participants are told the quiz-attempts limit up front — gated on `recruitment`, counted from the ejection threshold — 2026-08-25

A Prolific participant who fails the comprehension check too many times is
ejected with a RETURN REQUEST (`quiz_comprehension_dq`). They are now told so
before it can happen, in four config-driven places: a consent participation
condition, the instructions intro, the pre-quiz prompt, and the quiz's own
wrong-answer message, which counts down the remaining attempts and, on the last
tolerated failure, warns that the next wrong submission ends the study. None of
it appears in a lab session, where returning a submission is meaningless.

- **Gated on `common.is_prolific` (the `recruitment` axis), NOT on
  `participant_label` presence and NOT on a new config flag.** A lab session can
  carry a seat-ID label too, so a label-presence gate would show return-request
  wording in the room — the exact collapsed-distinction trap CLAUDE.md names.
  `recruitment` is already the template's "decides copy" signal (see the rule
  above `common.is_lab`), so this reuses it rather than inventing a parallel
  `is_prolific` boolean. *Rejected:* the task's own fallback suggestion of a new
  `is_prolific` SESSION_CONFIG flag — unnecessary here because a cleaner platform
  signal already exists.
- **The disclosed count is the failure THRESHOLD, not threshold+1.**
  `intro.quiz.error_message` ejects at `comprehension_failed_attempts >=
  quiz_comprehension_max_failures`, incrementing before the compare, so with the
  shipped `3` the third wrong submission is the ejecting one and a participant
  has exactly three chances. The mirrored source this was ported from computes
  `max_quiz_attempts = max_quiz_failures + 1` because ITS config means "tolerated
  failures"; this template's config already means "the failure that fails the
  quiz", i.e. it already equals that source's `cap+1`. Disclosing threshold+1
  here would promise four attempts and eject on the third — a broken promise, so
  the `+1` was deliberately NOT carried over. *Enforced:* `common.max_quiz_attempts`
  returns the threshold, with a docstring tying it to the ejection predicate, and
  `quiz_attempts_disclosure_test.py` walks the real countdown 2→1→eject.
- **One helper, both apps.** `common.max_quiz_attempts` is the single source of
  the number; the consent page (`before`) and the instructions/pre-quiz/error
  copy (`intro`) all read it, so the promise on the consent page and the count
  the quiz ejects on cannot drift — one-concept-two-implementations avoided.
- **Safe-config fallbacks, so old/lab sessions never 500 and never leak the
  wording.** The count reads through `common.cfg` (frozen session missing
  `quiz_comprehension_max_failures` → shipped default 3, not a KeyError); the
  gate reads through `common.is_prolific` → `cfg('recruitment')` → default `lab`,
  so a session created before `recruitment` existed reads as non-Prolific and
  shows nothing.
- **The consent line is kept to two lines, and Mode 2's reading rhythm was
  tightened, so consent keeps its one-screen fit.** The Prolific consent card is
  a Mode 2 single-page-fit page with only ~8px of spare height at the font floor
  at 1280x720, and this file's logo-footer note requires the consent control to
  stay ABOVE THE FOLD there. The disclosure as first written (two sentences plus
  a "does not affect your standing" clause, ~74px) pushed the card past the
  viewport — Mode 2 gave up and fell to whole-window scroll, dropping the consent
  radio below the fold (caught only by `render_check.py`, no 500, no other failing
  test — the layout trap CLAUDE.md warns of). Fixed by (a) compacting the consent
  line to one sentence + the bold `This is a return request, not a rejection.`
  (the "standing" reassurance lives in the quiz-page error instead), and (b)
  tightening the SHARED Mode-2 rhythm in `base.css .single-page-fit`: body
  line-height 1.65→1.4 (still an easy measure; the largest single reclaim), the
  content flex-gap 10→8px, the button-row pad 14→12px, and zeroing a stacked
  form's trailing `.mb-3` margin (Bootstrap `!important`, so overridden with
  `!important`). Prolific consent now fits Mode 2 at font 16 (above the 15 floor)
  with the radio and Next well above the fold; lab consent is a touch tighter and
  still fits at the full font. *Rejected:* accepting the Mode-1 scroll fallback on
  consent (a documented UX regression) and dropping the consent-page disclosure
  (the task requires all four places). *Not-yet-done here:* the CSS change ages
  the site previews — re-run `scripts/site_previews/build_site_previews.py` and
  its check after this (CLAUDE.md styling note).

*Enforced:* `scripts/tests/quiz_attempts_disclosure_test.py` (production, in-process)
asserts the Prolific path — wording on consent/instructions/pre-quiz, the exact
per-attempt error messages, the count of 3, the DQ on the third failure, and a
correct submission always passing — AND the lab path (no wording, plain error,
no 500), AND the two frozen-config fallbacks (threshold key absent → default 3;
`recruitment` key absent → no wording). `copy_routing_test.py` independently
holds that the word Prolific never reaches a lab participant and is still named
exactly once on the Prolific consent page. `render_check.py`'s `consent`
(Prolific) single-page-fit leg measures that the card, with the disclosure, still
fits one viewport at 1280x720 with the consent control above the fold.

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

## `/health` is a verdict a machine can act on, `verify_deploy.py` is the only thing that fails on a stamp, and appending a route to oTree has ONE implementation — 2026-08-23

The second half of the build-provenance work. Its first half asked *"what code
did this participant run?"*; this half asks *"did that deploy actually work?"* —
the question that was unanswerable when a Railway deploy reported SUCCESS with
the container already exited, and when a build went out with its stamp silently
missing and looked perfectly healthy.

### One route installer, because there are now two callers

Appending a route to oTree's own app existed once, in
`experimenter_dashboard.install_dashboard_route`. `/health` needs the same
thing, and a second copy is the inverted collapsed-distinction defect CLAUDE.md
devotes a section to: one concept, two implementations, drifting invisibly until
an oTree upgrade moves the route table and only one copy is updated. So the
route-table half moved to **`otree_routes.py`** — importing `otree.urls`, the
mid-import-versus-drift split, the `routes` shape check, idempotency by route
name, extending both the table and a live `otree.asgi` router, and the
`INSTALLED`/`ALREADY`/`NOT_IMPORTABLE` vocabulary. **Rejected:** importing the
dashboard from `health.py`, which would make a deploy gate depend on an operator
convenience.

**The `AdminView` auth shape check STAYED in the dashboard**, and the split is
the point: it is about WHO MAY LOOK AT THE PAGE, which is that module's
commitment. `/health` deliberately has no auth at all, because a platform
healthcheck can present no cookie. Those are different commitments, not one
commitment two callers share. It now runs inside the route-builder callback the
shared installer invokes, so it still fires only when an install is really about
to happen — never on the idempotent path.

**The NOT_IMPORTABLE-versus-drift distinction was preserved exactly**, because
CLAUDE.md names collapsing those two as a worked example of the class.

Two guards are NEW, and both close silent failures the single-caller version
could afford not to have: a route built under a name outside the caller's
declared tuple is REFUSED (that tuple is what idempotency and the
installed-check are decided on, so such a route installs twice and reads as
absent), and a path already served under another name is REFUSED (Starlette
matches the first route that matches, so two handlers on one path means a deploy
gate reads whichever was registered first).

**Both install from the tail of `outro/__init__.py`, not early.** The brief
argued `/health` "wants to install early, since its job is answering while
things are still coming up". Measured, that is not available here: importing
`otree.urls` builds the whole route table, which walks every app's
`page_sequence`, so it cannot happen before every app module is imported, and
`otree.urls` is not importable at `settings.py` time at all. There is also no
window to close — the routes only need to exist before `otree.asgi` builds the
app, which is after every app import on every supported boot path.

**The global-lock exemption is per-endpoint, not per-installer.**
`/health` registers itself in oTree's `VIEWS_WITHOUT_LOCK`; the dashboard
deliberately does not. oTree serialises every request behind one lock, so a
health poll queueing behind a participant page turns a 20ms check into a
timeout, a platform reads the timeout as UNHEALTHY, and a container gets
restarted for being BUSY — an outage manufactured by its own monitoring. The
dashboard reads a whole session's rows and already accepts the lock's cost;
running it unlocked would buy an operator screen showing half-committed state.

### `/health`: the verdict, and everything it must NOT depend on

200 when the database answers AND a session is bound to the room; 503 otherwise.
Those two are what a participant's first click depends on, and the two 503
reasons are kept apart deliberately — "nothing has bound a session yet" is
normal and self-healing, "the database is unreachable" is the dead-application
case. One indexed query answers both, which also makes it cheap enough to poll.

**The build stamp and the pre-launch checklist ride in the body and touch the
verdict nowhere.** A build running testing values is a perfectly healthy
deployment — it is how every pilot runs and it is the state this template ships
in. If a testing value made this 503, a platform would refuse to promote every
rehearsal build, and the check meant to protect the real launch would be the
check everybody disables.

**Unauthenticated, so it publishes problem NAMES and never VALUES.** The
checklist's values include Prolific completion codes, and a code is money to
whoever finds it. The test asserts the names are present AND that no placeholder
value appears anywhere in the body — an absence-only assertion would pass
against a 404.

**A method check written into the handler was DELETED, not kept.** Measured
against starlette 0.14.1, `Route.handle` answers 405 before the endpoint is
called, so that branch was unreachable. Inert code that looks like a guard is
worse than none: the next reader believes it. The `methods=` argument is both
the declaration and the enforcement, and a comment at the Route says so.

**A fork with no room** gets a permanent 503, correctly for this template (the
room IS the entry point) and wrongly for a study handing out links directly.
That is stated at `health._readiness_reasons`, which is the one function such a
fork changes. **Rejected:** a settings knob, which would be a second axis for
something one predicate already answers.

### `verify_deploy.py`: the one sanctioned failure, kept thin by delegating

It compares the RUNNING build's stamp against the one just deployed and exits
non-zero on a mismatch. That is the whole reason it exists, and it is safe to
make provenance fatal here for reasons that hold nowhere else: a human runs it
by hand after a deploy, it is not in the application path, and it cannot take a
study down.

**The room binding is read from `/api/rooms`, not from `/health`**, even though
`/health` also knows — two independent witnesses, so a bug in `health.py` cannot
certify itself. The test stages exactly that: a `/health` claiming the room is
bound while the REST API says it is not, and the gate still fails.

**Frozen-config drift is DELEGATED to `predeploy_check.audit_frozen_session_configs`**,
not reimplemented. That function is already the one implementation, and it
already carries the two-severity rule and the named exemption; a second copy
here is the same defect class the installer extraction just removed. Both inputs
are asked of the DEPLOYMENT (`/api/session_configs` and the bound session's
config) rather than computed from the local tree — comparing a deployment
against our belief about it is the error the script exists to remove. Two limits
are stated rather than papered over: liveness cannot be computed over REST (the
audit's own rule is that unsure counts as live, which is also the truth for the
bound session), and only the BOUND session is audited, because auditing every
session is `predeploy_check.sh` against a database copy, before the deploy.

**It does NOT fail on the pre-launch checklist**, which spec §4(a) asked for.
`/health` carries only the boot banner's subset of it — the full
`prelaunch_check.py` hashes every file under `_static/` and imports the app,
which is absurd on a polled route — so failing a deploy on it would be a check
lying about its own coverage. The names are printed as information; the complete
guard is `prelaunch_check.py`, run in the launch environment.

**FROZEN_CONFIG is the one assertion that is NOT retried.** It is a pure function
of the bound session and the running build, and neither changes on its own;
waiting out the deadline to be told the same thing again is how a gate teaches
people to stop running it.

### The pre-launch check prints the stamp, and that is all it does with it

`prelaunch_check.build_line()` names the build being cleared for launch, next to
the PASS/FAIL verdict, and is deliberately not in the `problems` list. It is a
different claim from `settings.py`'s boot banner (which says what the SERVER is),
and it is the line a CI capture needs to answer "which build did we clear?" three
months later.

**Enforced:** `scripts/tests/health_test.py` (49 checks — the shared installer's
five outcomes including both new guards, the verdict flipping 503→200→503 in one
process, an unstamped build and a dirty checklist both riding a 200, the body's
key set asserted CLOSED so no participant field can arrive on an open route
unnoticed, and every block broken in turn to prove the route cannot 500);
`scripts/tests/verify_deploy_test.py` (34 checks — the real script as a
subprocess against a programmable stub, green path first and re-asserted last,
with every red case one field different from it);
`scripts/tests/dashboard_test.py` §A, whose patch target moved to
`otree_routes.import_urls` with the seam.

---

## Check 2b exempts `build_at_creation` from MISSING — by name, reported, and on the audit's own argument — 2026-08-23

Closes the item Phase 1 left open. `scripts/predeploy_check.py` check 2b treats
a key MISSING from a live session's frozen config as a FAILURE, so a study that
adopts build stamping while sessions are running would see it fail on
`build_at_creation` for ever — which contradicts "provenance is documentation,
never a gate".

**The exemption is granted ON the audit's own argument, not despite it.** 2b
fails MISSING because of a stated consequence: participants run WITHOUT the key
while `settings.py` looks correct, because `common.cfg` quietly substitutes the
shipped default. For `build_at_creation` that consequence cannot occur. Its only
reader, `common.build_at_creation`, is deliberately RAW and never routes through
`cfg` — precisely so that absent keeps meaning *"this session was created before
build stamping existed"* rather than being back-filled with the build running
right now. So there is no silent default, nothing for a participant to run
without, and nothing a recreation would repair. Absent is not a defect; it is
the designed meaning, and saying so is the record working.

**Reported, never skipped.** The finding moves to the informational `diffs`
channel and reads like the plain value differences beside it — what the session
has (`absent (MISSING)`), what the current setting is, and the named reason. A
silent skip would be indistinguishable from the audit not looking, which is the
failure mode that whole file exists to avoid, and it would hide the day somebody
adds a key that does not deserve the exemption.

**A NAMED DICT, `MISSING_IS_THE_DESIGNED_MEANING`, with the bar written next to
it:** the key must have exactly one reader, that reader must be raw, and absence
must be a meaning that reader acts on. If a key can fall back to a shipped
default, it does not belong. Adding an entry is an edit a reviewer sees — the
same friction `SOURCE_PRUNE` in `build_context_test.py` exists for. **The
exemption covers MISSING only**; a PLACEHOLDER still fails, because that is a
different finding and only one of the two has this argument behind it.

**Rejected:** exempting the key silently (indistinguishable from a blind spot);
dropping MISSING to a warning generally (that would disarm the check for every
key, including the completion codes it was written for); and doing nothing,
which was Phase 1's honest position but leaves a study unable to deploy while it
adopts the feature.

**Also settled, unchanged:** `scripts/write_build_info.py` still REFUSES a
commit that is not a real 40-character SHA, exit 2. Phase 1 flagged it as
arguably a third thing that "fails" and offered to drop it. Julian's ruling: it
stays. It is a deploy-time tool validating its own arguments before anything
ships, the worst case is an unstamped deploy (which runs perfectly), and a stamp
that is not a real SHA is worse than no stamp because no later reader could tell
it from a real one.

**Enforced:** `scripts/tests/predeploy_frozen_audit_test.py` — the exempted key
reported as information rather than a problem AND carrying its reason; a SECOND
key missing from the same session still failing, so the exemption is one key
rather than a weakening of the rule; and the dict emptied to prove the same
session then DOES fail, so the pass is the exemption working and not the audit
looking away. Measured end to end against the real
`_ai/live_data/db_generated_2026-08-18.sqlite3` as well
(`_ai/build_provenance/phase2_test_output/exemption_against_live_data.txt`),
which is the database Phase 1 measured the failure on.

---

## Build provenance is DOCUMENTATION, NEVER A GATE — and it is recorded in three places so their disagreement is the signal — 2026-08-23

Decided by Julian, from a spec written by the `exp_pilots` study after it shipped
the same feature. Two questions kept being unanswerable for anyone running a real
study: *"what code did this participant actually run?"* (a study collects data
across days and redeploys; without a stamp in the data the honest answer is git
archaeology) and *"did that deploy actually work?"* (Railway reported a deploy as
SUCCESS with the container already dead). The first is what this entry is about.

**A commit cannot contain its own SHA** — the SHA is computed over the commit's
content — so the stamp is written at DEPLOY, by `scripts/write_build_info.py`,
into `BUILD_INFO.json` at the app root, carried into the image by the
Dockerfile's `COPY . .`, and **never committed** (it is gitignored: a committed
stamp would describe the previous commit in the tree of the next one).
`buildinfo.py` reads it once at boot. The writer takes the values as **explicit
arguments and never shells out to git**, so it is testable in a container that
has neither. `build_number` is `git rev-list --count HEAD`: monotonic, derived
rather than stored, and the half a human can say out loud.

**THE OVERRIDING CONSTRAINT, and it overrides the incoming spec.** Nothing in
`settings.py`, the boot banner, the pre-launch check or any participant path may
fail, refuse, warn-as-error or change behaviour because a stamp is missing,
absent or wrong. An unstamped build is a perfectly valid build — it is the state
of every local run and every test run in this repo. The spec asked for a
launch-time gate that FAILS on a missing stamp; Julian rejected that for the
template. Consequences, deliberately: a missing `BUILD_INFO.json` reads
`unstamped` everywhere and is not a problem; the pre-launch banner prints the
stamp as information next to its `DEBUG=` line and never counts it as a problem;
**there is no on/off setting, because there is nothing to switch** — "off" is
simply not running `write_build_info.py` at deploy, at which point the whole
feature is inert.

**Two sanctioned exceptions, both outside the application path.**
`scripts/verify_deploy.py` compares the running stamp against what was just
deployed and exits non-zero on a mismatch — a command a human runs by hand after
a deploy, and the whole reason that script exists. And
`scripts/write_build_info.py` REFUSES to write a stamp whose commit is not a real
40-character SHA: that is a deploy-time writer rejecting its own malformed
arguments before anything is deployed, and the study that results is simply an
unstamped one. A stamp that is not a real SHA would be worse than none, because
no later reader could tell it from a real one.

### Three places, and the disagreement is the point

1. **`participant.build_sha` / `build_number` — the evidence**, stamped ON
   ARRIVAL from the RUNTIME build, at the same call that takes the treatment cell
   (`before.treatment_assignment.assign_on_arrival`, reached from
   `intro.instructing.get`). **Not at session creation**: a session outlives
   redeploys, so a creation-time stamp would claim every participant ran the
   creation-time build. That is the identical argument this template already made
   when treatment assignment moved to arrival (2026-08-18), which is why the two
   are taken at one call. Seeded blank at creation, so blank means "never
   arrived", `unstamped` means "arrived on a build with no stamp", and a SHA
   means what it says — three different facts, kept apart.
2. **`session.config['build_at_creation']` — one half of a comparison, not
   truth.** Frozen at creation; its name carries that.
3. **The session config's `doc` string**, built at import, which oTree renders
   read-only on the create-session screen (it is in oTree's `NON_EDITABLE_FIELDS`
   and the REST API rejects attempts to modify it), so an operator sees which
   build they are about to create a session ON.

None is trusted alone. **Divergence is INFORMATION, not an error** — a session
created on one build and serving another is what a mid-study redeploy looks like
from the data — and nothing anywhere styles it as an alarm.

### `build_at_creation` is a DICT, and it is read RAW

**A dict, not a string:** oTree turns every bool/int/float/str config value into
an editable text box on the create-session screen, and provenance an operator can
retype is not provenance.

**Read raw** (`common.build_at_creation`), never through `common.cfg`. `cfg`
falls back to the value shipped in `SESSION_CONFIG_DEFAULTS`, and the shipped
value of this key is *the build running right now* — so reading it through `cfg`
would report a session created before the key existed as having been created on
the CURRENT build: provenance invented by the very helper that protects every
other parameter, and indistinguishable from a true record. Absent must keep
meaning "created before build stamping existed". This is the second deliberately
raw read in `common.py`, next to `flag`, and for a *related but different*
reason — the comment at each says which.

### The `.gitignore` / `railway up` interaction, written down because it bites

`railway up` **honours `.gitignore`**, so the very line that makes the stamp safe
for git makes it invisible to that deploy: the build ships completely inert,
reports unstamped, and looks perfectly healthy. The fix (delete `.gitignore` from
the throwaway staging tree, write a `.railwayignore` instead) is documented in
`docs/hosting_railway.md` and pointed at from `.gitignore` itself.
The same `.gitignore` also excludes curl COOKIE JARS by pattern rather than by
name: they only ever arrive from ad-hoc debugging, one was committed in
`exp_pilots` holding a live admin session cookie, and the next one will not be
called `cookies.txt`.

**A known consequence, CLOSED the same day — see the check-2b entry above.**
`scripts/predeploy_check.py` check 2b reports a config key MISSING from a live
session's frozen config as a FAILURE, so a study adopting build stamping while
it has running sessions would see 2b fail on `build_at_creation` for those
sessions, at odds with "provenance never fails anything". It is now a NAMED,
REPORTED exemption (`MISSING_IS_THE_DESIGNED_MEANING`) rather than the silent
skip that was rightly refused here.

**Enforced:** `scripts/tests/build_provenance_test.py` (three legs: the pure
reader/writer, plus a STAMPED and an UNSTAMPED in-process run each walking a real
arrival, because the running build is fixed at import and no monkeypatch can
honestly simulate the other case); `scripts/tests/frozen_config_test.py`'s final
section, which goes red if anyone ever routes `build_at_creation` through `cfg`;
`scripts/tests/xss_escaping_test.py`, which covers the commit subject — free text
from outside the repo, rendered UNESCAPED by `{{ config.doc|safe }}`.

---

## The build context is checked in BOTH directions, and the must-survive list is derived from the source tree — 2026-08-23

`.dockerignore` in this template was already clean — `data/`, `db.sqlite3`,
`_ai/`, `.venv/`, `previews/`, `*.log`, `.env` and the `*.command` launchers were
all excluded, with the nested cases spelled `**/`. So the deliverable was never a
fix; it was `scripts/tests/build_context_test.py`, which keeps it that way. **A
clean `.dockerignore` is a state, not a property**: the Dockerfile is `COPY . .`,
so every directory anybody adds ships by default, and both ways of getting this
wrong are silent. A hazard that arrives (an `exports/` of participant CSVs, a
curl cookie jar, a database snapshot) fails nothing and is baked into an image
that keeps every layer forever; a line added to stop that, which also excludes
something the app renders from, produces a container that boots perfectly and
500s a live page — which is how `_templates` shipped EMPTY in the study this
template feeds while every source-tree test stayed green.

**The must-survive half is DERIVED FROM THE SOURCE TREE, not parsed from the
Dockerfile and not declared as a list of paths.** The brief offered those two
options; both are wrong here for concrete reasons. The Dockerfile is `COPY . .`
and names no template, asset or module at all, so parsing it for the app's
runtime material would produce an EMPTY requirement that passes against
anything — the vacuous-test failure this repo treats as worse than no test. A
declared list is the retyping problem: it is correct the day it is written and
silently wrong the first time somebody adds a template. So the requirement is
four derivations that update themselves — every `.html` in the tree, every
served file under `_static/` (with "served" taken from
`prelaunch_check.IGNORED_NAMES`/`IGNORED_DIRS`, the asset guard's own definition,
and cross-checked against the file count `hash_static()` itself reports), every
`.py` outside `scripts/`, and the `/app/...` paths the Dockerfile DOES name (the
boot path: `scripts/db_state.py`, `requirements.txt`). This template has no image
verifier to defer the list to, which is what `exp_pilots` parsed its from.

**The one thing that must NOT be derived is the prune list.** `SOURCE_PRUNE` is
declared in the test and must never be read from `.dockerignore`, because a
requirement derived from the ignore rules deletes itself: exclude `_templates/`
and the requirement that `_templates/` survive disappears with it, and every
widening approves itself. The cost is that excluding a new directory needs a
second edit, in the test, where a reviewer sees it. **That friction is the
mechanism, not an oversight.**

Three smaller decisions inside the same change:

- **Hazards are judged by CONTENT, not by filename.** `data_backup/`,
  `db.sqlite3.old` and a cookie jar saved as `jar` carry exactly the same
  participant answers, Prolific IDs and admin session cookie, and a name check
  misses all three. The detectors key on the SQLite magic bytes, the Netscape
  cookie-jar header, and an oTree export's header row — the last as a whole
  comma-separated FIELD, because a substring test flagged this repo's own prose
  on the first run.
- **`exports/` is newly excluded, and it was a real gap.**
  `scripts/export_data.py --out` defaults to the RELATIVE `exports`, so the
  documented way to export data during a run drops every participant's answers
  into the repo root, where nothing was excluding them from git or the image.
- **`BUILD_INFO.json` is the one gitignored file that must NOT be
  dockerignored**, and the `.dockerignore` header's own advice ("when you add a
  line to `.gitignore`, add it here too") is what would break it. Excluding it
  fails nothing: the build succeeds, the container boots, every page renders, and
  every deployed build reports itself unstamped forever.

**Rejected:** running `docker build` in the test (no daemon here, and it would
make the check un-runnable on the machine most likely to need it); and asserting
only that the hazards are gone, which is an absence-only test and passes against
a `.dockerignore` that excluded the whole application.

*Where enforced:* `scripts/tests/build_context_test.py`. Section B self-tests the
Docker pattern matcher against the semantics that bite (a pattern with no `/`
matches at the context root ONLY; `*` does not cross `/`; `**/` matches zero or
more segments), and section E proves every absence can go red — with no rules the
content scan finds the real databases, each detector is run against a synthetic
hazard AND a lookalike that must not flag, and five over-broad rule sets are each
required to break the must-survive half. `docs/README.md` §4 tells a researcher
when to run it.

---

## `start.sh` states a timeout class at every call site, and re-reads the room before calling a creation failed — 2026-08-23

Two changes to the host-side room binder, both ported from a crash in
`exp_pilots` on 2026-08-21, and deliberately NOT the rewrite that study's spec
describes. Its boot script is a different thing — a Python entrypoint run inside
the container. This one is bash and curl, run by a human or a launcher against an
already-running server, so it never had that script's bug and does not need its
structure.

**1. Two timeout classes, with no default to inherit.** `exp_pilots` ran its
220-seat session creation through the same 15-second timeout as its millisecond
health checks; creation legitimately takes minutes (oTree builds every
participant x round row inside the one request), the script read a slow SUCCESS
as a failure, and the container exited. This script had the mirror-image risk —
**no timeouts at all**, so a server that accepts a connection and never answers
hangs the lab launcher silently, with no message and nothing to look at. Both are
now impossible: `api()` takes its `--max-time` as its FIRST ARGUMENT, so there is
no shared default for a future call site to inherit, and each site names its class
(`READ_MAX_TIME`, 20s; `CREATE_MAX_TIME`, 600s). The structural half matters more
than the numbers — a generous creation timeout costs nothing when creation is
quick, and the only thing a tight one buys is an outage.

**2. A client timeout is not proof the POST failed server-side.** The same
`exp_pilots` crash left an ORPHAN SESSION behind, created by a request that
completed after its client had stopped listening. So a failed creation — a curl
timeout, or a reply that parses to no session code — now RE-READS the room before
reporting anything fatal, and reports the binding it finds instead of failing.
This is the reuse rule the whole script exists for, applied to its own failure
path: a retry that does not re-check binds a second session over a good one, and
every participant already holding a link to the first is stranded. **Rejected:**
a retry loop (the spec's shape). One re-read answers the question that was
actually asked, and re-running the script is already the safe recovery, because
step 1 reuses whatever is bound by then — which the FATAL message now says.

The limitation is stated rather than papered over, and it was MEASURED rather
than assumed: against a real oTree 6.0.15 server, the room binding appears only
when `POST /api/sessions` returns (creation is one transaction — a 1200-seat
`lab` session bound the room at t+3.75s and returned at t+3.74s). So one re-read
detects a creation that COMPLETED unheard; a creation genuinely still in flight
is honestly reported as unbound, and re-running the script is the recovery. In
practice the re-read is often served AFTER the creation anyway, because it queues
behind it — a 400-seat creation cut off at a 1s client timeout was found bound by
the very next read, with exactly one session in the database.

*Where enforced:* `scripts/tests/start_sh_room_bind_test.py` drives the real
script as a subprocess against a stub oTree REST server that can be slow on
demand — the only way to stage "bind the room, then withhold the reply". It
asserts on the server's POST COUNT rather than on what the script printed, since
"reusing it" printed while a POST went out anyway is exactly the bug the message
would hide. Section 8 asserts the structural half: no bare `curl` call site, and
every `api()` call naming a declared class.

---

## The primary action is the RIGHTMOST control in a button row; the two re-read mechanisms stay apart — 2026-08-21

Julian reported being "offered an option to skip the instructions and the quiz"
in a PROLIFIC session and not in a LAB one. Investigated before changing
anything, and the report turned out to be about a real defect but not the one it
described.

**There is no skip.** Driven over real HTTP in production mode, neither study
type is offered any skip: `DEBUG` is off, so the "Skip quiz (testing)" and "Skip
instructions (testing)" buttons are not rendered at all. The prolific quiz page
does carry one control the lab's does not — the at-will **"Re-read the
instructions"** button — and it is a DIALOG opener: `type="button"`, and the
dialog it opens contains no form control of any kind. It submits nothing and
consumes no round. A hand-crafted `redoinstructions=1` POST from a prolific
participant is refused server-side (`reread_available` gates both
`error_message` and `before_next_page`), while the same POST from a lab
participant with the offer open is granted — so the refusal is about the study
type and not about luck.

**The defect was the BUTTON ORDER, which is what made it read as a skip.** The
row rendered `[Next] [Re-read the instructions]`, putting a secondary control in
the rightmost slot — the slot a participant's eye and thumb go to, and the one
the rest of the template reserves for the primary action. It is now a RULE OF
THE COMPONENT rather than a page's decision: `.button-row > .next-button:not(.ghost)
{ order: 1 }` in base.css, with the markup written secondary-then-primary too so
the visual, DOM and TAB orders agree and the `order` declaration is an inert
backstop. **`:not(.ghost)` is load-bearing** — the ghost variant IS the secondary
shape of the same button (the instructions pager's "Back"), so keying on
`.next-button` alone would put Back and Next in the same slot and settle nothing.
Every other page in the template has a one-control row, so nothing else moved.
**Rejected:** patching the quiz page, and extending the rule to `.modal-actions`
— a different component whose own primary-first convention is currently
consistent with itself, and which is not what was reported.

**The two re-read mechanisms are NOT one concept decided twice, and were kept
apart.** It looks like the classic drift: `reread_available` keyed on the
`quiz_reread` MODULE FLAG (True for lab, False for prolific) and
`show_reread_dialog` keyed on the STUDY TYPE (the mirror image). They are two
mechanisms. The lab's is a one-time re-read **PASS** that costs a round and sends
the participant back through `instructing`; the online one is an at-will
**DIALOG** that costs nothing and cannot advance anybody. Each modality gets
exactly one way to see the instructions again — supervised second pass plus a
human to ask in the lab, an always-available dialog online where there is no
such human — and two on one page would read as a contradiction. That is Julian's
own decision (2026-08-11). Merging them would leave one modality with no re-read
at all. The split is now stated at the split point, as a named predicate
(`intro.at_will_reread_available`) whose docstring says why it must not be
merged, with `reread_available` pointing back at it. It reads `not is_lab`
rather than `is_prolific` deliberately: the question is "is there an experimenter
in the room?", and a future third `recruitment` value must get the dialog, not
silently lose its only way to re-read.

**A reported third defect was not one.** `explicit_consent` is absent from the
PROLIFIC entry of `RECRUITMENT_PROFILES`, which looks like a key the profile
forgets to set. It is deliberate and already commented there: the key falls
through to `SESSION_CONFIG_DEFAULTS`, which oTree merges into every session
config at creation. Checked against a real created session — a prolific
session's STORED config carries `explicit_consent=True`, a lab session's carries
`False`. Nothing is missing and no lookup can fail; adding it to the profile
would only duplicate the baseline.

**Where it is enforced.** `scripts/tests/reread_controls_test.py` — both study
types walked to the quiz over real HTTP in production mode: no skip anywhere
(paired with DEBUG asserted off, without which that absence is a statement about
the server); the at-will control present online and absent in the lab; the
dialog proven inert (no form control in it, and its only exit goes back to the
quiz); the hand-crafted POST refused for prolific AND granted for lab; and the
document order. `scripts/tests/render_check.py` leg AI measures the RENDERED
boxes at three viewports — `order` is a layout property, so a source-order
assertion can see neither its success nor its failure.

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

## The "up to 2 weeks" payment line is LAB-ONLY, and the closing instruction is a shared CENTRED component — 2026-08-21

Two fixes to `outro/Results.html`, one participant-facing and one structural.

**The payment line.** "Please leave up to 2 weeks for the payment to be
processed" was unconditional. It describes the LAB's payment: the experimenter
collects an IBAN and the institution transfers weeks later. A Prolific
participant is paid **through Prolific**, on Prolific's timetable, so the
sentence is not merely redundant for them — it is **false**, and it invites a
support message about a payment we never make. It is now gated on the STUDY TYPE
axis (`is_lab`, one implementation in `common.is_lab`), joining the "stay
seated" sentence already under that gate.

**Gated on the axis, NOT on a payment module flag.** `collect_outro_bank_details`
was the tempting read — it is literally the bank-details switch — and it is
wrong twice: the `test` config turns it OFF on a `lab` session that still pays by
transfer, and "which platform pays" is a property of *where the study runs*, not
of which form we happened to show. Flags decide mechanics, `recruitment` decides
copy (`docs/conventions.md`).

**The closing instruction, and the collapsed distinction under it.** "Please
click the button below to complete the study and return to Prolific" rendered
**flush left** under a centred receipt. The cause was not a broken rule.
`.section-text` deliberately sets only the reading measure and centres the
*block*, leaving text alignment to the card FAMILY; the results card is a plain
`.screen-card`, so the sentence inherited the card's flush-left while the receipt
above it was centred by `.payment-summary` and the notes below it by
`.results-notes`. **The same sentence on `outro/Ended.html` was centred all
along**, for an unrelated reason — `.narrative-card .section-text`. One concept,
two implementations, already disagreeing: CLAUDE.md's inverted rule, wearing a
stylesheet. Rejected: adding `text-align: center` to the results page, which
would have made it three implementations. Both endings now compose the shared
`.closing-instruction` component (base.css, with a specimen in
`_static/global/html/template.html`), so the alignment is decided once.

**It also MOVED**: directly under the receipt, above the payment notes and the
payoff table, so it sits with the thank-you and the total rather than buried
between the SEPA warning and the table. Julian chose this over placing it
immediately after the greeting *inside* the 340px receipt, which would have told
participants to leave before showing what they earned and pushed the Total row
into the fold that `results.css`'s short-viewport block exists to keep it out of.

**Where it is enforced.** `scripts/tests/ending_copy_test.py` — four
configurations walked to Results over real HTTP in **production mode** (it boots
its own server, so the mode cannot be inherited), asserting the payment line
present for lab and absent for prolific, the closing instruction's document
order, and, for every absence, the matching presence plus `exit_code == finished`
so a walk that never reached the ending cannot pass. Rows 3 and 4 of its table
are the ones that matter: prolific with the redirects OFF must still not be
promised a transfer, and lab with them ON must still get its payment line — a
sentence gated on the nearest module flag passes a two-row version and fails
those. The centring is MEASURED in `scripts/tests/render_check.py` leg AH, off
the **line boxes of the real glyphs** (a Range's client rects) rather than off
`text-align`, on both endings at three viewports.

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
apps, `common`, `identity.py` and the tests; giving its values a richer shape
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
The convention is written up in `docs/skills_claude/writing_task.md`
("Elicitations — the shipped slider is the reference").

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
for the two new fields; `CODEBOOK.md` ("Passive focus trace").

**Schema-change consequence (the same rule as `round_payoff`).** This appends
two `main.Player` columns, and oTree's `create_all` never ALTERs an existing
table, so deploying it over a database that predates the columns 500s on every
page that loads the model — it needs `otree resetdb`, exactly like every prior
added column (CODEBOOK.md deploy note). The template has no live data, so this is
free here; a STUDY already running must add the trace at a reset boundary, never
hot over live sessions (the CLAUDE.md rule on schema changes). The local
predeploy fixture (`_ai/live_data/`, gitignored) was regenerated on the current
schema so `predeploy_check.sh` upgrade mode returns to its documented 8/9
baseline (only the deliberate REPLACE_* completion-code check fails).

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

## The scroll model is three modes: whole-window by default, single-page fit as enhancement, inner-scroll kept dormant — 2026-08-18

The card layout was reworked from ONE model (every card capped at 88vh with its
middle region scrolling inside it) into THREE. **Mode 1 — whole-window document
scroll — is the DEFAULT for every content page:** the card has no max-height, it
grows with its content and the whole browser viewport scrolls, with the forward /
decision control at the natural bottom. This is the SAFE default *because* it is
exactly what renders if a page's fit-check script never runs — nothing a
participant needs can be hidden by a script that fails silently, which is the
failure mode CLAUDE.md warns about. **Mode 2 — single-page fit — is progressive
enhancement layered on top of Mode 1**, opt-in on exactly the consent welcome
page and the tab-monitor agreement, desktop only: `global.js` measures and, if it
can, shrinks the body font within a narrow band (down to
`--single-page-font-floor`, ~15px) and tightens spacing to fit one viewport;
if fitting would drop below the floor it GIVES UP and the page is plain Mode 1.
It scales with **font-size and spacing only, never transform/zoom** — those make
the card a containing block and would trap the tab-monitor's fixed overlay inside
it. **The decision controls are never pinned** in either mode: a pinned Next lets
a participant reach the choice before seeing what they are agreeing to, or miss
that more exists below. **Mode 3 — inner-card scroll — is retained ONLY for the
results page** (its round-payment detail collapses to fit one page and expands to
scroll inside the card) and kept as a documented DORMANT opt-in (`.inner-scroll`)
rather than deleted, because the cap, the overflow region and the four scroll
affordances are real work any page may want again.

The card's TOP EDGE is **anchored** at a constant `--card-margin` below the
viewport top on every page, never viewport-centred, so it does not jump between
pages of different content height (Julian). One proportional token feeds both the
anchor offset and the resting floor `--card-min = 100dvh − 2·--card-margin`, so a
resting card is symmetric top-to-bottom (reads as centred) yet fixed: content
shorter than the floor fills/centres inside the frame and never shrinks it, so two
short pages show the identical card. The instructions page is deliberately kept a
Mode-1 page whose shipped payoff-matrix slide (the two blocks "The payoff matrix"
and "What this means in practice" merged into one) overflows a 1280×720 laptop,
so the template ships a permanent demonstration of whole-window scroll.

**Rejected:** the old single capped-and-inner-scroll model (hid consent options
below an inner fold at 1280×720, and made the safe path depend on the fade
script); pinning the decision controls (reach-the-action-before-reading);
scaling the card with `transform`/`zoom` (traps the tab-monitor overlay);
deleting the inner-scroll scaffolding (results still needs it, and it is a
reasonable future opt-in).
**Enforced:** `--card-margin` / `--card-min` / `--inner-scroll-max` /
`--single-page-font-floor`, `.screen-card` (floor, no ceiling), `.inner-scroll`
and `.single-page-fit` in `_static/global/css/base.css`; `initSinglePageFit` in
`_static/global/js/global.js`; `scripts/tests/render_check.py` (Check B asserts
Mode-1 whole-window scroll on content pages and Mode-3 inner scroll on the results
page; Check Q asserts the fixed resting floor and that a tall page grows past it);
the committed `scripts/tests/geometry_baseline.json`. Working notes in
`_ai/scroll_model/` (local only).

## Session-config keys are named family-first and ordered into families, so the admin form reads as sections — 2026-08-18

Decided by Julian, while the template has **NO live studies** (so the rename is
safe now and would be a schema change across running sessions later). The admin's
session-configuration form renders `SESSION_CONFIG_DEFAULTS` in **insertion
order** and gives it **no section headings at all** — so the only structure
available is the key order plus a shared naming prefix per family. Every key was
renamed into a prefixed family and the dict reordered so the families are
contiguous: unprefixed top-level keys (`doc`, `recruitment`, `pilot_feedback`,
`num_experimental_rounds`, `explicit_consent`, `expected_duration_minutes`), then
`payment_*` (`payment_show_up`, `payment_num_rewarded`, `payment_quiz_bonus`,
with the two oTree built-ins `real_world_currency_per_point` /
`participation_fee` kept at the bottom of the block under their built-in names),
`quiz_*` (`quiz_comprehension_max_failures`, `quiz_comprehension_dq`,
`quiz_reread`, `quiz_verify`), `display_*`
(`display_before_show_duration_and_fee`), `collect_outro_*`
(`collect_outro_demographics`, `collect_outro_bank_details`), `telemetry_*`
(`telemetry_passive_capture`, `telemetry_device_capture`), `build_*`
(`build_static_version`), `tab_monitor*`, and `prolific_*` last. This is the same
move the participant-tracking fields made (see 'Participant tracking fields are
named family-first' — 2026-08-17), applied to the config form.

The old names named the *thing* and lost the family: `showup`, `num_rewarded`,
`quiz_bonus`, `verify_quiz`, `device_capture` each sat alone in a form with no
grouping, so a lab operator scrolled past Prolific-only machinery with nothing to
say which keys were theirs. The rename is **complete and grep-verified** — a
config key is a string-keyed lookup, so a half-rename is a silent wrong default,
not an import error — reaching `settings.py`, `common.py`'s safe accessors, the
`before/`/`intro/`/`main/`/`outro/` modules and their templates (oTree exposes a
config value to a template as a bare `vars_for_template` name, so `{% if
device_capture %}` had to move too), the scripts, the tests, and the docs. Two
disambiguations were held apart deliberately: the config key `static_version`
became `build_static_version`, but the **module-level `STATIC_VERSION` constant,
`C.STATIC_VERSION`, the asset-manifest `static_version` field and the template
reads of `C.STATIC_VERSION` are the code asset version — a different thing — and
did NOT move**; and `quiz_comprehension_max_failures` / `quiz_comprehension_dq`
renamed while the participant field `comprehension_failed_attempts` did not. The
default `num_experimental_rounds` was also dropped `10 → 5` in the same pass.

### The device allow-list joins the `prolific_` naming family — 2026-08-18

`allowed_devices` became `prolific_allowed_devices` and moved into the
`prolific_` block at the bottom of the form. **This is a form-navigation choice
about the prefix and the position, and NOTHING about the runtime changed** — the
gate is still decided from the entry request in every study type, the key is
still absent from both `RECRUITMENT_PROFILES` bundles (so selecting the prolific
study type never starts screening devices out on its own), and it still falls
through to the all-four baseline meaning the gate is off.

**The superseded rationale is preserved, not deleted.** The key previously lived
in its own ENTRY section specifically *because* it is "not a Prolific parameter":
that reasoning was correct about the behaviour and is still true of the
behaviour. What overrode it is that the form has no headings, so a key outside
the `prolific_` block but conceptually distinct from the payment/quiz/telemetry
families had no home that read cleanly — and grouping it by prefix with the other
end-of-form machinery keeps it out of a lab operator's way. The `prolific_`
prefix is therefore a **grouping label, not a claim of Prolific-specificity**;
the note above `prolific_allowed_devices` in `settings.py` and the bundle comment
in `RECRUITMENT_PROFILES` both say so at the point of use. **Rejected:** leaving
it in a lone one-key ENTRY section (a section of one in a form with no section
headings reads as noise); adding it to the prolific bundle to match the prefix
(that would change behaviour — the exact trap the prefix must not cause).

**Enforced:** `scripts/prelaunch_check.py` and the config-key set in
`scripts/tests/frozen_config_test.py` (`STRIPPED`) both enumerate the new names,
so a missed rename or a bundle that wrongly gained `prolific_allowed_devices`
shows up there; the HTTP/bot suites go red on a half-done rename because a wrong
config default changes what a participant reaches; and every old name was grepped
to zero across the repo (this entry and superseded code comments are the only
places the old spellings survive, as history).

## Popups are a four-tier ladder, chosen by distance from the experiment frame — 2026-08-17

Decided by Julian; brief in `_ai/template_adoption_brief.md` Topic A (local only —
`_ai/` is gitignored; not in a clone) with his answers in its ANSWERED section, and
the commissioning entry in `TODO.md`. Every message put in front of a participant
is now a choice between **four documented behaviours**, numbered **0–3 by how far
OUTSIDE the experiment frame** the message sits. The tier fixes the *behaviour*
(backdrop? how dismissed? can it move layout?); the call site keeps its own *skin*
and its own words. One catalogue names all four in one place
(`_static/global/css/base.css`, "THE NOTIFICATION TIER LADDER"); the shared
behaviour is in `_static/global/js/global.js` ("POPUP LADDER"), keyed off the
`popup--*` classes and `data-popup-*` attributes, so a study author writes markup
only.

- **Tier 0 anchored** (`popup--anchored`) — no backdrop; a panel beside its
  trigger, dismissed by outside-click or Escape. For something the participant
  ASKED FOR BY CLICKING. NEW in this template (distinct from the CSS-only
  hover/focus `.popover-anchor` tooltip, which stays).
- **Tier 1 toast / "sidetone"** (`popup--toast`) — no backdrop, absolutely
  positioned so it cannot move layout, auto-clearing, `role="status"`. The tier
  that did not exist here before; NEW.
- **Tier 2 modal** (`popup--modal`) — dimmed backdrop, blocks the page.
  **Escape-dismissible BY DEFAULT**; a modal that must be acknowledged opts in to
  button-only with `popup--acknowledge`. Keeps the study card language. IMPLEMENTED
  BY the existing shared warning-modal component (`.modal-backdrop` / `.modal-card`).
- **Tier 3 takeover** (`popup--takeover`) — full-bleed, blurred, opaque, **no
  dismissal by contract**. IMPLEMENTED BY the tab monitor's existing red
  away-overlay (`.tabmon-overlay`), which predated the ladder.

**The load-bearing choice: bring the two existing tiers in BY NAME, not as a
second implementation.** This template already shipped a mature, tested tier-2
modal and a tier-3 takeover. Building fresh `popup--modal` / `popup--takeover`
skins beside them would be the "one concept, two implementations" defect this
repo hunts (CLAUDE.md). So `popup--modal` shares ONE rule block with
`.modal-backdrop`, and `popup--takeover` shares ONE rule block with
`.tabmon-overlay` (grouped selectors, identical declarations) — the ladder is the
vocabulary, the existing components are the implementation. Only tiers 0 and 1,
which genuinely did not exist, are built new.

**The tab-switch warning modal was deliberately NOT migrated onto the shared
chrome, and this is a STOP-and-report, not an oversight.** It is one of the three
tier-2 cases (with the quiz failed-attempt and re-read prompts). The other two
already use `.modal-backdrop`, so migrating them was free — they gained the
`popup popup--modal` name and the shared focus trap, nothing visible changed. The
tab-switch warning keeps its OWN `.tabmon-modal` chrome and its own string-injected
JS in `tab_monitor.js` because re-skinning it would (a) change what the participant
sees (backdrop opacity 0.72 → 0.55, a different box and button) and (b) edit the
file that owns the disqualification route — two unrelated risks in one change, and
the one that can cost a participant their payment is not the popup. It is
catalogued as the tier-2 button-only case instead; the reusable `popup--acknowledge`
modifier plus its specimen give future modals that behaviour without touching the
live monitor. `tab_monitor.js` and `.tabmon-overlay`'s BEHAVIOUR are untouched.

**Accessibility is part of the component.** New tiers 0/1 ship correct roles,
focus move + restore (tier 0), polite announcement (tier 1),
`prefers-reduced-motion` (tier 1 transition, tier 3 blur). A shared focus trap
(`global.js` `popupTrapFocus`, ONE implementation) is wired into the tier-2/3
modals that were missing it — the every-page warning modal and the quiz reread /
failed-attempt dialogs — a keyboard-containment improvement that changes nothing a
participant sees. The generic modal helper traps every takeover and every
non-acknowledge modal while open.

**Rejected:** a separate `popup.js` file (this template centralises shared page
behaviour in `global.js`, the way the warning modal already works, so a new asset
in every template's bundle was avoided); a second `popup--modal` / `popup--takeover`
skin (two implementations of one concept); rewiring the tab-switch warning's chrome
now (participant-visible change coupled to the disqualification route); renumbering
any existing `1–4` tier comments (there were none in this template — that clause of
the brief applied to the pilot). Terminal pages such as the disqualification screen
are a ROUTING concern and out of scope: `popup--takeover` is the in-page overlay
only.

**Enforced:** nothing at boot — the ladder is convention + shared CSS/JS, held by
the base.css catalogue, this entry, and the specimens in `template.html` (CARD 3,
per CLAUDE.md's styling rule that a shared component must be demonstrated). The
behaviour-preserving claim is what the suites hold: `scripts/tests/render_check.py`
(`--diff` 1513 measurements within ±3px, unmoved; the reread dialog, the quiz
failed-attempt modal, the shared warning modal and the tab-monitor overlay all
still measure correct, the overlay still covers the whole viewport); the
browser/HTTP quiz suites (`gated_flow_test`, `full_journey_test`,
`completion_codes_test`), the tab-monitor suites (`tab_monitor_detail_test`, and
render_check's record-only-outro leg), `dashboard_test`, and the site previews
(regenerated and re-checked, since the screens inline these stylesheets). The
just-fixed regression suites (`completion_codes_test`, `screenout_softwall_test`,
`device_gate_test`) stay green. `STATIC_VERSION` 15 → 16 and the manifest were
re-stamped (base.css, tabmonitor.css, global.js, quiz.js, template.html changed).

## The asset manifest is re-stamped by hand, so a test asserts it actually was — 2026-08-17

`settings.STATIC_VERSION` is the cache-buster on every CSS/JS URL;
`scripts/asset_manifest.json` records the sha256 of everything under `_static/`
against the version current when the files last changed, and
`scripts/prelaunch_check.py` fails when the two disagree so a redeploy can never
serve changed assets from cache on an unbumped version. **Who bumps it and
when:** anyone who changes, adds, renames or removes a file under `_static/`
bumps `STATIC_VERSION` (settings.py) *and* re-records the manifest with
`python scripts/prelaunch_check.py --stamp-assets`. Those are two manual steps,
and the second is the one that gets forgotten.

It was. On 2026-08-15 the logo rename bumped the version 14 → 15 and left the
manifest at 14; nothing runs the pre-launch guard routinely, so the stale stamp
sat hidden for two days and was found by accident on 2026-08-17 — the exact
"a check that goes stale silently and is then discovered by accident" failure
this repo names in CLAUDE.md. A stale stamp is not cosmetic: it compares the
files against a hash that describes no real generation of them, silently
disabling the guard for the *next* change. The fix on 2026-08-17 was a
RE-STAMP, not a further bump: version 15 had never been recorded at all, so
re-stamping recorded the current files (the logo rename plus that day's tab-
monitor JS rename) against the version already bumped for them.

**Rejected:** auto-stamping from a git hook — hooks are not committed, so they
would not travel with a copied template, and there is no static build step to
hang the stamp on. Also rejected: hashing `_static/` in `settings.py`'s boot
banner — the pre-launch script's docstring already refuses this, because
hashing every file on every server start is a deploy-time cost charged to every
page render.
**Enforced:** `scripts/tests/asset_manifest_test.py` runs the guard's OWN
`asset_problems()` in the routine suite (one implementation of "is it fresh?",
called by both the launch gate and the test) and pairs it with a positive
control that the guard fires on each stale shape; the launch gate itself is
`scripts/prelaunch_check.py` (`asset_problems`, `--stamp-assets`); the "when"
is stated at `settings.STATIC_VERSION` and in README's rebranding section.

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

**The stage value was changed even though stage values are frozen** (`common.py`
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
frozen-values note in `common.py`, the CODEBOOK stage table, and the test suites
(`dashboard_test`, `task_page_test`, `tab_monitor_detail_test`, `full_journey_test`,
`gated_flow_test`) which reference the class and stamp and go red on a half-done
rename.

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
scrolls. The monitor site-preview is regenerated from `experimenter_dashboard.py`
(`scripts/site_previews/`).

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
`URL_BASE` renamed consistently *inside* `experimenter_dashboard.py` while the
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
the `import experimenter_dashboard` trailer at the end of `outro/__init__.py` in a
`try/except` so a module-level error there (scenario 3), or a wholly missing
`URL_BASE` definition, would fail soft. **Rejected on Julian's rule:** a genuine
import-time error in the dashboard module is a code breakage the person launching
must see and fix, and softening it to a silent 404 is exactly the later-invisible
failure the rule forbids. The bare `import experimenter_dashboard` stays
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

## Participant tracking fields are named family-first, so an export groups by outcome — 2026-08-17

Decided by Julian. Every participant field about one outcome now shares that
outcome's prefix, so the columns sort into families instead of scattering: the
tab monitor's fields (`tab_monitor_disqualified`, `tab_monitor_focus_loss_count`,
`tab_monitor_focus_loss_count_outro`, `tab_monitor_focus_event_ids`,
`tab_monitor_focus_events`, `tab_monitor_focus_losses_missed_at_least`, joining
`tab_monitor_flag` / `tab_monitor_where` which already read this way);
comprehension's (`comprehension_failed_attempts`, `comprehension_reread_used`,
joining `comprehension_disqualified`); and the screen-out's `screenout_active`
(joining `screenout_cleared`, and the `screenout_cause` / `screenout_history`
keys already inside `participant_extra`). The shape is **family first, unit
last** — roughly `family_object_measure` — and it is written up in
`docs/conventions.md`.

The old names named the *measure* and lost the family: `focus_loss_count`,
`failed_attempts`, `screened_out` each sat alone in the export next to unrelated
columns, and a reader could not see at a glance that six columns were all one
instrument. The rename is deliberately **data-facing and complete** — a
half-renamed field is a `KeyError` at runtime, not an import error, because
`participant.vars` is a string-keyed store — so it reached every read and write
across the apps, the guards, the dashboard, the templates, the JS, the tests and
the docs, verified by grepping each old name to zero.

**`tab_monitor_disqualified` is the one rename that crosses the cover story.**
The field was `ai_safety_disqualified` because the participant-facing framing is
an "AI-safety" agreement; the data should name the *mechanism* (a tab-switch
monitor), so the column is `tab_monitor_*` like its siblings. The framing itself
did **not** move: the `AISafetyAgree` page, `_static/global/js/ai_safety_monitor.js`,
and every word a participant reads stay exactly as they were. Only the data name
changed. (Those two code symbols — the page class and the script — WERE later
renamed to `TabMonitorAgree` and `tab_monitor.js` on 2026-08-17, when the code and
docs were made to name the mechanism the tab monitor throughout; see that entry.
The participant copy still did not move then either.)

**This is a CONVENTION, not a rule, and there is deliberately no import-time or
boot-time check that enforces it** — a considered exception to this template's
habit of enforcing invariants at boot (`prelaunch_check.py`, the frozen-config
guard, the exit-code table). A study copied from this template may reasonably
want different field names for its own outcomes, and a boot check would turn that
ordinary choice into a failure to work around. The absence of a check is the
decision, not an oversight. **Rejected:** keeping the measure-first names (the
export does not group, and the tab-monitor family is invisible); renaming the
participant-facing AI-safety wording too (that is the study framing, not data);
adding a boot check that field names match the pattern (wrong for a copied
study). **Enforced:** nothing at boot, by design — held by `docs/conventions.md`,
this entry, and the field lists in `settings.PARTICIPANT_FIELDS` and `CODEBOOK.md`
being the single documented source. The suites that touch these fields
(`dashboard_test`, `task_page_test`, `identity_test`, `tab_monitor_detail_test`,
`full_journey_test`, `screenout_softwall_test`) go red on a half-done rename.

## The single oTree room was renamed `experiment` → `study`, so the URL reads `/room/study` — 2026-08-17

Decided by Julian. The participant-facing room URL is the one bit of plumbing a
participant actually sees (it goes in the Prolific study link and on printed lab
sheets), so its name should be neutral — not `experiment`, which reads as jargon,
and deliberately not anything that commits the URL to a lab or an online framing.
`study` is the right neutral word for both: it is what Prolific already calls the
thing, and a lab participant reading `/room/study` is not misled either. The
display name moved in step: `Experimental Session` → `Study Session`.

There is still exactly **ONE** room. This is the whole point — the same room
serves both study types (`prolific` and `lab`); the study type is one of the
three orthogonal controls resolved in `settings.py`, and it is not the room's job
to encode it. A second room for lab-vs-Prolific would duplicate the room-welcome
gate and the start.sh binding for a distinction the config already draws.

**Practical consequence — matters for a deployed study, not for this template:**
a room is bound to a name, so any session already bound to `/room/experiment`,
and any bookmarked or printed `/room/experiment` link, stops resolving the moment
the name changes. For this template there is no live session and no circulated
link, so the rename is free; for a study already in the field it would strand
participants and must not be done mid-run. **Rejected:** two rooms (defeats the
one-room-serves-both design); keeping `experiment` (leaks jargon into the one
URL a participant sees). **Enforced:** `settings.ROOMS`; the room tests bind to
`study` (`room_gate_test`, `identity_test`, `full_journey_test`,
`render_check`), so a half-done rename fails to bind a session and goes red.

## `monitoring.py` was renamed to `participant_tab_monitor.py` — the old name collided with the operator monitor — 2026-08-17

A pure rename, decided by Julian, recorded because the old name was actively
misleading and someone could later "fix" it back. The module holds the
PARTICIPANT-side tab-monitor page wiring — the `MonitoredPage` /
`OutroMonitoredPage` bases that arm each page against tab-switching, plus the
`assert_monitored_page_sequence` boot guard. But "monitoring" also names the
OPERATOR's job: `experimenter_dashboard.py` is the live session monitor the
experimenter watches, the previews call it "the experimenter monitor", and
`docs/` and `TODO.md` discuss "the monitor" meaning that screen. One word for
two unrelated things is the collapsed-distinction rule wearing a filename — a
reader chasing "the monitor" could not tell which was meant, and the two
concepts have nothing to do with each other. `participant_tab_monitor` says
exactly which monitor and for whom.

Only the MODULE name changed. The class names (`MonitoredPage`,
`OutroMonitoredPage`) and every function (`focus_live_method`,
`monitor_js_vars`, `assert_monitored_page_sequence`, …) are untouched — they
were never ambiguous, and renaming them would have churned the whole
tab-monitor contract for nothing. English prose about "monitoring" as a
concept, and every reference to the experimenter/operator monitor, was left
alone; only mentions that name the FILE or the import symbol were changed.
**Rejected:** renaming the classes too (needless blast radius); leaving the
name (the ambiguity is real and this template is copied, so it propagates).
**Enforced:** nothing structural — a rename needs none — but `git grep -i
monitoring` returns only concept/operator uses, and the apps still import (so
`participant_tab_monitor.assert_monitored_page_sequence` still fires at boot);
`scripts/tests/task_page_test.py` imports the module under its new name and
passes.

## The repo root is found by walking up to `settings.py`, never by counting directories — 2026-08-16

Decided by Julian, on the evidence of the restructure that same day.

**What it cost.** Nineteen files each answered "where is the project root?" by
counting levels up from their own location, in four different spellings —
`os.path.dirname(os.path.dirname(__file__))`, `dirname(_TESTS_DIR)`,
`Path(__file__).parent.parent`, `__file__.rsplit('/', 2)[0]`. Moving `tests/`
to `scripts/tests/` made **all nineteen wrong at once**: eighteen were silently
one level short, and the nineteenth — the `rsplit` spelling — hid from the sweep
that fixed the other eighteen and surfaced only as `ModuleNotFoundError: No
module named 'settings'` on the first full-suite run. One concept, nineteen
implementations, each encoding how deep it happened to sit.

**The fix is one implementation, in `scripts/tests/_repo.py`**, exporting
`REPO_ROOT` and putting it on `sys.path` on import. Every suite and every tool
in `scripts/` now imports it; no depth-to-root count survives anywhere.

**Why a MARKER WALK and not a corrected count.** A count is only right for the
layout it was written against, so fixing the number just re-arms the trap for
the next move. What actually *defines* this root is that `settings.py` sits in
it — oTree requires that, and `common.py` records that it can never move. The
helper walks up from `__file__` until it finds that marker: correct at any
depth, from any working directory, with nobody needing to remember a number. It
also resolves correctly from a **staged copy** of the repo, which is how the
HTTP suites run.

**The bootstrap is deliberately depth-free too.** A file puts its OWN directory
on `sys.path` (zero levels — stable under any move) and imports `_repo` from
there. The two tools outside `scripts/tests/` reference it as a child
(`prelaunch_check.py`) or a sibling (`scripts/site_previews/*`) — facts about
`scripts/` itself, not assumptions about how far the root is.

**Rejected:** correcting the nineteen counts and moving on. That is what was
done first, and it is why the nineteenth was found by a failing run rather than
by the sweep.
**Enforced:** by construction (there is nothing left to count) and by a mutation
check: with `scripts/tests/` moved one and then two levels deeper, both old
spellings resolve to the wrong directory (`scripts/deeper`, `scripts/`) while
the helper still returns the true root and the suites still pass. Re-run that
check after any future move: it is three lines and it is the only thing that
proves the helper solves the problem rather than re-encoding it.

## The screen-out exit says it is FINAL, because the code that frees the place forecloses the return — 2026-08-15

Decided by Julian, the same day as the per-population completion codes, and it
is the consequence of that decision rather than a separate one.

**What forced it.** The soft wall was designed around a re-decidable verdict: a
participant turned away at entry is HELD on `before.welcome`, the page's primary
ask is "switch to an accepted device and come back", and returning on an
accepted device before consent CLEARS the screen-out. The reversal recorded
above gave the screen-out its own completion code, chosen because an open
submission is limbo — it occupies a place and tells Prolific nothing. But a
completion code RETURNS the submission, and a returned submission can never be
retaken. **So for anybody who presses the exit, the route the page invites them
to take is gone.** Freeing the place was judged the better trade; being silent
about what it costs the participant was not.

**What the page now says**, in the `show_return_link` branch of
`before/screened_out.html`: *"Once you return it you cannot take part again,
even on an accepted device."* It replaces *"Once you do this you will not be
able to take part later"* — true, but on this page it reads as "not later
today", three inches under an invitation to come back on a different device.
The new sentence names the route it closes.

**What was deliberately NOT done.** It is one sentence in the page's existing
register, not a warning banner, and the control is untouched: it stays
`.exit-button`, never `.next-button`, because `global.js` Enter-clicks the first
`.next-button` on a page and an irreversible exit must not be one keystroke
away. The primary ask is still switching device, and the switch-device branch
still says *"Do not press the button below."*

**The honest statement of what survives.** The soft wall still exists and still
clears on an accepted device before consent — but only for somebody who has NOT
taken the exit. Those are now two different populations and the page has to be
readable by both.
**Enforced:** `scripts/tests/screenout_softwall_test.py` asserts the accepted-device
clause specifically (not merely that some permanence wording exists, which the
old sentence would also have satisfied), that the control carries
`.exit-button`, and that the way out is a real `<a href>` needing no script;
`scripts/tests/render_check.py` asserts the switch-device branch's "Do not press the
button below".

## The website's screen previews are GENERATED from the template, not drawn — 2026-08-15

Decided by Julian. The academic site shows several screens of the study (welcome
lab, consent lab, instructions, a decision screen, results lab; the experimenter
monitor was added 2026-08-16, see below). They used to be hand-written
one-off HTML snapshots, and by August they no longer looked anything like the
template.

**The failure is not that they were wrong; it is that nothing could tell.** A
snapshot has no relationship to the CSS it imitates, so when a shared component
moved, the snapshot went on rendering perfectly — just as a picture of an older
study. No error, no failing test, no visible symptom: the same silent-drift
shape as the client-side traps in `CLAUDE.md`. So the previews are now DERIVED —
`scripts/site_previews/build_site_previews.py` inlines `_static/global/css/` **verbatim**
(the stylesheets are never re-typed) and embeds the logos as data URIs, giving
one standalone file per screen with no external reference of any kind, because
they load in an iframe on a static site with no access to this repo.

**Source is tracked; output is not.** The script and
`scripts/site_previews/bodies/` are in the repo; the built files land in
gitignored `_ai/site_previews/`. A generator living in `_ai/` would die with the
container and the next person would hand-write another one-off — which is the
defect, restored.

**The screen is drawn on a fixed 1920x1080 canvas inside a nested `srcdoc`
frame**, scaled to the iframe by `calc(100vw / 1920px)` (a length over a length
is a number; no script, so it survives scripts being blocked). The frame is not
decoration: the template sizes itself in viewport units — the card is `88vh` and
`base.css` tightens its rhythm below 820px of height — so "what the template
looks like" is only defined at a given screen size, and rendered raw a small
iframe would be a different, clipped layout from a large one. Inside the nested
context those units resolve as they do for a participant on a 1080p display.

**Two honest departures, stated in the artefacts themselves** rather than only
in the hand-off message the files outlive: the decision screen is INVENTED (this
template ships no game screen — `main/game.html` is a placeholder — so it is
built only from real components, and must not be copied back into `main/`), and
the results screen is TRIMMED (the real page is the longest in the study and
genuinely scrolls inside its card; with the payoff table open it does not fit
16:9 at any size, so the greeting line is dropped and a short session shown).
**Enforced:** `scripts/site_previews/check_site_previews.py` — measured in headless Chromium
at four 16:9 sizes with JavaScript on and off: no external request, the canvas
viewport is the one composed for, no cut-off scroll region, the card fills, and
the lab screens name Prolific in no **rendered** text (asserted on `innerText`,
paired with a minimum-text assertion, because an absence check alone passes
against a blank page). Re-running after a CSS change is enforced by nothing —
it is a note in `CLAUDE.md`'s styling section and in `previews/SUMMARY.md`.

## The monitor preview is RENDERED BY THE DASHBOARD AND FROZEN, not hand-written — 2026-08-16

Requested by Julian: put the experimenter monitor on the academic site as a
sixth preview, same 1920x1080 canvas as the others.

**It could not be built like the other five, and the reason is worth keeping.**
Every participant preview is a hand-written body in
`scripts/site_previews/bodies/` composed of real shipped components, with the
real stylesheets inlined. The monitor has no body to write: `experimenter_dashboard.py`
serves a shell whose `<tbody>` says `Waiting for first data…`, and every row,
timeline marker, pill and quiz cell is built by that file's own `renderRow` /
`stateHTML` / `timelineHTML` in JavaScript from the poll's JSON. Hand-writing
those rows would have been **a second implementation of renderRow** — the
inverted collapsed-distinction rule in `CLAUDE.md`, and the drift would have
been invisible: a pill that changed shape in the dashboard would go on looking
right in the preview forever.

**So the build runs the real page.** `build_monitor` imports `_PAGE_HTML`
(stylesheet, script, header cells and step list all already resolved from
`STEP_LABELS`), inlines base.css in place of the `<link>`, stubs `fetch` to
return the invented session in `scripts/site_previews/monitor_session.py`, loads
it in headless Chromium, waits for the poll to paint, and **freezes the DOM with
every `<script>` stripped**. The output is markup the dashboard itself produced,
needing no server and no JavaScript — which is what earns it the same
scripts-disabled guarantee the other five have for free. The cost, stated: this
one screen makes the generator depend on Playwright at build time (the five
participant screens still build on the standard library alone).

**It is a LAB session, and that is why it shows no "ended early" rows.** All
four terminal states need a module `RECRUITMENT_PROFILES['lab']` switches off —
`telemetry_device_capture` (📵 screened out), `explicit_consent` (✋ declined), `quiz_comprehension_dq`
(❌), `tab_monitor` (👀) — so a real lab monitor never shows one. Putting them on
anyway would repeat the exact error that once shipped a consent preview with a
radio button no lab participant has ever seen. The built file says this in its
own header, because an absence on a picture reads as a missing feature.

**The data is invented and the file is public**: seat numbers, no Prolific IDs
(a Prolific row's label IS the platform ID), no completion codes, no contact or
bank details — the screen has no column for any of those.

**Enforced:** `check_site_previews.py` asserts the frozen page has the expected
row count (imported from the fixture, not typed) and at least one of each mark
the fixture exists to demonstrate — the timeline markers, the done tick, green
finished rows, amber stalled rows, dimmed not-arrived rows, all four quiz-cell
states, the earnings and live-timer pills, the Non-SEPA pill, the code fallback
and the averages strip. Without that, the way this preview fails is a freeze
caught before the paint: an empty or half-drawn table, which trips no geometry
check and is indistinguishable from a working one at thumbnail size.

**Known and accepted: it is not readable at grid-thumbnail size.** Measured
2026-08-16, apparent text in a two-up 590px tile is 3.3–5.7px; at a 1280px tile
the smallest labels are 7.3px. The screen reads as *shape* — a session table
with colour-coded rows — rather than as data at anything below full size. It is
the one preview whose value IS the data, so it wants a full-width tile or a
link to the full-size render; that is a website decision, left to Julian.

## One canvas for every preview, and the empty space on the short screens is accepted — 2026-08-16

Decided by Julian, reversing a change made the day before. `consent_lab.html`
had been moved to a **1152x648** canvas while the other screens stayed on
1920x1080. The reason was real: the shipped lab consent copy is genuinely short
(242px of content against ~700px for an instructions step) and floated in a
white void, and because `base.css` caps type at 19px from roughly 800px of width
upward, a smaller canvas shrinks the 88vh card while the text stays put — so the
copy fills more of it.

**What that missed is that the screens are shown side by side.** A tile scales
its canvas by `tile_width / canvas_width`, so the smaller canvas was scaled UP
1920/1152 = **1.67x** more than its neighbours: the same tile size, half again
the apparent text size. Julian saw it in the grid and chose the void. So the
canvas is now ONE constant for every screen, and **the empty space on the short
screens is the accepted outcome** — the shipped consent page really is that
short, and consistent scale across the grid matters more than a filled frame.

**The rejected alternative is the important half:** do *not* pad or lengthen the
consent copy to fill the frame. This preview goes on the website as what the
template produces, so it carries the literal shipped copy — a fuller consent
page here would be a picture of a study nobody ran, and a disclaimer in a file
header is invisible to somebody looking at the picture. (Same reasoning as the
INVENTED/TRIMMED notes on the entry above; those two departures are stated on
the artefacts because they could not be avoided. This one can be, so it is.)

**Why a constant and not a table of overrides that happen to agree:** the
uniformity *is* the decision, so it is expressed as something that cannot vary.
`check_site_previews.py` **imports** the constant rather than restating it —
one fact, one place, per `CLAUDE.md`'s two-implementations rule.

**Enforced:** `scripts/site_previews/check_site_previews.py` now also measures
the scale factor each tile applies and fails if the screens disagree by more
than 0.005. No per-screen assertion could catch this — every screen filled its
own tile perfectly on either canvas; the fault existed only *between* them.
Measured 2026-08-16 at four 16:9 sizes: all five screens report canvas
1920x1080 and identical scales (1.000 / 0.667 / 0.500 / 0.375), and the consent
screen renders complete with overflow +0 and its card inside the canvas.

## Every ending population gets its own completion code — 2026-08-15

Decided by Julian. Five endings, five codes, one per population:

| key | population | Prolific action |
|---|---|---|
| `prolific_cc_code` | completed | **auto-approve** |
| `prolific_noconsent_code` | declined consent | request return |
| `prolific_dq_quiz_code` | comprehension DQ | request return |
| `prolific_dq_tab_code` | tab-monitor DQ | request return |
| `prolific_device_code` | device screen-out | request return |

**Why not one shared `DQ-` code, which is what this replaces.** A shared code
**collapses two populations irreversibly, on a system we do not own.** Once a
comprehension failure and a tab-monitor ejection have both submitted under one
code, Prolific's submission list cannot tell them apart and nothing downstream
recovers it — not an export, not a rerun, not a support ticket. This is the
collapsed-distinction rule applied to a third party: the usual version of that
rule costs a debugging session, and this version cannot be fixed at all, which
is why it had to be got right before a launch rather than after one.

**THIS REVERSES the codeless screen-out** recorded on 2026-08-12 (marked
SUPERSEDED above, with its reasoning preserved). That decision was right that a
completion code closes a submission and a returned submission cannot be retaken.
It was wrong that leaving the submission open was therefore kind: a bare
researcher URL leaves it in limbo, occupying a place, telling Prolific nothing.
A **REQUEST_RETURN** code is a different instrument — it prompts the participant
to return the submission, which frees the place. So the screened-out exit is now
`prolific_device_code` rendered as a full completion URL, and the
`prolific_screenout_return_url` setting is gone: a URL that embeds a code, plus
a code key, is one value in two places and they drift.

**Rejected:** keeping `prolific_screenout_return_url` alongside the new code as
an override. Two sources for one value is the defect this repo has spent the
week removing.

**THE HAZARD THE SPLIT CREATES, AND THE RULE THAT CLOSES IT** (bossman-52, same
day). Splitting the DQ code invents a failure mode that could not exist while one
code served both populations: **if the displayed reason text and the completion
code are derived independently, they can silently disagree** — a comprehension
failure reads the quiz explanation and carries the TAB code back to Prolific. No
error, normal-looking data, and the population distinction corrupted at exactly
the point it was created to exist, findable only by reconciling submissions by
hand. **So the message and the code must come from ONE read of the cause.**

Verified today, and it is the safe shape already: `outro.dq_cause` is the only
implementation (`outro/__init__.py:51`); `Ended.vars_for_template` passes
`dq_cause=dq_cause(player)` and `outro/Ended.html` branches on that variable;
`completion_link` does `cause = dq_cause(player)`. No template reads
`tab_monitor_disqualified` or `comprehension_disqualified` directly — checked
across every `.html` in the repo. Two calls to one deterministic function in one
request cannot disagree; two implementations could, which is why the invariant is
written on `dq_cause` itself. **The next reader will see two calls and want to
refactor one away — that is the thing not to do.**

**Enforced, and each part separately verified:**

- `settings.PROLIFIC_CODE_KEYS` is the ONE enumeration; `_prelaunch_problems`
  iterates it rather than keeping a copy, so a sixth ending cannot ship
  unguarded. **Mutation-tested key by key**: with the other four set to
  plausible real codes, leaving each one placeholder in turn is named by the
  check — and only that one (no false positives). The old three-key enumeration
  would have shipped the two new codes completely unguarded while reporting
  clean, which is the trap this template keeps meeting.
- The frozen-session audit needs no enumeration: it walks every key in the
  current config, so the new keys are covered the moment they exist.
- `scripts/tests/completion_codes_test.py` — **one browser-driven journey per ending**,
  each asserting it carries ITS OWN code and NOT the other four. 30 checks, all
  passing. The absence half is the point: a disqualified participant who can
  read the COMPLETED code out of page source can self-approve and be paid, so
  every path checks all four others, and the codes are injected per page rather
  than bundled into the template context.
- `scripts/tests/render_check.py` leg AD asserted the screen-out carried NO code; that
  expectation is now reversed to assert it carries the DEVICE code and none of
  the other four.
- Two test-construction faults were found and fixed while writing the above,
  both worth knowing because they would have produced false confidence: a walker
  using the default `python-requests` User-Agent is classified `unknown` and is
  SCREENED OUT by `prolific_allowed_devices=['computer']`, and setting a DQ flag on a
  participant still at the consent page does not put them on their ending. In
  both cases the code assertions passed against the wrong page until the journey
  itself was asserted.

## `participation_fee` ships 0, and a boot guard holds it there — 2026-08-14

Decided by Julian. oTree's built-in `participation_fee` is a SECOND payment
channel: it is not part of `participant.payoff`, it is added on top of it by
`Session._get_payoff_plus_participation_fee` (otree/models/session.py:242-248),
which feeds the admin Payments page (`otree/views/admin.py:274`,
`templates/otree/SessionPayments.html:46`) and the MTurk payment table. It does
NOT reach the CSV export — verified against 6.0.15, the participant column list
ends at `payoff` (`otree/export.py:76-96`) — so a fee is invisible in the data
and visible only where a human reads off what to pay, which is worse. This template keeps **one payment ledger** — the base is
`payment_show_up`, which `outro.compute_final_payoff` folds into `participant.payoff` with
the bonus, so the admin figure equals the amount actually owed. A non-zero fee
splits that across two numbers computed by different code in different places,
which is the condition the single-ledger decision exists to prevent.

**Why a guard and not just a zero in the config.** A zero in a config is a
convention, and an unenforced convention in a template drifts the first time
somebody copies it. `participation_fee` is a standard oTree knob that the
official docs and tutorials set; a researcher starting from this template will
meet it there and set it in good faith, with no error to say the payment record
has quietly split. This repo has already had one convention-only rule turn out to
be nothing (three documents calling oTree's `player.payoff` raise "enforcement"
when it fires inside a participant's request).

**Boot, never request time** — the `payoff_guard.py` precedent, and the reason is
the same: oTree has no migrations, so an upgrade under live sessions is how every
study built from this template is actually deployed, and a check that fires in a
request is a dead page for whoever is mid-study. `fee_guard.py` is called from
`before/__init__.py` beside the other two boot guards.

**THE KNOWN COST, ACCEPTED WITH EYES OPEN.** A study copied from this template
that already sets a `participation_fee` **will refuse to boot** until the money
is moved into the ledger (into `payment_show_up`, or into `outro`'s `earned`). A real cost
paid by a real person — and the trade is deliberate: the alternative is a study
that runs happily with a payment record that is wrong in a way nobody notices
until payout, when somebody is underpaid.

**What it does NOT catch — a boot SOURCE scan cannot see a running session.**
oTree's `SessionEditPropertiesForm` (otree/views/admin.py:212) exposes
`participation_fee` as an editable field on a LIVE session, and `form_valid`
(admin.py:255-261) writes it into `session.config`, a DATABASE COLUMN on the
session row (`Column(_PickleField)`, models/session.py:35). The value lives in
data, so **no restart will ever catch it** — the guard passes while the session
carries a fee. Verified against 6.0.15, and measured: the ledger stayed at
€10.00 while the Payments figure moved to €13.00.

**Policing that is deliberately out of scope** (Julian + the hosting review): an
operator editing a live session is an operator action and is trusted. A
dashboard warning was proposed, costed, and CANCELLED. What was required instead
is that it be visible rather than silently clean — and it already is, for free,
because `predeploy_check`'s frozen-config audit reads the session ROWS rather
than the source and reports it as a plain value difference (`frozen 3.00cu vs
current setting 0.0`, confirmed on a real edited session). Check the artifact,
not the recipe; this guard is the recipe half and must never be written up as
more than that.

**Rejected:** relying on `AUTO_TABULATE_PAYOFFS`-style enforcement from oTree
(there is none for this field), and a runtime check in `outro` (same dead-page
trade the payoff guard exists to avoid).

**Enforced:** `fee_guard.assert_participation_fee_is_zero()`, called at boot from
`before/__init__.py`. Two halves: the RESOLVED configs (`SESSION_CONFIG_DEFAULTS`
must carry an explicit 0; a per-config entry may omit the key but must not set a
fee) and an AST scan of app packages and shared root modules for
`participation_fee` written as anything but a literal 0 — assignment, attribute,
`config['participation_fee']`, a `dict(participation_fee=…)` keyword, or a dict
literal. The scanned file list comes from `payoff_guard.files_to_scan`, not a
second copy of the rule, so the two guards cannot disagree about which
directories are apps. Verified 2026-08-14: the template boots clean (15 files
scanned); a fee in the defaults, an absent key, and a per-config override each
refuse the boot; a config omitting the key inherits correctly; all seven source
shapes fire and a literal 0, a `0.00` keyword and a *read* of the key do not.
Proven end to end with `otree resetdb` — the shipped template exits 0, and with
`participation_fee=2.50` the boot fails with the guard's message.

## Tracked docs are for whoever runs a study; `_ai/` stays local and is marked as such — 2026-08-14

Decided by Julian, after the sweep for the entry below found that tracked
documentation pointed into gitignored `_ai/` about fifteen times — nine in
`DECISIONS.md`, five in `README.md`, one in `CLAUDE.md`. Nothing under `_ai/` is
tracked (`git ls-files _ai/` returns nothing), so **every one of those was a dead
link in a clone**, including the recipe `CLAUDE.md` sends every agent to before
running a render check. A template whose first-read files point at absent
documents teaches the copy to distrust its own instructions.

**The test applied** is not "is this useful?" and not even "does a copy need
it?", but **"does a person running a study need it?"**. That reframing is what
made the split easy: an audit of how the dashboard was built is scaffolding no
matter how good it is; a recipe for running the render check without root is
something a researcher needs on day one.

**Three files moved to a new tracked `docs/`**: `headless_chromium_recipe.md`
(eight tracked references, and without it a copy cannot run the measured render
checks this template calls the only evidence a layout change works),
`postgres_assumptions.md` (item 8 is a gap every copy inherits), and
`group_matching_reference.py` (`main/__init__.py` tells whoever implements group
matching to read it first). Two were written into `docs/`: a researcher-facing
`README.md` — the front door, in the terms somebody running a study thinks in
rather than the terms we built it in — and `hosting_a_prolific_study.md`.

**Everything else stayed in `_ai/` and every reference to it now carries `local
only — _ai/ is gitignored; not in a clone`**, in one style, so a reader can tell
a deliberate absence from a missing file at a glance. `_ai/render_check/` and
`_ai/dashboard_render/` were deliberately NOT marked: they are output directories
created by running the checks, not documents to read, and marking them would
teach the reader that the tool is broken.

**Why `docs/` rather than the repo root or `docs/skills_claude/`.** The root already
carries the six documents everybody is told to read; adding second-tier reference
beside them makes the first tier harder to see. `docs/skills_claude/` is method
material addressed to an agent working ON the template, which is a different
audience from a researcher running a study. `docs/README.md` states the rule for
what may be added, so the next person has a test rather than a habit.

**Also settled, same theme — what belongs in a template at all.** Two
double-clickable macOS launchers were sitting untracked in the tree, having been
deliberately removed from the repo once already (`eb026e3`, 2026-07-23).
`GitHub_sync.command` is Julian's own sync convenience: kept on disk, added to
`.gitignore` by name rather than as `*.command`, so a launcher that IS template
material would still have to be ignored on purpose.

## `Preview_Instructions.command` is tracked — deliberately reversing `eb026e3` — 2026-08-14

Decided by Julian. `eb026e3` ("Remove local macOS launcher scripts from the
template", 2026-07-23) removed both `.command` launchers as personal tooling.
That was right for the file it removed and wrong as a permanent rule, and the
distinction is what the reversal turns on: **the launcher `eb026e3` removed drove
a stale copy of the generator; a launcher that drives the MAINTAINED generator is
template material.**

The removed one ran `previews/generate_instructions_preview.py` — a copy frozen
on 2026-05-28 inside the gitignored `previews/` OUTPUT directory, eleven lines
behind `intro/generate_instructions_preview.py` and writing the same filenames.
Double-clicking it silently replaced current previews with three-month-old
output. Deleting that was correct.

**What makes the rebuilt one travel:** every study copied from this template has
instructions, and the maintained generator is the only way to read them without
running a session — but it needs a command line, and *"I do not want to open a
terminal"* is a real requirement, not a preference to be argued with. A copied
study should not lose the no-terminal route. So the launcher is tracked, points
at `intro/`, resolves everything from its own `$SCRIPT_DIR` (no path from this
checkout), passes `--config .preview_state.json` when saved settings exist (the
generator otherwise opens a form and waits, which from a double-click looks like
a hang), and opens the interactive preview when it finishes.

**One thing it does NOT do, learned by measurement:** treat the generator's exit
code as the verdict. With no browser binary installed the generator writes both
HTML files correctly and still exits 1, because the PDF step failed. The launcher
therefore decides on WHAT EXISTS and reports the exit code only when nothing was
produced — otherwise it would tell somebody their previews were broken while they
sat there complete. (Found by dry-running it; the first draft had the bug.)

**Enforced:** nothing automated. The launcher carries a comment saying never to
point it into `previews/`, and the stale copy that caused the original problem is
still sitting in that gitignored directory for whoever looks there first.

**Enforced:** nothing automated — no check fails when a tracked file gains a link
into `_ai/`. `docs/README.md` carries the rule and the marking convention; that
is all that holds it.

## The predeploy check decides which database it touches in ONE place, and proves it before anything destructive — 2026-08-14

Found by the same sweep as the entry below, and fixed on Julian's instruction
before either was committed. `scripts/predeploy_check.sh` ran its degraded-mode
`otree resetdb --noinput` in a subshell that **inherited the environment**; the
line pinning the run to its own staged sqlite copy — `export
DATABASE_URL="sqlite:///$WORKDIR/app/db.sqlite3"` — sat *after* that branch. So
an operator with a live `DATABASE_URL=postgres://…` exported (the normal state of
a deploy shell) running the documented no-argument check had their live database
dropped and recreated, after which the run proceeded happily against the staged
sqlite file and **reported PASS**. Verified end to end before the fix: a seeded
session row went 1 → 0 and the gate exited 0 with `RESULT: PASS (DEGRADED)`.

**The severity is about where it sat, not just what it did.** This is the tool
whose entire purpose is preventing data loss before a deploy, it is destructive
in its *documented* mode, and the database it destroys is by construction the one
you are about to deploy to. The only thing standing between a Postgres operator
and this was whether `psycopg2` was importable — and a working Postgres
deployment necessarily has it.

**Root cause is the mirrored rule in CLAUDE.md — one concept, two
implementations.** "Which database does this check touch?" was answered twice:
by the shell (inherits ambient env, pins later) and by the helper, which never
set `DATABASE_URL` at all and relied on `os.chdir` — a lever that works *for
sqlite only*, since oTree ignores the path in a sqlite `DATABASE_URL` but honours
a Postgres one completely. Against an inherited Postgres URL the chdir lever is
inert. Two deciders, and their disagreement was destructive rather than merely
confusing.

**The decision:** one place decides, and the proof covers every decider.
`pin_database_url()` forces the URL onto the staged copy and **refuses** a
disagreeing one (a non-sqlite URL, or a sqlite URL naming a different file)
instead of overriding it silently — silence would hide an operator who believes
they are exercising their Postgres. `assert_engine_on()` then interrogates the
engine oTree actually built and hard-fails unless it resolves to the staged file:
declaration, then measurement, because for sqlite the environment variable is
only a statement of intent and the cwd is what binds. The shell pins immediately
after staging, **before any branch can run a destructive command**, and calls the
**same** proof through `predeploy_check.py --assert-engine-on` before its
`resetdb`. The helper pins and proves for itself too, because it is documented as
directly runnable.

**Rejected:** just moving the export above the branch. It fixes this instance and
leaves the second decider in the helper, and it leaves the proof covering only
one of the two — which is how this survived in the first place. A proof that
covers one decider is an invitation for the other to grow back at the next edit.

**Enforced:** `predeploy_check.py --assert-engine-on`, called by the shell before
its destructive step and by `check_boot` for itself — one function, two callers,
so the two processes cannot be proved against different rules. Demonstrated on
2026-08-14 against a real PostgreSQL 16: the pre-fix scenario destroyed a seeded
row and passed; post-fix the identical run leaves the row intact (`MUSTSURVIVE`,
22 tables) and still passes on its staged copy. The regression this is meant to
survive was simulated directly — the pin deleted, the proof left in place — and
the proof caught it: exit 2, `nothing was written`, live data untouched. Both
sqlite paths re-verified unchanged (upgrade mode with the `_ai/live_data/` (local only — `_ai/` is gitignored; not in a clone)
fixture: boot, schema, resume, fresh, no-JS and log-scan all pass, with 2b's
pre-existing frozen-config failure unaffected; degraded mode: PASS).

## Boot initialisation is decided by inspecting the database, not by a sqlite file — 2026-08-14

Found by the hosting review, which caught the same defect in `exp_pilots`'
`start.sh` and asked whether this template shared it. It did. The container's
CMD initialised on `[ "${RESET_DB:-0}" = "1" ] || [ ! -f /app/data/db.sqlite3 ]`
— **file existence as a proxy for "is this database new?"**. The proxy is only
equivalent to the real question when the database IS that file. Point
`DATABASE_URL` at a managed Postgres and the sqlite file never exists, so the
condition is true on every boot and `otree resetdb` runs against the Postgres on
every container restart. `otree/cli/resetdb.py` does `old_meta.reflect(bind);
old_meta.drop_all(bind)` — it drops whatever it finds, on whatever backend — so
that is a silent total wipe with no error in the log, discovered after a
session. On Railway/Heroku/Fly (ephemeral container filesystem, no volume) it
recurs on **every** restart; with a `-v <study>-db:/app/data` volume it fires on
the first boot and is then masked by an accident (below), which is worse, not
better, because the exposure comes back the day the volume is recreated.

**The proxy was not sound for sqlite either**, which is the part that makes
"just fix the condition" the wrong fix. Importing `otree.database` executes
`sqlite_disk_conn = sqlite3.connect('db.sqlite3')` at module scope —
unconditionally, *including when `DATABASE_URL` points at Postgres* — which
creates a **zero-byte file**. A zero-byte `db.sqlite3` is a file that exists and
a database that was never initialised; `-f` cannot tell those apart, so the old
guard would also skip initialisation and leave the server running against a
table-less database.

**The decision:** the guard asks the question it actually means — *does the
database oTree will connect to already contain oTree's tables?* — via
`scripts/db_state.py`, which uses **oTree's own engine** (`otree.database.engine`,
built from `DATABASE_URL` by the same code path the server uses, so it cannot
inspect a different database from the one the study runs on) and **oTree's own
table names** (`AnyModel.metadata`, not a hardcoded `otree_participant`, which
would be a second implementation of "what oTree's tables are called" and would
drift the day oTree renames one). Backend-agnostic by construction: the same
question has the same meaning on sqlite, Postgres and anything else SQLAlchemy
reaches. `RESET_DB=1` is unchanged and does not consult the probe.

**Four situations kept apart** (the collapsed-distinction rule; collapsing any
pair of them is how this class of bug destroys data): *no tables at all* →
initialise; *oTree's tables present* → keep; *tables present but none of them
oTree's* → refuse (resetdb would `drop_all()` somebody else's schema, or an
oTree database whose version named its tables differently); *cannot determine* —
unreachable database, missing driver, empty model registry, in-memory engine →
refuse. "I cannot see the database" is not "the database is empty": an
unreachable Postgres must never read as brand new. Both refusals stop the boot
non-zero and loudly. That bias is deliberate — a container that refuses to start
is a page in the log; a container that wipes a live study is a lost session.

**Rejected:** patching the condition to also test for a Postgres URL. It keeps
file existence as the sqlite answer (still wrong, see the zero-byte case) and
makes the guard a list of backends to remember, which is the shape that produced
this bug.

**WHAT THE GUARD IS ACTUALLY FOR — and it is not creating tables.** Relayed from
the `exp_pilots` fix (79d49c2) and verified here against otree 6.0.15: oTree
builds its own schema on every start. `otree.main.setup()` calls `init_orm()`,
which ends in `AnyModel.metadata.create_all(engine)` (otree/database.py:369), and
`create_all` is checkfirst-by-default — it adds missing tables and never drops or
alters an existing one. So `resetdb`-on-fresh is belt and braces; the server
would have built the schema anyway. The guard's only real job is NEGATIVE: to
stop `resetdb` running against a database that has data in it. That reframing is
load-bearing for the failure path — refusing to boot forfeits nothing the server
needed, because an unreachable database would have failed `create_all` too.

**Converged with the `exp_pilots` fix (79d49c2), which was written independently
against the same defect.** Three of its findings were taken:

- **The driver is part of this fix, not a follow-up.** `pip install otree` ships
  no Postgres driver, so without `psycopg2-binary` in the image the probe cannot
  connect, lands in the unanswerable branch and refuses to boot — a guard whose
  safe direction is triggered by our own missing dependency would fail 100% of
  Postgres deploys while looking like a database problem. Pinned to 2.9.12 to
  match. This had been written down as a "record, decide later" item; that was
  wrong, and the correction came from comparing against the other fix.
- **Waiting is not weakening.** A managed Postgres is very often not accepting
  connections at container start. The probe now retries a non-answering database
  (`DB_WAIT_ATTEMPTS` x `DB_WAIT_SECONDS`, default 30 x 2s) before calling it
  unanswerable, so refusal is the verdict after waiting rather than the first
  answer. Without it the guard converts every normal cold start into a failed
  deploy — which is how a safety mechanism gets switched off for being annoying.
  Only "did not answer" is retried; a missing driver, an empty registry, an
  in-memory engine or a foreign schema are answers already and fail at once
  (measured: 0s vs the full wait).
- **No password ever reaches a log.** Fatal banners render the URL through
  `repr(engine.url)` (SQLAlchemy 1.3 masks the password there; `str()` does not)
  plus a regex scrub of any `scheme://user:pw@` in driver messages and a literal
  replacement of the password read from `DATABASE_URL`.

Their fourth point — resolve the URL exactly as oTree does (`os.getenv` with the
`sqlite:///db.sqlite3` fallback, forcing sqlite paths back to the relative
`db.sqlite3` because oTree ignores the path) — **is satisfied here by
construction rather than by copying the rule**: this probe does not resolve a URL
at all, it imports `otree.database.engine`, the very object the server uses. A
second resolution is exactly the one-concept-two-implementations shape that would
drift, and with the same destructive consequence (bless one database, wipe
another). Demonstrated: with an initialised database in the CWD and
`DATABASE_URL` naming a *different, empty* sqlite file, the probe answers
`already-initialised` — it follows the CWD file, precisely as oTree does. The
corollary is that the probe must run with the server's CWD, which the CMD does.

**Also taken:** under `RESET_DB=1` the sqlite file is deleted only when the
backend is actually sqlite (`case "${DATABASE_URL:-sqlite}"`), since on a managed
database `resetdb` does its own dropping and deleting a stray file there would be
theatre. `RESET_DB=1` remains the only deliberate wipe path on any backend.

**Enforced:** nothing in CI — say so plainly. `scripts/predeploy_check.sh` is
sqlite-only by design (documented in its header: oTree ignores the path in a
sqlite `DATABASE_URL`, so isolation is achieved by CWD), no suite runs against
Postgres, and none of them boot the container, so **no automated check in this
repo would have caught the original defect or would catch its return.** What
exists instead is a manual proof, run on 2026-08-14 against a real PostgreSQL 16
(installed without root — recipe in the agent memory note `postgres-without-root`)
and a real sqlite database, driving the **actual CMD text extracted from the
Dockerfile** rather than a paraphrase:

| case | sqlite | Postgres |
|---|---|---|
| fresh/empty database → initialise | yes | yes (22 tables) |
| existing database → keep, data intact across restarts | yes | yes (3 restarts) |
| **the old condition**, same sequence | n/a | **row gone after 1 restart** |
| zero-byte `db.sqlite3` → initialise | yes | n/a |
| **dropped column preserved, NOT restored** | yes | yes |
| late-starting database (down at boot, up 14s later) | n/a | **waited 14s, then kept the data** |
| unreachable database → refuse, exit 1, nothing modified | n/a | yes (after the wait) |
| missing driver → refuse **immediately** (0s, no pointless retries) | n/a | yes |
| foreign (non-oTree) schema → refuse, schema untouched | n/a | yes |
| `RESET_DB=1` → full rebuild (dropped column comes back) | yes | yes |
| sqlite URL naming another file → follows CWD, as oTree does | yes | n/a |

The dropped-column case is the sharpest of these: a column removed by hand stays
removed after boot, which is direct evidence that no `resetdb` ran — and it still
boots, because oTree's own `create_all` does not repair columns either.

Two things remain UNVERIFIED and should not be read as covered: **Docker itself
was never run** (no image build, no real container boot, no `COPY` of
`scripts/db_state.py` — the CMD body was extracted and executed with `/app`
rewritten, and syntax-checked as `sh -c "bash -c '…'"`), and **no managed
provider was exercised** — the Postgres was local TCP with trust auth, so TLS
(`sslmode=require`) and connection-pooler behaviour are reasoned about, not
tested. The pooler case is the one most likely to behave differently, and it
fails toward refusal rather than toward wiping.

The Dockerfile comment states what the guard asks, why file existence was wrong,
and why the failure path refuses rather than initialises — because the condition
looks redundant next to a `-f` test and invites being simplified back, and
because a refusal invites being made permissive.

## A Postgres deployment has NO upgrade-path check — recorded as an open gap, not closed — 2026-08-14

Recorded on Julian's instruction while fixing the two Postgres data-loss defects
above, because **this is the gap behind both of them** and every study copied
from this template inherits it.

Everything this template has for "will the running study survive being upgraded
to this code?" runs on sqlite, and only on sqlite. `scripts/predeploy_check.sh`
pins itself to a staged **sqlite** file, validates its input by the sqlite magic
header, and proves its isolation with `PRAGMA database_list` — all sqlite-only,
all by design and documented in its header. The documented way to obtain its
input is `docker cp <container>:/app/data/db.sqlite3`, a file that does not exist
under Postgres. Every suite is likewise sqlite (`scripts/tests/otree_inprocess.py`,
`scripts/tests/render_check.py`), as is the `_ai/live_data/` fixture (local only — `_ai/` is gitignored; not in a clone) that makes upgrade
mode meaningful.

**So the one backend a hosted study actually uses is the one with no coverage at
all.** A study on Railway/Heroku/Fly runs on Postgres; its operator runs the
pre-deploy gate the documented way, lands in degraded mode — honest (it shouts
`THE UPGRADE PATH WAS NOT TESTED`) but empty — and deploys onto live participants
with the fresh-install checks only. The two outages this gate exists for (a
participant-vars key old participants never had; a session config frozen before a
parameter existed) are precisely what a fresh database cannot reproduce.

It is also **why both defects above survived**: each was destructive only against
Postgres, and no test in this repo has ever opened a Postgres connection, so
nothing went red.

**Closing it, in order:** (1) a **container boot test** — boot the image against
a Postgres URL, write a row, restart, assert the row survives. Smallest, highest
value, and the direct regression test for the defect that started this; it needs
Docker. (2) a **Postgres fixture** for the suites — a real server, which needs no
root (recipe: the agent memory note `postgres-without-root`), plus the driver,
now in the image. (3) a **Postgres mode for `predeploy_check.sh`**: the isolation
model changes shape rather than gaining a branch — `pg_dump` the live database
and restore into a **throwaway database**, the live-refusal guard becomes "the
target must not be the live database name", and `PRAGMA database_list` becomes
`SELECT current_database()`. That proof is now behind one function
(`assert_engine_on`), so it is one place to extend, not two.

**Enforced: NOTHING.** No test, no gate, no banner tells an operator that their
Postgres deployment is being upgraded without an upgrade check. The README's
Docker section now says so in words, which is the only thing standing here.
Working detail: `docs/postgres_assumptions.md`.

## `DB_NAME` in settings.py does not select Postgres — oTree 6 never reads `DATABASES` — 2026-08-14

`settings.py` sets `DATABASES = {...postgresql...}` when `DB_NAME` is in the
environment and a sqlite `DATABASES` otherwise. **oTree 6 never reads
`DATABASES`** — verified: zero references to the name anywhere in the installed
`otree` package (6.0.15). oTree 5 dropped Django; the backend is chosen solely by
`DATABASE_URL`. The block is a Django-era leftover that reads like a working
control, so somebody setting `DB_NAME`/`DB_USER`/`DB_HOST` expecting Postgres
silently gets sqlite. Same defect class as the two fixed above — a control whose
apparent meaning and real effect differ — but not destructive, so it is recorded
rather than changed in a hurry.

**Options for whoever settles it:** delete the block (simplest, matches how oTree
works); or keep the `DB_*` names as a convenience and have them **construct**
`DATABASE_URL` when it is not already set, so the documented knobs actually do
something. Either way the block needs a comment saying `DATABASES` is not
consulted, or the next reader will "restore" it.

**Enforced:** nothing. No check compares the configured backend against the one
actually in use. Detail: `docs/postgres_assumptions.md` item 4.

## The README documents that inert `DB_NAME` mechanism as if it worked — 2026-08-14

`README.md` ("Running the template") says Postgres is not needed *unless you set
`DB_NAME`*, and lists `DB_*` among the values to set via env in production. Both
halves teach the mechanism the entry above shows is dead. Recorded separately
because it is a second place to change, and changing the code without the prose
leaves the same wrong instruction in the file people actually read.

**Enforced:** nothing — prose is not tested. Fix it in the same change as the
entry above, whichever way that goes.

## A wrong-backend engine is reported as "the app failed to boot" — 2026-08-14

`check_boot` in `scripts/predeploy_check.py` wraps the in-process import and the
engine proof in one `try/except Exception` and reports any failure as *"the app
failed to boot against the database"*. A wrong **backend** is not a broken build,
and reading it as one sends the next person to debug their app instead of their
environment. The shared-`except` shape this codebase warns about, in its mild
form: nothing is destroyed, only misattributed.

**Partly addressed as a side effect of the predeploy fix:** `assert_engine_on()`
now names the backend explicitly ("oTree built a `postgresql` engine, not
sqlite") and `check_boot` re-raises `SystemExit`, so that case reports itself
accurately. What remains is the general shape — every other import-time failure
still collapses into one message.

**Enforced:** nothing. Worth splitting if that file is being edited anyway; not
worth a change on its own. Detail: `docs/postgres_assumptions.md` item 9.

## Ended.html carries no screen-out copy — deleted as unreachable, with the unreachability enforced — 2026-08-14

Decided by Julian (before-review N4), choosing deletion over the reviewer's
keep-both recommendation. The `reason == 'screened_out'` block in
`outro/Ended.html` — the four device-cause branches and the screened-out
title — duplicated `before/screened_out.html`'s live copy for a participant
who can never arrive: the soft wall holds a screened-out participant at the
entry page's own index precisely because oTree only moves forward, so walking
them to an outro ending would make the verdict un-liftable. A duplicate that
never renders can only drift from the copy that does.

**The deletion was not made on the unreachability claim alone.** This repo
has been bitten by untested claims (the 2026-08-13 monitor-coverage entry
below: four documents asserting something untrue), so the claim was made
ENFORCED in the same change: `scripts/tests/screenout_softwall_test.py` scenario 9
hammers a screened-out participant with forced submits and a direct
`/outro/Ended/` URL and requires every response to re-serve the held page.
If routing ever changes, the test goes red before a participant reads the
wrong page. Two second-line defences remain for that hypothetical future
gate: Ended's neutral else-fallback ("The study has ended for you") says
nothing false, and the shared footer include still picks the CODELESS exit
for `reason == 'screened_out'`, so their submission would stay open.

**What deliberately stayed:** `outro.was_screened_out` — a DIFFERENT
mechanism that looks related and is not. It is what keeps a screened-out
participant out of `is_completer`, so no future gate can hand them a
completion code; deleting it with the template branch would have been the
over-pull this entry exists to warn against. `Ended.vars_for_template`'s
`common.screenout_vars` spread also stays: the footer reads
`prolific_screenout_return_url` from it.

**Record check, done with the change:** no document claims the screen-out
exit code is written when the participant clicks the return link — it is
written at DECISION time (`common.set_screened_out`: a closed tab still
exports as screened out, not abandoned), and `set_screened_out`'s docstring,
the softwall test header and the footer include all state it correctly.

**Enforced:** `scripts/tests/screenout_softwall_test.py` scenario 9 (the deletion
guard); the header note in `outro/Ended.html` points at it.

## Explicit consent is its own flag (`explicit_consent`), split from `prolific_completion_redirects` — 2026-08-14

Decided by Julian, from the before-app review. Whether the consent page asks
an explicit question (required unticked radio, no-consent routed to exit code
-1) or states that continuing is consent was decided by
`prolific_completion_redirects` — which, read literally, said "if we hold a
completion code, consent must be an affirmative act". **Whether consent is
EXPLICIT is an ethics decision; holding a completion code is platform
plumbing.** The conflation is the same defect class as the screened-out
dead end of 2026-08-13 (one flag doing a second, unrelated job), caught this
time before it cost a participant.

The split: `explicit_consent` defaults **ON** in `SESSION_CONFIG_DEFAULTS` —
the one shipped flag that is deliberately not off-by-default, because a study
should have to OPT OUT of asking for consent — and the **lab profile resolves
it OFF** (implicit consent by continuing; there is an experimenter in the
room). That preserves the pre-split behaviour of both shipped profiles
exactly: prolific keeps the radio, the lab keeps implicit consent. The
prolific profile deliberately does NOT list the key (it falls through to the
baseline ON): explicit consent is the default, not a Prolific feature.

The audit for a second conflation found none: every other use of
`prolific_completion_redirects` (the outro return footers, the Ended/Results
"Back to Prolific" branches, the dashboard's awaiting-return pill, the
return-click stamp) is genuinely about the completion-code redirect. One
consequence is newly constructable and deliberate: `explicit_consent` on with
redirects off produces a decliner whose ending has no return button —
`outro/Ended.html`'s neutral fallback covers them.

A frozen session predating the flag reads it as OFF (`common.flag`'s
missing-module rule) — the radio would silently vanish for that session's
future entrants, which is why the predeploy frozen-config audit reporting the
missing key matters: the remedy is to recreate the session.

**Rejected:** deciding at runtime from `recruitment` (the consent page asking
"am I a lab study?") — profiles resolve to explicit config values at import
precisely so behaviour is never re-derived silently; and keeping the old
wiring with a comment — the rename made the misreading legible, a comment
would only apologise for it.

**Enforced:** `scripts/tests/explicit_consent_test.py` (radio present+required when
on, absent with implicit copy when off, in BOTH recruitment profiles — flag
decides mechanics, recruitment decides copy — plus the resolved values on
both shipped configs); `explicit_consent` in `scripts/tests/frozen_config_test.py`'s
STRIPPED list pins the frozen-session behaviour.

## One short-viewport rhythm for every `.stacked-form` option row — a leak ratified into the rule — 2026-08-14

The consent-fold block (`@media (max-height: 820px)` in base.css, 2026-08-13)
tightened option rows via `.stacked-form .mc-option / .form-check` while its
comment claimed consent-only scope — but the quiz and demographics stack their
options in `.stacked-form` directly (the "different wrapper" the comment cited
never existed), so both pages were retuned from day one. **Discovered through
a geometry-baseline diff, not by design** — the fold work never ran
`--update-baseline`, so the first `--diff` afterwards surfaced ~130 moved
measurements (quiz card −125px, demographics −59px at short viewports), which
were first mis-attributed to environment drift and then pinned by a CSSOM
toggle: deleting the one media rule sprang the rows back to the baseline's
values on both pages, while a rule audit proved the concurrently-added
tabmonitor.css matches nothing there. The log records the route because that
is how it actually happened.
**Julian's ruling: make the rule the intent.** One component, one rule,
everywhere — a component that tightens on short viewports on one page but not
another is the same mixing-and-matching the logo-strip principle forbids. The
shipped behaviour stands, the adopted baseline stands, and the earlier
"one page's shortfall must not silently retune every choice" scoping intent
is ABANDONED, on purpose, with the reversal recorded at the block itself.
Judged on screenshots before ratifying, not on the principle alone: rows stay
over the 44px touch floor, nothing cramped, quiz and demographics
neutral-to-better on short screens.
**Rejected:** re-scoping the rule to the consent group (a dedicated class) —
it would honour the written intent by making the same control obey two
rhythms, which is the defect class, not the fix.
**Enforced:** the rewritten comment at the block (base.css) states the
everywhere-rule and forbids re-scoping without a new decision;
`scripts/tests/geometry_baseline.json` pins the shared rhythm at all three viewports;
the affordance and touch-target legs of `scripts/tests/render_check.py` assert the
pages still behave.

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
inconsistent: `common._apply_focus_loss`, `participant_tab_monitor.py`, the top of
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

## One guard policy for a config-read money value: fail loudly — 2026-08-13

Whole-app review B4, decided by Julian. `payment_show_up` / `payment_quiz_bonus` were read two
ways: the promise side (consent, instructions) guarded with `or 0`, the
payment side (`outro.compute_final_payoff`) bare. For a config holding None
that split is the worst arrangement — the participant is silently promised
€0.00 and the crash still happens, at the payment page. The `or 0` guards are
gone; every side now reads bare and fails loudly at the first page that
renders the value. **This has a behavioural implication, stated plainly
because the decision was taken assuming it did not: a degenerate config that
used to render a silent €0.00 promise now errors instead.** Loud is chosen
because silently promising somebody nothing is the worse outcome — the same
reasoning `compute_final_payoff` already carried ("failing loudly beats
recording the wrong number quietly"). No shipped or frozen config is
affected: `common.cfg` falls back to the shipped numeric default for a
MISSING key; only an explicit None ever hit either path.
**Enforced:** nothing structural — the policy is one line of comment at each
former guard site (`before.welcome.vars_for_template`,
`intro.instructions_context`), and the loudness is the absence of the guard.

## The two-accessor question is CLOSED across the flow — 2026-08-13

Chased across three separate reviews (before N3 → whole-app B2 → this
implementation), and recorded here so nobody re-opens it: **every reader of
the study type now goes through `common.is_lab` / `common.is_prolific` /
`common.recruitment`.** The last holdout was `before.startpage.is_displayed`'s
raw `config.get('recruitment') == 'lab'`, which on a session frozen before
the key existed evaluated `None == 'lab'` → False — silently dropping the lab
hold screen while the consent page one index later rendered lab copy through
`is_lab`'s fallback: one participant, one question, two answers, one page
apart. Behaviour change is confined to that frozen-config case (the hold
screen now appears, which is what the neighbouring pages already assumed);
blast radius today is zero — no live sessions, the same window the
`prolific_` rename used.
**Enforced:** `grep "config.get('recruitment')"` returns nothing outside
`common.py`; `scripts/tests/copy_routing_test.py` pins the single-implementation rule
the accessor carries.

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
`experimenter_dashboard.note_admin_tab_problems` applies the identity.py
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

## One payment ledger: per-round `player.payoff` is not used, `participant.payoff` is written once from `earned` — 2026-08-13

Review item J1 (Julian; sub-decision also his). The underlying conflation:
oTree automatically sums `player.payoff` across rounds into
`participant.payoff`, but this template pays only `payment_num_rewarded` randomly
selected rounds — the per-round result and the amount paid are different
things, and the auto-sum is a total nobody is paid. So the game records each
round in its own `main.Player.round_payoff`; the template pays from
`participant.payoff_vector`; and oTree's `participant.payoff` gets exactly ONE
entry — `earned` (less `participation_fee`, de-converted when `USE_POINTS` is
on), written when the results page computes payment — so the admin Payments
page shows the figure the participant was shown, and there is nothing left to
disagree. `AUTO_TABULATE_PAYOFFS=False` also removes oTree's per-round payoff
column from the export (deliberately absent, not accidentally empty — no data
lost, every round is in `round_payoff` and `payoff_vector`; CODEBOOK "The
payment record").
Facts established before shipping: nothing in oTree 6.0.15 recomputes
`participant.payoff` after that write (the `player.payoff` setter's delta is
the only other writer), and nothing in the template or its tests read the
per-round column except the placeholder itself.
**Rejected:** zeroing `participant.payoff` so the admin page is obviously
wrong (option 1 — Julian chose agreement over conspicuous wrongness); and
keeping the per-round writes while overwriting the total at the end, which
leaves a round column summing to a number nobody was paid.

### AMENDED 2026-08-14 — the raise was never the enforcement, and it lands on a participant

**Caught by the exp_pilots bossman**, verified against the installed oTree
before acting: this entry, `settings.py`, `main/__init__.py`,
`outro/__init__.py`, `CODEBOOK.md` and `docs/skills_claude/writing_task.md` all
said `AUTO_TABULATE_PAYOFFS=False` "makes the old habit RAISE rather than
drift back silently" — presenting a **participant-facing crash as a safety
feature**. The setter is oTree's own (`otree/models/player.py:41-46`), it
cannot be removed, and it fires **at participant request time, on a page,
mid-round**. oTree has no migrations, so the realistic failure is an upgrade
under live sessions: a new build introduces a `player.payoff` write and the
first person mid-round to reach it gets a DEAD PAGE. The flag alone therefore
converts a CONDITIONAL data problem (one ledger drifting into two) into a
CERTAIN outage for whoever is part-way through — the same trade this repo has
already refused twice, in `install_duplicate_label_guard` (the early install
must fail quietly) and in `assert_duplicate_label_guard` (deliberately not on
the entry path). It was missed here for the reason it is always missed: **a
raise feels like the strict, careful option.**

The raise stays — it is oTree's, and it is the floor. What changed is that the
failure is now caught **earlier, at boot**, where loud is what loud should
mean for a server: `payoff_guard.assert_no_player_payoff_writes()`, called
from `before/__init__.py` beside the identity assert, refuses to START a build
whose app modules write `player.payoff`. The operator sees it at deploy time
while the old build is still serving; the participant never sees it.

**TWO CHECKS, DELIBERATELY, because their blind spots are disjoint** — the
judgement call the review left open. The boot scan parses app SOURCE with
`ast`, so it covers every syntactic write whether or not any test walks that
line, and it cannot be fooled by the six files that discuss `player.payoff` in
prose (a regex would refuse to boot over this very paragraph); it is blind to
indirection. The runtime test walks a real journey and asserts the underlying
`_payoff` column is still 0 on every round row, which catches indirection; it
is blind to code no walk reaches. Neither alone is sufficient, so both ship.
`participant.payoff` and `player.payoff` are two fields sharing a name, and
the scan tests the base expression explicitly rather than the attribute — the
collapsed-distinction rule, since a name-only check would refuse to boot over
`outro.compute_final_payoff`, the one write the decision exists to protect.
**Rejected:** a launch-gate-only check (`scripts/prelaunch_check.py`), which a
deploy can skip — the whole point is that the server will not come up; and
`import`-and-introspect instead of parsing, which would execute
`intro/generate_instructions_preview.py` and its browser driver at boot.
**Enforced:** `payoff_guard.py`; `scripts/tests/payoff_ledger_test.py` §7 (a walked
journey leaves every round row's `_payoff` at 0) and §8 (the guard catches six
write forms including `setattr` with a literal name, refuses a synthetic build
naming file and line, does NOT fire on the participant write or on prose,
declares its `setattr`-with-computed-name blind spot, and reports an
unparseable module as "cannot answer" rather than as a payoff write).

**Enforced:** `scripts/tests/payoff_ledger_test.py` (the two figures agree on the
admin page itself; the value survives re-renders; oTree's setter does raise;
the export column is absent while `round_payoff` is present) — plus the boot
guard above.

## A payment total is not a payment instruction: every component paid outside oTree must still be represented inside it — 2026-08-14

**Caught by the exp_pilots bossman**, and it is the natural blind spot of the
one-payment-ledger decision above: that decision made the total CORRECT and
made both ledgers AGREE on it, and stopped there. Our admin Payments figure is
one undifferentiated number — full `earned` into `participant.payoff`,
`participation_fee` shipped 0.00 — so it covers base plus bonus at once. **On
Prolific those components are paid through DIFFERENT MECHANISMS**: the base as
the study reward, the bonus through the bonus payment flow. A single total,
however correct, is therefore NOT ACTIONABLE — whoever pays needs the **bonus
figure on its own**, and that is the number that must survive intact.

THE RULE, in the reviewer's words:

> **ANY PAYMENT COMPONENT PAID OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE
> OTREE, OR THE ADMIN PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A
> TOTAL.**

**Corollary:** on Prolific the components are paid by different mechanisms, so
the total alone is not enough — the bonus must be separately visible.

THE TWO SHAPES, WHICH LOOK LIKE OPPOSITES AND ARE THE SAME DEFECT. Ours is
**complete but not itemised**: everything is inside oTree, the total is right,
and the payer cannot read the bonus off it. The reviewer's own study was
**itemised but incomplete**: components kept apart, but the base never entered
oTree at all, so its "total" was a partial figure wearing a total's name.
Neither has the property that matters, which is **itemisation of a complete
set** — and framing them as opposites is what let both ship.

WHY THE EXISTING TEST DID NOT CATCH IT — the part worth remembering. §1 pins
that the total is correct and that the two ledgers agree on it. **A study can
get the total right while making the actionable number unreadable**, and a
test written against the total cannot see that. This is the collapsed-
distinction rule in the measurement rather than in the code: "the payment is
correct" and "the payment is payable" were one assertion.

**DONE NOW (safe, and independent of the open config decision):**
`scripts/tests/payoff_ledger_test.py` §9 walks a *prolific* session and asserts the
BONUS IN ISOLATION as well as the total — each component recorded on its own,
the three reconstructing `earned` with zero residue, the bonus
(`selected_sum + quiz_bonus_awarded`) derived from the stored components
rather than as `total − base` (which would be right by construction and prove
nothing), both halves separately readable, and the components present as their
own export columns. It also records the admin-page state as a **measured gap**.

**THE CONCRETE FIGURES THIS DECISION IS BEING MADE AGAINST**, so nobody reading
it later has to reconstruct what the admin page actually showed. One real
walked Prolific completer (participant `240pbcpa`, config `prolific`, 10 rounds,
`payment_num_rewarded=2`, exit code 1), measured 2026-08-14, all figures EUR:

| Figure | Source | Value |
| --- | --- | --- |
| base / show-up | `payment_show_up` (session config) | **2.50** |
| selected rounds | `outro.Player.selected_sum` (r10 → 45.00, r6 → 98.00) | **143.00** |
| quiz bonus | `outro.Player.quiz_bonus_awarded` | **5.00** |
| **total earned** | `outro.Player.earned` — the three above, residue exactly 0 | **150.50** |
| `participant.payoff` | written once by `compute_final_payoff` | **150.50** |
| `participation_fee` | session config, as shipped | **0.00** |
| **admin Payments figure** | `payoff_plus_participation_fee()` | **150.50** |

The selected-rounds component is randomly drawn, so it and every total below it
vary per run (other runs measured 125.00 and 140.00); **base, quiz bonus and
`participation_fee` are fixed, and the SHAPE is invariant** — the admin figure
always equals `earned`, because `participation_fee` is 0.00 and the whole of
`earned` goes into `participant.payoff`.

**WHAT THE PAYER NEEDS IS TWO NUMBERS, AND THE ADMIN PAGE SHOWS NEITHER** — it
shows their sum. Study reward, set on the Prolific study: **2.50** (the base
alone). Bonus payment, entered in the bonus flow: **148.00** (selected rounds +
quiz bonus). Pasting the admin's 150.50 into the bonus flow pays 148.00 of
correct bonus plus 2.50 that Prolific has ALREADY paid as the study reward: the
participant is overpaid by exactly the base, and the error is invisible because
the total was right all along.

**THE MEASURED EVIDENCE**, fetched from oTree's own `/SessionPayments` for that
session: **€150.50 PRESENT. €148.00 (the bonus) ABSENT. €2.50 (the base)
ABSENT.** That is the itemisation argument in one line — the page carries the
total and neither component.

(Matched CURRENCY-PREFIXED, never as a bare number: `150.50` contains `2.50`, so
a substring search reported the base as present on a page that never mentions
it. See the comment at that check — a bare search makes both negative
assertions unable to fail, which is the same defect class as the total-only test
this whole entry is about.)

**DELIBERATELY NOT DONE YET:** changing `participation_fee` or how
`participant.payoff` is composed — that is an open decision with Julian, and it
changes what the exported columns MEAN, which is not something to do as a side
effect of adding a test.
**Rejected:** asserting only that the components exist, without asserting they
sum to `earned` — a component nobody can reconcile is a number, not an
itemisation; and deriving the bonus as `total − base` in the test, which passes
whatever the data says.
**Enforced:** `scripts/tests/payoff_ledger_test.py` §9; the rule is stated in
README "Paying participants — the itemisation rule" and in CODEBOOK "THE
ITEMISATION RULE".

## The end-of-page cookie reset is gone — 2026-08-13

`clearAllCookies` (run on load by the payoff, Ended and Results pages) was
removed with its three call sites and its helper — Julian: no longer needed.
It cleared every path=/ cookie each round and at the endings, including an
admin's own session cookie when previewing; oTree identifies participants by
URL code, not cookies, so nothing participant-facing depended on it. The other
dead cookie helpers an earlier review flagged (getCookie, setCookie,
printCookies, cl) were already gone. Do not re-add a cookie sweep without a
stated reason — the last one ran for years with nobody able to say what it was
for, which is why the review flagged it.
**Enforced:** nothing but grep — there is no cookie code left to guard.

## The dashboard summary strip: earnings is ONE pill carrying avg AND total; the total summed server-side over finished participants — 2026-08-17

Requested by Julian, from the live page. The payment picture lives on the one
dashboard tab, so nobody opens oTree's own Payments page to see what a running
session is paying out. The `dash-summary` strip beneath the table
(`experimenter_dashboard.py`) has TWO items: **avg intro time**, and a single
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

## The Non-SEPA pill: lab only, `sepa == 0` only, and no yellow state — 2026-08-13

Three deliberate narrowings, all Julian's: NULL `sepa` (the check never ran —
every Prolific row) is NO pill, never a flag; a non-Dutch but in-SEPA account
is NO pill (only non-SEPA is flagged — there is no yellow payment state); and
even a hand-edited `sepa=0` in a Prolific session shows nothing, because
payment there goes through the platform and the pill would send the operator
chasing a form that does not exist.
**Enforced:** `experimenter_dashboard._non_sepa_ids` (the one predicate);
`scripts/tests/dashboard_test.py` §D7 pins all three narrowings.

## The BIC requirement and the Non-SEPA flag are two predicates, not one — 2026-08-13

The lab bank form demands a BIC for ANY non-Dutch IBAN (in-SEPA or not;
non-empty is the whole requirement — no format validation, because a rejected
valid-but-unusual BIC strands a participant on the page that pays them). The
dashboard pill fires on non-SEPA ONLY. A German IBAN therefore needs a BIC and
gets no pill. Both read the country through `outro.iban_country_code` — one
implementation of "which country", two questions on top of it (the inverted
collapsed-distinction rule, applied in the direction that keeps the questions
apart and the mechanism shared).
**Rejected:** one combined predicate — it would either flag every German
account or let a US account through without a BIC.
**Enforced:** `scripts/tests/bank_details_test.py` pins both halves of the asymmetry,
next to each other.

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

## The return click is best-effort instrumentation, and the pill is gated on the button existing — 2026-08-13

"Finished here but never clicked Back to Prolific" is flagged ONLY when
`prolific_completion_redirects` is on — with no redirect there is nothing to
click, and the flag would fire on every lab participant forever (Julian's
critical condition; the gate comment in `_participant_row` is load-bearing).
The click stamp (`prolific_return_clicked`) rides the Results page's live
socket just before navigation, so it can be lost — absence means "no click
RECORDED", and the pill is a prompt to look, never a verdict. A grace period
(`DASHBOARD_RETURN_GRACE_SECONDS`) stops it firing on completers still reading
their receipt.
**Rejected:** routing the exit link through a stamping redirect — exact and
JS-free, but it puts instrumentation INSIDE the one path every completer
needs, and instrumentation must never be able to break a page (CLAUDE.md); the
link stays a plain href that works with the whole mechanism dead.
**Enforced:** `outro.results_live_method` (gated the same way);
`scripts/tests/dashboard_test.py` §D8 pins the gate from both sides; CODEBOOK.md
documents the stamp's best-effort nature.

## The shipped quiz items are machinery placeholders, not model items — 2026-08-13

Deliberately trivial ("What is ice when it melts?"), because they exist to
exercise the quiz machinery — wrong answers, retries, the attempt log, the
thresholds — and are replaced wholesale by every real study.
**Rejected:** shipping an exemplary Stag Hunt comprehension item. It would read
as content to keep, and the previous item ("If you fail the quiz twice…") also
hard-coded the failure threshold into participant copy and described behaviour
the shipped config doesn't produce.
**Enforced:** the comment atop `intro/quiz_items.py`;
`scripts/tests/example_quiz_content_test.py` §3 pins the placeholders and is designed
to fail when a study writes its own items, forcing the test to be rewritten
with them (see `docs/skills_claude/writing_quiz.md` for what real items look like).

## The quiz-bonus rule is stated in two places, deliberately — 2026-08-13

Once in the payment overview (`intro/instructions_text.html`), once as the
reminder directly before the quiz (`intro/prequiz_text.html`), both now naming
*which* quiz ("every quiz question on the instructions").
**Rejected:** stating it once — the pre-quiz reminder is worth the duplication.
**Enforced:** nothing. Two cross-referencing comments ("if the rule changes,
edit BOTH") rely on the next editor reading them.

## Missing completion codes degrade to `REPLACE_CC`, never to `None` — 2026-08-13

`outro.completion_link` reads codes through the safe accessor, so a session
frozen before a code existed builds the shipped `REPLACE_CC` placeholder into
the URL. Chosen *because* it produces the same symptom as the already-known
failure "nobody replaced the placeholder": anyone seeing `REPLACE_CC` knows
instantly what it means and what to do, while `?cc=None` looks like a bug of
ours and tells the operator nothing.
**Enforced:** `outro.completion_link` (reasoning in its docstring); pinned by
`scripts/tests/frozen_config_test.py`.

## The config-drift check has two severities, so it stays trustworthy — 2026-08-13

The pre-deploy audit of frozen session configs FAILS on exactly two things —
a key missing from a frozen config, and a surviving `REPLACE_*` placeholder —
and merely *reports* every other difference.
**Rejected:** failing on any difference. A session legitimately runs older
thresholds and `static_version` changes on nearly every deploy, so an
all-differences failure fires every time, gets ignored within a fortnight, and
then catches nothing — including the real cases.
**Enforced:** `scripts/predeploy_check.py` (`audit_frozen_session_configs`);
its docstring carries the warning not to promote diffs to failures.

## The logo footer is a rule, not a per-page arrangement — and yields first — 2026-08-13

The logo strip sits at the bottom of the white card, below its divider,
identically on every page that shows it — enforced structurally (`order: 999`,
`margin-top: auto`) so a template that includes it in the wrong place still
renders it right. Because it is decoration, it is the first thing to shrink
when vertical space runs short (mark height drops at the short-viewport
breakpoint).
**Rejected:** each template getting the markup order right — a new page copies
whichever page its author happened to open.
**Enforced:** the LOGO FOOTER RULE block in `_static/global/css/base.css`;
logo geometry is in `scripts/tests/geometry_baseline.json`.

## Styling is shared components, never page-local patches — 2026-08-13

A page template composes named classes from `_static/global/css/`; no inline
`style=`, no one-off rule to fix a single page, and every new component gets an
INTENTION comment plus a specimen in `_static/global/html/template.html`.
Driven by three real bugs of the same shape: a class referenced by three
templates and defined nowhere, one concept carrying two widths, and an inline
`height` beating the component's own rule. Genuine one-screen exceptions are
marked `EXCEPTION` with the reason.
**Enforced:** the Styling section of `CLAUDE.md`; layout drift is caught by
`scripts/tests/render_check.py` against the geometry baseline. The no-inline-style rule
itself relies on review. Full working: `_ai/css_divergence_report.md` (local only — `_ai/` is gitignored; not in a clone).

## "Flags decide mechanics, `recruitment` decides copy" — 2026-08-13

Every sentence a participant reads that names the platform, the room, or how to
reach a human branches on `recruitment`; module flags answer only "does the
machinery exist". Driven by a found dead end: the consent page inferred
"Prolific" from one flag, the screen-out page from another, and a
friend-test config told a participant to seek help through Prolific and then
gave them no way out at all — no error, no failing test.
**Rejected:** letting whichever flag is nearest stand in for the study type.
**Enforced:** `common.is_lab` / `common.is_prolific` are the only two
implementations; `scripts/tests/copy_routing_test.py` asserts the impossibility;
`settings._prelaunch_problems` refuses the config combination that created the
dead end.

## Completion fires when the results page loads — identically in both variants — 2026-08-12

`exit_code` becomes `finished` in `Results.vars_for_template`, not on the
"Back to Prolific" click. This reversed an earlier request, and the principle
behind the reversal outranks the detail: **lab and Prolific diverge only where
genuinely essential**, because every divergence can be true in one variant and
quietly wrong in the other, forever. A participant who closes the tab without
clicking has still finished; the click is Prolific's concern, not the data's.
**Enforced:** `outro/__init__.py` (`Results.vars_for_template`, idempotent);
`scripts/tests/full_journey_test.py` asserts exit code 1 at Results. The
minimal-divergence principle itself has no guard — the caller-list warning on
`common.is_lab` and review are what hold it.

## ~~A screened-out Prolific participant gets a codeless link back~~ — 2026-08-12, SUPERSEDED 2026-08-15

The way off the screen-out page is a plain link with **no completion code**,
because submitting a code closes the Prolific submission, and a returned
submission can never be retaken — which forecloses exactly what the page asks
("come back on a computer"). The old `error_code`/`REPLACE_ERR` pair was
removed for this reason and must not come back. Corollary (2026-08-13): being a
Prolific study and offering a screened-out exit are the same commitment, so the
dependency is enforced, not documented.
**Enforced:** the no-screened-out-code note in `settings.py`;
`settings._prelaunch_problems` refuses a `recruitment='prolific'` config with a
blank or unreplaced `prolific_screenout_return_url`;
`scripts/tests/copy_routing_test.py` walks the codeless way out end to end.

> **SUPERSEDED 2026-08-15 by "Every ending population gets its own completion
> code" (below/newest).** The reasoning above is kept, not deleted, because a
> reader who meets the codeless design in an older study — or who reasons their
> way back to it — should be able to see that it was reconsidered and why,
> rather than find it silently gone.
>
> **What it got right:** submitting a completion code does close a Prolific
> submission, and a returned submission cannot be retaken. That is still true.
>
> **What it got wrong:** it treated "leave the submission open" as the kind
> outcome. In practice a bare researcher URL leaves the submission sitting in
> LIMBO — the participant has been turned away, cannot continue, and nothing
> tells Prolific anything; the place stays occupied until it times out. A
> Prolific REQUEST_RETURN code is not the same instrument as a completion code:
> it actively PROMPTS the participant to return the submission, which is the
> outcome that frees the place and ends the ambiguity. The screened-out exit is
> now `prolific_device_code` used as a full completion URL, and
> `prolific_screenout_return_url` is gone as a setting.

## The screen-out return URL ships as a placeholder, not a working default — 2026-08-12

It used to ship as `https://app.prolific.com/`, which works — and that is the
problem: **a plausible default never gets checked**, and the person who
discovers it was wrong for this study is a participant already turned away.
**Enforced:** the `REPLACE_*` family is flagged by the prelaunch banner and by
the pre-deploy frozen-config audit's PLACEHOLDER severity.

## The device screen-out is a soft wall, clearable before consent only — 2026-08-12

A screened participant is HELD on the entry page (not walked to an ending oTree
could never bring them back from), and a later pre-consent request from an
accepted device clears the screen-out; exit code `-4` is the one code that can
revert. After consent the check never applies again. The state is reset, the
history never is — "how many did the gate turn away" is counted from
`screenout_history`, not the exit code.
**Rejected:** routing to a proper ending page (irreversible in oTree), and a
write-once `-4` (would leave genuine finishers recorded as screened out).
**Enforced:** `scripts/tests/screenout_softwall_test.py`; the consent boundary is the
durable `participant.consent_submitted` fact, not a page index. Full working:
`_ai/screenout_softwall_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The clear predicate is exactly the entry-allow predicate minus `undetermined` — 2026-08-12

If clearing allowed *more* than entry, a screen-out could be lifted by a device
that would not have been let in; if *less*, the page tells someone switching
will work when for them it cannot (the reference implementation had this bug:
its `unknown` never cleared, stranding privacy-proxy laptops). `undetermined`
is the single carve-out — no usable header is not a device, and treating it as
a clear would let anyone lift their own screen-out by sending no User-Agent.
**Enforced:** `common.device_clears_screenout` (explicit membership, so
`undetermined` cannot satisfy it whatever a config says);
`scripts/tests/screenout_softwall_test.py` §8 states the two asymmetric assertions side
by side.

## `unknown` and `undetermined` are different states — 2026-08-12

A User-Agent that parsed and matched nothing (`unknown`) is a device type a
study may accept or reject like any other; no usable header at all
(`undetermined`) is *not a device type* and must always be allowed. Collapsed,
a study rejecting `unknown` starts ejecting laptops behind privacy proxies.
This is the model case of the collapsed-distinction rule in `CLAUDE.md`.
**Enforced:** `common.classify_device`; `scripts/tests/device_gate_test.py`, which is
deliberately weighted toward false positives (browsers that must NOT be
screened). Full working: `_ai/device_allowlist_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The lab comprehension rule is help, not ejection — unlimited attempts — 2026-08-12

Online, crossing the failure threshold disqualifies (`quiz_comprehension_dq`); in
the lab the same threshold *starts the study helping*: the one-time re-read
offer (if `quiz_reread` is on), then a dismissible "raise your hand" notice,
escalating at twice the threshold — and the participant may keep trying
forever. The notice is keyed on the threshold and the study type, NOT the
module, so a lab session with `quiz_reread` off still calls the experimenter.
The notice deliberately does not say "you can keep trying" — some participants
should raise a hand instead of brute-forcing radio items.
**Rejected:** disqualification in the lab (there is a human in the room), and
keying the notice on the module (left a module-off lab session with no help at
all).
**Enforced:** `scripts/tests/gated_flow_test.py` (lab-reread and prolific-dq
scenarios); the prelaunch check refuses `quiz_comprehension_dq` in a lab config;
attempts proven uncapped by `scripts/tests/quiz_attempt_log_test.py`. Full working:
`_ai/lab_comprehension_proposal.md` (local only — `_ai/` is gitignored; not in a clone).

## Every graded quiz submission is logged — uncapped, and unable to break the page — 2026-08-12

`quiz_attempt_log` records what was answered and what was wrong *as judged at
the time* (never re-graded — the item set changes between studies), with no cap
on entries, and the whole write is wrapped so instrumentation can never cost a
participant their page.
**Enforced:** `intro.log_quiz_attempt` (never raises);
`scripts/tests/quiz_attempt_log_test.py` proves 25 attempts stored and the page still
standing.

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

## Participant identity is decided in one place — 2026-08-12

"Is this the same participant id?" was answered twice — label comparison in
Python (case-folded) and row lookup in SQL (collation-dependent) — so a
returning `ABC123` took a fresh row against a stored `abc123`, and behaviour
differed between sqlite (dev) and postgres (production). One implementation,
called by both.
**Enforced:** `identity.py`; `scripts/tests/identity_test.py`. This bug pattern is
generalised as the inverted collapsed-distinction rule in `CLAUDE.md`.

## The layout geometry baseline is committed, so intentional change is reviewable — 2026-08-12

`scripts/tests/render_check.py` measures element geometry at three viewports;
`scripts/tests/geometry_baseline.json` is committed **on purpose** (to `scripts/tests/`, not
gitignored `_ai/`) so an intentional layout change shows up as a reviewable
diff of that file, and an unintentional one fails `--diff`. Layout failures
produce no error otherwise — nothing 500s while the participant gets a broken
page.
**Enforced:** `render_check.py --diff` exits non-zero on movement beyond ±3px;
adopting a change requires `--update-baseline` and reading the diff.

## Three orthogonal controls; profiles resolve to explicit config keys at import — 2026-08-10

Study type, DEBUG (env-driven, so production can never ship skip controls), and
the pilot feedback form are independent axes; there is no "testing" study type
— testing loosenings are a reversible override honoured only under DEBUG. A
recruitment profile is rewritten into explicit per-config keys at import, so
the admin shows exactly what a session ran with and a profile can never change
behaviour silently at runtime.
**Rejected:** a `testing` study type (collapses two axes and lets loosenings
ship), and profiles consulted at runtime (invisible in the admin, mutable under
running sessions).
**Enforced:** `settings.resolve_recruitment_profile`;
`scripts/tests/frozen_config_test.py`; DEBUG derived from `OTREE_PRODUCTION` presence.

## Exit codes: initialised at creation, `0` means "never reached an ending" — 2026-08-07 (ported from the pilot)

Every participant carries `exit_code` from session creation, so no export row
is ever blank; `0` is *abandoned* — created but never reached any ending — and
is distinct from every deliberate outcome, each of which has its own code
(screened-out is `-4`, not `0`: you must be able to tell the gate's work from a
closed tab). A code nothing records is a lie in the export, so
reserved-but-unwired codes are deleted, not documented (`timed_out`, removed
2026-08-10).
**Enforced:** `common.init_participant`; the codes table in `CODEBOOK.md`;
tests assert on numeric codes rather than ending copy
(`full_journey_test`, `device_gate_test`).

## Participant and config reads go through safe accessors, always — 2026-08-07 (ported from the pilot)

`participant.vars.get(...)` (never `getattr` — the vars descriptor raises
`KeyError`, which the getattr default does not catch: a live outage), and
`common.cfg(...)` (never `config[...]` — a session config is frozen at
creation, so later-added parameters are absent for running sessions: also a
live outage). `common.flag` is the deliberate exception: a module flag missing
from a frozen config means the module post-dates the session and must read as
OFF.
**Enforced:** `common.pvar` / `common.cfg` / `common.flag`;
`scripts/tests/frozen_config_test.py` strips keys and walks; the rules are in
`CLAUDE.md`'s correctness list.

## A test that cannot fail is not evidence — standing principle

Bot tests passing is not evidence a browser works (three pilot outages went
green under bots); a content test loosened until it survives a content change
was never testing the content; a drift check that fails on everything gets
ignored and then catches nothing (see the two-severity entry above). Every
check must correspond to a participant it could save.
**Enforced:** as method, in `docs/skills_claude/writing_tests.md` (real HTTP, no-JS
submits, phone User-Agents, visible-text assertions, measured rendering);
structurally, nowhere — this one is held by review and by the suites being the
shape they are.
