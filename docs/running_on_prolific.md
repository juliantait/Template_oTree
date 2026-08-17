# Running this template on Prolific

**Status: everything described here is implemented and tested.** This is an
operating guide, not a conversion plan.

An earlier version of this file was a to-do list for porting a lab-only template
to Prolific, written against an external reference project. Every item on it has
since been built, and two of the mechanisms it documented no longer exist:

- the **inline mobile block** (an `error_message` that returned a "return
  submission" link inside a validation error) — replaced by a server-side gate
  that runs *before the consent page is rendered*, see §4;
- the **`timedout` participant variable** (`0/1/3`) — replaced by the numeric
  `exit_code` scheme in `settings.EXIT_CODES` and `CODEBOOK.md`. There is no
  `timedout` field anywhere in the template. A `timed_out = -5` exit code was
  briefly defined and then deleted, precisely because nothing set it.

If you find advice elsewhere that references either, it is stale.

---

## 1. Turn it on

Prolific behaviour is one axis of the three-axis config (see `settings.py` and
`CLAUDE.md`): set the **study type**.

```python
SESSION_CONFIGS = [
    dict(name='prolific', display_name='…', recruitment='prolific', …),
]
```

`recruitment='prolific'` resolves at import into explicit flags, so the admin's
session-configuration view shows exactly what ran:

| Flag | Prolific | Lab | What it does |
|------|---------|-----|--------------|
| `prolific_capture_participant_id` | on | off | Captures the platform id at entry and shows the confirmation page |
| `prolific_completion_redirects` | on | off | Explicit consent radio + return-to-Prolific buttons with completion codes |
| `tab_monitor` | on | off | Tab-switch monitor |
| `comprehension_dq` | on | off | Disqualify after too many quiz failures |
| `device_capture`, `passive_capture` | on | off | Device/screen and on-page measurement |
| `collect_bank_details`, `collect_demographics` | off | on | Lab pays by transfer and asks demographics itself |
| `quiz_reread` | off | on | The supervised one-time re-read pass |

`allowed_devices` is deliberately **not** narrowed by the profile — see §4.

## 2. Completion codes

Three codes, per session config, all shipping as `REPLACE_*` placeholders:

| Key | Used for | Exit code |
|-----|----------|-----------|
| `prolific_cc_code` | Normal completion | `1` |
| `prolific_noconsent_code` | Declined consent | `-1` |
| `prolific_dq_code` | Disqualified (comprehension or tab monitor) | `-2` / `-3` |

**FIVE CODES, ONE PER ENDING POPULATION** (2026-08-15). Create all five in the
Prolific study UI and paste them into the matching config keys:

| Ending | Config key | Prolific code type |
|---|---|---|
| Completed | `prolific_cc_code` | **COMPLETED — auto-approves the submission** |
| Declined consent | `prolific_noconsent_code` | REQUEST_RETURN |
| Comprehension DQ | `prolific_dq_quiz_code` | REQUEST_RETURN |
| Tab-monitor DQ | `prolific_dq_tab_code` | REQUEST_RETURN |
| Device screen-out | `prolific_device_code` | REQUEST_RETURN |

**Only the completed code auto-approves and pays.** The other four are
REQUEST_RETURN codes, which PROMPT the participant to return the submission and
free the place — that is why the device screen-out carries a code now instead of
a bare link, which used to leave the submission in limbo. **Each REQUEST_RETURN
code needs its own reason text**, and Prolific's API requires `return_reason` on
a code of that type, so write a short participant-facing sentence for each
(what happened, and that they are not at fault where that is true).

**Never reuse one code for two endings.** Once two populations have submitted
under the same code, Prolific's submission list cannot tell them apart and
nothing downstream recovers it.

**COMPLETION CODE SHAPE — `REASON-XXXXXX`.** A semantic prefix plus six random
alphanumerics: `COMP-K27XQ4` for a completion, `NOCONS-T8Q4R1` for a declined
consent, `DQ-W3FM9K` for a disqualification. Readable in a Prolific submission
list (you can tell at a glance why a submission carries the code it does) and
unguessable by a participant. The template ships them as
`COMP-XXXXXX_REPLACE` / `NOCONS-XXXXXX_REPLACE` / `DQ-XXXXXX_REPLACE`, so the
placeholder itself teaches the convention to whoever replaces it, and the
pre-launch guard refuses to launch while any `REPLACE` survives.

**The COMPLETION code is the one worth guarding**, because on Prolific it can
**auto-approve a payment**. Keep its random part at six characters or more, make
it genuinely random, and never use a short number — a guessable completion code
is somebody else's money. (A disqualified participant cannot read it off the
page: each ending is served only its own code — see below.)

