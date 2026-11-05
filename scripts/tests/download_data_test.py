#!/usr/bin/env python3
"""THE DASHBOARD'S "DOWNLOAD DATA" BUTTON, in-process (data_download.py).

The person this protects is whoever pays participants and shares data: a file
that overwrites last week's, a bank number in a file called anonymous, or a
button that says nothing when the folder was mistyped. It drives the real routes
over oTree's real app with participants walked through the real pages, so the
files are made from a real export, and it reads them back as raw text.

  A. Names: the lab session as a file name, and the date.
  B. The folder setting, including Windows spellings through `ntpath`.
  C. The login and CSRF walls, with AUTH_LEVEL OFF and OTREE_SKIP_CSRF ON: both
     must hold anyway. The dashboard page itself opening is the paired presence.
  D. The three files: names, subfolders, columns, values, against /ExportWide.
  E. A refused Prolific claim names the ID in participant_extra; ANONYMOUS must
     not carry it, and SENSITIVE must.
  F. Never overwrite: second press, taken names, a parallel storm.
  G. Failing on the screen: missing base folder, a file in a subfolder's way, no
     permission, a move that fails, a personal column left over, an empty database,
     and the rules for a study that lacks columns (no anonymous file, payments with
     what exists).
  H. No participant data in error text or logs.
  I. Read-only: not one INSERT, UPDATE or DELETE, where oTree's own /ExportWide
     rewrites every participant's vars; a dirty export is thrown away.
  J. Browser mode: three files in the answer, no-store, no temp file anywhere.
  K. Drift: loud on the button, quiet at boot; the launch check reports it.

  L. The lock: a slow disk does not hold up a participant page, over real HTTP.

What it cannot see: a real browser, a real prodserver and a participant running
at the same time. Those are download_data_browser_check.py.

Run: python scripts/tests/download_data_test.py   (boots oTree in-process)
"""
import csv
import datetime
import io
import logging
import ntpath
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
import threading

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402,F401

# Before boot: oTree reads these at import. AUTH_LEVEL OFF, so section C proves
# the button's wall holds where the rest of the admin has none.
os.environ.pop('OTREE_AUTH_LEVEL', None)
os.environ['OTREE_ADMIN_PASSWORD'] = 'admin'
os.environ['OTREE_SKIP_CSRF'] = '1'
os.environ.pop('OTREE_DATA_FOLDER', None)

from main_contract import task_page_submits  # noqa: E402
from otree_inprocess import boot, page_name_of, path_of  # noqa: E402
import bot_walker  # noqa: E402
from quiz_answers import CORRECT  # noqa: E402

ot = boot(production=True)

import data_columns  # noqa: E402
import data_download as dd  # noqa: E402
import experimenter_dashboard as ed  # noqa: E402

_failures = []
ENV = dd.ENV_VAR
TODAY = datetime.date.today().strftime('%d-%m-%Y')
PROLIFIC_ONE = '5f3c9d2e1a7b4c6d8e9f0a1b'
PROLIFIC_TWO = '60aa11bb22cc33dd44ee55ff'
IBAN = 'NL91ABNA0417164300'
DE_IBAN = 'DE89370400440532013000'
BIC = 'COBADEFFXXX'
DESKTOP = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/126.0.0.0 Safari/537.36')}


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def payload_for(page, label='', iban=IBAN, bic=''):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'ConfirmProlificID': {'participant_id_external': label},
        'quiz': dict(CORRECT),
        **task_page_submits(),
        'Demographics': {'age': '30', 'gender': 'Female', 'bank': iban,
                         'bank_confirmation': iban, 'bic': bic},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def walk(code, label='', iban=IBAN, bic='', url_label=None):
    """One participant through the real pages, entry to ending."""
    client = ot.client()
    entry = f'/InitializeParticipant/{code}'
    if url_label:
        entry += f'?participant_label={url_label}'
    resp = client.get(entry, allow_redirects=True, headers=DESKTOP)
    for _ in range(120):
        page = page_name_of(path_of(resp))
        if page is None or page in ('Results', 'Ended'):
            return page
        data = (bot_walker.dotbi_payload(code) if page == 'DotBiGate'
                else payload_for(page, label, iban, bic))
        resp = client.post(path_of(resp), data=data, allow_redirects=True,
                           headers=DESKTOP)
    return None


def admin_client():
    client = ot.client()
    page = client.get('/login')
    token = re.search(r'name="csrftoken" value="([^"]+)"', page.text).group(1)
    client.post('/login', data={'username': 'admin', 'password': 'admin',
                                'csrftoken': token}, allow_redirects=False)
    return client


def press(client, code, token=None):
    """What the page does: fetch the plan for its token, then POST with it. Pass
    `token` for a press after the plan step, when the plan itself would now fail."""
    if token is None:
        token = client.get(f'{ed.URL_BASE}/{code}{dd.PLAN_SUFFIX}').json()['csrf']
    return client.post(f'{ed.URL_BASE}/{code}{dd.DOWNLOAD_SUFFIX}',
                       data={'csrftoken': token}).json()


def read_csv(path):
    with open(path, newline='', encoding='utf-8') as fh:
        table = list(csv.reader(fh))
    return table[0], [dict(zip(table[0], row)) for row in table[1:]]


def csv_text(text):
    table = list(csv.reader(io.StringIO(text, newline='')))
    return table[0], [dict(zip(table[0], row)) for row in table[1:]]


def tree(folder):
    """Every file under `folder`, relative, so an absence can be asserted next to
    a presence."""
    found = []
    for root, _dirs, names in os.walk(folder):
        found += [os.path.relpath(os.path.join(root, n), folder) for n in names]
    return sorted(found)


class Folder:
    """A fresh base folder, set in the environment for the block."""

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix='download_test_')
        os.environ[ENV] = self.path
        return self.path

    def __exit__(self, *exc):
        os.environ.pop(ENV, None)
        for root, dirs, _names in os.walk(self.path):
            for name in dirs:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
        shutil.rmtree(self.path, ignore_errors=True)


