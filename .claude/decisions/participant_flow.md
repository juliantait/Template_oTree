# Decisions: Participant flow, endings and completion

Read when you change the page sequence, consent, an ending, exit codes, completion codes or the Prolific redirects.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## The "up to 2 weeks" payment line is LAB-ONLY, and the closing instruction is a shared CENTRED component — 2026-08-21

Two fixes to `outro/Results.html`, one participant-facing and one structural.

**The payment line.** "Please leave up to 2 weeks for the payment to be
processed" was unconditional. It describes the LAB's payment: the experimenter
collects an IBAN and the institution transfers weeks later. A Prolific
participant is paid **through Prolific**, on Prolific's timetable, so the
sentence is not merely redundant for them — it is **false**, and it invites a
support message about a payment we never make. It is now gated on the STUDY TYPE
axis (`is_lab`, one implementation in `common.is_lab`), joining the "stay
seated" sentence already under that gate.

**Gated on the axis, NOT on a payment module flag.** `collect_outro_bank_details`
was the tempting read — it is literally the bank-details switch — and it is
wrong twice: the `test` config turns it OFF on a `lab` session that still pays by
transfer, and "which platform pays" is a property of *where the study runs*, not
of which form we happened to show. Flags decide mechanics, `recruitment` decides
copy (`docs/conventions.md`).

**The closing instruction, and the collapsed distinction under it.** "Please
click the button below to complete the study and return to Prolific" rendered
**flush left** under a centred receipt. The cause was not a broken rule.
`.section-text` deliberately sets only the reading measure and centres the
*block*, leaving text alignment to the card FAMILY; the results card is a plain
`.screen-card`, so the sentence inherited the card's flush-left while the receipt
above it was centred by `.payment-summary` and the notes below it by
`.results-notes`. **The same sentence on `outro/Ended.html` was centred all
along**, for an unrelated reason — `.narrative-card .section-text`. One concept,
two implementations, already disagreeing: CLAUDE.md's inverted rule, wearing a
stylesheet. Rejected: adding `text-align: center` to the results page, which
would have made it three implementations. Both endings now compose the shared
`.closing-instruction` component (base.css, with a specimen in
`_static/global/html/template.html`), so the alignment is decided once.

**It also MOVED**: directly under the receipt, above the payment notes and the
payoff table, so it sits with the thank-you and the total rather than buried
between the SEPA warning and the table. Julian chose this over placing it
immediately after the greeting *inside* the 340px receipt, which would have told
participants to leave before showing what they earned and pushed the Total row
into the fold that `results.css`'s short-viewport block exists to keep it out of.

