# Decisions: Settings, profiles and parameters

Read when you change `settings.py`: the three controls, recruitment profiles, session-config keys, the safe accessors, or the CREED lab block.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## The launcher's lab session number is a session config key, read as text, 2026-11-05

The launcher sets `OTREE_LAB_SESSION`; `settings.py` puts it in
`SESSION_CONFIG_DEFAULTS` as `lab_session`, so oTree's wide export carries
`session.config.lab_session` on every participant row and the create-session form
shows it, editable. Nothing in the study reads it, so `common.cfg` does not come
into it.

**It breaks the family-prefix rule on purpose.** The name is shared with the
launcher and the export, and it is not a `prolific_*` or other family parameter.
It sits right after `recruitment`, a new row near the top of the form; the
existing keys keep their order.

**`format_session_data.py` reads it as text, in a second read of that one
column.** Pandas' guessing turns `007` into `7`, `217` into `217.0` once an empty
session shares the export, and `NA` into empty. A converter does not stop the last
one, and `keep_default_na=False` for the whole file would change every other
column. **An export without the column stays without it**: the script does not
create columns a session did not collect (`existing_payment_cols`,
`add_telemetry_derivation`), and an invented empty column would read as "this
session was asked and had none". Rejected: copying it to a second column with a
friendlier name, because one concept under two names is what CLAUDE.md warns
about. This script does not reshape.

**The long data is the R helper's job, and it decides missing columns the other
way.** `scripts/helper/otree.R` in Template_Analysis and the site's
`otree-wide-to-long.R` turn the wide export into long data, with the variable as
`lab_session`. There it is always present, `NA` when empty or absent, because long
output has a fixed set of columns and those files already give `NA` for a missing
one. Keep the two behaviours apart: they follow what each output is.

**A running session created before the key exists fails the pre-deploy frozen
audit as MISSING**, like any other added key. It does not qualify for
`MISSING_IS_THE_DESIGNED_MEANING`, whose bar is exactly one raw reader; this key
has no reader. Left as is: the template has no live sessions.
**Enforced:** `scripts/tests/format_session_data_test.py` (text handling, absent
column); `scripts/tests/frozen_config_test.py` strips the key and walks. The real
export and form were checked by hand end to end on oTree 6.0.15 on this date.
Nothing enforces the position in the form or that oTree keeps exporting the
column.

---

## The CREED lab block is EXTENDED to the launcher block's full behaviour — DATABASES, ADMIN_PASSWORD, AUTH_LEVEL and DEBUG, each env-gated — 2026-09-10

The CREED Lab Launcher now appends a larger self-documenting block to a project's
`settings.py`: one that re-asserts from the environment *everything* a lab run
needs, so it overrides anything hardcoded above and stays inert without the
launcher's variables. This template carried only the SMALLER version (ROOMS +
`participant_label_file` + `ADMIN_USERNAME`, the 2026-09-01 entry below). It is
brought up to the same behaviour so a study forked from here is protected the
same way the launcher would protect a hand-written project — CREED-lab-ready with
nothing to paste.

- **Four overrides added, each guarded by the ONE variable it needs.** `DATABASES`
  rebuilt as Postgres from the `DB_*` variables, gated on `DB_NAME`, so it wins
  over a hardcoded `DATABASES`; `ADMIN_PASSWORD` from `OTREE_ADMIN_PASSWORD`,
  gated on that var; `AUTH_LEVEL` from `OTREE_AUTH_LEVEL`, gated on that var; and
  `DEBUG` re-derived from `OTREE_PRODUCTION`, gated on that var, so a fork that
  hardcoded `DEBUG = True` cannot ship debug pages (skip buttons, quiz solutions)
  into a lab session. With NO lab environment set, every guard is false and the
  file resolves byte-for-byte as before.