**A device screened out at entry (`-4`) has NO completion code, deliberately.**
It gets a plain link to `prolific_screenout_return_url` (the Prolific participant site)
carrying nothing, so the submission stays OPEN and the participant can still
reopen the study on an accepted device and finish it — which submitting a code
would foreclose for good, since a returned submission can never be retaken. Do
not add a fourth code, and do not add one to the pre-launch required-codes
guard. See §4.

`outro.completion_link()` picks the code from the participant's outcome; the
ending pages render a **link**, never an automatic redirect, so oTree has
committed the final data before the participant leaves, and a participant whose
JavaScript never ran can still leave.

**The prelaunch check refuses to let a `REPLACE_*` placeholder reach a real
launch** — `settings._check_prelaunch()` prints a MUST-BE banner at startup for
any placeholder still in place, and for `DEBUG` still being on. Read the banner
before every launch.

## 3. The entry sequence

Two variants, and the shared page in the middle is shared **exactly**:

```
LAB       startpage (the "Welcome to CREED" gate, experimenter-advanced)
          -> welcome/consent
PROLIFIC  [device allow-list — server-side, renders no page]
          -> welcome/consent
          -> ConfirmProlificID
```

**The one rule that governs this**: a page either mentions Prolific or it does
not — never both, and never CREED plus Prolific. There is no hybrid entry page.

- `before/startpage.html` is the **only** page carrying the CREED welcome
  header. It is lab-only (`is_displayed` on `recruitment == 'lab'`) and has no
  Next button by design: the experimenter advances the room when everyone is
  seated.
- `before/welcome+consent.html` is **shared and identical in both variants** —
  no CREED header, no ID field, and no sentence naming the platform, a
  completion code or a participant id. Its config branches vary payment-mechanics
  wording only (`collect_bank_details`), because the same page renders in a lab
  where Prolific is meaningless.
- `before/confirm_prolific_id.html` is the **only page in the study that mentions
  Prolific**. Gated on `prolific_capture_participant_id`, so a lab session never sees it.

`scripts/tests/gated_flow_test.py` asserts all of this against the rendered visible text
of both variants, so a regression fails the build rather than reaching a
participant.

## 4. The device allow-list (`allowed_devices`)

**Wide open by default, including in the Prolific profile.** Choosing the
Prolific study type must never start screening devices out on its own; narrow it
explicitly:

```python
dict(name='prolific', recruitment='prolific', allowed_devices=['computer'], …)
```

The four types are `phone`, `tablet`, `computer` and `unknown`. **`computer`
covers laptops and desktops** — a browser exposes no way to tell them apart
(not the User-Agent, not client hints, not battery/touch/screen size), so there
is no `laptop` type and one must never be added; a study that truly needs that
has to ask the participant. **`unknown`** means a real User-Agent was read and
matched no family; it is listed like any other type, so admitting those
participants is a configuration decision rather than a code change. A request
with NO usable User-Agent at all is a different thing — no decision — and is
always allowed in. **README's "The device check" section is the full reference**
(what it inspects, the asymmetry, the limits); this is the operational summary.

With the **default** list (all four) it does nothing at all — every device
completes normally, and `device_capture` still *records* the device as
measurement that blocks nobody.

When **narrowed**, the decision is made server-side in `before.welcome.get()`,
from the entry request's User-Agent, **before a single byte of the consent page
exists**. The participant is flagged with exit code `-4` and HELD on that page,
which serves `before/screened_out.html` instead of the consent question. **That
is the first and only screen they ever see** — and, because they are held rather
than walked to an ending, a later pre-consent request from an accepted device
CLEARS the verdict and lets them carry on. Their way out is a plain link to
`prolific_screenout_return_url` with **no completion code**, so their submission stays
open. The client's own opinion of what it is (`device_info_json.device_type`) is
recorded beside the server's for comparison and never enforced — a client-side
check is trivially bypassed.

