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
   D3. the OUTRO monitor, end to end: a REAL tab blur (headed Chromium under
      Xvfb — headless pins visibility) held past tab_monitor_threshold_ms
      shows NO overlay, ejects NOBODY, and IS recorded in
      focus_loss_count_outro — the recorded count is what distinguishes
      record-only monitoring from no monitoring at all;
   plus the feature checks: option cards (bordered, selected state, whole card
   clickable), eyebrow, privacy panel, per-family text alignment, the justified
   instructions band, pill buttons + ghost variant, logo sizing from CSS,
   CREED header scoping, consent neutrality, Prolific-ID prefill, screen-out
   wording, and the self-hiding scroll shadow (measured off the pixels).

RUNNING IT (headless Chromium needs system libraries)
-----------------------------------------------------
On a box without root, unpack the library .debs into a private sysroot and point
LD_LIBRARY_PATH at it — full recipe in `docs/headless_chromium_recipe.md`:

    pip install playwright pillow uvicorn requests && playwright install chromium
    LD_LIBRARY_PATH=/path/to/sysroot/usr/lib/x86_64-linux-gnu \
        python tests/render_check.py

The script re-runs itself once with `--long-quiz` (a deliberately overflowing
quiz) to exercise the scroll checks; pass `--long-quiz` yourself to run only
that pass. Exit code 0 = every check passed.

LAYOUT REGRESSIONS (a diff, not a threshold)
--------------------------------------------
The checks above catch BROKEN. `tests/geometry_baseline.json` — committed, and
in tests/ rather than the gitignored _ai/ — catches CHANGED:

    python tests/render_check.py --diff             fail on anything that moved
    python tests/render_check.py --update-baseline  adopt an INTENTIONAL change

