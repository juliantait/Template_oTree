"""TASKPAGE — the task-page base class really ARMS its subclasses (J2).

The whole value of TaskPage is structural: a page that subclasses it cannot be
silently unarmed for the tab monitor, because the wiring is inherited rather
than retyped. So this file proves the structure rather than trusting the class
body:

  1. the shipped pages ARE subclasses and their bindings ARE the shared
     implementations (identity, not lookalikes);
  2. a FRESH subclass — the next study's page, written with zero wiring — is
     armed by subclassing alone;
  3. end-to-end through oTree's machinery over real HTTP: a served task page
     carries the monitor config and script that only the inherited js_vars /
     template gate can have put there, and the live route accepts a focus-loss
     message counted by the inherited live_method;
  4. the documented unbind gotcha works as documented: a page that must NOT
     bind the monitor needs an EXPLICIT override, and an explicit override
     does unbind.

Run: python tests/task_page_test.py     (boots oTree in-process; no server)
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, os.path.dirname(_TESTS_DIR))

from otree_inprocess import boot, path_of, page_name_of

ot = boot(production=True)          # MUST come before any app import

import common
import main

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

    section('1. the shipped pages inherit the wiring — identity, not copies')
    for cls in (main.GameStart, main.payoff):
        check(issubclass(cls, main.TaskPage),
              f'{cls.__name__} subclasses TaskPage')
        check(cls.live_method is common.focus_live_method,
              f'{cls.__name__}.live_method IS common.focus_live_method '
              f'(the monitor contract, one implementation)')
        check(cls.js_vars is main.ai_safety_js_vars,
              f'{cls.__name__}.js_vars IS ai_safety_js_vars')
        check(cls.is_displayed is main.task_page_visible,
              f'{cls.__name__}.is_displayed IS task_page_visible')

    section('2. a fresh subclass is armed by subclassing ALONE')
    # The next study's page, written the way the docstring tells them to:
    # subclass, add content, type no wiring.
    class NextStudysPage(main.TaskPage):
        template_name = 'main/game.html'

    check(NextStudysPage.live_method is common.focus_live_method
          and NextStudysPage.js_vars is main.ai_safety_js_vars
          and NextStudysPage.is_displayed is main.task_page_visible,
          'a subclass with an EMPTY body carries the full wiring — forgetting '
          'is structurally impossible')

    section('3. end-to-end: the inherited bindings reach a real served page')
    # Prolific config: tab_monitor is ON, so the inherited js_vars and the
    # template gate must put the monitor config + script into the page.
    sess = ot.create_session('prolific', num_participants=1)
    code = ot.participant_codes(sess)[0]
    client = ot.client()
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True,
                      headers=DESKTOP)
    for _ in range(30):
        page = page_name_of(path_of(resp))
        if page in (None, 'GameStart'):
            break
        resp = client.post(path_of(resp), data=payload_for(page, correct),
                           allow_redirects=True, headers=DESKTOP)
    check(page_name_of(path_of(resp)) == 'GameStart',
          'walked a prolific participant onto the task page')
    html = resp.text
    check('AI_SAFETY_CONFIG' in html and 'ai_safety_monitor.js' in html,
          'the served page carries the monitor config and script — the '
          'inherited js_vars and template include, through oTree itself')
    check('max_violations' in html,
          'the config in the page carries the configured thresholds '
          '(ai_safety_js_vars ran)')
    check('progress-strip' in html,
          'the shared progress-strip include rendered (task_template_vars '
          'delivered its numbers)')
    # The live channel: send the focus-loss message the client monitor sends
    # and check the INHERITED live_method counted it server-side.
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
    finally:
        s.close()

    section('4. the documented unbind gotcha — explicit override, not omission')
    # oTree resolves page attributes at import, so a page that must NOT bind
    # the monitor cannot just omit something (it inherits). The docstring says
    # the unbind is an explicit override — prove that works, and that omission
    # really does inherit (the very trap the docstring warns about).
    class Unmonitored(main.TaskPage):
        live_method = None
        js_vars = None

    check(Unmonitored.live_method is None and Unmonitored.js_vars is None,
          'an EXPLICIT override unbinds the monitor (the documented escape)')
    class Forgot(main.TaskPage):
        pass
    check(Forgot.live_method is common.focus_live_method,
          '…and mere omission does NOT unbind — it inherits, which is the '
          'gotcha the docstring exists to warn about')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main_test()
