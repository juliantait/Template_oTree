# Decisions: Build, deploy and databases

Read when you touch the Docker image, `/health`, build provenance, `start.sh`, the predeploy check, boot initialisation or the database backend.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## `/health` is a verdict a machine can act on, `verify_deploy.py` is the only thing that fails on a stamp, and appending a route to oTree has ONE implementation — 2026-08-23

The second half of the build-provenance work. Its first half asked *"what code
did this participant run?"*; this half asks *"did that deploy actually work?"* —
the question that was unanswerable when a Railway deploy reported SUCCESS with
the container already exited, and when a build went out with its stamp silently
missing and looked perfectly healthy.

### One route installer, because there are now two callers

Appending a route to oTree's own app existed once, in
`experimenter_dashboard.install_dashboard_route`. `/health` needs the same
thing, and a second copy is the inverted collapsed-distinction defect CLAUDE.md
devotes a section to: one concept, two implementations, drifting invisibly until
an oTree upgrade moves the route table and only one copy is updated. So the
route-table half moved to **`core/otree_routes.py`** — importing `otree.urls`, the
mid-import-versus-drift split, the `routes` shape check, idempotency by route
name, extending both the table and a live `otree.asgi` router, and the
`INSTALLED`/`ALREADY`/`NOT_IMPORTABLE` vocabulary. **Rejected:** importing the
dashboard from `core/health.py`, which would make a deploy gate depend on an operator
convenience.

**The `AdminView` auth shape check STAYED in the dashboard**, and the split is
the point: it is about WHO MAY LOOK AT THE PAGE, which is that module's
commitment. `/health` deliberately has no auth at all, because a platform
healthcheck can present no cookie. Those are different commitments, not one
commitment two callers share. It now runs inside the route-builder callback the
shared installer invokes, so it still fires only when an install is really about
to happen — never on the idempotent path.

**The NOT_IMPORTABLE-versus-drift distinction was preserved exactly**, because
CLAUDE.md names collapsing those two as a worked example of the class.

Two guards are NEW, and both close silent failures the single-caller version
could afford not to have: a route built under a name outside the caller's
declared tuple is REFUSED (that tuple is what idempotency and the
installed-check are decided on, so such a route installs twice and reads as
absent), and a path already served under another name is REFUSED (Starlette
matches the first route that matches, so two handlers on one path means a deploy
gate reads whichever was registered first).

**Both install from the tail of `outro/__init__.py`, not early.** The brief
argued `/health` "wants to install early, since its job is answering while
things are still coming up". Measured, that is not available here: importing
`otree.urls` builds the whole route table, which walks every app's
`page_sequence`, so it cannot happen before every app module is imported, and
`otree.urls` is not importable at `settings.py` time at all. There is also no
window to close — the routes only need to exist before `otree.asgi` builds the
app, which is after every app import on every supported boot path.

**The global-lock exemption is per-endpoint, not per-installer.**
`/health` registers itself in oTree's `VIEWS_WITHOUT_LOCK`; the dashboard
deliberately does not. oTree serialises every request behind one lock, so a
health poll queueing behind a participant page turns a 20ms check into a
timeout, a platform reads the timeout as UNHEALTHY, and a container gets
restarted for being BUSY — an outage manufactured by its own monitoring. The
dashboard reads a whole session's rows and already accepts the lock's cost;
running it unlocked would buy an operator screen showing half-committed state.

### `/health`: the verdict, and everything it must NOT depend on

200 when the database answers AND a session is bound to the room; 503 otherwise.
Those two are what a participant's first click depends on, and the two 503
reasons are kept apart deliberately — "nothing has bound a session yet" is
normal and self-healing, "the database is unreachable" is the dead-application
case. One indexed query answers both, which also makes it cheap enough to poll.

**The build stamp and the pre-launch checklist ride in the body and touch the
verdict nowhere.** A build running testing values is a perfectly healthy
deployment — it is how every pilot runs and it is the state this template ships
in. If a testing value made this 503, a platform would refuse to promote every
rehearsal build, and the check meant to protect the real launch would be the
check everybody disables.

**Unauthenticated, so it publishes problem NAMES and never VALUES.** The
checklist's values include Prolific completion codes, and a code is money to
whoever finds it. The test asserts the names are present AND that no placeholder
value appears anywhere in the body — an absence-only assertion would pass
against a 404.

**A method check written into the handler was DELETED, not kept.** Measured
against starlette 0.14.1, `Route.handle` answers 405 before the endpoint is
called, so that branch was unreachable. Inert code that looks like a guard is
worse than none: the next reader believes it. The `methods=` argument is both
the declaration and the enforcement, and a comment at the Route says so.

**A fork with no room** gets a permanent 503, correctly for this template (the
room IS the entry point) and wrongly for a study handing out links directly.
That is stated at `health._readiness_reasons`, which is the one function such a
fork changes. **Rejected:** a settings knob, which would be a second axis for
something one predicate already answers.

### `verify_deploy.py`: the one sanctioned failure, kept thin by delegating

It compares the RUNNING build's stamp against the one just deployed and exits
non-zero on a mismatch. That is the whole reason it exists, and it is safe to
make provenance fatal here for reasons that hold nowhere else: a human runs it
by hand after a deploy, it is not in the application path, and it cannot take a
study down.

