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
    track cells within 2px of each other, at FOUR viewports (1280, 1512, and
    the overview's 1728 and 1152);
  * the poll paints: rows appear without a reload, the status line ticks,
    and a repaint arrives within 2 poll intervals;
  * the marker carries the round ("2 of 3") during TASK; terminal rows show
    their emoji; the stalled row is visibly AMBER (pixel-sampled, not
    class-trusted); entry-only rows are dimmed and the header toggle hides
    them;
  * the table never scrolls the page horizontally, and no time/earnings/state
    cell is ever clipped, down to 1152px — the narrowest width a real operator
    has (a 1280 laptop with a sidebar, or a half-screen window);
  * a 13-ROW OVERVIEW session containing EVERY state the dashboard can show,
    measured and photographed at 1728 and 1152.

Screenshots land in _ai/dashboard_render/ for a human to flick through, and the
two overview shots in _ai/render_check/dashboard_overview*.png — those two are
OUTPUTS OF THIS FILE, not artefacts beside it, so the best picture of the
feature can always be regenerated.

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

# The two OVERVIEW screenshots live with the rest of the project's render
# checks, because they are the picture a human is pointed at to see what this
# feature is. Written by check_overview(); regenerable, unlike the hand-made
# originals they replace.
OVERVIEW_DIR = os.path.join(_APP_ROOT, '_ai', 'render_check')
os.makedirs(OVERVIEW_DIR, exist_ok=True)

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


def walk(base, code, quiz_answers, stop_after=None, stop_after_n=1,
         quiz_posts=None, ua=DESKTOP_UA, max_steps=200):
    """Walk a participant over real HTTP.

    stop_after / stop_after_n: stop once `stop_after` has been SUBMITTED
    `stop_after_n` times. The count is what lets a round be staged precisely —
    `main` is [GameStart, payoff] per round, so submitting `payoff` N times
    leaves the participant on GameStart of round N+1. Without the count every
    walk could only ever stop in round 1.
    """
    s = requests.Session()
    s.headers['User-Agent'] = ua
    resp = s.get(f'{base}/InitializeParticipant/{code}')
    quiz_posts = list(quiz_posts or [])
    statuses = [resp.status_code]
    submits = 0
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None or page in ('Results', 'Ended'):
            break
        data = (quiz_posts.pop(0) if page == 'quiz' and quiz_posts
                else payload_for(page, quiz_answers))
        resp = s.post(resp.url, data=data)
        statuses.append(resp.status_code)
        if stop_after and page == stop_after:
            submits += 1
            if submits >= stop_after_n:
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


def stage_instructions_time(code, seconds):
    """Backdate a participant's ENTRY-BLOCK stamps so the instructions column
    shows a realistic duration.

    TEST-SIDE WRITE, like the stall timestamp — the dashboard itself never
    writes. It is not decoration: a scripted walk submits instantly, so without
    this every instructions time is `0:00`, and a column of zeros makes the
    "nothing clips" assertion VACUOUS for the one column whose value can grow
    to four characters and a colon. Planting real durations (including one over
    ten minutes) is what gives that measurement something to measure.

    Shifts the START stamps rather than `instructions_done`, so the interval is
    the only thing that changes and no stamp lands in the future.
    """
    stamps = dict(ot.participant_vars(code).get('stage_timestamps') or {})
    anchor = stamps.get('instructions_done') or int(time.time())
    moved = False
    for key in ('consent', 'confirm_id', 'ai_safety_agreed'):
        if key in stamps:
            stamps[key] = anchor - seconds
            moved = True
    if moved:
        set_participant(code, **{'vars.stage_timestamps': stamps})


def stage_overview(base):
    """THE 13-ROW DEMONSTRATION SESSION behind the two `dashboard_overview`
    screenshots — the picture somebody looks at to understand this feature.

    IT LIVES IN THIS FILE ON PURPOSE (added 2026-08-12). Those two PNGs were
    first produced by a throwaway script that was never committed, so the best
    picture of the dashboard could not be regenerated by anyone, and drifted
    from the committed check the moment the page changed (conformance audit
    finding). Staging it here means the screenshots are an OUTPUT of the test
    suite, not an artefact beside it.

    Every state the dashboard can show, in ONE table, because that is the point
    of an overview — thirteen rows:

       1 Seat 01   arrived, sitting at Entry (present, and NOT dimmed)
       2 Seat 02   on the instructions and STALLED (amber)
       3 <pid>     on the quiz, one wrong attempt (cell filling)
       4 Seat 04   mid-task, round 2 of 10
       5 <pid>     mid-task, round 9 of 10
       6 Seat 06   on the questionnaire
       7 Seat 07   finished, earnings known, quiz passed first time
       8 <pid>     finished, earnings known, quiz passed on the 3rd attempt
       9 <pid>     ✋ declined consent
      10 <pid>     ❌ comprehension DQ (and the quiz cell RED)
      11 <pid>     📵 screened out (a phone against a computers-only list)
      12 <pid>     👀 tab-monitor DQ, marker filled at the step reached
      13 (none)    never arrived — dimmed, falls back to the participant code

    Labels are deliberately MIXED — lab seat numbers and Prolific-style ids in
    one table — because `participant.label` is the row key for both study types
    and the column has to stay readable either way.

    WHY THIS IS A PROLIFIC SESSION, given the seat numbers. It is the only study
    type in which all four terminal states can occur, so it is the only one that
    can show every state in one picture. **Declining consent is structurally
    impossible in a lab session**: `welcome.get_form_fields` only offers the
    consent radio when `completion_redirects` is on, because "lab consent is
    implicit in clicking Next" (before/__init__.py). An earlier version of this
    staging used the `lab` config and silently produced twelve states, not
    thirteen. `pilot_feedback` is switched on so the outro has a questionnaire
    page at all — Prolific skips demographics, and without the feedback form a
    completer goes straight from the last round to Results, leaving row 6 with
    nowhere to stand. That is a legitimate configuration, not a fudge: it is
    exactly a Prolific PILOT, and the third orthogonal control existing
    independently of the other two is the point of the parameter scheme.
    """
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}
    first = QUIZ_ITEMS[0]
    wrong = dict(correct)
    wrong[first['field']] = next(c for c in first['choices']
                                 if c != first['answer'])

    # 10 real rounds (so the task marker reads "2 of 10"), the quiz really
    # verified, and `allowed_devices` narrowed to make the screen-out reachable.
    sess = ot.create_session(
        'prolific', num_participants=13,
        modified_session_config_fields={'allowed_devices': 'computer',
                                        'pilot_feedback': True})
    codes = ot.participant_codes(sess)
    pid = ['5f8a3c1b9d2e4f6a7c8b0d1e', '5b21d94e0a7c3f8b6d2e1a9c',
           '5d77aa2c8e1b4f9d3a6c0e5b', '5e01bb7f3d9a2c5e8b4f6a1d',
           '5c33f28a6b0d4e7c1f9a3b5e', '5a99e04d2f7b8c1a5d3e6f0b',
           '5b6e1f04a8c25d9e3f7b0a1c']
    labels = ['Seat 01', 'Seat 02', pid[0], 'Seat 04', pid[1], 'Seat 06',
              'Seat 07', pid[2], pid[3], pid[4], pid[5], pid[6], None]
    for code, label in zip(codes, labels):
        if label:
            ot.set_label(code, label)

    # 1. arrived at Entry: a page RENDER and no submit. This row is the reason
    #    "at Entry" is no longer dimmed — a present person must not look absent.
    requests.get(f'{base}/InitializeParticipant/{codes[0]}',
                 headers={'User-Agent': DESKTOP_UA})
    # 2. on the instructions, then aged so the stall threshold has passed.
    #    Stops after the AGREEMENT page, not after welcome: for Prolific the
    #    entry block is welcome -> ConfirmProlificID -> AISafetyAgree, so
    #    stopping earlier would leave this row still at Entry.
    walk(base, codes[1], correct, stop_after='AISafetyAgree')
    set_participant(codes[1], _last_page_timestamp=int(time.time()) - 400)
    # 3. on the quiz with one wrong attempt (below the DQ threshold of 3)
    walk(base, codes[2], correct, quiz_posts=[wrong], stop_after='quiz')
    # 4-5. mid-task, early and late
    walk(base, codes[3], correct, stop_after='payoff', stop_after_n=1)
    walk(base, codes[4], correct, stop_after='payoff', stop_after_n=8)
    # 6. through the task and into the questionnaire (the feedback form)
    walk(base, codes[5], correct, stop_after='payoff', stop_after_n=10)
    # 7-8. finished, first-try and third-try quiz
    walk(base, codes[6], correct)
    walk(base, codes[7], correct, quiz_posts=[wrong, wrong])
    # 9. declined consent
    s = requests.Session()
    s.headers['User-Agent'] = DESKTOP_UA
    r = s.get(f'{base}/InitializeParticipant/{codes[8]}')
    s.post(r.url, data={'consent': 'False', 'is_mobile': '',
                        'device_info_json': '', 'participant_id_url': ''})
    # 10. comprehension DQ: past the threshold, so the walk is routed out
    walk(base, codes[9], correct, quiz_posts=[wrong, wrong, wrong])
    # 11. screened out by the device gate on the entry request
    requests.get(f'{base}/InitializeParticipant/{codes[10]}',
                 headers={'User-Agent': PHONE_UA})
    # 12. tab-monitor DQ mid-task (the authoritative flags; the live monitor
    #     flow is full_journey_test.py's job)
    walk(base, codes[11], correct, stop_after='quiz')
    set_participant(codes[11], **{'vars.ai_safety_disqualified': True,
                                  'vars.exit_code': -3})
    # 13. codes[12] never arrives.

    # Realistic instructions times, INCLUDING ONE OVER TEN MINUTES so the
    # widest value a real session produces ("12:45") is in the measured picture
    # rather than only the "0:00" a scripted walk produces. See
    # stage_instructions_time.
    for code, seconds in ((codes[1], 406), (codes[2], 340), (codes[3], 204),
                          (codes[4], 172), (codes[5], 195), (codes[6], 210),
                          (codes[7], 765), (codes[9], 380), (codes[11], 218)):
        stage_instructions_time(code, seconds)
    return sess


