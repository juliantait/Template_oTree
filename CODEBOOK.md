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
| `-2` | comprehension | Disqualified: failed the comprehension check too many times. **Prolific only** — see the next section for what the same threshold means in a lab session. | `intro.quiz.error_message` |
| `-3` | tab_monitor | Disqualified: AI-safety / tab-switch monitor. **Prolific only** — the tab monitor is not supported in the lab. | `common.focus_live_method` |
| `-4` | screened_out | **General** "removed at entry, before the consent page" bucket. Set by the **device allow-list** (`allowed_devices`) and by any future entry gate. WHICH DEVICE was detected is in `participant_extra['screenout_cause']` — see below. The code is deliberately NOT device-specific: one bucket, split by cause. | `common.set_screened_out`, called by `before._apply_device_gate` |

When you add an outcome, add it to `settings.EXIT_CODES` **and** this table —
with the place that sets it. Every code in the table must be set by real code:
a code that nothing records is a lie in the export, so a reserved-but-unwired
code gets deleted, not documented. (One such code, `-5`, has already been
removed on those grounds; `-4` was wired up instead of removed.)

### Comprehension failure means different things by study type

`comprehension_max_failures` is **one counter and one threshold**
(`participant.failed_attempts`, incremented in `intro.quiz.error_message`), the
same value in both study types. What differs is the consequence of crossing it:

| | Prolific | Lab |
|---|---|---|
| Crossing the threshold is | the point of **ejection** | the point at which the study **starts helping** |
| What happens | `comprehension_dq` flags the participant, exit code `-2`, straight to the ending, back to Prolific with `dq_code` | the one-time re-read offer (`quiz_reread`), then a dismissible "raise your hand" notice; at **twice** the threshold that notice also names the attempt count. Attempts are never capped and nobody is ejected |
| Exit code | `-2` | **`1` (finished)** — they completed the study |

**So `-2` never appears in a lab export, and its absence is not evidence that
nobody struggled.** The analysis-time flag is
`failed_attempts >= comprehension_max_failures` — deliberately the *same
predicate* the online rule ejects on, so "failed comprehension" means one thing
across both study types. Supporting columns, all existing:
`instructions_reread_used` and the `reread_taken` stamp (took the supervised
re-read); `intro.Player.num_failed_attempts` is **per round**, so round 2's
count is "still failing after being walked through the instructions again";
`outro.Player.quiz_bonus_awarded == 0` is the monetary trace of any failure.

**The integrity modules (`comprehension_dq`, `tab_monitor`) are not supported in
a lab session**, and `scripts/prelaunch_check.py` fails on a lab config that
turns either on. The reason is conceptual: in the lab a participant who does not
consent or does not pass comprehension simply cannot do the study, and that
essentially never happens because people know what they signed up for when they
come to the lab. The mechanical consequence — why it is a hard gate rather than
advice — is that a disqualified participant is not a completer, so they skip the
page collecting the lab's IBAN/BIC and the payment summary and are stranded at
the machine with no record of where to send their fee.

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

## Quiz attempt log (`intro.Player.quiz_attempt_log`)

Every **graded** quiz submission, as a JSON list, so an analyst can see *which
items people get wrong* rather than only how often they were wrong. Written by
`intro.log_quiz_attempt`, called from `intro.quiz.error_message`.

**It is a per-round `intro.Player` column**, so round 1 is the first pass and
round 2 is the post-re-read pass (lab only) — the two are separated for free,
with no extra field. Deliberately not a participant var: those reach the export
only through `PARTICIPANT_FIELDS`, and `participant_extra` would mix it in with
every other ad-hoc value. Deliberately not a spare column either — the spares
exist to avoid a schema change on a *live* study.

Shape — one object per submission, in submission order:

| Key | Meaning |
|---|---|
| `n` | Attempt number **within this round**, from 1. |
| `t` | Epoch seconds (3 dp) when the submission was graded. |
| `answers` | `{item_field: submitted_value}` for every item on the page; values truncated at 80 chars. An item left blank is `""`. |
| `wrong` | The item fields that were wrong **as judged at the time**. `[]` means the attempt passed. |

```json
[{"n": 1, "t": 1755000000.123, "answers": {"q1": "Yes", "q2": "Nothing happens"}, "wrong": ["q2"]},
 {"n": 2, "t": 1755000041.880, "answers": {"q1": "Yes", "q2": "I can try again"}, "wrong": []}]
```

**`wrong` is stored, never recomputed.** `intro/quiz_items.py` changes between
studies and can change between sessions of one study, so grading an old
`answers` blob against today's item set would be silently wrong with nothing to
notice it by. Trust `wrong`; treat `answers` as the raw record.

**Uncapped.** Every attempt is stored, however many there are — including in the
lab, where attempts themselves are unlimited. The log is for occasional
curiosity about which items people get wrong, not routine analysis data, so
completeness beats column size (Julian, 2026-08-12). The number of attempts in a
round is simply `len(log)`.

**Not every POST is an attempt.** Taking the re-read offer and the DEBUG
clickthrough (`verify_quiz=False`) both return before grading, so neither
appears here.

**Where to find it.** The column is in the RAW oTree export (`intro.Player`);
the standard cleaning script (`format_session_data.py`) strips JSON columns, so
it is **absent downstream by design** — pull it from the raw export if you want
it.

**Analysis caveat (Julian, 2026-08-12).** The **last entry is the passing
attempt for anyone who completed the quiz — but not for everyone**: a Prolific
participant disqualified at `comprehension_max_failures`, and anyone who
abandoned mid-quiz, ends on a FAILING entry. Do not assume the final row is a
pass; test `wrong == []`, and cross-check `participant.exit_code`.

**Instrumentation, so it never blocks a page.** The whole writer is wrapped
(CLAUDE.md): if a value will not serialise or the column is corrupt, the answer
is still graded and the participant still proceeds — the row is simply missing.
An empty string means "nothing was ever logged", not "no attempts".

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
  `num_failed_attempts`, and `quiz_attempt_log` (every graded submission — see
  the section above). Two rounds: round 2 is the lab re-read pass, so for
  every participant who never takes the re-read offer (all Prolific and most
  lab participants) the round-2 row is empty — expected, not data loss.
  `participant.instructions_reread_used` records whether the pass was taken;
  `failed_attempts` is the experimenter's record of quiz trouble (no flag is
  recorded for the "raise your hand" notice, nor for its escalated form — both
  are implied by `failed_attempts` against `comprehension_max_failures`; see the
  exit-code section above).
- `outro.Player`: demographics + payment fields (`age`, `gender`, `bank`,
  `bic`, `sepa`, `earned`, `payouts`, …), and `feedback` (free text, collected
  only when the `pilot_feedback` flag is on).
- `participant`: see `PARTICIPANT_FIELDS` in `settings.py`.
