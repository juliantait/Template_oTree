# Entry: device check, room gate, participant identity

*Read this when you touch the entry gate, the device classifier, rooms, or participant labels.*

## The device check: what it inspects, and what it cannot

`prolific_allowed_devices` is called a device check, and the name promises more than any
browser can deliver. This section is the reference for what it actually does, so
nobody has to read the classifier to find out.

### What it inspects

**The `User-Agent` header of the entry request. Nothing else.** It does **not**
measure screen size, viewport width, touch capability, battery, or anything else
that lives in the browser: the check runs server-side before the consent page
exists, and none of that has been sent yet. Two consequences, both deliberate:

- a **desktop browser in a narrow window is NOT screened out** (proved at 640px
  by `scripts/tests/render_check.py`, leg AE);
- a **phone held in landscape IS screened out**, because it is still a phone.

`telemetry_device_capture` separately records what the client says about itself
(`is_mobile`, `device_type`, screen size) as **measurement**. It arrives later,
on the consent form, it can be edited by anyone, and it gates nothing.

### The four types

| Type | Means |
| --- | --- |
| `phone` | iPhone/iPod, Android with `Mobile`, Windows Phone, BlackBerry, Opera Mini… |
| `tablet` | iPad, Android without `Mobile`, Kindle/Silk, anything self-declaring `Tablet` |
| `computer` | **laptops AND desktops** — Windows, macOS, X11/Linux, Chrome OS, BSD |
| `unknown` | a real, readable User-Agent that matches none of the above |

**There is no `laptop` type and one cannot be added.** A browser does not expose
the form factor of a computer: neither the User-Agent nor the client hints
(`Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform`, `navigator.userAgentData`)
distinguish a laptop from a tower, and battery, touch and screen size do not
either — a desktop can have a touch screen, a laptop can sit docked to a 27"
monitor with the lid shut. A study that truly needs "laptop only" has to ask the
participant.

### The fifth state, which is not a type

`unknown` means *we read a header and did not recognise it*. It is different
from **no decision at all**, which is what the code calls `UNDETERMINED`: no
request object (oTree instantiates pages without one while it walks the skip
chain), no `User-Agent`, an empty or whitespace-only one, one carrying
characters a header may not contain, one absurdly longer than any real browser
sends, or an exception anywhere in the classifier.

`UNDETERMINED` is never a member of `prolific_allowed_devices`, and the rule about it is
**asymmetric — this is the part that is easy to get backwards**:

- **on entry it ALWAYS allows**, and records nothing at all. The gate simply
  re-decides on the next real request. A false positive turns a real
  participant away; a miss costs one noisy row.
- **it NEVER clears an existing screen-out.** A stripped header is not evidence
  that somebody switched device. If it counted as one, anyone screened out
  could lift their own screen-out by sending no `User-Agent`, which takes
  seconds, and the check would be a suggestion.

Clearing therefore requires the detected type to be **explicitly in**
`prolific_allowed_devices` (`common.device_clears_screenout`), never "not rejected".

**`unknown` and `UNDETERMINED` are not interchangeable, and the whole safety
property rests on that.** `unknown` is a device type: a real header we could
read and did not recognise. If a study has LISTED `unknown` as allowed, an
`unknown` device *does* clear a screen-out — at that point it is positive
evidence of a device the study accepts, and refusing it would contradict the
allow-list. `UNDETERMINED` is not a device at all, is never in the list, and
never clears.

### The invariant (apply this to any device type you add)

> **The clear predicate must be exactly the entry-allow predicate minus
> `UNDETERMINED`.**

Nothing else is safe or coherent. If clear allows **more** than entry there is a
hole: somebody lifts a screen-out with a device that would not have been let in.
If clear allows **less** than entry, the page is telling somebody that switching
devices will work when for them it cannot — the mistake the implementation this
was adapted from made, where `unknown` never cleared even in a study that
admitted unknown devices. Their concrete victim: a laptop whose User-Agent is
stripped by a privacy tool or a corporate proxy classifies as unknown and is
admitted on a fresh visit, but if that person first opened the study on their
phone they are screened, and switching to that very laptop does not lift it —
while the page in front of them says to switch devices. Rare, and exactly the
person the soft wall exists for.

Ours cannot be exploited because of the property that is also the **test for any
new type**: *anything that clears could equally have entered fresh on that same
device*, so admitting it on the clear path takes nothing away from the gate. Add
a fifth type tomorrow and ask that question of it — if a participant arriving on
it for the first time would be let in, it must also lift an existing screen-out;
if it would not, it must not. `UNDETERMINED` is the single carve-out, because
"could they have entered fresh on it?" has no answer for a non-device, and
treating it as a clear would let anyone lift their own screen-out by sending no
header. The accepted cost, stated plainly: somebody screened on a phone who
switches to a laptop that sends no usable header stays screened, and their
remedy is the way off the page.

