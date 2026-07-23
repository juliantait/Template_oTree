# skills_claude/ — agent skill files for this template

This folder holds **skill files for AI agents** (not participant-facing content). When a
coauthor asks an agent to "make instructions" or "make the quiz" for an experiment built
from this template, the agent should read the matching file below **before writing anything**.
Each file is self-contained: what to produce, which files to edit, principles, do/don't
checklists, and short examples.

## Overriding principle (applies to every skill here)

> **FAVOUR SIMPLICITY FOR PARTICIPANTS OVER OVER-EXPLAINING.**
>
> Participants are lay members of the public recruited on Prolific: no stats background,
> skimming on a phone, with nobody to ask. Anything ambiguous will be misread; anything
> intimidating is a **confound**, not just a readability problem. When in doubt, cut.

## Skill files

- [`writing_instructions.md`](./writing_instructions.md) — how to write participant instructions (edit `intro/instructions_text.html`): lead with intuition, no formulas, one vocabulary, frequency framing, factual payment description, DEBUG-gated skips.
- [`writing_quiz.md`](./writing_quiz.md) — how to write the comprehension quiz (edit `intro/quiz_items.py`): test, never teach; **never quiz on the effect the study measures**; minimal item set; honest distractors.
