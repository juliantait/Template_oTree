#!/usr/bin/env python3
"""
build_site_previews.py
======================

Build the six screen previews shown on the academic website.

WHAT THIS IS FOR, AND WHY IT IS TRACKED
---------------------------------------
The website shows what a participant sees. Those screens were previously
hand-written one-off HTML snapshots, and that is exactly why they went stale:
there was no way to rebuild them, so when the shared CSS moved they silently
stopped representing the study and nobody could tell by looking. This script is
the rebuild path. It exists so the previews are DERIVED from the template
rather than drawn to look like it.

**RE-RUN IT WHENEVER `_static/global/css/` CHANGES** (and after any edit to the
components these screens use: the card, the header, the buttons, the
multiple-choice options, the payoff matrix, the results table). Nothing fails
when you don't — the outputs simply go quietly out of date, which is the whole
defect this replaces.

WHAT IT PRODUCES
----------------
Six standalone files in `_ai/site_previews/` (gitignored — they are build
ARTEFACTS, this script, `bodies/` and `monitor_session.py` are the source):

    welcome_lab.html     the LAB GATE (before/startpage.html) — sparse by design
    consent_lab.html     the shared consent page AS THE LAB RESOLVES IT
                         (implicit consent: no consent control on screen)
    instructions.html    one representative instruction step, with its pager
    game.html            an INVENTED stag-hunt decision screen (see below)
    results_lab.html     the lab variant of the results screen
    monitor.html         the EXPERIMENTER MONITOR over an invented lab session
                         — the one screen nobody in the study ever sees

THE FIRST FIVE ARE PARTICIPANT SCREENS AND ARE BUILT FROM `bodies/`; THE SIXTH
IS BUILT DIFFERENTLY, and it has to be — see BUILDING THE MONITOR below.

EVERY SCREEN MUST BE THE PROFILE AS RESOLVED, NOT AS REMEMBERED. Both lab
screens were built wrong first time by inventing config values (an explicit
consent radio the lab profile switches OFF, a fee sentence that ships off), and
neither error is visible without opening settings.py: the page renders
beautifully either way. Read the profile in `settings.RECRUITMENT_PROFILES`
before writing a body, and say in the body which flags produced what is on it.

THEY ARE WEBSITE DISPLAY MATERIAL, NOT PARTICIPANT-FACING. Nothing here is
served to a participant, nothing here is wired to oTree, and none of it may be
added to `before/`, `intro/`, `main/` or `outro/`. In particular `game.html` is
a plausible dummy: **this template ships no game screen** (`main/game.html` is a
one-line placeholder), so copying the invented screen back into the app would
be inventing an experiment.

HOW EACH FILE IS SELF-CONTAINED
-------------------------------
Each output is ONE .html file with no external reference of any kind — no
stylesheet link, no font, no script, no image by URL — because it is loaded in
an iframe on a static site with no access to this repository. The stylesheets
are inlined VERBATIM from `_static/global/css/` (never re-typed here, which is
what keeps the previews honest), and the institutional marks are embedded as
data URIs.

THE FIXED CANVAS, and why the page is drawn inside a nested srcdoc iframe
------------------------------------------------------------------------
The template's layout is driven by viewport units — the card is 88vh tall, its
padding and type scale are vw-based, and base.css has a `max-height: 820px`
branch that tightens the rhythm on a short screen. So "what the template looks
like" is only well defined AT A GIVEN SCREEN SIZE. These files are shown in a
16:9 iframe of unknown pixel size; rendered directly, a small iframe would be a
different (and clipped) layout from a large one.

So the screen is drawn on a fixed 1920x1080 canvas — an ordinary participant
display — and that canvas is scaled to whatever 16:9 box the site gives it. The
canvas has to be a nested browsing context, because vh/vw resolve against the
VIEWPORT: inside the srcdoc iframe the viewport is 1920x1080 whatever the outer
iframe measures, so every clamp() and vh in the real stylesheets resolves
exactly as it does for a participant on a 1080p screen. The scale is
`calc(100vw / 1920px)` — a length divided by a length is a plain number in CSS
Values 4 — so no script is involved and the page cannot fail to scale because
scripts are blocked.

The ONLY hand-written CSS in the output is the seven-line shell below. It
styles the canvas, never the screen: everything inside the frame is the
template's own stylesheets, untouched.

BUILDING THE MONITOR, AND WHY IT NEEDS A BROWSER
------------------------------------------------
`monitor.html` cannot be written as a body file, because the experimenter
monitor's rows are not markup anywhere. `experimenter_dashboard.py` serves a
shell whose `<tbody>` says `Waiting for first data…`, and every row, marker,
pill and quiz cell is built by that same file's `renderRow` / `stateHTML` /
`timelineHTML` — in JavaScript, from the poll's JSON. Hand-writing those rows
here would be a SECOND IMPLEMENTATION of renderRow, drifting silently from the
first (`CLAUDE.md`, the inverted collapsed-distinction rule).

So the monitor preview is built by RUNNING THE REAL PAGE: the dashboard's own
`_PAGE_HTML` — its stylesheet, its script, its header cells, its step list, all
imported rather than copied — is loaded in headless Chromium with `fetch`
stubbed to return the invented session in `monitor_session.py`, and the DOM it
paints is then FROZEN into static HTML with every `<script>` removed. The result
is markup the dashboard itself produced, that needs no server and no JavaScript
to display.

That makes this one screen depend on Playwright + Chromium at BUILD time (the
five participant screens still build on the standard library alone, and the
check step has always needed a browser anyway). The recipe for running Chromium
here without root is `docs/headless_chromium_recipe.md`. Freezing is what buys
the no-JavaScript guarantee the other five have for free — a website visitor
with scripts blocked must not be shown an empty table.

CHECKING THE OUTPUT
-------------------
Writing the files proves nothing — a layout fault here produces no error and no
failing test. Render them and MEASURE: the canvas must not overflow, the card's
scroll region must not be cut off, no request may leave the page, and the
composition must hold with JavaScript disabled. The house recipe for driving
headless Chromium without root is `docs/headless_chromium_recipe.md`.

Usage:
    python3 scripts/site_previews/build_site_previews.py
Dependencies:
    the five participant screens: none (standard library only)
    monitor.html: Playwright + Chromium, for the reason given above
"""

