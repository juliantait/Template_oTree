# Experimenter dashboard — the spec as briefed

**Written 2026-08-12. THIS IS THE BRIEF, NOT A DESCRIPTION OF THE CODE.**

Another worker is building this feature right now and is **not** working from
this document. It was written from the brief as given, without reading their
output, and it is deliberately **not** to be updated to match whatever gets
built. Its whole purpose is to let Julian compare, later, what was SPECIFIED
against what was BUILT — which it can only do if it stays a record of the
specification. If the two differ, that is the finding, not an error in this
file.

Nothing here has been implemented, verified or tested by the author of this
document.

---

## Purpose

A live, at-a-glance view of a running session for whoever is supervising it.
Both study types need it and both need very similar information: in the lab the
supervisor is the experimenter in the room; on Prolific it is whoever is
watching the study run.

## Architecture

- **In-process**, as a custom route inside oTree — not a separate service.
- Appended to `otree.urls.routes`, which `asgi.py` imports as a plain
  module-level list.
- Installed with **the same monkeypatch discipline as `identity.py`**: quiet
  when the module is legitimately not importable yet, loud on symbol drift. The
  two cases must not be collapsed into one `except`.
- **Reuses oTree's own login** via `_requires_login` rather than inventing an
  auth mechanism.

## The two hard constraints (these are the acceptance criteria)

1. **Strictly READ-ONLY.** The dashboard observes; it never writes participant
   or session state.
2. **The dashboard breaks instead of the study.** Every handler wrapped, so a
   failure in the dashboard cannot take a participant's page down with it —
   **and this must be PROVEN by a test** that makes a handler raise and then
   shows a participant can still complete a page.

## Contents

**One row per participant**, keyed on `participant.label` — the seat number in
the lab, the Prolific ID online.

**A six-step timeline, with EQUAL spacing:**

    ENTRY → INSTRUCTIONS → QUIZ → TASK → QUESTIONNAIRE → DONE

- The marker occupies **one step at a time** and advances on completion.
- **Consent, the ID page and the tab-monitor agreement all fold into ENTRY.**
- **During TASK the marker carries the round number inside it**, and advances
  *within* the step rather than along the line.

**Per-row cells:**

- **Quiz attempts** — white at the start; fills as attempts rise; **red at
  `comprehension_max_failures`**; **green with the attempt count once passed**,
  so `1` means passed first time.
- **Time on instructions** — from the stage timestamps.
- **Earnings** — once known.
- **Completion** — goes green at finished.

**Terminal states OVERRIDE the marker** and fill the row's state cell with an
emoji and a colour, wherever along the timeline the marker had reached:

- screened out
- comprehension disqualification
- tab-monitor disqualification
- declined consent

**Stalled participants:** the row goes **amber after 5 minutes on a single
page**. Configurable — Julian expects to tune this.

**Refresh:** poll and repaint on a **2 second floor**, skipping a tick if one is
already in flight.

## Explicit exclusions (both Julian)

- **No device type.**
- **No quiz attempt history** — too much for an overview.

## Design

Reuse the `base.css` tokens so it looks like the study — but it is an
**operator screen**: information density beats elegance, and it must be
**readable across a room**.

**Extensibility was an explicit ask:** adding a column later should be a small,
obvious change.

## Two defaults chosen rather than asked about

Recorded here because they were decisions, not omissions:

1. Participants who never got past ENTRY are **shown but de-emphasised**, with a
   filter toggle to hide them.
2. The **agreement page folds into ENTRY** rather than earning a dot of its own.

---

## Implementation Cost

**Appended 2026-08-12, after the feature was built. Everything above this line is
the specification as briefed and has NOT been edited** — this section records what
the work cost, which is the one thing that can only be added afterwards. It is
deliberately kept below the rule so the spec above stays a clean record to compare
against.

**A precise per-feature figure is not available from the tooling, and this section
does not pretend otherwise.** `mm cost` reports **per-PROJECT cumulative totals**,
not per-worker and not per-feature. Several workers ran in this folder on the same
days, on unrelated work (a settings.py batch, an export-script fix, a
behaviour-preserving cleanup, the participant-identity consolidation), and the
tooling does not attribute spend to any of them separately. There is therefore no
way to say from the tooling what the experimenter dashboard alone cost.

What can be recorded honestly is the folder total:

| Figure | Value | What it is |
|---|---|---|
| Project | `oTree-Template` | the whole folder, not this feature |
| Sessions | **19** | cumulative, all workers, all tasks |
| Cost | **≈ USD 2132** | cumulative, all workers, all tasks |
| As at | **2026-08-12** | the day the dashboard was built and audited |

**Read that as a folder cumulative, not as this feature's cost.** It is an upper
bound on the dashboard's share and a loose one: the dashboard is one of at least
half a dozen pieces of work inside those 19 sessions, and the folder total also
carries the template's own earlier development. Anyone wanting a real per-feature
number would have to attribute sessions to tasks by hand from the history; that
has not been done, and no estimate is offered here rather than an invented split.

Related: `_ai/dashboard_conformance_audit.md` (local only — `_ai/` is gitignored; not in a clone) records what was built against the
spec above (19 of 26 checklist items met as specified, 6 met differently, 1 not
met), including which deviations were deliberate. That audit was itself part of
the spend recorded above.
