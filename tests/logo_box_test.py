#!/usr/bin/env python3
"""THE LOGO BOX: any institution's mark, any aspect ratio, lands in one box.

WHY THIS EXISTS. The template ships two wide wordmarks and sizes them by
HEIGHT alone, which is only a "box" while every study ships the shape we do.
Once the marks became swappable by filename (2026-08-15) that stopped being
good enough: a square mark rendered 40px across against a banner's 276px, and
an EXTREME banner overshot the row, hit `max-width` and was scaled down by
width — so its height silently dropped below the 40px the strip aligns on.

**THE CLAIM UNDER TEST IS "ANY INSTITUTION CAN DROP IN THEIR OWN MARKS", AND
THE ONLY WAY TO KNOW IS TO TRY SHAPES WE DO NOT SHIP.** So this file GENERATES
real images at aspect ratios from 1:3 to 16:1, drops them into the real footer
strip and the real welcome header, renders them in headless Chromium against
the real `base.css`, and MEASURES where they land. Reasoning about the CSS is
not evidence; a rendered pixel is.

WHAT IS ASSERTED, per mark and per viewport:
  1. it fits the box — rendered height <= the box's max-height, rendered width
     <= the box's max-width;
  2. it is NOT distorted — the rendered aspect ratio matches the file's own to
     within 1%. (`object-fit: contain` is a guard here, not the mechanism: with
     width and height both `auto` the browser preserves the ratio itself.)
  3. it is NOT cropped — the whole image is inside its own border box;
  4. the strip stays INSIDE THE CARD at 375px — no sideways overflow. This is
     the measured 2026-08-11 regression (two shipped marks came to 221 + 108 +
     gap = 347px in a ~333px column and cost ~15px of the scroll region to a
     horizontal scrollbar), and the worst case here is far wider than that, so
     the row must wrap rather than widen the page.

THE EXPECTED BOX IS READ FROM THE PAGE, never hardcoded here: the test resolves
`--logo-box-h` / `--logo-box-w` (and the welcome header's pair) off the rendered
document, so retuning the box in `base.css` retunes this test with it. Two
places holding one number is the defect this repo keeps removing.

Prerequisites: Playwright with Chromium (docs/headless_chromium_recipe.md) and
Pillow. No server: the harness is built from the real stylesheet and the real
markup, which is what lets it test files the repo does not contain.

Usage:
    python3 tests/logo_box_test.py            # measure and assert
    python3 tests/logo_box_test.py --verbose  # print every measurement
Exits non-zero on any failed check.
"""

import base64
import io
import pathlib
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parent.parent
BASE_CSS = (REPO / '_static/global/css/base.css').read_text()
VERBOSE = '--verbose' in sys.argv

FAILURES = []
CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(label)
        print(f'  [FAIL] {label}')
    elif VERBOSE:
        print(f'  [ok]   {label}')


# --- the synthetic marks -----------------------------------------------------
# Shapes deliberately outside what this study ships. The two shipped marks are
# 6.90:1 and 3.37:1, so the interesting cases are a SQUARE (the shape that used
# to render at a fraction of a banner's width), a TALL PORTRAIT (height-bound
# where every shipped mark is width-bound), and an EXTREME BANNER (the one that
# used to lose its height to `max-width`).
SHAPES = [
    ('tall portrait', 120, 360),
    ('square', 200, 200),
    ('modest 3:1', 600, 200),
    ('exactly the box 7:1', 700, 100),
    ('wide banner 10:1', 1000, 100),
    ('extreme banner 16:1', 1600, 100),
]


def mark(w, h):
    """A real PNG of the given size, as a data URI. Two bands so a crop or a
    squash is visible in the screenshot as well as in the numbers."""
    img = Image.new('RGB', (w, h), (40, 70, 130))
    for y in range(h // 2, h):
        for x in range(w):
            img.putpixel((x, y), (210, 220, 240))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


FOOTER_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css}</style></head><body>
<div class="experimental-screen"><div class="screen-card narrative-card">
  <div class="experimental-header"><h2 class="header-title">Logo box harness</h2></div>
  <div class="experimental-content"><div class="section-text">Measuring the strip.</div></div>
  <div class="logo-section"><div class="logo-row">
    <img id="a" src="{a}" alt="University logo">
    <img id="b" src="{b}" alt="Research lab logo">
  </div></div>
</div></div></body></html>"""

HEADER_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css}</style></head><body>
<div class="experimental-screen"><div class="screen-card narrative-card">
  <div class="experimental-header"><div class="welcome-header-row">
    <h2 class="header-title">Welcome to</h2>
    <img id="a" src="{a}" alt="Research lab logo">
  </div></div>
  <div class="experimental-content"><div class="section-text">
    The experiment will start when everyone has taken their places.</div></div>
</div></div></body></html>"""

