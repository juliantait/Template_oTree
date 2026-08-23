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
| `running_on_prolific.md` | **Operating guide for a study running on Prolific** — the ID capture, the five completion codes, the device gate, what each ending does. Moved here from a top-level `prolific/` folder on 2026-08-16; it is an operating guide, not a conversion plan. Irrelevant to a lab study. |
| `conventions.md` | The design principles behind the template: what the parameter scheme is for, how the three controls interact, the naming rules. Moved from the repo root on 2026-08-16. Read it before adding a parameter or a page. |
| `skills_claude/` | Authoring playbooks for whoever (or whatever) edits the template: writing the task, the instructions, the quiz, the tests, and the Railway + Prolific hosting procedures. Kept as a group — start at `skills_claude/README.md`. |
| `experimenter_dashboard_brief.md` | The dashboard **as it was specified**, kept deliberately un-updated so the brief can be compared against what was built. Not a description of the code. |

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
(`quiz_verify=False`). It also prints on every server start, so you cannot miss
it. Its first line names the build it is clearing for launch — information
only; a missing build stamp never fails it (§7).

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

**A fresh clone has no saved settings** — `.preview_state.json` is gitignored.
Run `python3 intro/generate_instructions_preview.py --no-popup` once: it writes a
`.preview_state.json` template and exits, you edit the values, and every run after
that can use `--config .preview_state.json`. With neither flag the generator opens
a form to fill in, which is what `Preview_Instructions.command` does for you on a
first run — and which will appear to hang on a machine with no display.

## 4. Checking a change

`README.md` has the full table of what each kind of check is and is not evidence
of. The two rules worth knowing before you start:

- **Bot tests passing is not evidence that a browser works.** Drive form pages
  over real HTTP, including a submit with the JavaScript-filled hidden fields
  left empty — that is what a participant with a blocked script sends.
- **A change to what is in the repo needs a build-context check.**
  `python3 scripts/tests/build_context_test.py` computes the build context Docker
  would receive from `.dockerignore` and asserts **both directions**: that
  nothing local leaks in — no database, no curl cookie jar, no participant CSV
  export, judged by CONTENT so a renamed one is caught too — and that everything
  the app renders from is still there. Both failures are silent. An image
  carrying your participants' answers fails nothing and gets pushed to a registry
  that keeps every layer forever; a `.dockerignore` line that also excludes a
  template directory 500s a live page while every other test stays green (that
  happened, on a real study, to `_templates`). Run it whenever you add a
  directory to the repo or a line to `.dockerignore`. One thing to know before
  you export data: `scripts/export_data.py` writes to `exports/` by default, and
  that directory is excluded from both git and the image for exactly this reason.
- **A layout or copy change needs a measured render check, not a look.**
  `scripts/tests/render_check.py` drives real headless Chromium at three viewports and
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
boot until you move that money into the ledger** — put it in `payment_show_up`, or into
the `earned` computation in `outro`. That is deliberate: oTree adds
`participation_fee` on top of `participant.payoff` on the admin Payments page, so
leaving it set splits what you owe across two numbers. It does not appear in the
CSV export at all, so the split is invisible in your data.

**On Prolific, each ending has its own completion code** — completed, declined
consent, comprehension DQ, tab-monitor DQ and device screen-out. Only the
completed one auto-approves; the other four are REQUEST_RETURN codes that prompt
the participant to return the submission. Create all five before launch (the
pre-launch check refuses to start while any is still a placeholder) and give each
return code its own reason text. Full table: the README's "The five endings and
their codes".

One gap to know about: an experimenter can still edit the fee on a running
session from oTree's own admin page, and that lands in the session row in the
database — so no restart and no boot check will ever see it. That is treated as
an operator decision rather than something to block, but it is not invisible:
the pre-deploy frozen-config audit reads the session rows and reports the
difference, so it shows up as `participation_fee: frozen 3.00 vs current 0.0`.

## 6. Running it for participants

**A lab study needs none of the hosting material.** Run it on the lab machine or
a local server, bind a session to the room, and you are done — `scripts/start.sh`
binds the room without stranding anyone mid-experiment: it only creates a session
when the room has none, because binding a second session over a live one breaks
the links of everyone already mid-experiment.