- **In THIS template the overrides are REDUNDANT — and that redundancy is exactly
  why the block stays inert.** The template already env-derives `DATABASES`,
  `ADMIN_PASSWORD` and `DEBUG` higher up (from the same variables, with the same
  defaults), so each override reproduces the value the base code already produced.
  That is precisely what keeps `creed_lab_block_test.py`'s differential green: the
  block-present and block-absent runs resolve identically. The fork PROTECTION is
  the point — a fork is free to hardcode any of these to a literal, and then the
  launcher's box for it would silently do nothing without the override sitting
  after the project's own assignment. Do not "tidy" them as duplication; this is
  the same "helpfulness" failure the `ADMIN_USERNAME` duplication defends against
  (see the 2026-09-01 entry, whose argument now applies to each of these keys).
- **`AUTH_LEVEL` is genuinely new to `settings.py`.** The template never set it —
  oTree reads `OTREE_AUTH_LEVEL` from the environment itself
  (`otree/settings.py`), which is why `scripts/prelaunch_check.py` reads the env
  rather than the setting. Assigning it here to the same env value is consistent,
  not a change, and it is deliberately absent from the differential's `COMPARED`
  set, so it neither helps nor breaks that test — it is the one override with no
  base value to match, and it simply mirrors what oTree already derives.
