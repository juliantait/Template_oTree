#!/usr/bin/env python3
"""MEASURED render check for the NEW bot-detection participant surfaces.

A layout/visibility regression produces no error and no failing HTTP test — the
participant just gets a broken page — so the new surfaces get a real headless
Chromium pass at three viewports, asserting on MEASURED element geometry (not a
look). Covers:

  * the DOT-BI gate (before/dot_bi.html): the animated challenge is visible and
    fits the viewport (no horizontal overflow), the answer input and submit are
    visible, and the no-JS fallback is hidden once dot_bi.js has run. Belt to the
    opaque-id guard: the hidden number is absent from the rendered DOM.
  * the shared NeutralReturn ending (outro/neutral_return.html): the RETURN
    button is visible, above the fold on a laptop, and a real tap target, with
    the no-punishment message on screen.
  * the results-stage checkbox honeypot (ON the terminal outro/Results.html):
    the "Completed" checkbox is visible AND the no-JS completion link is intact.

It POSITIONS a participant on each page over real HTTP (requests), then renders
that page URL in Chromium (oTree addresses participant pages by code in the URL,
so no cookie juggling). Point it at a running PRODUCTION server:

    OTREE_PRODUCTION=1 OTREE_ADMIN_PASSWORD=admin otree prodserver 8000
    python scripts/tests/bot_render_check.py http://localhost:8000

Setup (headless Chromium): docs/headless_chromium_recipe.md. Exit 0 = all checks.
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402,F401
from http_flow_test import FormParser, build_payload  # noqa: E402
from quiz_answers import CORRECT as QUIZ_CORRECT  # noqa: E402
import bot_walker  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

_failures = []
SHOTS = os.path.join(REPO_ROOT, '_ai', 'render_check')
VIEWPORTS = [('laptop', 1280, 720), ('desktop', 1440, 900), ('phone', 390, 844)]


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        _failures.append(msg)


def section(t):
    print(f"\n=== {t} ===")


def _new_prolific(base):
    r = requests.post(base + '/api/sessions',
                      json={'session_config_name': 'prolific', 'num_participants': 3}).json()
    return r['code'], requests.get(r['session_wide_url'], allow_redirects=True)


def walk_to(base, stop_page, dotbi='correct'):
    """Position a fresh prolific participant so `stop_page` is the current page;
    return the requests.Session and the final response (its .url is the page)."""
    s = requests.Session()
    r = requests.post(base + '/api/sessions',
                      json={'session_config_name': 'prolific', 'num_participants': 3}).json()
    resp = s.get(r['session_wide_url'], allow_redirects=True)
    for _ in range(40):
        path = resp.url.split('/p/')[-1]
        page = path.split('/')[2] if '/p/' in resp.url and len(path.split('/')) > 2 else None
        if page == stop_page:
            return s, resp
        fp = FormParser(); fp.feed(resp.text)
        if not fp.found_form:
            return s, resp
        overrides = {}
        code = resp.url.split('/p/')[-1].split('/')[0]
        if page == 'DotBiGate' and dotbi != 'correct':
            overrides = bot_walker.dotbi_from_variant(
                next((f['value'] for f in fp.inputs if f.get('name') == 'bot_dotbi_variant'), ''),
                correct=False)
        # Seed the correct quiz answers so a walk PAST the quiz (e.g. to the
        # Results page) completes instead of failing comprehension.
        payload = build_payload(fp.inputs, overrides, dict(QUIZ_CORRECT))
        resp = s.post(resp.url, data=payload, allow_redirects=True)
    return s, resp


def geom(page, selector):
    return page.evaluate(
        """(sel) => { const e = document.querySelector(sel);
             if (!e) return null; const r = e.getBoundingClientRect();
             const cs = getComputedStyle(e);
             return {x:r.x,y:r.y,w:r.width,h:r.height,
                     vis: cs.display!=='none' && cs.visibility!=='hidden' && r.width>0 && r.height>0};
        }""", selector)


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
    os.makedirs(SHOTS, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])

        # ---- DOT-BI gate --------------------------------------------------
        section('DOT-BI gate — challenge visible & fits, fallback hidden (JS ran)')
        _, resp = walk_to(base, 'DotBiGate')
        dot_url = resp.url
        # Belt to the opaque-id guard: the hidden number must not be in the DOM.
        code = dot_url.split('/p/')[-1].split('/')[0]
        answer = bot_walker.DOT_BI.answer_for(bot_walker.DOT_BI.choose_variant(code))
        for name, w, h in VIEWPORTS:
            pg = browser.new_page(viewport={'width': w, 'height': h})
            pg.goto(dot_url, wait_until='networkidle')
            pg.wait_for_timeout(300)
            img = geom(pg, '.dotbi-image')
            inp = geom(pg, '#bot_dotbi_answer')
            sub = geom(pg, '.dotbi-challenge input[type=submit]')
            fb = geom(pg, '.dotbi-nojs')
            body_scroll = pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            pg.screenshot(path=os.path.join(SHOTS, f'dotbi_{name}.png'))
            check(img and img['vis'], f'[{name}] the animation is visible')
            check(img and img['x'] >= -1 and (img['x'] + img['w']) <= w + 1,
                  f'[{name}] the animation fits within the viewport width ({w}px)')
            check(inp and inp['vis'], f'[{name}] the answer input is visible')
            check(sub and sub['vis'], f'[{name}] the submit button is visible')
            check(bool(fb) and not fb['vis'],
                  f'[{name}] the no-JS fallback is HIDDEN once dot_bi.js ran')
            check(body_scroll, f'[{name}] the page does not scroll horizontally')
            check(str(answer) not in pg.content(),
                  f'[{name}] the hidden number ({answer}) is not in the rendered DOM')
            pg.close()

        # ---- NeutralReturn ------------------------------------------------
        section('NeutralReturn — RETURN button visible, above fold, a tap target')
        _, resp = walk_to(base, 'NeutralReturn', dotbi='wrong')
        nr_url = resp.url
        check('NeutralReturn' in nr_url, f'a wrong DOT-BI answer lands on NeutralReturn ({nr_url.split("/p/")[-1]})')
        for name, w, h in VIEWPORTS:
            pg = browser.new_page(viewport={'width': w, 'height': h})
            pg.goto(nr_url, wait_until='networkidle')
            btn = geom(pg, '.button-row a.next-button')
            pg.screenshot(path=os.path.join(SHOTS, f'neutral_return_{name}.png'))
            check(btn and btn['vis'], f'[{name}] the RETURN button is visible')
            check(btn and btn['h'] >= 36,
                  f'[{name}] the RETURN button is a real tap target (h={btn and round(btn["h"])}px >= 36)')
            check(btn and btn['y'] < h,
                  f'[{name}] the RETURN button is above the fold (y={btn and round(btn["y"])} < {h})')
            check('no penalty' in pg.inner_text('body').lower(),
                  f'[{name}] the no-punishment message is on screen')
            pg.close()

        # ---- Results-stage checkbox honeypot (ON the terminal Results page) ----
        section('Results checkbox honeypot — the "Completed" checkbox is visible on Results')
        _, resp = walk_to(base, 'Results')
        res_url = resp.url
        check('Results' in res_url, f'reached the terminal Results page ({res_url.split("/p/")[-1]})')
        for name, w, h in VIEWPORTS:
            pg = browser.new_page(viewport={'width': w, 'height': h})
            pg.goto(res_url, wait_until='networkidle')
            box = geom(pg, '#results_completed')
            # The no-JS completion link must remain intact ON this terminal page.
            link = geom(pg, '.button-row a.next-button')
            pg.screenshot(path=os.path.join(SHOTS, f'results_honeypot_{name}.png'))
            check(box and box['vis'], f'[{name}] the "Completed" checkbox is visible on Results')
            check(link and link['vis'],
                  f'[{name}] the no-JS "Back to Prolific" completion link is still on Results')
            pg.close()

        browser.close()

    print("\n=== SUMMARY ===")
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for m in _failures:
            print(f"    - {m}")
        return 1
    print(f"  ALL CHECKS PASSED (screenshots in {SHOTS})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