**The room binding is read from `/api/rooms`, not from `/health`**, even though
`/health` also knows — two independent witnesses, so a bug in `core/health.py` cannot
certify itself. The test stages exactly that: a `/health` claiming the room is
bound while the REST API says it is not, and the gate still fails.

**Frozen-config drift is DELEGATED to `predeploy_check.audit_frozen_session_configs`**,
not reimplemented. That function is already the one implementation, and it
already carries the two-severity rule and the named exemption; a second copy
here is the same defect class the installer extraction just removed. Both inputs
are asked of the DEPLOYMENT (`/api/session_configs` and the bound session's
config) rather than computed from the local tree — comparing a deployment
against our belief about it is the error the script exists to remove. Two limits
are stated rather than papered over: liveness cannot be computed over REST (the
audit's own rule is that unsure counts as live, which is also the truth for the
bound session), and only the BOUND session is audited, because auditing every
session is `predeploy_check.sh` against a database copy, before the deploy.

**It does NOT fail on the pre-launch checklist**, which spec §4(a) asked for.
`/health` carries only the boot banner's subset of it — the full
`prelaunch_check.py` hashes every file under `_static/` and imports the app,
which is absurd on a polled route — so failing a deploy on it would be a check
lying about its own coverage. The names are printed as information; the complete
guard is `prelaunch_check.py`, run in the launch environment.

**FROZEN_CONFIG is the one assertion that is NOT retried.** It is a pure function
of the bound session and the running build, and neither changes on its own;
waiting out the deadline to be told the same thing again is how a gate teaches
people to stop running it.

### The pre-launch check prints the stamp, and that is all it does with it

`prelaunch_check.build_line()` names the build being cleared for launch, next to
the PASS/FAIL verdict, and is deliberately not in the `problems` list. It is a
different claim from `settings.py`'s boot banner (which says what the SERVER is),
and it is the line a CI capture needs to answer "which build did we clear?" three
months later.

**Enforced:** `scripts/tests/health_test.py` (49 checks — the shared installer's
five outcomes including both new guards, the verdict flipping 503→200→503 in one
process, an unstamped build and a dirty checklist both riding a 200, the body's
key set asserted CLOSED so no participant field can arrive on an open route
unnoticed, and every block broken in turn to prove the route cannot 500);
`scripts/tests/verify_deploy_test.py` (34 checks — the real script as a
subprocess against a programmable stub, green path first and re-asserted last,
with every red case one field different from it);
`scripts/tests/dashboard_test.py` §A, whose patch target moved to
`otree_routes.import_urls` with the seam.

---

## Check 2b exempts `build_at_creation` from MISSING — by name, reported, and on the audit's own argument — 2026-08-23

Closes the item Phase 1 left open. `scripts/predeploy_check.py` check 2b treats
a key MISSING from a live session's frozen config as a FAILURE, so a study that
adopts build stamping while sessions are running would see it fail on
`build_at_creation` for ever — which contradicts "provenance is documentation,
never a gate".

**The exemption is granted ON the audit's own argument, not despite it.** 2b
fails MISSING because of a stated consequence: participants run WITHOUT the key
while `settings.py` looks correct, because `common.cfg` quietly substitutes the
shipped default. For `build_at_creation` that consequence cannot occur. Its only
reader, `common.build_at_creation`, is deliberately RAW and never routes through
`cfg` — precisely so that absent keeps meaning *"this session was created before
build stamping existed"* rather than being back-filled with the build running
right now. So there is no silent default, nothing for a participant to run
without, and nothing a recreation would repair. Absent is not a defect; it is
the designed meaning, and saying so is the record working.

**Reported, never skipped.** The finding moves to the informational `diffs`
channel and reads like the plain value differences beside it — what the session
has (`absent (MISSING)`), what the current setting is, and the named reason. A
silent skip would be indistinguishable from the audit not looking, which is the
failure mode that whole file exists to avoid, and it would hide the day somebody
adds a key that does not deserve the exemption.

**A NAMED DICT, `MISSING_IS_THE_DESIGNED_MEANING`, with the bar written next to
it:** the key must have exactly one reader, that reader must be raw, and absence
must be a meaning that reader acts on. If a key can fall back to a shipped
default, it does not belong. Adding an entry is an edit a reviewer sees — the
same friction `SOURCE_PRUNE` in `build_context_test.py` exists for. **The
exemption covers MISSING only**; a PLACEHOLDER still fails, because that is a
different finding and only one of the two has this argument behind it.

**Rejected:** exempting the key silently (indistinguishable from a blind spot);
dropping MISSING to a warning generally (that would disarm the check for every
key, including the completion codes it was written for); and doing nothing,
which was Phase 1's honest position but leaves a study unable to deploy while it
adopts the feature.

**Also settled, unchanged:** `scripts/write_build_info.py` still REFUSES a
commit that is not a real 40-character SHA, exit 2. Phase 1 flagged it as
arguably a third thing that "fails" and offered to drop it. Julian's ruling: it
stays. It is a deploy-time tool validating its own arguments before anything
ships, the worst case is an unstamped deploy (which runs perfectly), and a stamp
that is not a real SHA is worse than no stamp because no later reader could tell
it from a real one.

