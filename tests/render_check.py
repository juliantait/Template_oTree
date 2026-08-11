#!/usr/bin/env python
"""RENDER CHECK — real headless Chromium, three viewports, measured geometry.

WHY THIS EXISTS
---------------
Bots and HTTP tests post forms; they never RENDER. "Is the card ever taller than
the screen", "does the scroll region actually scroll", "is the focus ring sliced
off by the scroll edge", "does the monitor overlay cover the viewport or is it
trapped inside the card" are all questions only a browser can answer, and every
one of them is a silent failure: nothing 500s, no test goes red, the participant
just gets a broken page. This script drives a real headless Chromium over a real
HTTP server, writes screenshots a human can flick through, and asserts on
MEASURED ELEMENT GEOMETRY rather than on HTML.

WHAT IT DOES
------------
1. Boots oTree in-process against a THROWAWAY temp database (the repo's
   db.sqlite3 is never touched) and serves it with uvicorn on a free port.
2. Walks participants to each page of interest over real HTTP, then opens THAT
   participant's page in Chromium at three viewports (short laptop, tall
   desktop, narrow phone) and writes a full-page screenshot per page/viewport to
   `_ai/render_check/`.
3. Asserts the layout contract by measurement (see CHECKS below), writing every
   number to `_ai/render_check/geometry.json` so a later change can be diffed.

CHECKS (each printed as PASS/FAIL with the numbers)
   A. the white card never touches the top or bottom of the viewport;
   B. the card stops at its max-height and the content region GENUINELY scrolls
      (a flex child without `min-height: 0` silently fails to scroll — that is
      the exact failure mode of this layout);
   C. a :focus-visible ring on the FIRST and LAST option card is not clipped by
      the scroll overflow;
   D. the tab-monitor overlay covers the whole viewport and is not trapped
      inside the scrollable card;
   plus the feature checks: option cards (bordered, selected state, whole card
   clickable), eyebrow, privacy panel, per-family text alignment, the justified
   instructions band, pill buttons + ghost variant, logo sizing from CSS,
   CREED header scoping, consent neutrality, Prolific-ID prefill, screen-out
   wording, and the self-hiding scroll shadow (measured off the pixels).

RUNNING IT (headless Chromium needs system libraries)
-----------------------------------------------------
On a box without root, unpack the library .debs into a private sysroot and point
LD_LIBRARY_PATH at it — full recipe in `_ai/headless_chromium_recipe.md`:

    pip install playwright pillow uvicorn requests && playwright install chromium
    LD_LIBRARY_PATH=/path/to/sysroot/usr/lib/x86_64-linux-gnu \
        python tests/render_check.py

The script re-runs itself once with `--long-quiz` (a deliberately overflowing
quiz) to exercise the scroll checks; pass `--long-quiz` yourself to run only
that pass. Exit code 0 = every check passed.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

LONG_QUIZ = '--long-quiz' in sys.argv

# --- throwaway database, PRODUCTION mode ------------------------------------
# LIVE-BUILD FIDELITY: the screenshots must show what a PARTICIPANT sees, so the
# whole run is in production mode — no oTree "Debug info" footer under the card,
# no "Skip quiz (testing)" button in the button row, no solutions in the page.
# The walker therefore answers the quiz from QUIZ_ITEMS instead of from the
# DEBUG-only solutions blob.
#
# The switch is presence-based, not value-based: settings.py derives DEBUG as
# `'OTREE_PRODUCTION' not in os.environ`, so OTREE_PRODUCTION='' would still
# mean production here while oTree's own default derivation calls it debug.
# Set it to '1' to be unambiguous, and pop it to run with DEBUG on.
_TMPDIR = tempfile.mkdtemp(prefix='tmpl_render_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_TMPDIR, 'db.sqlite3')}"
os.environ['OTREE_PRODUCTION'] = '1'
os.environ.setdefault('OTREE_SECRET_KEY', 'render-check')

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _APP_ROOT)
sys.path.insert(0, _TESTS_DIR)

# A LONGER QUIZ, injected BEFORE oTree loads the app models. intro.Player's quiz
# columns are generated from QUIZ_ITEMS at import, so the items must be in place
# before `otree_main.setup()`. Injecting a patched module into sys.modules under
# the submodule name is how `from .quiz_items import QUIZ_ITEMS` picks it up
# without editing the repo's own file.
if LONG_QUIZ:
    import types

    _qi = types.ModuleType('intro.quiz_items')
    with open(os.path.join(_APP_ROOT, 'intro', 'quiz_items.py')) as fh:
        exec(fh.read(), _qi.__dict__)
    _qi.QUIZ_ITEMS = list(_qi.QUIZ_ITEMS) + [
        dict(field=f'quiz_long_{i}',
             prompt=f'Filler comprehension question {i} — this item exists only '
                    f'to make the quiz longer than the card, so the scroll '
                    f'region can be measured.',
             choices=[f'Answer {i}A', f'Answer {i}B', f'Answer {i}C'],
             answer=f'Answer {i}B')
        for i in range(1, 9)
    ]
    sys.modules['intro.quiz_items'] = _qi

# CRITICAL: oTree opens the RELATIVE name 'db.sqlite3' in the CURRENT DIRECTORY
# at import time (otree/database.py: DB_FILE / sqlite_disk_conn), ignoring the
# path inside a sqlite DATABASE_URL. Import otree.database WHILE chdir'd into the
# temp dir so that connection binds to the throwaway file, then chdir back so
# '_static' and the template roots (equally CWD-relative) still resolve.
os.chdir(_TMPDIR)
import otree.database  # noqa: E402
os.chdir(_APP_ROOT)

import otree.main as otree_main  # noqa: E402
otree_main.setup()

from otree.database import engine, AnyModel, DBSession  # noqa: E402
AnyModel.metadata.create_all(engine)

import requests  # noqa: E402
import uvicorn  # noqa: E402
from otree.asgi import app  # noqa: E402
from otree.session import create_session  # noqa: E402
from otree.models import Participant, Session  # noqa: E402

from http_flow_test import FormParser, build_payload  # noqa: E402
from intro.quiz_items import QUIZ_ITEMS  # noqa: E402  (patched above in --long-quiz)

OUT_DIR = os.path.join(_APP_ROOT, '_ai', 'render_check')
os.makedirs(OUT_DIR, exist_ok=True)

PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 '
            'Mobile/15E148 Safari/604.1')

VIEWPORTS = {
    'laptop_1280x720': dict(width=1280, height=720),
    'desktop_1512x1200': dict(width=1512, height=1200),
    'phone_375x667': dict(width=375, height=667),
}

_failures = []
geometry = {}


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# --------------------------------------------------------------------------
# a REAL server (the in-process TestClient cannot serve a browser)
# --------------------------------------------------------------------------
def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    def __init__(self):
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        cfg = uvicorn.Config(app, host='127.0.0.1', port=self.port,
                             log_level='error', lifespan='on')
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self):
        self._thread.start()
        deadline = time.time() + 30
        while time.time() < deadline:
            if getattr(self._server, 'started', False):
                return
            time.sleep(0.05)
        raise RuntimeError('uvicorn did not start')

    def stop(self):
        self._server.should_exit = True
        self._thread.join(timeout=10)


# --------------------------------------------------------------------------
# HTTP walking (identical mechanics to the other tests in this folder)
# --------------------------------------------------------------------------
LAB_ANSWERS = {'age': '30', 'gender': 'Female', 'bank': 'NL91ABNA0417164300',
               'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''}
# The quiz answered from the item definitions, not from the page: in production
# the correct answers never reach the browser, which is the point.
CORRECT_QUIZ = {item['field']: item['answer'] for item in QUIZ_ITEMS}
END_TEXT = ('Back to Prolific', 'participation has ended', 'Thank you')


def anon_code(session_code):
    s = DBSession()
    try:
        return s.query(Session).filter_by(code=session_code).one()._anonymous_code
    finally:
        s.close()


def page_of(url):
    parts = urlparse(str(url)).path.strip('/').split('/')
    return parts[3] if len(parts) >= 5 and parts[0] == 'p' else None


def code_of(url):
    parts = urlparse(str(url)).path.strip('/').split('/')
    return parts[1] if len(parts) >= 3 and parts[0] == 'p' else None


def walk_to(base, session, stop, label=None, user_agent=None, limit=90):
    """Enter the session and post pages until `stop` is the current page name.

    Returns (participant_code, last_response). Entering through /join/<anon>
    (rather than a direct participant URL) is deliberate: it is the real entry
    door, and it is the only way ?participant_label= reaches oTree.
    """
    s = requests.Session()
    if user_agent:
        s.headers['User-Agent'] = user_agent
    url = f'{base}/join/{anon_code(session.code)}'
    if label is not None:
        url += f'?participant_label={label}'
    r = s.get(url, allow_redirects=True)
    answers = dict(LAB_ANSWERS, **CORRECT_QUIZ)
    for _ in range(limit):
        assert r.status_code < 500, f'HTTP {r.status_code} at {r.url}'
        if page_of(r.url) == stop:
            return code_of(r.url), r
        if any(t in r.text for t in END_TEXT) and page_of(r.url) is None:
            break
        fp = FormParser()
        fp.feed(r.text)
        if not fp.found_form:
            break
        r = s.post(r.url, data=build_payload(fp.inputs, {}, answers),
                   allow_redirects=True)
    raise AssertionError(f'never reached {stop}; stuck at {r.url}')


# --------------------------------------------------------------------------
# browser measurement helpers
# --------------------------------------------------------------------------
BOX_JS = """(sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            top: Math.round(r.top), bottom: Math.round(r.bottom),
            display: cs.display, textAlign: cs.textAlign,
            fontSize: cs.fontSize, color: cs.color,
            background: cs.backgroundColor,
            borderTopWidth: cs.borderTopWidth, borderColor: cs.borderTopColor,
            borderRadius: cs.borderTopLeftRadius,
            overflowY: cs.overflowY, minHeight: cs.minHeight,
            scrollH: el.scrollHeight, clientH: el.clientHeight,
            paddingTop: cs.paddingTop, position: cs.position};
}"""


def box(page, selector):
    return page.evaluate(BOX_JS, selector)


def viewport_of(page):
    return page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight,"
                         " scrollW: document.documentElement.scrollWidth,"
                         " scrollH: document.documentElement.scrollHeight})")


def visible_text(page):
    return page.inner_text('body')


def screenshot(page, key, viewport):
    path = os.path.join(OUT_DIR, f'{key}__{viewport}.png')
    page.screenshot(path=path, full_page=True)
    return path


# --------------------------------------------------------------------------
# the pages to render
# --------------------------------------------------------------------------
def page_specs():
    """(key, config, stop-page, kwargs) for every page we render."""
    if LONG_QUIZ:
        return [dict(key='quiz_long', config='lab', stop='quiz')]
    return [
        dict(key='lab_entry_gate', config='lab', stop='startpage'),
        dict(key='consent_lab', config='lab', stop='welcome'),
        dict(key='consent_prolific', config='prolific', stop='welcome'),
        dict(key='prolific_id', config='prolific', stop='ConfirmProlificID',
             label='PID_FROM_URL_4242'),
        dict(key='instructions', config='lab', stop='instructing'),
        dict(key='quiz', config='lab', stop='quiz'),
        dict(key='task_tabmonitor', config='prolific', stop='GameStart'),
        dict(key='results', config='prolific', stop='Results'),
        dict(key='ended_screenout', config='prolific', stop='Ended',
             modified={'mobile_screenout': 1}, user_agent=PHONE_UA),
    ]


def render_all(server, browser):
    """Render every spec at every viewport; return {key: {viewport: page-facts}}."""
    facts = {}
    for spec in page_specs():
        key = spec['key']
        section(f'RENDER {key}  ({spec["config"]} -> {spec["stop"]})')
        facts[key] = {}
        for vp_name, vp in VIEWPORTS.items():
            session = create_session(
                spec['config'], num_participants=2,
                modified_session_config_fields=spec.get('modified'))
            code, _ = walk_to(server.base, session, spec['stop'],
                              label=spec.get('label'),
                              user_agent=spec.get('user_agent'))
            context = browser.new_context(
                viewport=vp,
                user_agent=spec.get('user_agent'),
                is_mobile=False)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(150)          # let page scripts settle
            shot = screenshot(page, key, vp_name)
            facts[key][vp_name] = collect_facts(page, key)
            geometry.setdefault(key, {})[vp_name] = facts[key][vp_name]
            print(f'  wrote {os.path.relpath(shot, _APP_ROOT)} '
                  f'({facts[key][vp_name]["card"]["w"]}x'
                  f'{facts[key][vp_name]["card"]["h"]} card)')
            context.close()
    return facts


def collect_facts(page, key):
    """Every measurement we assert on, for one page at one viewport."""
    f = {
        'url_page': page_of(page.url),
        'viewport': viewport_of(page),
        'card': box(page, '.screen-card'),
        'shell': box(page, '.experimental-screen'),
        'content': box(page, '.experimental-content'),
        'header': box(page, '.experimental-header'),
        'eyebrow': box(page, '.eyebrow'),
        'title': box(page, '.header-title'),
        'panel': box(page, '.panel'),
        'button': box(page, '.next-button'),
        'ghost_button': box(page, '.next-button.ghost'),
        'logo_img': box(page, '.logo-row img'),
        'creed_header': box(page, '.welcome-header-row'),
        'first_option': box(page, '.form-check, .mc-option'),
        'section_text': box(page, '.section-text'),
        'has_creed_header': page.locator('.welcome-header-row').count() > 0,
        'logo_inline_attrs': page.evaluate(
            """() => Array.from(document.querySelectorAll('.logo-row img, '
               + '.welcome-header-row img')).map(
                   i => ({height: i.getAttribute('height'),
                          style: i.getAttribute('style'),
                          rendered: Math.round(i.getBoundingClientRect().height)}))"""),
        'text': visible_text(page)[:4000],
    }
    return f


# ==========================================================================
# CHECK A — the card never touches the top or bottom of the viewport
# ==========================================================================
def check_card_gaps(facts):
    section('A. The white card never touches the top or bottom of the viewport')
    worst = None
    for key, per_vp in facts.items():
        for vp, f in per_vp.items():
            card, shell, view = f['card'], f['shell'], f['viewport']
            # Measured inside the page SHELL (the grey background box), not
            # against the document: the shell is what paints the background, and
            # the document can be taller for reasons that are not the layout.
            top_gap = card['y'] - shell['y']
            bottom_gap = (shell['y'] + shell['h']) - (card['y'] + card['h'])
            # The shell is at least 100vh tall, so a card that fits also has a
            # real on-screen gap; assert that too where the card fits.
            on_screen = view['h'] - (card['y'] + card['h']) if card['h'] < view['h'] else None
            ok = top_gap >= 1 and bottom_gap >= 1 and (on_screen is None or on_screen >= 1)
            if worst is None or min(top_gap, bottom_gap) < worst[0]:
                worst = (min(top_gap, bottom_gap), key, vp)
            check(ok, f'{key} @ {vp}: background gap above {top_gap}px, below '
                      f'{bottom_gap}px (card {card["h"]}px in a {view["h"]}px '
                      f'viewport; on-screen bottom gap '
                      f'{"n/a" if on_screen is None else str(on_screen) + "px"})')
    if worst:
        print(f'  tightest gap anywhere: {worst[0]}px ({worst[1]} @ {worst[2]})')


# ==========================================================================
# CHECK B — the card stops at max-height and the content REALLY scrolls
# ==========================================================================
def check_scrolling(server, browser, facts):
    section('B. Card stops at max-height and the content region genuinely scrolls')
    overflowing = [(k, vp, f) for k, per in facts.items() for vp, f in per.items()
                   if f['content'] and f['content']['scrollH'] >
                   f['content']['clientH'] + 2]
    check(bool(overflowing),
          f'at least one rendered page overflows its card '
          f'({len(overflowing)} page/viewport combinations do)')
    for key, vp, f in overflowing:
        card, view, content = f['card'], f['viewport'], f['content']
        cap = 0.88 * view['h']
        check(card['h'] <= cap + 2,
              f'{key} @ {vp}: card height {card["h"]}px <= max-height '
              f'{cap:.0f}px (88vh) although its content is '
              f'{content["scrollH"]}px')
        check(content['minHeight'] in ('0px', 'auto') and content['overflowY'] == 'auto',
              f'{key} @ {vp}: content region is overflow-y:auto with '
              f'min-height:{content["minHeight"]} (must be 0px — `auto` is the '
              f'silent no-scroll failure)')
        check(content['minHeight'] == '0px',
              f'{key} @ {vp}: min-height IS 0px (the load-bearing line)')


def check_scroll_affordance(server, browser):
    """D1/D2 (2026-08-10): the affordance must be READABLE, and a partially
    visible element must look partial rather than sliced.

    Asserted off the RENDERED PIXELS, not off the CSS: the previous version of
    this layout had the gradient rules present and correct and still showed a
    hard cut, because a background can only paint behind the text.
    """
    section('D1/D2. The scroll affordance is visible and fades partial content')
    try:
        from PIL import Image
    except ImportError:
        check(False, 'Pillow is installed (needed to measure rendered pixels)')
        return
    for page_key, config, stop in (('consent_prolific', 'prolific', 'welcome'),
                                   ('quiz', 'lab', 'quiz')):
        session = create_session(config, num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        for vp_name in ('laptop_1280x720', 'phone_375x667'):
            context = browser.new_context(viewport=VIEWPORTS[vp_name])
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(250)
            st = page.evaluate("""() => {
                const el = document.querySelector('.experimental-content');
                const r = el.getBoundingClientRect();
                return {overflows: el.scrollHeight > el.clientHeight + 2,
                        gutter: el.offsetWidth - el.clientWidth,
                        cls: el.className,
                        x: r.x, y: r.y, w: r.width, h: r.height};
            }""")
            label = f'{page_key} @ {vp_name}'
            if not st['overflows']:
                print(f'  [skip] {label}: content fits, no affordance needed')
                context.close()
                continue
            check(st['gutter'] >= 8,
                  f'{label}: a scrollbar gutter is reserved '
                  f'({st["gutter"]}px, stable both-edges)')
            check('is-scrollable-down' in st['cls'],
                  f'{label}: the region is marked is-scrollable-down '
                  f'(class={st["cls"]!r})')

            def edge_row(dy, h=4):
                """Mean darkness (0 = pure card white) of a strip h px tall,
                dy px above the bottom edge of the scroll box."""
                clip = dict(x=st['x'] + 8, y=st['y'] + st['h'] - dy,
                            width=max(10, st['w'] - 26), height=h)
                path = os.path.join(OUT_DIR, '_edge.png')
                page.screenshot(path=path, clip=clip)
                img = Image.open(path).convert('L')
                px = list(img.getdata())
                os.remove(path)
                return 255 - (sum(px) / len(px))

            # …and the bar in that gutter is actually PAINTED. Reserving the
            # gutter is layout; an overlay bar that fades out when idle occupies
            # it and shows nothing, so this is measured off the pixels.
            def gutter_darkness():
                clip = dict(x=st['x'] + st['w'] - st['gutter'] / 2 - 1,
                            y=st['y'] + st['h'] / 3, width=8, height=60)
                path = os.path.join(OUT_DIR, '_gutter.png')
                page.screenshot(path=path, clip=clip)
                img = Image.open(path).convert('L')
                px = list(img.getdata())
                os.remove(path)
                return 255 - (sum(px) / len(px))

            bar = gutter_darkness()
            check(bar > 4.0,
                  f'{label}: a scrollbar is actually PAINTED in that gutter '
                  f'(darkness {bar:.2f} vs 0 for bare card white)')

            at_edge = edge_row(4)
            above = edge_row(70, h=8)
            # Scale: pure card white is 0; an unfaded line of body copy across
            # this strip measures 12-19 (see the `above` numbers). A hard-sliced
            # glyph row therefore lands in double figures, so a threshold of 3
            # separates "faded to nothing" from "cut through the middle" with an
            # order of magnitude to spare.
            check(at_edge <= 3.0,
                  f'{label}: the last 4px at the cut are faded to nothing '
                  f'(darkness {at_edge:.2f} of a 12-19 unfaded line)')
            check(above - at_edge > 6.0 or above < 3.0,
                  f'{label}: content 70px up is much darker than the faded edge '
                  f'({above:.2f} vs {at_edge:.2f})')
            # …and the fade must GO AWAY at the end, or the last line would be
            # permanently half-invisible.
            page.evaluate("""() => { const el = document.querySelector(
                '.experimental-content'); el.scrollTop = el.scrollHeight; }""")
            page.wait_for_timeout(150)
            end_cls = page.evaluate(
                "() => document.querySelector('.experimental-content').className")
            check('is-scrollable-down' not in end_cls,
                  f'{label}: at the end of the scroll the bottom fade is off '
                  f'(class={end_cls!r})')
            check('is-scrollable-up' in end_cls,
                  f'{label}: …and the TOP fade is on instead')
            geometry.setdefault('affordance', {})[label] = {
                'gutter': st['gutter'], 'darkness_at_edge': round(at_edge, 3),
                'darkness_70px_up': round(above, 3), 'class_at_end': end_cls}
            screenshot(page, f'{page_key}_scrolled_to_end', vp_name)
            context.close()


def check_no_phantom_affordance(server, browser):
    """D5 (2026-08-11): a page that FITS must draw no scroll affordance at all.

    The background gradient pair hides its own shadows by painting the card
    colour over them; when the masking gradient was only opaque for 9px of a
    16px shadow, the bottom half bled through and drew a faint band across a
    card with nothing to scroll. Asserted on the pixels of a page that fits.
    """
    section('D5. No scroll affordance is painted on a page that fits')
    try:
        from PIL import Image
    except ImportError:
        check(False, 'Pillow is installed (needed to measure rendered pixels)')
        return
    for key, config, stop, vp_name in (
            ('lab_entry_gate', 'lab', 'startpage', 'desktop_1512x1200'),
            ('lab_entry_gate', 'lab', 'startpage', 'laptop_1280x720'),
            ('quiz', 'lab', 'quiz', 'desktop_1512x1200')):
        session = create_session(config, num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        context = browser.new_context(viewport=VIEWPORTS[vp_name])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        st = page.evaluate("""() => {
            const el = document.querySelector('.experimental-content');
            const r = el.getBoundingClientRect();
            const logo = el.querySelector('.logo-section');
            return {overflows: el.scrollHeight > el.clientHeight + 2,
                    cls: el.className,
                    x: r.x, y: r.y, w: r.width, h: r.height,
                    logoTop: logo ? Math.round(
                        logo.getBoundingClientRect().top - r.top) : null};
        }""")
        label = f'{key} @ {vp_name}'
        if not check(not st['overflows'],
                     f'{label}: this page FITS (nothing to scroll)'):
            context.close()
            continue
        check('is-scrollable' not in st['cls'],
              f'{label}: no scrollable class is set ({st["cls"]!r})')

        def strip(dy, h=16):
            clip = dict(x=st['x'] + 14, y=st['y'] + dy,
                        width=max(10, st['w'] - 48), height=h)
            path = os.path.join(OUT_DIR, '_phantom.png')
            page.screenshot(path=path, clip=clip)
            img = Image.open(path).convert('L')
            px = list(img.getdata())
            os.remove(path)
            return 255 - (sum(px) / len(px))

        top_edge = strip(1)
        # A blank reference band just INSIDE the affordance's reach (a shadow
        # cannot extend past ~16px), never mid-region: on a short page the copy
        # is centred there, so a mid-region strip measures the text.
        reference = strip(34)
        # Keep clear of anything drawn at the foot (the logo strip when present).
        bottom_dy = (st['logoTop'] - 24) if st['logoTop'] else int(st['h'] - 17)
        bottom_edge = strip(max(1, bottom_dy))
        check(top_edge < 0.6,
              f'{label}: the top edge is uniform card colour '
              f'(darkness {top_edge:.2f}; a bled shadow measured ~4)')
        check(bottom_edge < 0.6,
              f'{label}: the bottom edge is uniform card colour '
              f'(darkness {bottom_edge:.2f})')
        check(abs(top_edge - reference) < 0.6,
              f'{label}: the edge matches a blank band mid-region '
              f'({top_edge:.2f} vs {reference:.2f}) — no phantom line')
        geometry.setdefault('phantom', {})[label] = {
            'top': round(top_edge, 3), 'bottom': round(bottom_edge, 3),
            'reference': round(reference, 3)}
        context.close()


def check_no_sideways_overflow(facts, server, browser):
    """Nothing may overflow horizontally — not the page, not a scroll region.

    A card whose content is wider than it is does not just look wrong: the
    scroll region grows a horizontal scrollbar, which silently eats ~15px of its
    HEIGHT (that is how the lab gate's logo strip stopped sitting at the foot).
    """
    section('O. No page or scroll region overflows sideways')
    for key, per_vp in facts.items():
        for vp, f in per_vp.items():
            view = f['viewport']
            check(view['scrollW'] <= view['w'] + 1,
                  f'{key} @ {vp}: the page does not scroll sideways '
                  f'({view["scrollW"]} <= {view["w"]})')
    session = create_session('lab', num_participants=2)
    for stop, sel in (('startpage', '.experimental-content'),
                      ('instructing', '.instruction-wrapper')):
        code, _ = walk_to(server.base, create_session('lab', num_participants=2),
                          stop)
        for vp_name, vp in VIEWPORTS.items():
            context = browser.new_context(viewport=vp)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(150)
            m = page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                return {scrollW: el.scrollWidth, clientW: el.clientWidth,
                        hbar: el.offsetHeight - el.clientHeight -
                              (parseFloat(getComputedStyle(el).borderTopWidth) || 0) * 2};
            }""", sel)
            if m is None:
                continue
            check(m['scrollW'] <= m['clientW'] + 1,
                  f'{stop} {sel} @ {vp_name}: no horizontal overflow '
                  f'({m["scrollW"]} <= {m["clientW"]})')
            check(m['hbar'] <= 1,
                  f'{stop} {sel} @ {vp_name}: no horizontal scrollbar eating '
                  f'its height ({m["hbar"]}px)')
            context.close()


