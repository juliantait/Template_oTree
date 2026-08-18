#!/usr/bin/env python
"""PASSIVE FOCUS TRACE — the net-new observer PRODUCES a record, and is
independent of the tab monitor.

WHAT THIS PROVES, AND WHY EACH CHECK EARNS ITS PLACE
----------------------------------------------------
The focus trace is client-side instrumentation, and CLAUDE.md's rule for that
is blunt: *wiring can be verified, a silent refusal to run cannot — unless
something asserts that observations actually ARRIVE.* So this file does not stop
at "the page is configured to record": it drives the value all the way into the
`main.Player` row (§2), and it drives the browser half in a real Chromium and
reads the numbers it writes into the hidden inputs (§5). A test that only
checked the hidden inputs are PRESENT would pass against a dead observer.

  §1  WIRING, both directions. With telemetry_focus_trace ON the served task
      page carries both hidden inputs AND focus_trace.js; with it OFF neither
      appears — the module is a genuine no-op, not merely dormant.
  §2  THE OBSERVATION ARRIVES. A POST of the task form with a positive count and
      ms lands in main.Player.focus_trace_departures / _unfocused_ms, read back
      from the database. This is the check the CLAUDE.md rule demands.
  §3  NO-JS SUBMIT IS SAFE. The same form posted with the two fields EMPTY (a
      participant whose JS never ran) still submits; the columns read back as
      None via field_maybe_none, never a bare-null TypeError.
  §4  INDEPENDENT OF THE TAB MONITOR. A participant with a positive trace has
      ZERO tab-monitor violations and is not disqualified; firing a real
      tab-monitor focus_loss leaves the focus_trace_* columns untouched; and the
      two browser halves are different files, with focus_trace.js touching no
      tab-monitor symbol, calling no liveSend and no preventDefault.
  §5  THE exp_pilots CLAIMS, in a real browser (skipped if Chromium is absent).
      Verified against the actual JS, not the docs: one departure counts once
      however the browser reports it (blur AND visibilitychange dedupe via the
      open-interval guard); a blur within 300 ms of a mousedown is ignored; the
      unfocused ms include an interval STILL OPEN at submit; a clean page posts
      0 / 0.0.

RUN (boots oTree in-process against a throwaway DB and self-hosts uvicorn):

    /home/dev/.venv-otree/bin/python scripts/tests/focus_trace_test.py

For §5 the browser needs its system libraries — see
docs/headless_chromium_recipe.md — run with LD_LIBRARY_PATH set. Without a
browser §5 is SKIPPED (and said so, loudly), never silently passed. Exit 0 = all
run checks passed.
"""
import os
import socket
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

# THROWAWAY DB + PRODUCTION, before importing oTree (writing_tests.md: a leak
# test against a DEBUG server measures oTree's var-dump, not the participant's
# page; and the repo's own db.sqlite3 must never be touched).
_TMPDIR = tempfile.mkdtemp(prefix='tmpl_focus_trace_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_TMPDIR, 'db.sqlite3')}"
os.environ['OTREE_PRODUCTION'] = '1'
os.environ.setdefault('OTREE_SECRET_KEY', 'focus-trace-check')

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# oTree opens the RELATIVE name db.sqlite3 in the CWD at import time and ignores
# the path inside a sqlite DATABASE_URL — import otree.database chdir'd into the
# temp dir so the connection binds there, then chdir back (the template roots
# and _static are equally CWD-relative). See otree_inprocess.boot / render_check.
os.chdir(_TMPDIR)
import otree.database  # noqa: E402
os.chdir(REPO_ROOT)

import otree.main as otree_main  # noqa: E402
otree_main.setup()

from otree.database import engine, AnyModel, DBSession  # noqa: E402
AnyModel.metadata.create_all(engine)

import requests  # noqa: E402
import uvicorn  # noqa: E402
from otree.asgi import app  # noqa: E402
from otree.session import create_session  # noqa: E402
from otree.models import Participant, Session  # noqa: E402
from otree.common import get_models_module  # noqa: E402

import common  # noqa: E402
import main  # noqa: E402
from http_flow_test import FormParser, build_payload  # noqa: E402

_failures = []


def _strip_js_comments(src):
    """Remove /* ... */ blocks and // ... line comments so a source-level
    guarantee is asserted on CODE, not on the comments that describe it."""
    import re
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)//.*$', '', src)
    return src


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# --------------------------------------------------------------------------
# a REAL server (the browser and the HTTP walk both need one)
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


DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
              'Safari/537.36')