Two things about that script worth knowing on a study day, both about a server
that is slow rather than broken. Creating a big session is genuinely slow (oTree
builds every participant x round row inside the one request), so the creation
call has its own generous timeout — `OTREE_START_CREATE_TIMEOUT`, 600s —
separate from the short one on the room read, `OTREE_START_READ_TIMEOUT`, 20s.
And if the creation call does time out, the script **re-reads the room before
reporting a failure**, because a client giving up is not proof the server did
nothing: the request may well have completed and bound the room. **Re-running
`start.sh` is always safe** — it reuses whatever is bound by then.

**An online Prolific study needs a host.** This repo deliberately contains no
deployment configuration; `hosting_a_prolific_study.md` is a written record of
what such a deploy needs and what to watch for, so it can be implemented when
somebody decides to. Read `postgres_assumptions.md` alongside it.

**`GET /health` answers "is this thing actually ready?"** — 200 only when the
database answers *and* a session is bound to the room, 503 otherwise, with no
login needed. It is not just for hosted studies: on a lab machine it is what a
launcher can poll before you open the door, and `curl -s localhost:8000/health`
is the quickest way to find out whether `start.sh` got a session bound. On a
hosted study, pointing the platform's health check at it is what makes the
platform refuse to promote a broken build — the snippet is in
`skills_claude/hosting_railway.md`.

## 7. Which build is running, and which build your data came from

Every study collects data across days and redeploys, and "what code did this
participant actually run?" has to be answerable from the data months later. So
the build is recorded in **three places**, and their **disagreement is the
point** — a session created on Monday and still serving on Thursday is normal,
not an error.

| where | what it means | authoritative for |
|---|---|---|
| `participant.build_sha` / `participant.build_number` | stamped **on arrival**, from the build that was actually running when that person started | **this is the evidence.** The only one of the three that is authoritative about a participant, and the one your analysis uses |
| `session.config['build_at_creation']` | what was current **when the session was made** | one half of a comparison, nothing more — a room session outlives redeploys, so this does not say what anybody ran |
| the build line on the **create session** screen | what the **server** is running right now, read-only | reassurance before you click, not evidence afterwards |

Blank, `unstamped` and a SHA are three different facts and stay apart: blank
means the participant **never arrived**, `unstamped` means they **did arrive**,
on a build carrying no stamp, and a SHA means what it says. `CODEBOOK.md` has
the analyst's version of this table.

**It is on by default, and nothing anywhere fails because of it.** A missing
stamp reads `unstamped` everywhere, on the create-session screen, in `/health`
and in the export. The pre-launch check prints the build next to its verdict and
never counts it as a problem; `/health` reports it and never lets it change the
200/503. That is deliberate: an unstamped build is a perfectly valid build — it
is the state of every local run and every test run in this repo.

**To turn it off, do nothing.** There is no setting, because there is nothing to
switch: skip the deploy step below, and with no `BUILD_INFO.json` the whole
feature is inert. Do not delete code to disable it.

**The deploy step that writes the stamp.** This is the part a study deploying by
hand will otherwise miss, and the symptom is that everything reads `unstamped`
for ever with nothing looking wrong. A commit cannot contain its own SHA, so the
stamp is **written at deploy time**, never committed (`BUILD_INFO.json` is
gitignored on purpose). Add one command to whatever puts your code on the
server:

```sh
python3 scripts/write_build_info.py \
    --commit       "$(git rev-parse HEAD)" \
    --commit-date  "$(git log -1 --format=%cI)" \
    --subject      "$(git log -1 --format=%s)" \
    --build-number "$(git rev-list --count HEAD)" \
    --tree-clean   true \
    --out          BUILD_INFO.json
```

It takes the values as arguments and never shells out to git, so it also runs
where there is no repository. **If you deploy with `railway up`, read
`skills_claude/hosting_railway.md` first** — `railway up` honours `.gitignore`,
so the very line that makes the stamp safe for git stops it ever reaching the
server. That file has the trap and the fix; it is not repeated here.

**After a deploy, run `python3 scripts/verify_deploy.py`** with the base URL and
the `BUILD_INFO.json` you just deployed. It asks the running server which commit
it is and fails if that is not the one you sent — the one assertion a health
check can never make, because a perfectly healthy container can be serving last
week's code. It is read-only, safe against production, and never requests a URL
that would consume a participant slot. This is the **only** place a build stamp
is allowed to fail anything, and it is a command you run by hand, not something
in the application's path.
