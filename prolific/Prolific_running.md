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
| `capture_participant_id` | on | off | Captures the platform id at entry and shows the confirmation page |
| `completion_redirects` | on | off | Explicit consent radio + return-to-Prolific buttons with completion codes |
| `tab_monitor` | on | off | Tab-switch / AI-safety monitor |
| `comprehension_dq` | on | off | Disqualify after too many quiz failures |
| `device_capture`, `passive_capture` | on | off | Device/screen and on-page measurement |
| `collect_bank_details`, `collect_demographics` | off | on | Lab pays by transfer and asks demographics itself |
| `quiz_reread` | off | on | The supervised one-time re-read pass |

`mobile_screenout` is deliberately **not** in the profile — see §4.

## 2. Completion codes

Four codes, per session config, all shipping as `REPLACE_*` placeholders:

| Key | Used for | Exit code |
|-----|----------|-----------|
| `cc_code` | Normal completion | `1` |
| `noconsent_code` | Declined consent | `-1` |
| `dq_code` | Disqualified (comprehension or tab monitor) | `-2` / `-3` |
| `error_code` | Screened out at entry | `-4` |

`outro.completion_link()` picks the code from the participant's outcome; the
ending pages render a **button**, never an automatic redirect, so oTree has
committed the final data before the participant leaves.

**The prelaunch check refuses to let a `REPLACE_*` placeholder reach a real
launch** — `settings._check_prelaunch()` prints a MUST-BE banner at startup for
any placeholder still in place, and for `DEBUG` still being on. Read the banner
before every launch.

## 3. The entry sequence

Two variants, and the shared page in the middle is shared **exactly**:

```
LAB       startpage (the "Welcome to CREED" gate, experimenter-advanced)
          -> welcome/consent
PROLIFIC  [mobile screen-out — server-side, renders no page]
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
  Prolific**. Gated on `capture_participant_id`, so a lab session never sees it.

`tests/gated_flow_test.py` asserts all of this against the rendered visible text
of both variants, so a regression fails the build rather than reaching a
participant.

## 4. The mobile screen-out (`mobile_screenout`)

**Off by default, including in the Prolific profile.** Choosing the Prolific study
type must never start screening phones out on its own; turn it on explicitly:

```python
dict(name='prolific', recruitment='prolific', mobile_screenout=1, …)
```

With it **off** it does nothing at all — a phone completes normally, and
`device_capture` still *records* `is_mobile` as measurement that blocks nobody.

With it **on**, the decision is made server-side in `before.welcome.get()`, from
the entry request's User-Agent, **before a single byte of the consent page
exists**. There is no inline error and no page of its own: the participant is
flagged, given exit code `-4`, and every page between entry and the ending is
gated on `common.is_screened_out()`, so they are walked straight to
`outro/Ended.html`. **That ending is the first and only screen they ever see.**

Exit code `-4` is the **general** "removed at entry" bucket, not a phone-specific
code. The gate records *why* in `participant_extra['screenout_cause']`
(`'mobile'`), and the ending picks its wording from that cause. To add another
entry screen-out reason, add a cause — not a new exit code. See
`common.SCREENOUT_CAUSES` and the CODEBOOK section on screen-out causes.

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
"Back to Prolific" button only when `completion_redirects` is on, so the lab
never sees platform wording.

## 7. Before you launch

- [ ] Replace all four `REPLACE_*` codes; confirm the prelaunch banner is clean.
- [ ] Set `OTREE_PRODUCTION=1` so `DEBUG` is off and every skip control and quiz
      solution is gone from the page source.
- [ ] Set the study URL with `?participant_label={{%PROLIFIC_PID%}}`.
- [ ] Decide `mobile_screenout` explicitly (§4) and, if on, check the ending copy.
- [ ] Check `showup` and `expected_duration_minutes` — the consent page quotes
      both from config, so a testing config would advertise a length and a fee
      the study does not run.
- [ ] Run `OTREE_PRODUCTION=1 python scripts/prelaunch_check.py`. It exits
      non-zero on any placeholder or testing value, so it can gate a launcher or
      CI — unlike the startup banner, which is only advisory.
- [ ] Run `tests/http_flow_test.py`, `tests/gated_flow_test.py` and
      `tests/mobile_screenout_test.py` against a throwaway database.
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
| Tab-switch monitor (client) | `_static/global/js/ai_safety_monitor.js` |
| Endings and completion links | `outro/` |
| Every exported column and its meaning | `CODEBOOK.md` |