# The quiz answered from the item definitions, not from the page (production
# ships no solutions) — the one derivation, like the other suites here.
from quiz_answers import CORRECT as QUIZ_CORRECT  # noqa: E402


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


def walk_to(base, session, stop, limit=90):
    """Enter through the real front door and post pages until `stop` is current.

    Returns (participant_code, requests.Session, last_response) so the caller can
    keep posting from the stopped page with the SAME cookie jar."""
    s = requests.Session()
    s.headers['User-Agent'] = DESKTOP_UA
    r = s.get(f'{base}/join/{anon_code(session.code)}', allow_redirects=True)
    answers = dict(QUIZ_CORRECT)
    for _ in range(limit):
        assert r.status_code < 500, f'HTTP {r.status_code} at {r.url}'
        if page_of(r.url) == stop:
            return code_of(r.url), s, r
        fp = FormParser()
        fp.feed(r.text)
        if not fp.found_form:
            break
        r = s.post(r.url, data=build_payload(fp.inputs, {}, answers, warn=False),
                   allow_redirects=True)
    raise AssertionError(f'never reached {stop}; stuck at {r.url}')


def main_player(participant_code, round_number=1):
    """The main.Player row for a participant, read via the ORM. Nullable columns
    are read with field_maybe_none in the caller, never bare."""
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=participant_code).one()
        MainPlayer = get_models_module('main').Player
        pl = (s.query(MainPlayer)
              .filter(MainPlayer.participant_id == p.id,
                      MainPlayer.round_number == round_number).one())
        return dict(
            departures=pl.field_maybe_none('focus_trace_departures'),
            unfocused_ms=pl.field_maybe_none('focus_trace_unfocused_ms'),
            tab_task=p.vars.get('tab_monitor_focus_loss_count'),
            tab_dq=p.vars.get('tab_monitor_disqualified'),
            exit_code=p.vars.get('exit_code'),
        )
    finally:
        s.close()


def post_game_form(base, s, resp, overrides):
    """POST the current (GameStart) form with `overrides` merged in, exactly as a
    browser would submit its hidden fields. Returns the response."""
    fp = FormParser()
    fp.feed(resp.text)
    payload = build_payload(fp.inputs, overrides, {}, warn=False)
    return s.post(resp.url, data=payload, allow_redirects=True)