### The default, and two worked configs

Shipped: `prolific_allowed_devices=['phone', 'tablet', 'computer', 'unknown']` — every
type permitted, so **the check has no participant-visible effect whatsoever**
until a study opts in. It lives in the Prolific block but is *not* part of the
prolific profile bundle: choosing the prolific study type never narrows it.

```python
# Computers only — the common case for a study with charts or a wide table.
dict(name='prolific', recruitment='prolific', prolific_allowed_devices=['computer'], …)

# Phones turned away, tablets fine.
dict(name='prolific', recruitment='prolific',
     prolific_allowed_devices=['tablet', 'computer', 'unknown'], …)
```

A comma-separated string works too (`prolific_allowed_devices='computer'`). Unknown words
are dropped, and an empty list is treated as "no gate" rather than screening the
whole sample out.

### What happens to a screened-out participant (the soft wall)

They are **held on the consent page's own index** and served
`before/screened_out.html` instead of consent. They never see the consent
question, and they never advance into the study.

- **The verdict is written immediately**, at decision time: exit code `-4`,
  `screenout_active=True`, and the detected type as the cause. Somebody who reads
  the page and closes the tab still exports as a screen-out, not an abandoner.
- **It clears if they come back on an accepted device before consent.** The exit
  code goes back to `0`, `screenout_cleared` is set to `True` for good, and every
  verdict is appended to `participant_extra['screenout_history']`. They then do
  the study as an ordinary participant. Each value is reverted only if it still
  holds what the screen-out put there, so a clear cannot clobber another
  mechanism's record.
- **Accepted consequence:** the exit code is therefore no longer write-once. An
  export taken while somebody is mid-switch shows a `-4` that later changes;
  `screenout_cleared` and the history are how you tell those rows apart.
- **After consent the check never applies again** — not to a participant who
  switches to a phone mid-study, and not to anyone already running when a deploy
  turns it on. The boundary is the durable `consent_submitted` flag, never a
  page index.
- **The way out carries NO completion code.** The button is a plain link to
  `prolific_screenout_return_url` (the Prolific participant site). A completion code
  would close their submission the moment they clicked, and a returned
  submission can never be retaken — which forecloses the outcome the page is
  asking for. There is deliberately no screened-out completion code, and none
  must be added to the pre-launch required-codes guard. It is a real `<a href>`,
  not a scripted button, so it works with JavaScript disabled.
- **Re-entry depends on the participant label.** On a real Prolific link the id
  arrives in the URL at entry, so a returning participant is rematched to the
  same row. Somebody who was screened out after entering on a **bare link** has
  no label, so nothing can rematch them and they get a fresh row on their next
  visit. That is acceptable and visible in the data — see also *Rebinding a room
  mid-study* below.

### The limits, stated plainly

- **User-Agent strings can be spoofed** by anyone who wants to. This stops
  *accidental* entry on the wrong device; it does not stop determined
  circumvention, and it is not a security control.
- **Classification is pattern-matching** against strings that change as new
  devices ship, so it will drift. Review the patterns in `core/common.py`
  occasionally, and treat `unknown` verdicts in the export as the signal that it
  is time.
- **Prolific's own device restrictions are advisory** — they filter who is shown
  the study, not who can open the link. That is why this exists in app code at
  all.

### What is actually verified (and where)

Run these against a server on a **throwaway** database. The weighting is
deliberate: most of the checks exist to prove that people are **not** screened
out.

| Test | What it proves |
| --- | --- |
| `scripts/tests/device_gate_test.py` §A1–A2 | desktop Chrome, Safari, Firefox, Edge, Chrome OS, a touchscreen Windows laptop, an iPad and an Android tablet are **never** screened — under the shipped list, and under a computers-only list |
| `scripts/tests/device_gate_test.py` §A3 | a missing, empty, whitespace-only, absurdly long, or "long and says iPhone" User-Agent proceeds to consent with **no verdict recorded** |
| `scripts/tests/device_gate_test.py` §A3b | control-character/`None`/non-string values classify as `UNDETERMINED` (uvicorn rejects control-character headers before app code, so there is no HTTP leg for that one) |
| `scripts/tests/device_gate_test.py` §B–C | an excluded type never sees consent, gets exit `-4` with the DETECTED type as its cause and copy written for that type; any type can be excluded; `unknown` is configurable like the rest |
| `scripts/tests/screenout_softwall_test.py` §1–4 | verdict written immediately (closed tab still exports `-4`); cleared on returning from an accepted device with **both** verdicts in the history; re-screened on going back; a cleared participant completes as an ordinary `exit_code=1` |
| `scripts/tests/screenout_softwall_test.py` §5 | a participant who consented on a computer and then switches to a phone is **never** touched, whatever the allow-list says |
| `scripts/tests/screenout_softwall_test.py` §6–7 | the way out is a real `<a href>` with no completion code and no `onclick`; re-entry after pressing it does not silently revive the row |
| `scripts/tests/screenout_softwall_test.py` §8 | the asymmetry, both directions, side by side: the same unusable header allows a fresh participant and does **not** clear an already-screened one |
| `scripts/tests/identity_test.py` | one row per id across re-entry, two tabs and case/whitespace variants; a clashing id claim is refused silently; a duplicate label that exists anyway does not 500; a rebound room orphans people |
| `scripts/tests/render_check.py` leg L, AD | the screen-out page's copy and its two unequal paths; the way out measured **with JavaScript disabled** (present, visible, pressable, secondary) |
| `scripts/tests/render_check.py` leg AE | a 640px-wide **desktop** window still reaches consent — width screens nobody out |

