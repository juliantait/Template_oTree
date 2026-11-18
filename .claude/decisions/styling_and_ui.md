# Decisions: Styling and UI

Read before changing CSS, templates, page layout, popups, button rows, the Enter key or the screen lock.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## Enter belongs to the focused control; everywhere else it still moves on, 2026-11-05

**What it is.** `global.js` binds Enter to the page's forward action. It now first asks
whether the focused element has an Enter action of its own: a link, button, summary,
select, textarea, editable text, an ARIA widget role, an input button, an IME committing
a word, or a widget that already cancelled the key. If so, that action happens and the
forward control is not touched.

**Why.** The forward action on a Prolific Results page, and on `Ended` and
`NeutralReturn`, is the "Back to Prolific" link. `results.js` toggled the accordion and
cancelled the key's default, but the event still reached the document handler, so the
table opened and the participant left the study in the same keypress. Reproduced in real
Chromium. The same one rule also fixes: Back and "Re-read instructions" on the
instructions page went forward; the online quiz's re-read button tried to submit the
quiz; and on the lab quiz-failure dialog, Enter on "Re-read the instructions" or on "Keep
trying" submitted the quiz behind it, which graded the attempt and logged another failure.

**Two lists that look redundant and are not.**

- `OWN_ENTER_ACTION` is left to the browser. `INPUT_BUTTON` is pressed by the handler,
  with the key cancelled. On any page with a `live_method` (every monitored page), oTree's
  `live.js` cancels Enter's keypress on every `input`, so natively Enter on a focused
  `<input type="submit">` does nothing. It passes on a plain fixture and on pages without
  `live.js`, and only fails on real pages. Moving `input[type="submit"]` to the first list
  makes Next dead on the keyboard on `payoff`, `Feedback` and others; pressing it without
  cancelling the key would double-submit where `live.js` is absent.
- Text inputs, radio, checkbox and range are in neither list. Enter has no action of their
  own there beyond submitting, and "pick an answer, press Enter" is how people move on.

**Rejected.** Moving the fix into `results.js` with `stopPropagation`: it would fix one
control and leave the class. Dropping Enter-to-forward on ending pages: the brief for this
fix was that Enter elsewhere keeps working as it does today.

**Known and left as they are.** On a Prolific ending, Enter with nothing focused, or on
the "completed" checkbox, is still the forward action, so it still leaves the study. A
browser that does not focus a button on click (Safari) has nothing focused after a
mouse click on the accordion, so a following Enter leaves too. Whether an ending page's
forward action should answer Enter at all is an open decision, not an accident.

**Changed behaviour.** Enter on a focused select no longer moves forward in Chromium here:
the key is the browser's, and it did nothing on a closed list.

**Enforced:** `scripts/tests/enter_key_test.py` (real prodserver, real Chromium, real
keys, POSTs counted, plus every control kind on a fixture running the real `global.js`).
Not enforced: that a study's new custom widget has a role in the list or cancels the key.

---

## The screen lock: a switch, on by default, off for a frozen session, 2026-11-05

**What it is.** `screen_lock=True` in `SESSION_CONFIG_DEFAULTS`. `css_bundle.html` loads
`_static/global/js/screen_lock.js` when it is on; the script sets `html.screen-lock`,
which switches on the rules in `base.css`, and stops `contextmenu` and `dragstart`.
Julian's goal: participant pages feel like a screen, not a website. Copied from
CREED_Helping Micro 1 (b955f04), which has no switch, and is a lab classroom game.

**On by default, against "every flag ships OFF".** That rule is for study modules a
project opts in to. This is no module and gates nobody, and Julian wants it by default.
Not in a recruitment profile: it means the same in the lab and on Prolific.

**A session created before the key existed reads as OFF,** by `is_defined`, the
tab monitor's guard and `common.flag`'s rule, not by `common.cfg`, which would give
the shipped ON. People already in a session keep the pages it started with, and one
session does not change behaviour halfway through. `css_bundle.html` is the one reader,
so the key has an entry in `MISSING_IS_THE_DESIGNED_MEANING` in
`scripts/predeploy_check.py`: telling an operator to recreate a live session over how
text selects would cost more than it repairs. It is still reported.

