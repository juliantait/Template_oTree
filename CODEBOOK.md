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
| `-4` | screened_out | **General** "removed at entry, before the consent page" bucket. Set by the **device allow-list** (`allowed_devices`) and by any future entry gate. WHICH DEVICE was detected is in `participant_extra['screenout_cause']` — see below. The code is deliberately NOT device-specific: one bucket, split by cause. **NOT write-once** — see the note directly below. | `common.set_screened_out`, called by `before._apply_device_gate` |

> **`-4` IS THE ONE CODE THAT CAN CHANGE BACK.** The device screen-out is a soft
> wall: a participant who returns on an accepted device **before consent** is
> cleared, and their code reverts to `0` (`common.clear_screened_out`) so
> somebody who is really doing the study does not sit in the data as screened
> out. Each value is reverted only if it still holds what the screen-out put
> there, so a clear cannot clobber a code another mechanism wrote in the
> meantime. Consequences for analysis, stated plainly:
> * an export taken while somebody is mid-switch shows a `-4` that later becomes
>   `0` and then, usually, `1`;
> * the STATE is reset, the HISTORY never is. `participant.screenout_cleared`
>   stays `True` for good and `participant_extra['screenout_history']` keeps
>   every verdict, so "how many people did the gate turn away?" is answered from
>   those, not from the exit code;
> * after consent nothing here applies: the check never touches a participant
>   past `participant.consent_submitted`.

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
| What happens | `comprehension_dq` flags the participant, exit code `-2`, straight to the ending, back to Prolific with `prolific_dq_code` | the one-time re-read offer (`quiz_reread`), then a dismissible "raise your hand" notice; at **twice** the threshold that notice also names the attempt count. Attempts are never capped and nobody is ejected |
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
| `unknown` | A real, readable User-Agent that matches none of the three device families. `unknown` is its own allow-list entry, so admitting it is a study's decision. It does **not** mean "no User-Agent" — see the row below. | `before._apply_device_gate` |
| *(never recorded)* | **No decision.** No request object, no User-Agent, a blank/malformed/absurdly long one, or an exception in the classifier (`common.UNDETERMINED`). This is NOT a device type and NOT a cause: the participant is allowed through and **nothing at all is written**, so it can never appear in the export. It also never CLEARS an existing screen-out — absence of evidence is not evidence of a device switch. | — |
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
3. give it its own sentence. The three physical device types share ONE template
   branch, worded from `detected_device_label` (`common.DEVICE_TYPE_LABELS`, via
   `common.screenout_vars` — the one cause→noun mapping, so the two pages cannot
   drift); a NEW cause gets no label and therefore falls to the neutral fallback
   until you either add its own `{% elif %}` branch in
   `before/screened_out.html` (the page a screened-out participant is held on)
   and in `outro/Ended.html` (if your gate fires after entry), or — only if it
   really is a fifth device type — add its label to `DEVICE_TYPE_LABELS`.

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
| `screenout_cleared` | A screen-out was LIFTED: they came back on an accepted device before consent. |
| `consent` | Leaving the welcome/consent page. |
| `confirm_id` | Prolific only: leaving the Prolific-ID confirmation page (`prolific_capture_participant_id` on). |
| `ai_safety_agreed` | Leaving the AI-safety agreement page, i.e. when the tab monitor was armed. Only where that page is shown (`tab_monitor` on, so Prolific by default and never the lab). |
| `left_before_app` | Leaving ANY page of the `before` app — deliberately **overwritten** by each one, so its final value is the moment the participant left the entry block, whichever pages that config showed (`common.stamp_left_before_app`). |
| `instructions_done` | Leaving the instructions page (round 1). |
| `quiz_done` | Leaving the quiz page (overwritten by the re-read pass, if any). |
| `reread_taken` | Lab only: taking the one-time re-read offer (entering intro round 2). |
| `instructions_reread_done` | Lab only: leaving the re-read instructions page (intro round 2). |
| `task_done` | Completing the last displayed round of `main`. |
| `finished` | Reaching the final results page. |
| `prolific_return_clicked` | Prolific-redirect sessions only, **best-effort**: the first click on the results page's "Back to Prolific" link (`outro.results_live_method`). It rides the page's live socket just before the browser navigates away, so JS off or a dropped socket leaves it ABSENT for somebody who really did return — absence means "no click recorded", never "did not return". Feeds the dashboard's "no return click" pill (a prompt to look, not a verdict); never read by anything participant-facing. |