def section_names():
    section('A. names: the lab session as a file name')
    cases = [('217', '217'), ('217b', '217b'), ('217 b', '217-b'),
             ('217/b', '217-b'), ('007', '007'), ('test', 'test'),
             ('  217  ', '217'), ('../../etc/passwd', 'etc-passwd'),
             ('a\\b:c*d?e"f<g>h|i', 'a-b-c-d-e-f-g-h-i'), ('2.1', '2.1'),
             ('.hidden.', 'hidden'), ('Zürich 1', 'Zürich-1'), ('', ''),
             (None, ''), ('///', ''), (217, '217'), ('a\nb', 'a-b'),
             ('x\u202ey', 'x-y')]
    for value, want in cases:
        got = dd.safe_lab_session(value)
        check(got == want, f'{value!r} -> {want!r} (got {got!r})')
    check(len(dd.safe_lab_session('x' * 500)) <= dd.LAB_SESSION_MAX_CHARS,
          'a very long value is cut to a usable file-name length')

    day = datetime.date(2026, 11, 5)
    check(dd.name_stem('217', day) == 'EXP_217_05-11-2026', 'stem with a lab session')
    check(dd.name_stem('', day) == 'EXP_05-11-2026', 'stem without one')
    check(dd.name_stem(None, day) == 'EXP_05-11-2026', 'stem with None')
    check(dd.file_name('EXP_217_05-11-2026', 'SENSITIVE')
          == 'EXP_217_05-11-2026_SENSITIVE.csv', 'the SENSITIVE name')
    check(dd.file_name('EXP_217_05-11-2026', 'ANONYMOUS')
          == 'EXP_217_05-11-2026.csv', 'the ANONYMOUS name has no ending')
    check(dd.file_name('EXP_217_05-11-2026', 'PAYMENTS')
          == 'EXP_217_05-11-2026_PAYMENTS.csv', 'the PAYMENTS name')
    check(dd.file_name('EXP_05-11-2026', 'ANONYMOUS', 2) == 'EXP_05-11-2026_2.csv',
          'a numbered set, no lab session')
    check(dd.file_name('EXP_217_05-11-2026', 'SENSITIVE', 3)
          == 'EXP_217_05-11-2026_SENSITIVE_3.csv', 'a numbered SENSITIVE file')


def section_folder_setting():
    section('B. the folder setting')
    clean = dd.clean_folder_setting
    check(clean(None) == (None, None), 'unset means browser mode')
    check(clean('   ') == (None, None), 'blank means browser mode')
    check(clean('""') == (None, None), 'empty quotes mean browser mode')
    check(clean('/data/x/', posixpath) == ('/data/x', None), 'POSIX, trailing slash')
    check(clean('"/data/my x"', posixpath) == ('/data/my x', None),
          'POSIX, quoted with a space')
    folder, problem = clean('data/x', posixpath)
    check(problem is not None and 'data/x' in problem and folder == 'data/x',
          'a relative path is refused and named, not resolved')

    # Windows spellings, through the real ntpath, on this machine.
    for raw, want in [
            (r'C:\Users\lab\Data', r'C:\Users\lab\Data'),
            (r'C:\Users\lab\Data' + '\\', r'C:\Users\lab\Data'),
            (r'"C:\Users\lab\My Data"', r'C:\Users\lab\My Data'),
            (r'C:/Users/lab/Data', r'C:\Users\lab\Data'),
            (r'\\server\share\data', r'\\server\share\data')]:
        got = clean(raw, ntpath)
        check(got == (want, None), f'Windows {raw} -> {want} (got {got!r})')
    for raw in (r'Data\x', r'C:Data'):
        check(clean(raw, ntpath)[1] is not None,
              f'Windows {raw} is not a full path, so it is refused')
    check(ntpath.join(r'C:\Users\lab\Data', 'SENSITIVE',
                      dd.file_name('EXP_217_05-11-2026', 'SENSITIVE'))
          == r'C:\Users\lab\Data\SENSITIVE\EXP_217_05-11-2026_SENSITIVE.csv',
          'the file path a Windows machine would build')
    for bad in '<>:"/\\|?*':
        check(bad not in dd.safe_lab_session(f'a{bad}b'),
              f'no Windows-illegal {bad!r} survives into a file name')


def section_walls(lab):
    section('C. the login and CSRF walls hold with AUTH_LEVEL off and SKIP_CSRF on')
    plan_url = f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}'
    post_url = f'{ed.URL_BASE}/{lab.code}{dd.DOWNLOAD_SUFFIX}'

    with Folder() as folder:
        stranger = ot.client()
        page = stranger.get(f'{ed.URL_BASE}/{lab.code}', allow_redirects=False)
        check(page.status_code == 200 and 'dl-open' in page.text,
              'with AUTH_LEVEL off the dashboard page opens and carries the button '
              '(so the refusals below are the button\'s own wall)')
        answer = stranger.get(plan_url, allow_redirects=False)
        check(answer.status_code == 403 and answer.json()['problem'] == 'login',
              f'not logged in: the plan is refused (got {answer.status_code})')
        check('csrf' not in answer.json(), 'not logged in: no token is handed out')
        answer = stranger.post(post_url, data={'csrftoken': 'x'},
                               allow_redirects=False)
        check(answer.status_code == 403 and answer.json()['problem'] == 'login',
              f'not logged in: the POST is refused (got {answer.status_code})')
        check(tree(folder) == [], 'not logged in: nothing was written')

        admin = admin_client()
        answer = admin.post(post_url, data={}, allow_redirects=False)
        check(answer.status_code == 403 and answer.json()['problem'] == 'csrf',
              f'logged in, no token: refused (got {answer.status_code})')
        answer = admin.post(post_url, data={'csrftoken': 'wrong'},
                            allow_redirects=False)
        check(answer.status_code == 403 and answer.json()['problem'] == 'csrf',
              f'logged in, wrong token: refused (got {answer.status_code})')
        check(tree(folder) == [], 'no valid token: nothing was written')
        check(press(admin, lab.code)['ok'] is True, 'logged in, right token: works')
        check(len(tree(folder)) == 3, 'and three files appear')

        answer = admin.get(post_url)
        check(answer.status_code == 405, 'GET on the writing route is refused')
        check(len(tree(folder)) == 3, 'and writes nothing')
        answer = admin.post(plan_url, data={})
        check(answer.status_code == 405, 'POST on the plan route is refused')

        # A login check that breaks must deny.
        real = ed._checked_admin_view().__dict__.get('_is_logged_in')
        view = ed._checked_admin_view()

        def broken(self):
            raise ValueError('boom')
        view._is_logged_in = broken
        try:
            answer = admin.post(post_url, data={'csrftoken': 'x'})
            check(answer.status_code == 403, 'a login check that raises denies')
        finally:
            view._is_logged_in = real
        check(len(tree(folder)) == 3, 'and writes nothing')

    # A folder cannot be chosen by the request.
    with Folder() as folder:
        elsewhere = tempfile.mkdtemp(prefix='download_elsewhere_')
        plan = admin.get(plan_url).json()
        admin.post(post_url + f'?folder={elsewhere}',
                   data={plan['csrf_name']: plan['csrf'], 'folder': elsewhere,
                         ENV: elsewhere})
        check(tree(elsewhere) == [], 'a folder named in the request is ignored')
        check(len(tree(folder)) == 3, 'the files go to the configured folder')
        shutil.rmtree(elsewhere, ignore_errors=True)