def check_band_centred(server, browser):
    """D6 (2026-08-11): the reading band is centred on the CARD's centre line.

    A region with an explicit `width` plus negative side margins cannot widen —
    it only shifts — so the whole centred band drifted left of the card centre
    (measured 625 against 632.5) and titles read visibly off-centre.
    """
    section('D6. The reading band is symmetric about the card centre')
    for key, config, stop, selector in (
            ('instructions', 'lab', 'instructing', '.instruction-block > h2'),
            ('consent_prolific', 'prolific', 'welcome', '.section-text'),
            ('lab_entry_gate', 'lab', 'startpage', '.section-text')):
        session = create_session(config, num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        for vp_name, vp in VIEWPORTS.items():
            context = browser.new_context(viewport=vp)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(150)
            m = page.evaluate("""(sel) => {
                const card = document.querySelector('.screen-card');
                const band = document.querySelector(sel);
                if (!card || !band) return null;
                const c = card.getBoundingClientRect();
                const b = band.getBoundingClientRect();
                const cs = getComputedStyle(card);
                const inner = {l: c.left + parseFloat(cs.paddingLeft),
                               r: c.right - parseFloat(cs.paddingRight)};
                return {cardCentre: (inner.l + inner.r) / 2,
                        bandCentre: (b.left + b.right) / 2,
                        left: Math.round(b.left - inner.l),
                        right: Math.round(inner.r - b.right)};
            }""", selector)
            label = f'{key} @ {vp_name}'
            if not check(m is not None, f'{label}: the band renders'):
                context.close()
                continue
            off = abs(m['cardCentre'] - m['bandCentre'])
            check(off <= 1.5,
                  f'{label}: band centre {m["bandCentre"]:.1f} vs card centre '
                  f'{m["cardCentre"]:.1f} (off by {off:.1f}px; margins '
                  f'{m["left"]}px left / {m["right"]}px right)')
            geometry.setdefault('band_centring', {})[label] = m
            context.close()


def check_eyebrow_alignment(server, browser):
    """D8 (2026-08-11): the eyebrow is flush with the copy it introduces.

    With the frame a constant 1200px, an eyebrow pinned to the card's padding
    edge sits ~180px from the reading band it labels and reads as stranded in
    the margin. On a banded page it must share the band's left edge.
    """
    section('P. The eyebrow sits flush with the band it introduces')
    for key, config, stop, band_sel in (
            ('consent_prolific', 'prolific', 'welcome', '.section-text'),
            ('prolific_id', 'prolific', 'ConfirmProlificID', '.stacked-form'),
            ('ended_screenout', 'prolific', 'Ended', '.section-text'),
            ('instructions', 'lab', 'instructing', '.instruction-block')):
        modified = {'mobile_screenout': 1} if key == 'ended_screenout' else None
        ua = PHONE_UA if key == 'ended_screenout' else None
        session = create_session(config, num_participants=2,
                                 modified_session_config_fields=modified)
        code, _ = walk_to(server.base, session, stop, user_agent=ua)
        for vp_name, vp in VIEWPORTS.items():
            context = browser.new_context(viewport=vp, user_agent=ua)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(150)
            m = page.evaluate("""(sel) => {
                const eb = document.querySelector('.eyebrow');
                const band = document.querySelector(sel);
                const card = document.querySelector('.screen-card');
                if (!eb || !band) return null;
                const e = eb.getBoundingClientRect();
                const b = band.getBoundingClientRect();
                const cs = getComputedStyle(card);
                return {eyebrowX: Math.round(e.left), bandX: Math.round(b.left),
                        cardEdge: Math.round(card.getBoundingClientRect().left +
                                             parseFloat(cs.paddingLeft))};
            }""", band_sel)
            label = f'{key} @ {vp_name}'
            if not check(m is not None, f'{label}: eyebrow and band both render'):
                context.close()
                continue
            check(abs(m['eyebrowX'] - m['bandX']) <= 2,
                  f'{label}: eyebrow starts at x={m["eyebrowX"]}, the band it '
                  f'introduces at x={m["bandX"]} (card padding edge '
                  f'{m["cardEdge"]})')
            geometry.setdefault('eyebrow', {})[label] = m
            context.close()


def check_short_page_balance(server, browser):
    """D7 (2026-08-11): a very short narrative page is balanced.

    The lab gate is one sentence. It must read as centred copy with the
    institutional marks along the FOOT of the card — not copy and logos clumped
    together mid-card with a bigger hole underneath — and its text must not be
    justified (justification belongs to the instructions reading band).
    """
    section('D7. The lab entry gate: balanced, logos at the foot, not justified')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'startpage')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(150)
        m = page.evaluate("""() => {
            const el = document.querySelector('.experimental-content');
            const text = document.querySelector('.section-text');
            const logo = document.querySelector('.logo-section');
            if (!el || !text || !logo) return null;
            const r = el.getBoundingClientRect();
            const t = text.getBoundingClientRect();
            const g = logo.getBoundingClientRect();
            const cs = getComputedStyle(el);
            const pad = parseFloat(cs.paddingBottom) || 0;
            const gap = parseFloat(cs.rowGap || cs.gap) || 0;
            return {align: getComputedStyle(text).textAlign,
                    pad: pad, gap: gap,
                    // free space above the copy, and free space between the copy
                    // and the logo strip, both net of the fixed padding/gap
                    aboveFree: Math.round(t.top - r.top - pad),
                    betweenFree: Math.round(g.top - t.bottom - gap),
                    below: Math.round(r.bottom - g.bottom - pad),
                    overflows: el.scrollHeight > el.clientHeight + 2};
        }""")
        if not check(m is not None, f'{vp_name}: the gate renders text + logos'):
            context.close()
            continue
        check(m['align'] != 'justify',
              f'{vp_name}: the sentence is NOT justified (text-align: '
              f'{m["align"]})')
        check(m['below'] <= 2,
              f'{vp_name}: the logo strip sits at the FOOT of the scroll region '
              f'({m["below"]}px of free space below it, net of its '
              f'{m["pad"]:.0f}px padding)')
        # The two auto margins split the free space, so the copy is centred in
        # the space above the logos: the free space above it and the free space
        # between it and the strip should match.
        check(abs(m['aboveFree'] - m['betweenFree']) <= 2,
              f'{vp_name}: the copy is centred above the logo strip '
              f'({m["aboveFree"]}px free above, {m["betweenFree"]}px free '
              f'below)')
        geometry.setdefault('short_page', {})[vp_name] = m
        screenshot(page, 'lab_entry_gate_balance', vp_name)
        context.close()


