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

Run: python scripts/tests/dashboard_test.py   (boots oTree in-process; no server)

NB AUTH_LEVEL is set to STUDY before boot — oTree reads OTREE_AUTH_LEVEL at
import, so the whole file runs in the locked-down mode a real launch uses.
Participant pages are ALWAYS_UNRESTRICTED in oTree, so the walks still work.
"""
import json
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# Before boot: oTree freezes AUTH_LEVEL at import (see module docstring).
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

from main_contract import task_page_submits
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
        # The task pages' names and payloads come from the ONE contract
        # module (scripts/tests/main_contract.py) — a game swap edits it there.
        **task_page_submits(),
        'Demographics': {'age': '30', 'gender': 'Female',
                         'bank': 'NL91ABNA0417164300',
                         'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def walk(client, code, quiz_answers, stop_after=None, quiz_posts=None,
         max_steps=120, headers=None, overrides=None):
    """Walk a participant over the in-process app.

    stop_after: page name — stop once that page has been SUBMITTED.
    quiz_posts: list of payloads to POST on successive quiz renders (wrong
                answers first, e.g. to fail deliberately); afterwards the
                correct answers are used.
    overrides:  {page_name: {field: value}} merged over payload_for's default
                for that page (e.g. a non-Dutch IBAN on Demographics).
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
        if overrides and page in overrides:
            data = dict(data, **overrides[page])
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


def items_first(data, field):
    """The first-pass per-item aggregate for one field, from a quiz-mistakes
    payload."""
    return {i['field']: i for i in data['items']}[field]['first']


def items_reread(data, field):
    """The re-read-pass per-item aggregate for one field."""
    return {i['field']: i for i in data['items']}[field]['reread']


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


def backdate_stamp(code, stage, seconds_ago):
    """Move ONE stage stamp into the past (test-side write). The intro and
    questionnaire phases are judged on elapsed-since-a-stamp (see
    _stall_elapsed), so aging a participant in those phases means aging the
    STAMP — the page timestamp only ages the entry/task phases."""
    import time as _t
    stamps = dict(ot.participant_vars(code).get('stage_timestamps') or {})
    stamps[stage] = _t.time() - seconds_ago
    set_participant(code, **{'vars.stage_timestamps': stamps})


def set_outro_sepa(code, value):
    """Plant a value in the participant's outro.Player.sepa column — the
    hand-edited-row case D7 uses to pin the pill's lab-only gate."""
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        Player = get_models_module('outro').Player
        row = s.query(Player).filter(Player.participant_id == p.id).first()
        row.sepa = value
        s.commit()
    finally:
        s.close()