**Enforced:** `scripts/tests/predeploy_frozen_audit_test.py` — the exempted key
reported as information rather than a problem AND carrying its reason; a SECOND
key missing from the same session still failing, so the exemption is one key
rather than a weakening of the rule; and the dict emptied to prove the same
session then DOES fail, so the pass is the exemption working and not the audit
looking away. Measured end to end against the real
`_ai/live_data/db_generated_2026-08-18.sqlite3` as well
(`_ai/build_provenance/phase2_test_output/exemption_against_live_data.txt`),
which is the database Phase 1 measured the failure on.

---

## Build provenance is DOCUMENTATION, NEVER A GATE — and it is recorded in three places so their disagreement is the signal — 2026-08-23

Decided by Julian, from a spec written by the `exp_pilots` study after it shipped
the same feature. Two questions kept being unanswerable for anyone running a real
study: *"what code did this participant actually run?"* (a study collects data
across days and redeploys; without a stamp in the data the honest answer is git
archaeology) and *"did that deploy actually work?"* (Railway reported a deploy as
SUCCESS with the container already dead). The first is what this entry is about.

**A commit cannot contain its own SHA** — the SHA is computed over the commit's
content — so the stamp is written at DEPLOY, by `scripts/write_build_info.py`,
into `BUILD_INFO.json` at the app root, carried into the image by the
Dockerfile's `COPY . .`, and **never committed** (it is gitignored: a committed
stamp would describe the previous commit in the tree of the next one).
`core/buildinfo.py` reads it once at boot. The writer takes the values as **explicit
arguments and never shells out to git**, so it is testable in a container that
has neither. `build_number` is `git rev-list --count HEAD`: monotonic, derived
rather than stored, and the half a human can say out loud.

**THE OVERRIDING CONSTRAINT, and it overrides the incoming spec.** Nothing in
`settings.py`, the boot banner, the pre-launch check or any participant path may
fail, refuse, warn-as-error or change behaviour because a stamp is missing,
absent or wrong. An unstamped build is a perfectly valid build — it is the state
of every local run and every test run in this repo. The spec asked for a
launch-time gate that FAILS on a missing stamp; Julian rejected that for the
template. Consequences, deliberately: a missing `BUILD_INFO.json` reads
`unstamped` everywhere and is not a problem; the pre-launch banner prints the
stamp as information next to its `DEBUG=` line and never counts it as a problem;
**there is no on/off setting, because there is nothing to switch** — "off" is
simply not running `write_build_info.py` at deploy, at which point the whole
feature is inert.

**Two sanctioned exceptions, both outside the application path.**
`scripts/verify_deploy.py` compares the running stamp against what was just
deployed and exits non-zero on a mismatch — a command a human runs by hand after
a deploy, and the whole reason that script exists. And
`scripts/write_build_info.py` REFUSES to write a stamp whose commit is not a real
40-character SHA: that is a deploy-time writer rejecting its own malformed
arguments before anything is deployed, and the study that results is simply an
unstamped one. A stamp that is not a real SHA would be worse than none, because
no later reader could tell it from a real one.

### Three places, and the disagreement is the point

1. **`participant.build_sha` / `build_number` — the evidence**, stamped ON
   ARRIVAL from the RUNTIME build, at the same call that takes the treatment cell
   (`before.treatment_assignment.assign_on_arrival`, reached from
   `intro.instructing.get`). **Not at session creation**: a session outlives
   redeploys, so a creation-time stamp would claim every participant ran the
   creation-time build. That is the identical argument this template already made
   when treatment assignment moved to arrival (2026-08-18), which is why the two
   are taken at one call. Seeded blank at creation, so blank means "never
   arrived", `unstamped` means "arrived on a build with no stamp", and a SHA
   means what it says — three different facts, kept apart.
2. **`session.config['build_at_creation']` — one half of a comparison, not
   truth.** Frozen at creation; its name carries that.
3. **The session config's `doc` string**, built at import, which oTree renders
   read-only on the create-session screen (it is in oTree's `NON_EDITABLE_FIELDS`
   and the REST API rejects attempts to modify it), so an operator sees which
   build they are about to create a session ON.

None is trusted alone. **Divergence is INFORMATION, not an error** — a session
created on one build and serving another is what a mid-study redeploy looks like
from the data — and nothing anywhere styles it as an alarm.

### `build_at_creation` is a DICT, and it is read RAW

**A dict, not a string:** oTree turns every bool/int/float/str config value into
an editable text box on the create-session screen, and provenance an operator can
retype is not provenance.

**Read raw** (`common.build_at_creation`), never through `common.cfg`. `cfg`
falls back to the value shipped in `SESSION_CONFIG_DEFAULTS`, and the shipped
value of this key is *the build running right now* — so reading it through `cfg`
would report a session created before the key existed as having been created on
the CURRENT build: provenance invented by the very helper that protects every
other parameter, and indistinguishable from a true record. Absent must keep
meaning "created before build stamping existed". This is the second deliberately
raw read in `core/common.py`, next to `flag`, and for a *related but different*
reason — the comment at each says which.

### The `.gitignore` / `railway up` interaction, written down because it bites

`railway up` **honours `.gitignore`**, so the very line that makes the stamp safe
for git makes it invisible to that deploy: the build ships completely inert,
reports unstamped, and looks perfectly healthy. The fix (delete `.gitignore` from
the throwaway staging tree, write a `.railwayignore` instead) is documented in
`docs/hosting_railway.md` and pointed at from `.gitignore` itself.
The same `.gitignore` also excludes curl COOKIE JARS by pattern rather than by
name: they only ever arrive from ad-hoc debugging, one was committed in
`exp_pilots` holding a live admin session cookie, and the next one will not be
called `cookies.txt`.