def check_constant_card(facts):
    """Suggestion 1, now implemented: ONE card width for EVERY page."""
    section('N. The card frame is the same width on every page')
    for vp_name, vp in VIEWPORTS.items():
        widths = {k: per[vp_name]['card']['w'] for k, per in facts.items()}
        # The cap is min(94vw, 1200px), but on a narrow screen the page shell's
        # own gutter binds first, so the shell's inner width is the real ceiling.
        shell_box = next(iter(facts.values()))[vp_name]['shell']
        pad = float(str(shell_box['paddingTop']).rstrip('px') or 0)
        shell = int(shell_box['w'] - 2 * pad)      # the shell's INNER width
        expected = min(int(0.94 * vp['width']), 1200, shell)
        check(len(set(widths.values())) == 1,
              f'{vp_name}: every page renders the same card width '
              f'({sorted(set(widths.values()))})')
        check(all(abs(w - expected) <= 2 for w in widths.values()),
              f'{vp_name}: and it fills the frame it is allowed — '
              f'min(94vw, 1200px, shell {shell}px) = {expected}px '
              f'(got {sorted(set(widths.values()))})')
        geometry.setdefault('card_widths', {})[vp_name] = widths


def check_consent_choice_visible(server, browser, facts):
    """D3: on the consent page the CHOICE must be on screen without scrolling.

    A participant who can see only the privacy panel and a Next button can
    consent without ever seeing what they are consenting to, so this is asserted
    at every viewport, on the variant that actually renders the control.
    """
    section('D3. The consent options are visible without scrolling')
    session = create_session('prolific', num_participants=2)
    code, _ = walk_to(server.base, session, 'welcome')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        m = page.evaluate("""() => {
            const opts = Array.from(document.querySelectorAll(
                'input[name="consent"]')).map(i =>
                    i.closest('.form-check, .mc-option') || i);
            if (!opts.length) return null;
            const el = document.querySelector('.experimental-content');
            const sr = el.getBoundingClientRect();
            const btn = document.querySelector('.button-row');
            return {
                n: opts.length,
                first: (() => { const r = opts[0].getBoundingClientRect();
                                return {top: Math.round(r.top),
                                        bottom: Math.round(r.bottom)}; })(),
                last: (() => { const r = opts[opts.length - 1]
                                   .getBoundingClientRect();
                               return {top: Math.round(r.top),
                                       bottom: Math.round(r.bottom)}; })(),
                viewTop: Math.round(sr.top), viewBottom: Math.round(sr.bottom),
                buttonTop: btn ? Math.round(btn.getBoundingClientRect().top) : null,
                scrollTop: el.scrollTop,
            };
        }""")
        if not check(m is not None,
                     f'{vp_name}: the consent control is rendered'):
            context.close()
            continue
        visible_px = min(m['first']['bottom'], m['viewBottom']) - max(
            m['first']['top'], m['viewTop'])
        both = min(m['last']['bottom'], m['viewBottom']) - max(
            m['last']['top'], m['viewTop'])
        if vp_name == 'phone_375x667':
            # HONEST LIMIT: this page's copy is ~750px tall and a 375x667 phone
            # gives the scroll region ~415px, so no arrangement of the layout
            # puts the options above the fold — only cutting the consent text
            # would, and consent text is the one thing this template must not
            # trim (skills_claude/writing_welcome_consent.md). What IS required
            # on a phone is that nothing can be consented to blind: the region
            # must announce that it scrolls (checked above) and an untouched
            # submit must be REJECTED (checked below).
            print(f'  [note] {vp_name}: the first option sits '
                  f'{max(0, m["first"]["top"] - m["viewBottom"])}px below the '
                  f'fold (option {m["first"]["top"]}..{m["first"]["bottom"]}, '
                  f'viewport {m["viewTop"]}..{m["viewBottom"]}) — physically '
                  f'unfittable, see the note above')
        else:
            check(visible_px > 10,
                  f'{vp_name}: the FIRST consent option is on screen without '
                  f'scrolling ({visible_px}px of it visible; option '
                  f'{m["first"]["top"]}..{m["first"]["bottom"]}, scroll viewport '
                  f'{m["viewTop"]}..{m["viewBottom"]})')
        print(f'       second option: {both}px visible '
              f'({m["last"]["top"]}..{m["last"]["bottom"]})')
        geometry.setdefault('consent_choice', {})[vp_name] = dict(
            m, first_visible_px=visible_px, second_visible_px=both)
        screenshot(page, 'consent_prolific_fold', vp_name)
        context.close()

    # NOBODY CONSENTS BLIND. The radio must not be pre-ticked and an untouched
    # submit must be rejected, so a participant who never scrolls to the choice
    # cannot get past this page at all.
    s = requests.Session()
    session = create_session('prolific', num_participants=2)
    r = s.get(f'{server.base}/join/{anon_code(session.code)}',
              allow_redirects=True)
    check('name="consent"' in r.text, 'the consent page renders the radio group')
    checked = [line for line in r.text.split('<input')
               if 'name="consent"' in line and ' checked' in line]
    check(not checked,
          f'NEITHER consent option is pre-checked ({len(checked)} found)')
    before_url = r.url
    r2 = s.post(r.url, data={'is_mobile': '', 'device_info_json': '',
                             'participant_id_url': ''}, allow_redirects=True)
    check(r2.status_code < 500, 'an untouched submit does not 5xx')
    check(page_of(r2.url) == 'welcome' and str(r2.url) == str(before_url),
          f'an untouched submit is REJECTED and stays on the consent page '
          f'(now {page_of(r2.url)})')
    check('required' in r2.text.lower(),
          'oTree shows its "this field is required" message')


