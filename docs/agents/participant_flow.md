# Participant flow (lab and Prolific)

*Read this when you change the page sequence, endings, completion codes, or anything Prolific-specific.*

## Participant flow by study type

The two charts below are derived from the actual page sequences and
`is_displayed` gates (`before`, `intro`, `main`, `outro`) and the
`settings.EXIT_CODES` table. Dashed nodes/edges are **flag-dependent** (the
pilot feedback page appears only when `pilot_feedback` is on); everything else
is always part of that study type. The charts are laid out identically so the
lab/prolific differences stand out: entry (hold screen vs consent question),
the quiz-failure rule (supervised re-read vs disqualification), the tab
monitor, and the ending (bank details + demographics vs completion codes).

### Prolific

```mermaid
flowchart TD
    classDef terminal fill:#fdecea,stroke:#c0392b
    classDef success fill:#eaf7ea,stroke:#2e7d32
    classDef flagdep stroke-dasharray:6 4

    Start(["Opens the Prolific study link"]) --> Gate
    subgraph BEFORE ["before — entry"]
        Gate{"device in prolific_allowed_devices?<br>server-side User-Agent check,<br>runs on the consent page's own request"}
        Gate -- "default list (all devices), or a permitted type" --> Welcome
        Welcome["welcome + consent<br>explicit consent question,<br>Prolific ID + device capture"]
        ScreenOut["screened_out — shown INSTEAD of consent,<br>at the same page index (exit code -4).<br>Codeless link back to Prolific."]
        ConfirmID["ConfirmProlificID — confirm the platform id"]
        Arm["TabMonitorAgree — ARMS THE TAB MONITOR.<br>EVERY page after this one is monitored by default<br>(core/participant_tab_monitor.py): intro + main EJECT at the cap,<br>outro RECORDS ONLY — see the outro subgraph"]
    end
    Gate -. "a type the study excludes:<br>consent is never shown" .-> ScreenOut
    ScreenOut -. "returns on an accepted device<br>BEFORE consent: verdict CLEARED" .-> Welcome
    Welcome -- "does not consent" --> EndedNC
    Welcome -- "consents" --> ConfirmID
    ConfirmID --> Arm
    Arm --> Instr1

    subgraph INTRO ["intro — instructions + quiz (tab monitor live — round 2 exists but is never shown online)"]
        Instr1["instructing — instructions (round 1)"] --> Quiz1["quiz (round 1)"]
        Quiz1 -- "wrong answers, failures below<br>the cap: error, try again" --> Quiz1
    end
    Quiz1 -- "failures reach quiz_comprehension_max_failures" --> EndedDQ
    Quiz1 -. "tab-away violations reach<br>tab_monitor_max_violations<br>(counted on the instructions and quiz too)" .-> EndedTM

    Quiz1 -- "all correct" --> Game
    subgraph MAIN ["main — task rounds 1..num_experimental_rounds (tab monitor live)"]
        Game["GameStart — task page"] --> Payoff["payoff — round result"]
        Payoff -- "next round" --> Game
    end
    Game -. "tab-away violations reach<br>tab_monitor_max_violations<br>(one count across intro + main)" .-> EndedTM
    Payoff -- "after the last round" --> FbGate

    subgraph OUTRO ["outro — ending. Each ending carries ITS OWN completion code: completed -> prolific_cc_code (auto-approve), declined consent -> prolific_noconsent_code, comprehension DQ -> prolific_dq_quiz_code, tab-monitor DQ -> prolific_dq_tab_code (all request-return); the device screen-out never reaches here and carries prolific_device_code. Demographics skipped: Prolific exports demographics itself. Tab monitor still watching, but RECORD-ONLY: violations here land in tab_monitor_focus_loss_count_outro and NEVER eject. To READ any of this, sort on tab_monitor_flag — see CODEBOOK"]
        FbGate{"pilot_feedback<br>flag on?"}
        FbGate -. "yes (pilots only)" .-> Fb["Feedback — free-text pilot feedback"]
        Fb -.-> Results
        FbGate -- "no (real run)" --> Results
        Results["Results — payment summary"]
    end

    Results --> Done["FINISHED — exit code 1<br>'Back to Prolific' button with prolific_cc_code"]
    EndedNC["outro Ended — exit code -1 (no_consent)<br>'Back to Prolific' with prolific_noconsent_code"]
    EndedDQ["outro Ended — exit code -2 (comprehension)<br>'Back to Prolific' with prolific_dq_code"]
    EndedTM["outro Ended — exit code -3 (tab_monitor)<br>'Back to Prolific' with prolific_dq_code"]
    Abandon["Closes the tab at any point —<br>no ending page, exit code stays 0 (abandoned)"]

    class Done success
    class EndedNC,EndedDQ,EndedTM,ScreenOut,Abandon terminal
    class Fb,FbGate,Gate,ScreenOut flagdep
```

