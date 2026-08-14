# Running a study from this template

For the researcher starting a study, not for whoever built the template. It
answers "what do I have to do, and what will bite me?" — the reasoning behind
each answer lives in `DECISIONS.md`, and you do not need it to run a study.

Everything in `docs/` is **tracked**, so a study copied from this template gets
all of it. Records of how the template came to be — audits, work logs, pilot
snapshots, change-request rounds — stay in `_ai/`, which is gitignored and does
not travel. Where a tracked file mentions one of those it is marked *local only*,
so you know the file is deliberately absent rather than missing.

| page | what it is for |
|---|---|
| `headless_chromium_recipe.md` | Running the measured render checks on a machine without root. Needed the first time you change a layout. |
| `hosting_a_prolific_study.md` | Reference for putting an online study on managed hosting. **Reference, not machinery** — this repo deliberately ships no deploy config. Irrelevant to a lab study. |
| `postgres_assumptions.md` | The gaps you inherit if you host on Postgres. Read before a hosted launch. |
| `group_matching_reference.py` | Reference implementation to read first if your design needs participants matched into groups. |

## 1. The three controls

Everything a participant experiences comes from three independent switches at the
top of `settings.py`. Set them and most decisions are made for you:

- **Study type** — `prolific` or `lab`. Recruitment plumbing only: ID capture and
  completion-code redirects for Prolific, bank details and demographics for lab.
- **Debug** — comes from the environment, not the file. `OTREE_PRODUCTION` unset
  means debug on (skip buttons, quiz answers visible). Production can never ship
  those, because you cannot set the flag by accident in a config.
- **Pilot feedback form** — its own switch, on for a pilot or friend test, off for
  the real run.

They do not interact: a Prolific-configured study can be debugged with every
module on. `README.md` has the full parameter table.

## 2. Before a real launch

Run **`python3 scripts/prelaunch_check.py`**. It is the static config guard, it
takes a second, and it fails on the things that actually go wrong: completion
codes still set to `REPLACE_*`, `DEBUG` still on, testing loosenings left in
(`verify_quiz=False`). It also prints on every server start, so you cannot miss
it.

If your study already has participants in its database, also run
**`scripts/predeploy_check.sh <copy-of-live-db.sqlite3>`** before deploying new
code. It boots the candidate build against a copy of the live database and walks
a real mid-flow participant through it. A fresh install cannot detect a broken
upgrade path, and oTree has no migrations, so this is the check that catches the
failures that only exist for people who started before your change. **It only
works on sqlite** — see `postgres_assumptions.md` if you are hosted on Postgres.

## 3. Looking at your instructions without running a session

`python3 intro/generate_instructions_preview.py` writes three self-contained
files into a gitignored `previews/` directory: a long HTML with every block on
one page, an interactive HTML that steps through one block at a time with a
treatment switcher, and a PDF. No server, no session, no database. Email them to
a coauthor or mark up the PDF on paper.

Pass `--config .preview_state.json` to reuse saved settings; without it the
generator waits for you to fill in a form in the browser.

## 4. Checking a change

`README.md` has the full table of what each kind of check is and is not evidence
of. The two rules worth knowing before you start:

- **Bot tests passing is not evidence that a browser works.** Drive form pages
  over real HTTP, including a submit with the JavaScript-filled hidden fields
  left empty — that is what a participant with a blocked script sends.
- **A layout or copy change needs a measured render check, not a look.**
  `tests/render_check.py` drives real headless Chromium at three viewports and
  asserts on element geometry and rendered pixels. Layout failures produce no
  error at all: nothing returns a 500 and no test goes red while the participant
  gets a broken page. On a machine without root, the recipe that makes this
  possible is `headless_chromium_recipe.md`.

## 5. Money: there is one ledger

Everything a participant is owed ends up in **`participant.payoff`**, written
once by `outro.compute_final_payoff` from the show-up fee plus whatever the task
paid. The admin Payments figure is then the amount you actually owe.

Two things will refuse to boot rather than let a second ledger open, because both
are quiet in a way you would only notice at payout:

- writing oTree's per-round `player.payoff` (`payoff_guard.py`);
- setting oTree's built-in `participation_fee` to anything but 0
  (`fee_guard.py`).

**If you are copying a study that already sets a participation fee, it will not
boot until you move that money into the ledger** — put it in `showup`, or into
the `earned` computation in `outro`. That is deliberate: oTree adds
`participation_fee` on top of `participant.payoff` wherever it reports payment,
so leaving it set splits what you owe across two numbers that no report shows
together.

One gap to know about: an experimenter can still edit the fee on a running
session from oTree's own admin page. No boot check can see that. If you pay from
the admin Payments page, do not let anyone touch that field.

## 6. Running it for participants

**A lab study needs none of the hosting material.** Run it on the lab machine or
a local server, bind a session to the room, and you are done — `scripts/start.sh`
binds the room without stranding anyone mid-experiment.

**An online Prolific study needs a host.** This repo deliberately contains no
deployment configuration; `hosting_a_prolific_study.md` is a written record of
what such a deploy needs and what to watch for, so it can be implemented when
somebody decides to. Read `postgres_assumptions.md` alongside it.