def check_logo_unpinned(server, browser):
    """D4: the logo strip scrolls with the content instead of eating card height."""
    section('D4. The logo strip is inside the scroll region, not pinned')
    for key, config, stop in (('consent_prolific', 'prolific', 'welcome'),
                              ('results', 'prolific', 'Results')):
        session = create_session(config, num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(150)
        m = page.evaluate("""() => {
            const logo = document.querySelector('.logo-section');
            const el = document.querySelector('.experimental-content');
            if (!logo || !el) return null;
            const before = logo.getBoundingClientRect().top;
            el.scrollTop = el.scrollHeight;
            const after = logo.getBoundingClientRect().top;
            el.scrollTop = 0;
            return {inside: el.contains(logo), before: Math.round(before),
                    after: Math.round(after),
                    overflows: el.scrollHeight > el.clientHeight + 2};
        }""")
        if not check(m is not None, f'{key}: the page has a logo strip'):
            context.close()
            continue
        check(m['inside'],
              f'{key}: the logo strip is INSIDE .experimental-content')
        if m['overflows']:
            check(m['after'] != m['before'],
                  f'{key}: it moves when the region scrolls '
                  f'({m["before"]} -> {m["after"]}) — i.e. it is not pinned')
        geometry.setdefault('logo_strip', {})[key] = m
        context.close()


def check_scroll_really_moves(server, browser):
    """Not just "overflow-y:auto is set" — drive the scroll and measure it."""
    section('B2. Scrolling the content region actually moves the content')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'quiz')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        moved = page.evaluate("""() => {
            const el = document.querySelector('.experimental-content');
            if (!el) return null;
            const before = el.scrollTop;
            el.scrollTop = el.scrollHeight;
            const after = el.scrollTop;
            return {before, after, scrollH: el.scrollHeight,
                    clientH: el.clientHeight,
                    overflows: el.scrollHeight > el.clientHeight + 2};
        }""")
        if not moved['overflows']:
            print(f'  [skip] {vp_name}: quiz fits, nothing to scroll '
                  f'({moved["scrollH"]} <= {moved["clientH"]})')
        else:
            check(moved['after'] > moved['before'],
                  f'{vp_name}: scrollTop moved {moved["before"]} -> '
                  f'{moved["after"]} of {moved["scrollH"]}px')
        geometry.setdefault('scroll_probe', {})[vp_name] = moved
        context.close()