MEASURE = """(ids) => {
  const root = getComputedStyle(document.documentElement);
  const px = n => parseFloat(root.getPropertyValue(n));
  const out = {
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    box: {h: px('--logo-box-h'), w: px('--logo-box-w'),
          wh: px('--welcome-logo-box-h'), ww: px('--welcome-logo-box-w')},
    imgs: {},
  };
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    const r = el.getBoundingClientRect();
    const card = document.querySelector('.screen-card').getBoundingClientRect();
    out.imgs[id] = {
      w: r.width, h: r.height,
      // `max-width` is min(box, 100%), so on a narrow column the CONTAINER can
      // bind before the box does — that 100% term is the 2026-08-11 overflow
      // guard and must not read as the box failing to fill.
      parentW: el.parentElement.getBoundingClientRect().width,
      natW: el.naturalWidth, natH: el.naturalHeight,
      complete: el.complete && el.naturalWidth > 0,
      insideCardL: r.left >= card.left - 0.5,
      insideCardR: r.right <= card.right + 0.5,
    };
  }
  return out;
}"""

VIEWPORTS = [('laptop', 1280, 720), ('desktop', 1512, 1200), ('phone', 375, 667)]


def measure_page(page, html, ids):
    page.set_content(html, wait_until='load')
    return page.evaluate(MEASURE, ids)


def assert_mark(m, box_w, box_h, where, shape, vp):
    """The four guarantees, on one rendered mark."""
    tag = f'{where} @{vp} · {shape}'
    # The effective width cap: the box, or the column if the column is narrower
    # (`max-width: min(box, 100%)`).
    cap = min(box_w, m['parentW'])
    check(m['complete'], f'{tag}: the image actually loaded')
    check(m['h'] <= box_h + 0.5,
          f"{tag}: height {m['h']:.1f} <= box {box_h:.0f}")
    check(m['w'] <= cap + 0.5,
          f"{tag}: width {m['w']:.1f} <= cap {cap:.0f} "
          f"(box {box_w:.0f}, column {m['parentW']:.0f})")
    want = m['natW'] / m['natH']
    got = m['w'] / m['h'] if m['h'] else 0
    check(abs(got - want) / want < 0.01,
          f'{tag}: undistorted (ratio {got:.3f} vs {want:.3f})')
    check(m['insideCardL'] and m['insideCardR'],
          f'{tag}: sits inside the card, not cropped by its edge')
    # The mark should TOUCH whichever limit binds — otherwise it is smaller
    # than it needs to be and the box is not doing its job. Three candidates:
    # the box's height, the box's width, or the column (the 100% guard).
    touches = (abs(m['h'] - box_h) < 0.6) or (abs(m['w'] - cap) < 0.6)
    check(touches, f'{tag}: fills its binding dimension '
                   f"(h {m['h']:.1f}/{box_h:.0f}, w {m['w']:.1f}/{cap:.0f})")
    return got


def main():
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        for vp_name, w, h in VIEWPORTS:
            page = browser.new_page(viewport={'width': w, 'height': h})
            print(f'\n=== {vp_name} {w}x{h} ===')
            for shape, iw, ih in SHAPES:
                uri = mark(iw, ih)
                # FOOTER: the worst case is BOTH marks at the same extreme
                # shape, which is what a single institution supplying two
                # matching banners actually looks like.
                r = measure_page(page, FOOTER_PAGE.format(css=BASE_CSS, a=uri, b=uri),
                                 ['a', 'b'])
                box_w, box_h = r['box']['w'], r['box']['h']
                for i in ('a', 'b'):
                    got = assert_mark(r['imgs'][i], box_w, box_h, 'footer', shape, vp_name)
                m = r['imgs']['a']
                check(r['docScrollW'] <= r['docClientW'] + 0.5,
                      f'footer @{vp_name} · {shape}: NO sideways overflow '
                      f"(scrollW {r['docScrollW']} <= clientW {r['docClientW']})")
                rows.append((vp_name, shape, 'footer', iw, ih, m['w'], m['h'],
                             box_w, box_h))

                # HEADER: title + mark on one flex line.
                r2 = measure_page(page, HEADER_PAGE.format(css=BASE_CSS, a=uri), ['a'])
                bw, bh = r2['box']['ww'], r2['box']['wh']
                assert_mark(r2['imgs']['a'], bw, bh, 'header', shape, vp_name)
                check(r2['docScrollW'] <= r2['docClientW'] + 0.5,
                      f'header @{vp_name} · {shape}: NO sideways overflow '
                      f"(scrollW {r2['docScrollW']} <= clientW {r2['docClientW']})")
                rows.append((vp_name, shape, 'header', iw, ih,
                             r2['imgs']['a']['w'], r2['imgs']['a']['h'], bw, bh))
            page.close()
        browser.close()

    print('\n=== MEASURED (rendered px) ===')
    print(f"{'viewport':9} {'shape':22} {'where':7} {'file':>10}  "
          f"{'rendered':>13}  {'box':>10}  binds")
    for vp, shape, where, iw, ih, rw, rh, bw, bh in rows:
        binds = 'height' if abs(rh - bh) < 0.6 else 'width'
        binds += '' if abs(rw - bw) < 0.6 or binds == 'height' else ' (column)'
        print(f'{vp:9} {shape:22} {where:7} {f"{iw}x{ih}":>10}  '
              f'{f"{rw:.1f}x{rh:.1f}":>13}  {f"{bw:.0f}x{bh:.0f}":>10}  {binds}')

    print(f'\n=== SUMMARY ===\n  {CHECKS} checks')
    if FAILURES:
        print(f'  {len(FAILURES)} FAILED:')
        for f in FAILURES:
            print('    - ' + f)
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
