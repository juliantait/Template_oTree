"""EXPERIMENTER DASHBOARD — real-server, real-browser verification.

tests/dashboard_test.py proves the dashboard's contracts in-process (auth,
fail-soft, read-only, row truth). THIS file is the other half of the testing
standard: a REAL uvicorn server driven over real HTTP, and the page rendered
by REAL headless Chromium with the layout asserted by MEASUREMENT, because a
broken operator layout produces no error anywhere (CLAUDE.md: a layout change
needs a measured render check, not a look).

What is measured:
  * the login wall stands in a real browser (the dashboard URL lands on
    /login until oTree's own form is submitted);
  * the six timeline steps are EQUAL SPACING — six header cells and six
    track cells within 2px of each other, at two viewports;
  * the poll paints: rows appear without a reload, the status line ticks,
    and a repaint arrives within 2 poll intervals;
  * the marker carries the round ("2 of 3") during TASK; terminal rows show
    their emoji; the stalled row is visibly AMBER (pixel-sampled, not
    class-trusted); entry-only rows are dimmed and the header toggle hides
    them;
  * the table never scrolls the page horizontally at 1280px.

Screenshots land in _ai/dashboard_render/ for a human to flick through.

Run (see _ai/headless_chromium_recipe.md for the sysroot):
    LD_LIBRARY_PATH=<sysroot>/root/usr/lib/x86_64-linux-gnu \
        python tests/dashboard_render_check.py

The machine this template is developed on is memory-constrained: run nothing
else alongside, and retry once on exit code 137 before concluding anything.
"""
import os
import re
import socket
import sys
import threading
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, _APP_ROOT)

# Locked-down mode, like a real launch: the browser must hit the login wall.
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)

import requests  # noqa: E402
import uvicorn  # noqa: E402
from otree.asgi import app  # noqa: E402

import experimenter_dashboard as ed  # noqa: E402
from intro.quiz_items import QUIZ_ITEMS  # noqa: E402

OUT_DIR = os.path.join(_APP_ROOT, '_ai', 'dashboard_render')
os.makedirs(OUT_DIR, exist_ok=True)

PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 '
            'Mobile/15E148 Safari/604.1')
DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
              'Safari/537.36')

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


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
# staging: several participants at different points of the flow, over HTTP
# --------------------------------------------------------------------------
def payload_for(page, quiz_answers):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'ConfirmProlificID': {'participant_id_external': ''},
        'instructing': {},
        'quiz': dict(quiz_answers),
        'AISafetyAgree': {},
        'GameStart': {'client_ms': ''},
        'payoff': {},
        'Demographics': {'age': '30', 'gender': 'Female',
                         'bank': 'NL91ABNA0417164300',
                         'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def walk(base, code, quiz_answers, stop_after=None, quiz_posts=None,
         ua=DESKTOP_UA, max_steps=120):
    s = requests.Session()
    s.headers['User-Agent'] = ua
    resp = s.get(f'{base}/InitializeParticipant/{code}')
    quiz_posts = list(quiz_posts or [])
    statuses = [resp.status_code]
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None or page in ('Results', 'Ended'):
            break
        data = (quiz_posts.pop(0) if page == 'quiz' and quiz_posts
                else payload_for(page, quiz_answers))
        resp = s.post(resp.url, data=data)
        statuses.append(resp.status_code)
        if stop_after and page == stop_after:
            break
    assert all(st == 200 for st in statuses), \
        f'walking {code}: HTTP {statuses}'
    return resp