**Scoped through a class the script sets, rather than bare rules like Micro 1's.**
So switch off, previews (which link `base.css` directly), the room gate and admin
pages get none of it. With JavaScript off the page is simply not locked, which breaks
nothing. **No layout property**, so no geometry baseline can move.

**No cursor rule on fields,** which Micro 1 has as `input, textarea { cursor: text }`.
This template has radios and checkboxes, which that rule would give a text cursor. The
browser's own per-type rules already do the right thing, and inheriting from `body`
does not override them.

**`-webkit-user-select` and `-webkit-touch-callout` as well,** which Micro 1 does not
need on its lab PCs: Safari needs the first, and iOS shows its long-press menu without
the second, with no `contextmenu` event for the script to stop.

**A long-press in a field keeps its menu; a mouse right-click does not.** Julian
accepted losing right-click paste because Ctrl+V works. A phone has no Ctrl+V, and the
Prolific ID page tells a participant to copy their ID, so paste has to stay reachable
there. Written as `pointerType !== 'mouse'`, so a browser reporting no pointer leaves
fields alone: the failure that costs nothing.

**`.selectable` is the exemption, for selection, right-click and long-press.** The
template shows no completion code as text: the code rides the link (`completionlink`,
a real no-JS link, see `prolific_return_footer.html`). So the four ways back to Prolific
carry the class, so that Copy link address is there if the link does not open. There is
no contact email, and bank fields are fields. A fork showing text someone must copy adds
the class. Rejected: exempting by hand-written selectors in the script, a second list to
forget.

**Nothing relied on these events.** No `contextmenu`, `selectstart`, `dragstart` or
`getSelection` anywhere in the participant code. `telemetry_capture.js` listens for
`copy` and `paste`: Ctrl+C on a locked page still fires `copy`, so `copy_detected`
records the attempt, even though nothing is copied. **So `copy_detected` now means
"pressed copy", not "got text out".** Comparing it with sessions run with the lock off
compares two different things. The tab monitor and focus trace listen for `blur` and
`visibilitychange`, which the lock does not cause.

**The room's pages are not locked, and cannot be by this switch.** `room_welcome.html`
gets only `has_participant_label_file` and oTree's room wait page gets no session, so
neither can read a per-session key. Micro 1 loads the script there unconditionally;
here that would leave the switch unable to turn it off. A study's own stock wait page
is also not reached, since it has no `css_bundle.html`; this template ships none.

**Known cost.** Operating-system tools that read a selection (select to speak, a
dictionary lookup) do not work on locked text. Screen readers read the page as before,
and keyboard use and text zoom are not touched.

**Enforced:** `scripts/tests/screen_lock_test.py` (real prodserver, real Chromium, by
real mouse and keyboard, including the frozen session by the real route);
`scripts/tests/frozen_config_test.py` strips the key. Not enforced: that a fork adds
`selectable` to text it introduces. That relies on the README and the settings comment.

---

## The primary action is the RIGHTMOST control in a button row; the two re-read mechanisms stay apart — 2026-08-21

Julian reported being "offered an option to skip the instructions and the quiz"
in a PROLIFIC session and not in a LAB one. Investigated before changing
anything, and the report turned out to be about a real defect but not the one it
described.

**There is no skip.** Driven over real HTTP in production mode, neither study
type is offered any skip: `DEBUG` is off, so the "Skip quiz (testing)" and "Skip
instructions (testing)" buttons are not rendered at all. The prolific quiz page
does carry one control the lab's does not — the at-will **"Re-read the
instructions"** button — and it is a DIALOG opener: `type="button"`, and the
dialog it opens contains no form control of any kind. It submits nothing and
consumes no round. A hand-crafted `redoinstructions=1` POST from a prolific
participant is refused server-side (`reread_available` gates both
`error_message` and `before_next_page`), while the same POST from a lab
participant with the offer open is granted — so the refusal is about the study
type and not about luck.