def set_intro_log(code, round_number, value):
    """Plant an intro.Player.quiz_attempt_log for one round (test-side write;
    the dashboard only reads). `value` is a list of attempt dicts (JSON-encoded
    here) OR a raw string (planted verbatim, to stage a CORRUPT log). oTree
    creates every round's Player row at session creation, so a round-2 log can
    be planted for a participant who never re-read — which is how the two-pass
    separation is tested without walking the whole lab re-read flow."""
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        Player = get_models_module('intro').Player
        row = s.query(Player).filter(
            Player.participant_id == p.id,
            Player.round_number == round_number).one()
        row.quiz_attempt_log = (value if isinstance(value, str)
                                else json.dumps(value))
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
    check(r1['intro_live'] is True
          and isinstance(r1['intro_seconds'], int),
          'INTRO TIME runs LIVE while they are still in the intro app')
    r2 = rows[codes[2]]
    check(r2['step'] == 'task' and r2['task_round'] == 1,
          f"participant in the task carries the round in the marker "
          f"(1 of 3; got step={r2['step']}, round={r2['task_round']})")
    check(r2['quiz']['state'] == 'green' and r2['quiz']['display'] == 1,
          "first-try quiz shows GREEN 1 (1 = passed first attempt)")
    # NOT "fixed once instructions_done is stamped" any more (round-2 item 5):
    # the clock stops when the participant is OUT OF THE INTRO APP, which is
    # what lets a lab re-read after a failed quiz keep counting. r2 is in the
    # task, so it is stopped.
    check(isinstance(r2['intro_seconds'], int)
          and r2['intro_live'] is False,
          'intro time stops once the participant has left the intro app')
    r3 = rows[codes[3]]
    check(r3['step'] == 'done' and r3['finished'] is True,
          f"finished participant: step=done (got {r3['step']})")
    check(isinstance(r3['earnings'], float) and r3['earnings'] > 0,
          f"earnings shown once known (got {r3['earnings']})")
    # TOTAL PAYMENTS (summary strip): summed SERVER-SIDE from the same place the
    # row earnings come from (ctx['earnings']), so the strip total can never
    # disagree with the per-row cells — the discipline the timing pill follows.
    # Population = the participants who HAVE an earnings figure (finished), and
    # the count rides along, the way the averages state their denominator.
    et = data['earnings_total']
    row_earnings = [r['earnings'] for r in data['rows']
                    if r.get('earnings') is not None]
    check(et['n'] == len(row_earnings) and len(row_earnings) >= 1,
          f"earnings_total counts exactly the rows that HAVE earnings "
          f"(n={et['n']}, rows-with-earnings={len(row_earnings)})")
    check(et['total'] is not None
          and abs(et['total'] - sum(row_earnings)) < 1e-6,
          f"earnings_total.total is the SUM of the row earnings, computed "
          f"server-side (got {et['total']}, sum of rows {sum(row_earnings)})")
    # THE TIME PILL (summary strip): mean intro time AND mean COMPLETION time,
    # BOTH over the SAME finished population — one denominator, computed
    # server-side from stage_timestamps (never re-derived in the client), the
    # same discipline earnings_total follows (Julian, 2026-08-17).
    ts = data['time_summary']
    fin_rows = [r for r in data['rows'] if r.get('finished')]
    check(ts['n'] == len(fin_rows) and ts['n'] >= 1,
          f"time_summary covers exactly the FINISHED participants — one "
          f"population (n={ts['n']}, finished rows={len(fin_rows)})")
    # PAIRED PRESENCE: both subsections carry a value, and completion (the whole
    # run) is at least the intro block it contains — never a subsection missing.
    check(ts.get('intro_avg') is not None and ts.get('completion_avg') is not None
          and ts['completion_avg'] >= ts['intro_avg'] - 1,
          f"both means are present and completion >= intro (the whole run is at "
          f"least the intro block): intro={ts.get('intro_avg')}, "
          f"completion={ts.get('completion_avg')}")
    # DEGRADES TO NO PILL: a session nobody has finished has n=0 (no pill at
    # all), exactly as earnings_total does — the honest early-session state.
    empty = ot.create_session('lab', num_participants=2)
    de = admin.get(f'{URL}/{empty.code}/data').json()
    check(de['time_summary']['n'] == 0 and de['earnings_total']['n'] == 0,
          f"early in a session nobody has finished: the TIME pill and the "
          f"earnings pill both degrade to n=0 — no pill (time n="
          f"{de['time_summary']['n']}, earnings n={de['earnings_total']['n']})")
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
    set_participant(pcodes[3], **{'vars.tab_monitor_disqualified': True,
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

    section('D3. amber (stall) — PER-PHASE thresholds (round-2 item 6)')
    # The whole point of the change: the SAME time on a page is amber in one
    # phase and unremarkable in another. One global number could not be both,
    # and the failure was silent either way (see STALL_SETTING_BY_STEP).
    check(ed.stall_seconds_for('entry') == 60
          and ed.stall_seconds_for('instructions') == 480
          and ed.stall_seconds_for('quiz') == 480
          and ed.stall_seconds_for('task') == 180
          and ed.stall_seconds_for('questionnaire') == 300,
          'each phase has its own threshold from settings.py '
          '(entry 60, intro 480, task 180, outro 300)')
    check(ed.stall_seconds_for('instructions') == ed.stall_seconds_for('quiz'),
          'the two halves of intro share ONE threshold (Julian asked for a '
          'threshold on INTRO, not on each half)')
    import time as _time
    # THE MEASURE IS PER PHASE TOO (the pills change, 2026-08-13): entry is
    # judged on the CURRENT PAGE, intro on the WHOLE intro app (elapsed since
    # left_before_app — the same clock as the INTRO TIME column), because that
    # is what each threshold MEANS in settings.py. See _stall_elapsed.
    #
    # 400s: OVER the entry threshold, UNDER the intro one. codes[1] is on the
    # instructions, codes[6] is at entry — same dwell, different verdicts, which
    # is the behaviour a single threshold could not produce.
    set_participant(codes[6], _last_page_timestamp=int(_time.time()) - 400)
    set_participant(codes[1], _last_page_timestamp=int(_time.time()) - 400)
    backdate_stamp(codes[1], 'left_before_app', 400)
    data, rows = rows_by_code(admin, lab)
    check(rows[codes[6]]['stalled'] is True
          and rows[codes[6]]['seconds_on_page'] >= 400,
          '400s at ENTRY is amber (over the 60s entry threshold)')
    check(rows[codes[6]]['stall_section'] == 'Entry',
          f"…and the timing pill names its phase "
          f"(got {rows[codes[6]]['stall_section']!r})")
    check(rows[codes[1]]['stalled'] is False,
          'the SAME 400s in the INTRO is not (under the 480s intro '
          'threshold) — one number could not have said both')
    check(rows[codes[1]]['stall_limit'] == 480
          and rows[codes[6]]['stall_limit'] == 60,
          'each row carries the threshold it is judged against, so the screen '
          'can name it')
    # Ageing the PAGE alone must not trip the intro phase: its threshold is
    # about the whole app, so its elapsed is stamp-based, not page-based.
    set_participant(codes[1], _last_page_timestamp=int(_time.time()) - 600)
    data, rows = rows_by_code(admin, lab)
    check(rows[codes[1]]['stalled'] is False,
          '600s on one PAGE alone does not trip the INTRO phase — intro is '
          'judged on the whole app, not the current page')
    backdate_stamp(codes[1], 'left_before_app', 600)
    data, rows = rows_by_code(admin, lab)
    check(rows[codes[1]]['stalled'] is True,
          '600s INTO THE INTRO APP is amber (over the 480s intro threshold)')
    check(rows[codes[1]]['stall_section'] == 'Intro'
          and rows[codes[1]]['stall_elapsed'] >= 600,
          f"the pill names Intro and shows the PHASE elapsed — the number the "
          f"threshold judged (got {rows[codes[1]]['stall_section']!r} "
          f"{rows[codes[1]]['stall_elapsed']})")
    check(rows[codes[1]]['stall_elapsed'] == rows[codes[1]]['intro_seconds'],
          'display and detection are the SAME clock as the intro-time column '
          '(one implementation, not a second stopwatch)')
    check(rows[codes[3]]['stalled'] is False,
          'a finished row can never stall')
    import settings as user_settings
    user_settings.DASHBOARD_STALL_SECONDS_INTRO = 1000
    try:
        data, rows = rows_by_code(admin, lab)
        check(rows[codes[1]]['stalled'] is False,
              'raising the INTRO threshold in settings takes effect without '
              'touching dashboard code')
        check(rows[codes[6]]['stalled'] is True,
              '…and does NOT move the entry threshold with it (the phases are '
              'independent — that is the whole change)')
    finally:
        user_settings.DASHBOARD_STALL_SECONDS_INTRO = 480
    # Deleting every DASHBOARD_STALL_* line must still leave working defaults.
    _saved = {k: getattr(user_settings, k) for k in dir(user_settings)
              if k.startswith('DASHBOARD_STALL_SECONDS')}
    try:
        for k in _saved:
            delattr(user_settings, k)
        check(ed.stall_seconds_for('entry') == 60
              and ed.stall_seconds_for('task') == 180,
              'deleting every DASHBOARD_STALL_* line falls back to the same '
              'defaults inside the dashboard module')
    finally:
        for k, v in _saved.items():
            setattr(user_settings, k, v)
    # REFETCH: `data` above was taken while the intro threshold was temporarily
    # 1000, so the assertions below would read a snapshot from inside that
    # override rather than the shipped defaults.
    data, rows = rows_by_code(admin, lab)
    # The snapshot ships the whole map, so the operator screen and this test
    # read the thresholds from one place.
    check(isinstance(data['stall_seconds'], dict)
          and data['stall_seconds']['entry'] == 60,
          'the snapshot ships the per-phase threshold map, not one number')
    # THE HEADER LEGEND (round-2 item 17): "so we can see what the thresholds
    # are" without opening settings.py. Served as data, never as markup, so a
    # tuned threshold reaches the screen on the next poll.
    legend = data['stall_legend']
    check([p['label'] for p in legend]
          == ['Entry', 'Intro (instructions + quiz)', 'Task (one round)',
              'Questionnaire'],
          f'the legend names the four PHASES an operator thinks in '
          f'(got {[p["label"] for p in legend]})')
    check([p['seconds'] for p in legend] == [60, 480, 180, 300],
          f'…with the live values, not a hardcoded string '
          f'(got {[p["seconds"] for p in legend]})')
    user_settings.DASHBOARD_STALL_SECONDS_TASK = 240
    try:
        data2, _ = rows_by_code(admin, lab)
        check([p['seconds'] for p in data2['stall_legend']]
              == [60, 480, 240, 300],
              'tuning a threshold in settings.py changes what the legend '
              'shows, with no dashboard edit')
    finally:
        user_settings.DASHBOARD_STALL_SECONDS_TASK = 180

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
    check('left_before_app' in (ot.participant_vars(dwell_code)
                                .get('stage_timestamps') or {}),
          'leaving the LAST page of the before app stamps left_before_app '
          '(the start of INTRO TIME)')
    instr = drows[dwell_code]['intro_seconds']
    check(instr is not None and instr < DWELL,
          f'{DWELL}s on the AGREEMENT page and ~0s in the intro app reports '
          f'< {DWELL}s of intro time (got {instr}s) — the agreement page is '
          f'part of the ENTRY block and is not billed to the intro')

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

    section('D5b. ADVANCE SLOWEST PARTICIPANTS is not reported as a quiz pass')
    # QUESTION B, 2026-08-13. Julian force-advanced a session through the
    # template with the admin panel's "advance slowest participants" and every
    # participant then showed as having PASSED the quiz on the second attempt.
    #
    # What oTree actually does (measured; otree/models/participant.py
    # _submit_current_page): it POSTs an EMPTY form flagged as a timeout with
    # the admin secret code. oTree calls error_message anyway
    # (otree/views/abstract.py, the _process_auto_submitted_form branch), our
    # grading marks every item wrong and increments comprehension_failed_attempts, and the
    # page then ADVANCES REGARDLESS because a timeout submission discards the
    # error. So `quiz_done` is stamped by somebody who never answered.
    #
    # That made two different situations reach one predicate — the collapsed
    # distinction rule in CLAUDE.md — and the cell called both of them a pass.
    # This section is the regression guard on keeping them apart.
    fa = ot.create_session('lab', num_participants=2)
    from otree.database import db as _db
    from otree.models import Session as _Session
    _fa = _db.query(_Session).filter_by(code=fa.code).one()
    for _ in range(12):
        _fa.advance_last_place_participants()
        _db.commit()
        if all(p._current_page_name == 'quiz' for p in _fa.pp_set):
            break
    _, farows = rows_by_code(admin, fa)
    check(all(r['quiz']['state'] == 'idle' for r in farows.values()),
          'before the forced advance, nobody has attempted the quiz')
    _fa.advance_last_place_participants()      # the force-advance ON the quiz
    _db.commit()
    _, farows = rows_by_code(admin, fa)
    one = list(farows.values())[0]
    check(one['step'] == 'task',
          f"the forced advance really did push them past the quiz "
          f"(step={one['step']!r}) — otherwise this section proves nothing")
    check(one['quiz']['state'] == 'forced',
          f"a force-advanced participant reads FORCED, not passed "
          f"(got {one['quiz']['state']!r})")
    check(one['quiz']['state'] != 'green',
          'and specifically NOT the green "✓ 2" that started this question')
    check(one['quiz']['state'] != 'red',
          'and NOT a failure either — an experimenter did this deliberately, '
          'nothing is wrong with the participant')
    # The data itself was never corrupted, which is the half of the answer that
    # matters for the export. Pin it so a future change cannot make it untrue.
    from otree.common import get_models_module as _gmm
    _IntroPlayer = _gmm('intro').Player
    _pl = [r for r in _db.query(_IntroPlayer).filter(
        _IntroPlayer.session_id == _fa.id, _IntroPlayer.round_number == 1)]
    check(all(json.loads(p.field_maybe_none('quiz_attempt_log') or '[]')[-1]['wrong']
              for p in _pl),
          'the attempt log records the forced submission as WRONG, so no '
          'export column claims a pass')
    check(all(int(p.field_maybe_none('num_failed_attempts') or 0) == 1
              for p in _pl),
          'and it counts as a failed attempt, so the quiz bonus is forfeited')
    # A GENUINE pass in the same session type must still read green — the new
    # state must not have swallowed the ordinary case.
    check(rows[codes[2]]['quiz']['state'] in ('green', 'idle', 'progress'),
          'a normally-walked participant is unaffected by the forced state')

    section('D5c. rows are ordered by the DISPLAYED NAME, sorted naturally')
    # Julian, 2026-08-13: rows used to come out in participant-id order, i.e.
    # roughly ARRIVAL order, so the screen and the lab room disagreed.
    #
    # The natural sort is the part worth testing rather than the alphabetical
    # one: `Seat 01`-style labels are zero-padded and would sort correctly as
    # plain strings, so a plain-string bug would be INVISIBLE against the
    # template's own labels. `a2`/`a10` is the case that exposes it, and it is
    # the case a real study produces the moment it stops padding.
    ordering = ot.create_session('lab', num_participants=6)
    ocodes = ot.participant_codes(ordering)
    planted = ['a10', 'a2', 'Seat 03', '', 'a1', 'seat 1']
    for code, lbl in zip(ocodes, planted):
        if lbl:
            ot.set_label(code, lbl)
    data_o, _ = rows_by_code(admin, ordering)
    shown = [r['label'] or f'<{r["code"]}>' for r in data_o['rows']]
    # NB `seat 1` before `Seat 03`: the text runs casefold to the same thing, so
    # the DIGITS decide and 1 < 3. That is the natural sort doing its job, not a
    # padding accident — the first draft of this expectation had them the other
    # way round because it was still reading them as strings.
    check(shown[:5] == ['a1', 'a2', 'a10', 'seat 1', 'Seat 03'],
          f'labels sort NATURALLY — a2 before a10, not after it, and case is '
          f'ignored (got {shown})')
    check(shown[0] != 'a10',
          'and specifically NOT the plain-string order a10 < a2 would give')
    check(shown[-1].startswith('<'),
          f'the UNLABELLED row sorts LAST, not first — an empty label sorts '
          f'first as a string and would push never-arrived rows to the top of '
          f'the screen (got {shown})')
    # The key really is the DISPLAYED string, not the row id: the planted labels
    # are deliberately not in id order, so passing means id order was discarded.
    check([s.strip('<>') for s in shown][:3] != planted[:3],
          'the id (arrival) order was NOT preserved — the table is sorted')
    # THE FLIP JULIAN MAY ASK FOR must stay one line: with UNLABELLED_LAST off,
    # the table is exactly the displayed names in natural order, no special case.
    ed.UNLABELLED_LAST = False
    try:
        flipped_data, _ = rows_by_code(admin, ordering)
        flipped = [ed.displayed_name(r) for r in flipped_data['rows']]
        check(flipped == sorted(flipped, key=ed.natural_label_key),
              f'UNLABELLED_LAST=False interleaves the unlabelled row by its '
              f'displayed code — the one-line flip still works ({flipped})')
    finally:
        ed.UNLABELLED_LAST = True

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

    section('D7. state pills: Non-SEPA is lab-only, null is no pill, and '
            'conditions survive finishing')
    # THE STATE COLUMN IS A COLLECTION OF PILLS (Julian, 2026-08-13): outcome
    # pills (terminal / finished) plus CONDITION pills that persist regardless
    # of outcome. The Non-SEPA condition: red pill, LAB sessions only, fired by
    # sepa == 0 alone — sepa is nullable and NULL (never asked: every Prolific
    # row) must read as NO pill, not as a flag.
    sepa_lab = ot.create_session('lab', num_participants=3)
    scodes = ot.participant_codes(sepa_lab)
    US_IBAN = 'US64SVBKUS6S3300958879'
    walk(ot.client(), scodes[0], correct, overrides={'Demographics': {
        'bank': US_IBAN, 'bank_confirmation': US_IBAN, 'bic': 'SVBKUS6S'}})
    walk(ot.client(), scodes[1], correct)          # NL IBAN (the default)
    # scodes[2] never arrives: sepa stays NULL.
    _, srows = rows_by_code(admin, sepa_lab)
    s0 = srows[scodes[0]]
    check(s0['finished'] is True and s0['non_sepa'] is True,
          'a FINISHED participant with a non-SEPA account carries BOTH facts '
          '— the outcome does not clear the condition '
          f"(finished={s0['finished']}, non_sepa={s0['non_sepa']})")
    check(srows[scodes[1]]['finished'] is True
          and srows[scodes[1]]['non_sepa'] is False,
          'an in-SEPA (NL) account gets NO payment pill')
    check(srows[scodes[2]]['non_sepa'] is False,
          'sepa NULL (never asked) reads as NO pill, not as a flag')
    # A non-Dutch but in-SEPA account gets NO pill either (Julian: only
    # non-SEPA is flagged; there is no yellow payment state). NB this is
    # DELIBERATELY a different predicate from the bank form's BIC rule, which
    # DOES fire for any non-Dutch IBAN — scripts/tests/bank_details_test.py pins that
    # half of the asymmetry.
    DE_IBAN = 'DE89370400440532013000'
    sepa_lab2 = ot.create_session('lab', num_participants=1)
    de_code = ot.participant_codes(sepa_lab2)[0]
    walk(ot.client(), de_code, correct, overrides={'Demographics': {
        'bank': DE_IBAN, 'bank_confirmation': DE_IBAN, 'bic': 'COBADEFF'}})
    _, drows2 = rows_by_code(admin, sepa_lab2)
    check(drows2[de_code]['non_sepa'] is False,
          'a non-Dutch but IN-SEPA (DE) account gets NO pill — only non-SEPA '
          'is flagged (no yellow payment state)')
    # LAB ONLY: even a sepa=0 value sitting in a PROLIFIC session's outro row
    # (a hand-edited row, a future config mistake) must produce no pill —
    # Prolific pays through the platform and there is no bank form to chase.
    set_outro_sepa(pcodes[3], 0)
    _, prows2 = rows_by_code(admin, pro)
    check(prows2[pcodes[3]]['non_sepa'] is False,
          'sepa=0 in a PROLIFIC session still shows NO pill (lab only)')
    # The served page carries the pill machinery (classes + renderer).
    page = admin.get(f'{URL}/{sepa_lab.code}').text
    check('state-pills' in page and 'spill-nonsepa' in page
          and 'spill-stall' in page and 'spill-finished' in page,
          'the served page ships the pill renderer and all pill classes')
    # THE MERGED EARNINGS PILL — asserted on its actual STRUCTURE, not on a
    # phrase. 'total payments' used to appear in the rendered pill, but since
    # avg and total were merged into one pill (Julian, 2026-08-17) that phrase
    # survives ONLY in the pill's tooltip — so testing for it no longer proves
    # the pill renders; it would pass against any page carrying the tooltip
    # text. The subsection markup is what the pill is made of: the label
    # "earnings", an "avg" subsection and a "total" subsection, with the total
    # still read from the SERVER-side earnings_total (not re-summed in the
    # client — the one-number-in-one-place discipline).
    check('sum-label">earnings' in page
          and 'sum-n">avg' in page and 'sum-n">total' in page
          and 'data.earnings_total' in page,
          'the served page ships the MERGED earnings pill — label "earnings" '
          'with both an avg AND a total subsection — computed from the '
          'server-side earnings_total (not re-summed in the client)')
    # THE MERGED TIME PILL — same structural check: the label "time" with an
    # "avg intro" and an "avg completion" subsection, both read from the
    # SERVER-side time_summary (never re-derived in the client). Asserting the
    # markup, not a tooltip phrase, so it proves the pill renders.
    check('sum-label">time' in page
          and 'sum-n">avg intro' in page and 'sum-n">avg completion' in page
          and 'data.time_summary' in page,
          'the served page ships the MERGED time pill — label "time" with both '
          'an avg-intro AND an avg-completion subsection — computed from the '
          'server-side time_summary (not re-derived in the client)')

    section('D8. the no-return-click pill, the monitor count, the arrival '
            'count')
    # --- 1. FINISHED HERE ≠ PAID THERE (Julian's extra warnings, item 1).
    # The pill fires only when there is ACTUALLY A BUTTON to have clicked —
    # prolific_completion_redirects on — and only after the grace period.
    import outro as outro_app
    from otree.common import get_models_module as _gmm2
    from otree.database import db as _db2

    def _outro_player(code):
        from otree.models import Participant as _P
        p = _db2.query(_P).filter_by(code=code).one()
        return (_db2.query(_gmm2('outro').Player)
                .filter(_gmm2('outro').Player.participant_id == p.id).first())

    ret = ot.create_session('prolific', num_participants=1)
    rcode = ot.participant_codes(ret)[0]
    walk(ot.client(), rcode, correct, headers=DESKTOP)          # finishes
    _, rrows = rows_by_code(admin, ret)
    check(rrows[rcode]['finished'] is True
          and rrows[rcode]['awaiting_return'] is False,
          'within the grace period a fresh finisher is NOT flagged — they are '
          'still reading their receipt')
    backdate_stamp(rcode, 'finished', 200)      # past the 90s default grace
    _, rrows = rows_by_code(admin, ret)
    check(rrows[rcode]['awaiting_return'] is True,
          'past the grace with no click recorded, the finisher IS flagged')
    # A hand-crafted / wrong-shaped live message must not stamp anything…
    outro_app.results_live_method(_outro_player(rcode), {'type': 'other'})
    _db2.commit()
    check('prolific_return_clicked' not in
          (ot.participant_vars(rcode).get('stage_timestamps') or {}),
          'a wrong-shaped live message stamps nothing')
    # …and the real click message clears the flag on the next poll.
    outro_app.results_live_method(_outro_player(rcode),
                                  {'type': 'prolific_return_click'})
    _db2.commit()
    check('prolific_return_clicked' in
          (ot.participant_vars(rcode).get('stage_timestamps') or {}),
          'the click message stamps prolific_return_clicked')
    _, rrows = rows_by_code(admin, ret)
    check(rrows[rcode]['awaiting_return'] is False,
          'once the click is recorded the pill is gone')
    # THE GATE (Julian's critical condition): with redirects OFF there is no
    # button to have clicked, so the flag must NEVER fire — otherwise every
    # lab participant would carry it forever. scodes[1] is a lab finisher.
    backdate_stamp(scodes[1], 'finished', 10_000)
    _, srows = rows_by_code(admin, sepa_lab)
    check(srows[scodes[1]]['finished'] is True
          and srows[scodes[1]]['awaiting_return'] is False,
          'NO redirect button configured -> NO flag, however long ago they '
          'finished (the lab case that makes the gate load-bearing)')
    # And the handler itself is gated the same way: a lab "click" stamps
    # nothing even if some script sends one.
    outro_app.results_live_method(_outro_player(scodes[1]),
                                  {'type': 'prolific_return_click'})
    _db2.commit()
    check('prolific_return_clicked' not in
          (ot.participant_vars(scodes[1]).get('stage_timestamps') or {}),
          'the live handler is gated on the same flag (no stamp in the lab)')

    # --- 2. TAB-MONITOR VIOLATIONS WHILE THEY CLIMB (item 2): count and
    # limit together, from tab_monitor_focus_loss_count and tab_monitor_max_violations —
    # never a number in the markup.
    import common as _common
    mon = ot.create_session('prolific', num_participants=1)
    mcode = ot.participant_codes(mon)[0]
    walk(ot.client(), mcode, correct, stop_after='quiz', headers=DESKTOP)
    _, mrows = rows_by_code(admin, mon)
    check(mrows[mcode]['monitor_count'] is None,
          'no violations -> no count shipped (no pill, not a "0 of 3")')
    set_participant(mcode, **{'vars.tab_monitor_focus_loss_count': 2})
    _, mrows = rows_by_code(admin, mon)
    from otree.models import Session as _S2
    _mon = _db2.query(_S2).filter_by(code=mon.code).one()
    expected_max = int(_common.cfg(_mon.config, 'tab_monitor_max_violations'))
    check(mrows[mcode]['monitor_count'] == 2
          and mrows[mcode]['monitor_max'] == expected_max,
          f"a climbing count ships WITH the configured limit "
          f"(got {mrows[mcode]['monitor_count']} of "
          f"{mrows[mcode]['monitor_max']}, limit {expected_max})")
    set_participant(mcode, **{'vars.tab_monitor_disqualified': True,
                              'vars.exit_code': -3})
    _, mrows = rows_by_code(admin, mon)
    check(mrows[mcode]['terminal'] == 'tab_monitor'
          and mrows[mcode]['monitor_count'] is None,
          'once disqualified the terminal pill takes over — no climbing count '
          'next to a DQ')
    # tab_monitor OFF (every lab session): a planted count ships nothing.
    set_participant(scodes[0], **{'vars.tab_monitor_focus_loss_count': 2})
    _, srows = rows_by_code(admin, sepa_lab)
    check(srows[scodes[0]]['monitor_count'] is None,
          'with the tab_monitor module off, no count is ever shipped')

    # --- 3. THE ARRIVAL COUNT is client-side JS ('👤 X of Y arrived'); the
    # in-process check is that the page ships it — the measured check is
    # dashboard_render_check.py's, in a real browser.
    page = admin.get(f'{URL}/{ret.code}').text
    check('👤' in page and 'arrived' in page,
          'the served page ships the arrival-count segment (👤 X of Y)')

    section('D9. the admin Report TAB — a convenience layer over the '
            'standalone URL')
    # oTree's SUPPORTED admin-report extension point (Session._set_admin_
    # report_app_names scans for outro/admin_report.html at session creation;
    # Session.html renders the Report tab when found) carries the dashboard
    # into the session admin's own tab bar. THE CONSTRAINT THAT MATTERS: the
    # standalone URL is the primary surface and must keep working unchanged,
    # and a failure in either layer must not take down the other.
    from otree.models import Session as _S3
    _lab3 = _db2.query(_S3).filter_by(code=lab.code).one()
    check(_lab3.has_admin_report() is True,
          'a session registers the admin report at creation '
          '(outro/admin_report.html was found by oTree)')
    r = admin.get(f'/SessionMonitor/{lab.code}')
    check(r.status_code == 200 and 'AdminReport' in r.text,
          "oTree's OWN session tab bar shows the Report tab (no page of "
          "oTree's was templated over to get it there)")
    r = admin.get(f'/AdminReport/{lab.code}')
    check(r.status_code == 200 and f'{URL}/{lab.code}' in r.text,
          'the Report tab links AND embeds the dashboard at its real URL')
    d = admin.get(f'{URL}/{lab.code}/data').json()
    check(d.get('ok') is True,
          'the standalone dashboard URL works unchanged with the tab present')
    # Layer independence, both directions: a broken DASHBOARD leaves the
    # admin pages serving (the iframe would show the dashboard's own error
    # panel — its fail-soft, already proven in section C).
    real_snapshot3 = ed.session_snapshot
    ed.session_snapshot = lambda session: (_ for _ in ()).throw(
        RuntimeError('injected dashboard bug'))
    try:
        check(admin.get(f'/AdminReport/{lab.code}').status_code == 200,
              'a broken dashboard data layer leaves the Report tab serving')
        check(admin.get(f'/SessionMonitor/{lab.code}').status_code == 200,
              '…and the session Monitor page untouched')
    finally:
        ed.session_snapshot = real_snapshot3
    # …and a broken TAB layer cannot 500 the tab: vars_for_admin_report is
    # internally defensive, because oTree calls it unguarded. Break the one
    # thing it depends on (the module import) and it must fall back, not
    # raise.
    import outro as _outro3
    import sys as _sys3
    _saved_mod = _sys3.modules.get('experimenter_dashboard')
    _sys3.modules['experimenter_dashboard'] = None   # makes import raise
    try:
        _OutroSub = _gmm2('outro').Subsession
        _sub = (_db2.query(_OutroSub)
                .filter(_OutroSub.session_id == _lab3.id).first())
        v = _outro3.vars_for_admin_report(_sub)
        check(v['dashboard_url'] == f'/experimenter_dashboard/{lab.code}',
              'vars_for_admin_report survives a broken module import '
              f'(fallback URL, no raise: {v["dashboard_url"]})')
    finally:
        if _saved_mod is None:
            _sys3.modules.pop('experimenter_dashboard', None)
        else:
            _sys3.modules['experimenter_dashboard'] = _saved_mod
    # The drift check (quiet / loud discipline): green against this oTree.
    check(ed.note_admin_tab_problems() == 'ok',
          'note_admin_tab_problems reports ok against the installed oTree')

    # --- THE REALISTIC DRIFT, OVER REAL HTTP (blast-radius scenario 4). The
    # D9 case above breaks the module IMPORT (ImportError, always caught). The
    # drift that actually shipped is different and was NOT caught: URL_BASE
    # renamed consistently INSIDE experimenter_dashboard.py, the cross-file read
    # in vars_for_admin_report missed — an AttributeError, which the old
    # `except ImportError` let through, 500ing oTree's OWN Report tab (called
    # unguarded) the first time an operator clicked it mid-session. Delete the
    # attribute to reproduce the rename and drive the tab over real HTTP.
    real_url_base = ed.URL_BASE
    del ed.URL_BASE
    try:
        r = admin.get(f'/AdminReport/{lab.code}')
        # PAIRED PRESENCE, not "< 500" alone (CLAUDE.md testing standard): the
        # tab must actually RENDER with a working dashboard link (the literal
        # fallback), not merely avoid a 500 by serving a blank page. status==200
        # here is the regression guard — reverting the widened except makes this
        # AttributeError escape and the tab 500 again.
        check(r.status_code == 200
              and f'/experimenter_dashboard/{lab.code}' in r.text,
              f'the Report tab does NOT 500 when URL_BASE cannot be read — it '
              f'falls back to the literal base URL and still links the '
              f'dashboard (status {r.status_code})')
    finally:
        ed.URL_BASE = real_url_base
    r = admin.get(f'/AdminReport/{lab.code}')
    check(r.status_code == 200 and f'{URL}/{lab.code}' in r.text,
          'and with URL_BASE restored the Report tab renders normally again '
          '(the check above tested the broken state, not an always-200 page)')

    # --- SCENARIO 4′: the install-failure REPORTER must not raise on the symbol
    # it reports. install_dashboard_route_or_note formats a "not installed"
    # message; when URL_BASE is the missing symbol, an f-string reading
    # {URL_BASE} raises a SECOND NameError while reporting the first, and that
    # escapes the unguarded call site in outro/__init__.py and kills the boot.
    # Force install to raise AND remove URL_BASE, then assert the handler
    # REPORTS (returns 'drift') rather than raising.
    real_install = ed.install_dashboard_route
    real_url_base2 = ed.URL_BASE
    ed.install_dashboard_route = lambda: (_ for _ in ()).throw(
        NameError("name 'URL_BASE' is not defined"))
    del ed.URL_BASE
    try:
        raised = None
        try:
            outcome = ed.install_dashboard_route_or_note()   # must NOT raise
        except Exception as exc:
            raised = exc
        check(raised is None and outcome == 'drift',
              'the install-failure reporter returns drift WITHOUT raising even '
              'when URL_BASE — the very symbol it names — is the missing one '
              f'(raised={raised!r})')
    finally:
        ed.install_dashboard_route = real_install
        ed.URL_BASE = real_url_base2
    # PAIRED POSITIVE: with the real install restored the same reporter returns
    # the healthy outcome, so the check above tested the failure path rather
    # than a function that returns 'drift' unconditionally.
    check(ed.install_dashboard_route_or_note() == ed.ALREADY,
          'and on a healthy install the same reporter returns ALREADY')

    section('D10. the PRE-LAUNCH guard catches a broken dashboard')
    # THE LAUNCH HALF of the 2026-08-17 fix. The runtime widening above stops
    # the Report tab 500ing; this stops the underlying rename ever SHIPPING —
    # scripts/prelaunch_check.dashboard_problems() checks the module imports,
    # URL_BASE exists, vars_for_admin_report returns a plausible URL without
    # raising, and the routes install, reporting each as a normal prelaunch
    # problem. Caught at launch, while somebody can still fix it, rather than by
    # a curious click three hours into a session.
    sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
    import prelaunch_check as pc
    check(pc.dashboard_problems() == [],
          'the dashboard section of prelaunch_check passes on the healthy '
          'template (no false positive)')
    _rub = ed.URL_BASE
    del ed.URL_BASE
    try:
        broken = pc.dashboard_problems()
        check(any('URL_BASE' in label for label, _c, _m in broken),
              f'…and REPORTS a problem naming URL_BASE when the constant has '
              f'been renamed away (got {[l for l, _, _ in broken]})')
    finally:
        ed.URL_BASE = _rub
    check(pc.dashboard_problems() == [],
          'the guard is clean again once URL_BASE is restored (it was testing '
          'the broken state, not failing unconditionally)')

    # ------------------------------------------------------------------ F
    section('F. the quiz-mistakes panel — on-demand, over real HTTP')
    # Everything here drives the /quiz_mistakes ENDPOINT over HTTP (the panel
    # itself renders client-side, like the main table; the rendered DOM and its
    # escaping are dashboard_render_check.py's job). The endpoint's JSON is the
    # server-side aggregate, which is where the correctness lives.
    QM = lambda code: admin.get(f'{URL}/{code}/quiz_mistakes').json()  # noqa

    correct2 = {'quiz1': 'YES', 'quiz2': 'Water'}   # the shipped example items
    w1 = dict(correct2, quiz1='NO')                 # quiz1 wrong
    w2 = dict(correct2, quiz2='Metal')              # quiz2 wrong

    qm = ot.create_session('lab', num_participants=5)
    qcodes = ot.participant_codes(qm)
    # p0, p4 correct first try; p1, p2 miss quiz1 first (then pass); p3 misses
    # quiz2 first. The ones who retry leave a SECOND attempt underneath.
    walk(ot.client(), qcodes[0], correct2)
    walk(ot.client(), qcodes[1], correct2, quiz_posts=[w1])
    walk(ot.client(), qcodes[2], correct2, quiz_posts=[w1])
    walk(ot.client(), qcodes[3], correct2, quiz_posts=[w2])
    walk(ot.client(), qcodes[4], correct2)

    d = QM(qm.code)
    check(d.get('ok') is True and d.get('available') is True,
          f"a session with quiz attempts returns available data "
          f"(ok={d.get('ok')}, available={d.get('available')})")
    items = {it['field']: it for it in d['items']}
    check(len(d['items']) == 2 and 'quiz1' in items and 'quiz2' in items,
          f"the two shipped quiz items are present ({list(items)})")
    # FIRST ATTEMPT ONLY, and the real content: quiz1 was missed by two (both
    # chose NO), got right by three. PAIRED PRESENCE — the wrong option AND the
    # correct option, never one without the other (the leak-test rule).
    q1 = items['quiz1']['first']
    by_text = {o['text']: o for o in q1['options']}
    check(d['passes']['first']['n_valid'] == 5,
          f"all five reached the quiz with a valid first attempt "
          f"(n_valid={d['passes']['first']['n_valid']})")
    check(q1['n'] == 5 and q1['n_correct'] == 3,
          f"quiz1 first-attempt rate is 3 of 5 (got {q1['n_correct']}/{q1['n']})")
    check('NO' in by_text and by_text['NO']['count'] == 2
          and by_text['NO']['correct'] is False,
          f"the wrong option 'NO' is shown with its count of 2 ({by_text})")
    check('YES' in by_text and by_text['YES']['count'] == 3
          and by_text['YES']['correct'] is True,
          f"…and the correct option 'YES' alongside it ({by_text})")
    # WORST FIRST: quiz1 (0.6) before quiz2 (0.8), and quiz1 badged most-missed.
    check(d['items'][0]['field'] == 'quiz1' and d['items'][0]['missed'] is True,
          f"the worst item is first and badged 'most missed' "
          f"(order={[it['field'] for it in d['items']]})")
    # PER-PARTICIPANT DETAIL: at least one first-attempt miss AND at least one
    # first-attempt pass on quiz1 (paired), and a retried participant carries a
    # LATER attempt underneath — the 'kept, not headline' data.
    firsts = [p for p in d['participants'] if p['first']]
    missed_q1 = [p for p in firsts if p['first'].get('quiz1', {}).get('correct')
                 is False]
    got_q1 = [p for p in firsts if p['first'].get('quiz1', {}).get('correct')
              is True]
    check(len(missed_q1) == 2 and len(got_q1) == 3,
          f"the per-participant marks show two quiz1 misses and three passes "
          f"({len(missed_q1)} missed, {len(got_q1)} passed)")
    check(any(p['later'] for p in d['participants']),
          'a retried participant keeps a later attempt underneath (n >= 2)')

    section('F2. a corrupt or missing log costs the panel, not the table')
    # (a) A RAISING panel builder degrades to ok:false while the main /data
    #     poll — a SEPARATE route — stays ok:true. This is the check that fails
    #     if the endpoint's soft-fail wrapper is removed.
    real_qm = ed.quiz_mistakes_snapshot
    ed.quiz_mistakes_snapshot = lambda s: (_ for _ in ()).throw(
        RuntimeError('injected quiz-mistakes bug'))
    try:
        r = QM(qm.code)
        check(r.get('ok') is False
              and 'injected quiz-mistakes bug' in r.get('error', ''),
              'a raising panel builder returns ok:false JSON naming the error')
        dd = admin.get(f'{URL}/{qm.code}/data').json()
        check(dd.get('ok') is True,
              'the MAIN table is unaffected — a broken panel is a separate '
              'route on a separate fetch')
    finally:
        ed.quiz_mistakes_snapshot = real_qm
    check(QM(qm.code).get('ok') is True,
          'the panel recovers the moment the bug is gone (paired positive)')

    # (b) ONE participant's corrupt log renders THEM unreadable while every
    #     other participant still aggregates (row-granularity degradation).
    set_intro_log(qcodes[2], 1, '{not valid json')
    d2 = QM(qm.code)
    unreadable = [p for p in d2['participants'] if p.get('unreadable')]
    check(d2.get('ok') is True and d2.get('available') is True
          and len(unreadable) == 1,
          f"a corrupt log marks exactly that participant unreadable, panel "
          f"still available ({len(unreadable)} unreadable)")
    # PAIRED: the rest still aggregate — quiz1 now has 4 valid first attempts
    # (the corrupt one dropped), not zero, so the panel did not collapse.
    check(d2['passes']['first']['n_valid'] == 4
          and items_first(d2, 'quiz1')['n'] == 4,
          f"every other participant still aggregates "
          f"(n_valid={d2['passes']['first']['n_valid']})")

    # (c) FEATURE-MISSING (a renamed intro app / unreadable quiz_items) degrades
    #     to available:false — ok:true, NOT an error — so the panel shows a
    #     single 'no data' message. Paired against the available:true above.
    real_load = ed._load_quiz_items
    ed._load_quiz_items = lambda: None
    try:
        r = QM(qm.code)
        check(r.get('ok') is True and r.get('available') is False,
              f"feature-missing degrades to available:false (not an error): "
              f"ok={r.get('ok')}, available={r.get('available')}")
    finally:
        ed._load_quiz_items = real_load

    section('F3. blank admin-advance submissions are excluded AND counted')
    # A blank submission (every answer empty) is what oTree posts for 'advance
    # slowest participants'. It is dropped from the headline and the drop is
    # surfaced with its count. Planted directly for determinism (D5b proves the
    # real force-advance produces exactly this shape).
    qmb = ot.create_session('lab', num_participants=2)
    bcodes = ot.participant_codes(qmb)
    set_intro_log(bcodes[0], 1, [{'n': 1, 't': 1.0,
                  'answers': {'quiz1': '', 'quiz2': ''},
                  'wrong': ['quiz1', 'quiz2']}])
    set_intro_log(bcodes[1], 1, [{'n': 1, 't': 2.0,
                  'answers': {'quiz1': 'YES', 'quiz2': 'Metal'},
                  'wrong': ['quiz2']}])
    db_ = QM(qmb.code)
    check(db_['passes']['first']['n_excluded'] == 1,
          f"the blank submission is EXCLUDED and counted "
          f"(n_excluded={db_['passes']['first']['n_excluded']})")
    check(db_['passes']['first']['n_valid'] == 1,
          f"…and the real attempt still counts — the exclusion did not drop it "
          f"(n_valid={db_['passes']['first']['n_valid']})")
    forced = [p for p in db_['participants'] if p.get('first_excluded')]
    real = [p for p in db_['participants'] if p.get('first')]
    check(len(forced) == 1 and len(real) == 1,
          f"one participant reads force-advanced, the other carries real marks "
          f"({len(forced)} forced, {len(real)} real)")

    section('F4. the first pass and the re-read pass are NOT pooled')
    # Round 1 and round 2 are the two passes (a per-round column). Plant a
    # DIFFERENT wrong answer in each and check neither leaks into the other.
    qmp = ot.create_session('lab', num_participants=1)
    pcode = ot.participant_codes(qmp)[0]
    set_intro_log(pcode, 1, [{'n': 1, 't': 1.0,
                  'answers': {'quiz1': 'NO', 'quiz2': 'Water'},
                  'wrong': ['quiz1']}])          # first pass: quiz1 wrong (NO)
    set_intro_log(pcode, 2, [{'n': 1, 't': 2.0,
                  'answers': {'quiz1': 'YES', 'quiz2': 'Metal'},
                  'wrong': ['quiz2']}])          # re-read pass: quiz2 wrong
    dp = QM(qmp.code)
    check(dp['passes']['reread']['empty'] is False
          and dp['passes']['first']['n_valid'] == 1
          and dp['passes']['reread']['n_valid'] == 1,
          'both passes have one valid attempt and the re-read is not "empty"')
    q1f = items_first(dp, 'quiz1')
    q1r = items_reread(dp, 'quiz1')
    # First-pass quiz1 shows the wrong 'NO'; re-read quiz1 is all correct — if
    # the two were pooled, 'NO' would appear in the re-read options too.
    check(q1f['n_correct'] == 0
          and any(o['text'] == 'NO' and not o['correct']
                  for o in q1f['options']),
          f"first pass quiz1 carries the round-1 miss 'NO' ({q1f['options']})")
    check(q1r['n_correct'] == 1
          and all(o['text'] != 'NO' for o in q1r['options'])
          and all(o['correct'] for o in q1r['options']),
          f"the re-read pass does NOT carry that miss — the passes are not "
          f"pooled ({q1r['options']})")
    # And the mirror: quiz2 correct in the first pass, wrong only in the re-read.
    q2f = items_first(dp, 'quiz2')
    q2r = items_reread(dp, 'quiz2')
    check(q2f['n_correct'] == 1
          and any(o['text'] == 'Metal' and not o['correct']
                  for o in q2r['options']) and q2r['n_correct'] == 0,
          f"quiz2 is correct first pass, wrong ONLY in the re-read "
          f"(first {q2f['n_correct']}/{q2f['n']}, reread opts {q2r['options']})")

    section('F5. answer text is escaped')
    # The chosen-option text is participant-influenced and reaches the DOM; the
    # templates here do not auto-escape (a reflected XSS happened once). The
    # ENDPOINT carries the raw text (JSON transport is safe by construction) and
    # the PANEL escapes it at render with esc() — the real DOM escaping is
    # measured in dashboard_render_check.py. Here: the raw value round-trips,
    # AND the served page's panel renderer wraps every chosen text in esc().
    xss = '<img src=x onerror=alert(1)>'
    qmx = ot.create_session('lab', num_participants=1)
    xcode = ot.participant_codes(qmx)[0]
    set_intro_log(xcode, 1, [{'n': 1, 't': 1.0,
                  'answers': {'quiz1': xss, 'quiz2': 'Water'},
                  'wrong': ['quiz1']}])
    dx = QM(qmx.code)
    dx_opts = items_first(dx, 'quiz1')['options']
    check(any(o['text'] == xss for o in dx_opts),
          f"the endpoint carries the raw chosen text un-mangled ({dx_opts})")
    page_x = admin.get(f'{URL}/{qmx.code}').text
    check('esc(o.text)' in page_x and 'esc(m.chosen_text)' in page_x,
          'the served panel renderer escapes every chosen text with esc() — '
          'option breakdown and per-participant marks alike')
    # The served page ships the panel machinery: the trigger and the fetch.
    check('quiz-mistakes-info' in page_x and 'QM_URL' in page_x
          and 'qm-overlay' in page_x,
          'the served page ships the ⓘ trigger, the overlay and the '
          '/quiz_mistakes fetch')

    # ------------------------------------------------------------------ E
    section('E. strictly read-only')
    before = participant_dump()
    admin.get(f'{URL}/{lab.code}/data')
    admin.get(f'{URL}/{pro.code}/data')
    admin.get(f'{URL}/{lab.code}')
    # The quiz-mistakes endpoint is read-only too — building the aggregate must
    # not dirty a single row (it parses the log column, never assigns it).
    admin.get(f'{URL}/{lab.code}/quiz_mistakes')
    admin.get(f'{URL}/{qm.code}/quiz_mistakes')
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
