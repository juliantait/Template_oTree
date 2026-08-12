"""EXPERIMENTER DASHBOARD tests (experimenter_dashboard.py).

THE TWO TESTS THAT JUSTIFY RUNNING THE DASHBOARD IN-PROCESS AT ALL, proved
rather than asserted (sections B and C):

  B. A request with NO ADMIN LOGIN never reaches the dashboard — it is
     redirected to oTree's own /login, for the page, the data endpoint and
     the index alike. A participant mid-study (their own cookies, their own
     pages working) is exactly such a request.
  C. A dashboard handler that RAISES breaks the dashboard, never the study:
     with the data layer monkeypatched to throw, a participant completes
     pages normally over the same app, the dashboard page returns its error
     panel (HTTP 200, no oTree 500 machinery), and the data endpoint returns
     ok:false JSON. Un-patched, everything recovers without a restart.

Around them:

  A. Install discipline (identity.py's): installed at boot from
     outro/__init__.py, idempotent, QUIET when otree.urls is not importable,
     LOUD (a raise) on version drift — and the boot-time wrapper
     (install_dashboard_route_or_note) swallows even that raise, because a
     boot must never die over an operator page.
  D. The rows tell the truth: participants walked over real HTTP (the
     in-process ASGI client) to different stages read back with the right
     step, task round, quiz cell, instructions time, terminal state,
     earnings and amber/stall flag.
  E. STRICTLY READ-ONLY: a byte-identical dump of every participant row
     before and after dashboard reads.

Run: python tests/dashboard_test.py   (boots oTree in-process; no server)

NB AUTH_LEVEL is set to STUDY before boot — oTree reads OTREE_AUTH_LEVEL at
import, so the whole file runs in the locked-down mode a real launch uses.
Participant pages are ALWAYS_UNRESTRICTED in oTree, so the walks still work.
"""
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, os.path.dirname(_TESTS_DIR))

# Before boot: oTree freezes AUTH_LEVEL at import (see module docstring).
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

from otree_inprocess import boot, path_of, page_name_of

ot = boot(production=True)          # MUST come before any app import

import experimenter_dashboard as ed

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


URL = ed.URL_BASE

# A real phone User-Agent (device_gate_test.py carries the full battery; one
# is enough here — this file tests the dashboard's reporting, not the gate).
PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 '
            'Mobile/15E148 Safari/604.1')
# The in-process TestClient's default User-Agent ('testclient') classifies as
# 'unknown', which a computers-only allow-list screens out — so everyone in
# the D2 session who is NOT meant to be screened must arrive as a computer.
DESKTOP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
              'Safari/537.36')
DESKTOP = {'User-Agent': DESKTOP_UA}


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


def walk(client, code, quiz_answers, stop_after=None, quiz_posts=None,
         max_steps=120, headers=None):
    """Walk a participant over the in-process app.

    stop_after: page name — stop once that page has been SUBMITTED.
    quiz_posts: list of payloads to POST on successive quiz renders (wrong
                answers first, e.g. to fail deliberately); afterwards the
                correct answers are used.
    """
    kw = dict(headers=headers) if headers else {}
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True,
                      **kw)
    visited, statuses = [], [resp.status_code]
    quiz_posts = list(quiz_posts or [])
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None:
            break
        visited.append(page)
        if page in ('Results', 'Ended'):
            break
        if page == 'quiz' and quiz_posts:
            data = quiz_posts.pop(0)
        else:
            data = payload_for(page, quiz_answers)
        resp = client.post(path_of(resp), data=data, allow_redirects=True,
                           **kw)
        statuses.append(resp.status_code)
        if stop_after and page == stop_after:
            break
    return visited, statuses, resp


def admin_client():
    """A logged-in operator (oTree's own login flow, nothing invented)."""
    c = ot.client()
    r = c.get('/login')
    token = re.search(r'name="csrftoken" value="([^"]+)"', r.text).group(1)
    c.post('/login', data={'username': 'admin', 'password': 'admin',
                           'csrftoken': token}, allow_redirects=False)
    return c


def rows_by_code(client, session):
    data = client.get(f'{URL}/{session.code}/data').json()
    assert data.get('ok'), data
    return data, {r['code']: r for r in data['rows'] if not r.get('error')}