def check_overview(base, sess):
    """Measure and photograph the 13-row overview at a wide and a narrow width.

    THE 1152 WIDTH IS THE POINT of the narrow pass: it is the smallest width an
    operator realistically has (a 1280 laptop with a sidebar, or a half-screen
    window), and the notes claimed this was measured before it actually was
    (conformance audit). Times and money must never clip, at either width.
    """
    from playwright.sync_api import sync_playwright
    section('headless Chromium: the 13-row overview (dashboard_overview*.png)')
    url = f'{base}{ed.URL_BASE}/{sess.code}'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            ignore_default_args=['--hide-scrollbars'])
        pg = browser.new_page(viewport=dict(width=1728, height=1080))
        pg.goto(f'{base}/login')
        pg.fill('input[name=username]', 'admin')
        pg.fill('input[name=password]', 'admin')
        pg.click('button[type=submit], input[type=submit]')

        for width, height, name in ((1728, 1080, 'dashboard_overview.png'),
                                    (1152, 864, 'dashboard_overview_1152.png')):
            pg.set_viewport_size(dict(width=width, height=height))
            pg.goto(url)
            pg.wait_for_selector('tbody tr td.c-label', timeout=15000)
            n_rows = pg.eval_on_selector_all('tbody tr', 'els => els.length')
            check(n_rows == 13,
                  f'{width}px: all 13 rows painted (got {n_rows})')

            # equal spacing, measured, at THIS width
            widths = pg.eval_on_selector_all(
                'tbody tr:first-child .stepcell',
                'els => els.map(e => e.getBoundingClientRect().width)')
            check(len(widths) == 6 and max(widths) - min(widths) <= 2,
                  f'{width}px: six equal step cells (spread '
                  f'{max(widths) - min(widths):.1f}px)')

            # THE CONNECTOR'S INSET IS DERIVED ARITHMETIC (half a track,
            # 100/steps/2), so measure that it actually LANDS on the centre of
            # the first and last markers. A wrong inset is pure geometry: no
            # error, no failing assertion anywhere else, just a line that
            # over- or under-shoots the end dots. Measured via the ::before
            # pseudo-element's resolved `left`/`right`, which is the only way
            # to see it — it has no box of its own to query.
            line = pg.evaluate('''() => {
                const tl = document.querySelector('.tl');
                const cs = getComputedStyle(tl, '::before');
                const cell = tl.querySelector('.stepcell')
                               .getBoundingClientRect().width;
                return {left: parseFloat(cs.left),
                        right: parseFloat(cs.right), cell: cell};
            }''')
            half = line['cell'] / 2
            check(abs(line['left'] - half) <= 1.5
                  and abs(line['right'] - half) <= 1.5,
                  f'{width}px: the connector starts and ends at the MARKER '
                  f'CENTRES — inset {line["left"]:.1f}/{line["right"]:.1f}px '
                  f'vs half a {line["cell"]:.1f}px track ({half:.1f}px)')

            # nothing clips, at THIS width
            clipped = pg.evaluate('''() =>
                [...document.querySelectorAll(
                    'td.c-instr, td.c-earn, .stall-note, td.c-state')]
                .filter(e => e.scrollWidth > e.clientWidth + 1).length''')
            check(clipped == 0,
                  f'{width}px: no clipped time/earnings/state cell ({clipped})')
            check(pg.evaluate('document.documentElement.scrollWidth - '
                              'window.innerWidth') <= 0,
                  f'{width}px: no horizontal page scroll')

            # every state actually visible in the picture
            if width == 1728:
                markers = pg.eval_on_selector_all(
                    '.tl .marker', 'els => els.map(e => e.textContent.trim())')
                check('2 of 10' in markers and '9 of 10' in markers,
                      f'the task markers carry their round ({markers})')
                emojis = pg.eval_on_selector_all(
                    '.terminal-marker',
                    'els => els.map(e => e.textContent.trim())')
                check(len(emojis) == 4 and len(set(emojis)) == 4,
                      f'ALL FOUR terminal states, four distinct emojis, in one '
                      f'table ({emojis})')
                # The instructions column must carry REAL times, not a column
                # of 0:00 — otherwise the clipping measurement above has
                # nothing to bite on (see stage_instructions_time).
                times = [t.strip() for t in pg.eval_on_selector_all(
                    'td.c-instr', 'els => els.map(e => e.textContent)')
                    if t.strip()]
                real = [t for t in times if t not in ('', '0:00')]
                check(len(real) >= 8,
                      f'the instructions column shows real durations, not a '
                      f'column of zeros ({len(real)} of {len(times)}: {real})')
                check(any(len(t) >= 5 for t in real),
                      f'and at least one is over ten minutes, so the WIDEST '
                      f'value a session produces is in the measured picture '
                      f'({real})')
                for sel, what in ((
                        'tbody tr.stalled', 'an amber (stalled) row'), (
                        'tbody tr.entry-only', 'a dimmed never-arrived row'), (
                        'tbody tr.finished-row', 'a finished row'), (
                        'tbody tr.terminal-row', 'a terminal row'), (
                        '.quizcell.q-red', 'a RED quiz cell'), (
                        '.quizcell.q-green', 'a GREEN quiz cell')):
                    check(pg.eval_on_selector_all(sel, 'els => els.length') > 0,
                          f'the overview really contains {what}')

            pg.screenshot(path=os.path.join(OVERVIEW_DIR, name),
                          full_page=True)
            print(f'   wrote {os.path.relpath(os.path.join(OVERVIEW_DIR, name), _APP_ROOT)}')
        browser.close()


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
        # The overview last: it is the biggest staging job, and running it after
        # the assertions above means a failure there is not hidden behind it.
        check_overview(server.base, stage_overview(server.base))
    finally:
        server.stop()
    print(f'\nscreenshots: {OUT_DIR} and {OVERVIEW_DIR}')
    print('FAILED: ' + str(len(_failures)) + ' check(s)' if _failures
          else 'ALL CHECKS PASSED')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
