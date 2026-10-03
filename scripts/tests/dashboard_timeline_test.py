"""EXPERIMENTER MONITOR — the timeline is built PER SESSION from its own
app_sequence (experimenter_dashboard.timeline_for_apps, 2026-10-02).

Until then the monitor's steps were a fixed STEP_LABELS dict plus an APP_STEPS
map, and a study that added an app and forgot the map got every participant in
it rendered "not on the timeline" with nothing failing. This file proves the
replacement does what the operator needs, over the dashboard's real routes
(the in-process ASGI client, logged in through oTree's own login):

  T1. an app INSERTED between intro and main gets its own step, at the right
      position, labelled with its raw app name — header, JS STEPS, grid and
      the participant's marker all agree;
  T2. an app declaring C.MONITOR_LABEL shows that label, and a multi-round app
      that declares nothing gets the default "x of NUM_ROUNDS";
  T3. intro shows the round NUMBER only (C.MONITOR_ROUNDS = 'number');
  T4. main shows "x of N" with N = min(num_experimental_rounds, C.NUM_ROUNDS),
      the round capped at N;
  T5. the stall threshold is looked up by APP NAME
      (DASHBOARD_STALL_SECONDS_<APP>), else the default;
  T6. an app genuinely NOT in the session's app_sequence is still flagged
      unmapped — even a real app the template ships;
  T7. a terminal row in a session with an inserted app is placed where it
      happened, not one step early;
  T8. the launch-time warning names a config missing a name-bound app, and is
      silent for the shipped configs.

HOW THE INSERTED APPS EXIST WITHOUT TOUCHING THE REPO. The dashboard reads a
session's app_sequence from its stored config and an app's constants by
importing it. So the test (a) rewrites one throwaway session's stored
app_sequence and (b) registers tiny modules in sys.modules — nothing is written
under the project, and a participant's position is planted with the same
test-side write helper dashboard_test.py uses. Pages of the inserted apps are
never rendered (the participant flow is not what is under test here; the full
flows are other files' job), which is also the honest limit of this file.

PROVEN RED AGAINST THE OLD MODULE: run against the pre-2026-10-02
experimenter_dashboard.py, T1, T2, T3, T5, T6 and T7's inserted-app case fail
(see _ai/monitor_dynamic/REPORT.md for the transcript). T4 and T6's unknown-app
case are regression guards — the old code already did them.

Run: python scripts/tests/dashboard_timeline_test.py   (in-process; no server)
"""
import json
import os
import re
import sys
import time
import types

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402,F401  (also puts REPO_ROOT on sys.path)

os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

from otree_inprocess import boot  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

import experimenter_dashboard as ed  # noqa: E402

URL = ed.URL_BASE
_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def admin_client():
    c = ot.client()
    r = c.get('/login')
    token = re.search(r'name="csrftoken" value="([^"]+)"', r.text).group(1)
    c.post('/login', data={'username': 'admin', 'password': 'admin',
                           'csrftoken': token}, allow_redirects=False)
    return c


def set_participant(code, **fields):
    """Test-side WRITE helper (the dashboard itself never writes)."""
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


def place(code, app, page, round_number=1, seconds_on_page=5):
    """Plant a LIVE participant on a page, as oTree's own cursor records it."""
    set_participant(code, visited=True, _current_app_name=app,
                    _current_page_name=page, _round_number=round_number,
                    _index_in_pages=1,
                    _last_page_timestamp=int(time.time()) - seconds_on_page)


def set_app_sequence(session, apps):
    """Rewrite ONE throwaway session's stored app_sequence (test-side)."""
    from otree.database import DBSession
    from otree.models import Session
    s = DBSession()
    try:
        row = s.query(Session).filter_by(code=session.code).one()
        cfg = dict(row.config)
        cfg['app_sequence'] = list(apps)
        row.config = cfg
        s.commit()
    finally:
        s.close()


