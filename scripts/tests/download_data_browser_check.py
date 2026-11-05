#!/usr/bin/env python3
"""THE "DOWNLOAD DATA" BUTTON END TO END: a real `otree prodserver` and real Chromium.

download_data_test.py proves the rules against the routes. This proves what a
person sees and gets: press the button in a real browser against a real production
server, then read the real files on disk or the real downloads.

Measured and read back, not looked at:
  * the button is at the top right; the confirm step shows every path; the main
    action is visible without scrolling at 1280x720;
  * folder set: three files in the right subfolders with the right names, columns
    and values, for a lab session (217b), a value with a space, and no number;
  * a second press and a double click: a suffix, nothing overwritten;
  * missing base folder, a subfolder name taken by a file, an unwritable folder;
  * browser mode: three real downloads from one press, with the right names and
    bytes; the visible links work; the words claim only "sent to the browser";
  * from inside the admin Report tab's iframe too;
  * not logged in, and no CSRF token: refused over real HTTP and on screen;
  * a study with Prolific participants and a lab one with bank details, in one
    database;
  * a real participant walking through the study during exports, with its page
    times, and timing at a realistic row count;
  * a study NOT built from this template, on its own settings and app: no anonymous
    file, payments with the participant code alone, said before and after writing.

THE SERVER RUNS ON A THROWAWAY COPY of the project in a temp folder (this file makes
it), so no run can touch the project's db.sqlite3. It always starts production mode
with OTREE_AUTH_LEVEL=STUDY.

Run (the browser needs Playwright; the server needs only oTree):
    python scripts/tests/download_data_browser_check.py
Optional environment:
    DOWNLOAD_CHECK_OTREE   the `otree` executable to serve with, to prove the
                           button on an install without pandas
    DOWNLOAD_CHECK_SHOTS   where screenshots go (default _ai/download_button/)
    DOWNLOAD_CHECK_ROWS    participants in the timing session (default 300)
    DOWNLOAD_CHECK_HEADED  1: the full browser rather than the headless shell
"""
import csv
import datetime
import io
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402

import requests  # noqa: E402

sys.path.insert(0, REPO_ROOT)
import data_columns  # noqa: E402
from main_contract import task_page_submits  # noqa: E402
from quiz_answers import CORRECT  # noqa: E402
import bot_walker  # noqa: E402

PASSWORD = 'check-pass'
REST_KEY = 'check-rest-key'
TODAY = datetime.date.today().strftime('%d-%m-%Y')
PROLIFIC_ID = '5f3c9d2e1a7b4c6d8e9f0a1b'
IBAN = 'NL91ABNA0417164300'
DE_IBAN = 'DE89370400440532013000'
BIC = 'COBADEFFXXX'
DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
SHOTS = os.environ.get('DOWNLOAD_CHECK_SHOTS') or os.path.join(
    REPO_ROOT, '_ai', 'download_button')
TIMING_ROWS = int(os.environ.get('DOWNLOAD_CHECK_ROWS') or 300)
os.makedirs(SHOTS, exist_ok=True)