# ==========================================================================
# CHECK C — the focus ring on the first and last option is not clipped
# ==========================================================================
# The ring is painted on the element that HAS focus — the radio input inside the
# option card, not the card — so it is measured on document.activeElement. The
# card's own edges are reported beside it, because the card is the outer thing
# the scroll box could clip.
FOCUS_JS = """() => {
    const scroller = document.querySelector('.experimental-content');
    const opts = Array.from(document.querySelectorAll('.form-check, .mc-option'));
    if (!scroller || !opts.length) return null;
    const active = document.activeElement;
    if (!active) return null;
    const card = active.closest('.form-check, .mc-option');
    const cs = getComputedStyle(active);
    const ring = (parseFloat(cs.outlineWidth) || 0)
               + (parseFloat(cs.outlineOffset) || 0);
    const ar = active.getBoundingClientRect();
    const cr = (card || active).getBoundingClientRect();
    const sr = scroller.getBoundingClientRect();
    const sc = getComputedStyle(scroller);
    // The topmost/bottommost painted pixel: whichever is further out, the ring
    // around the focused input or the option card's own border.
    const paintedTop = Math.min(ar.top - ring, cr.top);
    const paintedBottom = Math.max(ar.bottom + ring, cr.bottom);
    return {
        tag: active.tagName + (active.type ? ':' + active.type : ''),
        outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth,
        outlineOffset: cs.outlineOffset, ring: ring,
        ringTop: Math.round(ar.top - ring), ringBottom: Math.round(ar.bottom + ring),
        cardTop: Math.round(cr.top), cardBottom: Math.round(cr.bottom),
        scrollerTop: Math.round(sr.top), scrollerBottom: Math.round(sr.bottom),
        padTop: parseFloat(sc.paddingTop), padBottom: parseFloat(sc.paddingBottom),
        headroom: Math.round(paintedTop - sr.top),
        footroom: Math.round(sr.bottom - paintedBottom),
        index: card ? opts.indexOf(card) : -1, n: opts.length,
    };
}"""


