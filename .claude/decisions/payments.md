# Decisions: Payments and payoffs

Read when you touch payoffs, the payment ledger, the participation fee, money read from config, or bank details.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## `participation_fee` ships 0, and a boot guard holds it there — 2026-08-14

Decided by Julian. oTree's built-in `participation_fee` is a SECOND payment
channel: it is not part of `participant.payoff`, it is added on top of it by
`Session._get_payoff_plus_participation_fee` (otree/models/session.py:242-248),
which feeds the admin Payments page (`otree/views/admin.py:274`,
`templates/otree/SessionPayments.html:46`) and the MTurk payment table. It does
NOT reach the CSV export — verified against 6.0.15, the participant column list
ends at `payoff` (`otree/export.py:76-96`) — so a fee is invisible in the data
and visible only where a human reads off what to pay, which is worse. This template keeps **one payment ledger** — the base is
`payment_show_up`, which `outro.compute_final_payoff` folds into `participant.payoff` with
the bonus, so the admin figure equals the amount actually owed. A non-zero fee
splits that across two numbers computed by different code in different places,
which is the condition the single-ledger decision exists to prevent.

**Why a guard and not just a zero in the config.** A zero in a config is a
convention, and an unenforced convention in a template drifts the first time
somebody copies it. `participation_fee` is a standard oTree knob that the
official docs and tutorials set; a researcher starting from this template will
meet it there and set it in good faith, with no error to say the payment record
has quietly split. This repo has already had one convention-only rule turn out to
be nothing (three documents calling oTree's `player.payoff` raise "enforcement"
when it fires inside a participant's request).

**Boot, never request time** — the `core/payoff_guard.py` precedent, and the reason is
the same: oTree has no migrations, so an upgrade under live sessions is how every
study built from this template is actually deployed, and a check that fires in a
request is a dead page for whoever is mid-study. `core/fee_guard.py` is called from
`before/__init__.py` beside the other two boot guards.

**THE KNOWN COST, ACCEPTED WITH EYES OPEN.** A study copied from this template
that already sets a `participation_fee` **will refuse to boot** until the money
is moved into the ledger (into `payment_show_up`, or into `outro`'s `earned`). A real cost
paid by a real person — and the trade is deliberate: the alternative is a study
that runs happily with a payment record that is wrong in a way nobody notices
until payout, when somebody is underpaid.

**What it does NOT catch — a boot SOURCE scan cannot see a running session.**
oTree's `SessionEditPropertiesForm` (otree/views/admin.py:212) exposes
`participation_fee` as an editable field on a LIVE session, and `form_valid`
(admin.py:255-261) writes it into `session.config`, a DATABASE COLUMN on the
session row (`Column(_PickleField)`, models/session.py:35). The value lives in
data, so **no restart will ever catch it** — the guard passes while the session
carries a fee. Verified against 6.0.15, and measured: the ledger stayed at
€10.00 while the Payments figure moved to €13.00.

**Policing that is deliberately out of scope** (Julian + the hosting review): an
operator editing a live session is an operator action and is trusted. A
dashboard warning was proposed, costed, and CANCELLED. What was required instead
is that it be visible rather than silently clean — and it already is, for free,
because `predeploy_check`'s frozen-config audit reads the session ROWS rather
than the source and reports it as a plain value difference (`frozen 3.00cu vs
current setting 0.0`, confirmed on a real edited session). Check the artifact,
not the recipe; this guard is the recipe half and must never be written up as
more than that.

**Rejected:** relying on `AUTO_TABULATE_PAYOFFS`-style enforcement from oTree
(there is none for this field), and a runtime check in `outro` (same dead-page
trade the payoff guard exists to avoid).

**Enforced:** `fee_guard.assert_participation_fee_is_zero()`, called at boot from
`before/__init__.py`. Two halves: the RESOLVED configs (`SESSION_CONFIG_DEFAULTS`
must carry an explicit 0; a per-config entry may omit the key but must not set a
fee) and an AST scan of app packages (the shared modules in `core/` included) for
`participation_fee` written as anything but a literal 0 — assignment, attribute,
`config['participation_fee']`, a `dict(participation_fee=…)` keyword, or a dict
literal. The scanned file list comes from `payoff_guard.files_to_scan`, not a
second copy of the rule, so the two guards cannot disagree about which
directories are apps. Verified 2026-08-14: the template boots clean (15 files
scanned); a fee in the defaults, an absent key, and a per-config override each
refuse the boot; a config omitting the key inherits correctly; all seven source
shapes fire and a literal 0, a `0.00` keyword and a *read* of the key do not.
Proven end to end with `otree resetdb` — the shipped template exits 0, and with
`participation_fee=2.50` the boot fails with the guard's message.

---

## One guard policy for a config-read money value: fail loudly — 2026-08-13

Whole-app review B4, decided by Julian. `payment_show_up` / `payment_quiz_bonus` were read two
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

---

## One payment ledger: per-round `player.payoff` is not used, `participant.payoff` is written once from `earned` — 2026-08-13

Review item J1 (Julian; sub-decision also his). The underlying conflation:
oTree automatically sums `player.payoff` across rounds into
`participant.payoff`, but this template pays only `payment_num_rewarded` randomly
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
`outro/__init__.py`, `docs/CODEBOOK.md` and `.claude/skills/writing-task/SKILL.md` all
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
**Enforced:** `core/payoff_guard.py`; `scripts/tests/payoff_ledger_test.py` §7 (a walked
journey leaves every round row's `_payoff` at 0) and §8 (the guard catches six
write forms including `setattr` with a literal name, refuses a synthetic build
naming file and line, does NOT fire on the participant write or on prose,
declares its `setattr`-with-computed-name blind spot, and reports an
unparseable module as "cannot answer" rather than as a payoff write).

**Enforced:** `scripts/tests/payoff_ledger_test.py` (the two figures agree on the
admin page itself; the value survives re-renders; oTree's setter does raise;
the export column is absent while `round_payoff` is present) — plus the boot
guard above.

---

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
`scripts/tests/payoff_ledger_test.py` §9 walks a *prolific* session and asserts the
BONUS IN ISOLATION as well as the total — each component recorded on its own,
the three reconstructing `earned` with zero residue, the bonus
(`selected_sum + quiz_bonus_awarded`) derived from the stored components
rather than as `total − base` (which would be right by construction and prove
nothing), both halves separately readable, and the components present as their
own export columns. It also records the admin-page state as a **measured gap**.

**THE CONCRETE FIGURES THIS DECISION IS BEING MADE AGAINST**, so nobody reading
it later has to reconstruct what the admin page actually showed. One real
walked Prolific completer (participant `240pbcpa`, config `prolific`, 10 rounds,
`payment_num_rewarded=2`, exit code 1), measured 2026-08-14, all figures EUR:

| Figure | Source | Value |
| --- | --- | --- |
| base / show-up | `payment_show_up` (session config) | **2.50** |
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
**Enforced:** `scripts/tests/payoff_ledger_test.py` §9; the rule is stated in
`.claude/reference/payments.md` "Paying participants — the itemisation rule" and in CODEBOOK "THE
ITEMISATION RULE".

---

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
**Enforced:** `scripts/tests/bank_details_test.py` pins both halves of the asymmetry,
next to each other.
