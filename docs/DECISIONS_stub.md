# Decisions (YOUR STUDY NAME)

> **This is the STUB for a study forked from oTree-Template.** On a new study,
> copy this file to the repository root as `DECISIONS.md`, replace the title, and
> **delete the template's own `DECISIONS.md`** (which logs the template's
> development, not your study; carrying it over hands the next agent the wrong
> precedent). Then delete this note and start logging below. See the README's
> "How to use and edit this template" for where this fits in setup.

Design and implementation decisions with the REASON attached. **The reason is the
point.** A forked study starts with no precedent, so every deliberate choice
looks arbitrary to the next agent who meets it, and the failure mode is not
ignorance but **helpfulness**:

- a **missing config value** reads as an unfinished port, so it gets filled in;
- **inert code** reads as dead weight, so it gets deleted;
- **a constant that is only coherent at one value** reads as a tunable knob, so
  it gets tuned.

Each of those would be "corrected" by a competent agent acting reasonably, and
each undoes a decision on purpose. The only defence is to **record the decision
with its reason, in the same change that makes it**, newest first. A reason
written a week later is a reason half-remembered; a reason never written is a bug
waiting for the next helpful hand.

Newest first. Each entry: what was decided, why, the alternative rejected, and
where it is enforced (or an admission that nothing enforces it).

---

## YYYY-MM-DD

### One-line decision, phrased as the choice you made
Why this and not the obvious alternative. What a later agent would "fix" if the
reason were not here, and what that would break. Where it is enforced (a guard, a
test, a boot check), or an honest "nothing enforces this; it relies on this
note."

<!--
Delete the example above and write your first real decision the moment you make
one. An empty log is fine on day one; a wrong-precedent log (the template's
carried over) is not.
-->
