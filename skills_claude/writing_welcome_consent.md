# Skill: writing the welcome + consent page(s)

Read this whole file before writing or editing the welcome/consent content. The
deliverable lives in the `before/` app: the page template `before/welcome+consent.html`
and its page class in `before/__init__.py` (plus a no-consent page, see below). The
shipped template contains a lab-style placeholder (implicit "by continuing you consent",
IBAN language); for a Prolific study it must be replaced along the lines described here.

## Overriding principle, and its one exception

> **FAVOUR SIMPLICITY FOR PARTICIPANTS OVER OVER-EXPLAINING.**

This still governs the **welcome** text: say little, cut hard.

But read this carefully, because the consent section is the **deliberate exception** to
the house style. Every other skill in this folder says "when in doubt, cut". On consent,
**completeness beats brevity**: the consent elements exist because ethics/IRB approval
requires them, not because they help UX. An agent that applies the usual "cut everything
that isn't doing work" instinct to a consent page will happily delete a legally required
clause. **Do not do this.** On consent you simplify the *language* (short sentences,
plain words, no legalese) but you never drop a *required element*. If a consent sentence
seems useless, assume it is required until a human confirms otherwise.

## ⚠️ Do not invent the consent wording ⚠️

This file gives you the **structure and the checklist only**. The actual consent text is
governed by the researcher's own institution: their ethics/IRB approval typically fixes
or constrains the wording. Draft against the checklist below if asked, but **flag
explicitly that the text must be checked against (and if necessary replaced by) the
institution's approved consent wording** before the study runs. Never present
agent-drafted consent text as final.

## The welcome part: say little

One short, warm paragraph. It tells the participant only:

- what this is, in the vaguest honest terms: a short judgment/estimation task on Prolific,
- roughly how long it takes,
- that payment is a base reward plus a bonus that depends on accuracy.

That is the whole job. **Do not explain the task mechanics here.** What the stimulus
looks like, what the choices are, how scoring works: all of that belongs to the
instructions (`writing_instructions.md`). Front-loading it on the welcome page makes
this page long and the instructions redundant, and the participant reads it before they
have any context to hang it on.

- ✅ "Welcome, and thank you for taking part. This is a short judgment task that takes
  about 10 minutes. You will earn a base reward, plus a bonus that depends on how
  accurate your answers are."
- ❌ A welcome that continues "...you will see boxes of blue and orange dots and decide
  which machine generated them, earning points under a scoring rule where..."

## The consent part: required elements

Consent must cover, in plain language, each of the following. This is a checklist of
**elements**, not approved wording (see the caveat above):

- [ ] **Voluntary participation**: taking part is voluntary, and the participant may
      withdraw at any time without penalty.
- [ ] **What data is collected, and that it is anonymous/confidential**: including how
      the Prolific ID is handled (it is received for payment/administration but is not
      linked to the participant's identity in the analysis).
- [ ] **Risks**: no foreseeable risks or discomfort beyond everyday computer use (or the
      study's honest equivalent).
- [ ] **Who is running the study, and an ethics/contact point**: institution, research
      team, and whom to contact with questions or concerns.
- [ ] **Data use, storage, and sharing**: what the data will be used for (research),
      how and how long it is stored, and whether/how it may be shared (e.g. anonymised
      data in publications or repositories).

Register: plain and honest. No legalese that loses a lay reader, but no dropping of
required substance to get there. Rewrite "the investigator may terminate your
participation" as "you can stop at any time", not by deleting the clause.

## Mechanics: explicit consent and a graceful no

- **Consent is an explicit affirmative action.** A button ("I consent and want to take
  part") or an unticked checkbox the participant selects themselves. **Never a
  pre-checked box**, and never the shipped placeholder's "by continuing to the next page
  you consent". Doing nothing must never count as consenting.
- **There is a graceful no-consent path.** Offer a decline option ("I do not consent")
  next to the consent action. Decliners go to a dedicated page, shown only to them,
  which says they have chosen not to take part and offers a single button to withdraw
  and return to Prolific via a Prolific screen-out/return completion code. Decliners
  **never enter the task**: no instructions, no quiz, no data collection beyond the
  decline itself.
- Wire this in `before/__init__.py`: record the consent choice on the page, and use
  `is_displayed` (or `app_after_this_page`) so the no-consent page appears only to
  decliners and consenters never see it.
- Keep the two outcomes symmetric in tone: declining is a normal, penalty-free choice,
  not a failure state. No guilt-tripping, no "are you sure?" loops.

## Checklist before you finish

- [ ] Welcome is one short paragraph: judgment/estimation task, rough duration, base
      reward plus accuracy bonus. Nothing about task mechanics.
- [ ] Every required consent element above is present (voluntariness/withdrawal, data
      and Prolific ID handling, risks, who is running it and a contact point, data use/
      storage/sharing).
- [ ] Language simplified, substance intact: no legalese, but no required element cut.
- [ ] Consent is an explicit action (button or unticked checkbox); nothing pre-checked;
      no "continuing means consenting".
- [ ] Decline path exists: dedicated page for decliners only, with a withdraw button
      that returns them to Prolific via a screen-out/return completion code.
- [ ] Decliners never reach instructions, quiz, or task.
- [ ] Flagged clearly to the researcher that the consent wording must be checked against
      their institution's ethics/IRB requirements and is not final as drafted.