**Measuring from the end of the entry block.** Use **`left_before_app`**. Which
page actually ends that block is CONFIG-DEPENDENT — `consent` in the lab,
`ai_safety_agreed` for Prolific (with `confirm_id` in between), something else
again for a study that adds an entry page — so anything that names one page is
wrong for some configuration, silently, and shows up as dwell time billed to the
wrong phase. That has already happened once here: the agreement page's dwell was
counted as instructions time, and only for Prolific. Every `before` page calls
`common.stamp_left_before_app`, which overwrites, so the stamp is correct for
every configuration including ones not written yet; a new entry page only has to
call it.

The older recipe — take the **maximum** of `consent` / `confirm_id` /
`ai_safety_agreed` — survives only as a fallback for participants who were
already mid-flow when `left_before_app` was deployed and will never have it.
`experimenter_dashboard._intro_seconds` does exactly this (and measures to
`quiz_done`, i.e. the whole intro block including a re-read, not to
`instructions_done`).

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
  `device_info_json`, `prolific_label_conflict`.
  - **The two id columns are a matched pair, recorded separately on purpose.**
    `participant_id_url` is the id as it ARRIVED (oTree's `?participant_label=`,
    or the consent page's hidden `?PROLIFIC_PID=` capture) and is never edited;
    `participant_id_external` is what the participant CONFIRMED or corrected on
    `before.ConfirmProlificID`, and is the value payment should use. A row where
    the two differ is a participant who edited their id — which is exactly what
    settles a later payment dispute. Both are empty in a lab session, which has
    no ConfirmProlificID page.
  - **`prolific_label_conflict` is empty for everybody, normally.** It carries
    the OWNING ROW's participant code when this participant typed an id that
    another row in the session already held: the claim was REFUSED (they keep
    their own row and finish the study normally, and their typed value is still
    in `participant_id_external` verbatim), because two rows sharing a label is
    a permanent 500 at entry for whoever really owns that id — see
    `identity.py`. A non-empty value is a PAYMENT TRIAGE flag: look at both rows
    before paying either. Nothing is ever shown to the participant, and no
    marker is ever written into `participant.label`, which stays the real id or
    empty. `participant_extra['prolific_label_conflict']` holds the fuller
    record (which id was refused, and whose row holds it).
  - **Two more keys exist for the case where a duplicate label got in ANYWAY**
    (a hand-edited row, a legacy database, a path we did not anticipate):
    `participant_extra['duplicate_label_seen']` is written on the row a
    returning participant was joined to, naming the label and every row holding
    it — entry degrades gracefully for them, but never silently for us, and the
    same event is logged at ERROR level. `participant_extra['duplicate_label_
    guard_missing']` appears only if the guard itself was not installed at
    entry, which should be impossible (it is asserted at boot) — treat either
    key as "read the server log before paying anybody in this session".
  - **`participant_extra['label_claim']`** records the outcome of the LAST
    attempt to stamp a participant label (`before._claim_participant_label`):
    `'set'`, `'unchanged'` (they already held that id, perhaps spelled
    differently), `'empty'`, `'conflict'` (refused — another row holds it) or
    `'error'` (the claim raised and was swallowed so the page could not 500).
    `'error'` is the one worth grepping for: it means a label was NOT written
    for a reason nobody anticipated, and it was previously invisible — the
    outcome was returned to two call sites that both ignored it.
  - **The client/server device disagreement, in `device_info_json`.** The server
    classifies the entry request's User-Agent (`participant_extra
    ['entry_device_type']`); the browser also classifies itself, and the two
    sitting side by side is the point. Read them in this order:
    `ua_rules` — `'server'` means the browser applied the SERVER's rules (there
    is only one pattern list, shipped to the page via `js_vars`);
    `'unavailable'` means they never arrived and the client classified nothing,
    so that row says nothing about agreement either way.
    `device_type_ua` — this browser's own User-Agent under those rules. It
    should equal `entry_device_type`; if it does not, the browser is reporting a
    different User-Agent than the request header carried (an extension, a proxy,
    client hints) — not a device disagreement.
    `device_type` — the client's final answer, `device_type_ua` refined by
    signals the server cannot see, with `device_type_signals` naming the ones
    that fired (today: `ipados_touch`, an iPad claiming to be a Macintosh).
    A difference between `device_type_ua` and `device_type` is the GENUINE
    disagreement this measurement exists for, and it is attributable to a named
    signal. Nothing here ever gates: the gate is the server's alone.
  - **CHANGED 2026-08-13 — what switches device capture on.** `is_mobile` and
    `device_info_json` are now filled if and only if **`device_capture`** is on.
    Until this date the two fields were also switched on by
    `prolific_capture_participant_id` (then named `capture_participant_id`), so
    turning on Prolific ID capture silently turned on device capture as well.
    **A config with `prolific_capture_participant_id` ON and `device_capture`
    OFF recorded device info before this change and records none after it.**
    Neither shipped recruitment profile is affected — `lab` has both off and
    `prolific` has both on — and the template had no live studies, so no data is
    lost; but an export compared ACROSS this date must be read with it in mind.
  - `is_mobile` is the client-side device measurement only — it blocks nobody;
    the screen-out is the server-side `allowed_devices` gate, whose User-Agent
    evidence is in `participant_extra['screenout_user_agent']`, whose detected
    device type is in `participant_extra['entry_device_type']` (recorded for
    everyone, not only the screened-out), and whose reason — the same detected
    type — is in `participant_extra['screenout_cause']`. Every verdict the gate
    reaches is appended to `participant_extra['screenout_history']`
    (`{ts, ua, device, screened_out, action}`, oldest first, deduped, first
    entry never dropped); the flat facts to filter on are the participant fields
    `screened_out` and `screenout_cleared`.
- `intro.Player`: the quiz fields from `intro/quiz_items.py`,
  `num_failed_attempts`, `quiz_attempt_log` (every graded submission — see
  the section above), and `redoinstructions` (`1` on the quiz submission that
  took the lab's one-time re-read offer, else `0`/empty; a quiz-page form
  field, so it is only ever written by the quiz POST).
  Two rounds: round 2 is the lab re-read pass, so for
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
  - **`sepa` has three states (CHANGED 2026-08-13): `1` = IBAN checked, inside
    SEPA; `0` = IBAN checked, OUTSIDE SEPA; empty = the check never ran** — no
    bank details were collected (every Prolific participant, and any config with
    `collect_bank_details` off). Until this date the field shipped `initial=1`,
    which collapsed "checked, fine" with "never asked": every Prolific row
    exported `sepa=1` as if a SEPA check had passed. A lab participant whose row
    holds `1` or `0` means exactly what it did before; only the never-asked rows
    change, from a false `1` to empty. The Results-page warning fires on
    `sepa == 0` and empty is not `0`, so participants who were never asked stop
    matching a warning that was never about them. The field is nullable: code
    reads it with `field_maybe_none`, never bare (CLAUDE.md).
- `participant`: see `PARTICIPANT_FIELDS` in `settings.py`.

**Removed columns (2026-08-12).** Six columns that no code path ever wrote or
read were deleted rather than documented (the same rule as unwired exit codes:
a column nothing records is a lie in the export): `intro.Player.
participant_label` (the *before* app's copy is the real one), `intro.Player.
skiptoquiz`, and `outro.Player.selected_round1` / `selected_round2` / `pay1` /
`pay2` (the payment path records its results in `payouts`,
`all_round_payoffs`, `selected_sum` and `earned`). This was a SCHEMA change,
applied while the template has no live data; an export from before that date
carries the six columns, blank.

**Deploying this over a study that HAS data needs `otree resetdb`** — the same
build also ADDS `before.Player.prolific_label_conflict`, and oTree has no
migrations, so a database without that column 500s on every page that loads the
model. Retiring the in-flight sessions is not sufficient. See the warning box
under "Before a deploy" in README.md for the full procedure and the one
hand-migration alternative.