The tolerance, what the baseline holds and what it deliberately leaves out are
written at the top of that file.
"""

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

LONG_QUIZ = '--long-quiz' in sys.argv
# Compare this run's geometry against the committed baseline and FAIL on any
# element that moved (see the baseline section at the bottom of this file).
DIFF = '--diff' in sys.argv
# Rewrite that baseline from this run — the one command to use when a layout
# change is INTENTIONAL.
UPDATE_BASELINE = '--update-baseline' in sys.argv

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
# Expected completion codes are READ from the shipped config, never hardcoded:
# a hardcoded 'REPLACE_CC' would have quietly stopped matching the day the
# placeholders changed shape (2026-08-14), leaving the check green and blind.
import settings as _settings  # noqa: E402
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
from main_contract import TASK_PAGES  # noqa: E402  (the one task-page contract)
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
# A computer, for the case that must NOT be screened out however small its
# window is (check_narrow_desktop_window).
DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
              'Safari/537.36')

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


def wait_for_stable_layout(page, selector='.experimental-content', frames=3,
                           max_frames=180):
    """Block until the page's LAYOUT HAS SETTLED, then report what it took.

    WHY THIS EXISTS, AND WHY IT IS NOT A POINTLESS DELAY — DO NOT DELETE IT AS
    ONE (Julian, 2026-08-13). Every measurement in this file is taken at ONE
    INSTANT, and several of the assertions built on those measurements are
    CONDITIONAL on a height: "does this region overflow?" decides whether a
    scroll affordance must be present or must be absent. If the height is read
    while the layout is still moving — a web font still loading and about to
    change every line box, a `clamp()` not yet resolved, an image arriving — the
    check can take the wrong branch entirely and assert the opposite of the
    truth. That is the flakiness that makes people stop trusting a suite.

    The PAGE itself is fine and this is not compensating for a page bug: the
    fade and edge shadow are pure CSS (recomputed at paint, they cannot go
    stale) and the scroll-cue arrow re-syncs on scroll and through a
    ResizeObserver per region. It is only the TEST that samples at a moment.

    WHAT IT WAITS FOR, in order:
      1. `document.fonts.ready` — web fonts change text metrics, so a height
         measured before they land is a height that is about to change;
      2. the region's own box to STOP CHANGING: the same scrollHeight,
         clientHeight and border-box height across `frames` consecutive
         animation frames.

    RETURNS the settled measurement plus `moved`, the difference between the
    FIRST reading and the settled one. `moved` is deliberately reported rather
    than discarded: a non-zero value is direct evidence that a measurement taken
    the old way (a fixed sleep after load) would have been read off a layout
    that was still moving, which is a claim this suite should be able to make
    from data rather than from argument.
    """
    result = page.evaluate(
        """async ([sel, frames, maxFrames]) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            if (document.fonts && document.fonts.ready) {
                try { await document.fonts.ready; } catch (e) {}
            }
            const raf = () => new Promise(r => requestAnimationFrame(() => r()));
            const read = () => ({
                scrollH: el.scrollHeight,
                clientH: el.clientHeight,
                boxH: Math.round(el.getBoundingClientRect().height),
            });
            const same = (a, b) => a && b && a.scrollH === b.scrollH
                && a.clientH === b.clientH && a.boxH === b.boxH;
            const first = read();
            let last = first, stable = 0, n = 0;
            while (stable < frames && n < maxFrames) {
                await raf();
                const now = read();
                if (same(now, last)) { stable++; } else { stable = 0; last = now; }
                n++;
            }
            return {
                ...last,
                settled: stable >= frames,
                frames: n,
                moved: {scrollH: last.scrollH - first.scrollH,
                        clientH: last.clientH - first.clientH,
                        boxH: last.boxH - first.boxH},
            };
        }""",
        [selector, frames, max_frames])
    if result and not result['settled']:
        print(f'  [warn] layout never settled for {selector!r} after '
              f'{result["frames"]} frames — the measurement below may be taken '
              f'off a moving layout')
    if result and any(result['moved'].values()):
        print(f'  [note] layout moved while settling ({selector}): '
              f'{result["moved"]} — a fixed-sleep measurement would have read '
              f'the pre-settle value')
    return result


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
        # The ONLINE quiz, which is the one that carries the at-will re-read
        # dialog (the lab deliberately has no such button — see
        # intro.quiz.vars_for_template).
        dict(key='quiz_prolific', config='prolific', stop='quiz'),
        # The tab-monitor agreement page: its one bold sentence is the
        # consequence the participant is agreeing to (change_requests item 18).
        dict(key='ai_safety', config='prolific', stop='AISafetyAgree'),
        dict(key='task_tabmonitor', config='prolific', stop=TASK_PAGES[0]),
        dict(key='task_payoff', config='prolific', stop=TASK_PAGES[1]),
        # The lab's demographics/bank page. It had NO render leg until
        # 2026-08-11, which is how a template syntax error on it (a tag quoted
        # inside a JS comment — oTree parses tags there too) reached a 500 that
        # nothing caught: the lab walks all stopped before this page.
        dict(key='demographics_lab', config='lab', stop='Demographics'),
        dict(key='results', config='prolific', stop='Results'),
        # THE ENTRY SCREEN-OUT PAGE. Rendered at the CONSENT page's own URL —
        # `before.welcome` serves before/screened_out.html instead of consent
        # for a device the allow-list rejects, and HOLDS the participant there
        # so the verdict stays re-decidable (the soft wall). The browser context
        # carries the phone User-Agent too, so the gate re-decides the same way
        # for the real browser request as it did for the walker's.
        dict(key='screened_out', config='prolific', stop='welcome',
             modified={'allowed_devices': ['computer']}, user_agent=PHONE_UA),
        # THE SAME PAGE IN A NARROW DESKTOP WINDOW is NOT screened out: the gate
        # reads the User-Agent and nothing else, so window width cannot remove
        # anybody. Rendered with a computer User-Agent at 640px — the case a
        # width-based check would get wrong (see check_narrow_desktop_window).
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
        'has_logo_strip': page.locator('.logo-section').count() > 0,
        'has_header_title': page.locator(
            '.experimental-header .header-title').count() > 0,
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
            # SETTLE BEFORE MEASURING — this leg branches on the answer (see
            # wait_for_stable_layout): an overflow read off a layout that is
            # still moving would assert "the affordance must be there" against a
            # region that ends up fitting, or the reverse. A fixed sleep after
            # `load` is not the same thing and was what stood here.
            wait_for_stable_layout(page)
            st = page.evaluate("""() => {
                const el = document.querySelector('.experimental-content');
                const r = el.getBoundingClientRect();
                return {overflows: el.scrollHeight > el.clientHeight + 2,
                        gutter: el.offsetWidth - el.clientWidth,
                        cls: el.className,
                        x: r.x, y: r.y, w: r.width, h: r.height};
            }""")
            label = f'{page_key} @ {vp_name}'
            # THE AFFORDANCE IS CONDITIONAL, AND SO IS THIS CHECK — BOTH WAYS
            # (Julian, 2026-08-13). It is not "the consent page has a fade": it
            # is "a region that overflows says so, and a region that does not
            # says nothing".
            #
            # THE SECOND HALF IS NOT SYMMETRY FOR ITS OWN SAKE. A PHANTOM
            # AFFORDANCE — a fade, an edge shadow or a pulsing V on a region
            # with nothing below the fold — is a defect this repo has already
            # fixed once: it tells a participant to scroll for content that does
            # not exist, and the ones who believe it are the conscientious ones.
            # It used to be a bare `[skip]` here, which asserted nothing at all,
            # so the phantom could come back silently on any page whose content
            # shortened. THIS IS ALSO THE CASE A LAYOUT FIX CAN CREATE: recover
            # enough vertical space and a page that used to scroll no longer
            # does, at which point the fade must GO.
            if not st['overflows']:
                check('is-scrollable-down' not in st['cls'],
                      f'{label}: content FITS, so there is NO scroll affordance '
                      f'— nothing claims there is more below '
                      f'(class={st["cls"]!r})')
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
            # THE COMPARISON STRIP IS THE DARKEST OF SEVERAL, NOT ONE AT A FIXED
            # OFFSET (2026-08-13). A single sample 70px up asks "is there darker
            # content above the fade?" by assuming a line of copy happens to sit
            # exactly there — and what sits there is a property of the page's
            # layout, not of the fade. Measured when the consent card's rhythm
            # changed: the 70px strip moved off an option's label and onto the
            # SEAM between two option cards, so it read 3.63 — too faint for the
            # gradient clause, too dark for the "nothing above" clause, and the
            # leg went red while the fade itself was working perfectly (the
            # `at_edge` assertion above passed at 1.60).
            #
            # Taking the darkest of four offsets asks the question the check is
            # actually for — IS THERE DARKER CONTENT NEAR THE FADED EDGE — and
            # is indifferent to which of them lands on a glyph, a border or a
            # gap. It can only make the check STRICTER (a page with real content
            # above the fade can no longer pass through the blank-content
            # escape), which is the right direction for a check that exists to
            # prove the fade is a fade.
            above = max(edge_row(dy, h=8) for dy in (40, 70, 100, 130))
            # Scale: pure card white is 0; an unfaded line of body copy across
            # this strip measures 12-19 (see the `above` numbers). A hard-sliced
            # glyph row therefore lands in double figures, so a threshold of 3
            # separates "faded to nothing" from "cut through the middle" with an
            # order of magnitude to spare.
            check(at_edge <= 3.0,
                  f'{label}: the last 4px at the cut are faded to nothing '
                  f'(darkness {at_edge:.2f} of a 12-19 unfaded line)')
            # AND THE GRADIENT IS ONLY ASSERTABLE WHERE THERE IS SOMETHING TO
            # FADE. A region can overflow while the last 130px before the cut
            # are whitespace — the quiz at 1280x720 is exactly that, measuring
            # 3.65 against a faded edge of 0.29. There is no gradient to find
            # because there is no ink there, and demanding one would be
            # asserting a property of the page's copy, not of the fade. The
            # fade's own assertion is `at_edge` above, which is unconditional
            # and is what proves the mask is applied.
            # THE GATE IS "IS THERE INK HERE", on the scale this file already
            # uses: a line of body copy measures 12-19, and a card border or the
            # seam between two option cards measures 3-4 (consent read 3.63 off
            # a seam, the quiz reads 3.65 off whitespace). 6.0 sits above that
            # noise and below any real copy — and it is the SAME constant as the
            # gradient below, deliberately: a strip fainter than 6 could not
            # satisfy `above - at_edge > 6` anyway, so gating on it adds no new
            # threshold, it just stops the check asserting something arithmetic
            # already makes impossible.
            if above >= 6.0:
                check(above - at_edge > 6.0,
                      f'{label}: the darkest content within 130px of the cut is '
                      f'much darker than the faded edge '
                      f'({above:.2f} vs {at_edge:.2f})')
            else:
                print(f'       {label}: nothing within 130px of the cut to fade '
                      f'(darkest {above:.2f} — below the 12-19 of a line of '
                      f'copy); the faded edge itself reads {at_edge:.2f}')
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
            ('screened_out', 'prolific', 'welcome', '.section-text'),
            ('instructions', 'lab', 'instructing', '.instruction-block')):
        modified = ({'allowed_devices': ['computer']}
                    if key == 'screened_out' else None)
        ua = PHONE_UA if key == 'screened_out' else None
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
    """D7 (2026-08-11, remeasured 2026-08-13): a very short narrative page is
    balanced.

    The lab gate is one sentence. It must read as centred copy with the
    institutional marks along the FOOT of the card — not copy and logos clumped
    together mid-card with a bigger hole underneath — and its text must not be
    justified (justification belongs to the instructions reading band).

    WHAT CHANGED under THE LOGO FOOTER RULE (item 9): the strip is no longer
    inside the scroll region, so "at the foot" is now measured against the CARD,
    not against `.experimental-content`, and the copy is centred in the content
    region rather than in the space above the strip. The PROPERTY being asserted
    is unchanged — that is the point of measuring it rather than the markup.
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
            const card = document.querySelector('.screen-card');
            const text = document.querySelector('.section-text');
            const logo = document.querySelector('.logo-section');
            if (!el || !card || !text || !logo) return null;
            const r = el.getBoundingClientRect();
            const c = card.getBoundingClientRect();
            const t = text.getBoundingClientRect();
            const g = logo.getBoundingClientRect();
            const cs = getComputedStyle(el);
            const cardCs = getComputedStyle(card);
            const pad = parseFloat(cs.paddingBottom) || 0;
            const cardPad = parseFloat(cardCs.paddingBottom) || 0;
            return {align: getComputedStyle(text).textAlign,
                    pad: pad, cardPad: cardPad,
                    // free space above and below the copy INSIDE the content
                    // region (the strip is no longer one of its children)
                    aboveFree: Math.round(t.top - r.top - pad),
                    belowFree: Math.round(r.bottom - t.bottom - pad),
                    // and the strip's distance from the card's bottom edge
                    below: Math.round(c.bottom - g.bottom - cardPad),
                    overflows: el.scrollHeight > el.clientHeight + 2};
        }""")
        if not check(m is not None, f'{vp_name}: the gate renders text + logos'):
            context.close()
            continue
        check(m['align'] != 'justify',
              f'{vp_name}: the sentence is NOT justified (text-align: '
              f'{m["align"]})')
        check(m['below'] <= 2,
              f'{vp_name}: the logo strip sits at the FOOT OF THE CARD '
              f'({m["below"]}px of free space below it, net of the card\'s '
              f'{m["cardPad"]:.0f}px padding)')
        # The copy is centred in the content region: equal free space above and
        # below it. (Before item 9 this compared the space above the copy with
        # the space between the copy and the strip, because the strip was one of
        # the region's own children and shared its free space.)
        check(abs(m['aboveFree'] - m['belowFree']) <= 2,
              f'{vp_name}: the copy is centred in the content region '
              f'({m["aboveFree"]}px free above, {m["belowFree"]}px free '
              f'below)')
        geometry.setdefault('short_page', {})[vp_name] = m
        screenshot(page, 'lab_entry_gate_balance', vp_name)
        context.close()


def check_card_min_derivation(server, browser, facts):
    """Q. --card-min is derived from the TASK screen, and the derivation holds.

    change_requests item 5. The floor exists so the frame stops jumping between
    pages, and it is DERIVED rather than eyeballed: this leg renders the task
    pages with the floor disabled, records their NATURAL height, and requires
    that height to be at or below the floor actually shipped. If a study grows
    its task screen past the floor, this fails and says re-derive — which is the
    whole point of writing the number down.

    It also asserts the consequence Julian asked for: with the floor in place
    the card is the SAME HEIGHT on every page at a given viewport.
    """
    section('Q. The card floor is derived from the task screen, and holds')
    natural = {}
    for key, stop in (('task', TASK_PAGES[0]), ('payoff', TASK_PAGES[1])):
        session = create_session('prolific', num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        for vp_name, vp in VIEWPORTS.items():
            context = browser.new_context(viewport=vp)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(120)
            m = page.evaluate("""() => {
                const card = document.querySelector('.screen-card');
                const cs = getComputedStyle(card);
                const shippedMin = parseFloat(cs.minHeight) || 0;
                // Measure the card's NATURAL height: no floor, no ceiling.
                const prevMin = card.style.minHeight;
                const prevMax = card.style.maxHeight;
                card.style.minHeight = '0px';
                card.style.maxHeight = 'none';
                const nat = Math.round(card.getBoundingClientRect().height);
                card.style.minHeight = prevMin;
                card.style.maxHeight = prevMax;
                return {natural: nat, shippedMin: Math.round(shippedMin),
                        rendered: Math.round(card.getBoundingClientRect().height),
                        vh: window.innerHeight};
            }""")
            label = f'{key} @ {vp_name}'
            natural[label] = m
            check(m['natural'] <= m['shippedMin'] + 2,
                  f'{label}: the task screen\'s NATURAL height {m["natural"]}px '
                  f'is at or below the shipped floor {m["shippedMin"]}px '
                  f'({100 * m["natural"] / m["vh"]:.0f}vh vs '
                  f'{100 * m["shippedMin"] / m["vh"]:.0f}vh) — if this fails, '
                  f're-derive --card-derived in base.css from this number')
            # The trap the spec calls out: a px floor taller than the ceiling
            # would beat max-height and push the card to the screen edges.
            check(m['rendered'] <= 0.88 * m['vh'] + 2,
                  f'{label}: the floor never beats the 88vh ceiling '
                  f'(card {m["rendered"]}px in a {m["vh"]}px viewport)')
            context.close()
    geometry['card_min_derivation'] = natural

    # …and the point of the floor: one card height per viewport.
    # WIDE SCREENS ONLY. On a phone the card-scroll model is switched off
    # (improvement_suggestions item 1), so the card is deliberately as tall as
    # its content and pages differ — the floor still applies as a FLOOR, which
    # is what is asserted there instead.
    for vp_name, vp in VIEWPORTS.items():
        heights = {k: per[vp_name]['card']['h'] for k, per in facts.items()}
        geometry.setdefault('card_heights', {})[vp_name] = heights
        if vp['width'] <= 520:
            floor = 0.88 * vp['height']
            short = {k: h for k, h in heights.items() if h < floor - 2}
            check(not short,
                  f'{vp_name}: the phone card still honours the floor — no page '
                  f'is shorter than {floor:.0f}px ({sorted(short.items())})')
            print(f'  [note] {vp_name}: card heights vary by design here '
                  f'({min(heights.values())}..{max(heights.values())}px) — the '
                  f'page scrolls, not the card')
            continue
        spread = max(heights.values()) - min(heights.values())
        check(spread <= 2,
              f'{vp_name}: every page renders the SAME card height '
              f'(spread {spread}px across {len(heights)} pages: '
              f'{sorted(set(heights.values()))})')


def check_titles_centred(facts):
    """R. THE CONSTANT RULE: if a page has a title, the title is centred."""
    section('R. Every page title is centred (change_requests item 8)')
    for key, per_vp in facts.items():
        for vp, f in per_vp.items():
            title = f['title']
            if not title:
                continue
            check(title['textAlign'] == 'center',
                  f'{key} @ {vp}: the page title is centred '
                  f'(text-align: {title["textAlign"]})')


def check_scroll_catchment(server, browser):
    """S. The scroll gesture is caught over the FULL WIDTH of the card.

    change_requests item 6. The instructions page used to scroll a 720px band
    inside a 1200px card, so the wheel did nothing over ~230px of card on either
    side. Measured two ways: the scroller's box really spans the card, and a
    point 12px inside the card's left and right edges really lands on it.
    """
    section('S. The scroll catchment is the full card width')
    pages = (('instructions', 'lab', 'instructing',
              '.instruction-wrapper', '.instruction-block'),
             # The quiz page has the same shape: a scroller that used to be
             # capped at the reading band, with dead card either side of it.
             ('quiz', 'lab', 'quiz', '.experimental-content', '.quiz-block'))
    for key, config, stop, scroll_sel, band_sel in pages:
      code, _ = walk_to(server.base, create_session(config, num_participants=2),
                        stop)
      for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        m = page.evaluate("""([scrollSel, bandSel]) => {
            const card = document.querySelector('.screen-card');
            const wrap = document.querySelector(scrollSel);
            const block = document.querySelector(bandSel);
            if (!card || !wrap || !block) return null;
            const cs = getComputedStyle(card);
            const c = card.getBoundingClientRect();
            const w = wrap.getBoundingClientRect();
            const b = block.getBoundingClientRect();
            const innerL = c.left + parseFloat(cs.paddingLeft);
            const innerR = c.right - parseFloat(cs.paddingRight);
            const midY = w.top + w.height / 2;
            const hit = (x) => {
                const el = document.elementFromPoint(x, midY);
                return el ? (el === wrap || wrap.contains(el) ? 'scroller'
                             : el.className || el.tagName) : 'none';
            };
            return {innerW: Math.round(innerR - innerL),
                    wrapW: Math.round(w.width),
                    bandW: Math.round(b.width),
                    leftHit: hit(innerL + 12), rightHit: hit(innerR - 12),
                    scrolls: wrap.scrollHeight > wrap.clientHeight + 2};
        }""", [scroll_sel, band_sel])
        label = f'{key} @ {vp_name}'
        if not check(m is not None, f'{label}: the scroller and its band render'):
            context.close()
            continue
        # The scroller may be up to one reserved scrollbar gutter narrower on
        # each side than the card's content box; anything more is a band.
        check(m['wrapW'] >= m['innerW'] - 24,
              f'{label}: the scrolling element spans the card '
              f'({m["wrapW"]}px of a {m["innerW"]}px content box)')
        check(m['bandW'] < m['wrapW'] + 1,
              f'{label}: …while the TEXT stays in its band '
              f'({m["bandW"]}px inside the {m["wrapW"]}px scroller)')
        check(m['leftHit'] == 'scroller' and m['rightHit'] == 'scroller',
              f'{label}: a point 12px inside each card edge lands on the '
              f'scroller (left: {m["leftHit"]}, right: {m["rightHit"]})')
        geometry.setdefault('catchment', {})[label] = m
        context.close()


def check_scroll_cue(server, browser):
    """T. The pulsing V: wide, low, painted only while there is more — and NEVER
    on top of a line of content.

    change_requests item 4, plus the defect Julian reported on 2026-08-11: the
    cue was drawn across the results page's "Total" row, which reads as a
    rendering fault rather than as a scroll cue. So the shape is measured (wide
    and low, constant stroke) AND its band is measured OFF THE PIXELS with the
    cue suppressed: whatever is behind the V must be blank card.

    Run on the three pages that scroll at laptop size (results, quiz, consent).
    """
    section('T. The scroll cue: wide, low, and never over content')
    try:
        from PIL import Image
    except ImportError:
        check(False, 'Pillow is installed (needed to measure the cue band)')
        return
    pages = (('results', 'prolific', 'Results'),
             ('quiz', 'lab', 'quiz'),
             ('consent_prolific', 'prolific', 'welcome'))
    for key, config, stop in pages:
        code, _ = walk_to(server.base, create_session(config, num_participants=2),
                          stop)
        for vp_name in ('laptop_1280x720', 'phone_375x667'):
            context = browser.new_context(viewport=VIEWPORTS[vp_name])
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(250)
            m = page.evaluate("""() => {
                const el = document.querySelector('.experimental-content');
                const row = document.querySelector('.screen-card > .button-row');
                if (!el || !row) return null;
                const a = getComputedStyle(row, '::before');
                const b = getComputedStyle(row, '::after');
                const r = row.getBoundingClientRect();
                const cs = getComputedStyle(row);
                const cardCS = getComputedStyle(
                    document.querySelector('.screen-card'));
                return {overflows: el.scrollHeight > el.clientHeight + 2,
                        cls: el.className,
                        content: a.content, content2: b.content,
                        armW: parseFloat(a.width) || 0,
                        armH: parseFloat(a.height) || 0,
                        animation: a.animationName,
                        gutter: el.offsetWidth - el.clientWidth,
                        edgeY: r.top, edgeX: r.left + r.width / 2,
                        padTop: parseFloat(cs.paddingTop) || 0,
                        gapAbove: parseFloat(cardCS.rowGap || cardCS.gap) || 0,
                        contentBottom: el.getBoundingClientRect().bottom};
            }""")
            label = f'{key} @ {vp_name}'
            if not m or not m['overflows']:
                print(f'  [skip] {label}: content fits, no cue expected')
                context.close()
                continue
            check(m['content'] not in ('none', 'normal')
                  and m['content2'] not in ('none', 'normal'),
                  f'{label}: BOTH arms of the V are generated')
            check(m['animation'] == 'scroll-cue-pulse',
                  f'{label}: it pulses (animation-name: {m["animation"]})')
            # WIDE AND LOW, with a stroke thick enough to see: two 51px arms at
            # 18.4 degrees span 96px across and 16px down, drawn 4px thick.
            check(m['armW'] >= 45 and m['armH'] >= 3.5,
                  f'{label}: each arm is {m["armW"]}x{m["armH"]}px — the V is '
                  f'~{2 * m["armW"] * 0.94:.0f}px wide and ~16px tall, at a '
                  f'constant {m["armH"]}px stroke')
            # ITS BAND IS RESERVED WHITESPACE on both sides of the row's top
            # edge: the card's flex gap above, the row's own padding below.
            check(m['gapAbove'] >= 10 and m['padTop'] >= 10,
                  f'{label}: the cue band is empty by construction '
                  f'({m["gapAbove"]}px card gap above the edge, '
                  f'{m["padTop"]}px row padding below it)')
            check(m['gutter'] >= 8,
                  f'{label}: the scrollbar gutter is STILL reserved alongside '
                  f'it ({m["gutter"]}px) — the cue joins the other layers')

            # …AND NOTHING IS UNDERNEATH IT. Suppress the cue, then measure the
            # exact band it occupies: it must be blank card colour.
            page.add_style_tag(content="""
                .button-row::before, .button-row::after,
                .instruction-controls::before, .instruction-controls::after {
                    content: none !important; }""")
            page.wait_for_timeout(80)
            clip = dict(x=max(0, m['edgeX'] - 50), y=max(0, m['edgeY'] - 9),
                        width=100, height=18)
            path = os.path.join(OUT_DIR, '_cueband.png')
            page.screenshot(path=path, clip=clip)
            img = Image.open(path).convert('L')
            px = list(img.getdata())
            os.remove(path)
            darkness = 255 - (sum(px) / len(px))
            darkest = 255 - min(px)
            check(darkness < 0.8 and darkest < 12,
                  f'{label}: the 100x18px band the V occupies is blank card '
                  f'(mean darkness {darkness:.2f}, darkest pixel {darkest}) — '
                  f'nothing is painted underneath it')
            geometry.setdefault('scroll_cue', {})[label] = dict(
                m, band_darkness=round(darkness, 3), band_darkest=darkest)

            # …and it goes away at the end of the scroll, with the fade.
            page.evaluate("""() => { const el = document.querySelector(
                '.experimental-content'); el.scrollTop = el.scrollHeight; }""")
            page.wait_for_timeout(200)
            end = page.evaluate("""() => {
                const el = document.querySelector('.experimental-content');
                const row = document.querySelector('.screen-card > .button-row');
                return {cls: el.className,
                        content: getComputedStyle(row, '::before').content};
            }""")
            check('is-scrollable-down' not in end['cls'],
                  f'{label}: at the end of the scroll the cue is gone '
                  f'(class={end["cls"]!r})')
            context.close()

    # A separate pass for the instructions pager, whose cue hangs off the pager
    # row rather than a button row, and only when a slide overflows.
    code, _ = walk_to(server.base, create_session('lab', num_participants=2),
                      'instructing')
    context = browser.new_context(viewport=VIEWPORTS['phone_375x667'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(250)
    m = page.evaluate("""() => {
        const wrap = document.querySelector('.instruction-wrapper');
        const row = document.querySelector('.instruction-controls');
        const cs = getComputedStyle(row);
        return {overflows: wrap.scrollHeight > wrap.clientHeight + 2,
                cls: wrap.className,
                content: getComputedStyle(row, '::before').content,
                padTop: parseFloat(cs.paddingTop) || 0};
    }""")
    if m['overflows']:
        check(m['content'] not in ('none', 'normal'),
              'instructions @ phone: the pager carries the cue when a slide '
              'overflows')
        check(m['padTop'] >= 10,
              f'instructions @ phone: the pager reserves the cue strip '
              f'({m["padTop"]}px padding-top)')
        screenshot(page, 'instructions_scroll_cue', 'phone_375x667')
    else:
        print('  [skip] instructions @ phone: the first slide fits')
    context.close()


def check_task_progress(server, browser, facts):
    """U. The task screen states the round of the total, in text AND a bar."""
    section('U. Round-of-total progress on the task screens (item 7)')
    code, _ = walk_to(server.base, create_session('prolific', num_participants=2),
                      TASK_PAGES[0])
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(120)
        m = page.evaluate("""() => {
            const strip = document.querySelector('.progress-strip');
            const count = document.querySelector('.progress-count');
            const track = document.querySelector('.progress-track');
            const fill = document.querySelector('.progress-fill');
            if (!strip || !count || !track || !fill) return null;
            const t = track.getBoundingClientRect();
            const f = fill.getBoundingClientRect();
            return {text: count.textContent.trim(),
                    trackW: Math.round(t.width), fillW: Math.round(f.width),
                    trackH: Math.round(t.height),
                    fillBg: getComputedStyle(fill).backgroundColor,
                    pct: t.width ? Math.round(100 * f.width / t.width) : null};
        }""")
        label = f'task @ {vp_name}'
        if not check(m is not None, f'{label}: the progress strip renders'):
            context.close()
            continue
        check(m['text'].startswith('Round 1 of '),
              f'{label}: the text line names the round AND the total '
              f'({m["text"]!r})')
        check(0 < m['fillW'] <= m['trackW'] + 1 and 3 <= m['trackH'] <= 8,
              f'{label}: the bar is drawn and filled to {m["pct"]}% of a '
              f'{m["trackW"]}x{m["trackH"]}px track')
        geometry.setdefault('task_progress', {})[vp_name] = m
        context.close()


def _money(text):
    """The number out of an oTree currency string, for adding up a receipt."""
    import re
    m = re.findall(r'-?\d+(?:[.,]\d+)?', (text or '').replace(',', ''))
    return float(m[0]) if m else None


def check_pager_aligns_with_text(server, browser):
    """W. The instructions pager shares the TEXT's edges (round-2 item 12).

    Back and Next used to sit on the edges of the CARD while the instructions
    text is held to `--read-measure`, so the pager floated outside the column it
    pages through. `.instruction-controls` now takes the same measure.

    MEASURED AGAINST THE RENDERED TEXT, not against the token: reading the CSS
    back would only prove the stylesheet says what it says, and the whole failure
    mode of a layout change is that nothing errors. The comparison is
    button-edge against paragraph-edge, at all three viewports.

    The counter between them must stay centred in that narrower span — it is the
    flex row's middle item, so the assertion is that its centre matches the
    row's centre, which is what "still centred" has to mean once the row is no
    longer the width of the card.
    """
    section('W. The instructions pager lines up with the text (item 12)')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'instructing')
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        m = page.evaluate("""() => {
            const row = document.querySelector('.instruction-controls');
            const back = document.querySelector('#prevBtn');
            const next = document.querySelector('#nextBtn');
            const counter = document.querySelector('.instruction-progress');
            // The visible slide's own running BODY copy — the column the pager
            // belongs to.
            // TWO PARAGRAPHS MUST BE EXCLUDED, and picking the first <p> blind
            // measures the wrong thing (it did, on the first run): the shipped
            // instructions open with a TEMPLATE NOTE carrying an inline
            // `font-size: 14px`, and `--read-measure` is `68ch`, which resolves
            // against each element's OWN font — so that note's measure is
            // ~519px against body copy's ~726px, and the leg failed against a
            // paragraph the rule was never about. Any <p> in a hidden slide has
            // a zero-width box for the same class of reason.
            const block = document.querySelector('.instruction-block');
            const p = block ? Array.from(block.querySelectorAll(':scope > p'))
                .find(el => !(el.getAttribute('style') || '')
                        .includes('font-size')
                     && el.getBoundingClientRect().width > 0) : null;
            if (!row || !back || !next || !p) return null;
            const R = row.getBoundingClientRect(), B = back.getBoundingClientRect();
            const N = next.getBoundingClientRect(), P = p.getBoundingClientRect();
            const C = counter ? counter.getBoundingClientRect() : null;
            return {textLeft: Math.round(P.left), textRight: Math.round(P.right),
                    backLeft: Math.round(B.left), nextRight: Math.round(N.right),
                    rowLeft: Math.round(R.left), rowRight: Math.round(R.right),
                    rowCentre: Math.round((R.left + R.right) / 2),
                    counterCentre: C ? Math.round((C.left + C.right) / 2) : null,
                    textW: Math.round(P.width), rowW: Math.round(R.width),
                    // The COMPUTED caps, so "they come from ONE rule" is
                    // asserted and not merely implied by the edges agreeing
                    // today. The pager and the slide BLOCK are the two elements
                    // in that rule; the running text carries no cap of its own
                    // any more and simply fills the block, which is checked
                    // separately below.
                    rowMaxW: getComputedStyle(row).maxWidth,
                    blockMaxW: getComputedStyle(block).maxWidth,
                    textMaxW: getComputedStyle(p).maxWidth};
        }""")
        if not check(m is not None, f'{vp_name}: the instructions page renders '
                                    f'a pager and running text'):
            context.close()
            continue
        check(abs(m['backLeft'] - m['textLeft']) <= 2,
              f'{vp_name}: Back\'s LEFT edge is the text\'s left edge '
              f'({m["backLeft"]} vs {m["textLeft"]})')
        check(abs(m['nextRight'] - m['textRight']) <= 2,
              f'{vp_name}: Next\'s RIGHT edge is the text\'s right edge '
              f'({m["nextRight"]} vs {m["textRight"]})')
        if m['counterCentre'] is not None:
            check(abs(m['counterCentre'] - m['rowCentre']) <= 3,
                  f'{vp_name}: the counter stays centred within that narrower '
                  f'span ({m["counterCentre"]} vs centre {m["rowCentre"]})')
        # ONE RULE, NOT TWO AGREEING (item 16). The edges lining up could also
        # happen with two rules that currently produce the same number and drift
        # on the next type-scale change — precisely the failure this was rebuilt
        # to make impossible. Two assertions pin the shape itself:
        check(m['rowMaxW'] == m['blockMaxW'],
              f'{vp_name}: the pager and the slide block resolve the SAME '
              f'max-width, i.e. they still come from ONE rule '
              f'({m["rowMaxW"]} == {m["blockMaxW"]})')
        check(m['textMaxW'] == 'none',
              f'{vp_name}: the running text carries NO cap of its own — the '
              f'second constraint that made these disagree is still gone '
              f'(got {m["textMaxW"]})')
        geometry.setdefault('pager_alignment', {})[vp_name] = m
        screenshot(page, 'pager_alignment', vp_name)
        context.close()


def check_results_table_look(server, browser):
    """V2. The per-round payoff table (round-2 item 8) and its accordion (10).

    THE LOOK IS PORTED BY REASON FROM exp_pilots, so this leg measures the
    REASONS rather than a screenshot: the header is quiet and sits on a stronger
    rule than the body rows, the body digits are TABULAR (which is most of why
    the table reads as tidy and is entirely invisible to a DOM test that only
    checks text), the last row drops its border, and a paid round carries BOTH
    an accent wash and an inset left bar — the second signal being what makes
    the paid rounds findable in a long list.

    ITEM 10 IS MEASURED HERE TOO, because it is the same table: the lab opens
    with it EXPANDED and Prolific still opens COLLAPSED, and in both cases the
    accordion must still work. The initial state is asserted through the three
    things that must agree — the wrapper's visibility, the button's
    aria-expanded and the caret's rotation class — since a disclosure whose ARIA
    contradicts the screen tells a screen-reader user the opposite of the truth.
    """
    section('V2. The per-round table: the ported look (8) + the accordion (10)')
    for key, config, expect_open in (('results_lab', 'lab', True),
                                     ('results_prolific', 'prolific', False)):
        code, _ = walk_to(server.base,
                          create_session(config, num_participants=2), 'Results')
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(150)
        state = page.evaluate("""() => {
            const wrap = document.querySelector('#results-table-wrapper');
            const btn = document.querySelector('#results-toggle');
            const arrow = document.querySelector('#results-arrow');
            if (!wrap || !btn) return null;
            return {hidden: wrap.classList.contains('is-hidden'),
                    aria: btn.getAttribute('aria-expanded'),
                    arrowOpen: arrow ? arrow.classList.contains('open') : null,
                    visibleH: Math.round(
                        wrap.getBoundingClientRect().height)};
        }""")
        if not check(state is not None, f'{key}: the page has the accordion'):
            context.close()
            continue
        check(state['hidden'] is not expect_open,
              f'{key}: the table starts '
              f'{"EXPANDED" if expect_open else "collapsed"} '
              f'(is-hidden={state["hidden"]})')
        check(state['aria'] == ('true' if expect_open else 'false'),
              f'{key}: aria-expanded agrees with what is on screen '
              f'(got {state["aria"]!r})')
        check(state['arrowOpen'] is expect_open,
              f'{key}: the caret agrees too (open={state["arrowOpen"]})')
        check((state['visibleH'] > 0) is expect_open,
              f'{key}: …and it is measurably {"open" if expect_open else "closed"} '
              f'({state["visibleH"]}px tall)')
        # THE ACCORDION STILL WORKS in both — item 10 changed the initial state
        # only, and Julian was explicit the accordion stays.
        page.click('#results-toggle')
        page.wait_for_timeout(120)
        after = page.evaluate(
            """() => ({hidden: document.querySelector('#results-table-wrapper')
                        .classList.contains('is-hidden'),
                      aria: document.querySelector('#results-toggle')
                        .getAttribute('aria-expanded')})""")
        check(after['hidden'] is not state['hidden'],
              f'{key}: clicking the control still toggles the table '
              f'({state["hidden"]} -> {after["hidden"]})')
        check(after['aria'] == ('false' if after['hidden'] else 'true'),
              f'{key}: …and aria-expanded follows it (got {after["aria"]!r})')
        if after['hidden']:
            page.click('#results-toggle')   # leave it open to measure the look
            page.wait_for_timeout(120)

        look = page.evaluate("""() => {
            const th = document.querySelector('.results-table th');
            const tds = Array.from(document.querySelectorAll(
                '.results-table tbody td'));
            const rows = Array.from(document.querySelectorAll(
                '.results-table tbody tr'));
            if (!th || !tds.length) return null;
            const last = rows[rows.length - 1].querySelector('td');
            const paid = rows.find(r => r.classList.contains('selected-row'));
            const paidTd = paid ? paid.querySelector('td') : null;
            const ths = getComputedStyle(th);
            return {
                headTransform: ths.textTransform,
                headSpacing: ths.letterSpacing,
                headBorder: parseFloat(ths.borderBottomWidth) || 0,
                bodyBorder: parseFloat(
                    getComputedStyle(tds[0]).borderBottomWidth) || 0,
                bodyNumeric: getComputedStyle(tds[0]).fontVariantNumeric,
                lastBorder: parseFloat(
                    getComputedStyle(last).borderBottomWidth) || 0,
                paidBg: paidTd ? getComputedStyle(paidTd).backgroundColor : null,
                paidShadow: paidTd ? getComputedStyle(paidTd).boxShadow : null,
                paidPill: paid ? !!paid.querySelector('.tag.paid-tag') : null,
                plainPill: rows.some(
                    r => !r.classList.contains('selected-row')
                         && r.querySelector('.tag.paid-tag')),
                nRows: rows.length};
        }""")
        if not check(look is not None, f'{key}: the table renders rows'):
            context.close()
            continue
        check(look['headTransform'] == 'uppercase'
              and look['headSpacing'] not in ('normal', '0px'),
              f'{key}: the header is uppercase and letter-spaced '
              f'({look["headTransform"]}, {look["headSpacing"]})')
        check(look['headBorder'] >= look['bodyBorder'],
              f'{key}: the header sits on a rule at least as strong as the '
              f'body rows ({look["headBorder"]} vs {look["bodyBorder"]})')
        # THE ONE THAT MATTERS MOST AND IS INVISIBLE TO EVERY OTHER TEST.
        check('tabular-nums' in look['bodyNumeric'],
              f'{key}: body cells use TABULAR numerals so the digits line up '
              f'down the column (font-variant-numeric: {look["bodyNumeric"]})')
        check(look['lastBorder'] == 0,
              f'{key}: the last row drops its bottom border '
              f'({look["lastBorder"]}px)')
        if look['paidBg'] is not None:
            check(look['paidBg'] not in ('rgba(0, 0, 0, 0)', 'transparent'),
                  f'{key}: a paid round has an accent row wash '
                  f'({look["paidBg"]})')
            check('inset' in (look['paidShadow'] or ''),
                  f'{key}: …AND an inset left bar, the second signal that makes '
                  f'it findable in a long list ({look["paidShadow"]})')
            check(look['paidPill'] is True,
                  f'{key}: …and it is named by a pill tag, not just coloured')
            check(look['plainPill'] is False,
                  f'{key}: an unpaid round carries NO paid pill')
        else:
            print(f'  [note] {key}: no paid round in this walk '
                  f'({look["nRows"]} rows) — highlight not measured')
        geometry.setdefault('results_table', {})[key] = dict(look, **state)
        screenshot(page, f'results_table_{key}', 'laptop_1280x720')
        context.close()


def check_sepa_warning_is_a_warning(server, browser):
    """V3. The non-SEPA bank warning LOOKS like a warning (round-2 item 4).

    It shipped in the quiet grey `.panel`, which is the component for secondary
    information — so the one sentence that can still stop a payment from failing
    read as a footnote. It now takes `.panel--warning`.

    MEASURED ON RENDERED COLOUR, not on the class name: the point of the change
    is what a participant sees, and a class that exists but resolves to the same
    grey would pass a DOM check while changing nothing. The comparison is
    against the plain `.panel` on the same page family, so this stays true if
    the palette is retuned.

    The lab config is the one that collects bank details; `sepa` is 0 only for a
    non-SEPA IBAN, so the panel is staged by writing the field directly.
    """
    section('V3. The SEPA warning is red, not grey (item 4)')
    session = create_session('lab', num_participants=2)
    code, _ = walk_to(server.base, session, 'Results')
    if not check(_force_non_sepa(code),
                 'staged a non-SEPA bank account for the results page'):
        return
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    m = page.evaluate("""() => {
        const warn = document.querySelector('.panel--warning');
        if (!warn) return null;
        const cs = getComputedStyle(warn);
        return {text: warn.textContent.replace(/\\s+/g, ' ').trim(),
                bg: cs.backgroundColor, border: cs.borderColor,
                shadow: cs.boxShadow,
                isPanel: warn.classList.contains('panel')};
    }""")
    if not check(m is not None,
                 'the non-SEPA warning panel is on the page'):
        context.close()
        return
    check('not in SEPA' in m['text'] and 'experimenter' in m['text'],
          f'it is the right panel (says what it must): {m["text"][:80]!r}')
    check(m['isPanel'],
          'it is still a .panel — a VARIANT of the component, not a new one')
    # Red, measured: the red channel must dominate in both the tint and the
    # border, which is what distinguishes it from the grey it replaced.
    def _rgb(s):
        nums = [int(x) for x in re.findall(r'\d+', s or '')[:3]]
        return nums if len(nums) == 3 else None
    bg, bd = _rgb(m['bg']), _rgb(m['border'])
    check(bg is not None and bg[0] > bg[1] and bg[0] > bg[2],
          f'the panel is tinted RED, not grey (background {m["bg"]})')
    check(bd is not None and bd[0] > bd[1] + 30 and bd[0] > bd[2] + 30,
          f'…and its border is the danger colour (border {m["border"]})')
    check('inset' in (m['shadow'] or ''),
          f'…with the inset bar that carries the alarm at a glance '
          f'({m["shadow"]})')
    geometry['sepa_warning'] = m
    screenshot(page, 'sepa_warning', 'laptop_1280x720')
    context.close()


def _force_non_sepa(code):
    """Set the outro player's `sepa` field to 0 for this participant.

    A non-SEPA IBAN cannot be typed in by the walker (the lab bank form is only
    shown in some configs and the field is computed from the country code), so
    the state is staged directly. The server runs IN THIS PROCESS against the
    same throwaway database (see the module header), so an ORM write here is
    what the next page load reads. Returns False if the row was not there, so
    the leg skips loudly rather than asserting on a page it failed to stage.
    """
    try:
        from otree.common import get_models_module
        Player = get_models_module('outro').Player
        s = DBSession()
        try:
            rows = (s.query(Player)
                    .join(Participant, Player.participant_id == Participant.id)
                    .filter(Participant.code == code).all())
            if not rows:
                return False
            for row in rows:
                row.sepa = 0
            s.commit()
            return True
        finally:
            s.close()
    except Exception as exc:
        print(f'  [note] could not stage a non-SEPA account: {exc}')
        return False


def check_results_receipt(server, browser):
    """V. The results receipt says the truth: the lines add up to the total.

    change_requests item 11 — this one is not cosmetic. The line wording is
    participant-facing and the figures must be the REAL ones, so the check
    reads the rendered receipt and adds it up.
    """
    section('V. The results receipt: real figures that add up (item 11)')
    code, _ = walk_to(server.base, create_session('prolific', num_participants=2),
                      'Results')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    m = page.evaluate("""() => {
        const total = document.querySelector('.payout-total');
        const lines = Array.from(document.querySelectorAll('.payout-line')).map(
            l => ({label: l.querySelector('span').textContent.trim(),
                   amount: l.querySelector('.amount').textContent.trim(),
                   isTotal: l.classList.contains('total')}));
        const summary = document.querySelector('.payment-summary');
        const card = document.querySelector('.screen-card');
        const s = summary ? summary.getBoundingClientRect() : null;
        const c = card.getBoundingClientRect();
        const cs = getComputedStyle(card);
        return {headline: total ? total.textContent.trim() : null, lines: lines,
                summaryCentre: s ? (s.left + s.right) / 2 : null,
                cardCentre: (c.left + parseFloat(cs.paddingLeft)
                             + c.right - parseFloat(cs.paddingRight)) / 2,
                summaryW: s ? Math.round(s.width) : null,
                cardW: Math.round(c.width)};
    }""")
    if not check(m and m['headline'], 'the receipt renders a headline figure'):
        context.close()
        return
    rows = {l['label']: _money(l['amount']) for l in m['lines']}
    total_row = [l for l in m['lines'] if l['isTotal']]
    check('Base payment' in rows and 'Bonus from your decisions' in rows,
          f'the breakdown names its lines in participant language '
          f'({list(rows)})')
    check(len(total_row) == 1, 'there is exactly one Total row')
    parts = sum(v for l, v in rows.items() if l != 'Total' and v is not None)
    headline = _money(m['headline'])
    check(headline is not None and abs(parts - headline) < 0.005,
          f'the lines ADD UP to the headline: {parts} vs {headline} '
          f'({rows})')
    check(abs(_money(total_row[0]['amount']) - headline) < 0.005,
          f'…and the Total row matches the headline '
          f'({total_row[0]["amount"]} vs {m["headline"]})')
    check(abs(m['summaryCentre'] - m['cardCentre']) <= 2,
          f'the summary block is CENTRED in the card '
          f'({m["summaryCentre"]:.0f} vs {m["cardCentre"]:.0f})')
    check(m['summaryW'] < m['cardW'] / 2,
          f'…and it is a narrow receipt, not a full-width panel '
          f'({m["summaryW"]}px in a {m["cardW"]}px card)')
    geometry['results_receipt'] = dict(m, rows=rows)
    screenshot(page, 'results_receipt', 'laptop_1280x720')
    context.close()

    # …AND THE TOTAL ROW IS READABLE, not cut and dimmed at the fold. It is the
    # line that proves the breakdown adds up, so on the two viewports where the
    # page can fit it, it must clear the scroll fade (46px, base.css) entirely.
    for vp_name in ('laptop_1280x720', 'desktop_1512x1200', 'phone_375x667'):
        context = browser.new_context(viewport=VIEWPORTS[vp_name])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        t = page.evaluate("""() => {
            const el = document.querySelector('.experimental-content');
            const total = document.querySelector('.payout-line.total');
            const head = document.querySelector('.payout-total');
            const r = el.getBoundingClientRect();
            const tr = total.getBoundingClientRect();
            const hr = head.getBoundingClientRect();
            const fade = parseFloat(getComputedStyle(document.documentElement)
                .getPropertyValue('--scroll-fade')) || 46;
            return {clearOfFold: Math.round(r.bottom - tr.bottom),
                    fade: fade,
                    headlineVisible: hr.bottom <= r.bottom && hr.top >= r.top};
        }""")
        check(t['headlineVisible'],
              f'{vp_name}: the headline "Total earned" figure is on screen '
              f'without scrolling')
        if vp_name == 'phone_375x667':
            # HONEST LIMIT: a 375x667 phone gives the region ~325px and this
            # page's own copy is ~640px, so no arrangement puts the breakdown's
            # last row above the fold. What matters there is that the HEADLINE
            # total is visible (checked above) and the page announces that it
            # scrolls (checked in D1/D2 and T).
            print(f'  [note] {vp_name}: the Total ROW sits {t["clearOfFold"]}px '
                  f'above the fold, inside the {t["fade"]:.0f}px fade — '
                  f'physically unfittable on this viewport; the headline figure '
                  f'is fully visible')
        else:
            check(t['clearOfFold'] >= t['fade'],
                  f'{vp_name}: the Total row clears the fold by '
                  f'{t["clearOfFold"]}px, past the {t["fade"]:.0f}px fade — it '
                  f'is not dimmed')
        geometry.setdefault('results_total_row', {})[vp_name] = t
        context.close()


def check_reread_dialog(server, browser):
    """W. The online quiz's at-will re-read dialog (item 17, Prolific half).

    Opens whether or not anything has been failed, shows the REAL instructions,
    disables the quiz's submit while it is open, and closes again. The LAB must
    NOT have the button at all: Julian's rule is that a lab participant re-reads
    only after a failed attempt, then raises their hand.
    """
    section('W. The online re-read dialog opens, reads, and closes (item 17)')
    code, _ = walk_to(server.base, create_session('prolific', num_participants=2),
                      'quiz')
    for vp_name in ('laptop_1280x720', 'phone_375x667'):
        context = browser.new_context(viewport=VIEWPORTS[vp_name])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(200)
        label = f'quiz_prolific @ {vp_name}'
        if not check(page.locator('#rereadOpen').count() == 1,
                     f'{label}: the re-read button is on the page, unfailed'):
            context.close()
            continue
        check(page.locator('#rereadOpen.next-button').count() == 0,
              f'{label}: it is NOT a .next-button (Enter must still submit)')
        page.click('#rereadOpen')
        page.wait_for_timeout(200)
        m = page.evaluate("""() => {
            const back = document.getElementById('reread-backdrop');
            const body = document.getElementById('reread-body');
            const blocks = Array.from(body.querySelectorAll('.instruction-block'));
            const visible = blocks.filter(
                b => b.getBoundingClientRect().height > 0);
            const submits = Array.from(document.querySelectorAll(
                '.screen-card input[type="submit"]'));
            const r = back.getBoundingClientRect();
            return {hidden: back.hidden,
                    covers: Math.round(r.width) >= window.innerWidth
                            && Math.round(r.height) >= window.innerHeight,
                    blocks: blocks.length, visible: visible.length,
                    scrolls: body.scrollHeight > body.clientHeight + 2,
                    submitsDisabled: submits.every(s => s.disabled),
                    text: body.innerText.slice(0, 400)};
        }""")
        check(not m['hidden'] and m['covers'],
              f'{label}: the dialog opens over the whole viewport')
        check(m['blocks'] >= 2 and m['visible'] == m['blocks'],
              f'{label}: EVERY instruction block is visible inside it '
              f'({m["visible"]} of {m["blocks"]}) — the pager hides all but the '
              f'first outside the dialog')
        check('Instructions' in m['text'] or len(m['text']) > 120,
              f'{label}: it contains the real instructions text')
        check(m['submitsDisabled'],
              f'{label}: the quiz submit is disabled while it is open')
        screenshot(page, 'quiz_reread_dialog', vp_name)
        # Escape closes it and the submit comes back.
        page.keyboard.press('Escape')
        page.wait_for_timeout(150)
        after = page.evaluate("""() => ({
            hidden: document.getElementById('reread-backdrop').hidden,
            enabled: Array.from(document.querySelectorAll(
                '.screen-card input[type="submit"]')).every(s => !s.disabled)})""")
        check(after['hidden'] and after['enabled'],
              f'{label}: Escape closes it and re-enables the submit')
        geometry.setdefault('reread_dialog', {})[vp_name] = m
        context.close()

    # …and the LAB does not have it at all.
    code, _ = walk_to(server.base, create_session('lab', num_participants=2),
                      'quiz')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    check(page.locator('#rereadOpen').count() == 0,
          'the LAB quiz has NO at-will re-read button (its re-read is offered '
          'only after a failed attempt)')
    context.close()


def check_lab_experimenter_notice(server, browser):
    """W2. The lab "raise your hand" notice, including its escalated form.

    Driven with quiz_reread OFF, which is the case that used to get NO help at
    all (the notice required the re-read module; fixed 2026-08-12) — so this
    also proves the hole stays closed. Past TWICE comprehension_max_failures the
    notice gains a line naming the attempt count, and the point of measuring
    rather than grepping is that the second line must actually RENDER inside the
    card: a modal whose card is a fixed height would push it out of view with
    nothing failing anywhere.

    Julian's copy is verbatim and deliberately does NOT offer "you can keep
    trying" (see intro/templates/quiz.html) — asserted here, because a helpful
    edit putting it back would otherwise be invisible.
    """
    section('W2. The lab experimenter notice renders, escalates, dismisses')
    threshold = 2
    session = create_session(
        'lab', num_participants=2,
        modified_session_config_fields={'quiz_reread': False,
                                        'comprehension_max_failures': threshold})
    code, _ = walk_to(server.base, session, 'quiz')
    wrong = {}
    for item in QUIZ_ITEMS:
        alternatives = [c for c in item['choices'] if c != item['answer']]
        wrong[item['field']] = alternatives[0] if alternatives else item['answer']
    s = requests.Session()
    r = s.get(f'{server.base}/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(2 * threshold):          # escalate: 2x the threshold
        if page_of(r.url) != 'quiz':
            break
        fp = FormParser()
        fp.feed(r.text)
        r = s.post(r.url, data=build_payload(fp.inputs, {}, wrong),
                   allow_redirects=True)
    if not check(page_of(r.url) == 'quiz',
                 f'{2 * threshold} wrong submissions and the lab participant is '
                 f'still on the quiz (now {page_of(r.url)}) — never ejected'):
        return

    for vp_name in ('laptop_1280x720', 'phone_375x667'):
        context = browser.new_context(viewport=VIEWPORTS[vp_name])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(250)
        label = f'quiz_notice @ {vp_name}'
        m = page.evaluate("""() => {
            const back = document.getElementById('quiz-modal-backdrop');
            if (!back) return {present: false};
            const card = back.querySelector('.modal-card');
            const r = back.getBoundingClientRect();
            const cr = card.getBoundingClientRect();
            const paras = Array.from(card.querySelectorAll('.modal-text'));
            return {present: true, hidden: back.hidden,
                    covers: Math.round(r.width) >= window.innerWidth
                            && Math.round(r.height) >= window.innerHeight,
                    centredX: Math.abs((cr.left + cr.right) / 2
                                       - window.innerWidth / 2) <= 2,
                    // Every line must be INSIDE the card, not spilling past it.
                    lines: paras.map(p => ({
                        text: p.innerText.trim(),
                        h: Math.round(p.getBoundingClientRect().height),
                        inside: p.getBoundingClientRect().bottom <= cr.bottom + 1})),
                    bolds: Array.from(card.querySelectorAll('strong'))
                               .map(b => b.innerText.trim()),
                    text: card.innerText.trim(),
                    dismissable: !!card.querySelector('.modal-actions button')};
        }""")
        if not check(m['present'] and not m['hidden'],
                     f'{label}: the notice is on the page and revealed'):
            context.close()
            continue
        check(m['covers'] and m['centredX'],
              f'{label}: it dims the whole viewport, card centred')
        flat = ' '.join(m['text'].split())
        check('raise your hand and speak to the experimenter' in flat,
              f'{label}: it says to raise your hand ({flat[:90]!r})')
        check(any('raise your hand' in b.lower() for b in m['bolds']),
              f'{label}: "raise your hand" is BOLD (bold runs: {m["bolds"]})')
        check(f'You have made {2 * threshold} attempts so far' in flat,
              f'{label}: escalated — it names the attempt count '
              f'({2 * threshold})')
        check(len(m['lines']) == 2 and all(l['h'] > 0 for l in m['lines']),
              f'{label}: BOTH lines are rendered with height '
              f'({[l["h"] for l in m["lines"]]})')
        check(all(l['inside'] for l in m['lines']),
              f'{label}: neither line spills out of the card')
        check('keep trying' not in flat.lower(),
              f'{label}: it does NOT tell them they can keep trying (Julian\'s '
              f'copy — do not add it back)')
        check(m['dismissable'], f'{label}: it is dismissible')
        screenshot(page, 'quiz_experimenter_notice', vp_name)
        geometry.setdefault('experimenter_notice', {})[vp_name] = m
        # Dismissible AT THE ESCALATED STAGE too: nothing ever blocks the quiz.
        page.click('#quiz-modal-backdrop .modal-actions button')
        page.wait_for_timeout(150)
        gone = page.evaluate(
            "() => document.getElementById('quiz-modal-backdrop').hidden")
        check(gone, f'{label}: dismissing it returns the participant to the quiz')
        context.close()


def check_warning_modal(server, browser):
    """X. A validation failure is a centred modal, not a banner (items 9 + 10).

    Driven on the DEMOGRAPHICS page, deliberately. The consent page's radios
    carry oTree's `required`, so a browser blocks that submit itself and the
    server-side banner never appears — testing there would have proved nothing.
    Demographics' fields are all blank=True and the page's own error_message()
    does the validating, so an empty submit produces exactly the server-rendered
    `.otree-form-errors` banner this feature is about.

    The same leg then checks item 10: after a failed submit the answers already
    given are still there.
    """
    section('X. Validation errors open a centred, dimming modal (items 9 + 10)')
    code, _ = walk_to(server.base, create_session('lab', num_participants=2),
                      'Demographics')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    # Submit with nothing filled in: the page's error_message() rejects it and
    # oTree re-renders with its own banner, which the helper must replace.
    with page.expect_navigation(wait_until='load'):
        page.click('.button-row input[type="submit"]')
    page.wait_for_timeout(300)
    m = page.evaluate("""() => {
        const banner = document.querySelector('.otree-form-errors');
        const back = document.getElementById('warning-modal-backdrop');
        if (!back) return {banner: !!banner, modal: false};
        const r = back.getBoundingClientRect();
        const card = back.querySelector('.modal-card');
        const cr = card.getBoundingClientRect();
        const cs = getComputedStyle(back);
        return {banner: !!banner,
                bannerVisible: banner ? banner.getBoundingClientRect().height > 0
                                      : false,
                modal: true,
                text: card.innerText.trim(),
                position: cs.position, dim: cs.backgroundColor,
                covers: Math.round(r.width) >= window.innerWidth
                        && Math.round(r.height) >= window.innerHeight,
                centredX: Math.abs((cr.left + cr.right) / 2
                                   - window.innerWidth / 2) <= 2,
                centredY: Math.abs((cr.top + cr.bottom) / 2
                                   - window.innerHeight / 2) <= 2,
                submitsDisabled: Array.from(document.querySelectorAll(
                    '.screen-card input[type="submit"]')).every(s => s.disabled)};
    }""")
    check(m['banner'], 'oTree did render its validation error (the page rejected '
                       'the empty submit)')
    check(m['modal'], 'the shared warning modal was built from it')
    if m['modal']:
        check(not m['bannerVisible'],
              'the plain banner is hidden — nothing pushes the page down')
        check(m['position'] == 'fixed' and m['covers'],
              'the modal dims the WHOLE screen (position:fixed, full viewport)')
        check(m['centredX'] and m['centredY'],
              'its card is centred both ways')
        check(m['submitsDisabled'],
              'the page submit is disabled while it is open (so Enter dismisses '
              'the modal instead of re-submitting)')
        check(len(m['text']) > 5, f'it says what is wrong ({m["text"][:60]!r})')
        geometry['warning_modal'] = m
        screenshot(page, 'demographics_warning_modal', 'laptop_1280x720')

        # --- item 10: the answers survive the next failed submit -------------
        page.click('#warning-modal-backdrop .modal-ok-button')
        page.fill('#id_age', '42')
        page.check('input[name="gender"][value="Female"]')
        with page.expect_navigation(wait_until='load'):
            page.click('.button-row input[type="submit"]')   # IBAN still empty
        page.wait_for_timeout(400)
        kept = page.evaluate("""() => {
            const age = document.getElementById('id_age');
            const gender = document.querySelector(
                'input[name="gender"]:checked');
            return {age: age ? age.value : null,
                    gender: gender ? gender.value : null,
                    stillHere: !!document.getElementById('id_age')};
        }""")
        check(kept['stillHere'], 'the page was re-rendered (submit rejected '
                                 'again — the IBAN is still missing)')
        check(kept['age'] == '42',
              f'ITEM 10: the age already typed is still there after the error '
              f'(got {kept["age"]!r})')
        check(kept['gender'] == 'Female',
              f'ITEM 10: …and the gender already chosen is still selected '
              f'(got {kept["gender"]!r})')
        geometry['preserved_answers'] = kept
    context.close()


def check_consent_single_question(server, browser, facts):
    """AA. The consent page asks its question ONCE, in one voice.

    improvement_suggestions item 3, verified rather than re-implemented: the
    field's `label` is `""` (before/__init__.py), which suppresses oTree's own
    question line above the options. This pins that — and pins that no OTHER
    field on the page reintroduces one, which is the half a one-line diff cannot
    show.
    """
    section('AA. The consent page asks one question, once (item 3)')
    for key, config in (('consent_prolific', 'prolific'), ('consent_lab', 'lab')):
        text = ' '.join(facts[key]['laptop_1280x720']['text'].split())
        check('Do you consent to take part' not in text,
              f'{key}: oTree\'s own field label is NOT rendered')
        code, _ = walk_to(server.base, create_session(config, num_participants=2),
                          'welcome')
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(150)
        m = page.evaluate("""() => {
            // Every label oTree or the template renders on this page, other
            // than the per-option labels inside the choice cards.
            const labels = Array.from(document.querySelectorAll(
                '.experimental-content label'))
                .filter(l => !l.closest('.form-check, .mc-option'))
                .map(l => l.textContent.trim())
                .filter(t => t.length);
            const qs = (document.querySelector('.experimental-content')
                .innerText.match(/\\?/g) || []).length;
            return {labels: labels, questionMarks: qs};
        }""")
        check(not m['labels'],
              f'{key}: no other field puts a labelled question above the '
              f'options (found {m["labels"]})')
        check(m['questionMarks'] == 0,
              f'{key}: the page asks nothing a second time — {m["questionMarks"]} '
              f'question marks in the content region')
        geometry.setdefault('consent_question', {})[key] = m
        context.close()


def check_page_anatomy(server, browser, facts):
    """AB. Which pages carry a logo strip, and where each page's title comes from.

    improvement_suggestions item 5, VERIFIED rather than assumed. Two separate
    claims, and they do not have the same answer:

      * the logo strip is now entry-and-ending only (lab gate, consent, the
        Prolific-ID page having lost it, the ending, results) — asserted here so
        a stray include shows up;
      * the instructions page's title. Every other page puts its title in the
        header strip as `.header-title`. The instructions page does NOT: each
        slide's own <h2> is the title, by the documented rule in
        writing_instructions.md. This asserts that CURRENT state explicitly, so
        the divergence is visible in the run rather than being something someone
        has to notice.
    """
    section('AB. Page anatomy: logo strips, and where the title comes from')
    expected_logo = {'lab_entry_gate', 'consent_lab', 'consent_prolific',
                     'screened_out', 'results'}
    for key, per_vp in facts.items():
        has = per_vp['laptop_1280x720']['has_logo_strip']
        if key in expected_logo:
            check(has, f'{key}: carries the institutional logo strip')
        else:
            check(not has,
                  f'{key}: has NO logo strip (mid-study pages are kept clean)')

    for key, per_vp in facts.items():
        has_title = per_vp['laptop_1280x720']['has_header_title']
        if key == 'instructions':
            check(not has_title,
                  'instructions: the header strip carries NO .header-title — '
                  'this page still takes its title from the SLIDE\'s <h2>, '
                  'unlike every other page (improvement_suggestions item 5 is '
                  'NOT resolved on this point)')
        elif key == 'task_tabmonitor':
            check(not has_title,
                  'task screen: no title — the progress strip states the round')
        else:
            check(has_title,
                  f'{key}: the title is in the header strip, as .header-title')

    # …and name the element that actually renders as the instructions title.
    code, _ = walk_to(server.base, create_session('lab', num_participants=2),
                      'instructing')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    m = page.evaluate("""() => {
        const h = document.querySelector('.instruction-block > h2');
        const inHeader = document.querySelector(
            '.experimental-header .header-title');
        return {slideTitle: h ? h.textContent.trim() : null,
                slideTitleInHeader: !!(h && h.closest('.experimental-header')),
                headerTitle: inHeader ? inHeader.textContent.trim() : null};
    }""")
    check(m['slideTitle'] and not m['slideTitleInHeader']
          and m['headerTitle'] is None,
          f'instructions: the visible title {m["slideTitle"]!r} is the slide '
          f'<h2>, rendered inside the SCROLL REGION, not the header strip')
    geometry['instructions_title_source'] = m
    context.close()


def check_lab_only_copy(server, browser):
    """AC. The two lab-only sentences, and their absence online (2026-08-12).

    Two DIFFERENT sentences for two different situations, both meaningless
    outside a physical lab:
      * results  — "stay seated" until the experimenter dismisses the room;
      * ending   — "raise your hand", because someone leaving early is not
                   waiting for a general dismissal.
    A Prolific participant must see neither. That absence is exactly the kind of
    thing that regresses silently when a template is edited, so it is asserted
    from the rendered text on BOTH variants of BOTH pages.
    """
    section('AC. Lab-only closing copy, and never on Prolific')
    cases = (
        ('results', 'Results', 'stay seated',
         'until the experimenter tells you that you can leave'),
        # The SCREEN-OUT page, not the outro ending: a screened-out participant
        # is now held at entry (the soft wall), so this is where the lab/online
        # divergence actually reaches somebody. In the lab there is a person in
        # the room to call; online there is a link back to Prolific instead.
        ('screenout', 'welcome', 'raise your hand',
         'so the experimenter can come to you'),
    )
    for page_key, stop, bold_phrase, tail in cases:
        for config in ('lab', 'prolific'):
            modified = ({'allowed_devices': ['computer']}
                        if page_key == 'screenout' else None)
            ua = PHONE_UA if page_key == 'screenout' else None
            session = create_session(config, num_participants=2,
                                     modified_session_config_fields=modified)
            code, _ = walk_to(server.base, session, stop, user_agent=ua)
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'],
                                          user_agent=ua)
            page = context.new_page()
            page.goto(f'{server.base}/InitializeParticipant/{code}',
                      wait_until='load')
            page.wait_for_timeout(150)
            flat = ' '.join(visible_text(page).split())
            bolds = [b.strip().lower() for b in page.evaluate(
                """() => Array.from(document.querySelectorAll(
                    '.experimental-content strong')).map(s => s.innerText)""")]
            label = f'{page_key} @ {config}'
            if config == 'lab':
                check(tail in flat,
                      f'{label}: the lab sentence is on the page ({tail!r})')
                check(any(bold_phrase in b for b in bolds),
                      f'{label}: "{bold_phrase}" is BOLD (bold runs: {bolds})')
            else:
                check(tail not in flat and bold_phrase not in flat.lower(),
                      f'{label}: neither lab sentence appears online')
                # …and the other page's sentence has not leaked here either.
                other = 'raise your hand' if page_key == 'results' else 'stay seated'
                check(other not in flat.lower(),
                      f'{label}: nor the other page\'s lab sentence')
            geometry.setdefault('lab_only_copy', {})[label] = {
                'has_tail': tail in flat, 'bolds': bolds}
            context.close()


def check_screenout_way_out(server, browser):
    """AD. The screen-out page's way out WORKS WITHOUT JAVASCRIPT.

    This is the bug the page was rebuilt to avoid: the implementation it was
    adapted from used `onclick="completed()"` with no href, so a participant
    whose JavaScript had not run had NO way off the page at all — a dead end on
    the one page whose entire job is to offer a way out. Driven with JS
    DISABLED, and measured, not looked at: the link must be present, visible,
    big enough to press, and pointing at the platform with no completion code.

    Also checks the VISUAL HIERARCHY the copy depends on. The irreversible
    action is the SECONDARY one: it must not be painted like the primary
    forward button used everywhere else in the study, or a participant reading
    "do not press this" sees the study's usual Next button.
    """
    section('AD. The screen-out way out: no JavaScript, and visibly secondary')
    # `prolific_screenout_return_url` ships as a REPLACE_* placeholder (see
    # settings.SCREENOUT_RETURN_URL_PLACEHOLDER), so drive this leg as a study
    # that has replaced it — the href assertions below are about a CONFIGURED
    # study's way out.
    session = create_session('prolific', num_participants=2,
                             modified_session_config_fields={
                                 'allowed_devices': ['computer'],
                                 'prolific_screenout_return_url': 'https://app.prolific.com/'})
    code, _ = walk_to(server.base, session, 'welcome', user_agent=PHONE_UA)
    for vp_name, vp in VIEWPORTS.items():
        context = browser.new_context(viewport=vp, user_agent=PHONE_UA,
                                      java_script_enabled=False)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        m = page.evaluate("""() => {
            const a = document.querySelector('a.exit-button');
            if (!a) return null;
            const r = a.getBoundingClientRect();
            const cs = getComputedStyle(a);
            return {href: a.getAttribute('href'), w: Math.round(r.width),
                    h: Math.round(r.height), display: cs.display,
                    visibility: cs.visibility, background: cs.backgroundColor,
                    color: cs.color, text: a.innerText.trim(),
                    onclick: a.getAttribute('onclick')};
        }""")
        primary = page.evaluate(
            """() => document.querySelectorAll('.next-button').length""")
        label = f'{vp_name}'
        if not check(m is not None,
                     f'{label}: the way out EXISTS with JS disabled'):
            context.close()
            continue
        check(m['href'].startswith('http'),
              f'{label}: it is a real href ({m["href"]!r}) — not a scripted button')
        check('submissions/complete' not in m['href'] and 'cc=' not in m['href'],
              f'{label}: it carries NO completion code ({m["href"]!r})')
        check(m['onclick'] is None,
              f'{label}: no onclick — nothing about it needs a script')
        check(m['visibility'] == 'visible' and m['w'] >= 120 and m['h'] >= 36,
              f'{label}: visible and pressable ({m["w"]}x{m["h"]}px)')
        check(primary == 0,
              f'{label}: there is NO .next-button on this page — the exit is '
              f'not painted as the study\'s primary forward action, and '
              f'global.js\'s Enter handler has nothing to click ({primary} found)')
        check(m['background'] in ('rgba(0, 0, 0, 0)', 'transparent'),
              f'{label}: the irreversible action is SECONDARY — outlined, not '
              f'filled (background {m["background"]})')
        geometry.setdefault('screenout_way_out', {})[vp_name] = m
        if vp_name == 'phone_375x667':
            screenshot(page, 'screened_out_nojs', vp_name)
        context.close()


def check_completion_link_nojs(server, browser):
    """AF. EVERY way back to Prolific works with JavaScript DISABLED.

    The completion codes are the participant's PAY. The Results button used to
    be `<button onclick="backToProlific()">` with the URL only in `js_vars`, so
    a completer whose JavaScript was blocked or broken finished the entire
    study, read their payment total, and then had no way to submit their
    completion — unpaid, and indistinguishable in the data from somebody who
    abandoned on the last page. The early-exit ending had the same shape, with
    the disqualification and no-consent codes on it.

    Both are real links now, and this drives them with JS off and reads the href
    the participant would actually follow — including the CODE in it, so a
    regression that renders an empty or wrong URL fails here too.
    """
    section('AF. The completion links: present and correct with JS disabled')
    cases = []

    # (1) A COMPLETER, the case that matters most: everybody who finishes.
    session = create_session('prolific', num_participants=2)
    code, _ = walk_to(server.base, session, 'Results')
    cases.append(('Results (completer)', code,
                  _settings.SESSION_CONFIG_DEFAULTS['prolific_cc_code']))

    # (2) An EARLY EXIT — the no-consent route, which carries prolific_noconsent_code.
    session = create_session('prolific', num_participants=2)
    s = requests.Session()
    r = s.get(f'{server.base}/join/{anon_code(session.code)}', allow_redirects=True)
    fp = FormParser(); fp.feed(r.text)
    r = s.post(r.url, data=build_payload(fp.inputs, {'consent': 'False'}, {},
                                         warn=False), allow_redirects=True)
    if check(page_of(r.url) == 'Ended',
             f'a non-consenter reaches the ending (got {page_of(r.url)})'):
        cases.append(('Ended (declined consent)', code_of(r.url),
                      _settings.SESSION_CONFIG_DEFAULTS['prolific_noconsent_code']))

    for label, participant_code, expected_code in cases:
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'],
                                      java_script_enabled=False)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{participant_code}',
                  wait_until='load')
        m = page.evaluate("""() => {
            const a = Array.from(document.querySelectorAll('a')).find(
                x => (x.getAttribute('href') || '').includes('prolific'));
            if (!a) return null;
            const r = a.getBoundingClientRect();
            return {href: a.getAttribute('href'), text: a.innerText.trim(),
                    w: Math.round(r.width), h: Math.round(r.height),
                    onclick: a.getAttribute('onclick'),
                    cls: a.getAttribute('class')};
        }""")
        buttons = page.evaluate(
            """() => Array.from(document.querySelectorAll('button')).map(
                   b => b.innerText.trim()).filter(t => /prolific/i.test(t))""")
        if not check(m is not None,
                     f'{label}: a Prolific link EXISTS with JS disabled'):
            context.close()
            continue
        check(m['href'].startswith('https://app.prolific.com/submissions/complete?cc='),
              f'{label}: it is the completion URL ({m["href"]!r})')
        check(expected_code in m['href'],
              f'{label}: carrying THIS outcome\'s code ({expected_code} in '
              f'{m["href"]!r})')
        check(m['onclick'] is None and not buttons,
              f'{label}: nothing about leaving needs a script '
              f'(onclick={m["onclick"]!r}, scripted buttons {buttons})')
        check(m['w'] >= 120 and m['h'] >= 36,
              f'{label}: visible and pressable ({m["w"]}x{m["h"]}px)')
        geometry.setdefault('completion_link_nojs', {})[label] = m
        context.close()


def check_narrow_desktop_window(server, browser):
    """AE. A NARROW DESKTOP WINDOW is not a phone, and is never screened out.

    The gate classifies the User-Agent and nothing else — no width, no touch,
    nothing client-side — and this is the case that would go wrong if anybody
    ever "improved" it with a viewport test: a computer browser 640px wide,
    under a computers-only allow-list. It must render CONSENT, and the layout
    must survive the width (no sideways overflow).
    """
    section('AE. A 640px-wide desktop window still gets consent')
    session = create_session('prolific', num_participants=2,
                             modified_session_config_fields={
                                 'allowed_devices': ['computer']})
    code, _ = walk_to(server.base, session, 'welcome', user_agent=DESKTOP_UA)
    context = browser.new_context(viewport={'width': 640, 'height': 900},
                                  user_agent=DESKTOP_UA)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    flat = ' '.join(visible_text(page).split())
    check('I consent and wish to take part' in flat,
          'a narrow desktop window reaches CONSENT (width screens nobody out)')
    check('Your place is still open' not in flat,
          'and never the screen-out page')
    over = page.evaluate("""() => ({doc: document.documentElement.scrollWidth,
                                    win: window.innerWidth})""")
    check(over['doc'] <= over['win'] + 1,
          f'and the page does not scroll sideways at 640px '
          f'({over["doc"]}px content in {over["win"]}px)')
    screenshot(page, 'consent_narrow_window', 'narrow_640x900')
    geometry['narrow_desktop_window'] = over
    context.close()


def check_phone_page_flow(server, browser):
    """Z. On a phone the PAGE scrolls, and Next comes after the content.

    improvement_suggestions item 1 (Julian, 2026-08-12). Below 520px the
    card-scroll model is switched off: the card grows, the browser's own scroll
    takes over, and the forward action sits after the content in document order
    so it cannot be reached without passing what is above it. This asserts all
    three, on the three pages where it matters most, and re-asserts that the
    WIDE layout still pins its action (the property the base.css comment now
    claims only for wide screens).
    """
    section('Z. Phone: the page scrolls and Next follows the content (item 1)')
    pages = (('consent_prolific', 'prolific', 'welcome',
              'input[name="consent"]'),
             ('quiz', 'lab', 'quiz', '.form-check input'),
             ('results', 'prolific', 'Results', '.payout-line.total'))
    for key, config, stop, last_sel in pages:
        code, _ = walk_to(server.base, create_session(config, num_participants=2),
                          stop)
        context = browser.new_context(viewport=VIEWPORTS['phone_375x667'])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(250)
        m = page.evaluate("""(sel) => {
            const el = document.querySelector('.experimental-content');
            const card = document.querySelector('.screen-card');
            const row = document.querySelector('.screen-card > .button-row')
                     || document.querySelector('.instruction-controls');
            const items = Array.from(document.querySelectorAll(sel));
            const last = items.length ? items[items.length - 1] : null;
            const cs = getComputedStyle(el);
            const doc = document.documentElement;
            return {
                overflowY: cs.overflowY,
                regionScrolls: el.scrollHeight > el.clientHeight + 2,
                cardMaxHeight: getComputedStyle(card).maxHeight,
                pageScrolls: doc.scrollHeight > window.innerHeight + 2,
                docH: doc.scrollHeight, viewH: window.innerHeight,
                lastBottom: last ? Math.round(
                    last.getBoundingClientRect().bottom + window.scrollY) : null,
                buttonTop: row ? Math.round(
                    row.getBoundingClientRect().top + window.scrollY) : null,
                buttonAfterInDom: (row && last)
                    ? !!(last.compareDocumentPosition(row)
                         & Node.DOCUMENT_POSITION_FOLLOWING) : null,
                cls: el.className,
            };
        }""", last_sel)
        label = f'{key} @ phone_375x667'
        check(m['overflowY'] == 'visible' and m['cardMaxHeight'] == 'none',
              f'{label}: the card-scroll model is OFF '
              f'(content overflow-y:{m["overflowY"]}, card '
              f'max-height:{m["cardMaxHeight"]})')
        check(not m['regionScrolls'],
              f'{label}: nothing scrolls inside the card any more')
        check(m['pageScrolls'],
              f'{label}: the PAGE scrolls instead ({m["docH"]}px document in a '
              f'{m["viewH"]}px viewport)')
        check('is-scrollable' not in m['cls'],
              f'{label}: and no in-card scroll affordance is drawn '
              f'({m["cls"]!r})')
        if m['buttonAfterInDom'] is not None:
            check(m['buttonAfterInDom'],
                  f'{label}: the forward action FOLLOWS the content in document '
                  f'order')
            check(m['buttonTop'] >= m['lastBottom'] - 2,
                  f'{label}: …and sits below it on screen (button at '
                  f'{m["buttonTop"]}, last item ends {m["lastBottom"]})')
        geometry.setdefault('phone_flow', {})[key] = m
        screenshot(page, f'{key}_phone_flow', 'phone_375x667')
        context.close()

    # …and the WIDE layout still does the opposite, which is what base.css now
    # claims only for wide screens: the action is pinned and always on screen.
    code, _ = walk_to(server.base, create_session('prolific', num_participants=2),
                      'welcome')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(200)
    w = page.evaluate("""() => {
        const el = document.querySelector('.experimental-content');
        const row = document.querySelector('.screen-card > .button-row');
        const r = row.getBoundingClientRect();
        return {regionScrolls: el.scrollHeight > el.clientHeight + 2,
                overflowY: getComputedStyle(el).overflowY,
                buttonOnScreen: r.top >= 0 && r.bottom <= window.innerHeight,
                pageScrolls: document.documentElement.scrollHeight
                             > window.innerHeight + 2};
    }""")
    check(w['overflowY'] == 'auto' and w['regionScrolls'],
          'consent @ laptop_1280x720: the card still scrolls internally')
    check(w['buttonOnScreen'] and not w['pageScrolls'],
          'consent @ laptop_1280x720: …and Next is pinned on screen, with no '
          'page scroll — the wide-screen intention still holds')
    context.close()


def check_dq_ending(server, browser):
    """Y. The ending says WHY the study ended (change_requests item 16).

    Drives a REAL comprehension failure: walk to the quiz, then submit wrong
    answers until comprehension_dq fires. The participant must be told which
    check they failed, not just that participation "cannot continue" — and the
    tab-monitor wording must not be what they get.
    """
    section('Y. A disqualified participant is told WHY (item 16)')
    session = create_session('prolific', num_participants=2)
    code, resp = walk_to(server.base, session, 'quiz')
    s = requests.Session()
    r = s.get(f'{server.base}/InitializeParticipant/{code}', allow_redirects=True)
    wrong = {}
    for item in QUIZ_ITEMS:
        alternatives = [c for c in item['choices'] if c != item['answer']]
        wrong[item['field']] = alternatives[0] if alternatives else item['answer']
    for _ in range(6):
        if page_of(r.url) != 'quiz':
            break
        fp = FormParser()
        fp.feed(r.text)
        r = s.post(r.url, data=build_payload(fp.inputs, {}, wrong),
                   allow_redirects=True)
    check(page_of(r.url) == 'Ended',
          f'the quiz disqualified them and routed to the ending '
          f'(now at {page_of(r.url)})')
    context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
    page.wait_for_timeout(150)
    text = ' '.join(visible_text(page).split())
    check('comprehension check' in text.lower(),
          f'the page names the comprehension check as the reason '
          f'({text[:160]!r})')
    check('inactive' not in text.lower(),
          'it does NOT give them the tab-monitor wording')
    check('cannot continue' not in text.lower(),
          'the old catch-all sentence is gone')
    geometry['dq_ending'] = text[:400]
    screenshot(page, 'ended_comprehension', 'laptop_1280x720')
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
        # The fully-visible assertions below are decided by a few pixels of
        # headroom (7px at 1280x720), so they are exactly the kind of check a
        # not-yet-settled layout turns flaky — see wait_for_stable_layout.
        wait_for_stable_layout(page)
        m = page.evaluate("""() => {
            const opts = Array.from(document.querySelectorAll(
                'input[name="consent"]')).map(i =>
                    i.closest('.form-check, .mc-option') || i);
            if (!opts.length) return null;
            const el = document.querySelector('.experimental-content');
            const sr = el.getBoundingClientRect();
            const btn = document.querySelector('.button-row');
            // VISIBILITY IS COMPUTED FROM THE RAW RECTS AND ROUNDED ONCE, at
            // the end. Rounding the edges first and subtracting afterwards
            // loses a pixel whenever a box straddles a half-pixel — measured on
            // 2026-08-13 at 1512x1200, where an option sitting 182px clear of
            // the fold reported 65 visible of 66. That is a spurious failure in
            // a check whose whole point is "partial is a failure", so the
            // arithmetic is done once, here, rather than papered over with a
            // tolerance downstream.
            const clipped = el => {
                const r = el.getBoundingClientRect();
                return {
                    top: Math.round(r.top),
                    bottom: Math.round(r.bottom),
                    height: Math.round(r.height),
                    visible: Math.round(Math.min(r.bottom, sr.bottom)
                                        - Math.max(r.top, sr.top)),
                };
            };
            return {
                n: opts.length,
                first: clipped(opts[0]),
                last: clipped(opts[opts.length - 1]),
                viewTop: Math.round(sr.top), viewBottom: Math.round(sr.bottom),
                buttonTop: btn ? Math.round(btn.getBoundingClientRect().top) : null,
                buttonBottom: btn ? Math.round(btn.getBoundingClientRect().bottom)
                                  : null,
                viewportH: window.innerHeight,
                scrollTop: el.scrollTop,
            };
        }""")
        if not check(m is not None,
                     f'{vp_name}: the consent control is rendered'):
            context.close()
            continue
        visible_px = m['first']['visible']
        both = m['last']['visible']
        if vp_name == 'phone_375x667':
            # THE PHONE CONTRACT CHANGED (improvement_suggestions item 1). This
            # page's copy is ~750px and the viewport is 667px, so the options
            # cannot be above the fold whatever the layout does — only cutting
            # consent copy would manage it, and that is the one thing this
            # template may not do. So the guarantee is no longer "the options
            # are on screen" but "the options cannot be BYPASSED": the card
            # scroll model is off here, the page scrolls, and Next comes after
            # the options in document order. That is asserted in its own leg
            # (check_phone_page_flow); here we only record where things sat.
            print(f'  [note] {vp_name}: the first option sits at '
                  f'{m["first"]["top"]}..{m["first"]["bottom"]} in a '
                  f'{vp["height"]}px viewport — reached by scrolling the PAGE, '
                  f'with Next below it (see the phone-flow leg)')
        else:
            check(visible_px > 10,
                  f'{vp_name}: the FIRST consent option is on screen without '
                  f'scrolling ({visible_px}px of it visible; option '
                  f'{m["first"]["top"]}..{m["first"]["bottom"]}, scroll viewport '
                  f'{m["viewTop"]}..{m["viewBottom"]})')
            # EVERY OPTION WHOLE, NOT JUST THE FIRST (Julian, 2026-08-13).
            #
            # THIS ASSERTION IS THE POINT OF THE LEG, and its absence is exactly
            # how the asymmetry it now catches survived: the check above passes
            # on 10px of the FIRST option, and the second was only ever PRINTED.
            # Measured on 2026-08-13 at 1280x720: "I consent" rendered whole at
            # 408..474 while "I do not consent" ran 484..550 against a scroll
            # region ending at 514 — half of it, under a complete-looking one.
            # A fold BETWEEN two options is worse than a fold below both,
            # because a sliced list still reads as a finished list.
            #
            # PARTIAL IS A FAILURE, not a degree: the bar is the option's OWN
            # height, so a row cut by one pixel fails. (Fixed by the consent
            # rhythm block in the `max-height: 820px` media query in base.css;
            # if this goes red, that block is where the space came from.)
            for which, box, seen in (('FIRST', m['first'], visible_px),
                                     ('LAST', m['last'], both)):
                height = box['height']
                # THE FAILURE MESSAGE HAS TO SAY WHAT TO DO. Whoever trips this
                # will almost always be someone who added a sentence to the
                # consent copy — an ethics committee asks for one, nobody ever
                # removes one — and they have no reason to connect that to a
                # media query in base.css two files away. A bare pixel
                # assertion would read as "the layout is broken"; it is not,
                # the copy has outgrown the fold.
                short = height - seen
                check(seen >= height,
                      f'{vp_name}: the {which} consent option is FULLY visible '
                      f'without scrolling ({seen}px of {height}px; option '
                      f'{box["top"]}..{box["bottom"]}, scroll region '
                      f'{m["viewTop"]}..{m["viewBottom"]})'
                      + (f' — THE CONSENT COPY HAS OUTGROWN THE FOLD by {short}px. '
                         f'A participant sees a complete-looking list with the '
                         f'last option sliced. Two levers, both in the '
                         f'`@media (max-height: 820px)` block in '
                         f'_static/global/css/base.css: (1) the consent rhythm '
                         f'— option row padding-block, currently .5em, with a '
                         f'hard floor at the 44px touch target (~16px left); '
                         f'(2) the LOGO STRIP, which yields first by rule — '
                         f'marks are 32px and go to 24px (~8px). Measured '
                         f'2026-08-13: about 32px is available in total, and a '
                         f'line of copy costs ~31px. IF THAT IS NOT ENOUGH, '
                         f'STOP TIGHTENING: shorten the copy, or accept that '
                         f'the card scrolls — the scroll affordance is real and '
                         f'is asserted, and "nobody consents blind" is enforced '
                         f'by the un-pre-checked radio and the rejected empty '
                         f'submit, not by the fold.'
                         if seen < height else ''))
            # And the forward action itself, in the viewport rather than the
            # scroll region — it is pinned below it, so a card that grew to fit
            # the options must not have pushed Next off the screen instead.
            if m['buttonBottom'] is not None:
                check(m['buttonBottom'] <= m['viewportH'],
                      f'{vp_name}: the Next button is fully on screen '
                      f'(button {m["buttonTop"]}..{m["buttonBottom"]} in a '
                      f'{m["viewportH"]}px viewport)')
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


def check_logo_footer_rule(server, browser):
    """D4. THE LOGO FOOTER RULE, measured on EVERY page that carries the strip.

    THE RULE (Julian, 2026-08-13, change_requests_round2 item 9): the logo
    footer sits at the BOTTOM of the white card, BELOW the divider line that
    separates it from the content, and it is THE SAME everywhere it appears.

    WHY THIS LEG REPLACED TWO. There used to be a D4 ("the strip is inside the
    scroll region") and a D4b ("except on results, where it is below the
    button"), which is the shape of a per-page arrangement — and a per-page
    arrangement is what item 9 abolished. Two legs asserting two different
    answers could not have caught a THIRD page doing a third thing, which is
    exactly how this drifted: at the time item 9 was raised, four pages had one
    arrangement, one had another, and the design-system demo modelled the wrong
    one twice. This leg walks every page that carries the strip and asserts the
    SAME four facts about each, so a new page that gets it wrong fails here
    rather than looking merely unusual.

    The measured facts, per page:
      1. the strip is a DIRECT CHILD of .screen-card (not inside the scroller);
      2. it is BELOW the content region;
      3. it is BELOW the button row, when the page has one;
      4. it carries its own divider line (border-top), so the separation
         travels with the component instead of being drawn per page.
    """
    section('D4. THE LOGO FOOTER RULE, on every page that shows the strip')
    pages = (
        ('lab_entry_gate', 'lab', 'startpage'),
        ('consent_lab', 'lab', 'welcome'),
        ('consent_prolific', 'prolific', 'welcome'),
        ('results_lab', 'lab', 'Results'),
        ('results_prolific', 'prolific', 'Results'),
    )
    for key, config, stop in pages:
        session = create_session(config, num_participants=2)
        code, _ = walk_to(server.base, session, stop)
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        page.wait_for_timeout(150)
        m = page.evaluate("""() => {
            const logo = document.querySelector('.logo-section');
            const el = document.querySelector('.experimental-content');
            const row = document.querySelector('.screen-card > .button-row');
            const card = document.querySelector('.screen-card');
            if (!logo || !el) return null;
            const l = logo.getBoundingClientRect();
            const cs = getComputedStyle(logo);
            return {insideScroller: el.contains(logo),
                    parentIsCard: logo.parentElement === card,
                    logoTop: Math.round(l.top),
                    logoBottom: Math.round(l.bottom),
                    cardBottom: Math.round(
                        card.getBoundingClientRect().bottom),
                    contentBottom: Math.round(el.getBoundingClientRect().bottom),
                    buttonBottom: row ? Math.round(
                        row.getBoundingClientRect().bottom) : null,
                    hasButton: !!row,
                    borderTop: parseFloat(cs.borderTopWidth) || 0};
        }""")
        if not check(m is not None, f'{key}: the page has a logo strip'):
            context.close()
            continue
        check(not m['insideScroller'] and m['parentIsCard'],
              f'{key}: the strip is a DIRECT CHILD of the card, outside the '
              f'scroll region')
        check(m['logoTop'] >= m['contentBottom'] - 2,
              f'{key}: it sits below the scrolling content '
              f'({m["logoTop"]} >= {m["contentBottom"]})')
        if m['hasButton']:
            check(m['logoTop'] >= m['buttonBottom'] - 2,
                  f'{key}: …and BELOW the button row — the `order: 999` rule, '
                  f'not the markup order ({m["logoTop"]} >= '
                  f'{m["buttonBottom"]})')
        else:
            print(f'  [note] {key}: no button row on this page, so the strip '
                  f'is simply the foot of the card')
        check(m['borderTop'] >= 1,
              f'{key}: it carries its own divider line above it '
              f'({m["borderTop"]}px border-top)')
        geometry.setdefault('logo_footer', {})[key] = m
        screenshot(page, f'logo_footer_{key}', 'laptop_1280x720')
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
# CHECK C — ONE focus indicator per option, and it is not clipped
# ==========================================================================
# THE INDICATOR IS THE CARD (improvement_suggestions item 2, 2026-08-12): the
# option card takes a border + ring on :focus-within, and the outline on the
# radio INSIDE it is suppressed, so a keyboard user sees exactly one ring rather
# than a ring inside a ring. This measures both halves — the card really is
# ringed, the input really has no outline — and then that the ring is not
# clipped by the scroll edge, which is the original point of this check.
FOCUS_JS = """() => {
    const scroller = document.querySelector('.experimental-content');
    const opts = Array.from(document.querySelectorAll('.form-check, .mc-option'));
    if (!scroller || !opts.length) return null;
    const active = document.activeElement;
    if (!active) return null;
    const card = active.closest('.form-check, .mc-option');
    const cs = getComputedStyle(active);
    const inputOutline = (parseFloat(cs.outlineWidth) || 0);
    const cardCS = card ? getComputedStyle(card) : null;
    // The card's ring is a box-shadow, so its painted extent is the shadow's
    // spread beyond the border box (3px, base.css .form-check:focus-within).
    const shadow = cardCS ? cardCS.boxShadow : 'none';
    const ring = shadow && shadow !== 'none' ? 3 : 0;
    const ar = active.getBoundingClientRect();
    const cr = (card || active).getBoundingClientRect();
    const sr = scroller.getBoundingClientRect();
    const sc = getComputedStyle(scroller);
    const paintedTop = cr.top - ring;
    const paintedBottom = cr.bottom + ring;
    return {
        tag: active.tagName + (active.type ? ':' + active.type : ''),
        inputOutlineStyle: cs.outlineStyle, inputOutlineWidth: cs.outlineWidth,
        inputOutline: inputOutline,
        inputBoxShadow: cs.boxShadow,
        cardShadow: shadow, cardBorder: cardCS ? cardCS.borderTopColor : null,
        ring: ring,
        cardTop: Math.round(cr.top), cardBottom: Math.round(cr.bottom),
        scrollerTop: Math.round(sr.top), scrollerBottom: Math.round(sr.bottom),
        scrollerClips: sc.overflowY !== 'visible',
        padTop: parseFloat(sc.paddingTop), padBottom: parseFloat(sc.paddingBottom),
        headroom: Math.round(paintedTop - sr.top),
        footroom: Math.round(sr.bottom - paintedBottom),
        index: card ? opts.indexOf(card) : -1, n: opts.length,
    };
}"""


def check_focus_rings(server, browser):
    section('C. ONE focus ring per option (the card), and it is not clipped')
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
        # SETTLE FIRST. The option card transitions its box-shadow over .14s, so
        # a measurement taken in the same tick as the keypress catches the ring
        # PART WAY IN (measured 1.1px of a 3px ring, at 12% alpha) and would
        # fail against any honest threshold.
        page.wait_for_timeout(250)
        first = page.evaluate(FOCUS_JS)
        # ONE indicator: the card is ringed…
        check(first['cardShadow'] not in ('none', None)
              and '0px 0px 0px 0px' not in first['cardShadow'],
              f'{vp_name}: the focused option CARD carries the ring '
              f'(box-shadow: {first["cardShadow"]})')
        # …and the control inside it draws no second one. Asserted on the
        # STYLE, not the width: with `outline: none` Chromium still reports a
        # used outline-width of 3px, and nothing is painted — the style is what
        # says whether a ring exists.
        check(first['inputOutlineStyle'] == 'none',
              f'{vp_name}: the radio inside draws NO second ring '
              f'(outline-style: {first["inputOutlineStyle"]}, nothing painted)')
        check('rgb(13, 110, 253)' not in (first['inputBoxShadow'] or ''),
              f'{vp_name}: …and no Bootstrap glow either '
              f'(box-shadow: {first["inputBoxShadow"]})')
        if first['scrollerClips']:
            check(first['headroom'] >= 0,
                  f'{vp_name}: first option ring clears the scroll edge by '
                  f'{first["headroom"]}px (>=0 = not clipped)')
        else:
            # Phone: the card-scroll model is off (item 1), so there is no
            # scroll edge to be clipped by — the page scrolls instead.
            print(f'  [note] {vp_name}: no in-card scroll region here, so no '
                  f'edge can clip the ring')
        screenshot(page, 'quiz_focus_ring', vp_name)
        # …then Shift+Tab backwards from the end for the LAST option.
        page.evaluate("""() => { const o = document.querySelectorAll(
            '.form-check input, .mc-option input');
            if (o.length) o[o.length - 1].focus(); }""")
        page.keyboard.press('Shift+Tab')
        page.keyboard.press('Tab')
        page.wait_for_timeout(250)
        last = page.evaluate(FOCUS_JS)
        if last and last['scrollerClips']:
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
    code, _ = walk_to(server.base, session, TASK_PAGES[0])
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
# CHECK D3 — the OUTRO monitor counts but never ejects, measured END TO END
# ==========================================================================
# WHY A HEADED BROWSER UNDER Xvfb, when every other leg is headless: this leg
# must GENUINELY blur the tab — fire the real `blur`/`visibilitychange` events
# ai_safety_monitor.js listens for, from the browser's own tab machinery, not
# a dispatched Event() that skips the threshold timer. Headless Chromium
# (both the headless shell and --headless=new, measured 2026-08-14) pins
# every page to `visible`/focused forever: bring_to_front, window.open,
# Target.activateTarget, Page.setWebLifecycleState — none of them fires
# anything. Under a real X server the same tab switch fires real events, with
# ONE more trap: Playwright's focus EMULATION (enabled on every page it
# drives) swallows them, so it must be switched off for the page under test
# via Emulation.setFocusEmulationEnabled. The Xvfb-without-root recipe lives
# with the Chromium one in docs/headless_chromium_recipe.md.
def _start_xvfb():
    """Start Xvfb without root; return (proc, display) or (None, why-not).

    Resolution order: $XVFB_BINARY, a system Xvfb on PATH, then the unpacked
    sysroot next to the libraries LD_LIBRARY_PATH already points at (the
    no-root recipe). The sysroot build hardcodes /usr/bin as the xkbcomp
    directory, which does not exist on a rootless box — so the binary is
    byte-patched IN A TEMP COPY to read the equal-length '/tmp/xkb' instead,
    and xkbcomp is symlinked there. The repo's own copy is never modified.
    """
    import shutil
    lib_dir = (os.environ.get('LD_LIBRARY_PATH') or '').split(':')[0]
    sysroot_bin = os.path.normpath(os.path.join(lib_dir, '..', '..', 'bin'))
    xvfb = (os.environ.get('XVFB_BINARY') or shutil.which('Xvfb')
            or os.path.join(sysroot_bin, 'Xvfb'))
    if not os.path.isfile(xvfb):
        return None, f'no Xvfb (looked at $XVFB_BINARY, PATH, {sysroot_bin})'
    args = []
    if not os.path.isfile('/usr/bin/xkbcomp'):
        xkbcomp = shutil.which('xkbcomp') or os.path.join(sysroot_bin, 'xkbcomp')
        if not os.path.isfile(xkbcomp):
            return None, f'no xkbcomp next to {xvfb} and none on PATH'
        # '/tmp/xkb' is EXACTLY as long as '/usr/bin': the string is replaced
        # inside the compiled binary, so only an equal-length path can stand in.
        try:
            os.makedirs('/tmp/xkb', exist_ok=True)
            link = '/tmp/xkb/xkbcomp'
            if os.path.islink(link) or os.path.exists(link):
                os.remove(link)
            os.symlink(xkbcomp, link)
        except OSError as exc:
            return None, f'cannot prepare /tmp/xkb ({exc})'
        blob = open(xvfb, 'rb').read()
        if b'/usr/bin\x00' in blob:
            patched = os.path.join(_TMPDIR, 'Xvfb.patched')
            with open(patched, 'wb') as fh:
                fh.write(blob.replace(b'/usr/bin\x00', b'/tmp/xkb\x00'))
            os.chmod(patched, 0o755)
            xvfb = patched
        xkb_data = os.path.normpath(
            os.path.join(sysroot_bin, '..', 'share', 'X11', 'xkb'))
        if os.path.isdir(xkb_data):
            args += ['-xkbdir', xkb_data]
    for n in range(99, 120):
        if os.path.exists(f'/tmp/.X{n}-lock'):
            continue
        proc = subprocess.Popen(
            [xvfb, f':{n}', '-screen', '0', '1600x1200x24', '-nolisten', 'tcp']
            + args,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.time() + 5
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if os.path.exists(f'/tmp/.X11-unix/X{n}'):
                return proc, f':{n}'
            time.sleep(0.1)
        if proc.poll() is None:      # up, but never wrote the socket path
            return proc, f':{n}'
        err = (proc.stderr.read() or b'').decode(errors='replace')[-300:]
        return None, f'Xvfb exited on :{n}: {err}'
    return None, 'no free X display between :99 and :119'


def check_outro_never_ejects(server, pw):
    """D3. The outro monitor COUNTS the violation and does NOT eject — the
    whole promise, measured end to end in a real browser for the first time.

    Every seam of this behaviour is pinned server-side (the two live handlers,
    the two columns, the ejects flag in js_vars), but until this leg nothing
    ever BLURRED an outro tab and watched what actually happens. The three
    assertions are a package, and the third is the load-bearing one:

      1. NO overlay is rendered (record-only mode builds no monitor UI at all,
         and no warning modal either — its threat would be a lie here);
      2. the participant is NOT ejected: still on Results after a reload,
         exit code untouched, ai_safety_disqualified unset;
      3. the violation IS recorded, in the outro's OWN column
         (focus_loss_count_outro), with the ejecting column untouched.

    WITHOUT (3) THIS TEST WOULD BE WORTHLESS: a study with the monitor
    switched off entirely shows the same "nothing happened" as (1) and (2) —
    the point of outro monitoring is that it counts WITHOUT ejecting, and only
    the recorded count distinguishes the two. (The collapsed-distinction rule,
    as a test-design trap.)

    The blur is GENUINE: a second tab in the same window is activated through
    the browser's own tab machinery (CDP Target.activateTarget), which fires
    the real window `blur`/`focus` events the monitor listens for — the same
    thing a participant's Cmd-clicking another tab fires. It is held blurred
    past tab_monitor_threshold_ms so the client's violation timer truly runs
    out, TWICE: two violations meet the default tab_monitor_max_violations, so
    if the outro ejected the way intro/main do, this participant WOULD be
    disqualified — that is what makes the not-ejected assertion mean anything.
    """
    import common
    section('D3. An outro blur past the threshold: counted, never ejected, '
            'no overlay')
    xvfb, display = _start_xvfb()
    if xvfb is None:
        # A missing X server must go RED, not silently skip: a leg that skips
        # quietly is indistinguishable from coverage (the exact failure this
        # leg exists to close at the next level down).
        check(False, f'headed Chromium under Xvfb is available for a real '
                     f'blur ({display})')
        return
    browser = None
    try:
        session = create_session('prolific', num_participants=2)
        threshold_ms = int(common.cfg(session.config, 'tab_monitor_threshold_ms'))
        max_violations = int(common.cfg(session.config, 'tab_monitor_max_violations'))
        cycles = max(2, max_violations)
        code, _ = walk_to(server.base, session, 'Results')
        browser = pw.chromium.launch(
            headless=False, env={**os.environ, 'DISPLAY': display})
        context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
        context.add_init_script(
            "try { sessionStorage.setItem('aiSafetyAgreed', '1'); } catch (e) {}")
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}',
                  wait_until='load')
        page.wait_for_timeout(600)   # let the live socket connect
        check(page_of(page.url) == 'Results',
              f'the participant renders the outro (Results) page '
              f'(at {page_of(page.url)})')
        # ARMED, REALLY — the guard against this leg passing because the
        # monitor never engaged: the script started, the server sent the
        # config, and the config says record-only.
        armed = page.evaluate("""() => ({
            started: !!window._tabmonStarted,
            cfg: (typeof js_vars !== 'undefined' && js_vars.AI_SAFETY_CONFIG)
                 || null,
            live: typeof liveSend === 'function'})""")
        check(armed['started'], 'the monitor script actually started '
                                '(window._tabmonStarted)')
        check(bool(armed['cfg']) and armed['cfg'].get('ejects') is False,
              f'this page\'s js_vars carry AI_SAFETY_CONFIG with ejects:false '
              f'(got {armed["cfg"]})')
        check(armed['live'], 'the live socket is up (liveSend exists)')

        # Playwright pins every page it drives to "focused" (focus emulation),
        # which swallows the very events this leg exists to fire — off it goes
        # for the page under test.
        cdp = context.new_cdp_session(page)
        cdp.send('Emulation.setFocusEmulationEnabled', {'enabled': False})
        own_tid = cdp.send('Target.getTargetInfo')['targetInfo']['targetId']
        with context.expect_page() as pop:
            page.evaluate("() => window.open('about:blank', '_blank')")
        distractor = pop.value
        cdp2 = context.new_cdp_session(distractor)
        distractor_tid = cdp2.send('Target.getTargetInfo')['targetInfo']['targetId']
        bcdp = browser.new_browser_cdp_session()
        # Opening the tab may itself have foregrounded it — come back first so
        # every cycle below starts from a focused study tab.
        bcdp.send('Target.activateTarget', {'targetId': own_tid})
        page.wait_for_timeout(400)

        for cycle in range(1, cycles + 1):
            page.evaluate("""() => { window._blurSeen = false;
                window.addEventListener('blur',
                    () => { window._blurSeen = true; }, {once: true}); }""")
            bcdp.send('Target.activateTarget', {'targetId': distractor_tid})
            # Hold the tab away for LONGER than the violation threshold, so
            # the monitor's own timer runs out for real.
            page.wait_for_timeout(threshold_ms + 2000)
            check(page.evaluate('() => window._blurSeen'),
                  f'cycle {cycle}: the browser fired a REAL blur event at the '
                  f'study tab (tab switch via the browser\'s own machinery)')
            # Measured WHILE the tab is still away — the moment the ejecting
            # phase would be showing its full-screen overlay.
            ui = page.evaluate("""() => ({
                overlay: !!document.querySelector('.tabmon-overlay'),
                overlayVisible: !!document.querySelector(
                    '.tabmon-overlay.is-visible'),
                modalVisible: !!document.querySelector(
                    '.tabmon-modal.is-visible')})""")
            check(not ui['overlay'],
                  f'cycle {cycle}: NO overlay is even in the DOM while blurred '
                  f'past the threshold (record-only mode builds no monitor UI)')
            check(not ui['overlayVisible'] and not ui['modalVisible'],
                  f'cycle {cycle}: …and nothing monitor-shaped is visible')
            bcdp.send('Target.activateTarget', {'targetId': own_tid})
            page.wait_for_timeout(700)   # real focus event + liveSend round trip
            # No warning modal on return either. If one IS present (that is a
            # red run), dismiss it so the NEXT cycle still measures the
            # server's consequence rather than the client refusing to count
            # behind an open modal.
            modal_open = page.evaluate(
                "() => !!document.querySelector('.tabmon-modal.is-visible')")
            check(not modal_open,
                  f'cycle {cycle}: no warning modal on returning to the tab')
            if modal_open:
                page.evaluate("""() => { const b = document.getElementById(
                    'tabmon-modal-btn'); if (b) b.click(); }""")
                page.wait_for_timeout(200)
            s = DBSession()
            try:
                p = s.query(Participant).filter_by(code=code).one()
                outro_count = p.vars.get('focus_loss_count_outro') or 0
                eject_count = p.vars.get('focus_loss_count') or 0
                dq = bool(p.vars.get('ai_safety_disqualified'))
                exit_code = p.vars.get('exit_code')
            finally:
                s.close()
            check(outro_count == cycle,
                  f'cycle {cycle}: the violation IS recorded server-side, in '
                  f'the outro\'s own column (focus_loss_count_outro = '
                  f'{outro_count})')
            check(eject_count == 0,
                  f'cycle {cycle}: the EJECTING column is untouched '
                  f'(focus_loss_count = {eject_count})')
            check(not dq and exit_code != common.EXIT_CODES['tab_monitor'],
                  f'cycle {cycle}: not disqualified (ai_safety_disqualified='
                  f'{dq}, exit_code={exit_code})')

        # …and after as many violations as would disqualify in intro/main,
        # the participant still has their page: a reload re-runs the whole
        # is_displayed chain, which is exactly how an ejection would land them
        # on Ended.
        page.goto(f'{server.base}/InitializeParticipant/{code}',
                  wait_until='load')
        page.wait_for_timeout(300)
        check(page_of(page.url) == 'Results',
              f'after {cycles} recorded violations (>= the ejecting phase\'s '
              f'limit of {max_violations}) a reload still lands on Results, '
              f'not an ending (at {page_of(page.url)})')
        screenshot(page, 'outro_after_violations', 'laptop_1280x720')
        geometry['outro_no_eject'] = dict(
            cycles=cycles, threshold_ms=threshold_ms,
            max_violations=max_violations)
        context.close()
    finally:
        if browser is not None:
            browser.close()
        xvfb.terminate()
        xvfb.wait(timeout=5)


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

    for key in ('consent_lab', 'consent_prolific', 'screened_out'):
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
        // BODY COPY, not the first <p> in the DOM. The shipped instructions
        // open with a template note carrying an inline `font-size: 14px`, and
        // `--read-measure` is `68ch` — which resolves against each element's
        // OWN font. Measured blind, this leg was comparing that note's 519px
        // against its own 519px probe and passing on a tautology; the real body
        // copy is 720px against a 726px measure (found 2026-08-13 while adding
        // the pager-alignment leg). Same defect class as the one that leg
        // exists for, which is why it is fixed rather than noted.
        const p = Array.from(document.querySelectorAll(
                  '.instruction-block > p'))
            .find(el => !(el.getAttribute('style') || '').includes('font-size')
                     && el.getBoundingClientRect().width > 0);
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
    # CONSENT NEUTRALITY, as amended on 2026-08-11 (change_requests items 12 +
    # 14). The lab consent page still never names the platform. The ONLINE one
    # now does, in exactly ONE place: the contact sentence, which tells the
    # participant how to reach a human. Everything else — no ID field, no
    # completion code, no CREED header — is unchanged, so this asserts the new
    # rule rather than dropping the old one.
    lab_text = facts['consent_lab']['laptop_1280x720']['text']
    check('Prolific' not in lab_text,
          'consent_lab: the participant never READS the word Prolific')
    check('raise your hand' in lab_text.lower(),
          'consent_lab: the contact sentence points at the experimenter in the '
          'room')
    pro_text = facts['consent_prolific']['laptop_1280x720']['text']
    check(pro_text.count('Prolific') == 1,
          f'consent_prolific: Prolific is named EXACTLY once '
          f'(got {pro_text.count("Prolific")})')
    check('contact the researchers through Prolific' in ' '.join(pro_text.split()),
          'consent_prolific: …and that once is the contact sentence')
    check('raise your hand' not in pro_text.lower(),
          'consent_prolific: no lab wording online')
    for key in ('consent_lab', 'consent_prolific'):
        text = facts[key]['laptop_1280x720']['text']
        check('Welcome to' not in text, f'{key}: no CREED welcome wording')
        # The duration/fee sentence is behind a flag that ships OFF (item 1).
        check('takes about' not in text and 'You will receive a payment' not in text,
              f'{key}: the duration/fee paragraph is hidden by default '
              f'(show_duration_and_fee)')
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

    section('L2. The tab-monitor agreement bolds its one load-bearing sentence')
    bold = None
    for vp in VIEWPORTS:
        code, _ = walk_to(server.base, create_session('prolific', num_participants=2),
                          'AISafetyAgree')
        context = browser.new_context(viewport=VIEWPORTS[vp])
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{code}', wait_until='load')
        bold = page.evaluate("""() => Array.from(
            document.querySelectorAll('.experimental-content strong')).map(
                s => ({text: s.innerText.trim(),
                       weight: getComputedStyle(s).fontWeight}))""")
        texts = [b['text'] for b in bold]
        check(any('Repeated inactivity will end your participation' in t
                  for t in texts),
              f'{vp}: the inactivity consequence is BOLD on the page '
              f'({texts})')
        context.close()
    geometry['ai_safety_bold'] = bold

    section('L. The screen-out page: its own wording, and its two unequal paths')
    text = facts['screened_out']['phone_375x667']['text']
    flat = ' '.join(text.split())
    check('computer' in flat.lower() or 'desktop' in flat.lower()
          or 'laptop' in flat.lower(),
          f'the phone screen-out explains the computer-only rule '
          f'(text: {flat[:120]!r})')
    check('phone' in flat.lower() and 'mobile device' not in flat.lower(),
          'it says PHONE, never "mobile device" (a study may accept tablets)')
    check('Your place is still open' in flat,
          'the SWITCH-DEVICE path promises their place is still open')
    check('Do not press the button below' in flat,
          'and tells them not to press the irreversible one')
    # It is served at the CONSENT page's own index — that is what holds the
    # participant somewhere a later request can re-decide.
    check(facts['screened_out']['laptop_1280x720']['url_page'] == 'welcome',
          'the screened-out participant is HELD on the entry page, not walked '
          'to an ending they could never come back from')


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
    # LAPTOP, not phone. The phone used to be the surest overflow, but since
    # improvement_suggestions item 1 a phone has no in-card scroll region at
    # all — so measuring the in-card shadow there would measure nothing and
    # skip silently. 1280x720 is now the smallest viewport that still uses the
    # card-scroll model, which is what this layer belongs to.
    vp = VIEWPORTS['laptop_1280x720']
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
    # THE BOTTOM AFFORDANCE AT THE END, MEASURED AGAINST ITSELF (2026-08-13).
    #
    # `bottom_at_end < bottom_at_start` compares two DIFFERENT sets of pixels —
    # the strip at the top of the scroll versus the strip at the end — so it
    # silently assumes the content that ends up under the edge is no darker than
    # the content that started there. That is a fact about the page, not about
    # the affordance. Measured when the consent card's rhythm changed: at the
    # end of the scroll the last 8px now hold a line of the contact sentence, so
    # darkness went 2.90 -> 3.58 and the leg went red even though the mask was
    # correctly OFF (the class assertion below passes).
    #
    # So the pixels are compared with themselves, at the same scroll position,
    # with the fade forced back on: if the mask were still applied it would
    # LIGHTEN exactly these pixels. That isolates the affordance from whatever
    # copy happens to sit at the edge, which is what the check was always for.
    faded_again = page.evaluate("""() => {
        const el = document.querySelector('.experimental-content');
        el.classList.add('is-scrollable-down');
        return true;
    }""")
    page.wait_for_timeout(80)
    bottom_forced = strip_darkness('bottom')
    page.evaluate("""() => document.querySelector('.experimental-content')
        .classList.remove('is-scrollable-down')""")
    check(faded_again and bottom_at_end >= bottom_forced,
          f'at the end of the content the BOTTOM fade is OFF — the same pixels '
          f'are darker than they would be with it on '
          f'({bottom_at_end:.2f} unmasked vs {bottom_forced:.2f} masked)')
    # Recorded, not asserted: the start-vs-end comparison is a fact about which
    # copy sits at the edge (see above), so it is printed for a reader and kept
    # in geometry.json for diffing, and no longer decides anything.
    print(f'       bottom strip darkness, scroll start -> end: '
          f'{bottom_at_start:.2f} -> {bottom_at_end:.2f}')
    geometry['scroll_shadow'] = {
        'top_at_start': round(top_at_start, 3),
        'bottom_at_start': round(bottom_at_start, 3),
        'top_at_end': round(top_at_end, 3),
        'bottom_at_end': round(bottom_at_end, 3),
    }
    context.close()


# ==========================================================================
# THE GEOMETRY BASELINE  (--diff / --update-baseline)
# ==========================================================================
# WHY: every other check in this file is an absolute threshold, so it catches
# BROKEN — a card taller than the viewport, a ring clipped by a scroll edge. A
# layout REGRESSION is usually not broken, it is CHANGED: the Next button moves
# 40px up, the reading band narrows, the eyebrow drifts. Nothing here would say
# a word. This compares a run against a committed baseline and fails on
# movement, printing page, viewport, element, old, new and delta so the numbers
# are readable while scrolling a terminal.
#
# The three decisions behind it — the tolerance, what is in the baseline and
# what is deliberately not, and how to regenerate it — are written at the top of
# the baseline file itself, because that is the file someone reads in a review.
BASELINE_PATH = os.path.join(_TESTS_DIR, 'geometry_baseline.json')

# ±3px. NOT zero: these numbers come from getBoundingClientRect via Math.round,
# so a value sitting on a half-pixel rounds either way between runs (±1); the
# fluid type and spacing (clamp()/vw) resolve to fractions that round the same
# way; and a platform whose scrollbar is a pixel wider shifts a centred band by
# about one more. 3px stays well under what a human notices as "moved" — the
# real regressions this exists for are tens of pixels — while staying above the
# noise floor. If some field turns out to be noisier than this, EXCLUDE it (see
# BASELINE_FIELDS) rather than raising the tolerance for everything.
BASELINE_TOLERANCE_PX = 3

# WHAT GOES IN: the boxes that pin a page's layout, per page and viewport.
BASELINE_FIELDS = {
    'card': ('x', 'y', 'w', 'h'),
    'shell': ('w', 'h'),
    'content': ('x', 'y', 'w', 'h', 'scrollH', 'clientH'),
    'header': ('x', 'y', 'w', 'h'),
    'eyebrow': ('x', 'y', 'h'),
    'title': ('x', 'y', 'w', 'h'),
    'panel': ('x', 'y', 'w', 'h'),
    'button': ('x', 'y', 'w', 'h'),
    'ghost_button': ('x', 'y', 'w', 'h'),
    'logo_img': ('h',),
    'first_option': ('x', 'y', 'w', 'h'),
    'section_text': ('x', 'y', 'w', 'h'),
}

# …and the whole-run measurement groups that are pure numbers.
BASELINE_GROUPS = ('band_centring', 'eyebrow', 'card_widths', 'card_heights',
                   'card_min_derivation', 'catchment', 'instructions_band',
                   'short_page', 'consent_choice', 'task_progress',
                   'results_total_row', 'phone_flow')

# WHAT IS DELIBERATELY OUT, and why — this list is the honest half of the
# feature, because a baseline full of noise gets ignored within a week:
#   * `text` (the 4000-char page dump) — every copy edit churns it, and it says
#     nothing about layout; the wording has its own assertions.
#   * colours, fonts, `display`/`overflow`/`textAlign` strings — real contracts,
#     but each is already asserted directly by the check that owns it, and a
#     diff would report them as "changed" without adding information.
#   * every PIXEL-DARKNESS number (`affordance`, `phantom`, `scroll_shadow`,
#     the scroll cue's band readings) — analogue values from antialiased
#     rendering; they drift by fractions between runs and already have
#     thresholds with an order of magnitude of headroom.
#   * anything CONTENT-RANDOM: the results receipt's figures (payoffs are drawn
#     at random per run), the disqualification text, the preserved answers.
#   * `focus_ring` — it depends on a CSS transition settling and on how many
#     Tab presses reached the first option, which is timing, not layout.
#   * `viewport` and `url_page` — constants by construction.


def baseline_view(geo):
    """Flatten the run's geometry into {path: number} for comparison."""
    flat = {}

    def put(path, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        flat[path] = value

    for key, per_vp in sorted(geo.items()):
        if key in ('pages',):
            continue
        if key in BASELINE_GROUPS:
            def walk(node, path):
                if isinstance(node, dict):
                    for k, v in sorted(node.items()):
                        walk(v, f'{path}/{k}')
                else:
                    put(path, node)
            walk(per_vp, key)
            continue
        # per-page/viewport facts (everything render_all recorded)
        if not isinstance(per_vp, dict):
            continue
        for vp_name, facts_ in sorted(per_vp.items()):
            if not isinstance(facts_, dict):
                continue
            for element, fields in BASELINE_FIELDS.items():
                box = facts_.get(element)
                if not isinstance(box, dict):
                    continue
                for field in fields:
                    if field in box:
                        put(f'{key}/{vp_name}/{element}/{field}', box[field])
    return flat


def write_baseline(geo):
    flat = baseline_view(geo)
    payload = {
        '_README': [
            "Layout baseline for tests/render_check.py. Committed ON PURPOSE, "
            "and to tests/ rather than _ai/ (which is gitignored), so that a "
            "layout change shows up as a reviewable diff in this file.",
            "",
            "HOW TO USE IT",
            "  python tests/render_check.py --diff             compare a run "
            "against this file; exits non-zero on movement, printing page, "
            "viewport, element, old, new and delta.",
            "  python tests/render_check.py --update-baseline  REGENERATE it. "
            "This is the command to run when a layout change is INTENTIONAL: "
            "run it, then read the diff of this file as part of the change.",
            "",
            f"TOLERANCE: {BASELINE_TOLERANCE_PX}px. Not zero — these numbers "
            "are rounded rects, so a half-pixel rounds either way between runs "
            "(±1), fluid clamp()/vw values resolve to fractions, and a "
            "different scrollbar width shifts a centred band by about one "
            "more. 3px is far below what reads as 'moved' (real regressions "
            "here are tens of pixels) and above the noise. A field noisier "
            "than this should be EXCLUDED, not have the tolerance raised.",
            "",
            "WHAT IS IN: the boxes that pin layout (card, shell, content "
            "region and its scroll height, header strip, eyebrow, title, "
            "panel, buttons, first option card, logo height, section text) per "
            "page and viewport, plus the numeric measurement groups (band "
            "centring, eyebrow alignment, card widths and heights, the "
            "card-floor derivation, scroll catchment, instructions band, short "
            "page balance, consent choice position, task progress bar, the "
            "results Total row, and the phone page-flow numbers).",
            "",
            "WHAT IS OUT, and why: page text (churns on every copy edit and is "
            "not layout); colours/fonts/display strings (each already has its "
            "own assertion); all pixel-darkness readings (analogue, "
            "antialiasing-dependent, already thresholded); anything "
            "content-random such as the results figures (payoffs are drawn at "
            "random per run); and the focus-ring numbers (they depend on a CSS "
            "transition settling and on Tab timing, not on layout).",
        ],
        'tolerance_px': BASELINE_TOLERANCE_PX,
        'measurements': flat,
    }
    with open(BASELINE_PATH, 'w') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    print(f'\nwrote {len(flat)} measurements -> '
          f'{os.path.relpath(BASELINE_PATH, _APP_ROOT)}')
    print('   review the diff of that file: it IS the record of what moved.')


def diff_baseline(geo):
    """Compare this run with the committed baseline. Returns a failure count."""
    section('GEOMETRY DIFF vs the committed baseline')
    try:
        with open(BASELINE_PATH) as fh:
            stored = json.load(fh)
    except (OSError, ValueError):
        print(f'  no baseline at {os.path.relpath(BASELINE_PATH, _APP_ROOT)} — '
              f'create it with:  python tests/render_check.py --update-baseline')
        return 1
    tol = stored.get('tolerance_px', BASELINE_TOLERANCE_PX)
    old = stored.get('measurements', {})
    new = baseline_view(geo)

    moved = []
    for path, was in sorted(old.items()):
        if path not in new:
            continue
        delta = new[path] - was
        if abs(delta) > tol:
            moved.append((path, was, new[path], delta))
    gone = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))

    for path, was, now, delta in moved:
        parts = path.split('/')
        where = ' · '.join(parts[:-1])
        what = parts[-1]
        print(f'  [MOVED] {where}  {what}: {was} -> {now} '
              f'({delta:+}px, tolerance ±{tol})')
    if gone:
        print(f'  [GONE ] {len(gone)} measurement(s) the baseline has and this '
              f'run does not — a check was removed or a page stopped '
              f'rendering:')
        for path in gone[:12]:
            print(f'          {path}')
        if len(gone) > 12:
            print(f'          … and {len(gone) - 12} more')
    if added:
        print(f'  [NEW  ] {len(added)} measurement(s) this run has and the '
              f'baseline does not (new checks — re-run with '
              f'--update-baseline to adopt them)')

    unchanged = len(set(old) & set(new)) - len(moved)
    print(f'  {unchanged} measurement(s) within ±{tol}px of the baseline')
    if moved or gone:
        _failures.append(
            f'geometry diff: {len(moved)} element(s) moved more than {tol}px'
            + (f', {len(gone)} measurement(s) missing' if gone else ''))
        print('  FAIL — if these moves are INTENTIONAL, adopt them with:'
              '  python tests/render_check.py --update-baseline')
        return 1
    print('  PASS — nothing moved beyond the tolerance')
    return 0


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
                      f'docs/headless_chromium_recipe.md')
                return 2
            try:
                facts = render_all(server, browser)
                check_card_gaps(facts)
                check_scrolling(server, browser, facts)
                if not LONG_QUIZ:
                    check_constant_card(facts)
                    check_card_min_derivation(server, browser, facts)
                    check_titles_centred(facts)
                    check_scroll_catchment(server, browser)
                    check_scroll_cue(server, browser)
                    check_task_progress(server, browser, facts)
                    check_results_receipt(server, browser)
                    check_results_table_look(server, browser)
                    check_sepa_warning_is_a_warning(server, browser)
                    check_pager_aligns_with_text(server, browser)
                    check_reread_dialog(server, browser)
                    check_lab_experimenter_notice(server, browser)
                    check_warning_modal(server, browser)
                    check_consent_single_question(server, browser, facts)
                    check_page_anatomy(server, browser, facts)
                    check_lab_only_copy(server, browser)
                    check_screenout_way_out(server, browser)
                    check_completion_link_nojs(server, browser)
                    check_narrow_desktop_window(server, browser)
                    check_phone_page_flow(server, browser)
                    check_dq_ending(server, browser)
                    check_scroll_really_moves(server, browser)
                    check_scroll_affordance(server, browser)
                    check_no_phantom_affordance(server, browser)
                    check_no_sideways_overflow(facts, server, browser)
                    check_band_centred(server, browser)
                    check_short_page_balance(server, browser)
                    check_eyebrow_alignment(server, browser)
                    check_consent_choice_visible(server, browser, facts)
                    check_logo_footer_rule(server, browser)
                    check_focus_rings(server, browser)
                    check_overlay(server, browser)
                    check_outro_never_ejects(server, pw)
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

    # THE BASELINE IS THE NORMAL PASS ONLY. The long-quiz pass deliberately
    # injects eight extra questions to force an overflow, so its geometry is a
    # different page by construction and must never be compared with, or
    # written into, the committed baseline.
    if not LONG_QUIZ:
        if UPDATE_BASELINE:
            write_baseline(geometry)
        elif DIFF:
            diff_baseline(geometry)
        else:
            print('   (layout regressions: python tests/render_check.py --diff)')

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
        # Deliberately WITHOUT --diff/--update-baseline: see the note above.
        rc |= subprocess.call([sys.executable, os.path.abspath(__file__),
                               '--long-quiz'])
    return rc


if __name__ == '__main__':
    sys.exit(main())