import base64
import html
import json
import pathlib
import re
import sys

# The repo root comes from the ONE marker-walking helper rather than a
# level count — see scripts/tests/_repo.py for why. `tests` is a SIBLING
# of this directory; that is a fact about scripts/, not an assumption
# about how far the repo root is.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))
from _repo import REPO_ROOT  # noqa: E402

REPO = pathlib.Path(REPO_ROOT)
CSS = REPO / '_static/global/css'
IMG = REPO / '_static/global/images'
BODIES = pathlib.Path(__file__).resolve().parent / 'bodies'
OUT = REPO / '_ai/site_previews'

# --- THE CANVAS: ONE SIZE, THE SAME FOR EVERY SCREEN -------------------------
# Each screen is drawn on this fixed canvas and scaled into the site's iframe
# (see the header). THE NUMBER IS NOT FREE-FLOATING — two facts pin it:
#
#   1. THE CANVAS MUST BE 16:9. The shell scales by WIDTH
#      (`calc(100vw / canvas-width)`), so a canvas of any other aspect leaves a
#      band of bare background along the bottom of a 16:9 iframe. Pick the
#      width and 16:9 fixes the height.
#   2. IT MUST BE THE SAME FOR EVERY SCREEN, because the site shows them side by
#      side in equally sized tiles. The scale a tile applies is
#      tile_width / canvas_width, so a screen on a smaller canvas is scaled UP
#      more than its neighbours and renders larger at the same tile size.
#
# THIS WAS TRIED THE OTHER WAY AND REVERSED — the reasoning is the useful part.
# A smaller canvas makes content look bigger: type is capped at 19px by
# base.css's clamp() from roughly 800px of width upward, so shrinking the canvas
# shrinks the CARD (88vh) while the text stays the same size, and the copy
# therefore fills more of the card. consent_lab was put on 1152x648 for exactly
# that reason, because the shipped lab consent copy is genuinely short (242px of
# content where the instructions step carries ~700px) and floated in a white
# void on 1920x1080. MEASURED 2026-08-15, shipped copy, at each candidate 16:9
# canvas (content / region / headroom, and the same content under a substituted
# serif, since these files render on a visitor's machine with their fonts):
#
#     1920x1080   262 / 622 / 360      serif 293   — the void
#     1440x810    242 / 466 / 224      serif 273
#     1280x720    242 / 387 / 145      serif 273
#     1152x648    242 / 328 /  86      serif 273   — 74% filled
#     1024x576    242 / 268 /  26      serif 273   — OVERFLOWS under serif
#
# JULIAN SAW THE RESULT IN THE SITE GRID AND DECIDED AGAINST IT (2026-08-16):
# 1152 against 1920 is a 1.67x difference in apparent size, and that one tile
# rendering half again as large as its neighbours reads worse than the void
# does. So every screen is back on 1920x1080 and THE VOID ON THE SHORT SCREENS
# IS THE ACCEPTED OUTCOME — the shipped consent page really is that short.
#
# THE REJECTED ALTERNATIVE, so nobody re-proposes it: do NOT pad or lengthen the
# consent copy to fill the frame. These screens go on the website as what the
# template produces, so they must carry the LITERAL SHIPPED COPY; a preview that
# invents a fuller consent page is a picture of a study nobody ran, and no file
# header disclaims what somebody sees in the picture.
#
# It is therefore ONE constant and not a per-screen table. A table of overrides
# that all happen to hold the same value is an invitation to differ again; the
# uniformity is the decision, so it is expressed as something that cannot vary.
# check_site_previews.py IMPORTS this rather than restating it — it is the same
# fact, and two copies of one fact drift.
CANVAS = (1920, 1080)


