# Head-to-toe run: observations

A running log from an observed end-to-end run where a fresh Fable-5 bossman built
a study from this template, from the published resources page through to a
Prolific draft + Railway deploy, with only the human steps (test-as-participant,
publish) left. Purpose: feed concrete improvements back into the template and the
bossman/worker flow. Kept as observation, not instruction: what went right, what
went wrong, and the flow lesson each implies.

Run: Correlated Beliefs abstract study, cloned into `Correlated_Beliefs/exp_beliefs`,
built by `bossman-58` (Fable 5). Started 2026-08-18.

---

## Going wrong

### The bossman stalled on its first command because it was not in auto mode
Spawned in "accept edits on" mode, it hit a permission-approval dialog on the
first `python3` command (reading the design) and stopped dead. An autonomous
overnight run cannot survive this: every command, worker spawn and cron setup
would block on a human.
**Flow lesson:** a bossman meant to run head-to-toe autonomously must be in
bypass-permissions / auto mode from the moment it is spawned. Worth making that a
stated precondition of kicking off an unattended run.

---

## Going right

### The resources-page path works end to end
Once in auto mode, the bossman did exactly the intended "get the template like a
real user" step: it fetched `https://juliantait.eu/otree-template.html`, used the
`git clone https://github.com/juliantait/Template_oTree.git` command published
there, and cloned into `Correlated_Beliefs/exp_beliefs`. Verified on disk: a real
clone with `origin` pointing at the GitHub repo, at the current template head
(commit `5aaa3c1`) — not a disk copy, and current to the latest push.
**Flow lesson:** publishing the template behind a plain `git clone` on the
resources page is enough for a fresh agent to bootstrap correctly. No special
tooling needed.

### It learned the template from the template before planning
Immediately after cloning it went to "learn the template's conventions from
itself" (read the skills, conventions, codebook) before writing its plan, rather
than guessing. The intended discover-from-the-template behaviour held.

---

### It orchestrated parallel workers with disjoint file ownership, unprompted
Given headroom to run more workers, it did not fan out blindly: it split work by
FILE OWNERSHIP and said so in each brief, telling the first implementer in writing
not to create or edit `scripts/compute_bonuses.py` or its tests because a second
worker owned those files. That is the exact discipline that keeps parallel workers
on one folder from clobbering each other, and it applied it on its own. It also
armed a short self-monitor plus a 20-minute cron backstop (autonomy as briefed)
and rode out a transient API overload with a retry rather than stalling.
**Flow lesson:** a capable bossman applies disjoint-ownership parallelism without
being told the mechanics; the brief only needed to grant the headroom.

### It inherited and used the fork skeletons and template patterns, unprompted
The strongest head-to-toe signal so far. Without being told the mechanics, the
build:
- started a fresh `DECISIONS.md` and pointed the `CODEBOOK` at this study (the
  two fork skeletons shipped today), rather than carrying the template's own logs;
- assigned the role, sender type and observer claim ON ARRIVAL (the
  treatment-on-arrival pattern the template ships), not at session creation;
- computed a deferred Prolific bonus from the export, and set the design
  constants (six cells, one round, GBP points) as study parameters.
`main/` (the core task) was built, tested and committed as step 3; workers then
fanned to outro and the instructions. The cron backstop fired on schedule
throughout.
**Flow lesson:** the skeleton-inheritance investment (fresh DECISIONS.md +
analyst-first CODEBOOK on fork, the on-arrival assignment, the writing guides)
pays off directly. A fresh bossman picks them up from the template alone.

### Timing convention for measuring a run
Use `exp_beliefs/.git/config` (the clone moment) as BUILD start; container-up as
total-wall-clock start. The clone is the first on-disk artifact, but design-reading
and any setup stall precede it, so the two markers measure different things.

### Minor: a text-keyed milestone waiter false-triggered on the bossman's own brief
Its supervision loop, watching for a phrase to signal a worker was done,
matched that phrase where it appeared in the bossman's own instruction, and
fired early. It caught this and re-armed on a file's existence instead.
**Flow lesson:** key a milestone waiter on an ARTIFACT (a commit landing, a
review file existing), never on a text phrase that also appears in the brief that
set up the wait. Small, self-corrected here, but a repeatable trap.

### It handled the dangerous shared-project deploy correctly, guardrail followed
The highest-stakes step: deploying next to a LIVE study (exp_pilots) in a shared
Railway project, where wiring the wrong database plus RESET_DB wipes real
participant data. Verified by a read-only Railway query from the observer side: it
created a SEPARATE service (`exp-beliefs`), left `exp-pilots` untouched, wired
`DATABASE_URL` to the SPARE `postgres-idbo` (not the live `Postgres`), set
`OTREE_PRODUCTION=1`, and did not leave `RESET_DB` standing.
**Flow lesson:** a clear, specific safety brief (create a service not a project,
use THIS spare database, never touch that service) is enough for a fresh bossman
to execute a genuinely dangerous shared-infra deploy safely. But the danger must
be named explicitly in the brief; it is not discoverable from the template. This
guardrail came from a sibling bossman that owns the live study, not from the
template docs, which is itself a gap worth closing (the hosting skill could warn
that a shared project with a live study needs a separate DB).

### The orchestrator's own context stayed light the whole run
bossman-58 never compacted across the run (verified: its transcript carried no
compaction marker, and its context percentage rose monotonically from 16% to ~32%,
never sawtoothing back). Because it delegated every heavy task (reading the design,
writing code, running suites) to workers in their own sessions, the bossman held
only short briefs and short status reads.
**Flow lesson:** an orchestrator can drive a multi-hour build without compacting;
the workers carry the context weight. Budget the bossman's context by how much IT
reads, not by how big the job is.

## Outcome: complete, stopped cleanly at the human line

The fresh bossman took the study from a published `git clone` to a live Railway
deploy plus an unpublished Prolific draft, stopping exactly where a human is
unavoidable.

**How long it took** (build start = `.git/config`, total start = container-up):
- Container up: **17:10 UTC**.
- Build start (clone landed): **17:51 UTC** (the ~40-min gap before it = observer
  setup plus the auto-mode stall, not building).
- Done (deploy + Prolific draft + handoff committed): **~21:05 UTC**.
- So **build ~3h15m** (clone to deliverables), **total ~3h55m** (container-up to
  done). Worker cost ~$937.

**Delivered, verified:** experiment built from the published template, two Fable-5
reviews, all suites green; a live Railway SERVICE (`exp-beliefs`,
`lantern-lbopwbzs.up.railway.app/room/study` returns 200) on the spare
`Postgres-iDbO` with `exp-pilots` untouched; an unpublished Prolific DRAFT ("A
Study on Decision Making", 150p / 10 min, not underpaying, 120 places <= 240
seats, five codes); a `LAUNCH_HANDOFF.md`; secrets in `MacMini/`; cost and memory
logged.

**Good judgment worth keeping:** it marked every design constant PLACEHOLDER for
Julian to confirm rather than inventing final values, exactly the restraint the
template's helpfulness warning asks for. It did not overstep into what is the
researcher's decision.

**Human steps it correctly left (in order):** confirm the placeholder design
constants; write the Prolific description / filters / ethics wording; Preview and
Test-as-a-participant (the only end-to-end money-path check); publish in waves.
