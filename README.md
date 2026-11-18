# oTree-Template

A ready-to-run oTree study you copy to start a new experiment. It has four apps
(consent, instructions and quiz, your task, endings), a shared look, recruitment
plumbing for a physical lab and for Prolific, and guards that stop a live study
from breaking quietly. You put your game in `main/` and run it.

## What you get

- **Four apps in order**: `before` (welcome, consent, Prolific ID and device check), `intro` (instructions and quiz), `main` (your task), `outro` (endings, demographics, payment).
- **Lab or Prolific from one switch** in `settings.py`, plus a debug mode and a pilot feedback form that are independent of it.
- **Prolific built in**: ID capture, a device check, and five endings that each send people back with their own completion code.
- **A live experimenter dashboard** at `/experimenter_dashboard`, with a Download data button for plain CSV files.
- **Payment done once**: one payment rule in `outro/payment_rule.py` and a Results receipt for participants.
- **Checks before you launch**: a config check, an upgrade check against a copy of the live database, and a test suite that drives real pages.
- **Docker image** that will not wipe your data on restart.

## Quick start

You need Python 3.9 or newer.

```bash
pip install otree==6.0.15
otree devserver
```

Open http://localhost:8000/demo and click through a session. Nothing needs configuring first. Do not run `otree resetdb` before `devserver`.

To turn it into your study:

1. **Copy the template** and start your own decision log from `.claude/DECISIONS_stub.md`.
2. **Pick lab or Prolific** in `settings.py` (the `recruitment` profile and the completion codes).
3. **Build your game in `main/`**, replacing the placeholder task. Guide: `.claude/skills/writing-task/SKILL.md`.
4. **Write the instructions and quiz** in `intro/instructions_text.html` and `intro/quiz_items.py`.
5. **Set the payment rule** in `outro/payment_rule.py`.
6. **Check before launch**: `python3 scripts/prelaunch_check.py`, and `scripts/predeploy_check.sh` if the study already has participants.

The full walkthrough is in [`.claude/reference/editing_a_study.md`](.claude/reference/editing_a_study.md).

## Folder layout

| Folder | What is in it |
| --- | --- |
| `before/` `intro/` `main/` `outro/` | the four oTree apps, run in this order |
| `core/` | shared Python modules the apps import (helpers, guards, dashboard, Download data) |
| `scripts/` | launch and deploy checks, data export and formatting, lab start scripts |
| `scripts/tests/` | the test suite: real HTTP flows and measured browser checks |
| `_static/` | shared CSS, JavaScript, images and the page template |
| `_templates/` | pages served outside oTree's page system (the room welcome gate) |
| `docs/` | guides for running a study: hosting, Prolific, Postgres, design principles, and the data codebook |
| `.claude/skills/` | how-to guides for writing the task, instructions, quiz, consent and tests |
| `.claude/reference/` | the detailed reference, by topic (written for AI agents, readable by anyone) |
| `.claude/DECISIONS.md` | the decision log: why things are the way they are |
| `previews/` | instruction previews; double-click `Preview_Instructions.command` there to make them (macOS) |

`settings.py` stays at the root: it holds the session configs, the recruitment profiles and every switch.

## Where to read next

- **Running a study**: [`docs/README.md`](docs/README.md). What to change, what to check before launch, how participants get paid.
- **Hosting online**: [`docs/hosting_railway.md`](docs/hosting_railway.md) for Railway, [`docs/running_on_prolific.md`](docs/running_on_prolific.md) for Prolific, [`docs/postgres_assumptions.md`](docs/postgres_assumptions.md) if you use Postgres.
- **A lab session**: [`.claude/reference/participant_flow.md`](.claude/reference/participant_flow.md) (lab flow) and `scripts/set_up_otree.bat` for the lab PC.
- **Reading your data**: [`docs/CODEBOOK.md`](docs/CODEBOOK.md), the analyst's reference: every column and exit code.
- **Why something is the way it is**: [`.claude/DECISIONS.md`](.claude/DECISIONS.md).
- **Rules for editing the template**: [`CLAUDE.md`](CLAUDE.md), with the topic index into `.claude/reference/`.

## Working with Claude

This template is set up for Claude Code. Open the project folder in Claude Code and describe what you want in plain words. Claude reads [`CLAUDE.md`](CLAUDE.md) at the start of every session, so it knows the rules, guards and checks, and it follows the pointers there into `.claude/reference/` and `.claude/skills/` when a task needs them.

Useful things to ask:

- **"Build my task in `main/`"**, describing your game. It follows `.claude/skills/writing-task/SKILL.md` and updates the tests that go with it.
- **"Rewrite the instructions and quiz for my game"**. It uses `.claude/skills/writing-instructions/SKILL.md` and `.claude/skills/writing-quiz/SKILL.md`.
- **"Set up hosting for a Prolific study"** or **"prepare the lab session"**. It uses `.claude/skills/hosting-a-prolific-study/SKILL.md` and `docs/hosting_railway.md`, or the lab scripts.
- **"Run the checks and tests before launch"**. It runs `scripts/prelaunch_check.py`, `scripts/predeploy_check.sh` and the suite in `scripts/tests/`.

Check its work in a browser before you launch. The checks catch a lot, not everything.

## Attribution (oTree)

The "powered by oTree" badge is hidden (see `_static/global/css/base.css`). The oTree licence is met by **citing the oTree paper** in any write-up: Chen, D. L., Schonger, M., & Wickens, C. (2016). oTree: An open-source platform for laboratory, online, and field experiments. *Journal of Behavioral and Experimental Finance*, 9, 88–97.