Exit code `-4` is the **general** "removed at entry" bucket, not a device-specific
code. The gate records *which device type it detected* in
`participant_extra['screenout_cause']` (`'phone'`, `'tablet'`, `'computer'` or
`'unknown'`), and the ending picks its wording from that cause, naming what the
study does accept. To add another entry screen-out reason, add a cause — not a
new exit code. See `common.SCREENOUT_CAUSES` and the CODEBOOK section on
screen-out causes. `screenout_cleared` (participant field) and
`participant_extra['screenout_history']` record device switches for the export.

## 5. Getting the participant id

Prolific appends its id to the study URL. The template accepts **either**
spelling:

- `?participant_label={{%PROLIFIC_PID%}}` — oTree's own parameter, which it
  resolves into `participant.label` for you. **Prefer this** in the Prolific
  study URL field.
- `?PROLIFIC_PID=…` — Prolific's default. Captured client-side on the consent
  page into a hidden field.

The capture must happen on the consent page because **the query string does not
survive oTree's `InitializeParticipant` redirect** — by the time the participant
reaches the confirmation page it is gone. Without it, every participant would
have to type their id by hand.

Both values are then recorded separately, on purpose:

| Column | What it is |
|--------|-----------|
| `participant_id_url` | The id as it ARRIVED. Never edited. |
| `participant_id_external` | What the participant CONFIRMED or corrected. This is the value payment should use, and it becomes `participant.label`. |

A row where the two differ is a participant who edited their id — which is
exactly what settles a payment dispute later.

The confirmation page pre-fills the arrived id and lets the participant correct
it. Nothing is required: an empty submit is always accepted, so it can never be a
dead end for a friend-tester on a bare room link.

> **Security, do not remove:** the prefill is participant-controlled (it comes
> from the URL), and oTree's ibis template engine does **not** auto-escape `{{ }}`
> output. `before/confirm_prolific_id.html` applies `|escape` explicitly. Without
> it a crafted id is a reflected XSS.

## 6. Endings

`outro/Ended.html` is the shared terminal page for everyone who did not complete
normally, with four branches: `no_consent`, `disqualified`, `screened_out` and a
default. `outro/Results.html` is the normal completion ending. Both render a
"Back to Prolific" button only when `prolific_completion_redirects` is on, so the lab
never sees platform wording.

## 7. Before you launch

- [ ] Replace all four `REPLACE_*` codes; confirm the prelaunch banner is clean.
- [ ] Set `OTREE_PRODUCTION=1` so `DEBUG` is off and every skip control and quiz
      solution is gone from the page source.
- [ ] Set the study URL with `?participant_label={{%PROLIFIC_PID%}}`.
- [ ] Decide `allowed_devices` explicitly (§4) and, if narrowed, check the ending copy for each excluded type.
- [ ] Check `showup` and `expected_duration_minutes` — the consent page quotes
      both from config, so a testing config would advertise a length and a fee
      the study does not run.
- [ ] Run `OTREE_PRODUCTION=1 python scripts/prelaunch_check.py`. It exits
      non-zero on any placeholder or testing value, so it can gate a launcher or
      CI — unlike the startup banner, which is only advisory.
- [ ] Run `scripts/tests/http_flow_test.py`, `scripts/tests/gated_flow_test.py` and
      `scripts/tests/device_gate_test.py` against a throwaway database.
- [ ] Run `scripts/predeploy_check.sh <copy-of-live-db>` before deploying over
      running sessions. It boots the candidate build against a **copy of the live
      database** and drives real participants over real HTTP — a fresh install
      cannot detect a broken upgrade path.

The two guards answer different questions and you want both: `prelaunch_check.py`
is a static config check ("is this configuration safe to launch?"),
`predeploy_check.sh` is a dynamic upgrade gate ("will the running study survive
this deploy?").
- [ ] Fuzz the participant-facing surfaces with a real browser. Bot tests passing
      is not evidence that a browser works; that practice previously found an XSS
      and a dropped participant label that server-side testing missed.

## 8. Where things live

| Concern | File |
|---------|------|
| Study type, flags, codes, exit codes | `settings.py` |
| Entry, consent, id confirmation, screen-out gate | `before/` |
| Screen-out causes, exit codes, tab-monitor handler | `common.py` |
| Tab-switch monitor (client) | `_static/global/js/tab_monitor.js` |
| Endings and completion links | `outro/` |
| Every exported column and its meaning | `CODEBOOK.md` |