| Exit code | Terminal state | Ending the participant sees | Completion code |
|----------:|----------------|-----------------------------|-----------------|
| `1` finished | Completed the study | `outro` Results → "Back to Prolific" | `prolific_cc_code` |
| `0` abandoned | Closed the tab, never reached the end | none (handled by Prolific as timed-out/returned) | none |
| `-1` no_consent | Declined consent at entry | `outro` Ended → "Back to Prolific" | `prolific_noconsent_code` |
| `-2` comprehension | Failed the quiz `quiz_comprehension_max_failures` times | `outro` Ended → "Back to Prolific" | `prolific_dq_code` |
| `-3` tab_monitor | Tab-away violations reached the cap | `outro` Ended → "Back to Prolific" | `prolific_dq_code` |
| `-4` screened_out | Device stopped by the entry allow-list (only when `prolific_allowed_devices` is narrowed) | `before` screened_out, in place of consent and their FIRST page — a plain link back to Prolific | **none, deliberately** ([why](entry_and_identity.md#the-device-check-what-it-inspects-and-what-it-cannot)) |

> **The table above is the whole table:** every code in `settings.EXIT_CODES` is
> set by real code and appears here (`CODEBOOK.md` names the line that sets
> each). A reserved-but-unwired code is a lie in the export, so it gets deleted
> rather than documented — one such code, `-5`, was removed on those grounds.

### Lab

```mermaid
flowchart TD
    classDef terminal fill:#fdecea,stroke:#c0392b
    classDef success fill:#eaf7ea,stroke:#2e7d32
    classDef flagdep stroke-dasharray:6 4

    Start(["Seated at a lab computer"]) --> Hold
    subgraph BEFORE ["before — entry"]
        Hold["startpage — hold screen,<br>experimenter starts the session"] --> Welcome
        Welcome["welcome + consent<br>implicit consent: continuing = consenting<br>(no ID or device capture; device allow-list wide open;<br>no TabMonitorAgree — the lab ships the tab monitor OFF,<br>and that page exists only to arm it)"]
    end
    Welcome --> Instr1

    subgraph INTRO ["intro — instructions + quiz (round 2 = the single supervised re-read pass)"]
        Instr1["instructing — instructions (round 1)"] --> Quiz1["quiz (round 1)"]
        Quiz1 -- "wrong answers, failures below<br>the threshold: error, try again" --> Quiz1
        Quiz1 -- "failures reach quiz_comprehension_max_failures<br>while the re-read is unused" --> Offer{"modal: re-read the<br>instructions? (available once)"}
        Offer -- "dismiss — keep trying,<br>offer stays open" --> Quiz1
        Offer -- "take it — consumed on entering<br>the second pass, not when offered" --> Instr2["instructing (round 2) —<br>instructions again from the start"]
        Instr2 --> Quiz2["quiz (round 2)"]
        Quiz2 -- "wrong answers: dismissible modal<br>'raise your hand and speak to the experimenter'<br>(from 2× the threshold it also names the<br>attempt count) — attempts are never capped,<br>no disqualification, nothing recorded<br>beyond comprehension_failed_attempts" --> Quiz2
    end
    Quiz1 -- "all correct" --> Game
    Quiz2 -- "all correct" --> Game

    subgraph MAIN ["main — task rounds 1..num_experimental_rounds (no tab monitor)"]
        Game["GameStart — task page"] --> Payoff["payoff — round result"]
        Payoff -- "next round" --> Game
    end
    Payoff -- "after the last round" --> Demo

    subgraph OUTRO ["outro — ending (Ended page unreachable: lab has no disqualification or consent-decline path)"]
        Demo["Demographics — age + gender,<br>IBAN/BIC bank details"] --> FbGate{"pilot_feedback<br>flag on?"}
        FbGate -. "yes (pilots only)" .-> Fb["Feedback — free-text pilot feedback"]
        Fb -.-> Results
        FbGate -- "no (real run)" --> Results
        Results["Results — payment summary"]
    end

    Results --> Done["FINISHED — exit code 1<br>paid by bank transfer"]
    Abandon["Leaves at any point —<br>no ending page, exit code stays 0 (abandoned)"]

    class Done success
    class Abandon terminal
    class Fb,FbGate flagdep
```

| Exit code | Terminal state | Ending the participant sees | Completion code |
|----------:|----------------|-----------------------------|-----------------|
| `1` finished | Completed the study | `outro` Results (payment summary; paid by bank transfer) | n/a (no redirects in lab) |
| `0` abandoned | Left the session | none — `comprehension_failed_attempts` and the stage timestamps are the experimenter's record | n/a |

`-1`/`-2`/`-3` cannot occur in lab: consent is implicit, and **the integrity
modules (`quiz_comprehension_dq`, `tab_monitor`) are not supported in a lab session**
— `scripts/prelaunch_check.py` FAILS on a lab config that turns either on. The
reason is conceptual: in the lab, a participant who does not consent or does not
pass the comprehension check simply cannot do the study, and that essentially
never happens because people know what they signed up for when they come to the
lab. The mechanical consequence, which is why it is a hard gate, is that a
disqualified participant is not a completer, so they skip the bank-details page
and the payment summary and are stranded at the machine. The lab's comprehension
rule is the re-read pass plus the "raise your hand" notice; a failed lab
participant is identified at analysis time by
`comprehension_failed_attempts >= quiz_comprehension_max_failures` (see `CODEBOOK.md`).
`-4` cannot occur either unless you narrow `prolific_allowed_devices` on the config — it
permits every device type by default in every profile, and a lab session's
computers would pass anyway.

## Running online on Prolific
Prolific support is **built in** — there is no manual wiring to do. Select the
`prolific` recruitment profile (set `recruitment='prolific'` on your session
config, as the shipped `prolific` config does) and the profile resolves the
relevant feature flags into explicit config keys at import (see the "Parameter
scheme" section and `settings.py`). That bundle turns on:

- **`prolific_capture_participant_id`** — captures the external Prolific participant ID at
  entry (stored in the `participant_id_external` field).
- **`prolific_completion_redirects`** — routes each ending to Prolific with the matching
  completion code: normal completion, declined consent (no-consent) and
  disqualification (comprehension / tab monitor). The entry screen-out is the
  exception: it returns them with NO code, so their submission stays open.
  **Each ending is served ONLY its own code** — a disqualified participant cannot
  read the completion code out of the page source and self-approve. Pinned by
  `scripts/tests/gated_flow_test.py`.

### The five endings and their codes

**Every ending population has its own code.** A shared code collapses two
populations irreversibly on Prolific's side — once a comprehension failure and a
tab-monitor ejection have both submitted under one `DQ-` code, the submission
list cannot tell them apart and nothing downstream recovers it.

| Ending | Config key | Shipped placeholder | Prolific action |
|---|---|---|---|
| Completed | `prolific_cc_code` | `COMP-XXXXXX_REPLACE` | **auto-approve** (this is the one that pays) |
| Declined consent | `prolific_noconsent_code` | `NOCONS-XXXXXX_REPLACE` | request return |
| Comprehension DQ | `prolific_dq_quiz_code` | `DQ-QUIZ-XXXXXX_REPLACE` | request return |
| Tab-monitor DQ | `prolific_dq_tab_code` | `DQ-TAB-XXXXXX_REPLACE` | request return |
| Device screen-out | `prolific_device_code` | `DEVICE-XXXXXX_REPLACE` | request return |

**Only the completed code auto-approves.** The other four are created on Prolific
as **REQUEST_RETURN** codes, each with its own reason text — the API requires
`return_reason` on such a code — so the participant is prompted to return the
submission, which frees the place. That is why the screen-out now carries a code
at all: the bare researcher URL it replaces left the submission in limbo. (This
reverses an earlier decision; see `DECISIONS.md`, both entries.)

Each ending is served **only its own code**, injected per page — never a bundle
in the template context — so a disqualified participant cannot read the completed
code out of the page source and self-approve. Pinned by
`scripts/tests/completion_codes_test.py`, one browser journey per ending.

**Codes are shaped `REASON-XXXXXX`** — a semantic prefix plus six random
alphanumerics (`COMP-K27XQ4`, `NOCONS-T8Q4R1`, `DQ-QUIZ-M4P2W7`): readable in a
Prolific submission list, unguessable by a participant. The template ships them as
`COMP-XXXXXX_REPLACE` / `NOCONS-XXXXXX_REPLACE` / `DQ-XXXXXX_REPLACE`, so the
placeholder itself teaches the convention — and **`scripts/prelaunch_check.py`
refuses to launch while any `REPLACE` survives**, matching by shape rather than by
exact string. The COMPLETION code is the one to guard hardest: on Prolific it can
auto-approve a payment, so keep its random part six or more characters and never
a short number. Full operational detail: `docs/running_on_prolific.md`.
- the **integrity modules** — `tab_monitor`, `quiz_comprehension_dq`, plus
  `telemetry_passive_capture` and `telemetry_device_capture`. With `tab_monitor` on, **every page
  after the agreement screen is monitored by default** (`core/participant_tab_monitor.py` — a
  page can only be unmonitored by opting out explicitly), with one deliberate
  asymmetry: same monitor, same counting, **different consequence by phase**.
  During the instructions, quiz and task, violations count toward
  disqualification (`tab_monitor_focus_loss_count`, ejecting at
  `tab_monitor_max_violations`); during the **outro they are recorded only**
  (`tab_monitor_focus_loss_count_outro`) and never eject — by then the task is over and
  the data collected, so disqualifying somebody who completed the whole study
  (say, for tabbing to Prolific while reading their receipt) would cost a
  real participant for no benefit. A nonzero outro count on a finished
  participant is measurement, not a near-miss.

The profile deliberately does **not** narrow `prolific_allowed_devices` (see the
parameter scheme, [parameters.md](parameters.md)): screening devices out is a separate, explicit decision,
so set e.g. `prolific_allowed_devices=['computer']` on the config if you want it.

**Completion codes** are config values, set in `settings.py`: the
`SESSION_CONFIG_DEFAULTS` placeholders `prolific_cc_code` (normal), `prolific_noconsent_code`
(declined consent) and `prolific_dq_code` (disqualified) — replace the `REPLACE_*`
values, or override them per-config on your `prolific` session config. The
prelaunch check refuses to run online while any code is still a `REPLACE_*`
placeholder. **There are three, not four:** a device screened out at entry gets
a codeless link back to Prolific instead, so its submission stays open — see
[The device check](entry_and_identity.md#the-device-check-what-it-inspects-and-what-it-cannot).

For the operational walkthrough — creating the Prolific study, wiring the URLs,
and the finish-screen routing in practice — see **`docs/running_on_prolific.md`**.
