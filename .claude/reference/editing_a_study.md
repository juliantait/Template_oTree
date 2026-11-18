# Editing the template into a study

*Read this when you start a new study from the template: the ordered walkthrough, rebranding, notification tiers, sharing instructions with coauthors.*

## How to use and edit this template

An ordered walkthrough for starting a new study, for people and agents alike.
Each step names what to edit and links the `.claude/skills/` file that holds
the method — read the matching skill file **before** editing that surface.
The order matters: the game is built in `main` **before** `intro` is written,
because `intro` *describes* the game and describing before building is
backwards. (The shipped template has more Stag Hunt content in `intro` than in
`main` — that is an artefact of it being a placeholder that needed something
concrete to describe, not a pattern to copy.)

0. **Start your own decision log, before you change anything else.** Copy
   [`.claude/decisions/_study_stub.md`](../decisions/_study_stub.md) to
   `.claude/decisions/study.md` and put your study's name in the title. The
   template's topic files in `.claude/decisions/` **stay**: they record why the
   code your study inherits is the way it is. `study.md` holds what is specific
   to your study, and where one of your decisions overrides a template one, it
   says so and names the entry. Then **record each deliberate
   choice with its reason in the same change that makes it**, newest first: a
   forked study starts with no precedent, and the failure mode that eats
   undocumented decisions is not ignorance but **helpfulness**: a missing config
   value reads as an unfinished port and gets filled in, inert code reads as dead
   weight and gets deleted, a constant only coherent at one value reads as a
   tunable knob and gets tuned. The stub explains this and shows the entry format.
   **The same fork-time step applies to `docs/CODEBOOK.md`:** it opens with an Analyst
   quick start built around the template's placeholder slider outcome, so replace
   that quick start with your study's own primary outcomes, exclusions and pooling
   caveats, and add your study fields to its primary tier (the file marks each
   spot with a PROMPT box). Do it in the same change that swaps the task in
   `main`, so an analyst opening the codebook cold sees your outcome first, not
   the placeholder.
1. **Decide the audience and the recruitment settings** — lab or Prolific,
   chosen via the `recruitment` profile plus the module flags and (for
   Prolific) the completion codes; see [the parameter scheme](parameters.md). Then shape
   the entry pages: welcome + consent live in `before/welcome+consent.html`
   and `before/__init__.py` → [`.claude/skills/writing-welcome-consent/SKILL.md`](../skills/writing-welcome-consent/SKILL.md).
   Treatment assignment: set your cells in `settings.TREATMENT_CELLS`
   (shipped as the placeholder `['row', 'column']`) — treatments are assigned
   **on arrival** at the first instructions page (`intro.instructing`), so a
   participant who abandons at consent or is turned away by the device gate
   never takes a cell. The mechanism in `before/treatment_assignment.py`
   (`assign_on_arrival`) balances the cells as participants arrive
   (least-filled, random tie-break) and is race-safe per session; change the
   cells, keep the mechanism.
2. **Build the game in `main/`** — replace the placeholder task pages,
   subclassing `TaskPage` and keeping the machinery you inherit (round loop,
   progress strip, monitoring, payoff plumbing); update
   `scripts/tests/main_contract.py` in the same change
   → [`.claude/skills/writing-task/SKILL.md`](../skills/writing-task/SKILL.md), the
   full manifest of everything a game swap touches.
3. **Write `intro` to match the game you built.**
   Instructions content: edit `intro/instructions_text.html` — each
   `<div class="instruction-block">` is shown as one page to participants;
   add, edit, or reorder blocks there to change the instruction pages
   → [`.claude/skills/writing-instructions/SKILL.md`](../skills/writing-instructions/SKILL.md).
   Quiz questions: edit `intro/quiz_items.py` — define `QUIZ_ITEMS` entries
   with `field`, `prompt`, `choices`, and `answer`; the intro quiz reads
   directly from this file
   → [`.claude/skills/writing-quiz/SKILL.md`](../skills/writing-quiz/SKILL.md).
4. **The `outro` work.** Experimental payoff: edit `outro/payment_rule.py` to
   determine how participants are actually paid — the logic inside this file
   controls which rounds and payoffs are selected for payment at the end.
   The Results receipt renders what `outro.compute_final_payoff` computes.
5. **Test what you built** — real HTTP, a no-JS submit, and a measured render
   check; before launch run `scripts/prelaunch_check.py` and
   `scripts/predeploy_check.sh`
   → [`.claude/skills/writing-tests/SKILL.md`](../skills/writing-tests/SKILL.md) and
   [testing.md](testing.md).

### Rebranding a copied study (whose logos and whose university)

This template ships the CREED and University of Amsterdam marks as its
defaults. **If you are not us, changing them is two image files and one line.**

| What | Where | Note |
|---|---|---|
| Your lab / centre mark | `_static/global/images/lab_logo.jpg` | replace the file, keep the name |
| Your institution mark | `_static/global/images/university_logo.jpg` | replace the file, keep the name |
| Your institution's name **in prose** | `settings.INSTITUTION_NAME` | read by the consent page's privacy sentence |