**A known consequence, CLOSED the same day — see the check-2b entry above.**
`scripts/predeploy_check.py` check 2b reports a config key MISSING from a live
session's frozen config as a FAILURE, so a study adopting build stamping while
it has running sessions would see 2b fail on `build_at_creation` for those
sessions, at odds with "provenance never fails anything". It is now a NAMED,
REPORTED exemption (`MISSING_IS_THE_DESIGNED_MEANING`) rather than the silent
skip that was rightly refused here.

**Enforced:** `scripts/tests/build_provenance_test.py` (three legs: the pure
reader/writer, plus a STAMPED and an UNSTAMPED in-process run each walking a real
arrival, because the running build is fixed at import and no monkeypatch can
honestly simulate the other case); `scripts/tests/frozen_config_test.py`'s final
section, which goes red if anyone ever routes `build_at_creation` through `cfg`;
`scripts/tests/xss_escaping_test.py`, which covers the commit subject — free text
from outside the repo, rendered UNESCAPED by `{{ config.doc|safe }}`.

---

## The build context is checked in BOTH directions, and the must-survive list is derived from the source tree — 2026-08-23

`.dockerignore` in this template was already clean — `data/`, `db.sqlite3`,
`_ai/`, `.venv/`, `previews/`, `*.log`, `.env` and the `*.command` launchers were
all excluded, with the nested cases spelled `**/`. So the deliverable was never a
fix; it was `scripts/tests/build_context_test.py`, which keeps it that way. **A
clean `.dockerignore` is a state, not a property**: the Dockerfile is `COPY . .`,
so every directory anybody adds ships by default, and both ways of getting this
wrong are silent. A hazard that arrives (an `exports/` of participant CSVs, a
curl cookie jar, a database snapshot) fails nothing and is baked into an image
that keeps every layer forever; a line added to stop that, which also excludes
something the app renders from, produces a container that boots perfectly and
500s a live page — which is how `_templates` shipped EMPTY in the study this
template feeds while every source-tree test stayed green.

**The must-survive half is DERIVED FROM THE SOURCE TREE, not parsed from the
Dockerfile and not declared as a list of paths.** The brief offered those two
options; both are wrong here for concrete reasons. The Dockerfile is `COPY . .`
and names no template, asset or module at all, so parsing it for the app's
runtime material would produce an EMPTY requirement that passes against
anything — the vacuous-test failure this repo treats as worse than no test. A
declared list is the retyping problem: it is correct the day it is written and
silently wrong the first time somebody adds a template. So the requirement is
four derivations that update themselves — every `.html` in the tree, every
served file under `_static/` (with "served" taken from
`prelaunch_check.IGNORED_NAMES`/`IGNORED_DIRS`, the asset guard's own definition,
and cross-checked against the file count `hash_static()` itself reports), every
`.py` outside `scripts/`, and the `/app/...` paths the Dockerfile DOES name (the
boot path: `scripts/db_state.py`, `requirements.txt`). This template has no image
verifier to defer the list to, which is what `exp_pilots` parsed its from.

**The one thing that must NOT be derived is the prune list.** `SOURCE_PRUNE` is
declared in the test and must never be read from `.dockerignore`, because a
requirement derived from the ignore rules deletes itself: exclude `_templates/`
and the requirement that `_templates/` survive disappears with it, and every
widening approves itself. The cost is that excluding a new directory needs a
second edit, in the test, where a reviewer sees it. **That friction is the
mechanism, not an oversight.**

Three smaller decisions inside the same change:

- **Hazards are judged by CONTENT, not by filename.** `data_backup/`,
  `db.sqlite3.old` and a cookie jar saved as `jar` carry exactly the same
  participant answers, Prolific IDs and admin session cookie, and a name check
  misses all three. The detectors key on the SQLite magic bytes, the Netscape
  cookie-jar header, and an oTree export's header row — the last as a whole
  comma-separated FIELD, because a substring test flagged this repo's own prose
  on the first run.
- **`exports/` is newly excluded, and it was a real gap.**
  `scripts/export_data.py --out` defaults to the RELATIVE `exports`, so the
  documented way to export data during a run drops every participant's answers
  into the repo root, where nothing was excluding them from git or the image.
- **`BUILD_INFO.json` is the one gitignored file that must NOT be
  dockerignored**, and the `.dockerignore` header's own advice ("when you add a
  line to `.gitignore`, add it here too") is what would break it. Excluding it
  fails nothing: the build succeeds, the container boots, every page renders, and
  every deployed build reports itself unstamped forever.

**Rejected:** running `docker build` in the test (no daemon here, and it would
make the check un-runnable on the machine most likely to need it); and asserting
only that the hazards are gone, which is an absence-only test and passes against
a `.dockerignore` that excluded the whole application.

*Where enforced:* `scripts/tests/build_context_test.py`. Section B self-tests the
Docker pattern matcher against the semantics that bite (a pattern with no `/`
matches at the context root ONLY; `*` does not cross `/`; `**/` matches zero or
more segments), and section E proves every absence can go red — with no rules the
content scan finds the real databases, each detector is run against a synthetic
hazard AND a lookalike that must not flag, and five over-broad rule sets are each
required to break the must-survive half. `docs/README.md` §4 tells a researcher
when to run it.

