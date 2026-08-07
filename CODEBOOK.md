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

| Code | Name | Meaning |
|-----:|------|---------|
| `1` | finished | Completed the study normally. |
| `0` | abandoned | Created but never reached the end (the default). |
| `-1` | no_consent | Declined consent on the entry page. |
| `-2` | comprehension | Disqualified: failed the comprehension check too many times. |
| `-3` | tab_monitor | Disqualified: AI-safety / tab-switch monitor. |
| `-4` | screened_out | Screened out at entry (e.g. mobile device). |
| `-5` | timed_out | Inactivity / never matched in time. |

When you add an outcome, add it to `settings.EXIT_CODES` **and** this table.

---

## Stage timestamps (`participant.stage_timestamps`)

A dict `{stage_name: epoch_seconds}` filled as the participant clears each stage
(`common.stamp_stage`). Stages currently stamped:

| Stage | Set when |
|-------|----------|
| `consent` | Leaving the welcome/consent page. |
| `instructions_done` | Leaving the instructions page. |
| `quiz_done` | Leaving the quiz page. |
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
  `participant_id_external`, `is_mobile`, `device_info_json`.
- `intro.Player`: the quiz fields from `intro/quiz_items.py`,
  `num_failed_attempts`.
- `outro.Player`: demographics + payment fields (`age`, `gender`, `bank`,
  `bic`, `sepa`, `earned`, `payouts`, …).
- `participant`: see `PARTICIPANT_FIELDS` in `settings.py`.