_failures = []


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}", flush=True)
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===', flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    """A real prodserver on a throwaway copy. The folder setting is an environment
    variable the server reads, so changing it means a restart on the same copy."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='download_check_')
        self.app = os.path.join(self.tmp, 'app')
        shutil.copytree(REPO_ROOT, self.app, ignore=shutil.ignore_patterns(
            '.git', '_ai', 'previews', '__pycache__', 'db.sqlite3*'))
        self.otree = os.environ.get('DOWNLOAD_CHECK_OTREE') or os.path.join(
            os.path.dirname(sys.executable), 'otree')
        self.log_path = os.path.join(self.tmp, 'server.log')
        self.proc = None
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'

    def env(self, folder):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('OTREE_') and k != 'DATABASE_URL'}
        env.update(OTREE_PRODUCTION='1', OTREE_AUTH_LEVEL='STUDY',
                   OTREE_ADMIN_PASSWORD=PASSWORD, OTREE_REST_KEY=REST_KEY,
                   OTREE_SECRET_KEY='check-secret',
                   PATH=os.path.dirname(self.otree) + os.pathsep + os.environ['PATH'])
        if folder is not None:
            env['OTREE_DATA_FOLDER'] = folder
        return env

    def resetdb(self):
        subprocess.run([self.otree, 'resetdb', '--noinput'], cwd=self.app,
                       env=self.env(None), check=True, capture_output=True)

    def start(self, folder=None):
        self.stop()
        log = open(self.log_path, 'ab')
        self.proc = subprocess.Popen(
            [self.otree, 'prodserver', f'127.0.0.1:{self.port}'], cwd=self.app,
            env=self.env(folder), stdout=log, stderr=log, start_new_session=True)
        for _ in range(400):
            try:
                if requests.get(self.base + '/login', timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(f'server died; see {self.log_path}')
            time.sleep(0.25)
        raise RuntimeError('the server did not answer')

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(5)
        self.proc = None

    def destroy(self):
        self.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def log(self):
        with open(self.log_path, errors='replace') as fh:
            return fh.read()


def api_session(server, config, n, **fields):
    r = requests.post(server.base + '/api/sessions', json={
        'session_config_name': config, 'num_participants': n,
        'modified_session_config_fields': fields},
        headers={'otree-rest-key': REST_KEY}, timeout=300)
    r.raise_for_status()
    return r.json()['code']


def participant_codes(server, session_code):
    r = requests.get(f'{server.base}/api/sessions/{session_code}',
                     headers={'otree-rest-key': REST_KEY}, timeout=60)
    r.raise_for_status()
    return [p['code'] for p in r.json()['participants']]


def walk(server, code, label='', iban=IBAN, bic='', stop_on=None, timings=None):
    """One participant through the real pages over real HTTP. Returns the last
    page name. `timings` collects each request's seconds, for the load check."""
    s = requests.Session()
    s.headers['User-Agent'] = DESKTOP_UA
    url = f'{server.base}/InitializeParticipant/{code}'
    if label:
        url += f'?participant_label={label}'

    def timed(call, *args, **kwargs):
        started = time.time()
        resp = call(*args, timeout=120, **kwargs)
        if timings is not None:
            timings.append(time.time() - started)
        assert resp.status_code < 500, (resp.status_code, resp.url)
        return resp
    resp = timed(s.get, url)
    for _ in range(300):
        match = re.search(r'/p/[^/]+/[^/]+/([^/]+)/\d+', resp.url)
        if not match:
            return None
        page = match.group(1)
        if page in ('Results', 'Ended') or page == stop_on:
            return page
        data = {
            'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                        'participant_id_url': label},
            'ConfirmProlificID': {'participant_id_external': label},
            'quiz': dict(CORRECT),
            'Demographics': {'age': '30', 'gender': 'Female', 'bank': iban,
                             'bank_confirmation': iban, 'bic': bic},
            'Feedback': {'feedback': ''},
            **task_page_submits(),
        }.get(page, {})
        if page == 'DotBiGate':
            data = bot_walker.dotbi_payload(code)
        token = re.search(r'name="csrftoken" value="([^"]+)"', resp.text)
        if token:
            data = dict(data, csrftoken=token.group(1))
        resp = timed(s.post, resp.url, data=data)
    return None


def http_admin(server):
    s = requests.Session()
    token = re.search(r'name="csrftoken" value="([^"]+)"',
                      s.get(server.base + '/login').text).group(1)
    r = s.post(server.base + '/login', allow_redirects=False, data={
        'username': 'admin', 'password': PASSWORD, 'csrftoken': token})
    assert r.status_code in (302, 303), r.status_code
    return s


def read_csv_bytes(data):
    table = list(csv.reader(io.StringIO(data.decode('utf-8'), newline='')))
    return table[0], [dict(zip(table[0], row)) for row in table[1:]]


def tree(folder):
    found = []
    for root, _dirs, names in os.walk(folder):
        found += [os.path.relpath(os.path.join(root, n), folder) for n in names]
    return sorted(found)


class Screen:
    """One logged-in browser context on the dashboard."""

    def __init__(self, browser, server, code, width=1280, height=720):
        self.server, self.code = server, code
        self.context = browser.new_context(viewport={'width': width, 'height': height},
                                            accept_downloads=True)
        self.page = self.context.new_page()
        self.downloads = []
        self.page.on('download', lambda d: self.downloads.append(d))
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.goto(server.base + '/login')
        self.page.fill('input[name=username]', 'admin')
        self.page.fill('input[name=password]', PASSWORD)
        self.page.click('button[type=submit], input[type=submit]')
        self.open()

    def open(self):
        self.page.goto(f'{self.server.base}/experimenter_dashboard/{self.code}')
        self.page.wait_for_selector('#dl-open')

    def panel_text(self):
        return ' '.join(self.page.inner_text('#dl-overlay').split())

    def press(self):
        self.page.click('#dl-open')
        self.page.wait_for_selector('#dl-overlay .qm-panel h2')
        self.page.wait_for_function(
            "!document.getElementById('dl-overlay').textContent.includes('Checking')")

    def confirm(self):
        self.page.click('#dl-confirm')
        self.page.wait_for_selector('#dl-cancel', timeout=120000)

    def close(self):
        self.context.close()

    def shot(self, name):
        self.page.screenshot(path=os.path.join(SHOTS, f'{name}.png'))


def check_files(server, folder, stem, want_rows):
    """The three files on disk, against the server's own /ExportWide now."""
    wide = http_admin(server).get(server.base + '/ExportWide').content
    wide_head, wide_rows = read_csv_bytes(wide)
    paths = {
        'SENSITIVE': os.path.join(folder, 'SENSITIVE', f'{stem}_SENSITIVE.csv'),
        'ANONYMOUS': os.path.join(folder, 'ANONYMOUS', f'{stem}.csv'),
        'PAYMENTS': os.path.join(folder, 'PAYMENTS', f'{stem}_PAYMENTS.csv'),
    }
    for path in paths.values():
        check(os.path.isfile(path), f'on disk: {path.replace(folder, "<folder>")}')
    data = {kind: open(path, 'rb').read() for kind, path in paths.items()}
    check(data['SENSITIVE'] == wide, 'SENSITIVE is byte for byte /ExportWide')
    head, rows = read_csv_bytes(data['ANONYMOUS'])
    check(head == [c for c in wide_head if c not in data_columns.ANON_DROP_COLUMNS],
          'ANONYMOUS has every column but the drop list')
    check(len(rows) == want_rows == len(wide_rows), f'ANONYMOUS has {want_rows} rows')
    check(all(a[c] == w[c] for a, w in zip(rows, wide_rows) for c in head
              if c not in data_columns.ANON_BLANK_COLUMNS),
          'ANONYMOUS values match the wide export')
    head, pay = read_csv_bytes(data['PAYMENTS'])
    check(head == list(data_columns.PAYMENT_COLUMNS),
          f'PAYMENTS has exactly the five columns: {", ".join(head)}')
    check(len(pay) == want_rows and all(p[c] == w[c] for p, w in zip(pay, wide_rows)
                                        for c in head),
          'PAYMENTS values match the wide export')
    return data, wide_rows


def scenario_folder(browser, server, folder, lab, prolific):
    section('folder set: a lab session 217b, with bank details and Prolific rows')
    screen = Screen(browser, server, lab)
    page = screen.page
    box = page.locator('#dl-open').bounding_box()
    top = page.locator('.dash-top').bounding_box()
    check(box['x'] + box['width'] <= top['x'] + top['width'] + 1
          and top['x'] + top['width'] - (box['x'] + box['width']) < 4,
          f'the button sits at the right edge of the header row '
          f'({top["x"] + top["width"] - box["x"] - box["width"]:.1f}px away)')
    check(box['y'] < 80, f'and at the top of the page (y={box["y"]:.0f})')
    screen.shot('01_dashboard_button')

    screen.press()
    text = screen.panel_text()
    for kind, name in (('SENSITIVE', f'EXP_217b_{TODAY}_SENSITIVE.csv'),
                       ('ANONYMOUS', f'EXP_217b_{TODAY}.csv'),
                       ('PAYMENTS', f'EXP_217b_{TODAY}_PAYMENTS.csv')):
        path = os.path.join(folder, kind, name)
        check(path in text, f'the confirm step shows {path.replace(folder, "<folder>")}')
    check(folder in text, 'and names the folder')
    check('All sessions' in text and 'not only the session on this screen' in text,
          'and says it covers all sessions')
    check(tree(folder) == [], 'nothing is written by opening the confirm step')
    confirm = page.locator('#dl-confirm').bounding_box()
    other = page.locator('#dl-cancel').bounding_box()
    check(confirm['y'] + confirm['height'] <= 720,
          f'the main action is on screen at 1280x720 (bottom {confirm["y"] + confirm["height"]:.0f})')
    check(confirm['height'] > other['height'] and confirm['width'] > other['width'],
          'and bigger than Cancel')
    check('—' not in text, 'no em dash in the words')
    screen.shot('02_confirm_folder')

    page.click('#dl-cancel')
    check(not page.locator('#dl-overlay.open').count(), 'Cancel closes it')
    check(tree(folder) == [], 'and writes nothing')

    screen.press()
    screen.confirm()
    text = screen.panel_text()
    check('All 3 files were written' in text, f'the result says so ({text[:60]}...)')
    stem = f'EXP_217b_{TODAY}'
    data, wide_rows = check_files(server, folder, stem, 5)
    for kind, name in (('SENSITIVE', f'{stem}_SENSITIVE.csv'), ('ANONYMOUS', f'{stem}.csv'),
                       ('PAYMENTS', f'{stem}_PAYMENTS.csv')):
        check(os.path.join(folder, kind, name) in text, f'the result lists the full {kind} path')
    check('5 rows' in text, 'and the row count')
    screen.shot('03_result_folder')

    section('the data: a Prolific study and a lab one with bank details, two sessions')
    check({r['session.code'] for r in wide_rows} == {lab, prolific},
          'the database holds two sessions and the file covers both')
    head, pay = read_csv_bytes(data['PAYMENTS'])
    by_id = {r['participant.participant_id_external']: r for r in pay}
    check(by_id[PROLIFIC_ID]['outro.1.player.bank'] == '' and
          by_id[PROLIFIC_ID]['outro.1.player.earned'] != '',
          'a Prolific finisher: an ID, no IBAN, a total')
    bank = {r['outro.1.player.bank']: r for r in pay}
    check(bank[IBAN]['participant.participant_id_external'] == '' and
          bank[IBAN]['outro.1.player.earned'] != '',
          'a lab finisher: an IBAN, no ID, a total')
    check(bank[DE_IBAN]['outro.1.player.bic'] == BIC, 'a German IBAN has its BIC')
    anonymous = data['ANONYMOUS'].decode('utf-8')
    for secret in (IBAN, DE_IBAN, BIC, PROLIFIC_ID):
        check(secret not in anonymous and secret in data['SENSITIVE'].decode('utf-8'),
              f'{secret}: in SENSITIVE, nowhere in ANONYMOUS')

    section('a second press: a suffix, nothing overwritten')
    first = {p: open(os.path.join(folder, p), 'rb').read() for p in tree(folder)}
    page.click('#dl-cancel')
    screen.press()
    text = screen.panel_text()
    check(f'EXP_217b_{TODAY}_SENSITIVE_2.csv' in text, 'the confirm step shows _2 already')
    screen.shot('04_confirm_second_press')
    screen.confirm()
    check('All 3 files were written' in screen.panel_text(), 'all three written')
    check(len(tree(folder)) == 6, f'six files now ({len(tree(folder))})')
    for name in (f'SENSITIVE/{stem}_SENSITIVE_2.csv', f'ANONYMOUS/{stem}_2.csv',
                 f'PAYMENTS/{stem}_PAYMENTS_2.csv'):
        check(os.path.isfile(os.path.join(folder, name)), f'{name.split("/")[1]} exists')
    check(all(open(os.path.join(folder, p), 'rb').read() == b for p, b in first.items()),
          'the first set is byte for byte unchanged')
    screen.shot('05_result_second_press')

    section('a double click on the confirm button')
    page.click('#dl-cancel')
    screen.press()
    page.dblclick('#dl-confirm')
    page.wait_for_selector('#dl-cancel', timeout=120000)
    time.sleep(0.5)
    check(len(tree(folder)) == 9, f'one press happened: nine files ({len(tree(folder))})')

    section('two tabs pressing at the same moment')
    page.click('#dl-cancel')
    second = screen.context.new_page()
    second.goto(page.url)
    second.wait_for_selector('#dl-open')
    for each in (page, second):
        each.click('#dl-open')
        each.wait_for_selector('#dl-confirm')
    # Fired from one script tick in each tab, as close together as a person can't.
    page.evaluate("setTimeout(() => document.getElementById('dl-confirm').click(), 200)")
    second.evaluate("setTimeout(() => document.getElementById('dl-confirm').click(), 200)")
    page.wait_for_selector('.dl-verdict', timeout=120000)
    second.wait_for_selector('.dl-verdict', timeout=120000)
    both = screen.panel_text() + ' ' + ' '.join(second.inner_text('#dl-overlay').split())
    check(both.count('All 3 files were written') == 2, 'both tabs report success')
    names = tree(folder)
    check(len(names) == 15, f'fifteen files, so nothing was shared or lost ({len(names)})')
    for number in ('_4', '_5'):
        check(sum(n.endswith(f'{number}.csv') for n in names) == 3,
              f'set {number} has all three')
    check(not any(n.endswith('.tmp') or '.export-' in n for n in names), 'no temp left')
    second.close()
    screen.close()

    section('a lab session with a space in it, and no lab session')
    # Made only now, because the row counts above are asserted exactly.
    spaced = api_session(server, 'lab', 1, lab_session='217 b')
    screen = Screen(browser, server, spaced)
    screen.press()
    screen.confirm()
    check(f'EXP_217-b_{TODAY}_SENSITIVE.csv' in screen.panel_text(),
          f'"217 b" keeps its meaning: EXP_217-b_{TODAY}_SENSITIVE.csv')
    screen.close()
    screen = Screen(browser, server, prolific)
    screen.press()
    screen.confirm()
    text = screen.panel_text()
    stem = f'EXP_{TODAY}'
    for kind, name in (('SENSITIVE', f'{stem}_SENSITIVE.csv'), ('ANONYMOUS', f'{stem}.csv'),
                       ('PAYMENTS', f'{stem}_PAYMENTS.csv')):
        check(os.path.join(folder, kind, name) in text
              and os.path.isfile(os.path.join(folder, kind, name)),
              f'no lab session: {name}')
    check(not screen.errors, f'no script errors on the page ({screen.errors})')
    screen.close()


def scenario_broken_folders(browser, server, folder, lab):
    section('a subfolder name taken by a file')
    screen = Screen(browser, server, lab)
    shutil.rmtree(os.path.join(folder, 'PAYMENTS'))
    with open(os.path.join(folder, 'PAYMENTS'), 'w') as fh:
        fh.write('in the way')
    screen.press()
    text = screen.panel_text()
    check('A file called PAYMENTS is in the way' in text, 'the confirm step warns')
    screen.shot('06_confirm_subfolder_taken')
    screen.confirm()
    text = screen.panel_text()
    check('Only 2 of the 3 files were written' in text, f'the result says so ({text[:70]})')
    check('not written' in text and 'a file is in the way of that folder' in text,
          'and says which and why')
    check(open(os.path.join(folder, 'PAYMENTS')).read() == 'in the way',
          'the file in the way is untouched')
    screen.shot('07_result_subfolder_taken')
    page_red = screen.page.locator('.dl-verdict.bad').count()
    check(page_red == 1, 'the verdict uses the failure style')
    os.remove(os.path.join(folder, 'PAYMENTS'))
    screen.page.click('#dl-cancel')

    section('an unwritable folder')
    if os.geteuid() == 0:
        print('  [SKIP] running as root: permissions do not apply')
    else:
        locked = os.path.join(folder, 'ANONYMOUS')
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        before = tree(folder)
        screen.press()
        screen.confirm()
        text = screen.panel_text()
        os.chmod(locked, stat.S_IRWXU)
        check('Only 2 of the 3 files were written' in text
              and 'no permission to write there' in text,
              f'says which file and why ({text[:90]})')
        after = tree(folder)
        check(len(after) == len(before) + 2, 'and exactly two new files are on disk')
        screen.shot('08_result_unwritable')
        screen.page.click('#dl-cancel')

        subfolders = [os.path.join(folder, kind) for kind in ('SENSITIVE', 'ANONYMOUS', 'PAYMENTS')]
        for sub in subfolders:
            os.chmod(sub, stat.S_IRUSR | stat.S_IXUSR)
        before = tree(folder)
        screen.press()
        screen.confirm()
        text = screen.panel_text()
        for sub in subfolders:
            os.chmod(sub, stat.S_IRWXU)
        check('No files were written' in text and text.count('no permission to write there') == 3,
              f'nothing can be written: the screen says so, file by file ({text[:60]})')
        check(tree(folder) == before, 'and the disk agrees')
        screen.shot('08b_result_nothing_written')
    screen.close()


def scenario_missing_base(browser, server, missing, lab):
    section('a missing base folder')
    screen = Screen(browser, server, lab)
    screen.press()
    text = screen.panel_text()
    check(missing in text and 'does not exist' in text, 'the error names the folder')
    check(screen.page.locator('#dl-confirm').count() == 0, 'there is nothing to confirm')
    check(not os.path.exists(missing), 'and nothing was created')
    screen.shot('09_missing_base_folder')
    admin = http_admin(server)
    plan = admin.get(f'{server.base}/experimenter_dashboard/{lab}/download_plan').json()
    answer = admin.post(f'{server.base}/experimenter_dashboard/{lab}/download',
                        data={'csrftoken': plan.get('csrf', '')})
    check(answer.status_code in (200, 403) and not os.path.exists(missing),
          'a direct POST creates nothing either')
    screen.close()


def scenario_walls(browser, server, folder, lab):
    section('not logged in; no CSRF token (real HTTP, real server)')
    stranger = requests.Session()
    url = f'{server.base}/experimenter_dashboard/{lab}'
    r = stranger.get(url + '/download_plan', allow_redirects=False)
    check(r.status_code == 403 and 'csrf' not in r.text, f'plan without login: {r.status_code}')
    r = stranger.post(url + '/download', data={'csrftoken': 'x'}, allow_redirects=False)
    check(r.status_code == 403, f'POST without login: {r.status_code}')
    r = stranger.get(url, allow_redirects=False)
    check(r.status_code == 302 and '/login' in r.headers.get('location', ''),
          'the dashboard page itself redirects to the login (AUTH_LEVEL=STUDY)')
    before = tree(folder)
    admin = http_admin(server)
    r = admin.post(url + '/download', data={}, allow_redirects=False)
    check(r.status_code == 403 and r.json()['problem'] == 'csrf', f'no token: {r.status_code}')
    r = admin.post(url + '/download', data={'csrftoken': 'wrong'}, allow_redirects=False)
    check(r.status_code == 403 and r.json()['problem'] == 'csrf', f'wrong token: {r.status_code}')
    check(tree(folder) == before, 'nothing was written by any of them')

    section('routes gone, a server error, no answer: the button says so')
    screen = Screen(browser, server, lab)
    screen.page.route('**/download_plan', lambda route: route.fulfill(
        status=404, content_type='text/html', body='<h1>Not found</h1>'))
    screen.page.click('#dl-open')
    screen.page.wait_for_selector('#dl-overlay .qm-err')
    text = screen.panel_text()
    check('not available' in text and 'server log' in text, f'a 404 page: {text[:60]}')
    screen.shot('14_not_available')
    screen.page.click('#dl-cancel')
    screen.page.unroute('**/download_plan')
    screen.page.route('**/download', lambda route: route.fulfill(
        status=500, content_type='text/html', body='<h1>Server error</h1>'))
    screen.press()
    screen.page.click('#dl-confirm')
    screen.page.wait_for_selector('#dl-overlay .qm-err')
    text = screen.panel_text()
    check('may or may not have written' in text, f'a 500 page: {text[:60]}')
    screen.page.click('#dl-cancel')
    screen.page.unroute('**/download')
    screen.page.route('**/download', lambda route: route.abort())
    screen.press()
    screen.page.click('#dl-confirm')
    screen.page.wait_for_selector('#dl-overlay .qm-err')
    text = screen.panel_text()
    check('did not answer' in text and 'check' in text, f'no answer at all: {text[:60]}')
    screen.close()

    section('logged out while the page is open: the button says so')
    screen = Screen(browser, server, lab)
    screen.context.clear_cookies()
    screen.page.click('#dl-open')
    screen.page.wait_for_selector('#dl-overlay a')
    text = screen.panel_text()
    check('Log in first' in text and 'oTree login page' in text, f'on screen: {text[:70]}')
    check(screen.page.get_attribute('#dl-overlay a', 'href') == '/login', 'with a login link')
    screen.shot('10_not_logged_in')
    screen.close()


def get_downloads(screen, want, timeout=25):
    deadline = time.time() + timeout
    while len(screen.downloads) < want and time.time() < deadline:
        screen.page.wait_for_timeout(200)
    screen.page.wait_for_timeout(1200)
    return screen.downloads


def scenario_browser_mode(browser, server, lab):
    section('browser mode: three real downloads from one press')
    tmp_before = set(os.listdir(tempfile.gettempdir()))
    screen = Screen(browser, server, lab)
    screen.press()
    text = screen.panel_text()
    check('allow multiple downloads' in text, 'the confirm step warns about the browser prompt')
    check(f'EXP_217b_{TODAY}.csv' in text, 'and lists the names')
    check('/SENSITIVE' not in text, 'and no server path')
    screen.shot('11_confirm_browser')
    screen.confirm()
    downloads = get_downloads(screen, 3)
    want = {f'EXP_217b_{TODAY}_SENSITIVE.csv', f'EXP_217b_{TODAY}.csv',
            f'EXP_217b_{TODAY}_PAYMENTS.csv'}
    check(len(downloads) == 3, f'exactly three downloads ({len(downloads)})')
    got = {d.suggested_filename: d for d in downloads}
    check(set(got) == want, f'with the right names ({sorted(got)})')
    saved = {}
    for name, download in got.items():
        path = os.path.join(server.tmp, 'dl_' + name)
        download.save_as(path)
        saved[name] = open(path, 'rb').read()
    wide = http_admin(server).get(server.base + '/ExportWide').content
    check(saved.get(f'EXP_217b_{TODAY}_SENSITIVE.csv') == wide,
          'the SENSITIVE download is byte for byte /ExportWide')
    head, rows = read_csv_bytes(saved[f'EXP_217b_{TODAY}_PAYMENTS.csv'])
    check(head == list(data_columns.PAYMENT_COLUMNS) and rows, 'the PAYMENTS download has its five columns')
    check(IBAN.encode() in saved[f'EXP_217b_{TODAY}_PAYMENTS.csv']
          and IBAN.encode() not in saved[f'EXP_217b_{TODAY}.csv'],
          'the IBAN is in PAYMENTS and not in ANONYMOUS')
    text = screen.panel_text()
    check('3 files sent to the browser' in text, f'the screen says "sent to the browser" ({text[:50]})')
    check('written' not in text and 'saved' not in text and 'arrived.' not in text.replace('whether they arrived', ''),
          'and claims nothing about them having arrived')
    check('cannot see whether they arrived' in text, 'and says the server cannot see that')
    links = screen.page.locator('#dl-overlay a[download]')
    check(links.count() == 3, 'three visible links as a fallback')
    screen.shot('12_result_browser')

    section('the fallback: a blocked download is one click away')
    with screen.page.expect_download() as caught:
        screen.page.click('#dl-overlay a[data-kind=PAYMENTS]')
    path = os.path.join(server.tmp, 'fallback.csv')
    caught.value.save_as(path)
    check(caught.value.suggested_filename == f'EXP_217b_{TODAY}_PAYMENTS.csv'
          and open(path, 'rb').read() == saved[f'EXP_217b_{TODAY}_PAYMENTS.csv'],
          'clicking the link gives the same file again')

    section('the server stores no copy in this mode')
    screen.close()
    found = []
    for root, _dirs, names in os.walk(server.app):
        for name in names:
            if name.startswith('EXP_') or name.endswith('.tmp') or name == 'SENSITIVE':
                found.append(os.path.join(root, name))
    check(found == [], f'no file named like an export in the project copy ({found})')
    new_tmp = [n for n in set(os.listdir(tempfile.gettempdir())) - tmp_before
               if n.startswith(('.export-', 'EXP_'))]
    check(new_tmp == [], f'nor in the temp folder ({new_tmp})')
    # The participant's own entry URL carries the Prolific ID in the access log, as
    # it does on any oTree server; what must be absent is anything the export said.
    log = [line for line in server.log().splitlines()
           if '/InitializeParticipant/' not in line]
    check(not any(IBAN in line or DE_IBAN in line or PROLIFIC_ID in line for line in log),
          f'and no IBAN or ID anywhere in the server log but the entry URL ({len(log)} lines)')

    section('from inside the admin Report tab (an iframe)')
    screen = Screen(browser, server, lab)
    screen.page.goto(f'{server.base}/AdminReport/{lab}')
    frame = screen.page.frame_locator('iframe[title="Experimenter dashboard"]')
    frame.locator('#dl-open').click()
    frame.locator('#dl-confirm').wait_for()
    screen.page.wait_for_timeout(300)
    bottom = frame.locator('#dl-confirm').bounding_box()
    check(bottom['y'] + bottom['height'] <= 720,
          f'the main action is on screen at 1280x720 inside the iframe '
          f'(bottom {bottom["y"] + bottom["height"]:.0f})')
    screen.shot('13_confirm_in_report_tab')
    frame.locator('#dl-confirm').click()
    frame.locator('.dl-verdict').wait_for(timeout=120000)
    downloads = get_downloads(screen, 3)
    check({d.suggested_filename for d in downloads} == want,
          f'all three arrive from inside the iframe ({len(downloads)})')
    screen.close()


def scenario_running_session(browser, server, folder, lab_big):
    section(f'a real participant running during exports, {TIMING_ROWS} rows in the database')
    codes = participant_codes(server, lab_big)
    baseline = []
    check(walk(server, codes[0], timings=baseline) == 'Results',
          f'a control participant finishes with no export running ({len(baseline)} requests)')

    during, outcome = [], {}
    done = threading.Event()

    def participant():
        outcome['page'] = walk(server, codes[1], iban=DE_IBAN, bic=BIC, timings=during)
        done.set()
    thread = threading.Thread(target=participant)

    admin = http_admin(server)
    url = f'{server.base}/experimenter_dashboard/{lab_big}'
    token = admin.get(url + '/download_plan').json()['csrf']
    thread.start()
    export_times = []
    answers = []
    while not done.is_set():
        started = time.time()
        answers.append(admin.post(url + '/download', data={'csrftoken': token}).json())
        export_times.append(time.time() - started)
        time.sleep(0.2)
    thread.join()
    baseline.sort()
    during.sort()
    p50 = lambda xs: xs[len(xs) // 2]
    p95 = lambda xs: xs[int(len(xs) * .95)]
    print(f'    participant page, no export: median {p50(baseline)*1000:.0f} ms, '
          f'p95 {p95(baseline)*1000:.0f} ms, worst {baseline[-1]*1000:.0f} ms, n={len(baseline)}')
    print(f'    participant page, exporting: median {p50(during)*1000:.0f} ms, '
          f'p95 {p95(during)*1000:.0f} ms, worst {during[-1]*1000:.0f} ms, n={len(during)}')
    print(f'    one export of {answers[0]["files"][0]["rows"]} rows, end to end: median '
          f'{sorted(export_times)[len(export_times)//2]*1000:.0f} ms, '
          f'worst {max(export_times)*1000:.0f} ms, n={len(export_times)}')
    check(outcome.get('page') == 'Results', 'the participant finished normally during the exports')
    check(len(answers) >= 2, f'and exports really ran during it ({len(answers)})')
    check(all(a.get('ok') for a in answers), 'every export succeeded')
    check(all(a['files'][0]['rows'] == a['files'][2]['rows'] for a in answers),
          'each set agrees with itself on the row count')
    wide = http_admin(server).get(server.base + '/ExportWide').content
    _head, rows = read_csv_bytes(wide)
    row = [r for r in rows if r['participant.code'] == codes[1]][0]
    check(row['outro.1.player.bank'] == DE_IBAN and row['participant.exit_code'] == '1'
          and row['outro.1.player.earned'] != '',
          'and their answers, exit code and total are in the database')
    check(during[-1] < 15, f'no participant page waited more than 15 s ({during[-1]:.1f})')


PLAIN_SETTINGS = """
from os import environ
SESSION_CONFIGS = [dict(name='plain', display_name='Plain study', app_sequence=['plain'],
                        num_demo_participants=2)]
SESSION_CONFIG_DEFAULTS = dict(real_world_currency_per_point=1.00, participation_fee=0.00)
PARTICIPANT_FIELDS = []
SESSION_FIELDS = []
LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')
SECRET_KEY = 'plain'
ROOMS = []
EXIT_CODES = dict(finished=1, abandoned=0)  # the dashboard's own helper module reads it
"""

PLAIN_APP = """
from otree.api import *

class C(BaseConstants):
    NAME_IN_URL = 'plain'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

class Subsession(BaseSubsession):
    pass

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    answer = models.StringField(blank=True)

class Ask(Page):
    form_model = 'player'
    form_fields = ['answer']

class Done(Page):
    pass

page_sequence = [Ask, Done]

import data_download
import experimenter_dashboard
experimenter_dashboard.install_dashboard_route_or_note()
data_download.install_download_route_or_note()
"""


def scenario_plain_study(browser):
    """A study NOT built from this template: its own settings and one app, carrying
    only the root modules the button needs. No IBAN, BIC, Prolific or earned column
    exists, and an export with those columns cannot be faked here: it is oTree's."""
    section('a study not built from this template: no anonymous file, payments as far as they exist')
    server = Server()
    keep = ('data_download.py', 'data_columns.py', 'otree_routes.py',
            'experimenter_dashboard.py', 'common.py', 'buildinfo.py')
    base_dir = tempfile.mkdtemp(prefix='download_check_plain_')
    try:
        shutil.rmtree(server.app)
        os.makedirs(os.path.join(server.app, 'plain'))
        os.makedirs(os.path.join(server.app, '_static', 'global', 'css'))
        for name in keep:
            shutil.copy(os.path.join(REPO_ROOT, name), server.app)
        shutil.copy(os.path.join(REPO_ROOT, '_static', 'global', 'css', 'base.css'),
                    os.path.join(server.app, '_static', 'global', 'css'))
        with open(os.path.join(server.app, 'settings.py'), 'w') as fh:
            fh.write(PLAIN_SETTINGS)
        with open(os.path.join(server.app, 'plain', '__init__.py'), 'w') as fh:
            fh.write(PLAIN_APP)
        for page in ('Ask', 'Done'):
            with open(os.path.join(server.app, 'plain', f'{page}.html'), 'w') as fh:
                fh.write('{{ block title }}Plain{{ endblock }}\n'
                         '{{ block content }}{{ formfields }}{{ next_button }}{{ endblock }}\n')
        server.resetdb()
        server.start(base_dir)
        code = api_session(server, 'plain', 2)
        p = participant_codes(server, code)
        s = requests.Session()
        r = s.get(f'{server.base}/InitializeParticipant/{p[0]}')
        check(r.status_code == 200 and '/plain/Ask/' in r.url, 'a participant reaches its own page')
        r = s.post(r.url, data={'answer': 'hello'})
        check(r.status_code == 200 and '/plain/Done/' in r.url, 'and submits it')

        screen = Screen(browser, server, code)
        screen.press()
        text = screen.panel_text()
        check('No anonymous file: this study has no IBAN, BIC or Prolific columns' in text,
              'the confirm step says there will be no anonymous file')
        check('This study has no column for: Prolific ID' in text and 'total earned' in text,
              'and which payment columns do not exist')
        check('write two files' in text.lower(), 'and that two files will be written')
        check(os.path.join('ANONYMOUS', f'EXP_{TODAY}.csv') not in text,
              'and promises no anonymous path')
        check(screen.page.inner_text('#dl-confirm') == 'Write the 2 files',
              'the main action counts the files')
        screen.shot('15_confirm_plain_study')
        screen.confirm()
        text = screen.panel_text()
        check('Both files were written' in text, f'the result says so ({text[:60]})')
        check('No anonymous file' in text and 'This study has no column for' in text,
              'and repeats why')
        check(screen.page.locator('.dl-verdict.good').count() == 1,
              'a study without those columns is not shown as a failure')
        check('2 rows' in text and os.path.join(base_dir, 'SENSITIVE') in text,
              'with paths and rows')
        screen.shot('16_result_plain_study')
        names = tree(base_dir)
        check(names == [os.path.join('PAYMENTS', f'EXP_{TODAY}_PAYMENTS.csv'),
                        os.path.join('SENSITIVE', f'EXP_{TODAY}_SENSITIVE.csv')],
              f'exactly two files on disk ({names})')
        wide = http_admin(server).get(server.base + '/ExportWide').content
        raw = open(os.path.join(base_dir, 'SENSITIVE', f'EXP_{TODAY}_SENSITIVE.csv'), 'rb').read()
        check(raw == wide, 'SENSITIVE is byte for byte /ExportWide')
        head, rows = read_csv_bytes(open(os.path.join(
            base_dir, 'PAYMENTS', f'EXP_{TODAY}_PAYMENTS.csv'), 'rb').read())
        check(head == ['participant.code'] and sorted(r['participant.code'] for r in rows)
              == sorted(p), 'PAYMENTS has the participant code alone, every participant')
        screen.close()

        server.start(None)
        screen = Screen(browser, server, code)
        screen.press()
        screen.shot('17_confirm_plain_browser')
        screen.confirm()
        downloads = get_downloads(screen, 2)
        check(sorted(d.suggested_filename for d in downloads)
              == [f'EXP_{TODAY}_PAYMENTS.csv', f'EXP_{TODAY}_SENSITIVE.csv'],
              'browser mode: two real downloads, no anonymous one')
        text = screen.panel_text()
        check('2 files sent to the browser' in text and 'No anonymous file' in text,
              f'and it says so ({text[:50]})')
        screen.shot('18_result_plain_browser')
        screen.close()
    finally:
        server.destroy()
        shutil.rmtree(base_dir, ignore_errors=True)


def main():
    from playwright.sync_api import sync_playwright
    server = Server()
    base_dir = tempfile.mkdtemp(prefix='download_check_folder_')
    folder = os.path.join(base_dir, 'My Data Folder')
    os.mkdir(folder)
    try:
        server.resetdb()
        server.start(folder)
        print(f'server: {server.otree}, port {server.port}')
        probe = subprocess.run(
            [os.path.join(os.path.dirname(server.otree), 'python'), '-c',
             'import importlib.util as u; print(u.find_spec("pandas") is not None)'],
            capture_output=True, text=True)
        print(f'pandas importable by the server: {probe.stdout.strip()}')

        lab = api_session(server, 'lab', 3, lab_session='217b')
        prolific = api_session(server, 'prolific', 2)
        codes = participant_codes(server, lab)
        assert walk(server, codes[0], iban=IBAN) == 'Results'
        assert walk(server, codes[1], iban=DE_IBAN, bic=BIC) == 'Results'
        pro = participant_codes(server, prolific)
        assert walk(server, pro[0], label=PROLIFIC_ID) == 'Results'

        with sync_playwright() as pw:
            # Headless is the default. DOWNLOAD_CHECK_HEADED=1 (under xvfb-run) runs
            # the full browser, the one with Chrome's multiple-downloads limiter.
            browser = pw.chromium.launch(
                headless=not os.environ.get('DOWNLOAD_CHECK_HEADED'))
            try:
                scenario_folder(browser, server, folder, lab, prolific)
                scenario_broken_folders(browser, server, folder, lab)
                scenario_walls(browser, server, folder, lab)

                server.start(os.path.join(base_dir, 'typo', 'no such folder'))
                scenario_missing_base(browser, server,
                                      os.path.join(base_dir, 'typo', 'no such folder'), lab)
                check('DOWNLOAD DATA WARNING' in server.log(),
                      'the server warned about the missing folder at boot')
                check(requests.get(server.base + '/login').status_code == 200,
                      'and a bad folder does not stop the server')

                server.start(None)
                scenario_browser_mode(browser, server, lab)

                server.start(folder)
                big = api_session(server, 'lab', TIMING_ROWS, lab_session='timing')
                scenario_running_session(browser, server, folder, big)
                server.stop()
                scenario_plain_study(browser)
            finally:
                browser.close()
    finally:
        server.destroy()
        for root, dirs, _names in os.walk(base_dir):
            for name in dirs:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
        shutil.rmtree(base_dir, ignore_errors=True)

    print('\n=== SUMMARY ===')
    print(f'  screenshots: {SHOTS}')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED')
        for m in _failures:
            print(f'    - {m}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