---

## `start.sh` states a timeout class at every call site, and re-reads the room before calling a creation failed — 2026-08-23

Two changes to the host-side room binder, both ported from a crash in
`exp_pilots` on 2026-08-21, and deliberately NOT the rewrite that study's spec
describes. Its boot script is a different thing — a Python entrypoint run inside
the container. This one is bash and curl, run by a human or a launcher against an
already-running server, so it never had that script's bug and does not need its
structure.

**1. Two timeout classes, with no default to inherit.** `exp_pilots` ran its
220-seat session creation through the same 15-second timeout as its millisecond
health checks; creation legitimately takes minutes (oTree builds every
participant x round row inside the one request), the script read a slow SUCCESS
as a failure, and the container exited. This script had the mirror-image risk —
**no timeouts at all**, so a server that accepts a connection and never answers
hangs the lab launcher silently, with no message and nothing to look at. Both are
now impossible: `api()` takes its `--max-time` as its FIRST ARGUMENT, so there is
no shared default for a future call site to inherit, and each site names its class
(`READ_MAX_TIME`, 20s; `CREATE_MAX_TIME`, 600s). The structural half matters more
than the numbers — a generous creation timeout costs nothing when creation is
quick, and the only thing a tight one buys is an outage.

**2. A client timeout is not proof the POST failed server-side.** The same
`exp_pilots` crash left an ORPHAN SESSION behind, created by a request that
completed after its client had stopped listening. So a failed creation — a curl
timeout, or a reply that parses to no session code — now RE-READS the room before
reporting anything fatal, and reports the binding it finds instead of failing.
This is the reuse rule the whole script exists for, applied to its own failure
path: a retry that does not re-check binds a second session over a good one, and
every participant already holding a link to the first is stranded. **Rejected:**
a retry loop (the spec's shape). One re-read answers the question that was
actually asked, and re-running the script is already the safe recovery, because
step 1 reuses whatever is bound by then — which the FATAL message now says.

The limitation is stated rather than papered over, and it was MEASURED rather
than assumed: against a real oTree 6.0.15 server, the room binding appears only
when `POST /api/sessions` returns (creation is one transaction — a 1200-seat
`lab` session bound the room at t+3.75s and returned at t+3.74s). So one re-read
detects a creation that COMPLETED unheard; a creation genuinely still in flight
is honestly reported as unbound, and re-running the script is the recovery. In
practice the re-read is often served AFTER the creation anyway, because it queues
behind it — a 400-seat creation cut off at a 1s client timeout was found bound by
the very next read, with exactly one session in the database.

*Where enforced:* `scripts/tests/start_sh_room_bind_test.py` drives the real
script as a subprocess against a stub oTree REST server that can be slow on
demand — the only way to stage "bind the room, then withhold the reply". It
asserts on the server's POST COUNT rather than on what the script printed, since
"reusing it" printed while a POST went out anyway is exactly the bug the message
would hide. Section 8 asserts the structural half: no bare `curl` call site, and
every `api()` call naming a declared class.

---

## The predeploy check decides which database it touches in ONE place, and proves it before anything destructive — 2026-08-14

Found by the same sweep as the entry below, and fixed on Julian's instruction
before either was committed. `scripts/predeploy_check.sh` ran its degraded-mode
`otree resetdb --noinput` in a subshell that **inherited the environment**; the
line pinning the run to its own staged sqlite copy — `export
DATABASE_URL="sqlite:///$WORKDIR/app/db.sqlite3"` — sat *after* that branch. So
an operator with a live `DATABASE_URL=postgres://…` exported (the normal state of
a deploy shell) running the documented no-argument check had their live database
dropped and recreated, after which the run proceeded happily against the staged
sqlite file and **reported PASS**. Verified end to end before the fix: a seeded
session row went 1 → 0 and the gate exited 0 with `RESULT: PASS (DEGRADED)`.

**The severity is about where it sat, not just what it did.** This is the tool
whose entire purpose is preventing data loss before a deploy, it is destructive
in its *documented* mode, and the database it destroys is by construction the one
you are about to deploy to. The only thing standing between a Postgres operator
and this was whether `psycopg2` was importable — and a working Postgres
deployment necessarily has it.

**Root cause is the mirrored rule in CLAUDE.md — one concept, two
implementations.** "Which database does this check touch?" was answered twice:
by the shell (inherits ambient env, pins later) and by the helper, which never
set `DATABASE_URL` at all and relied on `os.chdir` — a lever that works *for
sqlite only*, since oTree ignores the path in a sqlite `DATABASE_URL` but honours
a Postgres one completely. Against an inherited Postgres URL the chdir lever is
inert. Two deciders, and their disagreement was destructive rather than merely
confusing.

**The decision:** one place decides, and the proof covers every decider.
`pin_database_url()` forces the URL onto the staged copy and **refuses** a
disagreeing one (a non-sqlite URL, or a sqlite URL naming a different file)
instead of overriding it silently — silence would hide an operator who believes
they are exercising their Postgres. `assert_engine_on()` then interrogates the
engine oTree actually built and hard-fails unless it resolves to the staged file:
declaration, then measurement, because for sqlite the environment variable is
only a statement of intent and the cwd is what binds. The shell pins immediately
after staging, **before any branch can run a destructive command**, and calls the
**same** proof through `predeploy_check.py --assert-engine-on` before its
`resetdb`. The helper pins and proves for itself too, because it is documented as
directly runnable.

**Rejected:** just moving the export above the branch. It fixes this instance and
leaves the second decider in the helper, and it leaves the proof covering only
one of the two — which is how this survived in the first place. A proof that
covers one decider is an invitation for the other to grow back at the next edit.

**Enforced:** `predeploy_check.py --assert-engine-on`, called by the shell before
its destructive step and by `check_boot` for itself — one function, two callers,
so the two processes cannot be proved against different rules. Demonstrated on
2026-08-14 against a real PostgreSQL 16: the pre-fix scenario destroyed a seeded
row and passed; post-fix the identical run leaves the row intact (`MUSTSURVIVE`,
22 tables) and still passes on its staged copy. The regression this is meant to
survive was simulated directly — the pin deleted, the proof left in place — and
the proof caught it: exit 2, `nothing was written`, live data untouched. Both
sqlite paths re-verified unchanged (upgrade mode with the `_ai/live_data/` (local only — `_ai/` is gitignored; not in a clone)
fixture: boot, schema, resume, fresh, no-JS and log-scan all pass, with 2b's
pre-existing frozen-config failure unaffected; degraded mode: PASS).

---

## Boot initialisation is decided by inspecting the database, not by a sqlite file — 2026-08-14

Found by the hosting review, which caught the same defect in `exp_pilots`'
`start.sh` and asked whether this template shared it. It did. The container's
CMD initialised on `[ "${RESET_DB:-0}" = "1" ] || [ ! -f /app/data/db.sqlite3 ]`
— **file existence as a proxy for "is this database new?"**. The proxy is only
equivalent to the real question when the database IS that file. Point
`DATABASE_URL` at a managed Postgres and the sqlite file never exists, so the
condition is true on every boot and `otree resetdb` runs against the Postgres on
every container restart. `otree/cli/resetdb.py` does `old_meta.reflect(bind);
old_meta.drop_all(bind)` — it drops whatever it finds, on whatever backend — so
that is a silent total wipe with no error in the log, discovered after a
session. On Railway/Heroku/Fly (ephemeral container filesystem, no volume) it
recurs on **every** restart; with a `-v <study>-db:/app/data` volume it fires on
the first boot and is then masked by an accident (below), which is worse, not
better, because the exposure comes back the day the volume is recreated.

**The proxy was not sound for sqlite either**, which is the part that makes
"just fix the condition" the wrong fix. Importing `otree.database` executes
`sqlite_disk_conn = sqlite3.connect('db.sqlite3')` at module scope —
unconditionally, *including when `DATABASE_URL` points at Postgres* — which
creates a **zero-byte file**. A zero-byte `db.sqlite3` is a file that exists and
a database that was never initialised; `-f` cannot tell those apart, so the old
guard would also skip initialisation and leave the server running against a
table-less database.

**The decision:** the guard asks the question it actually means — *does the
database oTree will connect to already contain oTree's tables?* — via
`scripts/db_state.py`, which uses **oTree's own engine** (`otree.database.engine`,
built from `DATABASE_URL` by the same code path the server uses, so it cannot
inspect a different database from the one the study runs on) and **oTree's own
table names** (`AnyModel.metadata`, not a hardcoded `otree_participant`, which
would be a second implementation of "what oTree's tables are called" and would
drift the day oTree renames one). Backend-agnostic by construction: the same
question has the same meaning on sqlite, Postgres and anything else SQLAlchemy
reaches. `RESET_DB=1` is unchanged and does not consult the probe.