def fake_app(name, **constants):
    """A minimal importable app: a module with a `C`. Registered in
    sys.modules only, so nothing is written under the project."""
    mod = types.ModuleType(name)
    mod.C = type('C', (), dict(constants))
    sys.modules[name] = mod
    return mod


def snapshot(client, session):
    data = client.get(f'{URL}/{session.code}/data').json()
    assert data.get('ok'), data
    return data, {r['code']: r for r in data['rows'] if not r.get('error')}


def render_marker(data, code):
    """The marker text the dashboard's OWN JavaScript paints for one row,
    from a real /data payload, in headless Chromium (the page built exactly
    as a live session's is, by page_template_for_steps; fetch stubbed to
    return `data`). Returns None if the row painted no marker."""
    from playwright.sync_api import sync_playwright
    html = (ed.page_template_for_steps(data['timeline'])
            .replace('__CSS_HREF__', '').replace('__SESSION_CODE__', 'x')
            .replace('__SESSION_TITLE__', 'x').replace('__DATA_URL__', '/d')
            .replace('__POLL_MS__', '2000'))
    stub = ('<script>window.fetch=function(){return Promise.resolve('
            '{json:function(){return %s;}});};'
            'window.setInterval=function(){return 0};</script>'
            % json.dumps(data))
    html = html.replace('<head><meta charset="utf-8">',
                        '<head><meta charset="utf-8">' + stub, 1)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={'width': 1440, 'height': 800})
        pg.set_content(html)
        pg.wait_for_function(
            '() => document.querySelectorAll("#rows td.c-timeline").length')
        label = next(r['label'] or r['code'] for r in data['rows']
                     if r['code'] == code)
        text = pg.evaluate('''(label) => {
            for (const tr of document.querySelectorAll('#rows tr')) {
              const td = tr.querySelector('td.c-label');
              if (td && td.textContent.includes(label)) {
                const m = tr.querySelector('.tl .marker');
                return m ? m.textContent.trim() : null; } }
            return null; }''', label)
        b.close()
    return text


def page_derivations(page):
    header = re.search(r'<div class="tl-header">(.*?)</div>', page, re.S)
    labels = [x.replace('<wbr>', '') for x in re.findall(
            r'<span class="tl-hl">(.*?)</span>', header.group(1))] if header else []
    js = re.search(r'var STEPS = (\[[^\]]*\]);', page)
    try:
        steps = json.loads(js.group(1)) if js else None
    except ValueError:
        steps = js.group(1)
    return labels, steps


