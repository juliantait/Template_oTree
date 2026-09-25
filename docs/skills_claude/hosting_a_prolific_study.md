# Hosting and running a study on Prolific: the end-to-end agent playbook

> **Referenced by (update these if you move or rename this file):**
> - `docs/skills_claude/README.md`
> - `docs/README.md`

Audience: bossman or any agent asked to **host and run** a study built from this
template on Prolific, start to finish. This is the orchestrating playbook: it says
**do this, then that**, and hands off the detail to the two reference docs rather
than repeating them. Online studies only; a lab study needs none of this.

The three reference docs this skill drives, and the split between them:

- [`../hosting_railway.md`](../hosting_railway.md), the **hosting** info doc:
  everything a hosted deploy needs in general (container host, managed Postgres,
  `DATABASE_URL`, the boot guard, the untested caveats), plus the verified Railway
  PROCEDURE (deploy-repo export, tokens, GraphQL-vs-CLI, deploy order, domains,
  env vars, study day). Source of truth for hosting.
- [`../running_on_prolific.md`](../running_on_prolific.md), the **study-side**
  info doc: the five completion codes, the entry sequence, the device allow-list,
  the participant id, what each ending does, the before-you-launch list. Source of
  truth for how the template wires to Prolific.
- **This file**, the API procedure and the human-only steps for creating and
  configuring the Prolific study itself, plus the order the three pieces go in.

Do not restate the two info docs here. If something about hosting or study-side
wiring is wrong, fix it there and link.

## The order (each step delegates)

1. **Deploy the study on a host.** Follow
   [`../hosting_railway.md`](../hosting_railway.md) end to end: export the deploy
   repo, create the project and Postgres, set the env vars, deploy, generate the
   domain, run the crash rehearsal. You come out of this with a live
   `https://<railway-domain>/room/<room_name>` URL and a bound session.