def participant_dump():
    """A canonical dump of every participant row — the read-only witness."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        return [
            (p.code, p.label, p._index_in_pages, p._max_page_index,
             p._current_page_name, p._current_app_name, p._round_number,
             p._last_page_timestamp, p.visited, repr(dict(p.vars)))
            for p in s.query(Participant).order_by(Participant.id)
        ]
    finally:
        s.close()


def set_participant(code, **fields):
    """Test-side WRITE helper (the dashboard itself never writes): plant vars
    or columns to simulate states whose full flows other files already cover
    (tab monitor: full_journey_test; stall: nobody waits 5 minutes here)."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        for name, value in fields.items():
            if name.startswith('vars.'):
                p.vars[name[5:]] = value    # MutableDict: setitem flags dirty
            else:
                setattr(p, name, value)
        s.commit()
    finally:
        s.close()


def main():
    from intro.quiz_items import QUIZ_ITEMS
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}
    first = QUIZ_ITEMS[0]
    wrong = dict(correct)
    wrong[first['field']] = next(c for c in first['choices']
                                 if c != first['answer'])

    # ------------------------------------------------------------------ A
    section('A. install discipline (identity.py rules)')
    check(ed.dashboard_is_installed(),
          'routes installed at boot by outro/__init__.py')
    check(ed.install_dashboard_route() == ed.ALREADY,
          'second install is an idempotent no-op (ALREADY)')
    check(ed.assert_dashboard_route() == ed.ALREADY,
          'assert_dashboard_route passes when installed')

    real_import = ed._import_urls
    ed._import_urls = lambda: (_ for _ in ()).throw(ImportError('simulated'))
    try:
        outcome = ed.install_dashboard_route()   # must not raise
        check(outcome == ed.NOT_IMPORTABLE,
              'not-importable-yet is QUIET (returned, not raised)')
    finally:
        ed._import_urls = real_import

    class _Drifted:                     # imported fine, wrong shape
        routes = None
    ed._import_urls = lambda: _Drifted
    try:
        try:
            ed.install_dashboard_route()
            check(False, 'version drift raises (LOUD)')
        except RuntimeError as exc:
            check('drifted' in str(exc).lower() or 'routes' in str(exc),
                  'version drift raises (LOUD), naming the drifted symbol')
        # ... and the BOOT-TIME wrapper survives even that raise:
        check(ed.install_dashboard_route_or_note() == 'drift',
              'boot-time wrapper swallows the drift raise (boot survives)')
    finally:
        ed._import_urls = real_import

    # ------------------------------------------------------------------ B
    section('B. PROOF 1: no login, no dashboard — ever')
    lab = ot.create_session('test', num_participants=7)
    codes = ot.participant_codes(lab)

    anon = ot.client()
    for path in (URL, f'{URL}/{lab.code}', f'{URL}/{lab.code}/data'):
        r = anon.get(path, allow_redirects=False)
        check(r.status_code == 302
              and r.headers.get('location', '').endswith('/login'),
              f'unauthenticated GET {path} -> 302 to oTree /login '
              f'(got {r.status_code})')

    # A PARTICIPANT mid-study: their cookies open their own pages, and still
    # not the dashboard.
    pclient = ot.client()
    visited, statuses, _ = walk(pclient, codes[0], correct,
                                stop_after='welcome')
    check(all(s == 200 for s in statuses) and 'welcome' in visited,
          'participant client walks its own pages fine (200s)')
    r = pclient.get(f'{URL}/{lab.code}/data', allow_redirects=False)
    check(r.status_code == 302 and '/login' in r.headers.get('location', ''),
          'the SAME participant client is turned away from the dashboard')
    leaked = anon.get(f'{URL}/{lab.code}/data', allow_redirects=True)
    check(codes[0] not in leaked.text,
          'following the redirect leaks no participant data (login page)')

    admin = admin_client()
    r = admin.get(f'{URL}/{lab.code}')
    check(r.status_code == 200 and 'tl-header' in r.text,
          'logged-in operator gets the dashboard page (200)')
    r = admin.post(f'{URL}/{lab.code}/data', data={})
    check(r.status_code == 405,
          f'POST is refused (read-only endpoint, got {r.status_code})')

    # ------------------------------------------------------------------ C
    section('C. PROOF 2: a dashboard bug breaks the dashboard, not the study')
    real_snapshot = ed.session_snapshot
    real_page = ed._page_html
    ed.session_snapshot = lambda session: (_ for _ in ()).throw(
        RuntimeError('injected dashboard bug'))
    ed._page_html = lambda session: (_ for _ in ()).throw(
        RuntimeError('injected dashboard bug'))
    try:
        # The study: a participant walks pages NORMALLY while the dashboard
        # is broken, over the very same app instance. (Stopping after the
        # welcome submit leaves them ON the instructions page — which is
        # exactly where section D expects to find this row.)
        visited, statuses, _ = walk(ot.client(), codes[1], correct,
                                    stop_after='welcome')
        check(all(s == 200 for s in statuses)
              and 'welcome' in visited,
              f'participant completed pages normally while the dashboard '
              f'was broken (statuses {sorted(set(statuses))})')

        # The dashboard: its own error panel, not oTree's 500 machinery.
        r = admin.get(f'{URL}/{lab.code}')
        check(r.status_code == 200
              and 'Experimenter dashboard error' in r.text
              and 'unaffected' in r.text,
              'dashboard page renders the error panel (200), not a 500')
        r = admin.get(f'{URL}/{lab.code}/data')
        check(r.status_code == 200 and r.json().get('ok') is False
              and 'injected dashboard bug' in r.json().get('error', ''),
              'data endpoint degrades to ok:false JSON naming the error')
    finally:
        ed.session_snapshot = real_snapshot
        ed._page_html = real_page

    r = admin.get(f'{URL}/{lab.code}/data')
    check(r.status_code == 200 and r.json().get('ok') is True,
          'dashboard recovers the moment the bug is gone (no restart)')

    # ------------------------------------------------------------------ D
    section('D. rows reflect a real session (lab config, 3 rounds)')
    # codes[0]: stopped after consent (entry). codes[1]: on instructions.
    walk(ot.client(), codes[2], correct, stop_after='quiz')          # into task
    walk(ot.client(), codes[3], correct)                             # finish
    walk(ot.client(), codes[4], correct, stop_after='welcome',
         quiz_posts=[wrong])                                         # (see below)
    # codes[4]: one wrong quiz attempt, still on the quiz.
    c5 = ot.client()
    walk(c5, codes[4], correct, quiz_posts=[wrong], stop_after='instructing')
    r = c5.get(f'/InitializeParticipant/{codes[4]}', allow_redirects=True)
    c5.post(path_of(r), data=wrong, allow_redirects=True)            # 1 wrong

    # codes[6]: arrives (page render) but never submits — at entry, present.
    ot.client().get(f'/InitializeParticipant/{codes[6]}',
                    allow_redirects=True)

    data, rows = rows_by_code(admin, lab)
    check(data['rounds_total'] == 3,
          f"rounds_total is this session's count (3, got {data['rounds_total']})")
    check(data['poll_seconds'] >= 2, 'poll interval floor is 2s')

    r0 = rows[codes[5]]
    check(r0['arrived'] is False and r0['step'] == 'entry'
          and r0['entry_only'] is True,
          'never-arrived participant: entry step, de-emphasised (entry_only)')
    # ... but ARRIVED-at-entry is a present person and is NOT dimmed
    # (deliberate correction, 2026-08-12: the dim means "nobody is here").
    r6 = rows[codes[6]]
    check(r6['arrived'] is True and r6['step'] == 'entry'
          and r6['entry_only'] is False,
          'arrived participant still at entry is NOT entry_only (not dimmed)')
    r1 = rows[codes[1]]
    check(r1['step'] == 'instructions' and r1['entry_only'] is False,
          f"participant on instructions shows step=instructions "
          f"(got {r1['step']})")
    check(r1['instructions_live'] is True
          and isinstance(r1['instructions_seconds'], int),
          'time-on-instructions runs LIVE while they read')
    r2 = rows[codes[2]]
    check(r2['step'] == 'task' and r2['task_round'] == 1,
          f"participant in the task carries the round in the marker "
          f"(1 of 3; got step={r2['step']}, round={r2['task_round']})")
    check(r2['quiz']['state'] == 'green' and r2['quiz']['display'] == 1,
          "first-try quiz shows GREEN 1 (1 = passed first attempt)")
    check(isinstance(r2['instructions_seconds'], int)
          and r2['instructions_live'] is False,
          'instructions time is fixed once instructions_done is stamped')
    r3 = rows[codes[3]]
    check(r3['step'] == 'done' and r3['finished'] is True,
          f"finished participant: step=done (got {r3['step']})")
    check(isinstance(r3['earnings'], float) and r3['earnings'] > 0,
          f"earnings shown once known (got {r3['earnings']})")
    r4 = rows[codes[4]]
    check(r4['quiz']['state'] == 'progress'
          and r4['quiz']['attempts_wrong'] == 1,
          f"one wrong quiz attempt fills the cell (got {r4['quiz']})")

    section('D2. terminal states (prolific config)')
    pro = ot.create_session(
        'prolific', num_participants=4,
        modified_session_config_fields={'allowed_devices': 'computer'})
    pcodes = ot.participant_codes(pro)

    # declined consent
    c = ot.client()
    r = c.get(f'/InitializeParticipant/{pcodes[0]}', allow_redirects=True,
              headers=DESKTOP)
    c.post(path_of(r), data={'consent': 'False', 'is_mobile': '',
                             'device_info_json': '', 'participant_id_url': ''},
           allow_redirects=True, headers=DESKTOP)
    # comprehension DQ (threshold 3, comprehension_dq on for prolific)
    walk(ot.client(), pcodes[1], correct, quiz_posts=[wrong, wrong, wrong],
         headers=DESKTOP)
    # device screen-out (phone UA against a computers-only allow-list)
    r = ot.client().get(f'/InitializeParticipant/{pcodes[2]}',
                        allow_redirects=True,
                        headers={'User-Agent': PHONE_UA})
    # tab monitor: plant the authoritative flags (the full live flow is
    # full_journey_test.py's job); mid-task stamps so 'reached' is the task.
    walk(ot.client(), pcodes[3], correct, stop_after='quiz', headers=DESKTOP)
    set_participant(pcodes[3], **{'vars.ai_safety_disqualified': True,
                                  'vars.exit_code': -3})

    data, rows = rows_by_code(admin, pro)
    t0 = rows[pcodes[0]]
    check(t0['terminal'] == 'no_consent' and t0['step'] == 'entry'
          and t0['terminal_emoji'],
          f"declined consent: terminal at ENTRY with its emoji "
          f"(got {t0['terminal']}@{t0['step']})")
    t1 = rows[pcodes[1]]
    check(t1['terminal'] == 'comprehension' and t1['step'] == 'quiz',
          f"comprehension DQ: terminal at QUIZ (got {t1['terminal']}"
          f"@{t1['step']})")
    check(t1['quiz']['state'] == 'red',
          f"comprehension DQ quiz cell is RED (got {t1['quiz']['state']})")
    t2 = rows[pcodes[2]]
    check(t2['terminal'] == 'screened_out' and t2['step'] == 'entry',
          f"device screen-out: terminal at ENTRY (got {t2['terminal']}"
          f"@{t2['step']})")
    check(t2['entry_only'] is False,
          'a screened-out row is NEVER hidden by the entry filter')
    t3 = rows[pcodes[3]]
    check(t3['terminal'] == 'tab_monitor' and t3['step'] == 'task',
          f"tab-monitor DQ mid-task: emoji fills the marker at TASK "
          f"(got {t3['terminal']}@{t3['step']})")
    emojis = {rows[pcodes[i]]['terminal_emoji'] for i in range(4)}
    check(len(emojis) == 4, 'four terminal states, four distinct emojis')

    section('D3. amber (stall) — configurable threshold')
    check(ed.stall_seconds() == 300,
          'stall threshold defaults to 300s (5 minutes)')
    import time as _time
    set_participant(codes[1],
                    _last_page_timestamp=int(_time.time()) - 400)
    data, rows = rows_by_code(admin, lab)
    check(rows[codes[1]]['stalled'] is True
          and rows[codes[1]]['seconds_on_page'] >= 400,
          '400s on one page turns the row amber (stalled)')
    check(rows[codes[3]]['stalled'] is False,
          'a finished row can never stall')
    import settings as user_settings
    user_settings.DASHBOARD_STALL_SECONDS = 1000
    try:
        data, rows = rows_by_code(admin, lab)
        check(rows[codes[1]]['stalled'] is False,
              'raising DASHBOARD_STALL_SECONDS in settings takes effect '
              'without touching dashboard code')
    finally:
        del user_settings.DASHBOARD_STALL_SECONDS

    # ------------------------------------------------------------------ E
    section('E. strictly read-only')
    before = participant_dump()
    admin.get(f'{URL}/{lab.code}/data')
    admin.get(f'{URL}/{pro.code}/data')
    admin.get(f'{URL}/{lab.code}')
    admin.get(URL)
    after = participant_dump()
    check(before == after,
          'byte-identical participant rows after page+data+index reads '
          f'({len(before)} rows compared)')

    # The byte comparison alone cannot catch a SAME-BYTES rewrite — which is
    # exactly what reading the pp.vars PROPERTY would cause (its getter flags
    # the pickled column dirty; see _participant_row's docstring). So also
    # prove at the ORM level that building a row leaves the object clean.
    from sqlalchemy import inspect as sa_inspect
    from otree.database import DBSession
    from otree.models import Session as OTSession
    import time as _time
    s = DBSession()
    try:
        sess = s.query(OTSession).filter_by(code=lab.code).one()
        ctx = ed._session_context(sess)
        pp = sess.pp_set.order_by('id').first()
        ed._participant_row(pp, ctx, _time.time())
        check(not sa_inspect(pp).modified,
              'building a row marks NOTHING dirty (no same-bytes rewrite '
              'of the vars column on every poll)')
    finally:
        s.close()

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
