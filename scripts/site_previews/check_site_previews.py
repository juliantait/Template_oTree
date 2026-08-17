#!/usr/bin/env python3
"""
check_site_previews.py
======================

MEASURE the six website previews built by `build_site_previews.py`.

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
     must be the generator's CANVAS (1920x1080) whatever the outer iframe
     measures, which is the whole point of the nested frame (see the
     generator's header). The size is imported from the generator, not
     restated, so the two cannot drift apart.
  6. EVERY SCREEN RENDERS AT THE SAME SCALE IN A GIVEN TILE. The site shows
     these side by side in equally sized iframes, and a screen on a smaller
     canvas is scaled UP more than its neighbours — it fills its own tile
     perfectly and still looks wrong in the grid, so no per-screen check can
     catch it. The measured factors are printed as well as asserted.
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

import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

# The repo root comes from the ONE marker-walking helper rather than a
# level count — see scripts/tests/_repo.py for why. `tests` is a SIBLING
# of this directory; that is a fact about scripts/, not an assumption
# about how far the repo root is.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _repo import REPO_ROOT  # noqa: E402
from build_site_previews import CANVAS  # noqa: E402
from monitor_session import ROWS as MONITOR_ROWS  # noqa: E402

REPO = pathlib.Path(REPO_ROOT)
OUT = REPO / '_ai/site_previews'

# The canvas every screen is composed on, IMPORTED from the generator rather
# than restated here: it is one fact, and a second copy of it drifts silently —
# the check would go on asserting the old number against a rebuilt file, or
# worse, agree with itself while the outputs changed underneath.
#
# Asserting it is still real work, because what is measured is the RENDERED
# viewport inside the nested frame, not the constant. That frame's whole job is
# to give the screen the viewport it was composed for whatever size the site's
# iframe is; if that stops being true the layout silently becomes a different
# one. And since one canvas now serves every screen, this is also what proves
# the tiles share a scale: same canvas + same tile = same scale factor.
WANT_CANVAS = '%dx%d' % CANVAS
IFRAME_SIZES = [(1920, 1080), (1280, 720), (960, 540), (720, 405)]
FILES = ['welcome_lab.html', 'consent_lab.html', 'instructions.html',
         'game.html', 'results_lab.html', 'monitor.html']

# WHICH SCREENS MAY NEVER NAME PROLIFIC. Not "the ones ending _lab.html": the
# monitor preview is a LAB session too (see monitor_session.py — the lab profile
# is what decides which states can appear on it), and it is exactly the screen
# where a stray Prolific string would be easiest to miss, because the dashboard
# renders both modalities from one implementation.
LAB_SCREENS = {'welcome_lab.html', 'consent_lab.html', 'results_lab.html',
               'monitor.html'}

# THE MONITOR'S PRESENCE CHECK. Its rows are produced by the dashboard's own
# JavaScript at BUILD time and then frozen (see build_site_previews.build_monitor),
# so the way this preview fails is not a crash — it is a table that came out
# empty, or a paint caught before the pills were drawn. Both look fine at
# thumbnail size and neither trips a geometry assertion. The row count is
# imported from the fixture rather than typed; the marks below are the states
# that fixture exists to demonstrate, so their absence means the freeze caught a
# page that was not finished rendering.
MONITOR_MARKS = {
    '.tl .marker': 'timeline markers',
    '.tl .marker.done-marker': 'the ✓ done marker on a finished row',
    'tr.finished-row': 'green finished rows',
    'tr.stalled': 'amber stalled rows',
    'tr.entry-only': 'dimmed not-arrived rows',
    '.spill-finished': 'the finished pill',
    '.spill-stall': 'the timing pill',
    '.spill-nonsepa': 'the Non-SEPA condition pill',
    '.quizcell.q-green': 'a passed quiz cell',
    '.quizcell.q-red': 'a quiz cell at the failure limit',
    '.quizcell.q-forced': 'a force-advanced quiz cell',
    '.quizcell .fillbar': 'a filling quiz cell',
    '.pill-earn': 'earnings pills',
    '.pill-live': 'a live intro timer',
    '.code-fallback': 'the unlabelled row falling back to its code',
    '.dash-summary .sum-item': 'the averages strip under the table',
}


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
  // TWO PAGE SHAPES, and they are not the same measurement dressed up.
  // A PARTICIPANT screen is a card floating on a ground, with its own inner
  // scroll region: "cut off" means that region overflows. The MONITOR is the
  // operator's full-bleed table — no card, no inner scroller — so its frame is
  // the table itself and "cut off" means the DOCUMENT outgrew the canvas,
  // which the shell cannot show because a fixed canvas has nothing to scroll.
  // That case is caught by pageScroll below, and it is not hypothetical: at
  // twenty rows the averages strip fell 2px past the bottom edge.
  const card = q('.screen-card') || q('table.dash');
  // the instructions page scrolls its slide body, every other page scrolls
  // .experimental-content (see the scroll-chain note in instructions.css)
  const scroller = q('.instruction-wrapper') || q('.experimental-content')
                || document.scrollingElement;
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
    // Monitor only; empty on every other screen, which have no #rows tbody.
    rowCount: document.querySelectorAll('#rows tr').length,
    marks: __MARKS__.map(s => document.querySelectorAll(s).length),
  };
}""".replace('__MARKS__', json.dumps(list(MONITOR_MARKS)))


