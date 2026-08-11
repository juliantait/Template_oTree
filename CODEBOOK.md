# Codebook

The single reference for what every exported column means, the exit-code
scheme, and the mapping of any repurposed spare columns. Keep it current: an
export is only as trustworthy as this file.

---

## Exit codes (`participant.exit_code`)

Every participant carries a numeric `exit_code`, **initialised to 0 at session
creation** (`common.init_participant`) so no export row is ever blank. It is
raised to `1` only on a clean finish, or set to a negative reason when the
participant leaves early. Defined in `settings.EXIT_CODES`.

| Code | Name | Meaning | Set where |
|-----:|------|---------|-----------|
| `1` | finished | Completed the study normally. | `outro.Results.vars_for_template` |
| `0` | abandoned | Created but never reached the end (the default). | `common.init_participant` |
| `-1` | no_consent | Declined consent on the entry page. | `before.welcome.before_next_page` |
| `-2` | comprehension | Disqualified: failed the comprehension check too many times. | `intro.quiz.error_message` |
| `-3` | tab_monitor | Disqualified: AI-safety / tab-switch monitor. | `common.focus_live_method` |
| `-4` | screened_out | **General** "removed at entry, before the consent page" bucket. Set by the **device allow-list** (`allowed_devices`) and by any future entry gate. WHICH DEVICE was detected is in `participant_extra['screenout_cause']` — see below. The code is deliberately NOT device-specific: one bucket, split by cause. | `common.set_screened_out`, called by `before._apply_device_gate` |

When you add an outcome, add it to `settings.EXIT_CODES` **and** this table —
with the place that sets it. Every code in the table must be set by real code:
a code that nothing records is a lie in the export, so a reserved-but-unwired
code gets deleted, not documented. (One such code, `-5`, has already been
removed on those grounds; `-4` was wired up instead of removed.)

### Screen-out causes (`participant_extra['screenout_cause']`)

`-4` is deliberately **generic**. A study that screens participants out at entry
for a second reason adds a **cause**, not a new exit code — so analysis keeps one
clean "screened out at entry" bucket and splits by this column, and the exit-code
table stays a short list where every entry is genuinely wired up.

Since 2026-08-11 the entry gate is a **device allow-list**, so the cause is the
**device type the server detected** — not the name of the gate. A study lists the
types it accepts in `allowed_devices` (default: all four = no gate at all), and
anything else is screened out with the detected type recorded here. The ending
writes a different sentence per type.

| Cause | Meaning | Set where |
|-------|---------|-----------|
| `phone` | Entry User-Agent classified as a phone; `allowed_devices` excludes phones. | `before._apply_device_gate` |
| `tablet` | Entry User-Agent classified as a tablet (iPad, Android without "Mobile", Kindle…); excluded. | `before._apply_device_gate` |
| `computer` | Entry User-Agent classified as a computer; excluded. **Laptop and desktop are the same type** — see the note below. | `before._apply_device_gate` |
| `unknown` | The device could not be identified: no User-Agent, a blank one, one stripped by a privacy tool, or one this template does not recognise. `unknown` is its own allow-list entry, so admitting it is a study's decision. | `before._apply_device_gate` |
| *(empty)* | `-4` recorded without a cause. Valid but discouraged — the ending falls back to a neutral "not eligible" sentence. | — |

**Why there is no `laptop` cause, and why one must never be added.** A browser
does not expose the form factor of a computer. Neither the User-Agent nor the
client hints (`Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform`,
`navigator.userAgentData`) distinguish a laptop from a tower — both report the
same platform with the mobile hint false — and the usual proxies do not work
either: a desktop may have a touch screen, a laptop may be docked to a large
monitor with its lid shut, and the Battery Status API is removed or
permission-gated in current browsers. A study that genuinely needs "laptop only"
has to ask the participant. Both are recorded as `computer`.

**Related fields.** `participant_extra['entry_device_type']` holds the server's
classification for **every** participant, including the ones let through, so
device mix is analysable even when the gate is wide open;
`participant_extra['screenout_user_agent']` keeps the evidence for a screen-out;
and `device_info_json.device_type` (when `device_capture` is on) is the CLIENT's
own guess, recorded for comparison and never enforced.

**Adding a cause** — all three steps, or a participant reads the wrong thing:

1. add it to `common.SCREENOUT_CAUSES` (the registry + its export meaning);
2. set it at your gate via `common.set_screened_out(participant, '<cause>')`,
   which records the flag, the `-4` code and the cause together;
3. add an `{% elif %}` branch with its own sentence in `outro/Ended.html`.

