# .claude/skills/: authoring playbooks for this template

Claude Code skills for agents working on this template or a study built from it
(not participant-facing content). Each skill is a folder with a `SKILL.md`; its
frontmatter `description` says when to use it, and Claude Code loads it on demand.
When a coauthor asks an agent to "make instructions" or "make the quiz", the agent
reads the matching skill **before writing anything**.

## Overriding principle (applies to every skill here)

> **FAVOUR SIMPLICITY FOR PARTICIPANTS OVER OVER-EXPLAINING.**
>
> Participants are lay members of the public recruited on Prolific: no stats background,
> skimming on a phone, with nobody to ask. Anything ambiguous will be misread; anything
> intimidating is a **confound**, not just a readability problem. When in doubt, cut.

## Index

- [`writing-task`](writing-task/SKILL.md): replace the placeholder game in `main/`; `intro` describes it afterwards.
- [`writing-instructions`](writing-instructions/SKILL.md): participant instructions in `intro/instructions_text.html`.
- [`writing-quiz`](writing-quiz/SKILL.md): the comprehension quiz in `intro/quiz_items.py`.
- [`writing-tests`](writing-tests/SKILL.md): tests in `scripts/tests/` (read before any test).
- [`writing-welcome-consent`](writing-welcome-consent/SKILL.md): welcome and consent pages in `before/`.
- [`hosting-a-prolific-study`](hosting-a-prolific-study/SKILL.md): host and run a study on Prolific end to end. Online studies only.

Related reference, not a skill: [`docs/hosting_railway.md`](../../docs/hosting_railway.md), what a hosted deploy needs plus the verified Railway procedure.
