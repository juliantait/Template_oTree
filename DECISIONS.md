# Decisions

The procedural and design decisions behind this template, in one place. Each
entry: the decision, the date it was settled, why (the concrete failure or
argument that drove it), what was rejected where an alternative was genuinely
considered, and — the field that matters most — **where it is enforced**: the
test, guard or CSS rule that holds it in place, or a plain admission that
nothing does and it relies on people remembering. Newest first. Entries are
deliberately short; code comments and the linked working documents hold the full
working.

---

## The screen-out exit says it is FINAL, because the code that frees the place forecloses the return — 2026-08-15

Decided by Julian, the same day as the per-population completion codes, and it
is the consequence of that decision rather than a separate one.

**What forced it.** The soft wall was designed around a re-decidable verdict: a
participant turned away at entry is HELD on `before.welcome`, the page's primary
ask is "switch to an accepted device and come back", and returning on an
accepted device before consent CLEARS the screen-out. The reversal recorded
above gave the screen-out its own completion code, chosen because an open
submission is limbo — it occupies a place and tells Prolific nothing. But a
completion code RETURNS the submission, and a returned submission can never be
retaken. **So for anybody who presses the exit, the route the page invites them
to take is gone.** Freeing the place was judged the better trade; being silent
about what it costs the participant was not.

**What the page now says**, in the `show_return_link` branch of
`before/screened_out.html`: *"Once you return it you cannot take part again,
even on an accepted device."* It replaces *"Once you do this you will not be
able to take part later"* — true, but on this page it reads as "not later
today", three inches under an invitation to come back on a different device.
The new sentence names the route it closes.

**What was deliberately NOT done.** It is one sentence in the page's existing
register, not a warning banner, and the control is untouched: it stays
`.exit-button`, never `.next-button`, because `global.js` Enter-clicks the first
`.next-button` on a page and an irreversible exit must not be one keystroke
away. The primary ask is still switching device, and the switch-device branch
still says *"Do not press the button below."*

**The honest statement of what survives.** The soft wall still exists and still
clears on an accepted device before consent — but only for somebody who has NOT
taken the exit. Those are now two different populations and the page has to be
readable by both.
**Enforced:** `tests/screenout_softwall_test.py` asserts the accepted-device
clause specifically (not merely that some permanence wording exists, which the
old sentence would also have satisfied), that the control carries
`.exit-button`, and that the way out is a real `<a href>` needing no script;
`tests/render_check.py` asserts the switch-device branch's "Do not press the
button below".

## The website's screen previews are GENERATED from the template, not drawn — 2026-08-15

Decided by Julian. The academic site shows four screens of the study (welcome
lab, instructions, a decision screen, results lab). They used to be hand-written
one-off HTML snapshots, and by August they no longer looked anything like the
template.

**The failure is not that they were wrong; it is that nothing could tell.** A
snapshot has no relationship to the CSS it imitates, so when a shared component
moved, the snapshot went on rendering perfectly — just as a picture of an older
study. No error, no failing test, no visible symptom: the same silent-drift
shape as the client-side traps in `CLAUDE.md`. So the previews are now DERIVED —
`previews/build_site_previews.py` inlines `_static/global/css/` **verbatim**
(the stylesheets are never re-typed) and embeds the logos as data URIs, giving
one standalone file per screen with no external reference of any kind, because
they load in an iframe on a static site with no access to this repo.

**Source is tracked; output is not.** The script and
`previews/site_preview_bodies/` are in the repo; the four built files land in
gitignored `_ai/site_previews/`. A generator living in `_ai/` would die with the
container and the next person would hand-write another one-off — which is the
defect, restored.

**The screen is drawn on a fixed 1920x1080 canvas inside a nested `srcdoc`
frame**, scaled to the iframe by `calc(100vw / 1920px)` (a length over a length
is a number; no script, so it survives scripts being blocked). The frame is not
decoration: the template sizes itself in viewport units — the card is `88vh` and
`base.css` tightens its rhythm below 820px of height — so "what the template
looks like" is only defined at a given screen size, and rendered raw a small
iframe would be a different, clipped layout from a large one. Inside the nested
context those units resolve as they do for a participant on a 1080p display.

**Two honest departures, stated in the artefacts themselves** rather than only
in the hand-off message the files outlive: the decision screen is INVENTED (this
template ships no game screen — `main/game.html` is a placeholder — so it is
built only from real components, and must not be copied back into `main/`), and
the results screen is TRIMMED (the real page is the longest in the study and
genuinely scrolls inside its card; with the payoff table open it does not fit
16:9 at any size, so the greeting line is dropped and a short session shown).
**Enforced:** `previews/check_site_previews.py` — measured in headless Chromium
at four 16:9 sizes with JavaScript on and off: no external request, the canvas
viewport is the one composed for, no cut-off scroll region, the card fills, and
the lab screens name Prolific in no **rendered** text (asserted on `innerText`,
paired with a minimum-text assertion, because an absence check alone passes
against a blank page). Re-running after a CSS change is enforced by nothing —
it is a note in `CLAUDE.md`'s styling section and in `previews/SUMMARY.md`.

## Every ending population gets its own completion code — 2026-08-15

Decided by Julian. Five endings, five codes, one per population:

| key | population | Prolific action |
|---|---|---|
| `prolific_cc_code` | completed | **auto-approve** |
| `prolific_noconsent_code` | declined consent | request return |
| `prolific_dq_quiz_code` | comprehension DQ | request return |
| `prolific_dq_tab_code` | tab-monitor DQ | request return |
| `prolific_device_code` | device screen-out | request return |

**Why not one shared `DQ-` code, which is what this replaces.** A shared code
**collapses two populations irreversibly, on a system we do not own.** Once a
comprehension failure and a tab-monitor ejection have both submitted under one
code, Prolific's submission list cannot tell them apart and nothing downstream
recovers it — not an export, not a rerun, not a support ticket. This is the
collapsed-distinction rule applied to a third party: the usual version of that
rule costs a debugging session, and this version cannot be fixed at all, which
is why it had to be got right before a launch rather than after one.

**THIS REVERSES the codeless screen-out** recorded on 2026-08-12 (marked
SUPERSEDED above, with its reasoning preserved). That decision was right that a
completion code closes a submission and a returned submission cannot be retaken.
It was wrong that leaving the submission open was therefore kind: a bare
researcher URL leaves it in limbo, occupying a place, telling Prolific nothing.
A **REQUEST_RETURN** code is a different instrument — it prompts the participant
to return the submission, which frees the place. So the screened-out exit is now
`prolific_device_code` rendered as a full completion URL, and the
`prolific_screenout_return_url` setting is gone: a URL that embeds a code, plus
a code key, is one value in two places and they drift.

**Rejected:** keeping `prolific_screenout_return_url` alongside the new code as
an override. Two sources for one value is the defect this repo has spent the
week removing.

**THE HAZARD THE SPLIT CREATES, AND THE RULE THAT CLOSES IT** (bossman-52, same
day). Splitting the DQ code invents a failure mode that could not exist while one
code served both populations: **if the displayed reason text and the completion
code are derived independently, they can silently disagree** — a comprehension
failure reads the quiz explanation and carries the TAB code back to Prolific. No
error, normal-looking data, and the population distinction corrupted at exactly
the point it was created to exist, findable only by reconciling submissions by
hand. **So the message and the code must come from ONE read of the cause.**

Verified today, and it is the safe shape already: `outro.dq_cause` is the only
implementation (`outro/__init__.py:51`); `Ended.vars_for_template` passes
`dq_cause=dq_cause(player)` and `outro/Ended.html` branches on that variable;
`completion_link` does `cause = dq_cause(player)`. No template reads
`ai_safety_disqualified` or `comprehension_disqualified` directly — checked
across every `.html` in the repo. Two calls to one deterministic function in one
request cannot disagree; two implementations could, which is why the invariant is
written on `dq_cause` itself. **The next reader will see two calls and want to
refactor one away — that is the thing not to do.**

**Enforced, and each part separately verified:**

