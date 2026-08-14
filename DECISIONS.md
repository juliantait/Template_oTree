# Decisions

The procedural and design decisions behind this template, in one place. Each
entry: the decision, the date it was settled, why (the concrete failure or
argument that drove it), what was rejected where an alternative was genuinely
considered, and — the field that matters most — **where it is enforced**: the
test, guard or CSS rule that holds it in place, or a plain admission that
nothing does and it relies on people remembering. Newest first. Entries are
deliberately short; the linked `_ai/` documents and code comments hold the full
working.

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
ENFORCED in the same change: `tests/screenout_softwall_test.py` scenario 9
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

**Enforced:** `tests/screenout_softwall_test.py` scenario 9 (the deletion
guard); the header note in `outro/Ended.html` points at it.

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

**Enforced:** `tests/explicit_consent_test.py` (radio present+required when
on, absent with implicit copy when off, in BOTH recruitment profiles — flag
decides mechanics, recruitment decides copy — plus the resolved values on
both shipped configs); `explicit_consent` in `tests/frozen_config_test.py`'s
STRIPPED list pins the frozen-session behaviour.

## One short-viewport rhythm for every `.stacked-form` option row — a leak ratified into the rule — 2026-08-14

The consent-fold block (`@media (max-height: 820px)` in base.css, 2026-08-13)
tightened option rows via `.stacked-form .mc-option / .form-check` while its
comment claimed consent-only scope — but the quiz and demographics stack their
options in `.stacked-form` directly (the "different wrapper" the comment cited
never existed), so both pages were retuned from day one. **Discovered through
a geometry-baseline diff, not by design** — the fold work never ran
`--update-baseline`, so the first `--diff` afterwards surfaced ~130 moved
measurements (quiz card −125px, demographics −59px at short viewports), which
were first mis-attributed to environment drift and then pinned by a CSSOM
toggle: deleting the one media rule sprang the rows back to the baseline's
values on both pages, while a rule audit proved the concurrently-added
tabmonitor.css matches nothing there. The log records the route because that
is how it actually happened.
**Julian's ruling: make the rule the intent.** One component, one rule,
everywhere — a component that tightens on short viewports on one page but not
another is the same mixing-and-matching the logo-strip principle forbids. The
shipped behaviour stands, the adopted baseline stands, and the earlier
"one page's shortfall must not silently retune every choice" scoping intent
is ABANDONED, on purpose, with the reversal recorded at the block itself.
Judged on screenshots before ratifying, not on the principle alone: rows stay
over the 44px touch floor, nothing cramped, quiz and demographics
neutral-to-better on short screens.
**Rejected:** re-scoping the rule to the consent group (a dedicated class) —
it would honour the written intent by making the same control obey two
rhythms, which is the defect class, not the fix.
**Enforced:** the rewritten comment at the block (base.css) states the
everywhere-rule and forbids re-scoping without a new decision;
`tests/geometry_baseline.json` pins the shared rhythm at all three viewports;
the affordance and touch-target legs of `tests/render_check.py` assert the
pages still behave.

## The tab monitor is monitored-by-default after the agreement page — and the claim preceded the behaviour — 2026-08-13