2. **Wire the study to Prolific.** Follow
   [`../running_on_prolific.md`](../running_on_prolific.md): turn on the Prolific
   study type, create the **five** completion codes (one per ending population) in
   the Prolific UI and paste them into the matching `settings.py` keys, decide
   `prolific_allowed_devices`, set the `screenout_return_url`, and clear the
   pre-launch guard (`scripts/prelaunch_check.py`). Bind a **fresh** session
   AFTER the codes commit, because a session's config is frozen at creation, so a
   pre-codes session keeps the placeholder frozen inside it (the launch-order
   rules are in [`../hosting_railway.md`](../hosting_railway.md)'s "Study day").
3. **Create and configure the Prolific study via the API, then the human-only
   steps.** That is the rest of this file.

## Step 3: the Prolific study, the API, the money, and where a person is unavoidable

**The verified surface below was verified by the team that ran the live study,
against a draft study on 2026-08-18. This file was written from that record. It
does not re-verify anything, and the block marked NOT VERIFIED is carried as NOT
VERIFIED. Never treat that block as tested.**

### Agent autonomy: what the token gets you and where a human is unavoidable

With the API token an agent can create and fully configure the study draft
(reward, places, naming) and query its state. It **cannot** Preview or
Test-as-a-participant: both are UI-only, and Test-as-a-participant is the ONLY
end-to-end check of the return-to-Prolific and payment path. **Publishing via the
API is NOT verified** (see the NOT VERIFIED block), so treat publishing as a UI
step performed by a person until it is confirmed against the API. See the
`HUMAN STEP` markers below.

### Credentials

- Base URL `https://api.prolific.com/api/v1/`.
- Header `Authorization: Token <token>`.
- **Keep the token OUTSIDE this repository**, in a file in a gitignored directory
  or your OS keychain. Where exactly is site-specific and deliberately not
  recorded here: this file is tracked and ships with every copy of the template,
  so a precise pointer to where a live API token sits helps no legitimate reader
  (they have their own token, on their own machine) and only helps someone you
  would not want reading it. Never commit the token. Same stance as the Railway
  project token in [`../hosting_railway.md`](../hosting_railway.md).

### Verified working

- `GET /studies/<id>/` returns the full study object (about 90 fields).
- `PATCH /studies/<id>/` with a JSON body. Confirmed editable on an **UNPUBLISHED
  draft**: `name`, `reward`, `estimated_completion_time`,
  `total_available_places`, `external_study_url`.
- **Verify every PATCH by re-reading the object** with `GET`. Same discipline as
  every Railway mutation: the response is a claim, the re-read is the fact.

Fields worth reading back: `status`, `is_ready_to_publish`,
`average_reward_per_hour` (pence/hour, RECOMPUTED by Prolific), `places_taken`,
`number_of_submissions`, `total_cost`, `fees_percentage`, `is_underpaying`,
`minimum_reward_per_hour`, `published_at`.

### Semantics that bite (get these wrong and it costs money or strands a participant)

- **`reward` is in PENCE.** `175` means £1.75. Sending pounds overpays by 100x.
- **The advertised hourly rate is computed from the BASE reward only.** Prolific
  states that **bonuses may not be used to meet the minimum hourly pay
  requirement**, so the base reward must clear the minimum **by itself**. You
  cannot top up an underpaying base with a bonus and pass. Minimum £6/hr,
  recommended around £9/hr. Read back `is_underpaying` and
  `average_reward_per_hour` after any `reward` or `estimated_completion_time`
  change.
- **Returned and timed-out submissions reopen the place automatically and are not
  charged.** So `total_available_places` is the number of **completions you will
  pay for**, not a recruitment pool that shrinks with every dropout. Padding it
  buys more DATA; it does not insure against attrition.
- **Prolific places must NEVER exceed the oTree session's seat count.** The
  participant who arrives past the last seat meets a **full room** and cannot
  start. Padding the oTree session is free; padding Prolific costs money. So size
  the oTree session generously and recruit exactly the number you want:
  `total_available_places` no greater than the oTree seat count, always.

### Study naming convention (Julian)

Studies are named **"A Study on Decision Making"**, not more descriptive, and with
**no duration in the title**. A descriptive title primes participants; a duration
in the title is a second place the number lives and it drifts (one study shipped
"(~15 min)" while the field said 12, then 13). `estimated_completion_time` is the
single source of truth and Prolific displays it already.

### The URL and codes you hand Prolific

The `external_study_url` you PATCH must carry the participant id and point at the
live room:

```
https://<railway-domain>/room/<room_name>?participant_label={{%PROLIFIC_PID%}}
```

The **five completion codes**, one per ending population, and the
`screenout_return_url` are **study configuration**, not something to invent here.
They are specified and guarded in
[`../running_on_prolific.md`](../running_on_prolific.md) (section 2) and
`scripts/prelaunch_check.py`. This is Step 2 above: create all five in the
Prolific study, paste them into the matching `settings.py` keys, and bind a FRESH
session AFTER the codes commit. The launch-order rules are in
[`../hosting_railway.md`](../hosting_railway.md)'s "Study day" and in
[`../running_on_prolific.md`](../running_on_prolific.md).

### Where the API stops and a person must act

Two things have no API and are the exact points a fresh agent stalls silently, so
each carries a marker you cannot miss:

> **HUMAN STEP (UI only).** **Preview** the study. There is no API for it. A
> person opens the Prolific preview to see what a participant sees before
> publishing.

> **HUMAN STEP (UI only, and the ONLY end-to-end check).** **Test as a
> participant** is the only way to exercise the **return-to-Prolific and payment
> path end to end**, meaning the completion-code redirect actually landing back
> on Prolific and marking a submission. No API call reproduces it. It needs an
> email to create a test participant account, and it may **consume one of your
> places**, so check that before running it and pad `total_available_places` if
> it does. Skipping this is how a broken completion code reaches real
> participants: every server-side test can pass while the return link is still
> wrong.

### NOT VERIFIED (do not assume these work, and do not tell anyone they were tested)

The following were **not exercised** against the API and must be treated as
unknown, not as working:

- **Publishing** a study via the API.
- Editing **filters, completion codes, screeners**.
- **Participant groups**.
- **Listing or approving submissions.**
- **Paying bonuses.**

If a workflow needs one of these, treat it as a UI step performed by a person
until it has actually been verified against the API, and mark it as such at the
point it is needed. Do not quietly promote anything out of this block.