def main():
    admin = admin_client()
    import settings as user_settings

    # Two inserted apps. `extra_app` is NOT importable at all (raw-name label,
    # no constants); `labelled_app` declares a label and 4 rounds.
    fake_app('labelled_app', MONITOR_LABEL='Labelled Phase', NUM_ROUNDS=4)
    seq = ['before', 'intro', 'extra_app', 'labelled_app', 'main', 'outro']
    lab = ot.create_session('lab', num_participants=8,
                            modified_session_config_fields=dict(
                                num_experimental_rounds=3))
    set_app_sequence(lab, seq)
    codes = ot.participant_codes(lab)

    # ------------------------------------------------------------------ T1
    section('T1. an app inserted between intro and main is ON the timeline')
    place(codes[0], 'extra_app', 'SomePage')
    data, rows = snapshot(admin, lab)
    page = admin.get(f'{URL}/{lab.code}').text
    labels, js_steps = page_derivations(page)
    want_ids = ['before', 'instructions', 'quiz', 'extra_app', 'labelled_app',
                'main', 'outro', 'done']
    check(js_steps == want_ids,
          f"the page's JS STEPS are THIS session's app_sequence, intro split, "
          f"then done (got {js_steps})")
    check(labels[:4] == ['Entry', 'Instructions', 'Quiz', 'extra_app'],
          f'the inserted app sits between Quiz and the next app, labelled '
          f'with its RAW app name (got {labels})')
    check('repeat(8, minmax(0, 1fr))' in page,
          'the grid has one track per step of THIS session (8)')
    r = rows[codes[0]]
    check(r['step'] == 'extra_app' and r.get('unmapped_app') is None,
          f"a participant in the inserted app is placed ON it, not flagged "
          f"unmapped (got step={r['step']!r}, unmapped={r.get('unmapped_app')!r})")
    check(r.get('round') is None,
          'a single-round app with no declaration shows no round (hidden)')
    check([s.get('id') for s in data.get('timeline') or []] == want_ids,
          'the /data JSON ships the same timeline the page was drawn from')

    # ------------------------------------------------------------------ T2
    section('T2. C.MONITOR_LABEL is the header; undeclared rounds -> x of N')
    place(codes[1], 'labelled_app', 'Whatever', round_number=3)
    data, rows = snapshot(admin, lab)
    check(len(labels) > 4 and labels[4] == 'Labelled Phase',
          f'an app declaring C.MONITOR_LABEL is headed by it '
          f'(got {labels[4] if len(labels) > 4 else None!r})')
    r = rows[codes[1]]
    check(r['step'] == 'labelled_app' and r.get('round') == 3
          and r.get('round_total') == 4,
          f"a multi-round app declaring nothing shows 'x of C.NUM_ROUNDS' "
          f"(got {r['step']} {r.get('round')} of {r.get('round_total')})")

    # ------------------------------------------------------------------ T3
    section('T3. intro shows the round NUMBER only')
    place(codes[2], 'intro', 'instructing', round_number=2)
    place(codes[3], 'intro', 'quiz', round_number=1)
    data, rows = snapshot(admin, lab)
    r2, r3 = rows[codes[2]], rows[codes[3]]
    check(r2['step'] == 'instructions' and r2.get('round') == 2
          and r2.get('round_total') is None,
          f"a re-reader on the instructions shows '2', no total "
          f"(got {r2['step']} {r2.get('round')}/{r2.get('round_total')})")
    check(r3['step'] == 'quiz' and r3.get('round') == 1
          and r3.get('round_total') is None,
          f"first pass on the quiz shows '1', no total "
          f"(got {r3['step']} {r3.get('round')}/{r3.get('round_total')})")

    # ----------------------------------------------------------------- T3b
    section('T3b. a REAL re-reader (lab, intro round 2) reads "2" on screen')
    # T3 plants the cursor; this walks a real lab participant there, over the
    # in-process HTTP client: fail the quiz up to the threshold, take the
    # one-time re-read offer, land on the round-2 instructions. Then the
    # marker is checked where the operator reads it — rendered by the
    # dashboard's OWN JavaScript in Chromium from the real /data JSON — not
    # only in the JSON. A marker that hardcoded "1" (or dropped the round)
    # passes every JSON check above and fails here.
    import http_flow_test as hf
    from quiz_answers import WRONG
    rr = ot.create_session('lab', num_participants=1,
                           modified_session_config_fields=dict(
                               quiz_comprehension_max_failures=2))
    rcode = ot.participant_codes(rr)[0]
    ot.set_label(rcode, 'Seat 09')
    c = ot.client()
    resp = c.get(f'/InitializeParticipant/{rcode}', allow_redirects=True)
    reached = seen_quiz = False
    for _ in range(30):
        url = str(resp.url)
        if '/instructing/' in url and seen_quiz:
            reached = True
            break
        seen_quiz = seen_quiz or '/quiz/' in url
        fp = hf.FormParser()
        fp.feed(resp.text)
        if not fp.found_form:
            break
        on_quiz = '/quiz/' in url
        offered = 'value="Re-read the instructions"' in resp.text
        payload = hf.build_payload(
            fp.inputs, {'redoinstructions': '1' if offered else '0'}
            if on_quiz else {}, dict(WRONG) if on_quiz else {}, warn=False)
        resp = c.post(url.replace('http://testserver', ''), data=payload,
                      allow_redirects=True)
    check(reached, f'the walk reached the round-2 instructions by taking the '
                   f're-read offer (at {resp.url})')
    rdata, rrows = snapshot(admin, rr)
    r9 = rrows.get(rcode, {})
    check(r9.get('step') == 'instructions' and r9.get('round') == 2
          and r9.get('round_total') is None,
          f"the server sends round 2, no total, on the instructions step "
          f"(got {r9.get('step')} {r9.get('round')}/{r9.get('round_total')})")
    marker = render_marker(rdata, rcode)
    check(marker == '2',
          f'the operator SEES "2" in the re-reader\'s marker, not "1" '
          f'(rendered marker text: {marker!r})')
    check(marker not in ('1', '\u25cf', None),
          '…and specifically not the round-1 "1" or the plain dot')

    # ------------------------------------------------------------------ T4
    section('T4. main shows x of N, N = min(config rounds, C.NUM_ROUNDS)')
    from otree.common import get_models_module
    imported = int(get_models_module('main').C.NUM_ROUNDS)
    configured = int(lab.config.get('num_experimental_rounds'))
    check(configured < imported,
          f'the lab config runs FEWER rounds than main imported '
          f'({configured} < {imported}) — otherwise the cap proves nothing')
    place(codes[4], 'main', 'GameStart', round_number=2)
    place(codes[5], 'main', 'GameStart', round_number=imported)
    data, rows = snapshot(admin, lab)
    r4, r5 = rows[codes[4]], rows[codes[5]]
    check(r4['step'] == 'main' and r4.get('round') == 2
          and r4.get('round_total') == configured,
          f"round 2 of THIS session's {configured} "
          f"(got {r4.get('round')} of {r4.get('round_total')})")
    check(r5.get('round') == configured and r5.get('round_total') == configured,
          f"a cursor past the session's last round (skipped rounds) is capped "
          f"at {configured} (got {r5.get('round')} of {r5.get('round_total')})")
    check(labels[5:7] == ['Task', 'Questionnaire'],
          f'main and outro keep their header labels (got {labels[5:7]})')

    # ------------------------------------------------------------------ T5
    section('T5. the stall threshold is looked up by APP NAME')
    place(codes[0], 'extra_app', 'SomePage', seconds_on_page=100)
    user_settings.DASHBOARD_STALL_SECONDS_EXTRA_APP = 77
    try:
        data, rows = snapshot(admin, lab)
        r = rows[codes[0]]
        check(r['stall_limit'] == 77 and r['stalled'] is True,
              f'DASHBOARD_STALL_SECONDS_EXTRA_APP=77 governs the inserted app: '
              f'100s on its page is amber (limit={r["stall_limit"]}, '
              f'stalled={r["stalled"]})')
        check(r['stall_section'] == 'extra_app',
              f"the timing pill names the phase by its label "
              f"(got {r['stall_section']!r})")
        legend = {p['label']: p['seconds'] for p in data['stall_legend']}
        check(legend.get('extra_app') == 77,
              f'the header legend lists the inserted app with its threshold '
              f'(got {legend})')
        check(rows[codes[4]]['stall_limit'] == 180,
              'and main keeps its own (legacy DASHBOARD_STALL_SECONDS_TASK) '
              'threshold — the lookup is per app')
    finally:
        del user_settings.DASHBOARD_STALL_SECONDS_EXTRA_APP
    data, rows = snapshot(admin, lab)
    r = rows[codes[0]]
    default = int(getattr(user_settings, 'DASHBOARD_STALL_SECONDS_DEFAULT'))
    check(r['stall_limit'] == default and r['stalled'] is False,
          f'without its own line the app falls back to '
          f'DASHBOARD_STALL_SECONDS_DEFAULT ({default}); 100s is not amber '
          f'(limit={r["stall_limit"]})')

    # ------------------------------------------------------------------ T6
    section('T6. an app NOT in this session\'s app_sequence is still flagged')
    place(codes[6], 'not_in_this_session', 'Page')
    data, rows = snapshot(admin, lab)
    r = rows[codes[6]]
    check(r['step'] == ed.UNMAPPED_STEP
          and r.get('unmapped_app') == 'not_in_this_session',
          f"an unknown app is the loud unmapped row, naming the app "
          f"(got {r['step']!r}, {r.get('unmapped_app')!r})")
    # A REAL app the template ships, in a session whose sequence omits it: the
    # timeline is this session's, not a global registry of known apps.
    short = ot.create_session('lab', num_participants=1)
    set_app_sequence(short, ['before', 'intro', 'outro'])
    scode = ot.participant_codes(short)[0]
    place(scode, 'main', 'GameStart', round_number=2)
    sdata, srows = snapshot(admin, short)
    r = srows[scode]
    check(r['step'] == ed.UNMAPPED_STEP and r.get('unmapped_app') == 'main',
          f"a participant in 'main' of a session WITHOUT main is unmapped, "
          f"never silently placed (got {r['step']!r})")
    check([s['id'] for s in sdata.get('timeline') or []]
          == ['before', 'instructions', 'quiz', 'outro', 'done'],
          f"and that session's timeline has no Task step "
          f"(got {[s.get('id') for s in sdata.get('timeline') or []]})")
    # Presence paired with the absence: the same participant row in a session
    # that HAS main is placed normally (T4 above), so 'unmapped' here is about
    # the sequence, not about main.

    # ------------------------------------------------------------------ T7
    section('T7. terminal rows are placed where it happened')
    now = time.time()
    # Tab-monitor DQ on main's decision page, in the session WITH two apps
    # inserted after the quiz. The stamps alone say only "past the quiz",
    # which would put the emoji on extra_app; the server-recorded page of the
    # disqualifying focus loss puts it on main.
    set_participant(codes[7], visited=True, _current_app_name='outro',
                    _current_page_name='Ended', **{
                        'vars.stage_timestamps': {
                            'consent': now - 300, 'instructions_done': now - 200,
                            'quiz_done': now - 100},
                        'vars.tab_monitor_disqualified': True,
                        'vars.exit_code': -3,
                        'vars.tab_monitor_focus_events': [
                            dict(page='GameStart', region='task', ts=now - 10),
                            dict(page='Ended', region='questionnaire',
                                 ts=now - 5)]})
    data, rows = snapshot(admin, lab)
    r = rows[codes[7]]
    check(r['terminal'] == 'tab_monitor' and r['step'] == 'main',
          f"a tab-monitor DQ on main's page fills the marker at Task, not at "
          f"the inserted app after the quiz (got {r['terminal']}@{r['step']})")
    # Without the event: the step AFTER the last completed one — the inserted
    # app, which is the honest reading of "past the quiz, nothing more known".
    set_participant(codes[7], **{'vars.tab_monitor_focus_events': []})
    data, rows = snapshot(admin, lab)
    check(rows[codes[7]]['step'] == 'extra_app',
          f"with no recorded page, the marker is the step after the quiz "
          f"(got {rows[codes[7]]['step']!r})")

    # ------------------------------------------------------------------ T8
    section('T8. the launch-time warning for name-bound apps')
    problems_fn = getattr(ed, 'timeline_problems', None)
    check(callable(problems_fn), 'the dashboard exposes timeline_problems')
    if callable(problems_fn):
        warned = problems_fn([dict(name='fork', app_sequence=[
            'before', 'intro', 'survey', 'outro'])])
        check(any("'main'" in w and 'fork' in w for w in warned),
              f'a config without main is warned about by name (got {warned})')
        check(not any("'outro'" in w for w in warned),
              'and only for the app that is actually missing')
        check(problems_fn(user_settings.SESSION_CONFIGS) == [],
              'the shipped configs produce NO warning (so the warning, when it '
              'appears, means something)')
        clash = problems_fn([dict(name='c', app_sequence=[
            'before', 'intro', 'quiz', 'outro'])])
        check(any('collide' in w for w in clash),
              f"an app named like intro's 'quiz' sub-step is warned about "
              f"(got {clash})")

    print()
    if _failures:
        print(f'{len(_failures)} CHECK(S) FAILED')
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
