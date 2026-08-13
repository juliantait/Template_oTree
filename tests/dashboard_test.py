"""EXPERIMENTER DASHBOARD tests (experimenter_dashboard.py).

THE TWO TESTS THAT JUSTIFY RUNNING THE DASHBOARD IN-PROCESS AT ALL, proved
rather than asserted (sections B and C):

  B. A request with NO ADMIN LOGIN never reaches the dashboard — it is
     redirected to oTree's own /login, for the page, the data endpoint and
     the index alike. A participant mid-study (their own cookies, their own
     pages working) is exactly such a request.
  C. A dashboard handler that RAISES breaks the dashboard, never the study:
     with the data layer monkeypatched to throw, the dashboard page returns its
     error panel (HTTP 200, no oTree 500 machinery) and the data endpoint
     returns ok:false JSON; a participant THEN completes a page, and another
     completes a WHOLE journey, in a process where the dashboard has already
     blown up. Un-patched, everything recovers without a restart. One poisoned
     ROW leaves the table ok:true with every other row live.

     READ THE ORDERING NOTE IN SECTION C BEFORE TRUSTING THIS. The failing
     dashboard requests come FIRST on purpose, and the participant checks are a
     regression guard rather than proof of this module's wrapper — participant
     survival rests partly on oTree's own NEW_IDMAP_EACH_REQUEST, which C0
     pins so a future oTree version cannot quietly change what C means. The
     checks that fail when the wrapper is deleted are the error-panel ones.

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
    # 8 participants, every one of them spoken for: codes[0] stops at consent,
    # [1] sits on the instructions, [2] is mid-task, [3] finishes, [4] has a
    # wrong quiz attempt, [5] never arrives, [6] arrives and submits nothing,
    # and [7] is section C's full journey through a BROKEN dashboard. Adding a
    # scenario means adding a participant, not borrowing one.
    lab = ot.create_session('test', num_participants=8)
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
    # ORDER MATTERS IN THIS SECTION, AND IT IS THE WHOLE POINT (reordered
    # 2026-08-12 after the conformance audit).
    #
    # This used to walk the participant FIRST and only then hit the broken
    # dashboard — so at the moment the participant walked, the handlers were
    # patched to raise but nothing had raised yet, and the test never asked the
    # question it claimed to answer. The failing dashboard requests now come
    # first, so the participant walks in a process where a dashboard handler HAS
    # already blown up: same app instance, same DB session machinery, same
    # global commit lock.
    #
    # AND A HONEST WARNING ABOUT WHAT THIS PROVES. A participant surviving is
    # NOT, on its own, evidence that OUR wrapper is what saved them. oTree sets
    # `NEW_IDMAP_EACH_REQUEST = True` (otree/database.py), so
    # CommitTransactionMiddleware starts every request with `db.new_session()`
    # and an escaping exception — which skips BOTH commit and rollback, since it
    # escapes the middleware's `async with` — cannot poison the NEXT request.
    # Deleting the handler wrapper entirely leaves these participant checks
    # passing (verified by mutation, audit §3). So:
    #   * the participant checks below are a REGRESSION GUARD on the property
    #     that a broken dashboard is survivable at all, not proof of our code;
    #   * the load-bearing proof of OUR wrapper is the error-panel and
    #     ok:false checks, which DO fail when it is removed;
    #   * C0 below pins the oTree property we are leaning on, so a future oTree
    #     version dropping it is a RED TEST here rather than an invisible change
    #     of what this section means.
    from otree.database import NEW_IDMAP_EACH_REQUEST
    check(NEW_IDMAP_EACH_REQUEST is True,
          'C0: oTree still starts each request with a fresh DB session '
          '(NEW_IDMAP_EACH_REQUEST) — if this ever goes False, an escaping '
          'dashboard exception could reach a participant request and the '
          'handler wrapper becomes the ONLY thing standing between them')

    real_snapshot = ed.session_snapshot
    real_page = ed._page_html
    ed.session_snapshot = lambda session: (_ for _ in ()).throw(
        RuntimeError('injected dashboard bug'))
    ed._page_html = lambda session: (_ for _ in ()).throw(
        RuntimeError('injected dashboard bug'))
    try:
        # 1. THE DASHBOARD BREAKS FIRST — its own error panel, not oTree's 500
        #    machinery. THIS is the check that fails if the wrapper is removed.
        r = admin.get(f'{URL}/{lab.code}')
        check(r.status_code == 200
              and 'Experimenter dashboard error' in r.text
              and 'unaffected' in r.text,
              'dashboard page renders the error panel (200), not a 500')
        r = admin.get(f'{URL}/{lab.code}/data')
        check(r.status_code == 200 and r.json().get('ok') is False
              and 'injected dashboard bug' in r.json().get('error', ''),
              'data endpoint degrades to ok:false JSON naming the error')

        # 2. ONLY NOW does a participant use the study, in a process where the
        #    dashboard has already raised twice. (Stopping after the welcome
        #    submit leaves them ON the instructions page — which is exactly
        #    where section D expects to find this row.)
        visited, statuses, _ = walk(ot.client(), codes[1], correct,
                                    stop_after='welcome')
        check(all(s == 200 for s in statuses)
              and 'welcome' in visited,
              f'participant completes pages normally AFTER the dashboard has '
              f'blown up (statuses {sorted(set(statuses))})')

        # 3. And a WHOLE journey, not just one page: a broken dashboard must not
        #    strand somebody halfway either.
        visited, statuses, _ = walk(ot.client(), codes[7], correct)
        check(all(s == 200 for s in statuses) and 'Results' in visited,
              f'a full participant journey finishes with the dashboard still '
              f'broken (statuses {sorted(set(statuses))}, ended on '
              f'{visited[-1] if visited else "?"})')
    finally:
        ed.session_snapshot = real_snapshot
        ed._page_html = real_page

    r = admin.get(f'{URL}/{lab.code}/data')
    check(r.status_code == 200 and r.json().get('ok') is True,
          'dashboard recovers the moment the bug is gone (no restart)')

    # ---- C4: THE PER-ROW WRAPPER, which nothing asserted before -------------
    # The module's rule 2 is not only "the handler is wrapped" but "each ROW is
    # wrapped, so one poisoned row renders as an error row instead of killing
    # the whole table". That half had no test at all until now — and
    # rows_by_code() below FILTERS ERROR ROWS OUT, so it could never have caught
    # it. Poison exactly one row and check the other rows survive it.
    real_row = ed._participant_row
    _calls = {'n': 0}

    def _poison_second_row(pp, ctx, now):
        _calls['n'] += 1
        if _calls['n'] == 2:            # exactly one row of the session
            raise RuntimeError('poisoned row')
        return real_row(pp, ctx, now)

    ed._participant_row = _poison_second_row
    try:
        payload = admin.get(f'{URL}/{lab.code}/data').json()
        rows_all = payload.get('rows', [])
        errs = [r for r in rows_all if r.get('error')]
        live = [r for r in rows_all if not r.get('error')]
        check(payload.get('ok') is True,
              f"one poisoned row leaves the table ok:true "
              f"(got {payload.get('ok')})")
        check(len(errs) == 1 and len(live) == len(rows_all) - 1,
              f'exactly ONE error row, every other row still live '
              f'({len(errs)} error, {len(live)} live of {len(rows_all)})')
        check(bool(errs) and bool(errs[0].get('code')),
              'the error row still carries a participant code the operator '
              'can act on (not a blank row)')
        r = admin.get(f'{URL}/{lab.code}')
        check(r.status_code == 200 and 'Experimenter dashboard error'
              not in r.text,
              'the dashboard PAGE is unaffected by a poisoned row (200, the '
              'real page, not the error panel)')
    finally:
        ed._participant_row = real_row

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

    section('D4. the entry-block boundary (instructions time)')
    # THE AI-SAFETY AGREEMENT PAGE MUST NOT BE BILLED TO THE INSTRUCTIONS.
    # It sits between confirm_id and instructions_done, so before it was
    # stamped its dwell time landed in the instructions column — and only for
    # Prolific, because the lab never shows the page. That made one column mean
    # two different things depending on the study type (conformance audit,
    # 2026-08-12). The real sleep below is the only way to test it: with no
    # measurable dwell anywhere, a wrong start stamp and a right one give the
    # same answer.
    DWELL = 3
    pro2 = ot.create_session('prolific', num_participants=2)
    dwell_code = ot.participant_codes(pro2)[0]
    c = ot.client()
    resp = c.get(f'/InitializeParticipant/{dwell_code}', allow_redirects=True,
                 headers=DESKTOP)
    saw_agreement = False
    for _ in range(12):
        page = page_name_of(path_of(resp))
        if page is None or page == 'quiz':
            break
        if page == 'AISafetyAgree':
            saw_agreement = True
            _time.sleep(DWELL)          # the ONLY dwell in this walk
        resp = c.post(path_of(resp), data=payload_for(page, correct),
                      allow_redirects=True, headers=DESKTOP)
    check(saw_agreement,
          'the prolific flow really does show the AI-safety agreement page '
          '(otherwise this section proves nothing)')
    check('ai_safety_agreed' in (ot.participant_vars(dwell_code)
                                 .get('stage_timestamps') or {}),
          'leaving the agreement page stamps ai_safety_agreed')
    _, drows = rows_by_code(admin, pro2)
    instr = drows[dwell_code]['instructions_seconds']
    check(instr is not None and instr < DWELL,
          f'{DWELL}s on the AGREEMENT page and ~0s on the instructions reports '
          f'< {DWELL}s of instructions time (got {instr}s) — the agreement '
          f'page is no longer billed to the instructions')

    section('D5. an app the dashboard has never heard of is VISIBLE')
    # A study copied from this template WILL add an app, and until 2026-08-12
    # such a participant was rendered at Entry, indistinguishable from somebody
    # on the consent page and from somebody who had barely started. Plant the
    # cursor a study's new app would write and check the dashboard says so
    # instead of guessing.
    set_participant(codes[2], _current_app_name='a_study_added_this',
                    _current_page_name='SomeNewPage')
    _, urows = rows_by_code(admin, lab)
    u = urows[codes[2]]
    check(u['step'] == ed.UNMAPPED_STEP,
          f"a page in an unrecognised app is NOT reported as a timeline step "
          f"(got step={u['step']!r})")
    check(u['step'] != 'entry',
          'and specifically NOT as entry — the collapse this replaced')
    check(u['unmapped_app'] == 'a_study_added_this',
          f"the row names the app the operator must add to APP_STEPS "
          f"(got {u['unmapped_app']!r})")
    check(ed.UNMAPPED_STEP not in ed.STEPS,
          'the sentinel is not one of the six steps, so no marker is drawn')
    # ... while a known app in the same position still maps normally, i.e. the
    # new branch did not swallow the ordinary case.
    set_participant(codes[2], _current_app_name='main',
                    _current_page_name='GameStart')
    _, krows = rows_by_code(admin, lab)
    check(krows[codes[2]]['step'] == 'task'
          and krows[codes[2]]['unmapped_app'] is None,
          f"a KNOWN app still maps to its step with no unmapped flag "
          f"(got {krows[codes[2]]['step']!r})")

    section('D6. the six steps are defined ONCE and everything derives from it')
    # THE ANTI-DRIFT GUARD (added 2026-08-12 with the single-sourcing). The step
    # list used to be stated four times — the STEPS tuple, an unrendered
    # STEP_LABELS dict, the six <span>s in the table header, and the STEPS array
    # in the page's JavaScript — plus two more copies of the step COUNT in the
    # CSS (the grid's track count and the connector's half-track inset). Renaming
    # a step meant finding six places, and missing one gave a header that
    # disagreed with the data with nothing going red. These checks fail if any
    # of them is ever restated instead of derived.
    import json as _json
    check(ed.STEPS == tuple(ed.STEP_LABELS),
          f'STEPS is derived from STEP_LABELS, not typed alongside it '
          f'({ed.STEPS})')

    page = admin.get(f'{URL}/{lab.code}').text
    header = re.search(r'<div class="tl-header">(.*?)</div>', page, re.S)
    rendered = re.findall(r'<span>(.*?)</span>', header.group(1)) if header else []
    check(rendered == list(ed.STEP_LABELS.values()),
          f'the rendered header cells ARE STEP_LABELS, in order (got {rendered})')

    js = re.search(r'var STEPS = (\[[^\]]*\]);', page)
    # Parsed DEFENSIVELY, and single quotes normalised on purpose: a hand-typed
    # JS array (which is what a regression here looks like) is not valid JSON,
    # and this check must report the drift, not die on it. An unparseable value
    # is reported as itself. A test that fails by crashing tells you the test
    # broke, not the code — that criticism was made of section C, so it applies
    # here too.
    raw = js.group(1) if js else None
    try:
        js_steps = _json.loads(raw.replace("'", '"')) if raw else None
    except ValueError:
        js_steps = raw
    check(js_steps == list(ed.STEPS),
          f"the page's JavaScript step order is injected from STEPS, not "
          f"retyped (got {js_steps!r})")

    check(f'repeat({len(ed.STEPS)}, 1fr)' in page,
          f'the grid has one track per step (repeat({len(ed.STEPS)}, 1fr))')
    inset = f'{100 / len(ed.STEPS) / 2:.2f}%'
    check(page.count(f': {inset}') >= 2,
          f'the connector is inset by half a track ({inset}) on both sides')

    # A PLACEHOLDER THAT SURVIVED INTO THE PAGE IS INVISIBLE: `repeat(
    # __STEP_COUNT__, 1fr)` is invalid CSS, so the grid silently falls back and
    # the timeline collapses with nothing in any log. Cheap to assert, so assert.
    leftovers = sorted(set(re.findall(r'__[A-Z][A-Z0-9_]*__', page)))
    check(not leftovers,
          f'no __PLACEHOLDER__ survived into the served page ({leftovers})')

    # ... and the derivation is REAL, not a coincidence of matching literals:
    # change the definition and the generator follows.
    real_labels = ed.STEP_LABELS
    try:
        ed.STEP_LABELS = {'alpha': 'Alpha', 'omega': 'Omega'}
        check(ed._step_header_html() ==
              '<span>Alpha</span><span>Omega</span>',
              'the header generator follows STEP_LABELS (proved by changing it)')
    finally:
        ed.STEP_LABELS = real_labels
    check(ed._step_header_html() ==
          ''.join(f'<span>{lbl}</span>' for lbl in ed.STEP_LABELS.values()),
          'and the real labels are restored afterwards')

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
