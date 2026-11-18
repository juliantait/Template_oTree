# Paying participants

*Read this when you touch payoffs, the Results receipt, or the payment export.*

## Paying participants — the itemisation rule

> **ONE LEDGER.** Everything a participant is owed ends in `participant.payoff`,
> written once by `outro.compute_final_payoff`. Two boot guards hold that:
> `core/payoff_guard.py` refuses a build that writes oTree's per-round
> `player.payoff`, and `core/fee_guard.py` refuses one that sets oTree's built-in
> `participation_fee` to anything but 0 — oTree adds that fee ON TOP of
> `participant.payoff` on the admin Payments page, so a non-zero value splits
> what you owe across two numbers, and it never reaches the CSV export at all.
> **A study copied from here that already sets a fee will refuse to boot until
> the money is moved into the ledger** (into `payment_show_up`, or into `earned`). That
> cost is deliberate — see `.claude/DECISIONS.md`.

> **ANY PAYMENT COMPONENT PAID OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE
> OTREE, OR THE ADMIN PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A
> TOTAL.**
>
> **Corollary — on Prolific the components are paid by DIFFERENT MECHANISMS**
> (the base as the study reward, the bonus through the bonus payment flow), so
> the total alone is not enough: **the bonus must be separately visible**, and
> it is the number that has to survive intact.

Raised by the exp_pilots bossman (2026-08-14). The failure has two shapes and
they look like opposites, which is why one rule covers both:

- **Complete but not itemised** — every component is inside oTree and the total
  is right, but the admin Payments page shows one undifferentiated number. It is
  correct and **not actionable**: whoever pays the Prolific bonus cannot read the
  bonus off it. *This is the shape this template is in today.*
- **Itemised but incomplete** — the components are separate, but one of them (a
  base paid on the platform) never entered oTree at all, so the "total" is a
  partial figure wearing a total's name.

Neither has the property that matters, which is **itemisation of a complete
set**. What this template records per participant, all of it inside oTree:

| Figure | Where it lives | Paid on Prolific as |
| --- | --- | --- |
| base / show-up fee | `payment_show_up` in the session config; rendered on the receipt as **Base payment** | study reward |
| decision bonus | `outro.Player.selected_sum` (the `payment_num_rewarded` selected rounds) | bonus payment |
| quiz bonus | `outro.Player.quiz_bonus_awarded` | bonus payment |
| **total** | `outro.Player.earned`, mirrored once into `participant.payoff` | — |

The three components reconstruct `earned` exactly, with no residue, and the
export carries `player.selected_sum`, `player.quiz_bonus_awarded` and
`player.earned` as their own columns — so **the bonus figure is recoverable
today from the export**, even though the admin Payments page shows only the
total. The participant's own receipt already itemises; the gap is on the
payer's side.

**Pinned by** `scripts/tests/payoff_ledger_test.py` §9, which walks a *prolific*
session and asserts the bonus in isolation as well as the total — because a
study can get the total right while making the actionable number unreadable,
and a test that only checks the total will not notice. §9 also records the
current admin-page state as a measured gap; if the bonus is ever surfaced
there, that check is expected to go red and should be rewritten to assert the
new behaviour.

Whether `participation_fee` should carry the base (so oTree itself splits
reward from bonus) is an **open decision** — it changes what the exported
columns mean, so nothing has been changed yet.