def section_three_files(admin, lab, prolific):
    section('D. the three files, against the real wide export')
    wide = admin.get('/ExportWide')
    check(wide.status_code == 200 and b'participant.code' in wide.content,
          'oTree\'s own /ExportWide answers, as the reference')
    wide_header, wide_rows = csv_text(wide.content.decode('utf-8'))

    with Folder() as folder:
        answer = press(admin, lab.code)
        check(answer['ok'] is True and answer['mode'] == 'folder',
              f'folder mode says ok (got {answer.get("ok")})')
        stem = f'EXP_217b_{TODAY}'
        want = {
            'SENSITIVE': os.path.join(folder, 'SENSITIVE', f'{stem}_SENSITIVE.csv'),
            'ANONYMOUS': os.path.join(folder, 'ANONYMOUS', f'{stem}.csv'),
            'PAYMENTS': os.path.join(folder, 'PAYMENTS', f'{stem}_PAYMENTS.csv'),
        }
        got = {f['kind']: f for f in answer['files']}
        for kind, path in want.items():
            check(got[kind]['path'] == path and os.path.isfile(path),
                  f'{kind}: full path on the screen and on disk: {path}')
            check(got[kind]['rows'] == len(wide_rows),
                  f'{kind}: the row count on the screen is {len(wide_rows)}')
        check(len(tree(folder)) == 3, f'exactly three files and no temp ({tree(folder)})')

        with open(want['SENSITIVE'], 'rb') as fh:
            check(fh.read() == wide.content,
                  'SENSITIVE is byte for byte what /ExportWide serves')

        head, rows = read_csv(want['ANONYMOUS'])
        check(all(f['note'] is None and not f['skipped'] for f in answer['files']),
              'the template has every column: nothing to remark on')
        check(head == [c for c in wide_header
                       if c not in data_columns.ANON_DROP_COLUMNS],
              'ANONYMOUS: every other column, in the export\'s order')
        for column in data_columns.ANON_DROP_COLUMNS:
            check(column in wide_header and column not in head,
                  f'ANONYMOUS: {column} is in the export and not in this file')
        check(len(rows) == len(wide_rows), 'ANONYMOUS: every participant has a row')
        for a, w in zip(rows, wide_rows):
            same = all(a[c] == w[c] for c in head
                       if c not in data_columns.ANON_BLANK_COLUMNS)
            if not check(same and a['participant.code'] == w['participant.code'],
                         f'ANONYMOUS: row {a["participant.code"]} matches the export'):
                break
        with open(want['ANONYMOUS'], encoding='utf-8') as fh:
            text = fh.read()
        for secret in (IBAN, DE_IBAN, BIC, PROLIFIC_ONE):
            check(secret not in text, f'ANONYMOUS: {secret} is nowhere in it')
        check(any(w['outro.1.player.bank'] == IBAN for w in wide_rows),
              'and the export it came from does carry the IBAN')

        head, rows = read_csv(want['PAYMENTS'])
        check(head == list(data_columns.PAYMENT_COLUMNS),
              f'PAYMENTS: exactly the five columns ({head})')
        check(len(rows) == len(wide_rows), 'PAYMENTS: every participant has a row')
        by_code = {r['participant.code']: r for r in rows}
        for w in wide_rows:
            if not check(all(by_code[w['participant.code']][c] == w[c] for c in head),
                         f'PAYMENTS: {w["participant.code"]} matches the export'):
                break
        lab_rows = [r for w in wide_rows if w['session.code'] == lab.code
                    for r in [by_code[w['participant.code']]]]
        pro_rows = [r for w in wide_rows if w['session.code'] == prolific.code
                    for r in [by_code[w['participant.code']]]]
        check(any(r['outro.1.player.bank'] == DE_IBAN
                  and r['outro.1.player.bic'] == BIC for r in lab_rows),
              'PAYMENTS: a lab row has IBAN and BIC')
        check(all(not r['participant.participant_id_external'] for r in lab_rows),
              'PAYMENTS: lab rows have no Prolific ID')
        check(any(r['participant.participant_id_external'] == PROLIFIC_ONE
                  for r in pro_rows), 'PAYMENTS: a Prolific row has the ID')
        check(all(not r['outro.1.player.bank'] for r in pro_rows),
              'PAYMENTS: Prolific rows have no IBAN')
        finished = [r for r in pro_rows if r['outro.1.player.earned']]
        check(finished and float(finished[0]['outro.1.player.earned']) > 0,
              f'PAYMENTS: a finisher has a total ({finished[0]["outro.1.player.earned"]})')

    section('D2. the total is `earned`, which already includes every fee')
    for w in wide_rows:
        if not w['outro.1.player.earned']:
            continue
        rebuilt = (float(w['session.config.payment_show_up'])
                   + float(w['outro.1.player.selected_sum'])
                   + float(w['outro.1.player.quiz_bonus_awarded']))
        total = float(w['participant.payoff'])
        total += float(w['session.config.participation_fee'])
        if not check(abs(float(w['outro.1.player.earned']) - rebuilt) < 1e-9
                     and abs(float(w['outro.1.player.earned']) - total) < 1e-9,
                     f'earned {w["outro.1.player.earned"]} = show-up + rounds + bonus'
                     f' = payoff + participation_fee'):
            break

    section('D3. the name follows the session being viewed, with or without a number')
    with Folder() as folder:
        answer = press(admin, prolific.code)
        check({f['name'] for f in answer['files']}
              == {f'EXP_{TODAY}_SENSITIVE.csv', f'EXP_{TODAY}.csv',
                  f'EXP_{TODAY}_PAYMENTS.csv'},
              'a session with no lab session has no number in its names')
        head, rows = read_csv(answer['files'][0]['path'])
        check({r['session.code'] for r in rows} == {lab.code, prolific.code},
              'and the file still covers every session in the database')


