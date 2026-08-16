#!/usr/bin/env python3
"""
check_site_previews.py
======================

MEASURE the four website previews built by `build_site_previews.py`.

Why this exists next to the generator: writing those files proves nothing. A
layout fault in them produces no error and no failing test — nothing 500s,
nothing goes red, and the website just shows a broken or clipped screen. The
generator is the rebuild path; this is the evidence that a rebuild worked.
Run it after every rebuild.

What it asserts, per screen, at four 16:9 iframe sizes with JavaScript both on
and off:

  1. NO EXTERNAL REQUEST OF ANY KIND. Every request is logged; anything that is
     not the file:// document itself, its srcdoc frame or a data: URI fails the
     check. The page must render on a static site with no access to this repo.
  2. THE CANVAS IS THE ONE THE SCREEN WAS COMPOSED FOR — the frame's viewport
     must be 1920x1080 whatever the outer iframe measures, which is the whole
     point of the nested frame (see the generator's header).
  3. NOTHING IS CUT OFF: the card's scroll region must not overflow and the
     canvas must not scroll.
  4. NOTHING FLOATS IN A HUGE EMPTY CARD: the content must fill a fair share of
     the card, and the page must carry real text — an absence check alone would
     pass against a blank page.
  5. THE CANVAS FILLS THE IFRAME at every size, including with scripts off
     (the scale is CSS-only, and this is what proves it).

Prerequisites: Playwright with Chromium. On a container without root, follow
`docs/headless_chromium_recipe.md` — nine .debs into a sysroot you own plus
LD_LIBRARY_PATH — and run this with that variable set.

Usage:
    python3 scripts/site_previews/check_site_previews.py
Exit status is 0 only if every check passed.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

# The repo root comes from the ONE marker-walking helper rather than a
# level count — see scripts/tests/_repo.py for why. `tests` is a SIBLING
# of this directory; that is a fact about scripts/, not an assumption
# about how far the repo root is.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))
from _repo import REPO_ROOT  # noqa: E402

REPO = pathlib.Path(REPO_ROOT)
OUT = REPO / '_ai/site_previews'

# The canvas each screen is composed on — must match scripts/site_previews/build_site_previews.py's
# CANVASES. Asserted, because the nested frame's whole job is to give the screen
# the viewport it was composed for whatever size the site's iframe is; if that
# stops being true the layout silently becomes a different one.
CANVAS = {'consent_lab.html': '1152x648'}
DEFAULT_CANVAS = '1920x1080'
IFRAME_SIZES = [(1920, 1080), (1280, 720), (960, 540), (720, 405)]
FILES = ['welcome_lab.html', 'consent_lab.html', 'instructions.html',
         'game.html', 'results_lab.html']


# Minimum VISIBLE TEXT, per screen — the presence half of the Prolific absence
# check below (an absence check alone passes against a blank page).
#
# EXCEPTION — welcome_lab.html (the lab gate). One sentence and the
# institutional marks IS the page: it ships with no forward button, because an
# experimenter advances the room, and base.css names the gate as one of the
# short pages that sit at the card's height floor. Padding it to clear a
# generic threshold would make the preview lie about the screen, so the floor
# bends for this one file and says why.
MIN_TEXT = {'welcome_lab.html': 60}
DEFAULT_MIN_TEXT = 150

# measured INSIDE the canvas frame
MEASURE = """() => {
  const q = s => document.querySelector(s);
  const card = q('.screen-card');
  // the instructions page scrolls its slide body, every other page scrolls
  // .experimental-content (see the scroll-chain note in instructions.css)
  const scroller = q('.instruction-wrapper') || q('.experimental-content');
  const cr = card.getBoundingClientRect();
  return {
    view: window.innerWidth + 'x' + window.innerHeight,
    pageScroll: document.scrollingElement.scrollHeight - window.innerHeight,
    cardTop: Math.round(cr.top), cardBottom: Math.round(cr.bottom),
    cardW: Math.round(cr.width), cardH: Math.round(cr.height),
    viewH: window.innerHeight,
    overflow: scroller.scrollHeight - scroller.clientHeight,
    fill: Math.round(scroller.scrollHeight / cr.height * 100),
    imgsBroken: [...document.images].filter(i => !i.complete || i.naturalWidth === 0).length,
    imgCount: document.images.length,
    text: document.body.innerText.replace(/\\s+/g, ' ').trim(),
  };
}"""


def main():
    fails = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        for name in FILES:
            path = (OUT / name).as_uri()
            for i, (w, h) in enumerate(IFRAME_SIZES):
                for js in (True, False):
                    page = browser.new_page(viewport={'width': w, 'height': h},
                                            java_script_enabled=js)
                    external = []
                    page.on('request', lambda r: external.append(r.url)
                            if not (r.url.startswith('file://') or r.url.startswith('data:')
                                    or r.url.startswith('about:'))
                            else None)
                    page.goto(path)
                    page.wait_for_load_state('networkidle')
                    box = page.evaluate("""() => {
                        const r = document.getElementById('screen').getBoundingClientRect();
                        return [Math.round(r.width), Math.round(r.height),
                                Math.round(r.left), Math.round(r.top),
                                window.innerWidth, window.innerHeight];
                    }""")
                    tag = '%s @%dx%d%s' % (name, w, h, '' if js else ' (no JS)')
                    if abs(box[0] - box[4]) > 2 or abs(box[1] - box[5]) > 2 or box[2] or box[3]:
                        fails.append('%s: canvas %sx%s at (%s,%s) does not fill the %sx%s frame'
                                     % ((tag,) + tuple(box[:4]) + tuple(box[4:])))
                    m = page.frames[1].evaluate(MEASURE)
                    if js and i == 0:
                        print('%-30s canvas %s | card %dx%d y=%d..%d/%d | overflow=%+d '
                              'fill=%d%% imgs=%d broken=%d text=%d'
                              % (name, m['view'], m['cardW'], m['cardH'], m['cardTop'],
                                 m['cardBottom'], m['viewH'], m['overflow'], m['fill'],
                                 m['imgCount'], m['imgsBroken'], len(m['text'])))
                    if external:
                        fails.append('%s: EXTERNAL REQUESTS %s' % (tag, external[:3]))
                    want_canvas = CANVAS.get(name, DEFAULT_CANVAS)
                    if m['view'] != want_canvas:
                        fails.append('%s: canvas viewport is %s, not %s'
                                     % (tag, m['view'], want_canvas))
                    if m['overflow'] > 1:
                        fails.append('%s: content region overflows by %dpx (cut off)'
                                     % (tag, m['overflow']))
                    if m['pageScroll'] > 1:
                        fails.append('%s: canvas itself scrolls by %dpx' % (tag, m['pageScroll']))
                    if m['cardTop'] < 0 or m['cardBottom'] > m['viewH']:
                        fails.append('%s: card escapes the canvas' % tag)
                    if m['imgsBroken']:
                        fails.append('%s: %d broken image(s)' % (tag, m['imgsBroken']))
                    # NB `fill` is scroll-region content against card height, and
                    # the region is flex:1 — so this catches a card whose content
                    # cannot fill it, not a thin composition. Judge thinness by
                    # looking at the screenshot.
                    if m['fill'] < 45:
                        fails.append('%s: content fills only %d%% of the card' % (tag, m['fill']))
                    # An absence check needs its matching presence check: "no
                    # Prolific" passes happily against a blank page, so assert
                    # the screen has real text FIRST.
                    text_floor = MIN_TEXT.get(name, DEFAULT_MIN_TEXT)
                    if len(m['text']) < text_floor:
                        fails.append('%s: only %d characters of visible text (floor %d)'
                                     % (tag, len(m['text']), text_floor))
                    # THE LAB SCREENS MAY NEVER NAME PROLIFIC — asserted on what a
                    # viewer can actually READ (rendered innerText), not on the
                    # source, which carries the shared stylesheets' own comments.
                    if name.endswith('_lab.html') and 'prolific' in m['text'].lower():
                        fails.append('%s: a LAB screen names Prolific in visible text' % tag)
                    page.close()
        browser.close()

    print()
    if fails:
        print('FAILURES:')
        for f in dict.fromkeys(fails):
            print('  - ' + f)
        return 1
    print('all measured checks passed (%d screens x %d iframe sizes x JS on/off)'
          % (len(FILES), len(IFRAME_SIZES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