def check_focus_rings(server, browser):
    section('C. The :focus-visible ring on the first/last option is not clipped')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'quiz')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        # KEYBOARD focus, not .focus(): :focus-visible only paints a ring when the
        # browser believes the user is navigating by keyboard.
        first = None
        for _ in range(30):
            page.keyboard.press('Tab')
            first = page.evaluate(FOCUS_JS)
            if first and first['index'] == 0:
                break
        if not check(first is not None and first['index'] == 0,
                     f'{vp_name}: keyboard focus reaches the FIRST option'):
            context.close()
            continue
        check(first['outlineStyle'] != 'none' and first['ring'] > 0,
              f'{vp_name}: the focused control ({first["tag"]}) shows a ring '
              f'({first["outlineWidth"]} + {first["outlineOffset"]} offset)')
        check(first['headroom'] >= 0,
              f'{vp_name}: first option ring clears the scroll edge by '
              f'{first["headroom"]}px (>=0 = not clipped)')
        # Keep the picture: what a keyboard user actually sees is a ring around
        # the radio dot, not around the option card.
        screenshot(page, 'quiz_focus_ring', vp_name)
        # …then Shift+Tab backwards from the end for the LAST option.
        page.evaluate("""() => { const o = document.querySelectorAll(
            '.form-check input, .mc-option input');
            if (o.length) o[o.length - 1].focus(); }""")
        page.keyboard.press('Shift+Tab')
        page.keyboard.press('Tab')
        last = page.evaluate(FOCUS_JS)
        if last:
            check(last['footroom'] >= 0,
                  f'{vp_name}: last option ring clears the bottom scroll edge by '
                  f'{last["footroom"]}px (>=0 = not clipped)')
        geometry.setdefault('focus_ring', {})[vp_name] = {'first': first,
                                                          'last': last}
        context.close()


# ==========================================================================
# CHECK D — the tab-monitor overlay covers the viewport, not the card
# ==========================================================================
def check_overlay(server, browser):
    section('D. The tab-monitor overlay covers the whole viewport')
    session = create_session('prolific', num_participants=2)
    code, _ = walk_to(server.base, session, 'GameStart')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        # ARM THE MONITOR the way the study does: the AI-safety agreement page
        # sets sessionStorage.aiSafetyAgreed, and ai_safety_monitor.js builds no
        # DOM at all until it is set. The walk above passed that page over plain
        # HTTP, so this browser has never run its script.
        context.add_init_script(
            "try { sessionStorage.setItem('aiSafetyAgreed', '1'); } catch (e) {}")
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        present = page.evaluate(
            "() => !!document.querySelector('.tabmon-overlay')")
        if not check(present, f'{vp_name}: the monitor injected its overlay'):
            context.close()
            continue
        # Show it exactly as the monitor does (the class it adds), then measure.
        page.evaluate("""() => document.querySelector('.tabmon-overlay')
                              .classList.add('is-visible')""")
        page.wait_for_timeout(80)
        m = page.evaluate("""() => {
            const o = document.querySelector('.tabmon-overlay');
            const r = o.getBoundingClientRect();
            const card = document.querySelector('.screen-card')
                             .getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    vw: window.innerWidth, vh: window.innerHeight,
                    position: getComputedStyle(o).position,
                    cardTop: Math.round(card.top), cardBottom: Math.round(card.bottom),
                    topElement: (document.elementFromPoint(5, 5) || {}).className};
        }""")
        check(m['position'] == 'fixed', f'{vp_name}: overlay is position:fixed')
        check(m['x'] == 0 and m['y'] == 0 and m['w'] == m['vw']
              and m['h'] == m['vh'],
              f'{vp_name}: overlay is {m["w"]}x{m["h"]} at ({m["x"]},{m["y"]}) '
              f'= the whole {m["vw"]}x{m["vh"]} viewport')
        check(m['y'] < m['cardTop'] and m['y'] + m['h'] > m['cardBottom'],
              f'{vp_name}: overlay extends beyond the card '
              f'(card {m["cardTop"]}..{m["cardBottom"]}) — not trapped inside it')
        check('tabmon-overlay' in (m['topElement'] or ''),
              f'{vp_name}: the overlay is what sits at the top-left pixel '
              f'(got {m["topElement"]!r})')
        # …and it is READABLE: this chrome is white-on-red, and base.css's
        # global `strong { color: var(--ink) }` otherwise renders the emphasised
        # countdown in dark navy on red — the least legible text on the screen.
        emph = page.evaluate("""() => {
            const el = document.querySelector('.tabmon-overlay__msg strong');
            return el ? getComputedStyle(el).color : null;
        }""")
        check(emph in ('rgb(255, 255, 255)', None),
              f'{vp_name}: emphasised text on the red overlay is white '
              f'(got {emph})')
        screenshot(page, 'tabmonitor_overlay', vp_name)
        geometry.setdefault('overlay', {})[vp_name] = m
        context.close()


