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

- [`writing_task.md`](./writing_task.md) — how to replace the shipped placeholder game (build in `main/`, then update every placeholder site): the game belongs in `main` and `intro` describes it afterwards; what a task page inherits from `TaskPage` and must not rewrite; the full manifest of replace-sites including `scripts/tests/main_contract.py`.
- [`writing_instructions.md`](./writing_instructions.md) — how to write participant instructions (edit `intro/instructions_text.html`): lead with intuition, no formulas, one vocabulary, frequency framing, factual payment description, DEBUG-gated skips.
- [`writing_quiz.md`](./writing_quiz.md) — how to write the comprehension quiz (edit `intro/quiz_items.py`): test, never teach; **never quiz on the effect the study measures**; minimal item set; honest distractors.
- [`writing_tests.md`](./writing_tests.md) — how to test a study built from this template (add scripts to `scripts/tests/`): why bot tests are not evidence a browser works; driving form pages over real HTTP; the no-JS submit; simulating a phone; asserting against rendered visible text; escaping; frozen configs; and measured rendering checks in a real headless browser.
- [`hosting_railway.md`](./hosting_railway.md) — how to put a study from this template onto Railway (the one managed deploy actually done, 2026-08-14): the deploy-repo export, project tokens (and what a project token CANNOT do), which operations need the GraphQL API rather than the CLI, the attempt-then-verify rule, the deploy order for a schema-changing build, domains, the env vars, the crash rehearsal, study day. **Procedure only** — what a hosted deploy needs in general, what the boot guard does, and the caveats live in [`docs/hosting_a_prolific_study.md`](../hosting_a_prolific_study.md), which is written for the researcher rather than the agent. Relevant to ONLINE studies only; a lab study needs none of it, and this template deliberately ships no deployment configuration.
- [`hosting_prolific.md`](./hosting_prolific.md) — the Prolific API procedure and its money/seat semantics for an online study: `reward` is in pence, the hourly minimum must be cleared by the base reward alone, places are completions-you-pay-for (returned and timed-out submissions reopen automatically), and Prolific places must never exceed the oTree seat count. Marks the two steps with **no API** — Preview and Test-as-a-participant, the latter the only end-to-end check of the return-and-payment path. Companion to `hosting_railway.md`; the researcher-facing code, completion codes and endings stay in [`docs/running_on_prolific.md`](../running_on_prolific.md). Online studies only.
- [`writing_welcome_consent.md`](./writing_welcome_consent.md) — how to write the welcome + consent page(s) (edit `before/welcome+consent.html` and `before/__init__.py`): welcome says little; consent is the deliberate exception to "when in doubt, cut" (simplify language, never drop a required element); explicit affirmative consent and a graceful no-consent path back to Prolific; final wording must be checked against the institution's ethics/IRB requirements.