def section_refused_claim(admin, prolific):
    section('E. ANONYMOUS and a refused Prolific claim (participant_extra names the ID)')
    codes = ot.participant_codes(prolific)
    check(walk(codes[1], label=PROLIFIC_ONE, url_label=PROLIFIC_TWO) in ('Results', 'Ended'),
          'a participant walks in claiming an ID another row already holds')
    with Folder():
        answer = press(admin, prolific.code)
        by_kind = {f['kind']: f['path'] for f in answer['files']}
        sensitive = open(by_kind['SENSITIVE'], encoding='utf-8').read()
        anonymous = open(by_kind['ANONYMOUS'], encoding='utf-8').read()
        head, rows = read_csv(by_kind['SENSITIVE'])
        extra = [r['participant.participant_extra'] for r in rows
                 if r['participant.code'] == codes[1]][0]
        check(PROLIFIC_ONE in extra,
              'SENSITIVE: participant_extra of that row holds the refused ID '
              '(so the next checks test something real)')
        check(PROLIFIC_ONE in sensitive and PROLIFIC_TWO in sensitive,
              'SENSITIVE: both IDs are in the file')
        check(PROLIFIC_ONE not in anonymous and PROLIFIC_TWO not in anonymous,
              'ANONYMOUS: neither ID is anywhere in the file')
        head, rows = read_csv(by_kind['ANONYMOUS'])
        check('participant.participant_extra' in head
              and all(r['participant.participant_extra'] == '' for r in rows),
              'ANONYMOUS: participant_extra is there, and empty in every row')