def set_participant(code, **fields):
    """Test-side write to simulate slow/DQ states (the dashboard only reads)."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        for name, value in fields.items():
            if name.startswith('vars.'):
                p.vars[name[5:]] = value
            else:
                setattr(p, name, value)
        s.commit()
    finally:
        s.close()


def stage_sessions(base):
    """One lab session with live stages + one prolific session with the
    terminal states. Returns (lab_session, prolific_session)."""
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}
    first = QUIZ_ITEMS[0]
    wrong = dict(correct)
    wrong[first['field']] = next(c for c in first['choices']
                                 if c != first['answer'])

    lab = ot.create_session('test', num_participants=6, label='')
    codes = ot.participant_codes(lab)
    ot.set_label(codes[0], 'Seat 01')
    ot.set_label(codes[1], 'Seat 02')
    ot.set_label(codes[2], 'Seat 03')
    ot.set_label(codes[3], 'Seat 04')
    ot.set_label(codes[4], 'Seat 05')
    # codes[5]: never arrives (entry-only, de-emphasised)
    walk(base, codes[0], correct, stop_after='welcome')     # on instructions
    walk(base, codes[1], correct, quiz_posts=[wrong],
         stop_after='quiz')                                 # on quiz, 1 wrong
    walk(base, codes[2], correct, stop_after='quiz')        # into the task
    walk(base, codes[2], correct, stop_after='payoff')      # → round 2 opens
    walk(base, codes[3], correct)                           # finished
    walk(base, codes[4], correct, stop_after='welcome')
    set_participant(codes[4],                               # AMBER: stalled
                    _last_page_timestamp=int(time.time()) - 400)

    pro = ot.create_session(
        'prolific', num_participants=4,
        modified_session_config_fields={'allowed_devices': 'computer'})
    pcodes = ot.participant_codes(pro)
    for i, pid in enumerate(pcodes):
        ot.set_label(pid, f'PROLIFIC{i:02d}')
    s = requests.Session()
    s.headers['User-Agent'] = DESKTOP_UA
    r = s.get(f'{base}/InitializeParticipant/{pcodes[0]}')
    s.post(r.url, data={'consent': 'False', 'is_mobile': '',
                        'device_info_json': '', 'participant_id_url': ''})
    walk(base, pcodes[1], correct, quiz_posts=[wrong, wrong, wrong])
    requests.get(f'{base}/InitializeParticipant/{pcodes[2]}',
                 headers={'User-Agent': PHONE_UA})
    walk(base, pcodes[3], correct, stop_after='quiz')
    set_participant(pcodes[3], **{'vars.ai_safety_disqualified': True,
                                  'vars.exit_code': -3})
    return lab, pro


# --------------------------------------------------------------------------
# HTTP-level assertions (real socket, no TestClient shortcuts)
# --------------------------------------------------------------------------
def check_http(base, lab, pro):
    section('real HTTP: auth wall and row truth')
    url = f'{base}{ed.URL_BASE}/{lab.code}'
    anon = requests.Session()
    r = anon.get(url, allow_redirects=False)
    check(r.status_code == 302 and '/login' in r.headers.get('location', ''),
          'real server: unauthenticated dashboard GET -> 302 /login')

    op = requests.Session()
    r = op.get(f'{base}/login')
    token = re.search(r'name="csrftoken" value="([^"]+)"', r.text).group(1)
    op.post(f'{base}/login', data={'username': 'admin', 'password': 'admin',
                                   'csrftoken': token})
    r = op.get(url)
    check(r.status_code == 200 and 'tl-header' in r.text,
          'real server: operator gets the dashboard after oTree login')

    data = op.get(f'{url}/data').json()
    rows = {x['label']: x for x in data['rows'] if not x.get('error')}
    check(data['ok'] and len(data['rows']) == 6,
          f'data: 6 rows for 6 participants (got {len(data["rows"])})')
    check(rows['Seat 01']['step'] == 'instructions',
          f"Seat 01 on instructions (got {rows['Seat 01']['step']})")
    check(rows['Seat 02']['step'] == 'quiz'
          and rows['Seat 02']['quiz']['attempts_wrong'] == 1,
          "Seat 02 on the quiz with one wrong attempt")
    check(rows['Seat 03']['step'] == 'task'
          and rows['Seat 03']['task_round'] == 2,
          f"Seat 03 mid-task carries round 2 of 3 "
          f"(got {rows['Seat 03']['task_round']})")
    check(rows['Seat 04']['step'] == 'done' and rows['Seat 04']['finished']
          and rows['Seat 04']['earnings'] is not None,
          "Seat 04 finished, earnings known")
    check(rows['Seat 05']['stalled'] is True,
          "Seat 05 is stalled (amber)")

    pdata = op.get(f'{base}{ed.URL_BASE}/{pro.code}/data').json()
    prows = {x['label']: x for x in pdata['rows'] if not x.get('error')}
    got = {k: v['terminal'] for k, v in prows.items()}
    check(got == {'PROLIFIC00': 'no_consent', 'PROLIFIC01': 'comprehension',
                  'PROLIFIC02': 'screened_out', 'PROLIFIC03': 'tab_monitor'},
          f'all four terminal states over real HTTP (got {got})')
    return op.cookies


# --------------------------------------------------------------------------
# the browser: measured layout, live poll, screenshots
# --------------------------------------------------------------------------
def check_browser(base, lab, pro):
    from playwright.sync_api import sync_playwright
    section('headless Chromium: measured render')
    url = f'{base}{ed.URL_BASE}/{lab.code}'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            ignore_default_args=['--hide-scrollbars'])
        pg = browser.new_page(viewport=dict(width=1280, height=800))

        # The login wall, as a browser sees it.
        pg.goto(url)
        check(pg.url.endswith('/login'),
              'browser lands on oTree /login, not the dashboard')
        pg.fill('input[name=username]', 'admin')
        pg.fill('input[name=password]', 'admin')
        pg.click('button[type=submit], input[type=submit]')
        pg.goto(url)
        check(ed.URL_BASE in pg.url, 'after login the dashboard URL serves')

        # The poll paints without a reload.
        pg.wait_for_selector('tbody tr td.c-label', timeout=15000)
        n_rows = pg.eval_on_selector_all('tbody tr', 'els => els.length')
        check(n_rows == 6, f'poll painted 6 rows (got {n_rows})')
        first_status = pg.text_content('#status')
        pg.wait_for_function(
            'document.getElementById("status").textContent !== ' +
            repr(first_status), timeout=10000)
        check(True, 'status line ticked again within the poll interval')

        # EQUAL SPACING, measured: all 6 header cells and all 6 step cells of
        # the first row within 2px of each other.
        for sel, what in (('.tl-header span', 'header'),
                          ('tbody tr:first-child .stepcell', 'track')):
            widths = pg.eval_on_selector_all(
                sel, 'els => els.map(e => e.getBoundingClientRect().width)')
            check(len(widths) == 6 and max(widths) - min(widths) <= 2,
                  f'six {what} cells, equal spacing '
                  f'(spread {max(widths) - min(widths):.1f}px)')

        # The marker carries the round inside the TASK step.
        markers = pg.eval_on_selector_all(
            '.tl .marker', 'els => els.map(e => e.textContent.trim())')
        check('2 of 3' in markers,
              f'mid-task marker reads "2 of 3" (markers: {markers})')

        # AMBER is visible on pixels, not just a class: the stalled row's
        # first cell background differs from a normal row's.
        bg = pg.eval_on_selector_all(
            'tbody tr', '''els => els.map(e =>
                getComputedStyle(e.querySelector('td')).backgroundColor)''')
        check(len(set(bg)) >= 2, f'stalled row is a visibly different colour '
                                 f'({len(set(bg))} distinct row backgrounds)')

        # Entry-only rows are dimmed, and the toggle hides them.
        dimmed = pg.eval_on_selector_all(
            'tbody tr.entry-only td',
            'els => els.map(e => getComputedStyle(e).opacity)')
        check(dimmed and all(float(o) < 1 for o in dimmed),
              'entry-only row is de-emphasised (opacity < 1)')
        pg.check('#hide-entry')
        pg.wait_for_function(
            f'document.querySelectorAll("tbody tr").length < {n_rows}',
            timeout=10000)
        check(True, 'hide-entry toggle removes entry-only rows')
        pg.uncheck('#hide-entry')

        # No horizontal page scroll at 1280.
        overflow = pg.evaluate(
            'document.documentElement.scrollWidth - window.innerWidth')
        check(overflow <= 0, f'no horizontal page scroll (overflow '
                             f'{overflow}px)')

        # NO TIME OR MONEY EVER TRUNCATES (review, 2026-08-12: a live-timer
        # "…" suffix read as a clipped value; the suffix is gone and the
        # cells are nowrap — so any real clipping now shows as scrollWidth
        # exceeding clientWidth, which this measures).
        clipped = pg.evaluate('''() =>
            [...document.querySelectorAll(
                'td.c-instr, td.c-earn, .stall-note')]
            .filter(e => e.scrollWidth > e.clientWidth + 1).length''')
        check(clipped == 0,
              f'no clipped time/earnings/stall cell at 1280px ({clipped})')

        pg.wait_for_selector('tbody tr td.c-label', timeout=15000)
        pg.screenshot(path=os.path.join(OUT_DIR, 'lab_1280x800.png'),
                      full_page=True)

        # The prolific session: four terminal emojis visible.
        pg.goto(f'{base}{ed.URL_BASE}/{pro.code}')
        pg.wait_for_selector('.terminal-marker', timeout=15000)
        emojis = pg.eval_on_selector_all(
            '.terminal-marker', 'els => els.map(e => e.textContent.trim())')
        check(len(emojis) == 4 and len(set(emojis)) == 4,
              f'four distinct terminal emojis render ({emojis})')
        pg.screenshot(path=os.path.join(OUT_DIR, 'prolific_1280x800.png'),
                      full_page=True)

        # Across-the-room viewport, one more measured spacing pass. The SAME
        # page resized — a browser.new_page() would be a fresh context with
        # no login cookie, and would measure the login page instead.
        pg.set_viewport_size(dict(width=1512, height=1000))
        pg.goto(url)
        pg.wait_for_selector('tbody tr td.c-label', timeout=15000)
        widths = pg.eval_on_selector_all(
            'tbody tr:first-child .stepcell',
            'els => els.map(e => e.getBoundingClientRect().width)')
        check(len(widths) == 6 and max(widths) - min(widths) <= 2,
              f'equal spacing holds at 1512px (spread '
              f'{max(widths) - min(widths):.1f}px)')
        pg.screenshot(path=os.path.join(OUT_DIR, 'lab_1512x1000.png'),
                      full_page=True)
        browser.close()


def main():
    server = Server()
    server.start()
    try:
        lab, pro = stage_sessions(server.base)
        check_http(server.base, lab, pro)
        check_browser(server.base, lab, pro)
    finally:
        server.stop()
    print(f'\nscreenshots: {OUT_DIR}')
    print('FAILED: ' + str(len(_failures)) + ' check(s)' if _failures
          else 'ALL CHECKS PASSED')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