**Four situations kept apart** (the collapsed-distinction rule; collapsing any
pair of them is how this class of bug destroys data): *no tables at all* →
initialise; *oTree's tables present* → keep; *tables present but none of them
oTree's* → refuse (resetdb would `drop_all()` somebody else's schema, or an
oTree database whose version named its tables differently); *cannot determine* —
unreachable database, missing driver, empty model registry, in-memory engine →
refuse. "I cannot see the database" is not "the database is empty": an
unreachable Postgres must never read as brand new. Both refusals stop the boot
non-zero and loudly. That bias is deliberate — a container that refuses to start
is a page in the log; a container that wipes a live study is a lost session.

**Rejected:** patching the condition to also test for a Postgres URL. It keeps
file existence as the sqlite answer (still wrong, see the zero-byte case) and
makes the guard a list of backends to remember, which is the shape that produced
this bug.

**WHAT THE GUARD IS ACTUALLY FOR — and it is not creating tables.** Relayed from
the `exp_pilots` fix (79d49c2) and verified here against otree 6.0.15: oTree
builds its own schema on every start. `otree.main.setup()` calls `init_orm()`,
which ends in `AnyModel.metadata.create_all(engine)` (otree/database.py:369), and
`create_all` is checkfirst-by-default — it adds missing tables and never drops or
alters an existing one. So `resetdb`-on-fresh is belt and braces; the server
would have built the schema anyway. The guard's only real job is NEGATIVE: to
stop `resetdb` running against a database that has data in it. That reframing is
load-bearing for the failure path — refusing to boot forfeits nothing the server
needed, because an unreachable database would have failed `create_all` too.

**Converged with the `exp_pilots` fix (79d49c2), which was written independently
against the same defect.** Three of its findings were taken:

