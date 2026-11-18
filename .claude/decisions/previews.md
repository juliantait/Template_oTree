# Decisions: Instruction and site previews

Read when you touch the instructions preview or the website screen previews in `scripts/site_previews/`.
Part of the template's decision log; how to read and write an entry is in
[`README.md`](README.md). Newest first.

---

## Instructions preview: bare `{% if flag %}` is resolved at build time, absent = false — 2026-10-07

`intro/generate_instructions_preview.py` only understood treatment
conditionals (`{% if treatment == "row" %}`), which the interactive preview's
switcher flips live. The intro text gained profile/page-state flags on
2026-08-25 (`is_prolific` for the quiz-attempts disclosure, `is_reread_pass` in
`prequiz_text.html`), and those tags fell through every transform and were
printed as literal `{% if is_prolific %}` text in the long and interactive
previews — found while regenerating the website copy
(`_ai/site_previews/instructions_interactive.html`, which is this generator's
interactive output copied, not a `build_site_previews.py` product).

Such flags do not vary by treatment, so they are resolved once at build time
(`resolve_flag_conditionals`) from an optional top-level `"flags"` dict in the
config, and the PDF context receives the same dict. **An absent flag is
false** — matching the PDF path's Jinja `Undefined`, so all three outputs agree
— which makes the default the lab, first-pass view the website shows. Rejected:
treating flags as matrix rows (they would then appear as fake treatment
variables and could differ per column, which no session can do).
**Enforced:** nowhere by a test. A new kind of template tag in
`intro/*_text.html` can leak the same way; grep the outputs for `{%` after
regenerating.

---

## The website's screen previews are GENERATED from the template, not drawn — 2026-08-15

Decided by Julian. The academic site shows several screens of the study (welcome
lab, consent lab, instructions, a decision screen, results lab; the experimenter
monitor was added 2026-08-16, see below). They used to be hand-written
one-off HTML snapshots, and by August they no longer looked anything like the
template.

**The failure is not that they were wrong; it is that nothing could tell.** A
snapshot has no relationship to the CSS it imitates, so when a shared component
moved, the snapshot went on rendering perfectly — just as a picture of an older
study. No error, no failing test, no visible symptom: the same silent-drift
shape as the client-side traps in `CLAUDE.md`. So the previews are now DERIVED —
`scripts/site_previews/build_site_previews.py` inlines `_static/global/css/` **verbatim**
(the stylesheets are never re-typed) and embeds the logos as data URIs, giving
one standalone file per screen with no external reference of any kind, because
they load in an iframe on a static site with no access to this repo.

**Source is tracked; output is not.** The script and
`scripts/site_previews/bodies/` are in the repo; the built files land in
gitignored `_ai/site_previews/`. A generator living in `_ai/` would die with the
container and the next person would hand-write another one-off — which is the
defect, restored.

**The screen is drawn on a fixed 1920x1080 canvas inside a nested `srcdoc`
frame**, scaled to the iframe by `calc(100vw / 1920px)` (a length over a length
is a number; no script, so it survives scripts being blocked). The frame is not
decoration: the template sizes itself in viewport units — the card is `88vh` and
`base.css` tightens its rhythm below 820px of height — so "what the template
looks like" is only defined at a given screen size, and rendered raw a small
iframe would be a different, clipped layout from a large one. Inside the nested
context those units resolve as they do for a participant on a 1080p display.

**Two honest departures, stated in the artefacts themselves** rather than only
in the hand-off message the files outlive: the decision screen is INVENTED (this
template ships no game screen — `main/game.html` is a placeholder — so it is
built only from real components, and must not be copied back into `main/`), and
the results screen is TRIMMED (the real page is the longest in the study and
genuinely scrolls inside its card; with the payoff table open it does not fit
16:9 at any size, so the greeting line is dropped and a short session shown).
**Enforced:** `scripts/site_previews/check_site_previews.py` — measured in headless Chromium
at four 16:9 sizes with JavaScript on and off: no external request, the canvas
viewport is the one composed for, no cut-off scroll region, the card fills, and
the lab screens name Prolific in no **rendered** text (asserted on `innerText`,
paired with a minimum-text assertion, because an absence check alone passes
against a blank page). Re-running after a CSS change is enforced by nothing —
it is a note in `CLAUDE.md`'s styling section and in `previews/SUMMARY.md`.

---

## The monitor preview is RENDERED BY THE DASHBOARD AND FROZEN, not hand-written — 2026-08-16

Requested by Julian: put the experimenter monitor on the academic site as a
sixth preview, same 1920x1080 canvas as the others.