def main():
    fails = []
    scales = {}   # iframe size -> {screen: measured scale factor}
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
                    if m['view'] != WANT_CANVAS:
                        fails.append('%s: canvas viewport is %s, not %s'
                                     % (tag, m['view'], WANT_CANVAS))
                    # THE SCALE THE TILE APPLIES, which is the reason the canvas
                    # is uniform: the site shows these side by side, so two
                    # screens at one tile size must be scaled identically or one
                    # renders larger than its neighbours. Measured off the
                    # rendered box rather than computed from the constant.
                    scales.setdefault((w, h), {})[name] = box[0] / CANVAS[0]
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
                    # THE MONITOR ACTUALLY RENDERED. Its rows are the dashboard's
                    # own JavaScript output, frozen at build time — so the
                    # failure to guard against is a preview built from a paint
                    # that had not happened yet: an empty table, or rows without
                    # their pills. Neither trips a geometry check and neither is
                    # visible at thumbnail size, which is where this file is
                    # mostly looked at.
                    if name == 'monitor.html':
                        if m['rowCount'] != len(MONITOR_ROWS):
                            fails.append('%s: %d participant rows, expected %d'
                                         % (tag, m['rowCount'], len(MONITOR_ROWS)))
                        for sel, n in zip(MONITOR_MARKS, m['marks']):
                            if not n:
                                fails.append('%s: nothing matched %s — %s missing'
                                             % (tag, sel, MONITOR_MARKS[sel]))
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
                    if name in LAB_SCREENS and 'prolific' in m['text'].lower():
                        fails.append('%s: a LAB screen names Prolific in visible text' % tag)
                    page.close()
        browser.close()

    # THE GRID CHECK. Every screen sits in an equally sized tile on the site, so
    # the scale factors at a given tile size must AGREE — this is what a viewer
    # sees as "that one is bigger than the others", and it is not visible in any
    # per-screen assertion above, because each screen fills its own tile
    # perfectly whatever canvas it was composed on. Reported as well as
    # asserted: the numbers are the evidence that the tiles match.
    print()
    print('measured scale factor per tile size (tile width / canvas width):')
    for (w, h), by_screen in scales.items():
        spread = max(by_screen.values()) - min(by_screen.values())
        print('  %4dx%-4d  %s' % (w, h, '  '.join(
            '%s %.3fx' % (n.replace('.html', ''), s) for n, s in by_screen.items())))
        if spread > 0.005:
            fails.append('tile %dx%d: screens render at DIFFERENT scales (spread %.3f) — %s'
                         % (w, h, spread, by_screen))

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
