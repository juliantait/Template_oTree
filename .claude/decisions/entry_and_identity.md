# Decisions: Entry, device gate and identity

Read when you touch the room, the device check and its screen-out, or how a participant is identified.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## The single oTree room was renamed `experiment` → `study`, so the URL reads `/room/study` — 2026-08-17

Decided by Julian. The participant-facing room URL is the one bit of plumbing a
participant actually sees (it goes in the Prolific study link and on printed lab
sheets), so its name should be neutral — not `experiment`, which reads as jargon,
and deliberately not anything that commits the URL to a lab or an online framing.
`study` is the right neutral word for both: it is what Prolific already calls the
thing, and a lab participant reading `/room/study` is not misled either. The
display name moved in step: `Experimental Session` → `Study Session`.

There is still exactly **ONE** room. This is the whole point — the same room
serves both study types (`prolific` and `lab`); the study type is one of the
three orthogonal controls resolved in `settings.py`, and it is not the room's job
to encode it. A second room for lab-vs-Prolific would duplicate the room-welcome
gate and the start.sh binding for a distinction the config already draws.

**Practical consequence — matters for a deployed study, not for this template:**
a room is bound to a name, so any session already bound to `/room/experiment`,
and any bookmarked or printed `/room/experiment` link, stops resolving the moment
the name changes. For this template there is no live session and no circulated
link, so the rename is free; for a study already in the field it would strand
participants and must not be done mid-run. **Rejected:** two rooms (defeats the
one-room-serves-both design); keeping `experiment` (leaks jargon into the one
URL a participant sees). **Enforced:** `settings.ROOMS`; the room tests bind to
`study` (`room_gate_test`, `identity_test`, `full_journey_test`,
`render_check`), so a half-done rename fails to bind a session and goes red.

---

## The device screen-out is a soft wall, clearable before consent only — 2026-08-12

A screened participant is HELD on the entry page (not walked to an ending oTree
could never bring them back from), and a later pre-consent request from an
accepted device clears the screen-out; exit code `-4` is the one code that can
revert. After consent the check never applies again. The state is reset, the
history never is — "how many did the gate turn away" is counted from
`screenout_history`, not the exit code.
**Rejected:** routing to a proper ending page (irreversible in oTree), and a
write-once `-4` (would leave genuine finishers recorded as screened out).
**Enforced:** `scripts/tests/screenout_softwall_test.py`; the consent boundary is the
durable `participant.consent_submitted` fact, not a page index. Full working:
`_ai/screenout_softwall_log.md` (local only — `_ai/` is gitignored; not in a clone).

---

## The clear predicate is exactly the entry-allow predicate minus `undetermined` — 2026-08-12

If clearing allowed *more* than entry, a screen-out could be lifted by a device
that would not have been let in; if *less*, the page tells someone switching
will work when for them it cannot (the reference implementation had this bug:
its `unknown` never cleared, stranding privacy-proxy laptops). `undetermined`
is the single carve-out — no usable header is not a device, and treating it as
a clear would let anyone lift their own screen-out by sending no User-Agent.
**Enforced:** `common.device_clears_screenout` (explicit membership, so
`undetermined` cannot satisfy it whatever a config says);
`scripts/tests/screenout_softwall_test.py` §8 states the two asymmetric assertions side
by side.

---

## `unknown` and `undetermined` are different states — 2026-08-12

A User-Agent that parsed and matched nothing (`unknown`) is a device type a
study may accept or reject like any other; no usable header at all
(`undetermined`) is *not a device type* and must always be allowed. Collapsed,
a study rejecting `unknown` starts ejecting laptops behind privacy proxies.
This is the model case of the collapsed-distinction rule in `CLAUDE.md`.
**Enforced:** `common.classify_device`; `scripts/tests/device_gate_test.py`, which is
deliberately weighted toward false positives (browsers that must NOT be
screened). Full working: `_ai/device_allowlist_log.md` (local only — `_ai/` is gitignored; not in a clone).

---

## Participant identity is decided in one place — 2026-08-12

"Is this the same participant id?" was answered twice — label comparison in
Python (case-folded) and row lookup in SQL (collation-dependent) — so a
returning `ABC123` took a fresh row against a stored `abc123`, and behaviour
differed between sqlite (dev) and postgres (production). One implementation,
called by both.
**Enforced:** `core/identity.py`; `scripts/tests/identity_test.py`. This bug pattern is
generalised as the inverted collapsed-distinction rule in `CLAUDE.md`.
