#!/usr/bin/env python3
"""MEASURED check that the experimenter dashboard, embedded as oTree's admin
"Report" tab, grows to the full height of the viewing screen (Julian,
2026-08-23).

HOW THE DASHBOARD IS EMBEDDED (worked out before touching CSS, and what this
test reproduces). oTree's `AdminReport.html` renders, in normal document flow and
below its own chrome (the navbar, the session tab bar and the app_name /
round_number form row), `{% include user_template %}` — which is
`outro/admin_report.html`, an `<iframe>` pointing at the standalone dashboard.
At the old `height: 78vh` the whole Report page fit inside one viewport, so
nothing scrolled: the chrome was stuck at the top, the dashboard could not own
the screen, and a strip of empty page sat below the embed (made worse by the
iframe's default inline layout, which leaves a descender gap beneath it).

WHAT THE FIX MUST DELIVER, asserted here at three viewport heights:
  1. the iframe fills the viewport height (100dvh), so the dashboard owns the
     screen once the chrome is scrolled past;
  2. the page is TALLER than the viewport (chrome + full-height iframe), so the
     chrome CAN be scrolled out of the top — the thing that was impossible;
  3. no "leftover row" beneath the iframe: its container is exactly as tall as
     the iframe, which is only true when the iframe is `display: block` (an
     inline iframe leaves a few px of descender — the leftover strip).

IT READS THE REAL SHIPPED STYLE out of `outro/admin_report.html`, so the check is
of the file that actually renders, not a copy that could drift from it. Verified
at 700 / 900 / 1200px tall; a wide range because "the height of whatever screen
is viewing it" is the requirement.

Run: /home/dev/.venv-otree/bin/python scripts/tests/dashboard_embed_height_test.py
(headless Chromium; needs no server and no database).
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
_TEMPLATE = os.path.join(_APP_ROOT, 'outro', 'admin_report.html')

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def iframe_tag():
    """The REAL <iframe …> opening tag from outro/admin_report.html, with the
    templated src swapped for about:blank so it renders standalone. Fails loudly
    if the tag cannot be found — a moved iframe must break this test, not make it
    silently measure nothing."""
    html = open(_TEMPLATE, encoding='utf-8').read()
    m = re.search(r'<iframe\b[^>]*>', html, re.S)
    if not m:
        raise SystemExit('no <iframe> in outro/admin_report.html — did the embed '
                         'move? Update this test with it.')
    tag = m.group(0)
    tag = re.sub(r'src\s*=\s*"[^"]*"', 'src="about:blank"', tag)
    return tag


def wrapper_html(tag):
    """oTree's embedding, reduced to what matters for the geometry: fixed chrome
    above (its navbar + tab bar + the app_name/round_number form), then the
    iframe as the sole child of a container, in normal flow, margin:0 body."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>body{margin:0}#chrome{height:200px;background:#eee}</style>'
        '</head><body>'
        '<div id="chrome">oTree chrome: navbar, tabs, app_name/round_number</div>'
        f'<div id="host">{tag}</div>'
        '</body></html>')


def main():
    from playwright.sync_api import sync_playwright

    html = wrapper_html(iframe_tag())
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in ((1280, 700), (1512, 900), (1728, 1200)):
            pg = browser.new_page(viewport={'width': w, 'height': h})
            pg.route('**/embed', lambda r: r.fulfill(
                status=200, content_type='text/html', body=html))
            pg.goto('http://localhost/embed')
            pg.wait_for_selector('iframe', timeout=10000)
            g = pg.evaluate("""() => {
              const f = document.querySelector('iframe');
              const host = document.getElementById('host');
              return {
                ifh: f.getBoundingClientRect().height,
                hosth: host.getBoundingClientRect().height,
                inner: window.innerHeight,
                display: getComputedStyle(f).display,
                docH: document.documentElement.scrollHeight,
              };
            }""")
            # 1. the iframe fills the viewport height (100dvh).
            check(abs(g['ifh'] - g['inner']) <= 1.5,
                  f'{w}x{h}: the iframe fills the viewport height '
                  f'({g["ifh"]:.0f}px of {g["inner"]}px)')
            # 2. the page is taller than the viewport, so the chrome above the
            #    iframe CAN be scrolled out of the top (it could not before).
            check(g['docH'] > g['inner'] + 100,
                  f'{w}x{h}: the page is taller than the viewport, so the chrome '
                  f'scrolls away (doc {g["docH"]}px vs viewport {g["inner"]}px)')
            # 3. no leftover descender strip beneath the iframe: block layout
            #    makes the host exactly as tall as the iframe.
            check(g['display'] == 'block',
                  f'{w}x{h}: the iframe is display:block (no inline descender '
                  f'"leftover row") — got {g["display"]!r}')
            check(abs(g['hosth'] - g['ifh']) <= 0.5,
                  f'{w}x{h}: its container is exactly as tall as the iframe, so '
                  f'nothing is left over below it '
                  f'(host {g["hosth"]:.1f}px vs iframe {g["ifh"]:.1f}px)')
            pg.close()
        browser.close()

    print()
    if _failures:
        print(f'FAILED: {len(_failures)} check(s)')
        for f in _failures:
            print(f'  - {f}')
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