- `settings.PROLIFIC_CODE_KEYS` is the ONE enumeration; `_prelaunch_problems`
  iterates it rather than keeping a copy, so a sixth ending cannot ship
  unguarded. **Mutation-tested key by key**: with the other four set to
  plausible real codes, leaving each one placeholder in turn is named by the
  check — and only that one (no false positives). The old three-key enumeration
  would have shipped the two new codes completely unguarded while reporting
  clean, which is the trap this template keeps meeting.
- The frozen-session audit needs no enumeration: it walks every key in the
  current config, so the new keys are covered the moment they exist.
- `tests/completion_codes_test.py` — **one browser-driven journey per ending**,
  each asserting it carries ITS OWN code and NOT the other four. 30 checks, all
  passing. The absence half is the point: a disqualified participant who can
  read the COMPLETED code out of page source can self-approve and be paid, so
  every path checks all four others, and the codes are injected per page rather
  than bundled into the template context.
- `tests/render_check.py` leg AD asserted the screen-out carried NO code; that
  expectation is now reversed to assert it carries the DEVICE code and none of
  the other four.
- Two test-construction faults were found and fixed while writing the above,
  both worth knowing because they would have produced false confidence: a walker
  using the default `python-requests` User-Agent is classified `unknown` and is
  SCREENED OUT by `allowed_devices=['computer']`, and setting a DQ flag on a
  participant still at the consent page does not put them on their ending. In
  both cases the code assertions passed against the wrong page until the journey
  itself was asserted.

## `participation_fee` ships 0, and a boot guard holds it there — 2026-08-14

Decided by Julian. oTree's built-in `participation_fee` is a SECOND payment
channel: it is not part of `participant.payoff`, it is added on top of it by
`Session._get_payoff_plus_participation_fee` (otree/models/session.py:242-248),
which feeds the admin Payments page (`otree/views/admin.py:274`,
`templates/otree/SessionPayments.html:46`) and the MTurk payment table. It does
NOT reach the CSV export — verified against 6.0.15, the participant column list
ends at `payoff` (`otree/export.py:76-96`) — so a fee is invisible in the data
and visible only where a human reads off what to pay, which is worse. This template keeps **one payment ledger** — the base is
`showup`, which `outro.compute_final_payoff` folds into `participant.payoff` with
the bonus, so the admin figure equals the amount actually owed. A non-zero fee
splits that across two numbers computed by different code in different places,
which is the condition the single-ledger decision exists to prevent.