**The defect was the BUTTON ORDER, which is what made it read as a skip.** The
row rendered `[Next] [Re-read the instructions]`, putting a secondary control in
the rightmost slot — the slot a participant's eye and thumb go to, and the one
the rest of the template reserves for the primary action. It is now a RULE OF
THE COMPONENT rather than a page's decision: `.button-row > .next-button:not(.ghost)
{ order: 1 }` in base.css, with the markup written secondary-then-primary too so
the visual, DOM and TAB orders agree and the `order` declaration is an inert
backstop. **`:not(.ghost)` is load-bearing** — the ghost variant IS the secondary
shape of the same button (the instructions pager's "Back"), so keying on
`.next-button` alone would put Back and Next in the same slot and settle nothing.
Every other page in the template has a one-control row, so nothing else moved.
**Rejected:** patching the quiz page, and extending the rule to `.modal-actions`
— a different component whose own primary-first convention is currently
consistent with itself, and which is not what was reported.

**The two re-read mechanisms are NOT one concept decided twice, and were kept
apart.** It looks like the classic drift: `reread_available` keyed on the
`quiz_reread` MODULE FLAG (True for lab, False for prolific) and
`show_reread_dialog` keyed on the STUDY TYPE (the mirror image). They are two
mechanisms. The lab's is a one-time re-read **PASS** that costs a round and sends
the participant back through `instructing`; the online one is an at-will
**DIALOG** that costs nothing and cannot advance anybody. Each modality gets
exactly one way to see the instructions again — supervised second pass plus a
human to ask in the lab, an always-available dialog online where there is no
such human — and two on one page would read as a contradiction. That is Julian's
own decision (2026-08-11). Merging them would leave one modality with no re-read
at all. The split is now stated at the split point, as a named predicate
(`intro.at_will_reread_available`) whose docstring says why it must not be
merged, with `reread_available` pointing back at it. It reads `not is_lab`
rather than `is_prolific` deliberately: the question is "is there an experimenter
in the room?", and a future third `recruitment` value must get the dialog, not
silently lose its only way to re-read.

**A reported third defect was not one.** `explicit_consent` is absent from the
PROLIFIC entry of `RECRUITMENT_PROFILES`, which looks like a key the profile
forgets to set. It is deliberate and already commented there: the key falls
through to `SESSION_CONFIG_DEFAULTS`, which oTree merges into every session
config at creation. Checked against a real created session — a prolific
session's STORED config carries `explicit_consent=True`, a lab session's carries
`False`. Nothing is missing and no lookup can fail; adding it to the profile
would only duplicate the baseline.

**Where it is enforced.** `scripts/tests/reread_controls_test.py` — both study
types walked to the quiz over real HTTP in production mode: no skip anywhere
(paired with DEBUG asserted off, without which that absence is a statement about
the server); the at-will control present online and absent in the lab; the
dialog proven inert (no form control in it, and its only exit goes back to the
quiz); the hand-crafted POST refused for prolific AND granted for lab; and the
document order. `scripts/tests/render_check.py` leg AI measures the RENDERED
boxes at three viewports — `order` is a layout property, so a source-order
assertion can see neither its success nor its failure.

---

## The scroll model is three modes: whole-window by default, single-page fit as enhancement, inner-scroll kept dormant — 2026-08-18

The card layout was reworked from ONE model (every card capped at 88vh with its
middle region scrolling inside it) into THREE. **Mode 1 — whole-window document
scroll — is the DEFAULT for every content page:** the card has no max-height, it
grows with its content and the whole browser viewport scrolls, with the forward /
decision control at the natural bottom. This is the SAFE default *because* it is
exactly what renders if a page's fit-check script never runs — nothing a
participant needs can be hidden by a script that fails silently, which is the
failure mode CLAUDE.md warns about. **Mode 2 — single-page fit — is progressive
enhancement layered on top of Mode 1**, opt-in on exactly the consent welcome
page and the tab-monitor agreement, desktop only: `global.js` measures and, if it
can, shrinks the body font within a narrow band (down to
`--single-page-font-floor`, ~15px) and tightens spacing to fit one viewport;
if fitting would drop below the floor it GIVES UP and the page is plain Mode 1.
It scales with **font-size and spacing only, never transform/zoom** — those make
the card a containing block and would trap the tab-monitor's fixed overlay inside
it. **The decision controls are never pinned** in either mode: a pinned Next lets
a participant reach the choice before seeing what they are agreeing to, or miss
that more exists below. **Mode 3 — inner-card scroll — is retained ONLY for the
results page** (its round-payment detail collapses to fit one page and expands to
scroll inside the card) and kept as a documented DORMANT opt-in (`.inner-scroll`)
rather than deleted, because the cap, the overflow region and the four scroll
affordances are real work any page may want again.

The card's TOP EDGE is **anchored** at a constant `--card-margin` below the
viewport top on every page, never viewport-centred, so it does not jump between
pages of different content height (Julian). One proportional token feeds both the
anchor offset and the resting floor `--card-min = 100dvh − 2·--card-margin`, so a
resting card is symmetric top-to-bottom (reads as centred) yet fixed: content
shorter than the floor fills/centres inside the frame and never shrinks it, so two
short pages show the identical card. The instructions page is deliberately kept a
Mode-1 page whose shipped payoff-matrix slide (the two blocks "The payoff matrix"
and "What this means in practice" merged into one) overflows a 1280×720 laptop,
so the template ships a permanent demonstration of whole-window scroll.

**Rejected:** the old single capped-and-inner-scroll model (hid consent options
below an inner fold at 1280×720, and made the safe path depend on the fade
script); pinning the decision controls (reach-the-action-before-reading);
scaling the card with `transform`/`zoom` (traps the tab-monitor overlay);
deleting the inner-scroll scaffolding (results still needs it, and it is a
reasonable future opt-in).
**Enforced:** `--card-margin` / `--card-min` / `--inner-scroll-max` /
`--single-page-font-floor`, `.screen-card` (floor, no ceiling), `.inner-scroll`
and `.single-page-fit` in `_static/global/css/base.css`; `initSinglePageFit` in
`_static/global/js/global.js`; `scripts/tests/render_check.py` (Check B asserts
Mode-1 whole-window scroll on content pages and Mode-3 inner scroll on the results
page; Check Q asserts the fixed resting floor and that a tall page grows past it);
the committed `scripts/tests/geometry_baseline.json`. Working notes in
`_ai/scroll_model/` (local only).

---

## Popups are a four-tier ladder, chosen by distance from the experiment frame — 2026-08-17

Decided by Julian; brief in `_ai/template_adoption_brief.md` Topic A (local only —
`_ai/` is gitignored; not in a clone) with his answers in its ANSWERED section, and
the commissioning entry in `TODO.md`. Every message put in front of a participant
is now a choice between **four documented behaviours**, numbered **0–3 by how far
OUTSIDE the experiment frame** the message sits. The tier fixes the *behaviour*
(backdrop? how dismissed? can it move layout?); the call site keeps its own *skin*
and its own words. One catalogue names all four in one place
(`_static/global/css/base.css`, "THE NOTIFICATION TIER LADDER"); the shared
behaviour is in `_static/global/js/global.js` ("POPUP LADDER"), keyed off the
`popup--*` classes and `data-popup-*` attributes, so a study author writes markup
only.

- **Tier 0 anchored** (`popup--anchored`) — no backdrop; a panel beside its
  trigger, dismissed by outside-click or Escape. For something the participant
  ASKED FOR BY CLICKING. NEW in this template (distinct from the CSS-only
  hover/focus `.popover-anchor` tooltip, which stays).
- **Tier 1 toast / "sidetone"** (`popup--toast`) — no backdrop, absolutely
  positioned so it cannot move layout, auto-clearing, `role="status"`. The tier
  that did not exist here before; NEW.
- **Tier 2 modal** (`popup--modal`) — dimmed backdrop, blocks the page.
  **Escape-dismissible BY DEFAULT**; a modal that must be acknowledged opts in to
  button-only with `popup--acknowledge`. Keeps the study card language. IMPLEMENTED
  BY the existing shared warning-modal component (`.modal-backdrop` / `.modal-card`).
- **Tier 3 takeover** (`popup--takeover`) — full-bleed, blurred, opaque, **no
  dismissal by contract**. IMPLEMENTED BY the tab monitor's existing red
  away-overlay (`.tabmon-overlay`), which predated the ladder.

**The load-bearing choice: bring the two existing tiers in BY NAME, not as a
second implementation.** This template already shipped a mature, tested tier-2
modal and a tier-3 takeover. Building fresh `popup--modal` / `popup--takeover`
skins beside them would be the "one concept, two implementations" defect this
repo hunts (CLAUDE.md). So `popup--modal` shares ONE rule block with
`.modal-backdrop`, and `popup--takeover` shares ONE rule block with
`.tabmon-overlay` (grouped selectors, identical declarations) — the ladder is the
vocabulary, the existing components are the implementation. Only tiers 0 and 1,
which genuinely did not exist, are built new.

**The tab-switch warning modal was deliberately NOT migrated onto the shared
chrome, and this is a STOP-and-report, not an oversight.** It is one of the three
tier-2 cases (with the quiz failed-attempt and re-read prompts). The other two
already use `.modal-backdrop`, so migrating them was free — they gained the
`popup popup--modal` name and the shared focus trap, nothing visible changed. The
tab-switch warning keeps its OWN `.tabmon-modal` chrome and its own string-injected
JS in `tab_monitor.js` because re-skinning it would (a) change what the participant
sees (backdrop opacity 0.72 → 0.55, a different box and button) and (b) edit the
file that owns the disqualification route — two unrelated risks in one change, and
the one that can cost a participant their payment is not the popup. It is
catalogued as the tier-2 button-only case instead; the reusable `popup--acknowledge`
modifier plus its specimen give future modals that behaviour without touching the
live monitor. `tab_monitor.js` and `.tabmon-overlay`'s BEHAVIOUR are untouched.

**Accessibility is part of the component.** New tiers 0/1 ship correct roles,
focus move + restore (tier 0), polite announcement (tier 1),
`prefers-reduced-motion` (tier 1 transition, tier 3 blur). A shared focus trap
(`global.js` `popupTrapFocus`, ONE implementation) is wired into the tier-2/3
modals that were missing it — the every-page warning modal and the quiz reread /
failed-attempt dialogs — a keyboard-containment improvement that changes nothing a
participant sees. The generic modal helper traps every takeover and every
non-acknowledge modal while open.

**Rejected:** a separate `popup.js` file (this template centralises shared page
behaviour in `global.js`, the way the warning modal already works, so a new asset
in every template's bundle was avoided); a second `popup--modal` / `popup--takeover`
skin (two implementations of one concept); rewiring the tab-switch warning's chrome
now (participant-visible change coupled to the disqualification route); renumbering
any existing `1–4` tier comments (there were none in this template — that clause of
the brief applied to the pilot). Terminal pages such as the disqualification screen
are a ROUTING concern and out of scope: `popup--takeover` is the in-page overlay
only.

**Enforced:** nothing at boot — the ladder is convention + shared CSS/JS, held by
the base.css catalogue, this entry, and the specimens in `template.html` (CARD 3,
per CLAUDE.md's styling rule that a shared component must be demonstrated). The
behaviour-preserving claim is what the suites hold: `scripts/tests/render_check.py`
(`--diff` 1513 measurements within ±3px, unmoved; the reread dialog, the quiz
failed-attempt modal, the shared warning modal and the tab-monitor overlay all
still measure correct, the overlay still covers the whole viewport); the
browser/HTTP quiz suites (`gated_flow_test`, `full_journey_test`,
`completion_codes_test`), the tab-monitor suites (`tab_monitor_detail_test`, and
render_check's record-only-outro leg), `dashboard_test`, and the site previews
(regenerated and re-checked, since the screens inline these stylesheets). The
just-fixed regression suites (`completion_codes_test`, `screenout_softwall_test`,
`device_gate_test`) stay green. `STATIC_VERSION` 15 → 16 and the manifest were
re-stamped (base.css, tabmonitor.css, global.js, quiz.js, template.html changed).

---

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
`scripts/tests/geometry_baseline.json` pins the shared rhythm at all three viewports;
the affordance and touch-target legs of `scripts/tests/render_check.py` assert the
pages still behave.

---

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
logo geometry is in `scripts/tests/geometry_baseline.json`.

---

## Styling is shared components, never page-local patches — 2026-08-13

A page template composes named classes from `_static/global/css/`; no inline
`style=`, no one-off rule to fix a single page, and every new component gets an
INTENTION comment plus a specimen in `_static/global/html/template.html`.
Driven by three real bugs of the same shape: a class referenced by three
templates and defined nowhere, one concept carrying two widths, and an inline
`height` beating the component's own rule. Genuine one-screen exceptions are
marked `EXCEPTION` with the reason.
**Enforced:** the Styling section of `CLAUDE.md`; layout drift is caught by
`scripts/tests/render_check.py` against the geometry baseline. The no-inline-style rule
itself relies on review. Full working: `_ai/css_divergence_report.md` (local only — `_ai/` is gitignored; not in a clone).