**It could not be built like the other five, and the reason is worth keeping.**
Every participant preview is a hand-written body in
`scripts/site_previews/bodies/` composed of real shipped components, with the
real stylesheets inlined. The monitor has no body to write: `core/experimenter_dashboard.py`
serves a shell whose `<tbody>` says `Waiting for first data…`, and every row,
timeline marker, pill and quiz cell is built by that file's own `renderRow` /
`stateHTML` / `timelineHTML` in JavaScript from the poll's JSON. Hand-writing
those rows would have been **a second implementation of renderRow** — the
inverted collapsed-distinction rule in `CLAUDE.md`, and the drift would have
been invisible: a pill that changed shape in the dashboard would go on looking
right in the preview forever.

**So the build runs the real page.** `build_monitor` imports `_PAGE_HTML`
(stylesheet, script, header cells and step list all already resolved from
`STEP_LABELS`), inlines base.css in place of the `<link>`, stubs `fetch` to
return the invented session in `scripts/site_previews/monitor_session.py`, loads
it in headless Chromium, waits for the poll to paint, and **freezes the DOM with
every `<script>` stripped**. The output is markup the dashboard itself produced,
needing no server and no JavaScript — which is what earns it the same
scripts-disabled guarantee the other five have for free. The cost, stated: this
one screen makes the generator depend on Playwright at build time (the five
participant screens still build on the standard library alone).

**It is a LAB session, and that is why it shows no "ended early" rows.** All
four terminal states need a module `RECRUITMENT_PROFILES['lab']` switches off —
`telemetry_device_capture` (📵 screened out), `explicit_consent` (✋ declined), `quiz_comprehension_dq`
(❌), `tab_monitor` (👀) — so a real lab monitor never shows one. Putting them on
anyway would repeat the exact error that once shipped a consent preview with a
radio button no lab participant has ever seen. The built file says this in its
own header, because an absence on a picture reads as a missing feature.

**The data is invented and the file is public**: seat numbers, no Prolific IDs
(a Prolific row's label IS the platform ID), no completion codes, no contact or
bank details — the screen has no column for any of those.

**Enforced:** `check_site_previews.py` asserts the frozen page has the expected
row count (imported from the fixture, not typed) and at least one of each mark
the fixture exists to demonstrate — the timeline markers, the done tick, green
finished rows, amber stalled rows, dimmed not-arrived rows, all four quiz-cell
states, the earnings and live-timer pills, the Non-SEPA pill, the code fallback
and the averages strip. Without that, the way this preview fails is a freeze
caught before the paint: an empty or half-drawn table, which trips no geometry
check and is indistinguishable from a working one at thumbnail size.

**Known and accepted: it is not readable at grid-thumbnail size.** Measured
2026-08-16, apparent text in a two-up 590px tile is 3.3–5.7px; at a 1280px tile
the smallest labels are 7.3px. The screen reads as *shape* — a session table
with colour-coded rows — rather than as data at anything below full size. It is
the one preview whose value IS the data, so it wants a full-width tile or a
link to the full-size render; that is a website decision, left to Julian.

---

## One canvas for every preview, and the empty space on the short screens is accepted — 2026-08-16

Decided by Julian, reversing a change made the day before. `consent_lab.html`
had been moved to a **1152x648** canvas while the other screens stayed on
1920x1080. The reason was real: the shipped lab consent copy is genuinely short
(242px of content against ~700px for an instructions step) and floated in a
white void, and because `base.css` caps type at 19px from roughly 800px of width
upward, a smaller canvas shrinks the 88vh card while the text stays put — so the
copy fills more of it.

**What that missed is that the screens are shown side by side.** A tile scales
its canvas by `tile_width / canvas_width`, so the smaller canvas was scaled UP
1920/1152 = **1.67x** more than its neighbours: the same tile size, half again
the apparent text size. Julian saw it in the grid and chose the void. So the
canvas is now ONE constant for every screen, and **the empty space on the short
screens is the accepted outcome** — the shipped consent page really is that
short, and consistent scale across the grid matters more than a filled frame.

**The rejected alternative is the important half:** do *not* pad or lengthen the
consent copy to fill the frame. This preview goes on the website as what the
template produces, so it carries the literal shipped copy — a fuller consent
page here would be a picture of a study nobody ran, and a disclaimer in a file
header is invisible to somebody looking at the picture. (Same reasoning as the
INVENTED/TRIMMED notes on the entry above; those two departures are stated on
the artefacts because they could not be avoided. This one can be, so it is.)

**Why a constant and not a table of overrides that happen to agree:** the
uniformity *is* the decision, so it is expressed as something that cannot vary.
`check_site_previews.py` **imports** the constant rather than restating it —
one fact, one place, per `CLAUDE.md`'s two-implementations rule.

**Enforced:** `scripts/site_previews/check_site_previews.py` now also measures
the scale factor each tile applies and fails if the screens disagree by more
than 0.005. No per-screen assertion could catch this — every screen filled its
own tile perfectly on either canvas; the fault existed only *between* them.
Measured 2026-08-16 at four 16:9 sizes: all five screens report canvas
1920x1080 and identical scales (1.000 / 0.667 / 0.500 / 0.375), and the consent
screen renders complete with overflow +0 and its card inside the canvas.
