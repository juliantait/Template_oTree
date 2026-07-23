# Skill: writing participant instructions

Read this whole file before writing or editing instructions. The deliverable is the
content of `intro/instructions_text.html` (plus, if the task uses interactive controls,
a try-it page that reuses the real widgets).

## Overriding principle

> **FAVOUR SIMPLICITY FOR PARTICIPANTS OVER OVER-EXPLAINING.**

Your reader is a lay member of the public on Prolific: no stats background, probably on a
phone, skimming, with nobody to ask. Two consequences you must design around:

1. **Anything ambiguous will be misread.** There is no experimenter in the room to fix it.
2. **Anything intimidating is a confound.** Text that looks like a maths exam makes
   less-numerate participants disengage or drop out *differentially* — that biases the
   sample and threatens validity. This is a scientific problem, not a style preference.

So: favour simplicity over completeness. Cut every word that isn't doing work. If a
sentence survives only because it "might help someone", delete it.

## Where things live (this template)

- `intro/instructions_text.html` — the **only** file to edit for instruction content.
  Each `<div class="instruction-block">` is one page. The `<h2>` inside the block **is**
  the page title (single source of truth — there is no separate page-title element, do
  not add one in `intro/templates/instructing.html`).
- Template variables (`{{ var }}`) and treatment conditionals (`{% if treatment == ... %}`)
  work in this file and in the preview generator. See the comment header of
  `instructions_text.html` for the markup conventions. Beware: oTree parses template tags
  **even inside HTML comments** — write `{ {` with a space in comments.
- `previews/generate_instructions_preview.py` — regenerate previews after editing so
  coauthors can review.
- DEBUG-gated skip: `intro/templates/instructing.html` already renders a
  "Skip instructions (testing)" button only when `settings.DEBUG` is on
  (`OTREE_PRODUCTION` unset). **Keep it.** If you add new instruction-adjacent pages
  (e.g. a practice page), give them the same `{{ if is_debug }}` skip so testers can jump
  through, and confirm it disappears in production.

## Core principles

### Lead with the intuition, not the model
Describe what the participant **does with their eyes and hands** and what the stimulus
**looks like** — not the generative process behind it.

- ✅ "You will see a box of dots. Some are blue, some are orange. Your job is to say
  which colour the machine favours."
- ❌ "Dots are drawn i.i.d. from a Bernoulli distribution whose parameter depends on the
  machine's hidden state."

### No formulas in participant text
A formula signals "this is a maths task" and differentially intimidates less-numerate
participants — a validity threat (it changes *who* engages), not just a readability issue.
Express every rule in words and worked numbers. This includes the scoring rule: its name
and formula stay out of participant view (see Payment below).

### One vocabulary, everywhere
Pick one word for each key concept and use it in the instructions, the on-screen
controls, the quiz, and the results page. Never mix synonyms.

- ❌ "urn" on page 2, "box" on page 4, "container" in the quiz.
- ✅ Decide "box" once; grep the participant-facing files to enforce it.

### Concrete over abstract
Prefer plain-language state descriptions to abstract labels.

- ✅ "the machine that mostly shows blue" — ❌ "state A" / "the high-signal regime".

### Frequencies, not probabilities
- ✅ "60 in 100 rounds" / "6 out of every 10 draws" — ❌ "0.6", "60% probability", "p = .6".

### Frame confusability both ways
If two things can be mixed up, say both directions, don't rely on one.

- ✅ "The blue-leaning box still shows orange dots sometimes — and the orange-leaning box
  still shows blue dots sometimes."

### Bold sparingly
Bold only the handful of load-bearing phrases a skimmer must not miss (the choice they
make, the thing that stays fixed, the thing that changes). If more than ~2 phrases per
page are bold, nothing is.

### Honest but legible examples
Examples must be truthful about the task, but choose them for legibility: if an example
depends on a random draw or a treatment condition, **freeze it deterministically** and
pick a case that reads clearly (clean numbers, unambiguous outcome). Never leave an
example to be rendered from live randomness.

## Payment: describe it factually, never strategically

- State **what raises your chance of the prize / your earnings** in plain factual terms:
  "The closer your answer is to the truth, the higher your chance of winning the bonus."
- **Do NOT** tell participants that honest reporting is optimal, that the rule is
  "incentive-compatible", or that "there is nothing to gain from gaming it".
  Danz, Vesterlund & Wilson (2022) show that explaining the optimality of truthful
  reporting biases responses toward the middle. Facts about the mapping only; no advice
  about strategy.
- Keep the scoring rule's **name and formula out of participant view** (no "binarized
  scoring rule", no quadratic loss expression). The mechanics live in
  `outro/payment_rule.py`; participants get the plain-words version.
- If the design gives **no feedback during the task**, say so up front ("You will not be
  told whether you were right after each round") and reveal outcomes only at the end
  (`outro/Results.html`).

## Structure

- **Paginate; one idea per page.** One `instruction-block` = one concept. If a page
  needs a scrollbar on a phone, split it.
- **Single-source header**: the `<h2>` inside each block is that page's title. Don't
  duplicate it in a fixed header element.
- **Vague welcome.** The first page says only: what kind of study, roughly how long,
  that payment includes a bonus. **Do not front-load the task** — introduce the task on
  the next page. (See the shipped Stag Hunt example's "Welcome" block for the shape.)
- **Let them try the real controls.** Before the task starts, give a page where the
  participant interacts with the **actual widget components** used in `main/` (the real
  slider, allocation control, etc. — include the same partial/JS, not a screenshot).
  A control someone has moved once needs no paragraph explaining it.
- **Keep the whole thing short**: a few screens, short paragraphs (2–3 sentences),
  lists over prose where the content is genuinely list-shaped.

## Checklist before you finish

- [ ] Every page is one idea with its `<h2>` inside the block.
- [ ] No formulas, no scoring-rule name, no probability notation anywhere participant-facing.
- [ ] All probabilities phrased as frequencies ("60 in 100").
- [ ] One consistent term per concept across instructions, controls, and quiz (grep to verify).
- [ ] Payment described factually; no "honesty is optimal" language.
- [ ] No-feedback design (if applicable) stated explicitly.
- [ ] Welcome page is vague; task introduced on page 2.
- [ ] Examples frozen deterministically and chosen for legibility.
- [ ] Bold used only on load-bearing phrases.
- [ ] Real interactive controls available to try pre-task.
- [ ] DEBUG-gated skip present and hidden in production (`OTREE_PRODUCTION` set → no skip button).
- [ ] Previews regenerated via `previews/generate_instructions_preview.py`.