**Where it is enforced.** `scripts/tests/ending_copy_test.py` — four
configurations walked to Results over real HTTP in **production mode** (it boots
its own server, so the mode cannot be inherited), asserting the payment line
present for lab and absent for prolific, the closing instruction's document
order, and, for every absence, the matching presence plus `exit_code == finished`
so a walk that never reached the ending cannot pass. Rows 3 and 4 of its table
are the ones that matter: prolific with the redirects OFF must still not be
promised a transfer, and lab with them ON must still get its payment line — a
sentence gated on the nearest module flag passes a two-row version and fails
those. The centring is MEASURED in `scripts/tests/render_check.py` leg AH, off
the **line boxes of the real glyphs** (a Range's client rects) rather than off
`text-align`, on both endings at three viewports.

---

## The screen-out exit says it is FINAL, because the code that frees the place forecloses the return — 2026-08-15

Decided by Julian, the same day as the per-population completion codes, and it
is the consequence of that decision rather than a separate one.

**What forced it.** The soft wall was designed around a re-decidable verdict: a
participant turned away at entry is HELD on `before.welcome`, the page's primary
ask is "switch to an accepted device and come back", and returning on an
accepted device before consent CLEARS the screen-out. The reversal recorded
above gave the screen-out its own completion code, chosen because an open
submission is limbo — it occupies a place and tells Prolific nothing. But a
completion code RETURNS the submission, and a returned submission can never be
retaken. **So for anybody who presses the exit, the route the page invites them
to take is gone.** Freeing the place was judged the better trade; being silent
about what it costs the participant was not.

**What the page now says**, in the `show_return_link` branch of
`before/screened_out.html`: *"Once you return it you cannot take part again,
even on an accepted device."* It replaces *"Once you do this you will not be
able to take part later"* — true, but on this page it reads as "not later
today", three inches under an invitation to come back on a different device.
The new sentence names the route it closes.

**What was deliberately NOT done.** It is one sentence in the page's existing
register, not a warning banner, and the control is untouched: it stays
`.exit-button`, never `.next-button`, because `global.js` Enter-clicks the first
`.next-button` on a page and an irreversible exit must not be one keystroke
away. The primary ask is still switching device, and the switch-device branch
still says *"Do not press the button below."*

**The honest statement of what survives.** The soft wall still exists and still
clears on an accepted device before consent — but only for somebody who has NOT
taken the exit. Those are now two different populations and the page has to be
readable by both.
**Enforced:** `scripts/tests/screenout_softwall_test.py` asserts the accepted-device
clause specifically (not merely that some permanence wording exists, which the
old sentence would also have satisfied), that the control carries
`.exit-button`, and that the way out is a real `<a href>` needing no script;
`scripts/tests/render_check.py` asserts the switch-device branch's "Do not press the
button below".

---

## Every ending population gets its own completion code — 2026-08-15

Decided by Julian. Five endings, five codes, one per population:

| key | population | Prolific action |
|---|---|---|
| `prolific_cc_code` | completed | **auto-approve** |
| `prolific_noconsent_code` | declined consent | request return |
| `prolific_dq_quiz_code` | comprehension DQ | request return |
| `prolific_dq_tab_code` | tab-monitor DQ | request return |
| `prolific_device_code` | device screen-out | request return |

**Why not one shared `DQ-` code, which is what this replaces.** A shared code
**collapses two populations irreversibly, on a system we do not own.** Once a
comprehension failure and a tab-monitor ejection have both submitted under one
code, Prolific's submission list cannot tell them apart and nothing downstream
recovers it — not an export, not a rerun, not a support ticket. This is the
collapsed-distinction rule applied to a third party: the usual version of that
rule costs a debugging session, and this version cannot be fixed at all, which
is why it had to be got right before a launch rather than after one.

**THIS REVERSES the codeless screen-out** recorded on 2026-08-12 (marked
SUPERSEDED above, with its reasoning preserved). That decision was right that a
completion code closes a submission and a returned submission cannot be retaken.
It was wrong that leaving the submission open was therefore kind: a bare
researcher URL leaves it in limbo, occupying a place, telling Prolific nothing.
A **REQUEST_RETURN** code is a different instrument — it prompts the participant
to return the submission, which frees the place. So the screened-out exit is now
`prolific_device_code` rendered as a full completion URL, and the
`prolific_screenout_return_url` setting is gone: a URL that embeds a code, plus
a code key, is one value in two places and they drift.

**Rejected:** keeping `prolific_screenout_return_url` alongside the new code as
an override. Two sources for one value is the defect this repo has spent the
week removing.

**THE HAZARD THE SPLIT CREATES, AND THE RULE THAT CLOSES IT** (bossman-52, same
day). Splitting the DQ code invents a failure mode that could not exist while one
code served both populations: **if the displayed reason text and the completion
code are derived independently, they can silently disagree** — a comprehension
failure reads the quiz explanation and carries the TAB code back to Prolific. No
error, normal-looking data, and the population distinction corrupted at exactly
the point it was created to exist, findable only by reconciling submissions by
hand. **So the message and the code must come from ONE read of the cause.**

Verified today, and it is the safe shape already: `outro.dq_cause` is the only
implementation (`outro/__init__.py:51`); `Ended.vars_for_template` passes
`dq_cause=dq_cause(player)` and `outro/Ended.html` branches on that variable;
`completion_link` does `cause = dq_cause(player)`. No template reads
`tab_monitor_disqualified` or `comprehension_disqualified` directly — checked
across every `.html` in the repo. Two calls to one deterministic function in one
request cannot disagree; two implementations could, which is why the invariant is
written on `dq_cause` itself. **The next reader will see two calls and want to
refactor one away — that is the thing not to do.**

**Enforced, and each part separately verified:**

- `settings.PROLIFIC_CODE_KEYS` is the ONE enumeration; `_prelaunch_problems`
  iterates it rather than keeping a copy, so a sixth ending cannot ship
  unguarded. **Mutation-tested key by key**: with the other four set to
  plausible real codes, leaving each one placeholder in turn is named by the
  check — and only that one (no false positives). The old three-key enumeration
  would have shipped the two new codes completely unguarded while reporting
  clean, which is the trap this template keeps meeting.
- The frozen-session audit needs no enumeration: it walks every key in the
  current config, so the new keys are covered the moment they exist.
- `scripts/tests/completion_codes_test.py` — **one browser-driven journey per ending**,
  each asserting it carries ITS OWN code and NOT the other four. 30 checks, all
  passing. The absence half is the point: a disqualified participant who can
  read the COMPLETED code out of page source can self-approve and be paid, so
  every path checks all four others, and the codes are injected per page rather
  than bundled into the template context.
- `scripts/tests/render_check.py` leg AD asserted the screen-out carried NO code; that
  expectation is now reversed to assert it carries the DEVICE code and none of
  the other four.
- Two test-construction faults were found and fixed while writing the above,
  both worth knowing because they would have produced false confidence: a walker
  using the default `python-requests` User-Agent is classified `unknown` and is
  SCREENED OUT by `prolific_allowed_devices=['computer']`, and setting a DQ flag on a
  participant still at the consent page does not put them on their ending. In
  both cases the code assertions passed against the wrong page until the journey
  itself was asserted.

---

## Ended.html carries no screen-out copy — deleted as unreachable, with the unreachability enforced — 2026-08-14

Decided by Julian (before-review N4), choosing deletion over the reviewer's
keep-both recommendation. The `reason == 'screened_out'` block in
`outro/Ended.html` — the four device-cause branches and the screened-out
title — duplicated `before/screened_out.html`'s live copy for a participant
who can never arrive: the soft wall holds a screened-out participant at the
entry page's own index precisely because oTree only moves forward, so walking
them to an outro ending would make the verdict un-liftable. A duplicate that
never renders can only drift from the copy that does.

**The deletion was not made on the unreachability claim alone.** This repo
has been bitten by untested claims (the 2026-08-13 monitor-coverage entry
below: four documents asserting something untrue), so the claim was made
ENFORCED in the same change: `scripts/tests/screenout_softwall_test.py` scenario 9
hammers a screened-out participant with forced submits and a direct
`/outro/Ended/` URL and requires every response to re-serve the held page.
If routing ever changes, the test goes red before a participant reads the
wrong page. Two second-line defences remain for that hypothetical future
gate: Ended's neutral else-fallback ("The study has ended for you") says
nothing false, and the shared footer include still picks the CODELESS exit
for `reason == 'screened_out'`, so their submission would stay open.

**What deliberately stayed:** `outro.was_screened_out` — a DIFFERENT
mechanism that looks related and is not. It is what keeps a screened-out
participant out of `is_completer`, so no future gate can hand them a
completion code; deleting it with the template branch would have been the
over-pull this entry exists to warn against. `Ended.vars_for_template`'s
`common.screenout_vars` spread also stays: the footer reads
`prolific_screenout_return_url` from it.

**Record check, done with the change:** no document claims the screen-out
exit code is written when the participant clicks the return link — it is
written at DECISION time (`common.set_screened_out`: a closed tab still
exports as screened out, not abandoned), and `set_screened_out`'s docstring,
the softwall test header and the footer include all state it correctly.

**Enforced:** `scripts/tests/screenout_softwall_test.py` scenario 9 (the deletion
guard); the header note in `outro/Ended.html` points at it.

---

## Explicit consent is its own flag (`explicit_consent`), split from `prolific_completion_redirects` — 2026-08-14

Decided by Julian, from the before-app review. Whether the consent page asks
an explicit question (required unticked radio, no-consent routed to exit code
-1) or states that continuing is consent was decided by
`prolific_completion_redirects` — which, read literally, said "if we hold a
completion code, consent must be an affirmative act". **Whether consent is
EXPLICIT is an ethics decision; holding a completion code is platform
plumbing.** The conflation is the same defect class as the screened-out
dead end of 2026-08-13 (one flag doing a second, unrelated job), caught this
time before it cost a participant.

The split: `explicit_consent` defaults **ON** in `SESSION_CONFIG_DEFAULTS` —
the one shipped flag that is deliberately not off-by-default, because a study
should have to OPT OUT of asking for consent — and the **lab profile resolves
it OFF** (implicit consent by continuing; there is an experimenter in the
room). That preserves the pre-split behaviour of both shipped profiles
exactly: prolific keeps the radio, the lab keeps implicit consent. The
prolific profile deliberately does NOT list the key (it falls through to the
baseline ON): explicit consent is the default, not a Prolific feature.

The audit for a second conflation found none: every other use of
`prolific_completion_redirects` (the outro return footers, the Ended/Results
"Back to Prolific" branches, the dashboard's awaiting-return pill, the
return-click stamp) is genuinely about the completion-code redirect. One
consequence is newly constructable and deliberate: `explicit_consent` on with
redirects off produces a decliner whose ending has no return button —
`outro/Ended.html`'s neutral fallback covers them.

A frozen session predating the flag reads it as OFF (`common.flag`'s
missing-module rule) — the radio would silently vanish for that session's
future entrants, which is why the predeploy frozen-config audit reporting the
missing key matters: the remedy is to recreate the session.

**Rejected:** deciding at runtime from `recruitment` (the consent page asking
"am I a lab study?") — profiles resolve to explicit config values at import
precisely so behaviour is never re-derived silently; and keeping the old
wiring with a comment — the rename made the misreading legible, a comment
would only apologise for it.

**Enforced:** `scripts/tests/explicit_consent_test.py` (radio present+required when
on, absent with implicit copy when off, in BOTH recruitment profiles — flag
decides mechanics, recruitment decides copy — plus the resolved values on
both shipped configs); `explicit_consent` in `scripts/tests/frozen_config_test.py`'s
STRIPPED list pins the frozen-session behaviour.

---

## The end-of-page cookie reset is gone — 2026-08-13

`clearAllCookies` (run on load by the payoff, Ended and Results pages) was
removed with its three call sites and its helper — Julian: no longer needed.
It cleared every path=/ cookie each round and at the endings, including an
admin's own session cookie when previewing; oTree identifies participants by
URL code, not cookies, so nothing participant-facing depended on it. The other
dead cookie helpers an earlier review flagged (getCookie, setCookie,
printCookies, cl) were already gone. Do not re-add a cookie sweep without a
stated reason — the last one ran for years with nobody able to say what it was
for, which is why the review flagged it.
**Enforced:** nothing but grep — there is no cookie code left to guard.

---

## The return click is best-effort instrumentation, and the pill is gated on the button existing — 2026-08-13

"Finished here but never clicked Back to Prolific" is flagged ONLY when
`prolific_completion_redirects` is on — with no redirect there is nothing to
click, and the flag would fire on every lab participant forever (Julian's
critical condition; the gate comment in `_participant_row` is load-bearing).
The click stamp (`prolific_return_clicked`) rides the Results page's live
socket just before navigation, so it can be lost — absence means "no click
RECORDED", and the pill is a prompt to look, never a verdict. A grace period
(`DASHBOARD_RETURN_GRACE_SECONDS`) stops it firing on completers still reading
their receipt.
**Rejected:** routing the exit link through a stamping redirect — exact and
JS-free, but it puts instrumentation INSIDE the one path every completer
needs, and instrumentation must never be able to break a page (CLAUDE.md); the
link stays a plain href that works with the whole mechanism dead.
**Enforced:** `outro.results_live_method` (gated the same way);
`scripts/tests/dashboard_test.py` §D8 pins the gate from both sides; docs/CODEBOOK.md
documents the stamp's best-effort nature.

---

## Missing completion codes degrade to `REPLACE_CC`, never to `None` — 2026-08-13

`outro.completion_link` reads codes through the safe accessor, so a session
frozen before a code existed builds the shipped `REPLACE_CC` placeholder into
the URL. Chosen *because* it produces the same symptom as the already-known
failure "nobody replaced the placeholder": anyone seeing `REPLACE_CC` knows
instantly what it means and what to do, while `?cc=None` looks like a bug of
ours and tells the operator nothing.
**Enforced:** `outro.completion_link` (reasoning in its docstring); pinned by
`scripts/tests/frozen_config_test.py`.

---

## Completion fires when the results page loads — identically in both variants — 2026-08-12

`exit_code` becomes `finished` in `Results.vars_for_template`, not on the
"Back to Prolific" click. This reversed an earlier request, and the principle
behind the reversal outranks the detail: **lab and Prolific diverge only where
genuinely essential**, because every divergence can be true in one variant and
quietly wrong in the other, forever. A participant who closes the tab without
clicking has still finished; the click is Prolific's concern, not the data's.
**Enforced:** `outro/__init__.py` (`Results.vars_for_template`, idempotent);
`scripts/tests/full_journey_test.py` asserts exit code 1 at Results. The
minimal-divergence principle itself has no guard — the caller-list warning on
`common.is_lab` and review are what hold it.

---

## ~~A screened-out Prolific participant gets a codeless link back~~ — 2026-08-12, SUPERSEDED 2026-08-15

The way off the screen-out page is a plain link with **no completion code**,
because submitting a code closes the Prolific submission, and a returned
submission can never be retaken — which forecloses exactly what the page asks
("come back on a computer"). The old `error_code`/`REPLACE_ERR` pair was
removed for this reason and must not come back. Corollary (2026-08-13): being a
Prolific study and offering a screened-out exit are the same commitment, so the
dependency is enforced, not documented.
**Enforced:** the no-screened-out-code note in `settings.py`;
`settings._prelaunch_problems` refuses a `recruitment='prolific'` config with a
blank or unreplaced `prolific_screenout_return_url`;
`scripts/tests/copy_routing_test.py` walks the codeless way out end to end.

> **SUPERSEDED 2026-08-15 by "Every ending population gets its own completion
> code" (below/newest).** The reasoning above is kept, not deleted, because a
> reader who meets the codeless design in an older study — or who reasons their
> way back to it — should be able to see that it was reconsidered and why,
> rather than find it silently gone.
>
> **What it got right:** submitting a completion code does close a Prolific
> submission, and a returned submission cannot be retaken. That is still true.
>
> **What it got wrong:** it treated "leave the submission open" as the kind
> outcome. In practice a bare researcher URL leaves the submission sitting in
> LIMBO — the participant has been turned away, cannot continue, and nothing
> tells Prolific anything; the place stays occupied until it times out. A
> Prolific REQUEST_RETURN code is not the same instrument as a completion code:
> it actively PROMPTS the participant to return the submission, which is the
> outcome that frees the place and ends the ambiguity. The screened-out exit is
> now `prolific_device_code` used as a full completion URL, and
> `prolific_screenout_return_url` is gone as a setting.

---

## The screen-out return URL ships as a placeholder, not a working default — 2026-08-12

It used to ship as `https://app.prolific.com/`, which works — and that is the
problem: **a plausible default never gets checked**, and the person who
discovers it was wrong for this study is a participant already turned away.
**Enforced:** the `REPLACE_*` family is flagged by the prelaunch banner and by
the pre-deploy frozen-config audit's PLACEHOLDER severity.

---

## Exit codes: initialised at creation, `0` means "never reached an ending" — 2026-08-07 (ported from the pilot)

Every participant carries `exit_code` from session creation, so no export row
is ever blank; `0` is *abandoned* — created but never reached any ending — and
is distinct from every deliberate outcome, each of which has its own code
(screened-out is `-4`, not `0`: you must be able to tell the gate's work from a
closed tab). A code nothing records is a lie in the export, so
reserved-but-unwired codes are deleted, not documented (`timed_out`, removed
2026-08-10).
**Enforced:** `common.init_participant`; the codes table in `docs/CODEBOOK.md`;
tests assert on numeric codes rather than ending copy
(`full_journey_test`, `device_gate_test`).