def section_never_overwrite(admin, lab):
    section('F. never overwrite')
    with Folder() as folder:
        stem = f'EXP_217b_{TODAY}'
        first = press(admin, lab.code)
        before = {f['path']: open(f['path'], 'rb').read() for f in first['files']}
        second = press(admin, lab.code)
        check(second['ok'] is True, 'a second press works')
        check({f['name'] for f in second['files']}
              == {f'{stem}_SENSITIVE_2.csv', f'{stem}_2.csv', f'{stem}_PAYMENTS_2.csv'},
              'it gets _2, the same number on all three')
        check(all(open(p, 'rb').read() == data for p, data in before.items()),
              'the first set is byte for byte unchanged')
        third = press(admin, lab.code)
        check(all(f['name'].endswith('_3.csv') for f in third['files']), 'a third gets _3')
        check(len(tree(folder)) == 9, 'nine files, no temp left behind')

    with Folder() as folder:
        # A planted file on one name moves the WHOLE set to the next number.
        stem = f'EXP_217b_{TODAY}'
        os.mkdir(os.path.join(folder, 'PAYMENTS'))
        planted = os.path.join(folder, 'PAYMENTS', f'{stem}_PAYMENTS.csv')
        with open(planted, 'w') as fh:
            fh.write('precious')
        plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()
        check(all(f['name'].endswith('_2.csv') for f in plan['files']),
              'the plan already shows the next free number')
        answer = press(admin, lab.code)
        check(all(f['written'] and f['name'].endswith('_2.csv') for f in answer['files']),
              'one taken name moves all three to _2, so the set stays together')
        check(open(planted).read() == 'precious', 'and the taken file is untouched')

    with Folder() as folder:
        # A dangling link on a final name must count as taken: O_EXCL fails on it,
        # and a follow-the-link create would write somewhere else.
        stem = f'EXP_217b_{TODAY}'
        os.mkdir(os.path.join(folder, 'ANONYMOUS'))
        target = os.path.join(folder, 'outside.txt')
        os.symlink(target, os.path.join(folder, 'ANONYMOUS', f'{stem}.csv'))
        answer = press(admin, lab.code)
        check(answer['ok'] and not os.path.exists(target),
              'a dangling link on a name is not followed; the set takes _2')

    section('F2. the race: eight presses at once at the writing layer')
    with Folder() as folder:
        stem = 'EXP_race_05-11-2026'
        results, errors = [], []
        barrier = threading.Barrier(8)

        def racer(i):
            try:
                barrier.wait()
                built = [dict(kind=k, rows=1, data=f'{i},{k}\r\n'.encode())
                         for k in dd.KINDS]
                results.append((i, dd.write_set(folder, stem, built)))
            except Exception as exc:                           # noqa: BLE001
                errors.append(exc)
        threads = [threading.Thread(target=racer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check(not errors, f'no press raised ({errors})')
        check(all(f['written'] for _i, r in results for f in r),
              'all eight sets were written in full')
        check(len(tree(folder)) == 24, f'24 files, so no name was shared, no temp '
                                       f'left ({len(tree(folder))})')
        for i, result in results:
            numbers = {re.search(r'(_\d+)?\.csv$', f['name']).group(1) for f in result}
            bodies = {open(f['path']).read().split(',')[0] for f in result}
            if not check(len(numbers) == 1 and bodies == {str(i)},
                         f'press {i}: one number on all three, and its own content'):
                break


def section_failing_loudly(admin, lab):
    section('G. missing base folder')
    os.environ[ENV] = os.path.join(tempfile.gettempdir(), 'download_no_such_typo_dir', 'x')
    missing = os.environ[ENV]
    try:
        plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()
        check(plan['ok'] is False and missing in plan['message'],
              'the plan says so and names the folder')
        answer = press(admin, lab.code)
        check(answer['ok'] is False and missing in answer['message']
              and answer['files'] == [], 'so does the POST, with no files listed')
        check(not os.path.exists(os.path.dirname(missing)),
              'and no folder was created')
    finally:
        os.environ.pop(ENV, None)

    section('G2. the base "folder" is a file; a relative path')
    with tempfile.NamedTemporaryFile(prefix='download_afile_') as fh:
        os.environ[ENV] = fh.name
        answer = press(admin, lab.code)
        check(answer['ok'] is False and fh.name in answer['message'],
              'a file as the base folder is refused and named')
    os.environ[ENV] = 'relative/data'
    answer = press(admin, lab.code)
    check(answer['ok'] is False and 'relative/data' in answer['message'],
          'a relative path is refused and named')
    check(not os.path.exists('relative'), 'and created nothing')
    os.environ.pop(ENV, None)

    section('G3. a file in the way of one subfolder')
    with Folder() as folder:
        with open(os.path.join(folder, 'PAYMENTS'), 'w') as fh:
            fh.write('in the way')
        plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()
        check(plan['ok'] and any('PAYMENTS' in w for w in plan['warnings']),
              'the confirm step warns about it')
        answer = press(admin, lab.code)
        by_kind = {f['kind']: f for f in answer['files']}
        check(answer['ok'] is False, 'the answer is not ok')
        check(by_kind['SENSITIVE']['written'] and os.path.isfile(by_kind['SENSITIVE']['path']),
              'SENSITIVE is written and listed')
        check(by_kind['ANONYMOUS']['written'] and os.path.isfile(by_kind['ANONYMOUS']['path']),
              'ANONYMOUS is written and listed')
        check(not by_kind['PAYMENTS']['written']
              and 'in the way' in (by_kind['PAYMENTS']['why'] or ''),
              f'PAYMENTS is not, and says why ({by_kind["PAYMENTS"]["why"]})')
        check(open(os.path.join(folder, 'PAYMENTS')).read() == 'in the way',
              'the file in the way is untouched')

    section('G4. no permission')
    if os.geteuid() == 0:
        print('  [SKIP] running as root: permissions do not apply')
    else:
        with Folder() as folder:
            os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
            answer = press(admin, lab.code)
            os.chmod(folder, stat.S_IRWXU)
            check(answer['ok'] is False and answer['files']
                  and all(not f['written'] for f in answer['files']),
                  'an unwritable base folder: no file claims to be written')
            check(all('permission' in (f['why'] or '') for f in answer['files']),
                  'each says why, in plain words')
            check(tree(folder) == [], 'and the disk agrees')
        with Folder() as folder:
            os.mkdir(os.path.join(folder, 'ANONYMOUS'))
            os.chmod(os.path.join(folder, 'ANONYMOUS'), stat.S_IRUSR | stat.S_IXUSR)
            answer = press(admin, lab.code)
            by_kind = {f['kind']: f for f in answer['files']}
            check(not by_kind['ANONYMOUS']['written'] and by_kind['SENSITIVE']['written']
                  and by_kind['PAYMENTS']['written'],
                  'one unwritable subfolder: the other two are saved')

    section('G5. a move that fails: retried, then reported, nothing left behind')
    real_replace = os.replace
    with Folder() as folder:
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) <= 2:
                raise PermissionError(13, 'in use')
            return real_replace(src, dst)
        os.replace = flaky
        try:
            answer = press(admin, lab.code)
        finally:
            os.replace = real_replace
        check(answer['ok'] is True and len(calls) >= 4,
              'a scanner holding the file for a moment is waited out (Windows)')

    with Folder() as folder:
        def always(src, dst):
            if 'PAYMENTS' in dst:
                raise PermissionError(13, 'in use')
            return real_replace(src, dst)
        os.replace = always
        try:
            answer = press(admin, lab.code)
        finally:
            os.replace = real_replace
        by_kind = {f['kind']: f for f in answer['files']}
        check(not by_kind['PAYMENTS']['written'] and by_kind['PAYMENTS']['why'],
              'a move that never works is reported')
        check(not os.path.exists(by_kind['PAYMENTS']['path']),
              'its empty placeholder is removed')
        check(os.listdir(os.path.join(folder, 'PAYMENTS')) == [],
              'and its temp file is removed')
        check(by_kind['SENSITIVE']['written'], 'the others are still written')

    section('G6. a study whose personal columns moved')
    header = ['participant.code', 'payment.1.player.bank', 'session.label',
              'main.1.player.earned', 'outro.1.player.earned', 'participant.label']
    built = dd.build_files([header, ['a', 'NL00', 'x', '1', '2', 'L']])
    by_kind = {b['kind']: b for b in built}
    check(by_kind['ANONYMOUS']['data'] is None and not by_kind['ANONYMOUS']['skipped']
          and 'payment.1.player.bank' in by_kind['ANONYMOUS']['why'],
          'a renamed outro: ANONYMOUS is refused as a failure, naming the column')
    check(by_kind['SENSITIVE']['data'] is not None, 'SENSITIVE still comes out')
    check(data_columns.personal_columns_left(
              ['outro.2.player.bic', 'x.1.player.participant_id_external',
               'pay.1.player.iban', 'participant.prolific_id']) ==
          ['outro.2.player.bic', 'x.1.player.participant_id_external',
           'pay.1.player.iban', 'participant.prolific_id'],
          'a second round of the bank page, a renamed entry app, other spellings: all caught')
    check(data_columns.personal_columns_left(
              ['session.label', 'main.1.player.earned', 'main.1.player.answer',
               'participant.code', 'participant.payoff']) == [],
          'session.label, an analysis `earned` and the code are not caught')
    with Folder() as folder:
        files = dd.write_set(folder, 'EXP_x', built)
        results = {f['kind']: f for f in files}
        check(results['SENSITIVE']['written'] and not results['ANONYMOUS']['written']
              and results['ANONYMOUS']['why'], 'the screen would list it, with the reason')
        check(results['PAYMENTS']['written'], 'and PAYMENTS is written with what exists')
        check(tree(folder) == [os.path.join('PAYMENTS', 'EXP_x_PAYMENTS.csv'),
                               os.path.join('SENSITIVE', 'EXP_x_SENSITIVE.csv')],
              'and only the safe files are on disk')

    section('G6b. a study not built from this template: the rules for missing columns')
    bare = ['participant.code', 'participant.label', 'participant.payoff',
            'plain.1.player.answer']
    parts = {p['kind']: p for p in data_columns.split_export(
        [bare, ['c1', '', '1.5', 'yes'], ['c2', '', '2.5', 'no']])}
    check(parts['SENSITIVE']['table'] is not None, 'SENSITIVE is always made')
    check(parts['ANONYMOUS']['table'] is None and parts['ANONYMOUS']['skipped'],
          'no personal columns and no labels: no ANONYMOUS, and that is not a failure')
    check('IBAN, BIC or Prolific' in parts['ANONYMOUS']['why'],
          f'with the reason in plain words ({parts["ANONYMOUS"]["why"]})')
    check(parts['PAYMENTS']['table'] == [['participant.code'], ['c1'], ['c2']],
          'PAYMENTS: the participant code alone still counts as a file')
    for words in ('Prolific ID', 'IBAN', 'BIC', 'total earned', 'outro.1.player.earned'):
        check(words in parts['PAYMENTS']['note'], f'the note names what is missing: {words}')
    check('participant code' not in parts['PAYMENTS']['note'],
          'and not what is there')

    labelled = {p['kind']: p for p in data_columns.split_export(
        [bare, ['c1', 'SEAT1', '1.5', 'yes'], ['c2', '', '2.5', 'no']])}
    check(labelled['ANONYMOUS']['table'] is not None
          and 'participant.label' not in labelled['ANONYMOUS']['table'][0]
          and 'SEAT1' not in str(labelled['ANONYMOUS']['table']),
          'a label in any row IS something to remove: ANONYMOUS, without it')

    with_earned = ['participant.code', 'participant.label', 'outro.1.player.earned',
                   'outro.1.player.bic']
    only = {p['kind']: p for p in data_columns.split_export(
        [with_earned, ['c1', '', '9.5', '']])}
    check(only['PAYMENTS']['table'] == [
              ['participant.code', 'outro.1.player.bic', 'outro.1.player.earned'],
              ['c1', '', '9.5']],
          'earned and a BIC exist: included, in the list\'s order, not the export\'s')
    check(only['ANONYMOUS']['table'] is not None, 'a BIC column is something to remove')
    earned_alone = {p['kind']: p for p in data_columns.split_export(
        [['participant.code', 'participant.label', 'outro.1.player.earned'],
         ['c1', '', '9.5']])}
    check(earned_alone['ANONYMOUS']['skipped'],
          'earned alone is not: it identifies nobody, so no misleading file')
    check(earned_alone['PAYMENTS']['table'] == [
              ['participant.code', 'outro.1.player.earned'], ['c1', '9.5']],
          'and PAYMENTS includes the earned that exists')

    with Folder() as folder:
        built = dd.build_files([bare, ['c1', '', '1.5', 'yes']])
        files = {f['kind']: f for f in dd.write_set(folder, 'EXP_y', built)}
        check(files['ANONYMOUS']['skipped'] and files['ANONYMOUS']['path'] is None,
              'on writing: no path claimed for the file that does not exist')
        check(files['PAYMENTS']['note'] and files['PAYMENTS']['written'],
              'and PAYMENTS carries its note')
        check(tree(folder) == [os.path.join('PAYMENTS', 'EXP_y_PAYMENTS.csv'),
                               os.path.join('SENSITIVE', 'EXP_y_SENSITIVE.csv')],
              'exactly two files on disk')
        again = {f['kind']: f for f in dd.write_set(folder, 'EXP_y', built)}
        check(again['PAYMENTS']['name'] == 'EXP_y_PAYMENTS_2.csv'
              and again['SENSITIVE']['name'] == 'EXP_y_SENSITIVE_2.csv',
              'a second press still numbers the set together')


def section_no_data_leaks(admin, lab):
    section('H. no participant data in error text or logs')
    from otree import export
    real = export.get_rows_for_wide_csv
    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    logging.getLogger().addHandler(handler)
    dd.logger.addHandler(handler)

    token = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()['csrf']

    def leaky(session_code):
        raise ValueError(f'row 7 has bank {IBAN} and id {PROLIFIC_ONE}')
    export.get_rows_for_wide_csv = leaky
    try:
        with Folder() as folder:
            plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()
            check(plan['ok'] is False and IBAN not in str(plan)
                  and 'ValueError' in plan['message'],
                  'the confirm step already says the export fails, without the data')
            answer = press(admin, lab.code, token)
            check(answer['ok'] is False and answer['problem'] == 'failed',
                  'an export that raises gives a failure on the screen')
            check('no files were written' in answer['message'],
                  f'saying no files were written ({answer["message"]})')
            check('ValueError' in answer['message'], 'naming the error type')
            check(IBAN not in str(answer) and PROLIFIC_ONE not in str(answer),
                  'the IBAN and ID in the exception are not on the screen')
            check(tree(folder) == [], 'nothing on disk')
    finally:
        export.get_rows_for_wide_csv = real
        logging.getLogger().removeHandler(handler)
        dd.logger.removeHandler(handler)
    logged = captured.getvalue()
    check('ValueError' in logged and 'data_download.py' in logged,
          f'the log has the type and the place ({logged.strip()[:120]!r})')
    check(IBAN not in logged and PROLIFIC_ONE not in logged,
          'and neither the IBAN nor the ID')


def _dump_database():
    """Every row of every table, as plain text, on the app's own connection."""
    from sqlalchemy import inspect, text
    from otree.database import engine
    out = {}
    with engine.connect() as conn:
        for table in sorted(inspect(engine).get_table_names()):
            out[table] = repr(conn.execute(text(f'SELECT * FROM "{table}"')).fetchall())
    return out


class WriteSpy:
    """Every INSERT/UPDATE/DELETE that reaches the database during the block."""

    def __enter__(self):
        from sqlalchemy import event
        from otree.database import engine
        self.engine, self.writes = engine, []
        event.listen(engine, 'before_cursor_execute', self._seen)
        return self

    def _seen(self, _conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().split(None, 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE'):
            self.writes.append(statement.split('\n')[0][:60])

    def __exit__(self, *exc):
        from sqlalchemy import event
        event.remove(self.engine, 'before_cursor_execute', self._seen)


def section_read_only(admin, lab):
    section('I. read-only: not one statement that writes')
    before = _dump_database()
    check(sum(len(v) for v in before.values()) > 100,
          'the dump really holds rows (it would otherwise prove nothing)')

    # The spy has to be able to see a write. oTree's own export writes, because its
    # `.vars` property marks every row changed on a read: that is the trap.
    with WriteSpy() as spy:
        check(admin.get('/ExportWide').status_code == 200, 'oTree\'s own /ExportWide runs')
    check(any(w.startswith('UPDATE') for w in spy.writes),
          f'and the spy sees it write ({len(spy.writes)} statements), so it can '
          f'see what the next checks say is absent')
    before = _dump_database()

    with WriteSpy() as spy:
        with Folder():
            answer = press(admin, lab.code)
            check(answer['ok'] is True and all(f['written'] for f in answer['files']),
                  'an export ran in folder mode')
        answer = press(admin, lab.code)
        check(answer['ok'] is True and answer['mode'] == 'browser',
              'and one in browser mode')
        check(admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()['ok'],
              'and a plan')
    check(spy.writes == [], f'no INSERT, UPDATE or DELETE reached the database ({spy.writes[:3]})')
    check(_dump_database() == before,
          'every row of every table is byte-identical afterwards')

    # An export that really dirties a row must not get it committed.
    from otree import export
    from otree.database import db
    from otree.models import Participant
    real = export.get_rows_for_wide_csv
    code = ot.participant_codes(lab)[0]

    def dirtying(session_code):
        rows = real(session_code)
        db.query(Participant).filter_by(code=code).one().label = 'DIRTIED'
        return rows
    export.get_rows_for_wide_csv = dirtying
    try:
        with Folder():
            answer = press(admin, lab.code)
    finally:
        export.get_rows_for_wide_csv = real
    check(answer['ok'] is True, 'with an export that dirties a row, the files still come')
    check('DIRTIED' not in _dump_database()['otree_participant'],
          'and the change is thrown away, not committed')


def section_browser_mode(admin, lab):
    section('J. browser mode')
    os.environ.pop(ENV, None)
    made = []
    real = tempfile.mkstemp

    def counting(*args, **kwargs):
        made.append(kwargs.get('dir'))
        return real(*args, **kwargs)
    tempfile.mkstemp = counting
    try:
        plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}')
        check(plan.json()['mode'] == 'browser', 'unset means browser mode')
        response = admin.post(f'{ed.URL_BASE}/{lab.code}{dd.DOWNLOAD_SUFFIX}',
                              data={plan.json()['csrf_name']: plan.json()['csrf']})
    finally:
        tempfile.mkstemp = real
    for label, resp in (('the plan', plan), ('the download', response)):
        check('no-store' in resp.headers.get('cache-control', ''),
              f'{label} is sent with no-store')
    answer = response.json()
    check(answer['ok'] and answer['mode'] == 'browser', 'the answer says browser')
    check([f['kind'] for f in answer['files']] == list(dd.KINDS), 'with three files')
    check([f['name'] for f in answer['files']]
          == [f'EXP_217b_{TODAY}_SENSITIVE.csv', f'EXP_217b_{TODAY}.csv',
              f'EXP_217b_{TODAY}_PAYMENTS.csv'], 'with the right names')
    wide = admin.get('/ExportWide').content
    check(answer['files'][0]['text'].encode('utf-8') == wide,
          'SENSITIVE in the answer is byte for byte /ExportWide')
    check(IBAN not in answer['files'][1]['text'] and IBAN in answer['files'][2]['text'],
          'ANONYMOUS has no IBAN, PAYMENTS does')
    check(made == [], f'no temp file was made in this mode ({made})')
    tempfile.mkstemp = counting
    made.clear()
    try:
        with Folder():
            press(admin, lab.code)
    finally:
        tempfile.mkstemp = real
    check(len(made) == 3, f'the same counter sees 3 in folder mode ({len(made)})')


def section_lock(lab):
    section('L. the disk is outside oTree\'s lock, the read is inside it (real HTTP)')
    import socket
    import time
    import requests
    import uvicorn
    from otree import export
    from otree.asgi import app

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                           log_level='error', lifespan='on'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not getattr(server, 'started', False):
        time.sleep(0.05)

    operator = requests.Session()
    token = re.search(r'name="csrftoken" value="([^"]+)"',
                      operator.get(base + '/login').text).group(1)
    operator.post(base + '/login', data={'username': 'admin', 'password': 'admin',
                                         'csrftoken': token})
    url = f'{base}{ed.URL_BASE}/{lab.code}'
    code = ot.participant_codes(lab)[2]

    def page_seconds_during_press():
        """Press in a thread, and meanwhile time a participant's real page load."""
        token = operator.get(url + dd.PLAN_SUFFIX).json()['csrf']
        answers = []
        presser = threading.Thread(target=lambda: answers.append(
            operator.post(url + dd.DOWNLOAD_SUFFIX, data={'csrftoken': token}).json()))
        started = time.time()
        presser.start()
        time.sleep(0.4)
        loaded = time.time()
        page = requests.get(f'{base}/InitializeParticipant/{code}', headers=DESKTOP,
                            timeout=60)
        seconds = time.time() - loaded
        presser.join()
        return seconds, time.time() - started, page.status_code, answers[0]

    try:
        real_temp = dd._write_temp

        def slow_disk(sub, data):
            time.sleep(1.0)
            return real_temp(sub, data)
        dd._write_temp = slow_disk
        try:
            with Folder():
                seconds, total, status, answer = page_seconds_during_press()
        finally:
            dd._write_temp = real_temp
        check(answer['ok'] is True and total >= 3.0,
              f'a disk taking 3 s: the press took {total:.1f} s and worked')
        check(status == 200 and seconds < 1.0,
              f'and the participant page did not wait for it ({seconds:.2f} s)')

        real_read = export.get_rows_for_wide_csv

        def slow_read(session_code):
            time.sleep(1.5)
            return real_read(session_code)
        export.get_rows_for_wide_csv = slow_read
        try:
            with Folder():
                seconds, total, status, answer = page_seconds_during_press()
        finally:
            export.get_rows_for_wide_csv = real_read
        check(answer['ok'] is True and status == 200 and seconds >= 0.8,
              f'the same page behind a slow READ waits ({seconds:.2f} s): so the read '
              f'is under the lock, and this measurement can see a lock being held')
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def section_no_data(admin, lab, prolific):
    section('G7. a session with no participants, then an empty database')
    from otree.database import DBSession
    from otree.models import Participant, Session
    s = DBSession()
    empty = Session(code='emptysess', config={'name': 'lab', 'app_sequence': ['before']},
                    num_participants=0)
    s.add(empty)
    s.commit()
    s.close()
    with Folder() as folder:
        plan = admin.get(f'{ed.URL_BASE}/emptysess{dd.PLAN_SUFFIX}').json()
        check(plan['ok'] and any('no participants' in w for w in plan['warnings']),
              'a session with no participants: the plan says so')
        check(plan['session_participants'] == 0 and plan['participants'] > 0,
              'while the others still count')
        check(plan['sessions'] >= 3, 'and every session is counted')
        check(press(admin, 'emptysess')['ok'] is True and len(tree(folder)) == 3,
              'the files still cover the others')

    answer = admin.get(f'{ed.URL_BASE}/nosuchsession{dd.PLAN_SUFFIX}')
    check(answer.status_code == 404 and answer.json()['problem'] == 'session',
          'a session that does not exist: a clear refusal')

    # An empty database, in the middle of a live process. The tables are cleared
    # with foreign keys off, on the app's own connection. Last section that needs
    # data, so nothing after it depends on these rows.
    from sqlalchemy import inspect, text
    from otree.database import engine
    with engine.begin() as conn:
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        for table in inspect(engine).get_table_names():
            if table != 'otree_session':
                conn.execute(text(f'DELETE FROM "{table}"'))
        conn.execute(text('PRAGMA foreign_keys=ON'))
    with Folder() as folder:
        plan = admin.get(f'{ed.URL_BASE}/emptysess{dd.PLAN_SUFFIX}').json()
        check(plan['ok'] is False and plan['problem'] == 'no_data'
              and 'no participant data' in plan['message'],
              'no participants anywhere: the plan says so')
        answer = press(admin, 'emptysess')
        check(answer['ok'] is False and answer['problem'] == 'no_data',
              'and the POST says so')
        check(tree(folder) == [], 'no files were made')


def section_drift(admin, lab):
    section('K. drift: loud on the button, quiet at boot')
    check(dd.download_is_installed(), 'the routes are installed at boot')
    check(dd.install_download_route() == dd.otree_routes.ALREADY,
          'installing again is a no-op')

    # The boot-time wrapper never raises, even on the install's own drift raise.
    real_install = dd.otree_routes.install

    def drifted(*args, **kwargs):
        raise RuntimeError('otree.urls.routes moved')
    dd.otree_routes.install = drifted
    try:
        check(dd.install_download_route_or_note() == 'drift',
              'a drift raise at boot is swallowed and reported')
        problems = dd.launch_problems()
        check(any('moved' in str(p) for p in problems),
              'and the launch check reports it')
    finally:
        dd.otree_routes.install = real_install
    check(ed.dashboard_is_installed(), 'the dashboard is not affected')

    # A login machinery that drifted must install nothing, so nothing is open.
    view = ed._checked_admin_view()
    real = view.__dict__['_is_logged_in']
    del view._is_logged_in
    try:
        raised = False
        try:
            dd._build_routes()
        except RuntimeError:
            raised = True
        check(raised, 'AdminView without its login: the routes refuse to be built')
    finally:
        view._is_logged_in = real

    # oTree's export moved: said on the button, naming it.
    from otree import export
    real_export = export.get_rows_for_wide_csv
    token = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()['csrf']
    del export.get_rows_for_wide_csv
    try:
        with Folder() as folder:
            plan = admin.get(f'{ed.URL_BASE}/{lab.code}{dd.PLAN_SUFFIX}').json()
            check(plan['ok'] is False and 'get_rows_for_wide_csv' in plan['message'],
                  'export gone: the confirm step says so')
            answer = press(admin, lab.code, token)
            check(answer['ok'] is False
                  and 'get_rows_for_wide_csv' in answer['message'],
                  f'export gone: the button says so ({answer["message"][:70]}...)')
            check(tree(folder) == [], 'nothing on disk')
        check(any('get_rows_for_wide_csv' in str(p) for p in dd.launch_problems()),
              'and the launch check reports it')
    finally:
        export.get_rows_for_wide_csv = real_export

    for label, bad in (('not a list of rows', 'hello'),
                       ('no participant.code', [['a', 'b'], [1, 2]]),
                       ('rows of another length',
                        [['participant.code', 'b'], [1, 2, 3]])):
        raised = False
        try:
            dd.check_rows(bad)
        except dd.ExportDrift:
            raised = True
        check(raised, f'the shape check catches {label}')
    for empty in ([[]], []):
        raised = False
        try:
            dd.check_rows(empty)
        except dd.NoData:
            raised = True
        check(raised, f'{empty!r} is no data, not drift')

    section('K2. the launch check and the folder')
    check(dd.launch_problems() == [], 'clean with the variable unset')
    with Folder():
        check(dd.launch_problems() == [], 'clean with an existing folder')
    os.environ[ENV] = os.path.join(tempfile.gettempdir(), 'download_typo_no_such')
    try:
        check(any(ENV in p[0] for p in dd.launch_problems()),
              'a folder that does not exist fails the launch check')
    finally:
        os.environ.pop(ENV, None)

    section('K3. pure on import')
    code = ('import sys, data_download, data_columns;'
            'bad=[m for m in ("otree","pandas","starlette") if m in sys.modules];'
            'print(bad)')
    import subprocess
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          cwd=REPO_ROOT)
    check(done.stdout.strip() == '[]',
          f'importing it drags in neither oTree nor pandas ({done.stdout.strip()} '
          f'{done.stderr.strip()[-120:]})')
    code = ('import ast;t=ast.parse(open("data_download.py").read());'
            'print(any("pandas" in getattr(n,"name","") or "pandas" == getattr(n,"module","")'
            ' for s in ast.walk(t) if isinstance(s,(ast.Import,ast.ImportFrom))'
            ' for n in ([s] if isinstance(s,ast.ImportFrom) else s.names)))')
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          cwd=REPO_ROOT)
    check(done.stdout.strip() == 'False', 'and no line of it imports pandas')


def main():
    lab = ot.create_session('lab', num_participants=3,
                            modified_session_config_fields={'lab_session': '217b'})
    prolific = ot.create_session('prolific', num_participants=3)
    codes = ot.participant_codes(lab)
    print('walking participants through the real pages...')
    assert walk(codes[0], iban=IBAN) == 'Results'
    assert walk(codes[1], iban=DE_IBAN, bic=BIC) == 'Results'
    pro_codes = ot.participant_codes(prolific)
    assert walk(pro_codes[0], label=PROLIFIC_ONE, url_label=PROLIFIC_ONE) == 'Results'

    admin = admin_client()
    section_names()
    section_folder_setting()
    section_walls(lab)
    section_three_files(admin, lab, prolific)
    section_refused_claim(admin, prolific)
    section_never_overwrite(admin, lab)
    section_failing_loudly(admin, lab)
    section_no_data_leaks(admin, lab)
    section_read_only(admin, lab)
    section_browser_mode(admin, lab)
    section_drift(admin, lab)
    section_lock(lab)
    section_no_data(admin, lab, prolific)

    print('\n=== SUMMARY ===')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED')
        for m in _failures:
            print(f'    - {m}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