The ending picks its copy from the **cause**, never from the bare exit code.
`mobile` currently says "This study needs a computer" — if a new gate were to
reuse `-4` without a cause and the template keyed off the code, that participant
would be told they need a computer. The neutral fallback exists so that failure
mode degrades to a correct generic sentence instead.

---

## Stage timestamps (`participant.stage_timestamps`)

A dict `{stage_name: epoch_seconds}` filled as the participant clears each stage
(`common.stamp_stage`). Stages currently stamped:

| Stage | Set when |
|-------|----------|
| `screened_out` | The entry device gate removed the participant (their device type is not in `allowed_devices`). |
| `consent` | Leaving the welcome/consent page. |
| `confirm_id` | Prolific only: leaving the Prolific-ID confirmation page (`capture_participant_id` on). |
| `instructions_done` | Leaving the instructions page (round 1). |
| `quiz_done` | Leaving the quiz page (overwritten by the re-read pass, if any). |
| `reread_taken` | Lab only: taking the one-time re-read offer (entering intro round 2). |
| `instructions_reread_done` | Lab only: leaving the re-read instructions page (intro round 2). |
| `task_done` | Completing the last displayed round of `main`. |
| `finished` | Reaching the final results page. |

---

## Spare columns (future-proofing)

Each app's `Player` ships with unused spare columns, and every participant has a
free JSON bucket. They exist so a late-breaking measure can be added **without a
schema migration** (an export against a database whose schema predates the
running code returns HTTP 500 — see `scripts/export_data.py`).

Spare inventory:

| Location | Field(s) | Type |
|----------|----------|------|
| `before.Player` | `spare_str_1`, `spare_str_2` | LongStringField |
| `intro.Player` | `spare_str_1`, `spare_str_2` | LongStringField |
| `main.Player` | `spare_str_1`, `spare_str_2` | LongStringField |
| `outro.Player` | `spare_str_1`, `spare_str_2` | LongStringField |
| `participant` | `participant_extra` | JSON dict (via `common.extra_set`) |

### Repurpose convention (READ BEFORE REUSING A SPARE)

1. **Never rename a spare in place.** Keep the column name (`spare_str_1`) in the
   code; a rename mid-study silently splits one measure across two columns in the
   export and corrupts the record.
2. **Record the mapping here** in the table below, *with the date* you started
   writing the new meaning into it.
3. **Add a rename-before-launch todo** so that, for the *next* clean study, the
   column is renamed to its real name in one deliberate migration (never during a
   live study).

### Repurpose log

| Date | Column | Now holds | Notes |
|------|--------|-----------|-------|
| _(none yet)_ | | | |

---

## Column reference

Fill in per-study fields as you build the task. The template ships with:

- `before.Player`: `participant_label`, `treatment_group`, `consent`,
  `participant_id_url`, `participant_id_external`, `is_mobile`,
  `device_info_json`.
  - **The two id columns are a matched pair, recorded separately on purpose.**
    `participant_id_url` is the id as it ARRIVED (oTree's `?participant_label=`,
    or the consent page's hidden `?PROLIFIC_PID=` capture) and is never edited;
    `participant_id_external` is what the participant CONFIRMED or corrected on
    `before.ConfirmProlificID`, and is the value payment should use. A row where
    the two differ is a participant who edited their id — which is exactly what
    settles a later payment dispute. Both are empty in a lab session, which has
    no ConfirmProlificID page.
  - `is_mobile` is the client-side device measurement only — it blocks nobody;
    the screen-out is the server-side `allowed_devices` gate, whose User-Agent
    evidence is in `participant_extra['screenout_user_agent']`, whose detected
    device type is in `participant_extra['entry_device_type']` (recorded for
    everyone, not only the screened-out), and whose reason — the same detected
    type — is in `participant_extra['screenout_cause']`.
- `intro.Player`: the quiz fields from `intro/quiz_items.py`,
  `num_failed_attempts`. Two rounds: round 2 is the lab re-read pass, so for
  every participant who never takes the re-read offer (all Prolific and most
  lab participants) the round-2 row is empty — expected, not data loss.
  `participant.instructions_reread_used` records whether the pass was taken;
  `failed_attempts` is the experimenter's record of quiz trouble (no flag is
  recorded for the "raise your hand" notice).
- `outro.Player`: demographics + payment fields (`age`, `gender`, `bank`,
  `bic`, `sepa`, `earned`, `payouts`, …), and `feedback` (free text, collected
  only when the `pilot_feedback` flag is on).
- `participant`: see `PARTICIPANT_FIELDS` in `settings.py`.