Whole-app review B1, decided by Julian. **First, the record correction this
entry exists to hold: from 2026-08-12 to 2026-08-13 four places (this file's
armed-before-the-quiz entry, README's Prolific flow diagram, the
`AISafetyAgree` docstring, `intro/__init__.py`'s closing comment) stated that
the instructions and the quiz were monitored, and they were not.** The
agreement page had moved but no monitor wiring existed in `intro` — no
live_method, no js_vars, no script — so the very check the move was made to
protect stayed unwatched, with nothing anywhere to say so (the enforcement
test pinned page ORDER, not coverage). The gap was found by asking where one
concept — "a monitored page" — had two implementations, and it is recorded
here because a claim that quietly becomes true later is exactly the kind of
thing a future auditor must be able to date.

**What closed it — an INVERSION, not page-by-page opt-in** (Julian's rule):
everything after `before.AISafetyAgree` is monitored BY DEFAULT
(`monitoring.MonitoredPage`, generalising TaskPage's J2 reasoning), and a
page can only be unmonitored by asking (`monitored = False`, one switch that
disarms all the wiring together — never `js_vars = None`, which 500s at
render because oTree calls js_vars unconditionally). The four pieces travel
as one: live_method and js_vars from the base class; script and stylesheet
through `css_bundle.html` (self-gating on `session.config.tab_monitor` and on
the page's own js_vars), so there is no per-template include left to forget —
a per-template include is how the gap happened. The client lost its
threshold-defaults fallback (a second copy of SESSION_CONFIG_DEFAULTS kept in
sync by a comment) and its `/outro/` path check (a second spelling of "which
pages are monitored"): the server's js_vars are now the one authority.
`intro.intro_page_visible` gates on the new `common.removed_from_study` belt
(one membership list for every removal mechanism, used by main too), so a
mid-quiz disqualification's reload lands on the ending.

**THE PHASE ASYMMETRY — same monitor, same counting, different consequence
(Julian): intro + main EJECT at the threshold; the outro RECORDS ONLY and
never ejects.** By the outro the task is over and the data already collected,
so disqualifying somebody who has completed the whole study — for tabbing
away while typing bank details, or to fetch their Prolific tab — would cost a
real participant for no benefit. Outro violations land in their OWN column
(`focus_loss_count_outro`), so a completed-with-violations participant is
distinguishable from a nearly-ejected one (`focus_loss_count` keeps meaning
"how close to disqualification"); the dedup set is shared so no event counts
twice. The client is told its phase (`ejects: false`) and shows no overlay
and no warning modal in the outro — the modal's threat would be a lie there.
The asymmetry is stated, with its why, at every site that could read as
inconsistent: `common._apply_focus_loss`, `monitoring.py`, the top of
`outro/__init__.py`, settings' integrity block, README (section + diagram),
CODEBOOK ("Tab-monitor violation counts"), conventions.md.
**Rejected:** page-by-page opt-in (the model that produced the gap — a
checklist cannot make forgetting impossible); ejecting in the outro
(cost-without-benefit above, plus a mechanical trap: `Ended` sits FIRST in
outro's sequence, so a mid-outro ejection has no ending page ahead of it to
land on); and a client-side warning without counting or counting with the
old threatening modal in the outro (each a new collapsed distinction).
**Enforced:** `monitoring.assert_monitored_page_sequence` runs at IMPORT at
the bottom of `intro`, `main` and `outro` and refuses to BOOT over a page
that is neither monitored nor explicitly opted out — you can only get an
unmonitored page by asking for one. `tests/task_page_test.py` (reworked)
pins the bindings by identity, the quiz page's served monitor config
end-to-end, the record-only outro (violations past the threshold disqualify
nobody and stay in their own column), the Results dispatcher (one live
channel, both message types), and the checker refusing a dodger.

## One guard policy for a config-read money value: fail loudly — 2026-08-13

Whole-app review B4, decided by Julian. `showup` / `quiz_bonus` were read two
ways: the promise side (consent, instructions) guarded with `or 0`, the
payment side (`outro.compute_final_payoff`) bare. For a config holding None
that split is the worst arrangement — the participant is silently promised
€0.00 and the crash still happens, at the payment page. The `or 0` guards are
gone; every side now reads bare and fails loudly at the first page that
renders the value. **This has a behavioural implication, stated plainly
because the decision was taken assuming it did not: a degenerate config that
used to render a silent €0.00 promise now errors instead.** Loud is chosen
because silently promising somebody nothing is the worse outcome — the same
reasoning `compute_final_payoff` already carried ("failing loudly beats
recording the wrong number quietly"). No shipped or frozen config is
affected: `common.cfg` falls back to the shipped numeric default for a
MISSING key; only an explicit None ever hit either path.
**Enforced:** nothing structural — the policy is one line of comment at each
former guard site (`before.welcome.vars_for_template`,
`intro.instructions_context`), and the loudness is the absence of the guard.

## The two-accessor question is CLOSED across the flow — 2026-08-13

Chased across three separate reviews (before N3 → whole-app B2 → this
implementation), and recorded here so nobody re-opens it: **every reader of
the study type now goes through `common.is_lab` / `common.is_prolific` /
`common.recruitment`.** The last holdout was `before.startpage.is_displayed`'s
raw `config.get('recruitment') == 'lab'`, which on a session frozen before
the key existed evaluated `None == 'lab'` → False — silently dropping the lab
hold screen while the consent page one index later rendered lab copy through
`is_lab`'s fallback: one participant, one question, two answers, one page
apart. Behaviour change is confined to that frozen-config case (the hold
screen now appears, which is what the neighbouring pages already assumed);
blast radius today is zero — no live sessions, the same window the
`prolific_` rename used.
**Enforced:** `grep "config.get('recruitment')"` returns nothing outside
`common.py`; `tests/copy_routing_test.py` pins the single-implementation rule
the accessor carries.

## Task pages inherit their wiring from `TaskPage` — the template's one use of page inheritance — 2026-08-13

> **SUPERSEDED IN PART, same day — see the monitored-by-default entry above.**
> The J2 reasoning held and GENERALISED: the monitor wiring moved up into
> `monitoring.MonitoredPage`, which every page after the agreement screen now
> subclasses, so page inheritance is no longer "used nowhere else" — it is the
> rule for three of the four apps, for exactly the reason this entry gives.
> TaskPage survives as the task-specific layer (round gating + progress vars)
> on top of that base. The monitor contract itself is still untouched.

Review item J2, approved with Julian's reasoning (recorded at the class, which
is where the next reader meets the indirection): a task page that is SILENTLY
NOT ARMED for the tab monitor is worse than the cost of a base class —
forgetting the wiring produces no error, only monitoring that never fires,
discovered from the data. `main.TaskPage` carries `is_displayed` /
`live_method` / `js_vars` / the base template vars; `GameStart` and `payoff`
subclass it; the two repeated template blocks became includes
(`task_progress_strip.html`, `tabmonitor_assets.html`). THE MONITOR CONTRACT
IS UNTOUCHED — same bindings, names and thresholds; only who types them
changed. Two gotchas live in the docstring: oTree resolves page attributes at
IMPORT, so unbinding needs an explicit override, never an omission; and
subclass, never copy, or the drift returns. Page inheritance is used nowhere
else in the template, deliberately.
**Rejected:** staying explicit-per-page with a checklist — the checklist
cannot make forgetting impossible, and the failure it guards is silent.
**Enforced:** `tests/task_page_test.py` — structurally (an empty-bodied
subclass is fully armed; identity of the bindings, not lookalikes) and
end-to-end (the served page carries the monitor config; the inherited
live_method counts a violation), plus the unbind-by-override gotcha proven in
both directions.

## The dashboard's admin "Report" tab rides oTree's supported extension point, as a layer over the standalone URL — 2026-08-13

Julian promoted the TODO investigation to a build. The investigation's answer:
oTree 6.0.15 has a first-class extension point — at session creation,
`Session._set_admin_report_app_names` (otree/models/session.py:250) scans each
app for `<app>/admin_report.html`; oTree's OWN session tab bar
(otree/templates/otree/Session.html:84) renders a "Report" tab when found; the
`AdminReport` view (otree/views/admin.py:482) renders our template with
optional `vars_for_admin_report`. So the tab (`outro/admin_report.html`,
embedding the dashboard in an iframe with an open-standalone link) depends on
a documented feature, not on oTree's page structure. **The standalone URL is
the primary surface and works unchanged with the tab deleted or broken** —
built that way round deliberately. `vars_for_admin_report` is internally
defensive (oTree calls it unguarded) and catches ONLY the import, with a
literal fallback URL as the belt.
`experimenter_dashboard.note_admin_tab_problems` applies the identity.py
discipline to the one silent failure mode: quiet when oTree is legitimately
absent, LOUD (logged, never raised) when the admin-report symbols or the
template lookup have drifted — because drift here means the tab quietly stops
appearing. Known limitation: sessions created before the template shipped
carry no tab (the scan is frozen into the session row).
**Rejected:** injecting into oTree's admin page structure (templating over /
DOM patching) — far more upgrade-exposed than our routing-level install, and
unnecessary given the supported point.
**Enforced:** `tests/dashboard_test.py` §D9 — the tab appears in oTree's own
tab bar, the standalone URL works with it present, a broken dashboard leaves
the admin pages serving, a broken import leaves the tab serving via the
fallback, and the drift check reports ok against the installed oTree.

## One payment ledger: per-round `player.payoff` is not used, `participant.payoff` is written once from `earned` — 2026-08-13

Review item J1 (Julian; sub-decision also his). The underlying conflation:
oTree automatically sums `player.payoff` across rounds into
`participant.payoff`, but this template pays only `num_rewarded` randomly
selected rounds — the per-round result and the amount paid are different
things, and the auto-sum is a total nobody is paid. So the game records each
round in its own `main.Player.round_payoff`; the template pays from
`participant.payoff_vector`; and oTree's `participant.payoff` gets exactly ONE
entry — `earned` (less `participation_fee`, de-converted when `USE_POINTS` is
on), written when the results page computes payment — so the admin Payments
page shows the figure the participant was shown, and there is nothing left to
disagree. `AUTO_TABULATE_PAYOFFS=False` also removes oTree's per-round payoff
column from the export (deliberately absent, not accidentally empty — no data
lost, every round is in `round_payoff` and `payoff_vector`; CODEBOOK "The
payment record").
Facts established before shipping: nothing in oTree 6.0.15 recomputes
`participant.payoff` after that write (the `player.payoff` setter's delta is
the only other writer), and nothing in the template or its tests read the
per-round column except the placeholder itself.
**Rejected:** zeroing `participant.payoff` so the admin page is obviously
wrong (option 1 — Julian chose agreement over conspicuous wrongness); and
keeping the per-round writes while overwriting the total at the end, which
leaves a round column summing to a number nobody was paid.

### AMENDED 2026-08-14 — the raise was never the enforcement, and it lands on a participant

**Caught by the exp_pilots bossman**, verified against the installed oTree
before acting: this entry, `settings.py`, `main/__init__.py`,
`outro/__init__.py`, `CODEBOOK.md` and `skills_claude/writing_task.md` all
said `AUTO_TABULATE_PAYOFFS=False` "makes the old habit RAISE rather than
drift back silently" — presenting a **participant-facing crash as a safety
feature**. The setter is oTree's own (`otree/models/player.py:41-46`), it
cannot be removed, and it fires **at participant request time, on a page,
mid-round**. oTree has no migrations, so the realistic failure is an upgrade
under live sessions: a new build introduces a `player.payoff` write and the
first person mid-round to reach it gets a DEAD PAGE. The flag alone therefore
converts a CONDITIONAL data problem (one ledger drifting into two) into a
CERTAIN outage for whoever is part-way through — the same trade this repo has
already refused twice, in `install_duplicate_label_guard` (the early install
must fail quietly) and in `assert_duplicate_label_guard` (deliberately not on
the entry path). It was missed here for the reason it is always missed: **a
raise feels like the strict, careful option.**

The raise stays — it is oTree's, and it is the floor. What changed is that the
failure is now caught **earlier, at boot**, where loud is what loud should
mean for a server: `payoff_guard.assert_no_player_payoff_writes()`, called
from `before/__init__.py` beside the identity assert, refuses to START a build
whose app modules write `player.payoff`. The operator sees it at deploy time
while the old build is still serving; the participant never sees it.

**TWO CHECKS, DELIBERATELY, because their blind spots are disjoint** — the
judgement call the review left open. The boot scan parses app SOURCE with
`ast`, so it covers every syntactic write whether or not any test walks that
line, and it cannot be fooled by the six files that discuss `player.payoff` in
prose (a regex would refuse to boot over this very paragraph); it is blind to
indirection. The runtime test walks a real journey and asserts the underlying
`_payoff` column is still 0 on every round row, which catches indirection; it
is blind to code no walk reaches. Neither alone is sufficient, so both ship.
`participant.payoff` and `player.payoff` are two fields sharing a name, and
the scan tests the base expression explicitly rather than the attribute — the
collapsed-distinction rule, since a name-only check would refuse to boot over
`outro.compute_final_payoff`, the one write the decision exists to protect.
**Rejected:** a launch-gate-only check (`scripts/prelaunch_check.py`), which a
deploy can skip — the whole point is that the server will not come up; and
`import`-and-introspect instead of parsing, which would execute
`intro/generate_instructions_preview.py` and its browser driver at boot.
**Enforced:** `payoff_guard.py`; `tests/payoff_ledger_test.py` §7 (a walked
journey leaves every round row's `_payoff` at 0) and §8 (the guard catches six
write forms including `setattr` with a literal name, refuses a synthetic build
naming file and line, does NOT fire on the participant write or on prose,
declares its `setattr`-with-computed-name blind spot, and reports an
unparseable module as "cannot answer" rather than as a payoff write).

**Enforced:** `tests/payoff_ledger_test.py` (the two figures agree on the
admin page itself; the value survives re-renders; oTree's setter does raise;
the export column is absent while `round_payoff` is present) — plus the boot
guard above.

## A payment total is not a payment instruction: every component paid outside oTree must still be represented inside it — 2026-08-14

**Caught by the exp_pilots bossman**, and it is the natural blind spot of the
one-payment-ledger decision above: that decision made the total CORRECT and
made both ledgers AGREE on it, and stopped there. Our admin Payments figure is
one undifferentiated number — full `earned` into `participant.payoff`,
`participation_fee` shipped 0.00 — so it covers base plus bonus at once. **On
Prolific those components are paid through DIFFERENT MECHANISMS**: the base as
the study reward, the bonus through the bonus payment flow. A single total,
however correct, is therefore NOT ACTIONABLE — whoever pays needs the **bonus
figure on its own**, and that is the number that must survive intact.

THE RULE, in the reviewer's words:

> **ANY PAYMENT COMPONENT PAID OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE
> OTREE, OR THE ADMIN PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A
> TOTAL.**

**Corollary:** on Prolific the components are paid by different mechanisms, so
the total alone is not enough — the bonus must be separately visible.

THE TWO SHAPES, WHICH LOOK LIKE OPPOSITES AND ARE THE SAME DEFECT. Ours is
**complete but not itemised**: everything is inside oTree, the total is right,
and the payer cannot read the bonus off it. The reviewer's own study was
**itemised but incomplete**: components kept apart, but the base never entered
oTree at all, so its "total" was a partial figure wearing a total's name.
Neither has the property that matters, which is **itemisation of a complete
set** — and framing them as opposites is what let both ship.

WHY THE EXISTING TEST DID NOT CATCH IT — the part worth remembering. §1 pins
that the total is correct and that the two ledgers agree on it. **A study can
get the total right while making the actionable number unreadable**, and a
test written against the total cannot see that. This is the collapsed-
distinction rule in the measurement rather than in the code: "the payment is
correct" and "the payment is payable" were one assertion.

**DONE NOW (safe, and independent of the open config decision):**
`tests/payoff_ledger_test.py` §9 walks a *prolific* session and asserts the
BONUS IN ISOLATION as well as the total — each component recorded on its own,
the three reconstructing `earned` with zero residue, the bonus
(`selected_sum + quiz_bonus_awarded`) derived from the stored components
rather than as `total − base` (which would be right by construction and prove
nothing), both halves separately readable, and the components present as their
own export columns. It also records the admin-page state as a **measured gap**.

**THE CONCRETE FIGURES THIS DECISION IS BEING MADE AGAINST**, so nobody reading
it later has to reconstruct what the admin page actually showed. One real
walked Prolific completer (participant `240pbcpa`, config `prolific`, 10 rounds,
`num_rewarded=2`, exit code 1), measured 2026-08-14, all figures EUR:

| Figure | Source | Value |
| --- | --- | --- |
| base / show-up | `showup` (session config) | **2.50** |
| selected rounds | `outro.Player.selected_sum` (r10 → 45.00, r6 → 98.00) | **143.00** |
| quiz bonus | `outro.Player.quiz_bonus_awarded` | **5.00** |
| **total earned** | `outro.Player.earned` — the three above, residue exactly 0 | **150.50** |
| `participant.payoff` | written once by `compute_final_payoff` | **150.50** |
| `participation_fee` | session config, as shipped | **0.00** |
| **admin Payments figure** | `payoff_plus_participation_fee()` | **150.50** |

The selected-rounds component is randomly drawn, so it and every total below it
vary per run (other runs measured 125.00 and 140.00); **base, quiz bonus and
`participation_fee` are fixed, and the SHAPE is invariant** — the admin figure
always equals `earned`, because `participation_fee` is 0.00 and the whole of
`earned` goes into `participant.payoff`.

**WHAT THE PAYER NEEDS IS TWO NUMBERS, AND THE ADMIN PAGE SHOWS NEITHER** — it
shows their sum. Study reward, set on the Prolific study: **2.50** (the base
alone). Bonus payment, entered in the bonus flow: **148.00** (selected rounds +
quiz bonus). Pasting the admin's 150.50 into the bonus flow pays 148.00 of
correct bonus plus 2.50 that Prolific has ALREADY paid as the study reward: the
participant is overpaid by exactly the base, and the error is invisible because
the total was right all along.

**THE MEASURED EVIDENCE**, fetched from oTree's own `/SessionPayments` for that
session: **€150.50 PRESENT. €148.00 (the bonus) ABSENT. €2.50 (the base)
ABSENT.** That is the itemisation argument in one line — the page carries the
total and neither component.

(Matched CURRENCY-PREFIXED, never as a bare number: `150.50` contains `2.50`, so
a substring search reported the base as present on a page that never mentions
it. See the comment at that check — a bare search makes both negative
assertions unable to fail, which is the same defect class as the total-only test
this whole entry is about.)

**DELIBERATELY NOT DONE YET:** changing `participation_fee` or how
`participant.payoff` is composed — that is an open decision with Julian, and it
changes what the exported columns MEAN, which is not something to do as a side
effect of adding a test.
**Rejected:** asserting only that the components exist, without asserting they
sum to `earned` — a component nobody can reconcile is a number, not an
itemisation; and deriving the bonus as `total − base` in the test, which passes
whatever the data says.
**Enforced:** `tests/payoff_ledger_test.py` §9; the rule is stated in
README "Paying participants — the itemisation rule" and in CODEBOOK "THE
ITEMISATION RULE".

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

## The dashboard's state column is a collection of pills, and conditions survive outcomes — 2026-08-13

Two kinds accumulate in one cell (Julian): OUTCOME pills (a terminal state, or
the finished tick) and CONDITION pills (Non-SEPA, the timing warning, the
tab-monitor count while it climbs, the missing return click). A finished row
KEEPS its condition pills — finishing does not make a condition go away.

**ROW TINT IS OUTCOME, PILLS ARE CONDITIONS** (Julian, same day, second pass).
The row tint is one consistent outcome signal: green finished, red ended
early, amber stalled, untinted still going — mutually exclusive by
construction, so no precedence. A condition NEVER touches the row: the
finished non-SEPA participant keeps the green row AND the red pill; turning
that row red would collapse the two channels back into one. The green is
deliberately lighter than the green pills' own background so the row does not
go monotone. The amber tint's second job stands: across-the-room salience,
with the pill carrying the facts.
**Rejected:** one state per row (the original design); and, briefly, no
finished tint at all (superseded — the tint was re-added as the outcome
CHANNEL once the channel rule made "green row + red pill" coherent rather
than contradictory).
**Enforced:** `tests/dashboard_test.py` §D7/§D8;
`tests/dashboard_render_check.py` `check_pills` measures one row carrying the
finished tick and the Non-SEPA pill together, that the finished tint is
distinct from the amber and from the pills' own background, and that the red
pill stays white-on-red against the green row.

## The Non-SEPA pill: lab only, `sepa == 0` only, and no yellow state — 2026-08-13

Three deliberate narrowings, all Julian's: NULL `sepa` (the check never ran —
every Prolific row) is NO pill, never a flag; a non-Dutch but in-SEPA account
is NO pill (only non-SEPA is flagged — there is no yellow payment state); and
even a hand-edited `sepa=0` in a Prolific session shows nothing, because
payment there goes through the platform and the pill would send the operator
chasing a form that does not exist.
**Enforced:** `experimenter_dashboard._non_sepa_ids` (the one predicate);
`tests/dashboard_test.py` §D7 pins all three narrowings.

## The BIC requirement and the Non-SEPA flag are two predicates, not one — 2026-08-13

The lab bank form demands a BIC for ANY non-Dutch IBAN (in-SEPA or not;
non-empty is the whole requirement — no format validation, because a rejected
valid-but-unusual BIC strands a participant on the page that pays them). The
dashboard pill fires on non-SEPA ONLY. A German IBAN therefore needs a BIC and
gets no pill. Both read the country through `outro.iban_country_code` — one
implementation of "which country", two questions on top of it (the inverted
collapsed-distinction rule, applied in the direction that keeps the questions
apart and the mechanism shared).
**Rejected:** one combined predicate — it would either flag every German
account or let a US account through without a BIC.
**Enforced:** `tests/bank_details_test.py` pins both halves of the asymmetry,
next to each other.

## The timing warning shows the number the threshold judged — per phase — 2026-08-13

The stall verdict and the pill display are ONE value (`_stall_elapsed`), and it
is measured per phase to match what each threshold MEANS in settings.py: entry
on the current page (a block-level 60s would flag every careful consent
reader), intro on the whole app since `left_before_app` (per-page under-fired:
7 minutes on each half never tripped 480s), task per round (the threshold's own
definition), questionnaire since `task_done`. Falls back to page time where a
stamp is missing (mid-flow deploys).
**Rejected:** page-time detection with a phase-labelled display — the pill
would name a phase the verdict never measured.
**Enforced:** `tests/dashboard_test.py` §D3 (page-ageing alone must NOT trip
the intro phase; stamp-ageing must); the render check asserts the pill text.

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
`tests/dashboard_test.py` §D8 pins the gate from both sides; CODEBOOK.md
documents the stamp's best-effort nature.

## The shipped quiz items are machinery placeholders, not model items — 2026-08-13

Deliberately trivial ("What is ice when it melts?"), because they exist to
exercise the quiz machinery — wrong answers, retries, the attempt log, the
thresholds — and are replaced wholesale by every real study.
**Rejected:** shipping an exemplary Stag Hunt comprehension item. It would read
as content to keep, and the previous item ("If you fail the quiz twice…") also
hard-coded the failure threshold into participant copy and described behaviour
the shipped config doesn't produce.
**Enforced:** the comment atop `intro/quiz_items.py`;
`tests/example_quiz_content_test.py` §3 pins the placeholders and is designed
to fail when a study writes its own items, forcing the test to be rewritten
with them (see `skills_claude/writing_quiz.md` for what real items look like).

## The quiz-bonus rule is stated in two places, deliberately — 2026-08-13

Once in the payment overview (`intro/instructions_text.html`), once as the
reminder directly before the quiz (`intro/prequiz_text.html`), both now naming
*which* quiz ("every quiz question on the instructions").
**Rejected:** stating it once — the pre-quiz reminder is worth the duplication.
**Enforced:** nothing. Two cross-referencing comments ("if the rule changes,
edit BOTH") rely on the next editor reading them.

## Missing completion codes degrade to `REPLACE_CC`, never to `None` — 2026-08-13

`outro.completion_link` reads codes through the safe accessor, so a session
frozen before a code existed builds the shipped `REPLACE_CC` placeholder into
the URL. Chosen *because* it produces the same symptom as the already-known
failure "nobody replaced the placeholder": anyone seeing `REPLACE_CC` knows
instantly what it means and what to do, while `?cc=None` looks like a bug of
ours and tells the operator nothing.
**Enforced:** `outro.completion_link` (reasoning in its docstring); pinned by
`tests/frozen_config_test.py`.

## The config-drift check has two severities, so it stays trustworthy — 2026-08-13

The pre-deploy audit of frozen session configs FAILS on exactly two things —
a key missing from a frozen config, and a surviving `REPLACE_*` placeholder —
and merely *reports* every other difference.
**Rejected:** failing on any difference. A session legitimately runs older
thresholds and `static_version` changes on nearly every deploy, so an
all-differences failure fires every time, gets ignored within a fortnight, and
then catches nothing — including the real cases.
**Enforced:** `scripts/predeploy_check.py` (`audit_frozen_session_configs`);
its docstring carries the warning not to promote diffs to failures.

## The logo footer is a rule, not a per-page arrangement — and yields first — 2026-08-13

The logo strip sits at the bottom of the white card, below its divider,
identically on every page that shows it — enforced structurally (`order: 999`,
`margin-top: auto`) so a template that includes it in the wrong place still
renders it right. Because it is decoration, it is the first thing to shrink
when vertical space runs short (mark height drops at the short-viewport
breakpoint).
**Rejected:** each template getting the markup order right — a new page copies
whichever page its author happened to open.
**Enforced:** the LOGO FOOTER RULE block in `_static/global/css/base.css`;
logo geometry is in `tests/geometry_baseline.json`.

## Styling is shared components, never page-local patches — 2026-08-13

A page template composes named classes from `_static/global/css/`; no inline
`style=`, no one-off rule to fix a single page, and every new component gets an
INTENTION comment plus a specimen in `_static/global/html/template.html`.
Driven by three real bugs of the same shape: a class referenced by three
templates and defined nowhere, one concept carrying two widths, and an inline
`height` beating the component's own rule. Genuine one-screen exceptions are
marked `EXCEPTION` with the reason.
**Enforced:** the Styling section of `CLAUDE.md`; layout drift is caught by
`tests/render_check.py` against the geometry baseline. The no-inline-style rule
itself relies on review. Full working: `_ai/css_divergence_report.md`.

## "Flags decide mechanics, `recruitment` decides copy" — 2026-08-13

Every sentence a participant reads that names the platform, the room, or how to
reach a human branches on `recruitment`; module flags answer only "does the
machinery exist". Driven by a found dead end: the consent page inferred
"Prolific" from one flag, the screen-out page from another, and a
friend-test config told a participant to seek help through Prolific and then
gave them no way out at all — no error, no failing test.
**Rejected:** letting whichever flag is nearest stand in for the study type.
**Enforced:** `common.is_lab` / `common.is_prolific` are the only two
implementations; `tests/copy_routing_test.py` asserts the impossibility;
`settings._prelaunch_problems` refuses the config combination that created the
dead end.

## Completion fires when the results page loads — identically in both variants — 2026-08-12

`exit_code` becomes `finished` in `Results.vars_for_template`, not on the
"Back to Prolific" click. This reversed an earlier request, and the principle
behind the reversal outranks the detail: **lab and Prolific diverge only where
genuinely essential**, because every divergence can be true in one variant and
quietly wrong in the other, forever. A participant who closes the tab without
clicking has still finished; the click is Prolific's concern, not the data's.
**Enforced:** `outro/__init__.py` (`Results.vars_for_template`, idempotent);
`tests/full_journey_test.py` asserts exit code 1 at Results. The
minimal-divergence principle itself has no guard — the caller-list warning on
`common.is_lab` and review are what hold it.

## A screened-out Prolific participant gets a codeless link back — 2026-08-12

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
`tests/copy_routing_test.py` walks the codeless way out end to end.

## The screen-out return URL ships as a placeholder, not a working default — 2026-08-12

It used to ship as `https://app.prolific.com/`, which works — and that is the
problem: **a plausible default never gets checked**, and the person who
discovers it was wrong for this study is a participant already turned away.
**Enforced:** the `REPLACE_*` family is flagged by the prelaunch banner and by
the pre-deploy frozen-config audit's PLACEHOLDER severity.

## The device screen-out is a soft wall, clearable before consent only — 2026-08-12

A screened participant is HELD on the entry page (not walked to an ending oTree
could never bring them back from), and a later pre-consent request from an
accepted device clears the screen-out; exit code `-4` is the one code that can
revert. After consent the check never applies again. The state is reset, the
history never is — "how many did the gate turn away" is counted from
`screenout_history`, not the exit code.
**Rejected:** routing to a proper ending page (irreversible in oTree), and a
write-once `-4` (would leave genuine finishers recorded as screened out).
**Enforced:** `tests/screenout_softwall_test.py`; the consent boundary is the
durable `participant.consent_submitted` fact, not a page index. Full working:
`_ai/screenout_softwall_log.md`.

## The clear predicate is exactly the entry-allow predicate minus `undetermined` — 2026-08-12

If clearing allowed *more* than entry, a screen-out could be lifted by a device
that would not have been let in; if *less*, the page tells someone switching
will work when for them it cannot (the reference implementation had this bug:
its `unknown` never cleared, stranding privacy-proxy laptops). `undetermined`
is the single carve-out — no usable header is not a device, and treating it as
a clear would let anyone lift their own screen-out by sending no User-Agent.
**Enforced:** `common.device_clears_screenout` (explicit membership, so
`undetermined` cannot satisfy it whatever a config says);
`tests/screenout_softwall_test.py` §8 states the two asymmetric assertions side
by side.

## `unknown` and `undetermined` are different states — 2026-08-12

A User-Agent that parsed and matched nothing (`unknown`) is a device type a
study may accept or reject like any other; no usable header at all
(`undetermined`) is *not a device type* and must always be allowed. Collapsed,
a study rejecting `unknown` starts ejecting laptops behind privacy proxies.
This is the model case of the collapsed-distinction rule in `CLAUDE.md`.
**Enforced:** `common.classify_device`; `tests/device_gate_test.py`, which is
deliberately weighted toward false positives (browsers that must NOT be
screened). Full working: `_ai/device_allowlist_log.md`.

## The lab comprehension rule is help, not ejection — unlimited attempts — 2026-08-12

Online, crossing the failure threshold disqualifies (`comprehension_dq`); in
the lab the same threshold *starts the study helping*: the one-time re-read
offer (if `quiz_reread` is on), then a dismissible "raise your hand" notice,
escalating at twice the threshold — and the participant may keep trying
forever. The notice is keyed on the threshold and the study type, NOT the
module, so a lab session with `quiz_reread` off still calls the experimenter.
The notice deliberately does not say "you can keep trying" — some participants
should raise a hand instead of brute-forcing radio items.
**Rejected:** disqualification in the lab (there is a human in the room), and
keying the notice on the module (left a module-off lab session with no help at
all).
**Enforced:** `tests/gated_flow_test.py` (lab-reread and prolific-dq
scenarios); the prelaunch check refuses `comprehension_dq` in a lab config;
attempts proven uncapped by `tests/quiz_attempt_log_test.py`. Full working:
`_ai/lab_comprehension_proposal.md`.

## Every graded quiz submission is logged — uncapped, and unable to break the page — 2026-08-12

`quiz_attempt_log` records what was answered and what was wrong *as judged at
the time* (never re-graded — the item set changes between studies), with no cap
on entries, and the whole write is wrapped so instrumentation can never cost a
participant their page.
**Enforced:** `intro.log_quiz_attempt` (never raises);
`tests/quiz_attempt_log_test.py` proves 25 attempts stored and the page still
standing.

## The tab monitor is armed before the instructions and quiz, not after — 2026-08-12

> **CORRECTED 2026-08-13 — see the monitored-by-default entry above.** This
> entry implied the move made the instructions and quiz monitored. It did
> not: only the AGREEMENT moved; no monitor wiring existed in `intro`, so the
> quiz stayed unwatched for a day while four documents said otherwise. The
> enforcement below pinned page ORDER, never coverage — which is how the gap
> survived its own test. Coverage is now real, and enforced at boot.

The agreement page moved from the end of `intro` to `before`: armed after the
quiz, the very check that gates entry was unmonitored — a participant could
consult an AI assistant during it, which is exactly what the page warns
against.
**Enforced:** the page lives in `before.AISafetyAgree`; a comment in
`intro/__init__.py` forbids moving it back; `tests/gated_flow_test.py` asserts
the agreement is not after the quiz.

## Participant identity is decided in one place — 2026-08-12

"Is this the same participant id?" was answered twice — label comparison in
Python (case-folded) and row lookup in SQL (collation-dependent) — so a
returning `ABC123` took a fresh row against a stored `abc123`, and behaviour
differed between sqlite (dev) and postgres (production). One implementation,
called by both.
**Enforced:** `identity.py`; `tests/identity_test.py`. This bug pattern is
generalised as the inverted collapsed-distinction rule in `CLAUDE.md`.

## The layout geometry baseline is committed, so intentional change is reviewable — 2026-08-12

`tests/render_check.py` measures element geometry at three viewports;
`tests/geometry_baseline.json` is committed **on purpose** (to `tests/`, not
gitignored `_ai/`) so an intentional layout change shows up as a reviewable
diff of that file, and an unintentional one fails `--diff`. Layout failures
produce no error otherwise — nothing 500s while the participant gets a broken
page.
**Enforced:** `render_check.py --diff` exits non-zero on movement beyond ±3px;
adopting a change requires `--update-baseline` and reading the diff.

## Three orthogonal controls; profiles resolve to explicit config keys at import — 2026-08-10

Study type, DEBUG (env-driven, so production can never ship skip controls), and
the pilot feedback form are independent axes; there is no "testing" study type
— testing loosenings are a reversible override honoured only under DEBUG. A
recruitment profile is rewritten into explicit per-config keys at import, so
the admin shows exactly what a session ran with and a profile can never change
behaviour silently at runtime.
**Rejected:** a `testing` study type (collapses two axes and lets loosenings
ship), and profiles consulted at runtime (invisible in the admin, mutable under
running sessions).
**Enforced:** `settings.resolve_recruitment_profile`;
`tests/frozen_config_test.py`; DEBUG derived from `OTREE_PRODUCTION` presence.

## Exit codes: initialised at creation, `0` means "never reached an ending" — 2026-08-07 (ported from the pilot)

Every participant carries `exit_code` from session creation, so no export row
is ever blank; `0` is *abandoned* — created but never reached any ending — and
is distinct from every deliberate outcome, each of which has its own code
(screened-out is `-4`, not `0`: you must be able to tell the gate's work from a
closed tab). A code nothing records is a lie in the export, so
reserved-but-unwired codes are deleted, not documented (`timed_out`, removed
2026-08-10).
**Enforced:** `common.init_participant`; the codes table in `CODEBOOK.md`;
tests assert on numeric codes rather than ending copy
(`full_journey_test`, `device_gate_test`).

## Participant and config reads go through safe accessors, always — 2026-08-07 (ported from the pilot)

`participant.vars.get(...)` (never `getattr` — the vars descriptor raises
`KeyError`, which the getattr default does not catch: a live outage), and
`common.cfg(...)` (never `config[...]` — a session config is frozen at
creation, so later-added parameters are absent for running sessions: also a
live outage). `common.flag` is the deliberate exception: a module flag missing
from a frozen config means the module post-dates the session and must read as
OFF.
**Enforced:** `common.pvar` / `common.cfg` / `common.flag`;
`tests/frozen_config_test.py` strips keys and walks; the rules are in
`CLAUDE.md`'s correctness list.

## A test that cannot fail is not evidence — standing principle

Bot tests passing is not evidence a browser works (three pilot outages went
green under bots); a content test loosened until it survives a content change
was never testing the content; a drift check that fails on everything gets
ignored and then catches nothing (see the two-severity entry above). Every
check must correspond to a participant it could save.
**Enforced:** as method, in `skills_claude/writing_tests.md` (real HTTP, no-JS
submits, phone User-Agents, visible-text assertions, measured rendering);
structurally, nowhere — this one is held by review and by the suites being the
shape they are.
