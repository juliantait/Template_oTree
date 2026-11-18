# Decisions: Quiz and instructions

Read when you touch the comprehension quiz, its attempts rule, its logging, or the quiz bonus.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

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

---

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
with them (see `.claude/skills/writing-quiz/SKILL.md` for what real items look like).

---

## The quiz-bonus rule is stated in two places, deliberately — 2026-08-13

Once in the payment overview (`intro/instructions_text.html`), once as the
reminder directly before the quiz (`intro/prequiz_text.html`), both now naming
*which* quiz ("every quiz question on the instructions").
**Rejected:** stating it once — the pre-quiz reminder is worth the duplication.
**Enforced:** nothing. Two cross-referencing comments ("if the rule changes,
edit BOTH") rely on the next editor reading them.

---

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

---

## Every graded quiz submission is logged — uncapped, and unable to break the page — 2026-08-12

`quiz_attempt_log` records what was answered and what was wrong *as judged at
the time* (never re-graded — the item set changes between studies), with no cap
on entries, and the whole write is wrapped so instrumentation can never cost a
participant their page.
**Enforced:** `intro.log_quiz_attempt` (never raises);
`scripts/tests/quiz_attempt_log_test.py` proves 25 attempts stored and the page still
standing.