# ==========================================================================
def http_checks(server):
    JS_FILE = 'focus_trace.js'
    IDS = ('id="focus_trace_departures"', 'id="focus_trace_unfocused_ms"')

    section('1. wiring — present with the flag ON, absent with it OFF (no-op)')
    # prolific resolves telemetry_focus_trace = True (see settings profiles).
    sess_on = create_session('prolific', num_participants=2)
    code_on, s_on, resp_on = walk_to(server.base, sess_on, 'GameStart')
    html_on = resp_on.text
    check(all(tok in html_on for tok in IDS),
          'flag ON: the served task page carries BOTH focus-trace hidden inputs')
    check(JS_FILE in html_on,
          'flag ON: the served task page ships focus_trace.js')

    # lab resolves telemetry_focus_trace = False.
    sess_off = create_session('lab', num_participants=2)
    _, _, resp_off = walk_to(server.base, sess_off, 'GameStart')
    html_off = resp_off.text
    check(not any(tok in html_off for tok in IDS),
          'flag OFF: NEITHER hidden input is rendered (a genuine no-op)…')
    check(JS_FILE not in html_off,
          '…and focus_trace.js is not shipped at all')
    # Positive control: the page itself DID render (so the absence above is a
    # real absence on a real page, not an assertion against a blank/error page).
    check('Press Next' in html_off,
          'the flag-OFF page is the real task page (absence asserted against '
          'presence, per writing_tests.md)')

    section('2. THE OBSERVATION ARRIVES — a positive trace reaches main.Player')
    # A browser fills these hidden inputs from focus_trace.js; here we post the
    # values a browser WOULD post and require them in the database.
    post_game_form(server.base, s_on, resp_on,
                   {'focus_trace_departures': '3',
                    'focus_trace_unfocused_ms': '1234.5'})
    row = main_player(code_on)
    check(row['departures'] == 3,
          f'focus_trace_departures reached the Player row (={row["departures"]})')
    check(abs((row['unfocused_ms'] or 0) - 1234.5) < 1e-6,
          f'focus_trace_unfocused_ms reached the Player row (={row["unfocused_ms"]})')

    section('3. no-JS submit is safe — empty fields, no 500, read back as None')
    sess_njs = create_session('prolific', num_participants=2)
    code_njs, s_njs, resp_njs = walk_to(server.base, sess_njs, 'GameStart')
    r_after = post_game_form(server.base, s_njs, resp_njs,
                             {'focus_trace_departures': '',
                              'focus_trace_unfocused_ms': ''})
    check(r_after.status_code < 500,
          f'the empty-field task submit did not 500 (HTTP {r_after.status_code})')
    check(page_of(r_after.url) != 'GameStart',
          'the participant advanced past the task page on a no-JS submit')
    row_njs = main_player(code_njs)
    check(row_njs['departures'] is None and row_njs['unfocused_ms'] is None,
          'both columns read back as None via field_maybe_none — a bare read '
          'would have been the TypeError this template hunts')

    section('4. independent of the tab monitor')
    # (a) the §2 participant: a positive trace, but the tab monitor counted
    #     nothing and did not disqualify — the trace is measurement, not
    #     enforcement, and posting it touched no tab-monitor variable.
    check((row['tab_task'] or 0) == 0 and not row['tab_dq'],
          'a participant with a positive focus trace has ZERO tab-monitor '
          'violations and is not disqualified (positive trace, zero violations)')

    # (b) the reverse: firing a REAL tab-monitor focus_loss must not write the
    #     focus_trace_* columns. The monitor and the trace never cross-write.
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code_on).one()
        MainPlayer = get_models_module('main').Player
        pl = (s.query(MainPlayer)
              .filter(MainPlayer.participant_id == p.id,
                      MainPlayer.round_number == 1).one())
        main.GameStart.live_method(pl, {'type': 'focus_loss', 'event_id': 'ft1'})
        s.commit()
        tab_now = p.vars.get('tab_monitor_focus_loss_count')
        # Re-read the trace columns straight from the row.
        ft_dep = pl.field_maybe_none('focus_trace_departures')
        ft_ms = pl.field_maybe_none('focus_trace_unfocused_ms')
    finally:
        s.close()
    check(tab_now == 1,
          f'the tab monitor counted its own focus_loss (tab count={tab_now})…')
    check(ft_dep == 3 and abs((ft_ms or 0) - 1234.5) < 1e-6,
          '…and the focus_trace_* columns are UNCHANGED by it (3 / 1234.5) — '
          'the two observers never cross-write')

    # (c) source-level separate-observer guarantees. Asserted on the CODE, not
    #     the prose: focus_trace.js's own comments DESCRIBE what it must not do
    #     ("never calls liveSend", "references no tab-monitor variable"), so a
    #     raw substring scan would flag the file for documenting its own
    #     guarantee. Strip comments first — the guarantee is about behaviour.
    ft_path = os.path.join(REPO_ROOT, '_static', 'global', 'js', 'focus_trace.js')
    tabmon_path = os.path.join(REPO_ROOT, '_static', 'global', 'js',
                               'tab_monitor.js')
    with open(ft_path) as fh:
        js = fh.read()
    code = _strip_js_comments(js).lower()
    check(os.path.exists(tabmon_path)
          and os.path.abspath(tabmon_path) != os.path.abspath(ft_path),
          'focus_trace.js and tab_monitor.js are DIFFERENT files')
    check('livesend' not in code,
          'focus_trace.js CODE never calls liveSend (no server channel of its own)')
    check('preventdefault' not in code,
          'focus_trace.js CODE never calls preventDefault (cannot block navigation)')
    check('tabmon' not in code and 'tab_monitor' not in code,
          'focus_trace.js CODE references NO tab-monitor symbol')
    # Presence, so the absence checks above are about a real, working observer.
    check('addeventlistener' in code and 'focus_trace_departures' in code
          and 'focus_trace_unfocused_ms' in code,
          'focus_trace.js is its own observer: adds its own listeners and '
          'writes its own two hidden inputs')


# ==========================================================================
# §5 — the exp_pilots CLAIMS, verified in a real browser against the real JS.
# Synthetic dispatchEvent fires addEventListener handlers regardless of the
# window's real focus, so headless Chromium (which can never truly blur) is fine
# here — we are exercising the LISTENERS, not the OS focus state.
# ==========================================================================
BROWSER_HARNESS = r"""
() => {
    // Reset the trace to a known state by reloading is heavy; instead we read
    // the live hidden inputs the on-page script maintains.
    const dep = () => Number(document.getElementById('focus_trace_departures').value);
    const ms = () => Number(document.getElementById('focus_trace_unfocused_ms').value);
    return {dep: dep(), ms: ms()};
}
"""


