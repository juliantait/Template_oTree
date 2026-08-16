#!/usr/bin/env python3
"""
build_site_previews.py
======================

Build the five screen previews shown on the academic website.

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
Five standalone files in `_ai/site_previews/` (gitignored — they are build
ARTEFACTS, this script and `bodies/` are the source):

    welcome_lab.html     the LAB GATE (before/startpage.html) — sparse by design
    consent_lab.html     the shared consent page AS THE LAB RESOLVES IT
                         (implicit consent: no consent control on screen)
    instructions.html    one representative instruction step, with its pager
    game.html            an INVENTED stag-hunt decision screen (see below)
    results_lab.html     the lab variant of the results screen

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
    none (standard library only)
"""

import base64
import html
import pathlib
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

# --- THE CANVAS, AND WHY IT IS PER SCREEN ------------------------------------
# Each screen is drawn on a fixed canvas and scaled into the site's iframe (see
# the header). TWO RULES DECIDE THE NUMBERS, and the second one is a real
# constraint rather than a preference:
#
#   1. THE CANVAS MUST BE 16:9. The shell scales by WIDTH
#      (`calc(100vw / canvas-width)`), so a canvas of any other aspect leaves a
#      band of bare background along the bottom of a 16:9 iframe. Height is not
#      free: pick the width, and 16:9 fixes the height.
#   2. A SMALLER CANVAS MAKES THE CONTENT LOOK BIGGER. Type is capped at 19px by
#      base.css's clamp() from roughly 800px of width upward, so shrinking the
#      canvas shrinks the CARD (88vh) while the text stays the same size — the
#      content therefore fills more of the card. That is the lever used below.
#
# THE COST, STATED RATHER THAN HIDDEN (Julian, 2026-08-15): screens on different
# canvases render at different apparent text sizes when scaled into
# same-sized iframes. consent_lab sits on a 1152-wide canvas against 1920 for
# the rest, so its text renders 1920/1152 = 1.67x larger in a tile of the same
# width. There is no single canvas that suits every screen — the shipped
# consent page carries 242px of copy where the instructions step carries ~700px,
# a threefold spread — so the choice is: one canvas and the sparse screens float
# in a void, or one canvas per screen and the tiles differ in zoom. This picks
# the second. If the website shows the five side by side and the mismatch reads
# badly, the fix is to put them all back on 1920x1080 and accept the void on
# the two short screens, NOT to pad the copy: what these screens show has to be
# what the template produces.
DEFAULT_CANVAS = (1920, 1080)
CANVASES = {
    # MEASURED 2026-08-15, shipped copy, at each candidate 16:9 canvas
    # (content / region / headroom, and the same content under a substituted
    # serif, since these files render on a visitor's machine with their fonts):
    #     1920x1080   262 / 622 / 360      serif 293   — the void Julian saw
    #     1440x810    242 / 466 / 224      serif 273
    #     1280x720    242 / 387 / 145      serif 273
    #     1152x648    242 / 328 /  86      serif 273   <- chosen: 74% filled,
    #                                                     55px clear under serif
    #     1024x576    242 / 268 /  26      serif 273   — OVERFLOWS under serif
    'consent_lab.html': (1152, 648),
}


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


def main():
    # THE SAME TWO FILES A REBRAND REPLACES (README, "Rebranding a copied
    # study"). Named by ROLE, never by institution, so a copied study that
    # swaps its marks gets correct previews without touching this script.
    logo_university = data_uri('university_logo.jpg')
    logo_lab = data_uri('lab_logo.jpg')

    OUT.mkdir(parents=True, exist_ok=True)
    for name, title, sheets, note in SCREENS:
        body = (BODIES / name.replace('.html', '.body.html')).read_text()
        body = (body.replace('__LOGO_UNIVERSITY__', logo_university)
                    .replace('__LOGO_LAB__', logo_lab))
        inner = INNER.format(title=title, css=css(*sheets), body=body)
        cw, ch = CANVASES.get(name, DEFAULT_CANVAS)
        page = OUTER.format(title=title, srcdoc=html.escape(inner, quote=True),
                            note=note, cw=cw, ch=ch)
        (OUT / name).write_text(page)
        print('%-22s %8.1f kB  canvas %dx%d  ->  %s'
              % (name, len(page) / 1024, cw, ch, OUT / name))


if __name__ == '__main__':
    main()