Then bump `settings.STATIC_VERSION` and re-record the asset manifest
(`python scripts/prelaunch_check.py --stamp-assets`), as with any change under
`_static/` — both steps, every time. Forgetting the re-stamp turns the
cache-buster stale silently; `scripts/tests/asset_manifest_test.py` goes red
when the manifest no longer matches the files, and `prelaunch_check.py` blocks
the launch.

Three things worth knowing before you swap:

- **Both marks are sized by HEIGHT** (40px in the footer, 32px on a phone and
  on a short screen), so their widths follow their aspect ratios. The shipped
  marks are wide wordmarks; a tall, square mark will take much more width than
  the row can give it and the strip will wrap. See the `.logo-row` note in
  `base.css`.
- **`lab_logo.jpg` appears in two places** — the footer strip on every page
  where the institution speaks, and beside "Welcome to" on the lab gate
  (`before/startpage.html`). One file, both places, on purpose: it is what
  keeps the swap to two files. If you want a compact variant on the gate,
  point that one `<img>` in `_static/global/html/welcome_header.html` at it and
  mark the departure.
- **The alt text is deliberately generic** ("University logo", "Research lab
  logo") rather than read from `INSTITUTION_NAME`, and that is not an
  oversight. The logo partials are also included by `_templates/room_welcome.html`,
  which oTree renders with a context of only `has_participant_label_file` — no
  session, no config, no `C` — so a constant referenced there would work on
  every participant page and break the room gate, which is the lab's front
  door. The institution is carried by the image; the name lives in settings for
  the places that can read it.

`INSTITUTION_NAME` carries its own article (`'the University of Amsterdam'`,
but `'MIT'`): the sentence using it cannot know which one your name takes.

### Notification tiers (popups)

Every message you put in front of a participant is a choice between **four
documented behaviours**, numbered 0–3 by how far *outside the experiment frame*
the message sits. The tier fixes the behaviour (backdrop? how is it dismissed?
can it move the page layout?); your call site supplies the words. Add
`class="popup popup--<tier>"` and the shared CSS (`_static/global/css/base.css`,
"THE NOTIFICATION TIER LADDER") plus the shared JS (`_static/global/js/global.js`,
"POPUP LADDER") give you the ARIA, keyboard and dismissal for free — you write
markup only. A working specimen of each is in
`_static/global/html/template.html` (CARD 3).

| Tier | Class | Backdrop | Dismissal | Use it for |
|---|---|---|---|---|
| 0 anchored | `popup--anchored` | none | outside-click / Escape | something the participant **opened by clicking** — an explainer beside a label, a term, how the bonus works. Not for anything that must be acknowledged, reports a broken rule, or is time-critical. (For a passive hover hint use `.popover-anchor` instead.) |
| 1 toast (sidetone) | `popup--toast` | none | auto-clears (≈4s, or `data-popup-timeout`) | a **fading acknowledgement** of what they just did. Never dismissed by hand. Its host must be `position: relative` (use `.popup-toast-host`). |
| 2 modal | `popup--modal` | dimmed | Escape **by default**; `popup--acknowledge` makes it button-only | a **decision they must make** before continuing. Keeps the study's own card language (the shared `.modal-card`). |
| 3 takeover | `popup--takeover` | opaque, blurred | **none** — clears only when the condition clears | **the study has stopped**. A takeover never carries a close control; if it needs a button it is a modal. |

Wiring at the call site: a `data-popup-open="ID"` button opens tier 0/2/3;
`data-popup-toast="ID"` shows a toast; `data-popup-close` inside a modal closes
it. Tiers 2 and 3 already had live instances when the ladder landed — the
shared warning modal, the quiz dialogs, and the tab monitor's red away-overlay
(tier 3) — so those keep their own behaviour and are brought in *by name*, not
rewired; see `.claude/decisions/styling_and_ui.md`.

## Collaborating on the instructions flow with others?
You can share the instructions with coauthors who don't have the codebase installed.

**No terminal? Double-click `previews/Preview_Instructions.command`** (macOS). It picks a
Python, checks the two packages the generator needs, runs it against saved
settings if you have them, and opens the interactive preview in your browser. It
drives the maintained generator in `intro/` — never the stale copy that the
regenerable `previews/` output directory may also contain.

Otherwise the generator lives in the intro app it previews: run `python3 intro/generate_instructions_preview.py` (from the project root) to produce three self-contained files in a gitignored `previews/` output dir it creates on demand: a long stacked HTML (every block on one page), an interactive single-page HTML (one block at a time, with a floating treatment switcher), and a PDF rendition. All three are fully self-contained — no external dependencies, no internet — so you can email them or drop them into a doc and they'll render the same anywhere. The interactive HTML lets coauthors click through the instructions exactly as participants would and flip between treatments live via the corner buttons; the PDF is good for printing or marking up on paper. The generated files are regenerable and never tracked in git.