**Why a guard and not just a zero in the config.** A zero in a config is a
convention, and an unenforced convention in a template drifts the first time
somebody copies it. `participation_fee` is a standard oTree knob that the
official docs and tutorials set; a researcher starting from this template will
meet it there and set it in good faith, with no error to say the payment record
has quietly split. This repo has already had one convention-only rule turn out to
be nothing (three documents calling oTree's `player.payoff` raise "enforcement"
when it fires inside a participant's request).

**Boot, never request time** — the `payoff_guard.py` precedent, and the reason is
the same: oTree has no migrations, so an upgrade under live sessions is how every
study built from this template is actually deployed, and a check that fires in a
request is a dead page for whoever is mid-study. `fee_guard.py` is called from
`before/__init__.py` beside the other two boot guards.

**THE KNOWN COST, ACCEPTED WITH EYES OPEN.** A study copied from this template
that already sets a `participation_fee` **will refuse to boot** until the money
is moved into the ledger (into `showup`, or into `outro`'s `earned`). A real cost
paid by a real person — and the trade is deliberate: the alternative is a study
that runs happily with a payment record that is wrong in a way nobody notices
until payout, when somebody is underpaid.

**What it does NOT catch — a boot SOURCE scan cannot see a running session.**
oTree's `SessionEditPropertiesForm` (otree/views/admin.py:212) exposes
`participation_fee` as an editable field on a LIVE session, and `form_valid`
(admin.py:255-261) writes it into `session.config`, a DATABASE COLUMN on the
session row (`Column(_PickleField)`, models/session.py:35). The value lives in
data, so **no restart will ever catch it** — the guard passes while the session
carries a fee. Verified against 6.0.15, and measured: the ledger stayed at
€10.00 while the Payments figure moved to €13.00.

**Policing that is deliberately out of scope** (Julian + the hosting review): an
operator editing a live session is an operator action and is trusted. A
dashboard warning was proposed, costed, and CANCELLED. What was required instead
is that it be visible rather than silently clean — and it already is, for free,
because `predeploy_check`'s frozen-config audit reads the session ROWS rather
than the source and reports it as a plain value difference (`frozen 3.00cu vs
current setting 0.0`, confirmed on a real edited session). Check the artifact,
not the recipe; this guard is the recipe half and must never be written up as
more than that.

**Rejected:** relying on `AUTO_TABULATE_PAYOFFS`-style enforcement from oTree
(there is none for this field), and a runtime check in `outro` (same dead-page
trade the payoff guard exists to avoid).

**Enforced:** `fee_guard.assert_participation_fee_is_zero()`, called at boot from
`before/__init__.py`. Two halves: the RESOLVED configs (`SESSION_CONFIG_DEFAULTS`
must carry an explicit 0; a per-config entry may omit the key but must not set a
fee) and an AST scan of app packages and shared root modules for
`participation_fee` written as anything but a literal 0 — assignment, attribute,
`config['participation_fee']`, a `dict(participation_fee=…)` keyword, or a dict
literal. The scanned file list comes from `payoff_guard.files_to_scan`, not a
second copy of the rule, so the two guards cannot disagree about which
directories are apps. Verified 2026-08-14: the template boots clean (15 files
scanned); a fee in the defaults, an absent key, and a per-config override each
refuse the boot; a config omitting the key inherits correctly; all seven source
shapes fire and a literal 0, a `0.00` keyword and a *read* of the key do not.
Proven end to end with `otree resetdb` — the shipped template exits 0, and with
`participation_fee=2.50` the boot fails with the guard's message.

## Tracked docs are for whoever runs a study; `_ai/` stays local and is marked as such — 2026-08-14

Decided by Julian, after the sweep for the entry below found that tracked
documentation pointed into gitignored `_ai/` about fifteen times — nine in
`DECISIONS.md`, five in `README.md`, one in `CLAUDE.md`. Nothing under `_ai/` is
tracked (`git ls-files _ai/` returns nothing), so **every one of those was a dead
link in a clone**, including the recipe `CLAUDE.md` sends every agent to before
running a render check. A template whose first-read files point at absent
documents teaches the copy to distrust its own instructions.

**The test applied** is not "is this useful?" and not even "does a copy need
it?", but **"does a person running a study need it?"**. That reframing is what
made the split easy: an audit of how the dashboard was built is scaffolding no
matter how good it is; a recipe for running the render check without root is
something a researcher needs on day one.

**Three files moved to a new tracked `docs/`**: `headless_chromium_recipe.md`
(eight tracked references, and without it a copy cannot run the measured render
checks this template calls the only evidence a layout change works),
`postgres_assumptions.md` (item 8 is a gap every copy inherits), and
`group_matching_reference.py` (`main/__init__.py` tells whoever implements group
matching to read it first). Two were written into `docs/`: a researcher-facing
`README.md` — the front door, in the terms somebody running a study thinks in
rather than the terms we built it in — and `hosting_a_prolific_study.md`.

**Everything else stayed in `_ai/` and every reference to it now carries `local
only — _ai/ is gitignored; not in a clone`**, in one style, so a reader can tell
a deliberate absence from a missing file at a glance. `_ai/render_check/` and
`_ai/dashboard_render/` were deliberately NOT marked: they are output directories
created by running the checks, not documents to read, and marking them would
teach the reader that the tool is broken.

**Why `docs/` rather than the repo root or `skills_claude/`.** The root already
carries the six documents everybody is told to read; adding second-tier reference
beside them makes the first tier harder to see. `skills_claude/` is method
material addressed to an agent working ON the template, which is a different
audience from a researcher running a study. `docs/README.md` states the rule for
what may be added, so the next person has a test rather than a habit.

**Also settled, same theme — what belongs in a template at all.** Two
double-clickable macOS launchers were sitting untracked in the tree, having been
deliberately removed from the repo once already (`eb026e3`, 2026-07-23).
`GitHub_sync.command` is Julian's own sync convenience: kept on disk, added to
`.gitignore` by name rather than as `*.command`, so a launcher that IS template
material would still have to be ignored on purpose.

## `Preview_Instructions.command` is tracked — deliberately reversing `eb026e3` — 2026-08-14

Decided by Julian. `eb026e3` ("Remove local macOS launcher scripts from the
template", 2026-07-23) removed both `.command` launchers as personal tooling.
That was right for the file it removed and wrong as a permanent rule, and the
distinction is what the reversal turns on: **the launcher `eb026e3` removed drove
a stale copy of the generator; a launcher that drives the MAINTAINED generator is
template material.**

The removed one ran `previews/generate_instructions_preview.py` — a copy frozen
on 2026-05-28 inside the gitignored `previews/` OUTPUT directory, eleven lines
behind `intro/generate_instructions_preview.py` and writing the same filenames.
Double-clicking it silently replaced current previews with three-month-old
output. Deleting that was correct.

**What makes the rebuilt one travel:** every study copied from this template has
instructions, and the maintained generator is the only way to read them without
running a session — but it needs a command line, and *"I do not want to open a
terminal"* is a real requirement, not a preference to be argued with. A copied
study should not lose the no-terminal route. So the launcher is tracked, points
at `intro/`, resolves everything from its own `$SCRIPT_DIR` (no path from this
checkout), passes `--config .preview_state.json` when saved settings exist (the
generator otherwise opens a form and waits, which from a double-click looks like
a hang), and opens the interactive preview when it finishes.

**One thing it does NOT do, learned by measurement:** treat the generator's exit
code as the verdict. With no browser binary installed the generator writes both
HTML files correctly and still exits 1, because the PDF step failed. The launcher
therefore decides on WHAT EXISTS and reports the exit code only when nothing was
produced — otherwise it would tell somebody their previews were broken while they
sat there complete. (Found by dry-running it; the first draft had the bug.)

**Enforced:** nothing automated. The launcher carries a comment saying never to
point it into `previews/`, and the stale copy that caused the original problem is
still sitting in that gitignored directory for whoever looks there first.

**Enforced:** nothing automated — no check fails when a tracked file gains a link
into `_ai/`. `docs/README.md` carries the rule and the marking convention; that
is all that holds it.

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
under Postgres. Every suite is likewise sqlite (`tests/otree_inprocess.py`,
`tests/render_check.py`), as is the `_ai/live_data/` fixture (local only — `_ai/` is gitignored; not in a clone) that makes upgrade
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

## The README documents that inert `DB_NAME` mechanism as if it worked — 2026-08-14

`README.md` ("Running the template") says Postgres is not needed *unless you set
`DB_NAME`*, and lists `DB_*` among the values to set via env in production. Both
halves teach the mechanism the entry above shows is dead. Recorded separately
because it is a second place to change, and changing the code without the prose
leaves the same wrong instruction in the file people actually read.

**Enforced:** nothing — prose is not tested. Fix it in the same change as the
entry above, whichever way that goes.

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

## Ended.html carries no screen-out copy — deleted as unreachable, with the unreachability enforced — 2026-08-14

Decided by Julian (before-review N4), choosing deletion over the reviewer's
keep-both recommendation. The `reason == 'screened_out'` block in
`outro/Ended.html` — the four device-cause branches and the screened-out
title — duplicated `before/screened_out.html`'s live copy for a participant
who can never arrive: the soft wall holds a screened-out participant at the
entry page's own index precisely because oTree only moves forward, so walking
them to an outro ending would make the verdict un-liftable. A duplicate that
never renders can only drift from the copy that does.

**The deletion was not made on the unreachability claim alone.** This repo
has been bitten by untested claims (the 2026-08-13 monitor-coverage entry
below: four documents asserting something untrue), so the claim was made
ENFORCED in the same change: `tests/screenout_softwall_test.py` scenario 9
hammers a screened-out participant with forced submits and a direct
`/outro/Ended/` URL and requires every response to re-serve the held page.
If routing ever changes, the test goes red before a participant reads the
wrong page. Two second-line defences remain for that hypothetical future
gate: Ended's neutral else-fallback ("The study has ended for you") says
nothing false, and the shared footer include still picks the CODELESS exit
for `reason == 'screened_out'`, so their submission would stay open.

**What deliberately stayed:** `outro.was_screened_out` — a DIFFERENT
mechanism that looks related and is not. It is what keeps a screened-out
participant out of `is_completer`, so no future gate can hand them a
completion code; deleting it with the template branch would have been the
over-pull this entry exists to warn against. `Ended.vars_for_template`'s
`common.screenout_vars` spread also stays: the footer reads
`prolific_screenout_return_url` from it.

**Record check, done with the change:** no document claims the screen-out
exit code is written when the participant clicks the return link — it is
written at DECISION time (`common.set_screened_out`: a closed tab still
exports as screened out, not abandoned), and `set_screened_out`'s docstring,
the softwall test header and the footer include all state it correctly.

**Enforced:** `tests/screenout_softwall_test.py` scenario 9 (the deletion
guard); the header note in `outro/Ended.html` points at it.

## Explicit consent is its own flag (`explicit_consent`), split from `prolific_completion_redirects` — 2026-08-14

Decided by Julian, from the before-app review. Whether the consent page asks
an explicit question (required unticked radio, no-consent routed to exit code
-1) or states that continuing is consent was decided by
`prolific_completion_redirects` — which, read literally, said "if we hold a
completion code, consent must be an affirmative act". **Whether consent is
EXPLICIT is an ethics decision; holding a completion code is platform
plumbing.** The conflation is the same defect class as the screened-out
dead end of 2026-08-13 (one flag doing a second, unrelated job), caught this
time before it cost a participant.

The split: `explicit_consent` defaults **ON** in `SESSION_CONFIG_DEFAULTS` —
the one shipped flag that is deliberately not off-by-default, because a study
should have to OPT OUT of asking for consent — and the **lab profile resolves
it OFF** (implicit consent by continuing; there is an experimenter in the
room). That preserves the pre-split behaviour of both shipped profiles
exactly: prolific keeps the radio, the lab keeps implicit consent. The
prolific profile deliberately does NOT list the key (it falls through to the
baseline ON): explicit consent is the default, not a Prolific feature.

The audit for a second conflation found none: every other use of
`prolific_completion_redirects` (the outro return footers, the Ended/Results
"Back to Prolific" branches, the dashboard's awaiting-return pill, the
return-click stamp) is genuinely about the completion-code redirect. One
consequence is newly constructable and deliberate: `explicit_consent` on with
redirects off produces a decliner whose ending has no return button —
`outro/Ended.html`'s neutral fallback covers them.

A frozen session predating the flag reads it as OFF (`common.flag`'s
missing-module rule) — the radio would silently vanish for that session's
future entrants, which is why the predeploy frozen-config audit reporting the
missing key matters: the remedy is to recreate the session.

**Rejected:** deciding at runtime from `recruitment` (the consent page asking
"am I a lab study?") — profiles resolve to explicit config values at import
precisely so behaviour is never re-derived silently; and keeping the old
wiring with a comment — the rename made the misreading legible, a comment
would only apologise for it.

**Enforced:** `tests/explicit_consent_test.py` (radio present+required when
on, absent with implicit copy when off, in BOTH recruitment profiles — flag
decides mechanics, recruitment decides copy — plus the resolved values on
both shipped configs); `explicit_consent` in `tests/frozen_config_test.py`'s
STRIPPED list pins the frozen-session behaviour.

## One short-viewport rhythm for every `.stacked-form` option row — a leak ratified into the rule — 2026-08-14

The consent-fold block (`@media (max-height: 820px)` in base.css, 2026-08-13)
tightened option rows via `.stacked-form .mc-option / .form-check` while its
comment claimed consent-only scope — but the quiz and demographics stack their
options in `.stacked-form` directly (the "different wrapper" the comment cited
never existed), so both pages were retuned from day one. **Discovered through
a geometry-baseline diff, not by design** — the fold work never ran
`--update-baseline`, so the first `--diff` afterwards surfaced ~130 moved
measurements (quiz card −125px, demographics −59px at short viewports), which
were first mis-attributed to environment drift and then pinned by a CSSOM
toggle: deleting the one media rule sprang the rows back to the baseline's
values on both pages, while a rule audit proved the concurrently-added
tabmonitor.css matches nothing there. The log records the route because that
is how it actually happened.
**Julian's ruling: make the rule the intent.** One component, one rule,
everywhere — a component that tightens on short viewports on one page but not
another is the same mixing-and-matching the logo-strip principle forbids. The
shipped behaviour stands, the adopted baseline stands, and the earlier
"one page's shortfall must not silently retune every choice" scoping intent
is ABANDONED, on purpose, with the reversal recorded at the block itself.
Judged on screenshots before ratifying, not on the principle alone: rows stay
over the 44px touch floor, nothing cramped, quiz and demographics
neutral-to-better on short screens.
**Rejected:** re-scoping the rule to the consent group (a dedicated class) —
it would honour the written intent by making the same control obey two
rhythms, which is the defect class, not the fix.
**Enforced:** the rewritten comment at the block (base.css) states the
everywhere-rule and forbids re-scoping without a new decision;
`tests/geometry_baseline.json` pins the shared rhythm at all three viewports;
the affordance and touch-target legs of `tests/render_check.py` assert the
pages still behave.

## The tab monitor is monitored-by-default after the agreement page — and the claim preceded the behaviour — 2026-08-13

Whole-app review B1, decided by Julian. **First, the record correction this
entry exists to hold: from 2026-08-12 to 2026-08-13 four places (this file's
armed-before-the-quiz entry, README's Prolific flow diagram, the
`AISafetyAgree` docstring, `intro/__init__.py`'s closing comment) stated that
the instructions and the quiz were monitored, and they were not.** The
agreement page had moved but no monitor wiring existed in `intro` — no
live_method, no js_vars, no script — so the very check the move was made to
protect stayed unwatched, with nothing anywhere to say so (the enforcement
test pinned page ORDER, not coverage). The gap was found by asking where one
concept — "a monitored page" — had two implementations, and it is recorded
here because a claim that quietly becomes true later is exactly the kind of
thing a future auditor must be able to date.

**What closed it — an INVERSION, not page-by-page opt-in** (Julian's rule):
everything after `before.AISafetyAgree` is monitored BY DEFAULT
(`monitoring.MonitoredPage`, generalising TaskPage's J2 reasoning), and a
page can only be unmonitored by asking (`monitored = False`, one switch that
disarms all the wiring together — never `js_vars = None`, which 500s at
render because oTree calls js_vars unconditionally). The four pieces travel
as one: live_method and js_vars from the base class; script and stylesheet
through `css_bundle.html` (self-gating on `session.config.tab_monitor` and on
the page's own js_vars), so there is no per-template include left to forget —
a per-template include is how the gap happened. The client lost its
threshold-defaults fallback (a second copy of SESSION_CONFIG_DEFAULTS kept in
sync by a comment) and its `/outro/` path check (a second spelling of "which
pages are monitored"): the server's js_vars are now the one authority.
`intro.intro_page_visible` gates on the new `common.removed_from_study` belt
(one membership list for every removal mechanism, used by main too), so a
mid-quiz disqualification's reload lands on the ending.

**THE PHASE ASYMMETRY — same monitor, same counting, different consequence
(Julian): intro + main EJECT at the threshold; the outro RECORDS ONLY and
never ejects.** By the outro the task is over and the data already collected,
so disqualifying somebody who has completed the whole study — for tabbing
away while typing bank details, or to fetch their Prolific tab — would cost a
real participant for no benefit. Outro violations land in their OWN column
(`focus_loss_count_outro`), so a completed-with-violations participant is
distinguishable from a nearly-ejected one (`focus_loss_count` keeps meaning
"how close to disqualification"); the dedup set is shared so no event counts
twice. The client is told its phase (`ejects: false`) and shows no overlay
and no warning modal in the outro — the modal's threat would be a lie there.
The asymmetry is stated, with its why, at every site that could read as
inconsistent: `common._apply_focus_loss`, `monitoring.py`, the top of
`outro/__init__.py`, settings' integrity block, README (section + diagram),
CODEBOOK ("Tab-monitor violation counts"), conventions.md.
**Rejected:** page-by-page opt-in (the model that produced the gap — a
checklist cannot make forgetting impossible); ejecting in the outro
(cost-without-benefit above, plus a mechanical trap: `Ended` sits FIRST in
outro's sequence, so a mid-outro ejection has no ending page ahead of it to
land on); and a client-side warning without counting or counting with the
old threatening modal in the outro (each a new collapsed distinction).
**Enforced:** `monitoring.assert_monitored_page_sequence` runs at IMPORT at
the bottom of `intro`, `main` and `outro` and refuses to BOOT over a page
that is neither monitored nor explicitly opted out — you can only get an
unmonitored page by asking for one. `tests/task_page_test.py` (reworked)
pins the bindings by identity, the quiz page's served monitor config
end-to-end, the record-only outro (violations past the threshold disqualify
nobody and stay in their own column), the Results dispatcher (one live
channel, both message types), and the checker refusing a dodger.

## One guard policy for a config-read money value: fail loudly — 2026-08-13

Whole-app review B4, decided by Julian. `showup` / `quiz_bonus` were read two
ways: the promise side (consent, instructions) guarded with `or 0`, the
payment side (`outro.compute_final_payoff`) bare. For a config holding None
that split is the worst arrangement — the participant is silently promised
€0.00 and the crash still happens, at the payment page. The `or 0` guards are
gone; every side now reads bare and fails loudly at the first page that
renders the value. **This has a behavioural implication, stated plainly
because the decision was taken assuming it did not: a degenerate config that
used to render a silent €0.00 promise now errors instead.** Loud is chosen
because silently promising somebody nothing is the worse outcome — the same
reasoning `compute_final_payoff` already carried ("failing loudly beats
recording the wrong number quietly"). No shipped or frozen config is
affected: `common.cfg` falls back to the shipped numeric default for a
MISSING key; only an explicit None ever hit either path.
**Enforced:** nothing structural — the policy is one line of comment at each
former guard site (`before.welcome.vars_for_template`,
`intro.instructions_context`), and the loudness is the absence of the guard.

## The two-accessor question is CLOSED across the flow — 2026-08-13

Chased across three separate reviews (before N3 → whole-app B2 → this
implementation), and recorded here so nobody re-opens it: **every reader of
the study type now goes through `common.is_lab` / `common.is_prolific` /
`common.recruitment`.** The last holdout was `before.startpage.is_displayed`'s
raw `config.get('recruitment') == 'lab'`, which on a session frozen before
the key existed evaluated `None == 'lab'` → False — silently dropping the lab
hold screen while the consent page one index later rendered lab copy through
`is_lab`'s fallback: one participant, one question, two answers, one page
apart. Behaviour change is confined to that frozen-config case (the hold
screen now appears, which is what the neighbouring pages already assumed);
blast radius today is zero — no live sessions, the same window the
`prolific_` rename used.
**Enforced:** `grep "config.get('recruitment')"` returns nothing outside
`common.py`; `tests/copy_routing_test.py` pins the single-implementation rule
the accessor carries.

## Task pages inherit their wiring from `TaskPage` — the template's one use of page inheritance — 2026-08-13

> **SUPERSEDED IN PART, same day — see the monitored-by-default entry above.**
> The J2 reasoning held and GENERALISED: the monitor wiring moved up into
> `monitoring.MonitoredPage`, which every page after the agreement screen now
> subclasses, so page inheritance is no longer "used nowhere else" — it is the
> rule for three of the four apps, for exactly the reason this entry gives.
> TaskPage survives as the task-specific layer (round gating + progress vars)
> on top of that base. The monitor contract itself is still untouched.

Review item J2, approved with Julian's reasoning (recorded at the class, which
is where the next reader meets the indirection): a task page that is SILENTLY
NOT ARMED for the tab monitor is worse than the cost of a base class —
forgetting the wiring produces no error, only monitoring that never fires,
discovered from the data. `main.TaskPage` carries `is_displayed` /
`live_method` / `js_vars` / the base template vars; `GameStart` and `payoff`
subclass it; the two repeated template blocks became includes
(`task_progress_strip.html`, `tabmonitor_assets.html`). THE MONITOR CONTRACT
IS UNTOUCHED — same bindings, names and thresholds; only who types them
changed. Two gotchas live in the docstring: oTree resolves page attributes at
IMPORT, so unbinding needs an explicit override, never an omission; and
subclass, never copy, or the drift returns. Page inheritance is used nowhere
else in the template, deliberately.
**Rejected:** staying explicit-per-page with a checklist — the checklist
cannot make forgetting impossible, and the failure it guards is silent.
**Enforced:** `tests/task_page_test.py` — structurally (an empty-bodied
subclass is fully armed; identity of the bindings, not lookalikes) and
end-to-end (the served page carries the monitor config; the inherited
live_method counts a violation), plus the unbind-by-override gotcha proven in
both directions.

## The dashboard's admin "Report" tab rides oTree's supported extension point, as a layer over the standalone URL — 2026-08-13

Julian promoted the TODO investigation to a build. The investigation's answer:
oTree 6.0.15 has a first-class extension point — at session creation,
`Session._set_admin_report_app_names` (otree/models/session.py:250) scans each
app for `<app>/admin_report.html`; oTree's OWN session tab bar
(otree/templates/otree/Session.html:84) renders a "Report" tab when found; the
`AdminReport` view (otree/views/admin.py:482) renders our template with
optional `vars_for_admin_report`. So the tab (`outro/admin_report.html`,
embedding the dashboard in an iframe with an open-standalone link) depends on
a documented feature, not on oTree's page structure. **The standalone URL is
the primary surface and works unchanged with the tab deleted or broken** —
built that way round deliberately. `vars_for_admin_report` is internally
defensive (oTree calls it unguarded) and catches ONLY the import, with a
literal fallback URL as the belt.
`experimenter_dashboard.note_admin_tab_problems` applies the identity.py
discipline to the one silent failure mode: quiet when oTree is legitimately
absent, LOUD (logged, never raised) when the admin-report symbols or the
template lookup have drifted — because drift here means the tab quietly stops
appearing. Known limitation: sessions created before the template shipped
carry no tab (the scan is frozen into the session row).
**Rejected:** injecting into oTree's admin page structure (templating over /
DOM patching) — far more upgrade-exposed than our routing-level install, and
unnecessary given the supported point.
**Enforced:** `tests/dashboard_test.py` §D9 — the tab appears in oTree's own
tab bar, the standalone URL works with it present, a broken dashboard leaves
the admin pages serving, a broken import leaves the tab serving via the
fallback, and the drift check reports ok against the installed oTree.

## One payment ledger: per-round `player.payoff` is not used, `participant.payoff` is written once from `earned` — 2026-08-13

Review item J1 (Julian; sub-decision also his). The underlying conflation:
oTree automatically sums `player.payoff` across rounds into
`participant.payoff`, but this template pays only `num_rewarded` randomly
selected rounds — the per-round result and the amount paid are different
things, and the auto-sum is a total nobody is paid. So the game records each
round in its own `main.Player.round_payoff`; the template pays from
`participant.payoff_vector`; and oTree's `participant.payoff` gets exactly ONE
entry — `earned` (less `participation_fee`, de-converted when `USE_POINTS` is
on), written when the results page computes payment — so the admin Payments
page shows the figure the participant was shown, and there is nothing left to
disagree. `AUTO_TABULATE_PAYOFFS=False` also removes oTree's per-round payoff
column from the export (deliberately absent, not accidentally empty — no data
lost, every round is in `round_payoff` and `payoff_vector`; CODEBOOK "The
payment record").
Facts established before shipping: nothing in oTree 6.0.15 recomputes
`participant.payoff` after that write (the `player.payoff` setter's delta is
the only other writer), and nothing in the template or its tests read the
per-round column except the placeholder itself.
**Rejected:** zeroing `participant.payoff` so the admin page is obviously
wrong (option 1 — Julian chose agreement over conspicuous wrongness); and
keeping the per-round writes while overwriting the total at the end, which
leaves a round column summing to a number nobody was paid.

### AMENDED 2026-08-14 — the raise was never the enforcement, and it lands on a participant

**Caught by the exp_pilots bossman**, verified against the installed oTree
before acting: this entry, `settings.py`, `main/__init__.py`,
`outro/__init__.py`, `CODEBOOK.md` and `skills_claude/writing_task.md` all
said `AUTO_TABULATE_PAYOFFS=False` "makes the old habit RAISE rather than
drift back silently" — presenting a **participant-facing crash as a safety
feature**. The setter is oTree's own (`otree/models/player.py:41-46`), it
cannot be removed, and it fires **at participant request time, on a page,
mid-round**. oTree has no migrations, so the realistic failure is an upgrade
under live sessions: a new build introduces a `player.payoff` write and the
first person mid-round to reach it gets a DEAD PAGE. The flag alone therefore
converts a CONDITIONAL data problem (one ledger drifting into two) into a
CERTAIN outage for whoever is part-way through — the same trade this repo has
already refused twice, in `install_duplicate_label_guard` (the early install
must fail quietly) and in `assert_duplicate_label_guard` (deliberately not on
the entry path). It was missed here for the reason it is always missed: **a
raise feels like the strict, careful option.**

The raise stays — it is oTree's, and it is the floor. What changed is that the
failure is now caught **earlier, at boot**, where loud is what loud should
mean for a server: `payoff_guard.assert_no_player_payoff_writes()`, called
from `before/__init__.py` beside the identity assert, refuses to START a build
whose app modules write `player.payoff`. The operator sees it at deploy time
while the old build is still serving; the participant never sees it.

**TWO CHECKS, DELIBERATELY, because their blind spots are disjoint** — the
judgement call the review left open. The boot scan parses app SOURCE with
`ast`, so it covers every syntactic write whether or not any test walks that
line, and it cannot be fooled by the six files that discuss `player.payoff` in
prose (a regex would refuse to boot over this very paragraph); it is blind to
indirection. The runtime test walks a real journey and asserts the underlying
`_payoff` column is still 0 on every round row, which catches indirection; it
is blind to code no walk reaches. Neither alone is sufficient, so both ship.
`participant.payoff` and `player.payoff` are two fields sharing a name, and
the scan tests the base expression explicitly rather than the attribute — the
collapsed-distinction rule, since a name-only check would refuse to boot over
`outro.compute_final_payoff`, the one write the decision exists to protect.
**Rejected:** a launch-gate-only check (`scripts/prelaunch_check.py`), which a
deploy can skip — the whole point is that the server will not come up; and
`import`-and-introspect instead of parsing, which would execute
`intro/generate_instructions_preview.py` and its browser driver at boot.
**Enforced:** `payoff_guard.py`; `tests/payoff_ledger_test.py` §7 (a walked
journey leaves every round row's `_payoff` at 0) and §8 (the guard catches six
write forms including `setattr` with a literal name, refuses a synthetic build
naming file and line, does NOT fire on the participant write or on prose,
declares its `setattr`-with-computed-name blind spot, and reports an
unparseable module as "cannot answer" rather than as a payoff write).

**Enforced:** `tests/payoff_ledger_test.py` (the two figures agree on the
admin page itself; the value survives re-renders; oTree's setter does raise;
the export column is absent while `round_payoff` is present) — plus the boot
guard above.

## A payment total is not a payment instruction: every component paid outside oTree must still be represented inside it — 2026-08-14

**Caught by the exp_pilots bossman**, and it is the natural blind spot of the
one-payment-ledger decision above: that decision made the total CORRECT and
made both ledgers AGREE on it, and stopped there. Our admin Payments figure is
one undifferentiated number — full `earned` into `participant.payoff`,
`participation_fee` shipped 0.00 — so it covers base plus bonus at once. **On
Prolific those components are paid through DIFFERENT MECHANISMS**: the base as
the study reward, the bonus through the bonus payment flow. A single total,
however correct, is therefore NOT ACTIONABLE — whoever pays needs the **bonus
figure on its own**, and that is the number that must survive intact.

THE RULE, in the reviewer's words:

> **ANY PAYMENT COMPONENT PAID OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE
> OTREE, OR THE ADMIN PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A
> TOTAL.**

**Corollary:** on Prolific the components are paid by different mechanisms, so
the total alone is not enough — the bonus must be separately visible.

THE TWO SHAPES, WHICH LOOK LIKE OPPOSITES AND ARE THE SAME DEFECT. Ours is
**complete but not itemised**: everything is inside oTree, the total is right,
and the payer cannot read the bonus off it. The reviewer's own study was
**itemised but incomplete**: components kept apart, but the base never entered
oTree at all, so its "total" was a partial figure wearing a total's name.
Neither has the property that matters, which is **itemisation of a complete
set** — and framing them as opposites is what let both ship.

WHY THE EXISTING TEST DID NOT CATCH IT — the part worth remembering. §1 pins
that the total is correct and that the two ledgers agree on it. **A study can
get the total right while making the actionable number unreadable**, and a
test written against the total cannot see that. This is the collapsed-
distinction rule in the measurement rather than in the code: "the payment is
correct" and "the payment is payable" were one assertion.

**DONE NOW (safe, and independent of the open config decision):**
`tests/payoff_ledger_test.py` §9 walks a *prolific* session and asserts the
BONUS IN ISOLATION as well as the total — each component recorded on its own,
the three reconstructing `earned` with zero residue, the bonus
(`selected_sum + quiz_bonus_awarded`) derived from the stored components
rather than as `total − base` (which would be right by construction and prove
nothing), both halves separately readable, and the components present as their
own export columns. It also records the admin-page state as a **measured gap**.

**THE CONCRETE FIGURES THIS DECISION IS BEING MADE AGAINST**, so nobody reading
it later has to reconstruct what the admin page actually showed. One real
walked Prolific completer (participant `240pbcpa`, config `prolific`, 10 rounds,
`num_rewarded=2`, exit code 1), measured 2026-08-14, all figures EUR:

| Figure | Source | Value |
| --- | --- | --- |
| base / show-up | `showup` (session config) | **2.50** |
| selected rounds | `outro.Player.selected_sum` (r10 → 45.00, r6 → 98.00) | **143.00** |
| quiz bonus | `outro.Player.quiz_bonus_awarded` | **5.00** |
| **total earned** | `outro.Player.earned` — the three above, residue exactly 0 | **150.50** |
| `participant.payoff` | written once by `compute_final_payoff` | **150.50** |
| `participation_fee` | session config, as shipped | **0.00** |
| **admin Payments figure** | `payoff_plus_participation_fee()` | **150.50** |

The selected-rounds component is randomly drawn, so it and every total below it
vary per run (other runs measured 125.00 and 140.00); **base, quiz bonus and
`participation_fee` are fixed, and the SHAPE is invariant** — the admin figure
always equals `earned`, because `participation_fee` is 0.00 and the whole of
`earned` goes into `participant.payoff`.

**WHAT THE PAYER NEEDS IS TWO NUMBERS, AND THE ADMIN PAGE SHOWS NEITHER** — it
shows their sum. Study reward, set on the Prolific study: **2.50** (the base
alone). Bonus payment, entered in the bonus flow: **148.00** (selected rounds +
quiz bonus). Pasting the admin's 150.50 into the bonus flow pays 148.00 of
correct bonus plus 2.50 that Prolific has ALREADY paid as the study reward: the
participant is overpaid by exactly the base, and the error is invisible because
the total was right all along.

**THE MEASURED EVIDENCE**, fetched from oTree's own `/SessionPayments` for that
session: **€150.50 PRESENT. €148.00 (the bonus) ABSENT. €2.50 (the base)
ABSENT.** That is the itemisation argument in one line — the page carries the
total and neither component.

(Matched CURRENCY-PREFIXED, never as a bare number: `150.50` contains `2.50`, so
a substring search reported the base as present on a page that never mentions
it. See the comment at that check — a bare search makes both negative
assertions unable to fail, which is the same defect class as the total-only test
this whole entry is about.)

**DELIBERATELY NOT DONE YET:** changing `participation_fee` or how
`participant.payoff` is composed — that is an open decision with Julian, and it
changes what the exported columns MEAN, which is not something to do as a side
effect of adding a test.
**Rejected:** asserting only that the components exist, without asserting they
sum to `earned` — a component nobody can reconcile is a number, not an
itemisation; and deriving the bonus as `total − base` in the test, which passes
whatever the data says.
**Enforced:** `tests/payoff_ledger_test.py` §9; the rule is stated in
README "Paying participants — the itemisation rule" and in CODEBOOK "THE
ITEMISATION RULE".

## The end-of-page cookie reset is gone — 2026-08-13

`clearAllCookies` (run on load by the payoff, Ended and Results pages) was
removed with its three call sites and its helper — Julian: no longer needed.
It cleared every path=/ cookie each round and at the endings, including an
admin's own session cookie when previewing; oTree identifies participants by
URL code, not cookies, so nothing participant-facing depended on it. The other
dead cookie helpers an earlier review flagged (getCookie, setCookie,
printCookies, cl) were already gone. Do not re-add a cookie sweep without a
stated reason — the last one ran for years with nobody able to say what it was
for, which is why the review flagged it.
**Enforced:** nothing but grep — there is no cookie code left to guard.

## The dashboard's state column is a collection of pills, and conditions survive outcomes — 2026-08-13

Two kinds accumulate in one cell (Julian): OUTCOME pills (a terminal state, or
the finished tick) and CONDITION pills (Non-SEPA, the timing warning, the
tab-monitor count while it climbs, the missing return click). A finished row
KEEPS its condition pills — finishing does not make a condition go away.

**ROW TINT IS OUTCOME, PILLS ARE CONDITIONS** (Julian, same day, second pass).
The row tint is one consistent outcome signal: green finished, red ended
early, amber stalled, untinted still going — mutually exclusive by
construction, so no precedence. A condition NEVER touches the row: the
finished non-SEPA participant keeps the green row AND the red pill; turning
that row red would collapse the two channels back into one. The green is
deliberately lighter than the green pills' own background so the row does not
go monotone. The amber tint's second job stands: across-the-room salience,
with the pill carrying the facts.
**Rejected:** one state per row (the original design); and, briefly, no
finished tint at all (superseded — the tint was re-added as the outcome
CHANNEL once the channel rule made "green row + red pill" coherent rather
than contradictory).
**Enforced:** `tests/dashboard_test.py` §D7/§D8;
`tests/dashboard_render_check.py` `check_pills` measures one row carrying the
finished tick and the Non-SEPA pill together, that the finished tint is
distinct from the amber and from the pills' own background, and that the red
pill stays white-on-red against the green row.

## The Non-SEPA pill: lab only, `sepa == 0` only, and no yellow state — 2026-08-13

Three deliberate narrowings, all Julian's: NULL `sepa` (the check never ran —
every Prolific row) is NO pill, never a flag; a non-Dutch but in-SEPA account
is NO pill (only non-SEPA is flagged — there is no yellow payment state); and
even a hand-edited `sepa=0` in a Prolific session shows nothing, because
payment there goes through the platform and the pill would send the operator
chasing a form that does not exist.
**Enforced:** `experimenter_dashboard._non_sepa_ids` (the one predicate);
`tests/dashboard_test.py` §D7 pins all three narrowings.

## The BIC requirement and the Non-SEPA flag are two predicates, not one — 2026-08-13

The lab bank form demands a BIC for ANY non-Dutch IBAN (in-SEPA or not;
non-empty is the whole requirement — no format validation, because a rejected
valid-but-unusual BIC strands a participant on the page that pays them). The
dashboard pill fires on non-SEPA ONLY. A German IBAN therefore needs a BIC and
gets no pill. Both read the country through `outro.iban_country_code` — one
implementation of "which country", two questions on top of it (the inverted
collapsed-distinction rule, applied in the direction that keeps the questions
apart and the mechanism shared).
**Rejected:** one combined predicate — it would either flag every German
account or let a US account through without a BIC.
**Enforced:** `tests/bank_details_test.py` pins both halves of the asymmetry,
next to each other.

## The timing warning shows the number the threshold judged — per phase — 2026-08-13

The stall verdict and the pill display are ONE value (`_stall_elapsed`), and it
is measured per phase to match what each threshold MEANS in settings.py: entry
on the current page (a block-level 60s would flag every careful consent
reader), intro on the whole app since `left_before_app` (per-page under-fired:
7 minutes on each half never tripped 480s), task per round (the threshold's own
definition), questionnaire since `task_done`. Falls back to page time where a
stamp is missing (mid-flow deploys).
**Rejected:** page-time detection with a phase-labelled display — the pill
would name a phase the verdict never measured.
**Enforced:** `tests/dashboard_test.py` §D3 (page-ageing alone must NOT trip
the intro phase; stamp-ageing must); the render check asserts the pill text.

## The return click is best-effort instrumentation, and the pill is gated on the button existing — 2026-08-13

"Finished here but never clicked Back to Prolific" is flagged ONLY when
`prolific_completion_redirects` is on — with no redirect there is nothing to
click, and the flag would fire on every lab participant forever (Julian's
critical condition; the gate comment in `_participant_row` is load-bearing).
The click stamp (`prolific_return_clicked`) rides the Results page's live
socket just before navigation, so it can be lost — absence means "no click
RECORDED", and the pill is a prompt to look, never a verdict. A grace period
(`DASHBOARD_RETURN_GRACE_SECONDS`) stops it firing on completers still reading
their receipt.
**Rejected:** routing the exit link through a stamping redirect — exact and
JS-free, but it puts instrumentation INSIDE the one path every completer
needs, and instrumentation must never be able to break a page (CLAUDE.md); the
link stays a plain href that works with the whole mechanism dead.
**Enforced:** `outro.results_live_method` (gated the same way);
`tests/dashboard_test.py` §D8 pins the gate from both sides; CODEBOOK.md
documents the stamp's best-effort nature.

## The shipped quiz items are machinery placeholders, not model items — 2026-08-13

Deliberately trivial ("What is ice when it melts?"), because they exist to
exercise the quiz machinery — wrong answers, retries, the attempt log, the
thresholds — and are replaced wholesale by every real study.
**Rejected:** shipping an exemplary Stag Hunt comprehension item. It would read
as content to keep, and the previous item ("If you fail the quiz twice…") also
hard-coded the failure threshold into participant copy and described behaviour
the shipped config doesn't produce.
**Enforced:** the comment atop `intro/quiz_items.py`;
`tests/example_quiz_content_test.py` §3 pins the placeholders and is designed
to fail when a study writes its own items, forcing the test to be rewritten
with them (see `skills_claude/writing_quiz.md` for what real items look like).

## The quiz-bonus rule is stated in two places, deliberately — 2026-08-13

Once in the payment overview (`intro/instructions_text.html`), once as the
reminder directly before the quiz (`intro/prequiz_text.html`), both now naming
*which* quiz ("every quiz question on the instructions").
**Rejected:** stating it once — the pre-quiz reminder is worth the duplication.
**Enforced:** nothing. Two cross-referencing comments ("if the rule changes,
edit BOTH") rely on the next editor reading them.

## Missing completion codes degrade to `REPLACE_CC`, never to `None` — 2026-08-13

`outro.completion_link` reads codes through the safe accessor, so a session
frozen before a code existed builds the shipped `REPLACE_CC` placeholder into
the URL. Chosen *because* it produces the same symptom as the already-known
failure "nobody replaced the placeholder": anyone seeing `REPLACE_CC` knows
instantly what it means and what to do, while `?cc=None` looks like a bug of
ours and tells the operator nothing.
**Enforced:** `outro.completion_link` (reasoning in its docstring); pinned by
`tests/frozen_config_test.py`.

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

## The logo footer is a rule, not a per-page arrangement — and yields first — 2026-08-13

The logo strip sits at the bottom of the white card, below its divider,
identically on every page that shows it — enforced structurally (`order: 999`,
`margin-top: auto`) so a template that includes it in the wrong place still
renders it right. Because it is decoration, it is the first thing to shrink
when vertical space runs short (mark height drops at the short-viewport
breakpoint).
**Rejected:** each template getting the markup order right — a new page copies
whichever page its author happened to open.
**Enforced:** the LOGO FOOTER RULE block in `_static/global/css/base.css`;
logo geometry is in `tests/geometry_baseline.json`.

## Styling is shared components, never page-local patches — 2026-08-13

A page template composes named classes from `_static/global/css/`; no inline
`style=`, no one-off rule to fix a single page, and every new component gets an
INTENTION comment plus a specimen in `_static/global/html/template.html`.
Driven by three real bugs of the same shape: a class referenced by three
templates and defined nowhere, one concept carrying two widths, and an inline
`height` beating the component's own rule. Genuine one-screen exceptions are
marked `EXCEPTION` with the reason.
**Enforced:** the Styling section of `CLAUDE.md`; layout drift is caught by
`tests/render_check.py` against the geometry baseline. The no-inline-style rule
itself relies on review. Full working: `_ai/css_divergence_report.md` (local only — `_ai/` is gitignored; not in a clone).

## "Flags decide mechanics, `recruitment` decides copy" — 2026-08-13

Every sentence a participant reads that names the platform, the room, or how to
reach a human branches on `recruitment`; module flags answer only "does the
machinery exist". Driven by a found dead end: the consent page inferred
"Prolific" from one flag, the screen-out page from another, and a
friend-test config told a participant to seek help through Prolific and then
gave them no way out at all — no error, no failing test.
**Rejected:** letting whichever flag is nearest stand in for the study type.
**Enforced:** `common.is_lab` / `common.is_prolific` are the only two
implementations; `tests/copy_routing_test.py` asserts the impossibility;
`settings._prelaunch_problems` refuses the config combination that created the
dead end.

## Completion fires when the results page loads — identically in both variants — 2026-08-12

`exit_code` becomes `finished` in `Results.vars_for_template`, not on the
"Back to Prolific" click. This reversed an earlier request, and the principle
behind the reversal outranks the detail: **lab and Prolific diverge only where
genuinely essential**, because every divergence can be true in one variant and
quietly wrong in the other, forever. A participant who closes the tab without
clicking has still finished; the click is Prolific's concern, not the data's.
**Enforced:** `outro/__init__.py` (`Results.vars_for_template`, idempotent);
`tests/full_journey_test.py` asserts exit code 1 at Results. The
minimal-divergence principle itself has no guard — the caller-list warning on
`common.is_lab` and review are what hold it.

## ~~A screened-out Prolific participant gets a codeless link back~~ — 2026-08-12, SUPERSEDED 2026-08-15

The way off the screen-out page is a plain link with **no completion code**,
because submitting a code closes the Prolific submission, and a returned
submission can never be retaken — which forecloses exactly what the page asks
("come back on a computer"). The old `error_code`/`REPLACE_ERR` pair was
removed for this reason and must not come back. Corollary (2026-08-13): being a
Prolific study and offering a screened-out exit are the same commitment, so the
dependency is enforced, not documented.
**Enforced:** the no-screened-out-code note in `settings.py`;
`settings._prelaunch_problems` refuses a `recruitment='prolific'` config with a
blank or unreplaced `prolific_screenout_return_url`;
`tests/copy_routing_test.py` walks the codeless way out end to end.

> **SUPERSEDED 2026-08-15 by "Every ending population gets its own completion
> code" (below/newest).** The reasoning above is kept, not deleted, because a
> reader who meets the codeless design in an older study — or who reasons their
> way back to it — should be able to see that it was reconsidered and why,
> rather than find it silently gone.
>
> **What it got right:** submitting a completion code does close a Prolific
> submission, and a returned submission cannot be retaken. That is still true.
>
> **What it got wrong:** it treated "leave the submission open" as the kind
> outcome. In practice a bare researcher URL leaves the submission sitting in
> LIMBO — the participant has been turned away, cannot continue, and nothing
> tells Prolific anything; the place stays occupied until it times out. A
> Prolific REQUEST_RETURN code is not the same instrument as a completion code:
> it actively PROMPTS the participant to return the submission, which is the
> outcome that frees the place and ends the ambiguity. The screened-out exit is
> now `prolific_device_code` used as a full completion URL, and
> `prolific_screenout_return_url` is gone as a setting.

## The screen-out return URL ships as a placeholder, not a working default — 2026-08-12

It used to ship as `https://app.prolific.com/`, which works — and that is the
problem: **a plausible default never gets checked**, and the person who
discovers it was wrong for this study is a participant already turned away.
**Enforced:** the `REPLACE_*` family is flagged by the prelaunch banner and by
the pre-deploy frozen-config audit's PLACEHOLDER severity.

## The device screen-out is a soft wall, clearable before consent only — 2026-08-12

A screened participant is HELD on the entry page (not walked to an ending oTree
could never bring them back from), and a later pre-consent request from an
accepted device clears the screen-out; exit code `-4` is the one code that can
revert. After consent the check never applies again. The state is reset, the
history never is — "how many did the gate turn away" is counted from
`screenout_history`, not the exit code.
**Rejected:** routing to a proper ending page (irreversible in oTree), and a
write-once `-4` (would leave genuine finishers recorded as screened out).
**Enforced:** `tests/screenout_softwall_test.py`; the consent boundary is the
durable `participant.consent_submitted` fact, not a page index. Full working:
`_ai/screenout_softwall_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The clear predicate is exactly the entry-allow predicate minus `undetermined` — 2026-08-12

If clearing allowed *more* than entry, a screen-out could be lifted by a device
that would not have been let in; if *less*, the page tells someone switching
will work when for them it cannot (the reference implementation had this bug:
its `unknown` never cleared, stranding privacy-proxy laptops). `undetermined`
is the single carve-out — no usable header is not a device, and treating it as
a clear would let anyone lift their own screen-out by sending no User-Agent.
**Enforced:** `common.device_clears_screenout` (explicit membership, so
`undetermined` cannot satisfy it whatever a config says);
`tests/screenout_softwall_test.py` §8 states the two asymmetric assertions side
by side.

## `unknown` and `undetermined` are different states — 2026-08-12

A User-Agent that parsed and matched nothing (`unknown`) is a device type a
study may accept or reject like any other; no usable header at all
(`undetermined`) is *not a device type* and must always be allowed. Collapsed,
a study rejecting `unknown` starts ejecting laptops behind privacy proxies.
This is the model case of the collapsed-distinction rule in `CLAUDE.md`.
**Enforced:** `common.classify_device`; `tests/device_gate_test.py`, which is
deliberately weighted toward false positives (browsers that must NOT be
screened). Full working: `_ai/device_allowlist_log.md` (local only — `_ai/` is gitignored; not in a clone).

## The lab comprehension rule is help, not ejection — unlimited attempts — 2026-08-12

Online, crossing the failure threshold disqualifies (`comprehension_dq`); in
the lab the same threshold *starts the study helping*: the one-time re-read
offer (if `quiz_reread` is on), then a dismissible "raise your hand" notice,
escalating at twice the threshold — and the participant may keep trying
forever. The notice is keyed on the threshold and the study type, NOT the
module, so a lab session with `quiz_reread` off still calls the experimenter.
The notice deliberately does not say "you can keep trying" — some participants
should raise a hand instead of brute-forcing radio items.
**Rejected:** disqualification in the lab (there is a human in the room), and
keying the notice on the module (left a module-off lab session with no help at
all).
**Enforced:** `tests/gated_flow_test.py` (lab-reread and prolific-dq
scenarios); the prelaunch check refuses `comprehension_dq` in a lab config;
attempts proven uncapped by `tests/quiz_attempt_log_test.py`. Full working:
`_ai/lab_comprehension_proposal.md` (local only — `_ai/` is gitignored; not in a clone).

## Every graded quiz submission is logged — uncapped, and unable to break the page — 2026-08-12

`quiz_attempt_log` records what was answered and what was wrong *as judged at
the time* (never re-graded — the item set changes between studies), with no cap
on entries, and the whole write is wrapped so instrumentation can never cost a
participant their page.
**Enforced:** `intro.log_quiz_attempt` (never raises);
`tests/quiz_attempt_log_test.py` proves 25 attempts stored and the page still
standing.

## The tab monitor is armed before the instructions and quiz, not after — 2026-08-12

> **CORRECTED 2026-08-13 — see the monitored-by-default entry above.** This
> entry implied the move made the instructions and quiz monitored. It did
> not: only the AGREEMENT moved; no monitor wiring existed in `intro`, so the
> quiz stayed unwatched for a day while four documents said otherwise. The
> enforcement below pinned page ORDER, never coverage — which is how the gap
> survived its own test. Coverage is now real, and enforced at boot.

The agreement page moved from the end of `intro` to `before`: armed after the
quiz, the very check that gates entry was unmonitored — a participant could
consult an AI assistant during it, which is exactly what the page warns
against.
**Enforced:** the page lives in `before.AISafetyAgree`; a comment in
`intro/__init__.py` forbids moving it back; `tests/gated_flow_test.py` asserts
the agreement is not after the quiz.

## Participant identity is decided in one place — 2026-08-12

"Is this the same participant id?" was answered twice — label comparison in
Python (case-folded) and row lookup in SQL (collation-dependent) — so a
returning `ABC123` took a fresh row against a stored `abc123`, and behaviour
differed between sqlite (dev) and postgres (production). One implementation,
called by both.
**Enforced:** `identity.py`; `tests/identity_test.py`. This bug pattern is
generalised as the inverted collapsed-distinction rule in `CLAUDE.md`.

## The layout geometry baseline is committed, so intentional change is reviewable — 2026-08-12

`tests/render_check.py` measures element geometry at three viewports;
`tests/geometry_baseline.json` is committed **on purpose** (to `tests/`, not
gitignored `_ai/`) so an intentional layout change shows up as a reviewable
diff of that file, and an unintentional one fails `--diff`. Layout failures
produce no error otherwise — nothing 500s while the participant gets a broken
page.
**Enforced:** `render_check.py --diff` exits non-zero on movement beyond ±3px;
adopting a change requires `--update-baseline` and reading the diff.

## Three orthogonal controls; profiles resolve to explicit config keys at import — 2026-08-10

Study type, DEBUG (env-driven, so production can never ship skip controls), and
the pilot feedback form are independent axes; there is no "testing" study type
— testing loosenings are a reversible override honoured only under DEBUG. A
recruitment profile is rewritten into explicit per-config keys at import, so
the admin shows exactly what a session ran with and a profile can never change
behaviour silently at runtime.
**Rejected:** a `testing` study type (collapses two axes and lets loosenings
ship), and profiles consulted at runtime (invisible in the admin, mutable under
running sessions).
**Enforced:** `settings.resolve_recruitment_profile`;
`tests/frozen_config_test.py`; DEBUG derived from `OTREE_PRODUCTION` presence.

## Exit codes: initialised at creation, `0` means "never reached an ending" — 2026-08-07 (ported from the pilot)

Every participant carries `exit_code` from session creation, so no export row
is ever blank; `0` is *abandoned* — created but never reached any ending — and
is distinct from every deliberate outcome, each of which has its own code
(screened-out is `-4`, not `0`: you must be able to tell the gate's work from a
closed tab). A code nothing records is a lie in the export, so
reserved-but-unwired codes are deleted, not documented (`timed_out`, removed
2026-08-10).
**Enforced:** `common.init_participant`; the codes table in `CODEBOOK.md`;
tests assert on numeric codes rather than ending copy
(`full_journey_test`, `device_gate_test`).

## Participant and config reads go through safe accessors, always — 2026-08-07 (ported from the pilot)

`participant.vars.get(...)` (never `getattr` — the vars descriptor raises
`KeyError`, which the getattr default does not catch: a live outage), and
`common.cfg(...)` (never `config[...]` — a session config is frozen at
creation, so later-added parameters are absent for running sessions: also a
live outage). `common.flag` is the deliberate exception: a module flag missing
from a frozen config means the module post-dates the session and must read as
OFF.
**Enforced:** `common.pvar` / `common.cfg` / `common.flag`;
`tests/frozen_config_test.py` strips keys and walks; the rules are in
`CLAUDE.md`'s correctness list.

## A test that cannot fail is not evidence — standing principle

Bot tests passing is not evidence a browser works (three pilot outages went
green under bots); a content test loosened until it survives a content change
was never testing the content; a drift check that fails on everything gets
ignored and then catches nothing (see the two-severity entry above). Every
check must correspond to a participant it could save.
**Enforced:** as method, in `skills_claude/writing_tests.md` (real HTTP, no-JS
submits, phone User-Agents, visible-text assertions, measured rendering);
structurally, nowhere — this one is held by review and by the suites being the
shape they are.