## The room welcome gate

oTree 6 serves an interstitial on every room entry — a GET on `/room/<name>`
without `welcome_page_ok=1` — that oTree 5 had no equivalent of. Stock it is bare
framework markup, and it is the FIRST thing a participant sees. This template
ships a styled copy at `_templates/room_welcome.html`, wired through
`welcome_page` on the `ROOMS` entry in `settings.py`.

It also **auto-passes anyone whose URL already identifies them** — a lab seat link
or a Prolific arrival (`?participant_label=…` or `?PROLIFIC_PID=…`) flows straight
through to the study and never perceives the page. Three properties are
load-bearing and must not be traded away:

- **A bare URL still shows the button, and no slot is claimed without a click.**
  That is what keeps bots out: they arrive with no id and usually run no
  JavaScript.
- **`form.requestSubmit()`, never `form.submit()`.** `submit()` does not fire
  submit-event listeners, so it would bypass oTree's own gate handler and — in
  any study with a participant-labels file — loop the page forever, for
  id-carrying arrivals only, which is to say for real participants and never
  while you test with a bare URL.
- **A loop guard**: auto-pass fires at most once per tab, so a failure leaves a
  clickable button rather than a participant who never arrives and leaves no
  trace.

With JavaScript disabled the gate cannot be passed at all — oTree's handler *is*
the mechanism — so the page says so plainly. Behaviour is covered end to end by
`scripts/tests/room_gate_test.py` (id present, bare URL, the loop guard in the config
where the loop is real, and the no-session lab prep flow); the look is measured by
`scripts/tests/render_check.py` leg AR.

## Rebinding a room mid-study orphans participants

**Operational rule, not a bug we can fix.** oTree matches a participant label
**within a session** (`session.pp_set`), so the moment a room is bound to a NEW
session, anybody mid-study in the old one can no longer be rematched: their next
visit lands on a fresh row in the new session and they start again, while their
old row keeps their data and their id.

So: **never rebind the room while participants are running.** `scripts/start.sh`
deliberately reuses a room's already-bound session for this reason. If you must
create a new session, treat everyone in the old one as finished, and expect
duplicate ids **across** sessions (which is fine — the constraint is per
session). Pinned by `scripts/tests/identity_test.py` §6.

## Duplicate participant labels

oTree resolves a returning participant by label, and its lookup calls `.one()`:
**two rows sharing a label is an uncaught `MultipleResultsFound` — a 500 at the
front door, for the id's real owner, permanently.** Re-entry is that lookup, and
so is the device screen-out's soft wall, so this template defends it twice
(`core/identity.py`):

1. **It refuses to create one.** Every label write goes through
   `identity.claim_label`, which will not stamp a label another row in the
   session already holds. The participant is not blocked and is told nothing;
   the owning row's code lands in `before.Player.prolific_label_conflict` for
   payment triage.
2. **It survives one that exists anyway** — a hand-edited row, a legacy
   database. oTree's lookup is patched to match labels **in Python, with the
   same normalisation conflict detection uses** (whitespace-collapsed,
   case-folded), so `ABC123` rejoins the row holding `abc123` and the answer
   cannot change with the database collation — oTree's own `filter_by(label=…)`
   is SQL, and would behave one way on sqlite and another on postgres. Among the
   rows that match, it joins **the earliest that has not FINISHED** (a finished row is a dead end to join; a *screened-out* row is
   terminal but must stay joinable, because joining it is what lifts the
   screen-out). When it actually sees a duplicate it is **loud**: an ERROR line
   in the server log naming every row, and a `duplicate_label_seen` record on
   the joined participant. An ordinary lookup records nothing.

**If the server refuses to boot with a `RuntimeError` from
`identity.assert_duplicate_label_guard`, oTree has drifted** — its entry lookup
has been renamed, moved, or has a different signature. That is deliberate: the
guard is asserted once, at app import, where a failure costs a boot rather than
a participant's page. Re-point `core/identity.py` at the new lookup; do not delete
the assertion. (The *early* install from `settings.py` is expected to fail
harmlessly — oTree's views are not importable that early — and never raises.)