- **The marker line is kept VERBATIM; the banner is added as comments under it.**
  The task asked for an unmissable opening banner; the `# === CREED lab support
  (paste at the END of settings.py) ===` line is how the launcher DETECTS opt-in
  (a text match) and is pinned character-for-character by
  `creed_lab_block_test.py` §1, so it must not be reflowed into a new banner. The
  banner wording ("appended by the CREED lab launcher … TO REMOVE delete
  everything from the marker line above to the END of the file … safe to leave in
  permanently") is carried in the comment lines immediately below the marker,
  which are cut with the block and have no behavioural effect.
- **Rejected: rebuilding `DATABASES` from `DATABASE_URL`** (which the bat also
  exports). Parsing the URL would produce a `DATABASES` dict of a different shape
  than the template's own `DB_*` Postgres branch, so the block-present and
  block-absent runs would DIFFER and the differential would go red — a false
  alarm hiding a real question. The task and the base code both use `DB_*`, so the
  override matches the base exactly. **Also rejected: renaming the marker into the
  new banner** (breaks launcher detection and §1) and **dropping the guards to
  assign unconditionally** (a fork with no lab environment would then have its
  `DATABASES`/`DEBUG` silently reset at import).

**Enforced:** `scripts/tests/creed_lab_block_test.py` — `DATABASES`,
`ADMIN_PASSWORD` and `DEBUG` are already in its `COMPARED` set, so the differential
now covers the three new env-derived overrides for free, under BOTH the bare
environment (§3) and the exact `set_up_otree.bat` environment (§4, which sets
`DB_NAME`, `OTREE_ADMIN_PASSWORD`, `OTREE_PRODUCTION` and `OTREE_AUTH_LEVEL`), and
§4 additionally asserts the Postgres engine, the database name, `ADMIN_PASSWORD`
and `DEBUG=False` absolutely. `AUTH_LEVEL` is not compared (no base value to match).
`scripts/prelaunch_check.py`, `scripts/tests/frozen_config_test.py` and
`scripts/tests/room_gate_test.py` stay green. **NOT enforced, honestly:** as with
the 2026-09-01 entry, nothing here exercises the real launcher — the contract
tested is the block's behaviour under the variables the launcher is documented to
export, not that the launcher exports them, and the block body is not pinned
byte-for-byte.

---

## The CREED lab block is CARRIED in `settings.py`, verbatim and last — the seat list is never hardcoded — 2026-09-01

The CREED Lab Launcher (a GUI app, outside this repo) replaces the hand-edited
`scripts/set_up_otree.bat` that lab staff run today. Each lab computer opens a
desktop shortcut at the oTree ROOM carrying that machine's seat label
(`/room/study?participant_label=B3`), and the admin page only shows the per-seat
present/absent board when the room has a `participant_label_file`. The launcher
writes that seat file into ITS OWN config directory and exports two variables —
`CREED_LABEL_FILE` (absolute path) and `CREED_ROOM_NAME` (default `study`). It
never writes a file into a project. A project opts in by carrying one marked
block at the END of `settings.py`, which this template now does, so a study
forked from here is CREED-lab ready with nothing to paste.

- **The block is carried VERBATIM, both marker lines intact, and the delivery
  vehicle was deleted.** `# === CREED lab support (paste at the END of
  settings.py) ===` … `# === end CREED lab support ===` is how the launcher
  detects that a project has opted in — a **text match**, not an import and not
  a config key. So reflowing a marker, renaming it, or wrapping the block in
  anything is not cosmetic: it makes the launcher believe this project never
  opted in, and the only symptom is a lab session whose board is empty. The
  block arrived as a top-level `creed_lab_block.py`; that file is a delivery
  vehicle, not code this project runs, and a stray second copy of the block is
  exactly the one-concept-two-implementations shape this file exists to prevent,
  so it was removed in the same change.
- **It APPENDS, and it MUTATES the room dict in place — it never reassigns
  `ROOMS`.** This template's single room carries `welcome_page`
  (`_templates/room_welcome.html`, the styled room gate — see the 2026-08-17
  entry on the `experiment` → `study` rename) and `display_name`. A block that
  ended `ROOMS = [dict(name=…, participant_label_file=…)]` would resolve
  perfectly, raise nothing, fail no test, and drop both keys — the participant's
  first screen silently reverts to oTree's bare framework interstitial. In-place
  mutation keeps every key the project set, whatever they are, which is what
  makes the block safe to carry into a study whose room this template has never
  seen. The corollary is that POSITION is load-bearing in both directions: the
  block must come after the project's `ROOMS` (or there is nothing to mutate),
  and **nothing may assign `ROOMS` after the block** (that assignment wins, and
  deletes the room the launcher just configured, again with no error).
- **The duplicate `ADMIN_USERNAME` is deliberate. Do not "tidy" either one.**
  `settings.py:1104` sets it from `OTREE_ADMIN_USERNAME`; the block sets it
  again at the end, falling back to whatever was already defined. Under this
  template the two resolve to the same value in every environment — that is
  measured, not assumed. Both stay: the block's line is the only reason the
  launcher's admin-username box does anything in a project that hardcodes
  `ADMIN_USERNAME` to a literal (oTree reads the admin PASSWORD from the
  environment but not the username), and it must sit after the project's own
  assignment or the project's would win. Deleting the template's line instead
  would make a block a study is free to remove the sole source of the
  template's own credentials. This is precisely the "helpfulness" failure
  CLAUDE.md opens with: the redundancy reads as an unfinished merge and is not.
- **Rejected: hardcoding the CREED seat lists into `settings.py`.** Tempting,
  because it needs no launcher and no environment variable. But which seats
  exist — and which machines are broken this week — is a fact about the LAB,
  not about a study, and a hardcoded list makes every study forked from this
  template carry its own copy. They then go stale **independently and
  invisibly**: nothing errors, the board simply stops matching the room, and it
  is noticed on the day of a session. One seat file, owned by the launcher and
  passed by path, is the single implementation. The project owns nothing.
- **`room_gate_test.py` §3b's synthetic configuration is now the REAL lab
  configuration.** That check builds a room WITH a `participant_label_file` by
  hand, because without one a native GET submit strips the id and its
  auto-submit loop cannot happen — it says so in its own docstring, and it says
  the dangerous configuration is what "a copied study that adds a labels file"
  would land in. Under the launcher that is no longer hypothetical: a CREED lab
  run is always that configuration. §3b is therefore load-bearing for the lab,
  not a defensive extra, and must not be simplified away on the grounds that
  the template ships no labels file.

**Enforced:** `scripts/tests/creed_lab_block_test.py`, 91 checks, no server and
no browser. Its method is a **differential**, not a remembered baseline: each
scenario executes `settings.py`'s source text in a child process twice under a
byte-identical environment — once as shipped, once with everything from the
start marker cut away — and requires `ROOMS`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `DEBUG`, `DATABASES` and `SECRET_KEY` to be equal. A child
process because `settings.py` is import-once and its values are decided by the
environment at import; a differential because a committed "this is what ROOMS
looked like" literal answers the wrong question and goes stale the first time a
study edits its room. §1 pins the markers and that the block is genuinely last;
§2 pins from the AST that nothing binds `ROOMS` after the block, and compares
the executed `ROOMS` against the `ROOMS = [...]` literal evaluated alone, which
catches a MUTATION an assignment scan cannot see; §3 runs the CREED variables
absent; **§4 is the backwards-compatibility guarantee** — it runs the exact
environment `scripts/set_up_otree.bat` exports, **read out of the bat file
rather than retyped**, so `DATABASES`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
`DEBUG` and `ROOMS` are proved identical for the workflow the lab uses today;
§5 proves an ACTIVE block adds exactly one key to the room and changes or
removes none, asserted as a key-by-key diff; §6 pins the `study` default and
that a launcher pointed at a different room name leaves the `study` room alone;
§7 aims squarely at `ADMIN_USERNAME`, the one name both assignments write.
The suite was mutation-checked when it was written: reassigning `ROOMS` instead
of mutating, removing the environment guard, and appending `ROOMS = []` after
the block each turn it red on the checks that name that failure.

**NOT enforced, honestly:** nothing here exercises the actual launcher, which is
not in this repository — the contract tested is the block's behaviour under the
variables the launcher is documented to export, not that the launcher exports
them. The block's BODY is not pinned byte-for-byte against a copy of the
delivered file either (deleting that copy was the point), so an edit inside the
markers is caught by the behavioural checks above and not by a checksum. And as
everywhere in this repo, nothing runs the suite for you.

---

## Session-config keys are named family-first and ordered into families, so the admin form reads as sections — 2026-08-18

Decided by Julian, while the template has **NO live studies** (so the rename is
safe now and would be a schema change across running sessions later). The admin's
session-configuration form renders `SESSION_CONFIG_DEFAULTS` in **insertion
order** and gives it **no section headings at all** — so the only structure
available is the key order plus a shared naming prefix per family. Every key was
renamed into a prefixed family and the dict reordered so the families are
contiguous: unprefixed top-level keys (`doc`, `recruitment`, `pilot_feedback`,
`num_experimental_rounds`, `explicit_consent`, `expected_duration_minutes`), then
`payment_*` (`payment_show_up`, `payment_num_rewarded`, `payment_quiz_bonus`,
with the two oTree built-ins `real_world_currency_per_point` /
`participation_fee` kept at the bottom of the block under their built-in names),
`quiz_*` (`quiz_comprehension_max_failures`, `quiz_comprehension_dq`,
`quiz_reread`, `quiz_verify`), `display_*`
(`display_before_show_duration_and_fee`), `collect_outro_*`
(`collect_outro_demographics`, `collect_outro_bank_details`), `telemetry_*`
(`telemetry_passive_capture`, `telemetry_device_capture`), `build_*`
(`build_static_version`), `tab_monitor*`, and `prolific_*` last. This is the same
move the participant-tracking fields made (see 'Participant tracking fields are
named family-first' — 2026-08-17), applied to the config form.

The old names named the *thing* and lost the family: `showup`, `num_rewarded`,
`quiz_bonus`, `verify_quiz`, `device_capture` each sat alone in a form with no
grouping, so a lab operator scrolled past Prolific-only machinery with nothing to
say which keys were theirs. The rename is **complete and grep-verified** — a
config key is a string-keyed lookup, so a half-rename is a silent wrong default,
not an import error — reaching `settings.py`, `core/common.py`'s safe accessors, the
`before/`/`intro/`/`main/`/`outro/` modules and their templates (oTree exposes a
config value to a template as a bare `vars_for_template` name, so `{% if
device_capture %}` had to move too), the scripts, the tests, and the docs. Two
disambiguations were held apart deliberately: the config key `static_version`
became `build_static_version`, but the **module-level `STATIC_VERSION` constant,
`C.STATIC_VERSION`, the asset-manifest `static_version` field and the template
reads of `C.STATIC_VERSION` are the code asset version — a different thing — and
did NOT move**; and `quiz_comprehension_max_failures` / `quiz_comprehension_dq`
renamed while the participant field `comprehension_failed_attempts` did not. The
default `num_experimental_rounds` was also dropped `10 → 5` in the same pass.

### The device allow-list joins the `prolific_` naming family — 2026-08-18

`allowed_devices` became `prolific_allowed_devices` and moved into the
`prolific_` block at the bottom of the form. **This is a form-navigation choice
about the prefix and the position, and NOTHING about the runtime changed** — the
gate is still decided from the entry request in every study type, the key is
still absent from both `RECRUITMENT_PROFILES` bundles (so selecting the prolific
study type never starts screening devices out on its own), and it still falls
through to the all-four baseline meaning the gate is off.

**The superseded rationale is preserved, not deleted.** The key previously lived
in its own ENTRY section specifically *because* it is "not a Prolific parameter":
that reasoning was correct about the behaviour and is still true of the
behaviour. What overrode it is that the form has no headings, so a key outside
the `prolific_` block but conceptually distinct from the payment/quiz/telemetry
families had no home that read cleanly — and grouping it by prefix with the other
end-of-form machinery keeps it out of a lab operator's way. The `prolific_`
prefix is therefore a **grouping label, not a claim of Prolific-specificity**;
the note above `prolific_allowed_devices` in `settings.py` and the bundle comment
in `RECRUITMENT_PROFILES` both say so at the point of use. **Rejected:** leaving
it in a lone one-key ENTRY section (a section of one in a form with no section
headings reads as noise); adding it to the prolific bundle to match the prefix
(that would change behaviour — the exact trap the prefix must not cause).

**Enforced:** `scripts/prelaunch_check.py` and the config-key set in
`scripts/tests/frozen_config_test.py` (`STRIPPED`) both enumerate the new names,
so a missed rename or a bundle that wrongly gained `prolific_allowed_devices`
shows up there; the HTTP/bot suites go red on a half-done rename because a wrong
config default changes what a participant reaches; and every old name was grepped
to zero across the repo (this entry and superseded code comments are the only
places the old spellings survive, as history).

---

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
`core/common.py`; `scripts/tests/copy_routing_test.py` pins the single-implementation rule
the accessor carries.

---

## "Flags decide mechanics, `recruitment` decides copy" — 2026-08-13

Every sentence a participant reads that names the platform, the room, or how to
reach a human branches on `recruitment`; module flags answer only "does the
machinery exist". Driven by a found dead end: the consent page inferred
"Prolific" from one flag, the screen-out page from another, and a
friend-test config told a participant to seek help through Prolific and then
gave them no way out at all — no error, no failing test.
**Rejected:** letting whichever flag is nearest stand in for the study type.
**Enforced:** `common.is_lab` / `common.is_prolific` are the only two
implementations; `scripts/tests/copy_routing_test.py` asserts the impossibility;
`settings._prelaunch_problems` refuses the config combination that created the
dead end.

---

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
`scripts/tests/frozen_config_test.py`; DEBUG derived from `OTREE_PRODUCTION` presence.

---

## Participant and config reads go through safe accessors, always — 2026-08-07 (ported from the pilot)

`participant.vars.get(...)` (never `getattr` — the vars descriptor raises
`KeyError`, which the getattr default does not catch: a live outage), and
`common.cfg(...)` (never `config[...]` — a session config is frozen at
creation, so later-added parameters are absent for running sessions: also a
live outage). `common.flag` is the deliberate exception: a module flag missing
from a frozen config means the module post-dates the session and must read as
OFF.
**Enforced:** `common.pvar` / `common.cfg` / `common.flag`;
`scripts/tests/frozen_config_test.py` strips keys and walks; the rules are in
`CLAUDE.md`'s correctness list.
