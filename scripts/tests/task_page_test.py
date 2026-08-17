"""MONITORED BY DEFAULT — the page bases really ARM their subclasses (B1).

This file began as the TaskPage test (J2: a task page silently unarmed for
the tab monitor is found in the data, not in a test). The same reasoning now
covers EVERY page after the agreement screen
(participant_tab_monitor.MonitoredPage / OutroMonitoredPage — the 2026-08-13
inversion), so this file proves the
generalised structure:

  1. every page of intro, main and outro IS a MonitoredPage subclass, and the
     bindings ARE the shared implementations (identity, not lookalikes) — the
     ejecting pair on intro/main, the record-only pair on outro;
  2. a FRESH subclass — the next study's page, written with zero wiring — is
     armed by subclassing alone, and the boot-time checker REFUSES a page
     that dodged the rule;
  3. end-to-end through oTree over real HTTP: the QUIZ page (the page the
     whole inversion existed to protect) and a task page both carry the
     monitor config and script; a page before the agreement carries the
     script (shipped via the bundle) but NO config, so it is inert; the
     inherited live_method counts a violation server-side;
  4. THE PHASE ASYMMETRY: the outro handler records into its OWN column
     (focus_loss_count_outro) and never disqualifies, however many arrive;
     the Results dispatcher serves both message types on one channel;
  5. the documented opt-out (`monitored = False`) disarms all the Python-side
     wiring in one stroke — and an explicit live_method override still works,
     while mere omission still inherits (the original gotcha).

Run: python scripts/tests/task_page_test.py     (boots oTree in-process; no server)
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

from otree_inprocess import boot, path_of, page_name_of

ot = boot(production=True)          # MUST come before any app import

import common
import participant_tab_monitor
import main
import intro
import outro

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


DESKTOP = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/126.0.0.0 Safari/537.36')}


def payload_for(page, quiz_answers):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'ConfirmProlificID': {'participant_id_external': ''},
        'instructing': {},
        'quiz': dict(quiz_answers),
        'AISafetyAgree': {},
    }.get(page, {})


def main_test():
    from intro.quiz_items import QUIZ_ITEMS
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}

    section('1. every post-agreement page inherits the wiring — identity, not copies')
    # The ejecting phase: intro's pages and the task pages.
    for cls in (intro.instructing, intro.quiz, main.GameStart, main.payoff):
        check(issubclass(cls, participant_tab_monitor.MonitoredPage),
              f'{cls.__module__}.{cls.__name__} subclasses MonitoredPage')
        check(cls.live_method is common.focus_live_method,
              f'{cls.__name__}.live_method IS common.focus_live_method '
              f'(the ejecting handler, one implementation)')
        check(cls.js_vars is common.monitor_js_vars,
              f'{cls.__name__}.js_vars IS common.monitor_js_vars')
    check(issubclass(main.TaskPage, participant_tab_monitor.MonitoredPage),
          'TaskPage itself subclasses MonitoredPage (generalised, not duplicated)')
    for cls in (main.GameStart, main.payoff):
        check(cls.is_displayed is main.task_page_visible,
              f'{cls.__name__}.is_displayed IS task_page_visible')
    # The record-only phase: the outro pages.
    for cls in (outro.Ended, outro.Demographics, outro.Feedback):
        check(issubclass(cls, participant_tab_monitor.OutroMonitoredPage),
              f'outro.{cls.__name__} subclasses OutroMonitoredPage')
        check(cls.live_method is common.focus_live_method_outro,
              f'{cls.__name__}.live_method IS the record-only handler')
        check(cls.js_vars is common.monitor_js_vars_outro,
              f'{cls.__name__}.js_vars IS the record-only js_vars '
              f'(ejects: false reaches the client)')
    # Results overrides the channel — legitimately, because it DELEGATES.
    check(outro.Results.live_method is not common.focus_live_method_outro
          and outro.Results.live_method is not None,
          'Results carries its own live_method (the click+monitor dispatcher)'
          ' — delegation proven in section 4')

    section('2. a fresh subclass is armed by subclassing ALONE, and dodging fails the boot')
    class NextStudysPage(main.TaskPage):
        template_name = 'main/game.html'

    check(NextStudysPage.live_method is common.focus_live_method
          and NextStudysPage.js_vars is common.monitor_js_vars
          and NextStudysPage.is_displayed is main.task_page_visible,
          'a subclass with an EMPTY body carries the full wiring — forgetting '
          'is structurally impossible')
    from otree.api import Page
    class Dodger(Page):
        pass
    try:
        participant_tab_monitor.assert_monitored_page_sequence('fake_app', [Dodger])
        check(False, 'the checker REFUSES a plain-Page dodger')
    except TypeError as exc:
        check('monitored' in str(exc),
              'the checker REFUSES a plain-Page dodger, naming the rule')
    for app, seq in (('intro', intro.page_sequence),
                     ('main', main.page_sequence),
                     ('outro', outro.page_sequence)):
        try:
            participant_tab_monitor.assert_monitored_page_sequence(app, seq)
            check(True, f'{app}.page_sequence passes the checker')
        except TypeError as exc:
            check(False, f'{app}.page_sequence passes the checker ({exc})')

    section('3. end-to-end: the bindings reach real served pages')
    sess = ot.create_session('prolific', num_participants=1)
    code = ot.participant_codes(sess)[0]
    client = ot.client()
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True,
                      headers=DESKTOP)
    # The consent page: BEFORE the agreement. The script ships (the bundle is
    # universal) but there is no monitor config, so it is inert by design.
    check(page_name_of(path_of(resp)) == 'welcome', 'entered on the consent page')
    check('ai_safety_monitor.js' in resp.text,
          'the monitor script ships to a pre-agreement page (universal bundle)…')
    check('AI_SAFETY_CONFIG' not in resp.text,
          '…but WITHOUT monitor config in its js_vars: inert, by design')
    quiz_html = None
    for _ in range(30):
        page = page_name_of(path_of(resp))
        if page == 'quiz' and quiz_html is None:
            quiz_html = resp.text
        if page in (None, 'GameStart'):
            break
        resp = client.post(path_of(resp), data=payload_for(page, correct),
                           allow_redirects=True, headers=DESKTOP)
    check(page_name_of(path_of(resp)) == 'GameStart',
          'walked a prolific participant onto the task page')
    check(quiz_html is not None
          and 'AI_SAFETY_CONFIG' in quiz_html
          and 'ai_safety_monitor.js' in quiz_html
          and '"ejects": true' in quiz_html.replace("'", '"'),
          'THE QUIZ PAGE carries the monitor config, script and ejecting '
          'phase — the page the inversion existed to protect')
    html = resp.text
    check('AI_SAFETY_CONFIG' in html and 'ai_safety_monitor.js' in html,
          'the served task page carries the monitor config and script')
    check('max_violations' in html,
          'the config in the page carries the configured thresholds '
          '(common.monitor_js_vars ran)')
    check('progress-strip' in html,
          'the shared progress-strip include rendered (task_template_vars '
          'delivered its numbers)')
    from otree.database import DBSession
    from otree.models import Participant
    from otree.common import get_models_module
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        MainPlayer = get_models_module('main').Player
        pl = (s.query(MainPlayer)
              .filter(MainPlayer.participant_id == p.id,
                      MainPlayer.round_number == 1).one())
        main.GameStart.live_method(pl, {'type': 'focus_loss', 'event_id': 'e1'})
        s.commit()
        count = p.vars.get('focus_loss_count')
        check(count == 1,
              f'the inherited live_method counts a violation server-side '
              f'(focus_loss_count={count})')

        section('4. the phase asymmetry: outro records, never ejects')
        OutroPlayer = get_models_module('outro').Player
        opl = (s.query(OutroPlayer)
               .filter(OutroPlayer.participant_id == p.id).one())
        max_v = int(sess.config['tab_monitor_max_violations'])
        rets = []
        for i in range(max_v + 2):     # well past the ejection threshold
            rets.append(outro.Ended.live_method(
                opl, {'type': 'focus_loss', 'event_id': f'o{i}'}))
        s.commit()
        check(p.vars.get('focus_loss_count_outro') == max_v + 2,
              f'outro violations land in their OWN column '
              f'(focus_loss_count_outro={p.vars.get("focus_loss_count_outro")})')
        check(p.vars.get('focus_loss_count') == 1,
              'the ejecting-phase count is untouched by outro violations — '
              'an analyst can tell the phases apart')
        check(not p.vars.get('ai_safety_disqualified')
              and p.vars.get('exit_code') != common.EXIT_CODES['tab_monitor'],
              f'{max_v + 2} outro violations (threshold {max_v}) disqualify '
              f'NOBODY and never touch the exit code')
        check(all(r is None for r in rets),
              'the record-only handler never broadcasts a disqualification')
        # The Results dispatcher: one channel, two message types.
        outro.Results.live_method(
            opl, {'type': 'focus_loss', 'event_id': 'r1'})
        s.commit()
        check(p.vars.get('focus_loss_count_outro') == max_v + 3,
              'Results DELEGATES focus messages to the record-only handler '
              '(the one-live_method-per-page dispatcher)')
        outro.Results.live_method(opl, {'type': 'prolific_return_click'})
        s.commit()
        stamps = p.vars.get('stage_timestamps') or {}
        check(common.STAGE_PROLIFIC_RETURN_CLICKED in stamps,
              '…and still stamps the return click on the same channel')
        # The event-id dedup is SHARED across phases: a replayed id counts once.
        outro.Ended.live_method(opl, {'type': 'focus_loss', 'event_id': 'e1'})
        s.commit()
        check(p.vars.get('focus_loss_count_outro') == max_v + 3,
              'an event id already counted in the ejecting phase cannot be '
              'counted again in the outro (shared dedup)')
        # The client is TOLD its phase: the outro's js_vars say ejects: false
        # (no overlay, no threatening modal — see ai_safety_monitor.js), the
        # task's say true.
        check(outro.Ended.js_vars(opl)['AI_SAFETY_CONFIG']['ejects'] is False,
              "an outro page's js_vars carry ejects: false — the client shows "
              'no overlay and no warning modal in the record-only phase')
        check(main.GameStart.js_vars(pl)['AI_SAFETY_CONFIG']['ejects'] is True,
              "…and a task page's carry ejects: true")
    finally:
        s.close()

    section('5. the documented opt-out — one explicit switch, not omission')
    class OptedOut(participant_tab_monitor.MonitoredPage):
        monitored = False

    check(OptedOut.live_method is None,
          '`monitored = False` unbinds the live handler')
    check(OptedOut.js_vars is participant_tab_monitor.unmonitored_js_vars,
          '…and swaps js_vars for the empty builder — CALLABLE, never None '
          '(oTree calls js_vars at render, so None would be a 500)')
    class OwnFeature(participant_tab_monitor.MonitoredPage):
        monitored = False
        @staticmethod
        def live_method(player, data):
            return 'mine'
    check(OwnFeature.live_method is not None,
          'an opted-out page keeps its OWN (non-monitor) live feature')
    class Unmonitored(main.TaskPage):
        live_method = None
    check(Unmonitored.live_method is None,
          'an EXPLICIT live_method override still unbinds (the original escape)')
    class Forgot(main.TaskPage):
        pass
    check(Forgot.live_method is common.focus_live_method,
          '…and mere omission does NOT unbind — it inherits, which is the '
          'gotcha the docstrings warn about')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main_test()