- **The driver is part of this fix, not a follow-up.** `pip install otree` ships
  no Postgres driver, so without `psycopg2-binary` in the image the probe cannot
  connect, lands in the unanswerable branch and refuses to boot — a guard whose
  safe direction is triggered by our own missing dependency would fail 100% of
  Postgres deploys while looking like a database problem. Pinned to 2.9.12 to
  match. This had been written down as a "record, decide later" item; that was
  wrong, and the correction came from comparing against the other fix.
- **Waiting is not weakening.** A managed Postgres is very often not accepting
  connections at container start. The probe now retries a non-answering database
  (`DB_WAIT_ATTEMPTS` x `DB_WAIT_SECONDS`, default 30 x 2s) before calling it
  unanswerable, so refusal is the verdict after waiting rather than the first
  answer. Without it the guard converts every normal cold start into a failed
  deploy — which is how a safety mechanism gets switched off for being annoying.
  Only "did not answer" is retried; a missing driver, an empty registry, an
  in-memory engine or a foreign schema are answers already and fail at once
  (measured: 0s vs the full wait).
- **No password ever reaches a log.** Fatal banners render the URL through
  `repr(engine.url)` (SQLAlchemy 1.3 masks the password there; `str()` does not)
  plus a regex scrub of any `scheme://user:pw@` in driver messages and a literal
  replacement of the password read from `DATABASE_URL`.

Their fourth point — resolve the URL exactly as oTree does (`os.getenv` with the
`sqlite:///db.sqlite3` fallback, forcing sqlite paths back to the relative
`db.sqlite3` because oTree ignores the path) — **is satisfied here by
construction rather than by copying the rule**: this probe does not resolve a URL
at all, it imports `otree.database.engine`, the very object the server uses. A
second resolution is exactly the one-concept-two-implementations shape that would
drift, and with the same destructive consequence (bless one database, wipe
another). Demonstrated: with an initialised database in the CWD and
`DATABASE_URL` naming a *different, empty* sqlite file, the probe answers
`already-initialised` — it follows the CWD file, precisely as oTree does. The
corollary is that the probe must run with the server's CWD, which the CMD does.

**Also taken:** under `RESET_DB=1` the sqlite file is deleted only when the
backend is actually sqlite (`case "${DATABASE_URL:-sqlite}"`), since on a managed
database `resetdb` does its own dropping and deleting a stray file there would be
theatre. `RESET_DB=1` remains the only deliberate wipe path on any backend.

**Enforced:** nothing in CI — say so plainly. `scripts/predeploy_check.sh` is
sqlite-only by design (documented in its header: oTree ignores the path in a
sqlite `DATABASE_URL`, so isolation is achieved by CWD), no suite runs against
Postgres, and none of them boot the container, so **no automated check in this
repo would have caught the original defect or would catch its return.** What
exists instead is a manual proof, run on 2026-08-14 against a real PostgreSQL 16
(installed without root — recipe in the agent memory note `postgres-without-root`)
and a real sqlite database, driving the **actual CMD text extracted from the
Dockerfile** rather than a paraphrase:

| case | sqlite | Postgres |
|---|---|---|
| fresh/empty database → initialise | yes | yes (22 tables) |
| existing database → keep, data intact across restarts | yes | yes (3 restarts) |
| **the old condition**, same sequence | n/a | **row gone after 1 restart** |
| zero-byte `db.sqlite3` → initialise | yes | n/a |
| **dropped column preserved, NOT restored** | yes | yes |
| late-starting database (down at boot, up 14s later) | n/a | **waited 14s, then kept the data** |
| unreachable database → refuse, exit 1, nothing modified | n/a | yes (after the wait) |
| missing driver → refuse **immediately** (0s, no pointless retries) | n/a | yes |
| foreign (non-oTree) schema → refuse, schema untouched | n/a | yes |
| `RESET_DB=1` → full rebuild (dropped column comes back) | yes | yes |
| sqlite URL naming another file → follows CWD, as oTree does | yes | n/a |

The dropped-column case is the sharpest of these: a column removed by hand stays
removed after boot, which is direct evidence that no `resetdb` ran — and it still
boots, because oTree's own `create_all` does not repair columns either.

Two things remain UNVERIFIED and should not be read as covered: **Docker itself
was never run** (no image build, no real container boot, no `COPY` of
`scripts/db_state.py` — the CMD body was extracted and executed with `/app`
rewritten, and syntax-checked as `sh -c "bash -c '…'"`), and **no managed
provider was exercised** — the Postgres was local TCP with trust auth, so TLS
(`sslmode=require`) and connection-pooler behaviour are reasoned about, not
tested. The pooler case is the one most likely to behave differently, and it
fails toward refusal rather than toward wiping.

The Dockerfile comment states what the guard asks, why file existence was wrong,
and why the failure path refuses rather than initialises — because the condition
looks redundant next to a `-f` test and invites being simplified back, and
because a refusal invites being made permissive.

---

## A Postgres deployment has NO upgrade-path check — recorded as an open gap, not closed — 2026-08-14

Recorded on Julian's instruction while fixing the two Postgres data-loss defects
above, because **this is the gap behind both of them** and every study copied
from this template inherits it.