def data_uri(name):
    raw = (IMG / name).read_bytes()
    return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')


def css(*names):
    parts = []
    for n in names:
        parts.append('/* ===== %s — verbatim from _static/global/css/ ===== */' % n)
        parts.append((CSS / n).read_text())
    return '\n\n'.join(parts)


# The page a participant would see: the template's own stylesheets, inlined.
INNER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
/* The ground oTree's own page chrome would otherwise paint. */
html, body {{ margin: 0; padding: 0; background: #eef1f6; }}

{css}
</style>
</head>
<body>
{body}
</body>
</html>
"""

# The shell: a fixed canvas scaled into whatever 16:9 box the site provides.
OUTER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — oTree study template</title>
<!--
  =========================================================================
  WHAT THIS FILE IS
  =========================================================================
  A DISPLAY ARTEFACT for the academic website: one screen of the CREED oTree
  study template, shown in a 16:9 iframe. It is NOT participant-facing, it is
  not wired to anything, and it is not part of the shipped study apps.

  {note}

  =========================================================================
  HOW IT WAS MADE — do not hand-edit this file
  =========================================================================
  Generated from the live template by scripts/site_previews/build_site_previews.py.
  Hand-editing it is how the previous website snapshots went stale: edit the
  body in scripts/site_previews/bodies/ and RE-RUN THE SCRIPT instead, and
  re-run it whenever _static/global/css/ changes, or this screen quietly
  stops representing the study.

  SELF-CONTAINED BY REQUIREMENT: it is loaded on a static site with no access
  to the study repository, so there is no stylesheet link, no font, no script
  and no image by URL anywhere in this file. Every rule inside the frame
  below is copied verbatim from _static/global/css/; the two institutional
  marks are embedded as data URIs.

  WHY THE NESTED FRAME: the template sizes itself in viewport units (the card
  is 88vh; base.css tightens its rhythm below 820px of height), so the layout
  is only defined at a given screen size. The screen is therefore drawn on a
  fixed {cw}x{ch} canvas — an ordinary participant display — inside its own
  browsing context, where those units resolve as they do for a participant,
  and the canvas is scaled to fill whatever 16:9 box the page is given. The
  scale is pure CSS (a length divided by a length is a number), so it works
  with scripts disabled.
-->
<style>
/* PREVIEW SHELL — the only hand-written CSS in this file. It positions the
   canvas; it never styles the screen inside it. */
html, body {{ margin: 0; height: 100%; overflow: hidden; background: #eef1f6; }}
#screen {{
    position: absolute;
    top: 0;
    left: 0;
    width: {cw}px;
    height: {ch}px;
    border: 0;
    transform-origin: top left;
    transform: scale(calc(100vw / {cw}px));
}}
</style>
</head>
<body>
<iframe id="screen" title="{title}" srcdoc="{srcdoc}"></iframe>
</body>
</html>
"""

# WHAT A VIEWER IS OWED, PER SCREEN. Anything a viewer could mistake for the
# shipped study is stated HERE, in the artefact itself — not only in whatever
# message accompanied the hand-off, which the file outlives. Two of these
# screens carry such a note and both are load-bearing:
#   * game.html is INVENTED and is the one most likely to mislead someone into
#     thinking the template ships a game;
#   * results_lab.html is TRIMMED to fit 16:9, so a viewer can tell that what
#     they are seeing is shorter than the page a participant gets.
SCREENS = [
    ('welcome_lab.html', 'Welcome (lab)', ('base.css',),
     'THE LAB GATE (before/startpage.html) — the wait-to-be-seated hold screen an\n'
     '  experimenter advances, shown only in a lab session, and the one page in the\n'
     '  study that carries the "Welcome to [lab]" header.\n\n'
     '  IT IS MEANT TO LOOK SPARSE: one sentence and the institutional marks is the\n'
     '  whole page, and it ships with no forward button because the experimenter\n'
     '  advances the room. base.css names the lab gate as one of the short pages\n'
     '  that sits at the card\'s height floor, so the empty card is this screen\n'
     '  rendered correctly rather than a composition fault.'),

    ('consent_lab.html', 'Consent (lab)', ('base.css',),
     'THE LAB RENDERING of the shared welcome/consent page. Consent in the lab is\n'
     '  IMPLICIT — the profile sets explicit_consent=False, an ethics choice made\n'
     '  because there is an experimenter in the room — so there is no consent\n'
     '  control on screen at all, and the duration/fee sentence is off by default.\n'
     '  An earlier build of this preview showed a pre-selected "I consent" radio\n'
     '  and a fee: a screen no lab participant has ever seen. It carries no lab\n'
     '  header, because that belongs to the gate page alone.'),

    ('instructions.html', 'Instructions', ('base.css', 'instructions.css'),
     'ONE REPRESENTATIVE INSTRUCTION STEP, in the real instruction-block layout\n'
     '  with its Back / counter / Next pager. The study\'s instructions are\n'
     '  authored in intro/instructions_text.html and run to several such steps;\n'
     '  this is one of them, composed to fill the screen.'),

    ('game.html', 'Decision screen', ('base.css', 'instructions.css'),
     'THIS SCREEN IS INVENTED. **The template ships NO game screen** — main/\n'
     '  carries a one-line placeholder and nothing else — so nothing you see\n'
     '  here exists in the study apps, and no participant has ever been shown\n'
     '  it. It is a plausible stag-hunt decision page, built ONLY out of real\n'
     '  shipped components (the round-of-total progress strip, the\n'
     '  multiple-choice option cards, the payoff matrix, the card\'s button row)\n'
     '  so that the STYLING is truthful even though the task is not. Treat it as\n'
     '  an illustration of the design system, never as evidence of what the\n'
     '  template does, and do not copy it back into main/.'),

    ('results_lab.html', 'Results (lab)', ('base.css', 'results.css'),
     'THE LAB VARIANT of the results screen: the lab ending, with no Prolific\n'
     '  completion link and none anywhere on the page.\n\n'
     '  TRIMMED FOR DISPLAY, AND HERE IS WHAT WAS TRIMMED. The real page is the\n'
     '  longest in the study and genuinely SCROLLS inside its card on an\n'
     '  ordinary display — with the payoff table open it does not fit 16:9 at\n'
     '  any size. Two cuts bought the room: the unconditional "Thank you,\n'
     '  you\'re all done." greeting above the total is dropped, and a short\n'
     '  three-round session is shown rather than a full-length one. So a\n'
     '  participant sees MORE than this, and sees it a screenful at a time.\n'
     '  Everything present — the receipt and its arithmetic, the lab note, the\n'
     '  accordion, the table styling — is the page as it really renders.'),
]


MONITOR_NOTE = (
    'THE EXPERIMENTER MONITOR — the operator\'s screen, not a participant\'s.\n'
    '  It is a live view of one running session: one row per participant, a\n'
    '  six-step timeline showing where each of them is, and pills for the\n'
    '  things somebody in the room has to act on.\n\n'
    '  THE SESSION IS INVENTED. Nineteen rows, no real participant behind any of\n'
    '  them: no Prolific IDs (a Prolific row\'s label IS the platform ID), no\n'
    '  completion codes, no contact or bank details — the screen has no column\n'
    '  for any of those. The rows are in scripts/site_previews/monitor_session.py.\n\n'
    '  IT IS A LAB SESSION, AND THAT IS WHY THERE ARE NO RED "ENDED EARLY" ROWS.\n'
    '  All four terminal states (screened out, declined consent, comprehension\n'
    '  DQ, tab-monitor DQ) need a module the lab profile switches OFF, so a lab\n'
    '  monitor genuinely never shows one. An online session does; showing them\n'
    '  here would be a picture of a configuration this study does not run.\n\n'
    '  THE ROWS WERE DRAWN BY THE DASHBOARD ITSELF. This is not a mock-up of the\n'
    '  monitor: experimenter_dashboard.py\'s own JavaScript rendered every row\n'
    '  below, and the DOM it produced was then frozen so the page needs no\n'
    '  server and no scripts. The controls are therefore inert here — the live\n'
    '  screen refreshes itself every two seconds.')


def build_monitor():
    """Freeze the experimenter monitor, RENDERED BY ITS OWN JAVASCRIPT.

    The dashboard is imported, never copied: `_PAGE_HTML` already carries its
    stylesheet, its script, the header cells and the step list, all resolved
    from `STEP_LABELS` at that module's import. Only three things are changed,
    and each is a consequence of the page leaving the server:

      1. the `<link>` to base.css becomes the stylesheet INLINE — the file
         loads on a static site with no access to this repo;
      2. `fetch` is stubbed to hand back the invented session instead of
         polling `/data`, and `setInterval` is neutered so the frozen DOM is
         one deterministic paint rather than whichever tick we caught;
      3. `toLocaleTimeString` returns a fixed time, so rebuilding the preview
         does not produce a different file every run for no reason.

    Then every `<script>` is removed. What is left is the dashboard's own
    output as static markup: no server, no poll, no JavaScript — which is what
    lets this screen pass the same scripts-disabled check as the other five.
    """
    from playwright.sync_api import sync_playwright   # build-time only

    sys.path.insert(0, str(REPO))
    import experimenter_dashboard as dash             # stdlib-only at import
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import monitor_session

    live = (dash._PAGE_HTML
            .replace('<link rel="stylesheet" href="__CSS_HREF__">',
                     '<style>\n%s\n</style>' % css('base.css'))
            .replace('__SESSION_TITLE__', html.escape(monitor_session.SESSION_TITLE))
            .replace('__SESSION_CODE__', html.escape(monitor_session.SESSION_CODE))
            .replace('__DATA_URL__', 'about:blank')
            .replace('__POLL_MS__', '2000'))
    # The stub goes in the HEAD, so it is installed before the page's own
    # script (which is at the end of the body) ever runs.
    stub = """<script>
window.fetch = function () {
  return Promise.resolve({json: function () { return %s; }});
};
window.setInterval = function () { return 0; };
Date.prototype.toLocaleTimeString = function () { return '10:42:18 AM'; };
</script>""" % json.dumps(monitor_session.payload())
    live = live.replace('<html><head><meta charset="utf-8">',
                        '<html><head><meta charset="utf-8">' + stub, 1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': CANVAS[0], 'height': CANVAS[1]})
        page.set_content(live)
        # Wait for the POLL to have painted: until the first tick lands the
        # tbody still holds the shell's "Waiting for first data…" placeholder,
        # and freezing that would produce a preview of an empty dashboard that
        # looks, at thumbnail size, exactly like a working one.
        page.wait_for_function(
            '() => document.querySelectorAll("#rows tr").length > 0')
        # THE VIEW CONTROL IS TICKED BEFORE THE FREEZE (2026-08-21). The
        # dashboard now HIDES not-arrived rows by default, and this preview's
        # whole job is to show every state the monitor can display — including
        # the dimmed never-arrived row, which check_site_previews.py asserts is
        # present (MONITOR_MARKS['tr.entry-only']). The ATTRIBUTE is set as well
        # as the property, because every script is stripped below: without it
        # the frozen page would show a full table beside an UNTICKED box, which
        # is a picture of a state the live dashboard never produces.
        page.evaluate(
            "() => { const b = document.getElementById('show-not-arrived');"
            "        b.checked = true; b.setAttribute('checked', '');"
            "        b.dispatchEvent(new Event('change')); }")
        page.wait_for_function(
            '() => document.querySelectorAll("#rows tr").length === %d'
            % len(monitor_session.ROWS))
        frozen = page.evaluate('() => document.documentElement.outerHTML')
        browser.close()

    # EVERY script out: the stub, and the dashboard's own poll loop. What
    # remains has to stand up with scripts disabled, because a visitor who
    # blocks them must not be shown an empty table.
    frozen = re.sub(r'<script\b[^>]*>.*?</script>', '', frozen, flags=re.S)
    if '<script' in frozen:
        raise SystemExit('monitor: a script survived the freeze — not shippable')
    return '<!DOCTYPE html>\n' + frozen


def main():
    # THE SAME TWO FILES A REBRAND REPLACES (README, "Rebranding a copied
    # study"). Named by ROLE, never by institution, so a copied study that
    # swaps its marks gets correct previews without touching this script.
    logo_university = data_uri('university_logo.jpg')
    logo_lab = data_uri('lab_logo.jpg')

    OUT.mkdir(parents=True, exist_ok=True)
    cw, ch = CANVAS

    def write(name, title, note, inner):
        """ONE shell, ONE canvas, for every screen — the participant pages and
        the monitor alike. The monitor differs only in how its inner document
        was obtained; it must not differ in how it is framed, or it stops
        scaling like its neighbours in the site's grid (see CANVAS)."""
        page = OUTER.format(title=title, srcdoc=html.escape(inner, quote=True),
                            note=note, cw=cw, ch=ch)
        (OUT / name).write_text(page)
        print('%-22s %8.1f kB  canvas %dx%d  ->  %s'
              % (name, len(page) / 1024, cw, ch, OUT / name))

    for name, title, sheets, note in SCREENS:
        body = (BODIES / name.replace('.html', '.body.html')).read_text()
        body = (body.replace('__LOGO_UNIVERSITY__', logo_university)
                    .replace('__LOGO_LAB__', logo_lab))
        write(name, title, note, INNER.format(title=title, css=css(*sheets),
                                              body=body))

    # The monitor last: it is the only screen that needs a browser to build, so
    # a missing Chromium leaves the five participant screens already written
    # and fails with a message naming the recipe, rather than failing the whole
    # run before anything is produced.
    write('monitor.html', 'Experimenter monitor', MONITOR_NOTE, build_monitor())


if __name__ == '__main__':
    main()