def browser_checks(server):
    section('5. the exp_pilots claims — real Chromium, real focus_trace.js')
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f'  [skip] playwright not importable ({e}); §5 not run')
        return False
    try:
        pw = sync_playwright().start()
    except Exception as e:
        print(f'  [skip] could not start playwright ({e}); §5 not run')
        return False
    browser = None
    try:
        try:
            browser = pw.chromium.launch()
        except Exception as e:
            print(f'  [skip] Chromium will not launch ({e}); §5 not run — see '
                  f'docs/headless_chromium_recipe.md')
            return False

        # A fresh prolific participant on the real served task page.
        sess = create_session('prolific', num_participants=2)
        code, _, resp = walk_to(server.base, sess, 'GameStart')
        page = browser.new_page()
        page.goto(str(resp.url), wait_until='load')
        # focus_trace.js overrides document.hidden reads via the Page Visibility
        # API; to drive visibilitychange we install a controllable getter.
        page.evaluate("""() => {
            window.__hidden = false;
            Object.defineProperty(document, 'hidden',
                {configurable: true, get: () => window.__hidden});
        }""")
        # focus_trace.js's mousedown grace compares performance.now() against
        # lastMouseDown, which INITIALISES to 0. A blur fired within 300 ms of
        # navigation start therefore falls inside the grace of that initial 0 and
        # is (correctly) ignored — an artefact of testing faster than any real
        # participant, who blurs long after load. Wait past the window first so
        # §5 measures the steady-state behaviour, not the first-300 ms edge.
        page.wait_for_timeout(400)

        def dep():
            return page.evaluate(
                "() => Number(document.getElementById('focus_trace_departures').value)")

        def ms():
            return page.evaluate(
                "() => Number(document.getElementById('focus_trace_unfocused_ms').value)")

        def fire(target, type_):
            page.evaluate(
                "([t, e]) => (t === 'win' ? window : document)"
                ".dispatchEvent(new Event(e))", [target, type_])

        def set_hidden(v):
            page.evaluate("(v) => { window.__hidden = v; }", v)

        # A clean page posts 0 / 0.0 (write() ran on load).
        check(dep() == 0 and ms() == 0.0,
              f'a page with no focus loss reads 0 / 0.0 (dep={dep()}, ms={ms()})')

        # ── Claim: one DEPARTURE counts once however the browser reports it. A
        #    tab switch fires blur AND visibilitychange; the open-interval guard
        #    makes the pair count once. ──
        fire('win', 'blur')
        after_blur = dep()
        set_hidden(True)
        fire('doc', 'visibilitychange')   # same departure, still open
        after_pair = dep()
        check(after_blur == 1 and after_pair == 1,
              f'blur THEN visibilitychange-hidden = ONE departure '
              f'(after blur={after_blur}, after pair={after_pair})')
        # Come back.
        set_hidden(False)
        fire('doc', 'visibilitychange')
        fire('win', 'focus')
        # A genuinely separate departure counts again.
        set_hidden(True)
        fire('doc', 'visibilitychange')
        check(dep() == 2,
              f'a second, separate departure increments the count (={dep()})')
        set_hidden(False)
        fire('doc', 'visibilitychange')
        fire('win', 'focus')

        # ── Claim: a blur within 300 ms of an in-page mousedown is IGNORED. ──
        before = dep()
        fire('doc', 'mousedown')
        fire('win', 'blur')       # immediately after — inside the grace window
        check(dep() == before,
              f'a blur right after a mousedown is ignored (grace window kept '
              f'the count at {before})')

        # ── Claim: the unfocused ms INCLUDE an interval still open at submit. ──
        set_hidden(True)
        fire('doc', 'visibilitychange')   # open an interval and leave it open
        time.sleep(0.25)
        # capture WITHOUT coming back — the exposed snapshot the task page can
        # call, which must fold the still-open interval into the total.
        page.evaluate("() => window.captureFocusTrace && window.captureFocusTrace()")
        open_ms = ms()
        check(open_ms >= 150,
              f'an interval still OPEN at snapshot is counted in unfocused_ms '
              f'(={open_ms:.0f} ms after ~250 ms away)')
        set_hidden(False)
        fire('doc', 'visibilitychange')
        return True
    finally:
        if browser is not None:
            browser.close()
        pw.stop()


def main_test():
    server = Server()
    server.start()
    try:
        http_checks(server)
        browser_checks(server)
    finally:
        server.stop()

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main_test()