# ==========================================================================
# FEATURE CHECKS — every implemented feature, proven by measurement
# ==========================================================================
def check_features(server, browser, facts):
    section('E. Option cards: bordered card, selected state, whole card clickable')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'quiz')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    opt = page.evaluate("""() => {
        const el = document.querySelector('.form-check, .mc-option');
        if (!el) return null;
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const input = el.querySelector('input');
        const ir = input ? input.getBoundingClientRect() : null;
        return {border: cs.borderTopWidth, borderColor: cs.borderTopColor,
                background: cs.backgroundColor, radius: cs.borderTopLeftRadius,
                w: Math.round(r.width), h: Math.round(r.height),
                x: Math.round(r.x), y: Math.round(r.y),
                inputW: ir ? Math.round(ir.width) : 0,
                inputX: ir ? Math.round(ir.x) : 0,
                cursor: cs.cursor, checked: input ? input.checked : null};
    }""")
    check(opt is not None and float(opt['border'].rstrip('px')) > 0,
          f'option renders as a bordered card (border {opt and opt["border"]}, '
          f'radius {opt and opt["radius"]})')
    check(opt['background'] not in ('rgba(0, 0, 0, 0)', 'transparent'),
          f'option card has its own (grey) fill: {opt["background"]}')
    # WHOLE CARD CLICKABLE: click far from the radio dot — 20px inside the card's
    # RIGHT edge, which is nowhere near the input — and require it to select.
    page.mouse.click(opt['x'] + opt['w'] - 20, opt['y'] + opt['h'] / 2)
    page.wait_for_timeout(60)
    after = page.evaluate("""() => {
        const el = document.querySelector('.form-check, .mc-option');
        const input = el.querySelector('input');
        const cs = getComputedStyle(el);
        return {checked: input.checked, background: cs.backgroundColor,
                borderColor: cs.borderTopColor};
    }""")
    check(after['checked'] is True,
          f'clicking the card {opt["w"] - 20}px from its left edge (the radio is '
          f'{opt["inputX"] - opt["x"]}px in, {opt["inputW"]}px wide) selects it')
    check(after['background'] != opt['background']
          or after['borderColor'] != opt['borderColor'],
          f'the selected state is visible: fill {opt["background"]} -> '
          f'{after["background"]}, border {opt["borderColor"]} -> '
          f'{after["borderColor"]}')
    geometry['option_card'] = {'before': opt, 'after': after}
    screenshot(page, 'quiz_option_selected', 'laptop_1280x720')
    context.close()

    section('F. Eyebrow, privacy panel and per-family text alignment')
    consent = facts['consent_lab']['laptop_1280x720']
    eb, title, card = consent['eyebrow'], consent['title'], consent['card']
    check(eb is not None, 'consent page renders an eyebrow')
    check(eb['y'] + eb['h'] <= title['y'] + 2,
          f'eyebrow sits ABOVE the title ({eb["y"]}+{eb["h"]} <= {title["y"]})')
    check(eb['x'] < card['x'] + card['w'] / 3,
          f'eyebrow sits top-LEFT (x={eb["x"]}, card x={card["x"]})')
    check(float(eb['fontSize'].rstrip('px')) < 15,
          f'eyebrow is small text ({eb["fontSize"]})')
    check(eb['color'] != consent['section_text']['color'],
          f'eyebrow is muted grey, not body ink ({eb["color"]} vs '
          f'{consent["section_text"]["color"]})')
    panel = consent['panel']
    check(panel is not None and float(panel['borderTopWidth'].rstrip('px')) > 0
          and panel['background'] not in ('rgba(0, 0, 0, 0)', 'transparent'),
          f'the privacy statement is a PANEL BOX, not inline prose '
          f'(border {panel and panel["borderTopWidth"]}, fill '
          f'{panel and panel["background"]})')
    check(panel['display'] == 'table' and panel['w'] < consent['content']['w'],
          f'it is the hug variant: shrink-wrapped ({panel["w"]}px inside a '
          f'{consent["content"]["w"]}px column), display:{panel["display"]}')

    for key in ('consent_lab', 'consent_prolific', 'ended_screenout'):
        st = facts[key]['laptop_1280x720']['section_text']
        if st:
            check(st['textAlign'] == 'center',
                  f'{key}: body copy is CENTRED (text-align:{st["textAlign"]})')
    quiz_align = facts['quiz']['laptop_1280x720']
    q = quiz_align['first_option']
    check(q['textAlign'] == 'left',
          f'quiz options stay LEFT aligned (text-align:{q["textAlign"]})')
    geometry['alignment'] = {
        'consent_section_text': facts['consent_lab']['laptop_1280x720']['section_text'],
        'quiz_option': q,
    }

    section('G. The instructions reading band is justified and holds its measure')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'instructing')
    context = browser.new_context(viewport=VIEWPORTS['desktop_1512x1200'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    band = page.evaluate("""() => {
        const p = document.querySelector('.instruction-block p, .instructions p');
        const wrap = document.querySelector('.instructions');
        const card = document.querySelector('.screen-card');
        if (!p) return null;
        const cs = getComputedStyle(p);
        const probe = document.createElement('div');
        probe.style.cssText = 'width:68ch;position:absolute;visibility:hidden';
        p.parentNode.appendChild(probe);
        const measure = Math.round(probe.getBoundingClientRect().width);
        probe.remove();
        return {textAlign: cs.textAlign,
                pw: Math.round(p.getBoundingClientRect().width),
                bandw: Math.round(wrap.getBoundingClientRect().width),
                cardw: Math.round(card.getBoundingClientRect().width),
                measure68ch: measure};
    }""")
    check(band and band['textAlign'] == 'justify',
          f'instruction body copy is JUSTIFIED (text-align:'
          f'{band and band["textAlign"]})')
    check(band['pw'] <= band['measure68ch'] + 4,
          f'it holds the reading measure: {band["pw"]}px <= 68ch '
          f'({band["measure68ch"]}px)')
    check(band['pw'] < band['cardw'],
          f'the band is narrower than the card ({band["pw"]} < {band["cardw"]})')
    geometry['instructions_band'] = band

    section('H. Buttons are pill shaped, with a working ghost variant on Back')
    btn = page.evaluate("""() => {
        const out = {};
        for (const [k, sel] of [['next', '#nextBtn'], ['back', '#prevBtn']]) {
            const el = document.querySelector(sel);
            if (!el) { out[k] = null; continue; }
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            out[k] = {radius: cs.borderTopLeftRadius, h: Math.round(r.height),
                      background: cs.backgroundColor, color: cs.color,
                      border: cs.borderTopWidth, borderColor: cs.borderTopColor,
                      disabled: el.disabled};
        }
        return out;
    }""")
    for name in ('next', 'back'):
        b = btn[name]
        radius = float(b['radius'].rstrip('px')) if b['radius'].endswith('px') else 999
        check(b is not None and radius >= b['h'] / 2 - 1,
              f'{name} button is PILL shaped (radius {b["radius"]} >= half of '
              f'{b["h"]}px height)')
    check(btn['back']['background'] in ('rgba(0, 0, 0, 0)', 'transparent'),
          f'Back is the GHOST variant: transparent fill '
          f'({btn["back"]["background"]}) vs Next {btn["next"]["background"]}')
    check(btn['back']['color'] != btn['next']['color'],
          f'ghost text colour differs from the solid button '
          f'({btn["back"]["color"]} vs {btn["next"]["color"]})')
    geometry['buttons'] = btn
    context.close()

    section('I. Logos render at the CSS size, with no inline height attribute')
    for key in ('consent_lab', 'lab_entry_gate'):
        for vp, f in facts[key].items():
            attrs = f['logo_inline_attrs']
            check(all(a['height'] is None and not a['style'] for a in attrs),
                  f'{key} @ {vp}: no inline height/style on any logo '
                  f'({len(attrs)} images)')
        desktop = facts[key]['desktop_1512x1200']['logo_img']
        phone = facts[key]['phone_375x667']['logo_img']
        check(desktop and desktop['h'] == 40,
              f'{key}: logo renders at the CSS 40px on desktop '
              f'(got {desktop and desktop["h"]}px)')
        check(phone and phone['h'] == 32,
              f'{key}: the phone breakpoint shrinks it to 32px '
              f'(got {phone and phone["h"]}px)')

    section('J. CREED header scoping and consent neutrality')
    for key, f in facts.items():
        has = f['laptop_1280x720']['has_creed_header']
        if key == 'lab_entry_gate':
            check(has, 'the lab entry gate DOES show the CREED welcome header')
        else:
            check(not has, f'{key}: no CREED header (it belongs to the gate only)')
    for key in ('consent_lab', 'consent_prolific'):
        text = facts[key]['laptop_1280x720']['text']
        check('Prolific' not in text,
              f'{key}: the participant never READS the word Prolific')
        check('Welcome to' not in text, f'{key}: no CREED welcome wording')
    idtext = facts['prolific_id']['laptop_1280x720']['text']
    check('Prolific' in idtext,
          'the ID page names Prolific (the one page that may)')

    section('K. The Prolific ID page pre-fills from the URL parameter')
    session = create_session('prolific', num_participants=2)
    code, resp = walk_to(server.base, session, 'ConfirmProlificID',
                         label='PID_FROM_URL_4242')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    val = page.input_value('#participant_id_external')
    check(val == 'PID_FROM_URL_4242',
          f'the field is pre-filled with the URL id (got {val!r})')
    check('We do not have a Prolific ID' not in visible_text(page),
          'the loud no-ID panel is NOT shown when an id arrived')
    context.close()

    section('L. The screened-out ending shows its OWN wording')
    text = facts['ended_screenout']['phone_375x667']['text']
    check('computer' in text.lower() or 'desktop' in text.lower()
          or 'laptop' in text.lower(),
          f'the phone screen-out ending explains the desktop-only rule '
          f'(text: {text[:120]!r})')
    check(facts['ended_screenout']['laptop_1280x720']['url_page'] == 'Ended',
          'the screened-out participant lands on the ending page')


# ==========================================================================
# CHECK M — the scroll shadow appears, then disappears at the end
# ==========================================================================
def check_scroll_shadow(server, browser):
    """M. The JS-FREE fallback: the background shadows self-hide.

    Driven with JavaScript DISABLED on purpose. With the script running the mask
    fade (layer 3) is the affordance and is measured in D1/D2; this leg is the
    other half of the contract — that a participant whose JS is blocked still
    gets a shadow that appears while there is more content and goes away at the
    end, from CSS alone.
    """
    section('M. JS DISABLED: the CSS-only scroll shadow appears, then hides')
    try:
        from PIL import Image
    except ImportError:
        check(False, 'Pillow is installed (needed to measure the shadow pixels)')
        return
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'quiz')
    vp = VIEWPORTS['phone_375x667']          # the surest overflow
    context = browser.new_context(viewport=vp, java_script_enabled=False)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    state = page.evaluate("""() => {
        const el = document.querySelector('.experimental-content');
        const r = el.getBoundingClientRect();
        return {overflows: el.scrollHeight > el.clientHeight + 2,
                x: r.x, y: r.y, w: r.width, h: r.height};
    }""")
    if not state['overflows']:
        print('  [skip] the quiz does not overflow at this viewport; the long-quiz '
              'pass covers the shadow')
        context.close()
        return

    def strip_darkness(edge):
        """Mean darkness of an 8px strip at the top/bottom of the scroll box."""
        y = state['y'] + 1 if edge == 'top' else state['y'] + state['h'] - 9
        clip = dict(x=state['x'] + 6, y=y, width=max(10, state['w'] - 12),
                    height=8)
        path = os.path.join(OUT_DIR, f'_shadow_{edge}.png')
        page.screenshot(path=path, clip=clip)
        img = Image.open(path).convert('L')
        px = list(img.getdata())
        os.remove(path)
        return 255 - (sum(px) / len(px))       # 0 = pure white

    page.evaluate("() => document.querySelector('.experimental-content')"
                  ".scrollTop = 0")
    page.wait_for_timeout(60)
    top_at_start, bottom_at_start = strip_darkness('top'), strip_darkness('bottom')
    page.evaluate("""() => { const el = document.querySelector(
        '.experimental-content'); el.scrollTop = el.scrollHeight; }""")
    page.wait_for_timeout(120)
    top_at_end, bottom_at_end = strip_darkness('top'), strip_darkness('bottom')
    check(bottom_at_start > top_at_start,
          f'at the TOP of the scroll only the BOTTOM shadow is painted '
          f'(darkness bottom {bottom_at_start:.2f} > top {top_at_start:.2f})')
    check(top_at_end > top_at_start,
          f'scrolling down reveals the TOP shadow '
          f'({top_at_start:.2f} -> {top_at_end:.2f})')
    check(bottom_at_end < bottom_at_start,
          f'the BOTTOM shadow disappears at the end of the content '
          f'({bottom_at_start:.2f} -> {bottom_at_end:.2f})')
    geometry['scroll_shadow'] = {
        'top_at_start': round(top_at_start, 3),
        'bottom_at_start': round(bottom_at_start, 3),
        'top_at_end': round(top_at_end, 3),
        'bottom_at_end': round(bottom_at_end, 3),
    }
    context.close()


# ==========================================================================
def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright is not installed: pip install playwright && '
              'playwright install chromium')
        return 2

    server = Server()
    server.start()
    print(f'server on {server.base}; screenshots -> {OUT_DIR}'
          f'{"  [LONG QUIZ PASS]" if LONG_QUIZ else ""}')
    try:
        with sync_playwright() as pw:
            try:
                # `--hide-scrollbars` is one of Playwright's DEFAULT headless
                # args, so out of the box every screenshot silently loses the
                # single clearest "this region scrolls" signal — and any check
                # measuring the affordance off the pixels would be judging a
                # page the participant never sees. Drop it.
                browser = pw.chromium.launch(
                    ignore_default_args=['--hide-scrollbars'])
            except Exception as exc:
                print(f'headless Chromium did not launch ({exc.__class__.__name__}: '
                      f'{exc}).\nSet LD_LIBRARY_PATH to an unpacked sysroot — see '
                      f'_ai/headless_chromium_recipe.md')
                return 2
            try:
                facts = render_all(server, browser)
                check_card_gaps(facts)
                check_scrolling(server, browser, facts)
                if not LONG_QUIZ:
                    check_constant_card(facts)
                    check_scroll_really_moves(server, browser)
                    check_scroll_affordance(server, browser)
                    check_no_phantom_affordance(server, browser)
                    check_no_sideways_overflow(facts, server, browser)
                    check_band_centred(server, browser)
                    check_short_page_balance(server, browser)
                    check_eyebrow_alignment(server, browser)
                    check_consent_choice_visible(server, browser, facts)
                    check_logo_unpinned(server, browser)
                    check_focus_rings(server, browser)
                    check_overlay(server, browser)
                    check_features(server, browser, facts)
                check_scroll_shadow(server, browser)
            finally:
                browser.close()
    finally:
        server.stop()

    name = 'geometry_long_quiz.json' if LONG_QUIZ else 'geometry.json'
    with open(os.path.join(OUT_DIR, name), 'w') as fh:
        json.dump(geometry, fh, indent=2, sort_keys=True, default=str)
    print(f'\nmeasured geometry -> {os.path.join(OUT_DIR, name)}')

    section('SUMMARY' + (' (long-quiz pass)' if LONG_QUIZ else ''))
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        rc = 1
    else:
        print('  ALL CHECKS PASSED')
        rc = 0

    if not LONG_QUIZ:
        print('\n--- re-running with a deliberately overflowing quiz ---')
        rc |= subprocess.call([sys.executable, os.path.abspath(__file__),
                               '--long-quiz'])
    return rc


if __name__ == '__main__':
    sys.exit(main())
