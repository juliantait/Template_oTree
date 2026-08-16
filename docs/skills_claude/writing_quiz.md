# Skill: writing the comprehension quiz

Read this whole file before writing or editing quiz items. The deliverable is
`QUIZ_ITEMS` in `intro/quiz_items.py` (entries with `field`, `prompt`, `choices`,
`answer`). The quiz page and retry logic are already wired in
`intro/templates/quiz.html` and `intro/__init__.py` — you only edit the items.

## Overriding principle

> **FAVOUR SIMPLICITY FOR PARTICIPANTS OVER OVER-EXPLAINING.**

And the quiz-specific corollary: a comprehension check **tests** understanding — it must
never **teach**, hint, or give away the answer. Every item is read by a participant who
may be confused; the item must not resolve their confusion for them, only detect it.

## ⚠️ THE SINGLE MOST IMPORTANT RULE ⚠️

> **NEVER QUIZ ON THE VERY EFFECT THE STUDY MEASURES.**

A quiz item that primes or teaches the measured behaviour **contaminates the data** —
the study then measures "did our quiz work", not the phenomenon. Two forms of this:

1. **Priming the measured cue.** If the study measures whether people use sample size,
   do not ask anything like "does more data help?" or "which is more reliable, 10 draws
   or 100?".
2. **Collapsing elicitations that must stay distinct.** If the design elicits two things
   separately (e.g. an allocation **and** a confidence rating), never quiz the optimal
   relationship between them — that tells participants the two are one quantity and
   collapses them.

Concrete cautionary examples — items like these must be **removed, not reworded**:

- ❌ "Which plot is easier to judge: the one with more dots or fewer dots?"
  → primes sample-size weighting; if that's the DV, this item destroys it.
- ❌ "If you believe there is a 60% chance the left box is correct, what is the best way
  to split your 100 points?" → teaches the allocation↔confidence mapping and collapses
  the two elicitations into one.

There is no acceptable rewording of an item whose *topic* is the measured effect. Cut it.

## Keep the quiz minimal

Only check the **load-bearing comprehension** a participant needs to do the task
honestly. Typically that is three or four items:

1. the prior / starting setup (e.g. "before any dots appear, how likely is each box?"),
2. the independence of rounds (e.g. "does what happened last round change this round?"),
3. how payment works (the factual mapping, per the instructions skill — never
   "what should you do to maximise earnings").

Do **not** quiz everything the instructions said. Every extra item adds dropout,
annoyance, and another chance to teach something you shouldn't.

## Writing the options

- **Bare, parallel statements.** Same grammatical shape, similar length. No option
  carries its own justification ("...because that way you earn more" gives it away).
- **The correct answer must not be the longest or most reasonable-sounding option.**
  If you can spot it without reading the instructions, rewrite.
- **Distractors are genuine misconceptions** a confused participant could actually hold
  (e.g. "the box is re-drawn every round" when it isn't) — never absurdities or joke
  options, which make the item a giveaway by elimination.
- **Plain wording, no jargon.** Use exactly the same vocabulary as the instructions
  (one term per concept — see `writing_instructions.md`), frequencies not probabilities.

### Example shape (good)

```python
dict(
    field='quiz1',
    prompt='At the start of each round, how is the box chosen?',
    choices=[
        'The same box is kept for the whole study',
        'A new box is chosen, and each box is equally likely',
        'The box that was correct last round is used again',
    ],
    answer='A new box is chosen, and each box is equally likely',
),
```

Note: all three options are bare parallel statements; the two distractors are real
misconceptions (state persistence, hot-hand carryover); the correct one is not the
longest.

## Mechanics of this template

- Options render **in the written order, with no shuffle**. Vary which position holds
  the correct answer across items — never let "B" (or the last option) be a pattern.
- `answer` must be a **character-for-character copy** of one entry in `choices`. After
  *any* rewording, re-verify that the marked answer still matches its option string —
  a silent mismatch makes the item unpassable.
- Failing twice routes the participant back to re-read the instructions
  (`intro/templates/quiz.html`); you don't need to build retry logic.
- DEBUG-gated skip: quiz.html already renders a "Skip quiz (testing)" button and emits
  solutions to the browser **only under `settings.DEBUG`** (`OTREE_PRODUCTION` unset).
  **Keep it**; never expose solutions outside the `{{ if is_debug }}` guard.

## Checklist before you finish

- [ ] No item touches the measured effect or the relationship between separately
      elicited quantities (removed, not reworded).
- [ ] No item teaches, hints, or contains its own justification.
- [ ] 3–4 items max, covering only load-bearing comprehension (prior, round
      independence, payment mechanics — as applicable).
- [ ] Options bare, parallel, similar length; correct one not longest/most reasonable.
- [ ] Distractors are plausible misconceptions, not absurdities.
- [ ] Vocabulary identical to the instructions; frequencies not probabilities; no jargon.
- [ ] Correct positions varied across items (no shuffle exists to save you).
- [ ] Every `answer` string re-verified as an exact match of one `choices` entry.
- [ ] DEBUG skip and solutions remain gated on `is_debug`.