Everything this template has for "will the running study survive being upgraded
to this code?" runs on sqlite, and only on sqlite. `scripts/predeploy_check.sh`
pins itself to a staged **sqlite** file, validates its input by the sqlite magic
header, and proves its isolation with `PRAGMA database_list` — all sqlite-only,
all by design and documented in its header. The documented way to obtain its
input is `docker cp <container>:/app/data/db.sqlite3`, a file that does not exist
under Postgres. Every suite is likewise sqlite (`scripts/tests/otree_inprocess.py`,
`scripts/tests/render_check.py`), as is the `_ai/live_data/` fixture (local only — `_ai/` is gitignored; not in a clone) that makes upgrade
mode meaningful.

**So the one backend a hosted study actually uses is the one with no coverage at
all.** A study on Railway/Heroku/Fly runs on Postgres; its operator runs the
pre-deploy gate the documented way, lands in degraded mode — honest (it shouts
`THE UPGRADE PATH WAS NOT TESTED`) but empty — and deploys onto live participants
with the fresh-install checks only. The two outages this gate exists for (a
participant-vars key old participants never had; a session config frozen before a
parameter existed) are precisely what a fresh database cannot reproduce.

It is also **why both defects above survived**: each was destructive only against
Postgres, and no test in this repo has ever opened a Postgres connection, so
nothing went red.

**Closing it, in order:** (1) a **container boot test** — boot the image against
a Postgres URL, write a row, restart, assert the row survives. Smallest, highest
value, and the direct regression test for the defect that started this; it needs
Docker. (2) a **Postgres fixture** for the suites — a real server, which needs no
root (recipe: the agent memory note `postgres-without-root`), plus the driver,
now in the image. (3) a **Postgres mode for `predeploy_check.sh`**: the isolation
model changes shape rather than gaining a branch — `pg_dump` the live database
and restore into a **throwaway database**, the live-refusal guard becomes "the
target must not be the live database name", and `PRAGMA database_list` becomes
`SELECT current_database()`. That proof is now behind one function
(`assert_engine_on`), so it is one place to extend, not two.

**Enforced: NOTHING.** No test, no gate, no banner tells an operator that their
Postgres deployment is being upgraded without an upgrade check. The README's
Docker section now says so in words, which is the only thing standing here.
Working detail: `docs/postgres_assumptions.md`.

---

## `DB_NAME` in settings.py does not select Postgres — oTree 6 never reads `DATABASES` — 2026-08-14

`settings.py` sets `DATABASES = {...postgresql...}` when `DB_NAME` is in the
environment and a sqlite `DATABASES` otherwise. **oTree 6 never reads
`DATABASES`** — verified: zero references to the name anywhere in the installed
`otree` package (6.0.15). oTree 5 dropped Django; the backend is chosen solely by
`DATABASE_URL`. The block is a Django-era leftover that reads like a working
control, so somebody setting `DB_NAME`/`DB_USER`/`DB_HOST` expecting Postgres
silently gets sqlite. Same defect class as the two fixed above — a control whose
apparent meaning and real effect differ — but not destructive, so it is recorded
rather than changed in a hurry.

**Options for whoever settles it:** delete the block (simplest, matches how oTree
works); or keep the `DB_*` names as a convenience and have them **construct**
`DATABASE_URL` when it is not already set, so the documented knobs actually do
something. Either way the block needs a comment saying `DATABASES` is not
consulted, or the next reader will "restore" it.

**Enforced:** nothing. No check compares the configured backend against the one
actually in use. Detail: `docs/postgres_assumptions.md` item 4.

---

## The README documents that inert `DB_NAME` mechanism as if it worked — 2026-08-14

`README.md` ("Running the template") says Postgres is not needed *unless you set
`DB_NAME`*, and lists `DB_*` among the values to set via env in production. Both
halves teach the mechanism the entry above shows is dead. Recorded separately
because it is a second place to change, and changing the code without the prose
leaves the same wrong instruction in the file people actually read.

**Enforced:** nothing — prose is not tested. Fix it in the same change as the
entry above, whichever way that goes.

---

## A wrong-backend engine is reported as "the app failed to boot" — 2026-08-14

`check_boot` in `scripts/predeploy_check.py` wraps the in-process import and the
engine proof in one `try/except Exception` and reports any failure as *"the app
failed to boot against the database"*. A wrong **backend** is not a broken build,
and reading it as one sends the next person to debug their app instead of their
environment. The shared-`except` shape this codebase warns about, in its mild
form: nothing is destroyed, only misattributed.

**Partly addressed as a side effect of the predeploy fix:** `assert_engine_on()`
now names the backend explicitly ("oTree built a `postgresql` engine, not
sqlite") and `check_boot` re-raises `SystemExit`, so that case reports itself
accurately. What remains is the general shape — every other import-time failure
still collapses into one message.

**Enforced:** nothing. Worth splitting if that file is being edited anyway; not
worth a change on its own. Detail: `docs/postgres_assumptions.md` item 9.

---

## The config-drift check has two severities, so it stays trustworthy — 2026-08-13

The pre-deploy audit of frozen session configs FAILS on exactly two things —
a key missing from a frozen config, and a surviving `REPLACE_*` placeholder —
and merely *reports* every other difference.
**Rejected:** failing on any difference. A session legitimately runs older
thresholds and `static_version` changes on nearly every deploy, so an
all-differences failure fires every time, gets ignored within a fortnight, and
then catches nothing — including the real cases.
**Enforced:** `scripts/predeploy_check.py` (`audit_frozen_session_configs`);
its docstring carries the warning not to promote diffs to failures.
