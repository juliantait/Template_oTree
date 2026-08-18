"""THE SLIDER ELICITATION PAYS WHAT WAS CHOSEN — the proof for the shipped
placeholder task (main/game.html, the reference example a study copies).

The task is one slider that picks a payoff. The single most important rule for
any replacement task (docs/skills_claude/writing_task.md) is that the chosen
value must reach participant payoff and task_done must be stamped, or every
participant is silently paid show-up (plus quiz bonus) only. This walks it end
to end over real HTTP-shaped requests (the in-process client) and asserts:

  1. A participant who moves the slider HIGH is paid that: payoff_vector holds
     the chosen value on every round, and participant.payoff exceeds the
     show-up fee by the selected rounds' worth of it.
  2. task_done is stamped (finish_task_block ran on the last round).
  3. A NO-JS / untouched submit is SAFE: the slider posts EMPTY, no page 500s,
     the round pays 0, and the participant still completes — paid show-up (plus
     quiz bonus) and nothing from the never-made choices.

Run: python scripts/tests/slider_payoff_test.py   (boots oTree in-process; no server)
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

import common                        # noqa: E402  (the config accessor)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def payload_for(page, quiz_answers, slider_value):
    """One walk's per-page form data. `slider_value` is what the task page
    posts for the slider — a real value, or '' for the untouched/no-JS case."""
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'ConfirmProlificID': {'participant_id_external': 'PROLIFICTEST01'},
        'instructing': {},
        'quiz': dict(quiz_answers),
        # The slider is posted DIRECTLY here (not via main_contract) so this
        # test controls the value — the whole point of the proof.
        'GameStart': {'slider_payoff_points': slider_value, 'client_ms': ''},
        'payoff': {},
        'Demographics': {'age': '30', 'gender': 'Female',
                         'bank': 'NL91ABNA0417164300',
                         'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def walk_to_results(client, code, quiz_answers, slider_value, max_steps=120):
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None or page == 'Results':
            return resp
        resp = client.post(path_of(resp),
                           data=payload_for(page, quiz_answers, slider_value),
                           allow_redirects=True)
        # A no-JS empty slider must NOT 500 anywhere along the walk.
        assert resp.status_code == 200, f'walk {page}: HTTP {resp.status_code}'
    raise AssertionError('never reached Results')


def participant_row(code):
    """(participant.payoff, earned, payoff_vector, stage_timestamps)."""
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        OutroPlayer = get_models_module('outro').Player
        row = (s.query(OutroPlayer)
               .filter(OutroPlayer.participant_id == p.id).first())
        earned = row.field_maybe_none('earned') if row else None
        return (float(p.payoff),
                None if earned is None else float(earned),
                list(p.vars.get('payoff_vector') or []),
                dict(p.vars.get('stage_timestamps') or {}))
    finally:
        s.close()


def main():
    from quiz_answers import CORRECT   # one derivation, from the shipped items
    correct = dict(CORRECT)

    # 'test' config: 3 rounds, lab profile (bank/demographics off is fine — the
    # walker fills them if asked). USE_POINTS=False, participation_fee=0.
    ROUNDS = 3
    HIGH = 88   # a clearly-high, in-range (0..100) chosen payoff

    section('1. a participant who moves the slider HIGH is paid that')
    sess = ot.create_session('test', num_participants=2)
    codes = ot.participant_codes(sess)
    cfg = sess.config
    show_up = float(common.cfg(cfg, 'payment_show_up'))
    num_rewarded = int(common.cfg(cfg, 'payment_num_rewarded'))
    quiz_bonus = float(common.cfg(cfg, 'payment_quiz_bonus'))

    walk_to_results(ot.client(), codes[0], correct, str(HIGH))
    payoff, earned, vector, stamps = participant_row(codes[0])

    check(len(vector) == ROUNDS,
          f'payoff_vector holds every round ({vector}) — finish_task_block '
          f'collected the task block')
    check(all(float(v) == HIGH for v in vector),
          f'every round records the CHOSEN slider value ({HIGH}), not a '
          f'random/default number ({vector})')
    check(common.STAGE_TASK_DONE in stamps,
          f'task_done is stamped ({common.STAGE_TASK_DONE!r} present) — the '
          f'dashboard/export task boundary is set')
    # The high choice actually reaches the money: earned exceeds the show-up fee
    # by exactly the selected rounds' worth of the chosen value (plus the quiz
    # bonus a clean walk earns). Correct-quiz walk -> bonus awarded.
    expected = show_up + num_rewarded * HIGH + quiz_bonus
    check(earned is not None and abs(earned - expected) < 1e-9,
          f'earned == show-up + {num_rewarded}x{HIGH} + quiz bonus '
          f'({show_up} + {num_rewarded*HIGH} + {quiz_bonus} = {expected}); got {earned}')
    check(payoff == earned,
          f'participant.payoff EQUALS earned ({payoff}) — the chosen value '
          f'reached the ONE ledger the admin and receipt both read')
    check(payoff > show_up,
          f'…and it is MORE than just the show-up fee ({payoff} > {show_up}): '
          f'a high slider is paid, not ignored')

    section('2. a NO-JS / untouched slider is safe (empty -> 0, no 500)')
    # Post the slider EMPTY on every round, as a scriptless browser that never
    # filled it would (the walker asserts no 500 the whole way).
    walk_to_results(ot.client(), codes[1], correct, '')
    payoff0, earned0, vector0, stamps0 = participant_row(codes[1])
    check(len(vector0) == ROUNDS and all(float(v) == 0 for v in vector0),
          f'an empty slider stores 0 for every round ({vector0}) — blank is '
          f'stored, never rejected')
    check(common.STAGE_TASK_DONE in stamps0,
          'task_done is stamped even for the empty walk — the participant still '
          'completes')
    expected0 = show_up + quiz_bonus   # no decision bonus: nothing was chosen
    check(earned0 is not None and abs(earned0 - expected0) < 1e-9,
          f'earned == show-up + quiz bonus only ({expected0}); got {earned0} — '
          f'paid the guaranteed parts, nothing from choices never made')
    check(payoff0 == earned0,
          f'participant.payoff EQUALS earned ({payoff0}) for the empty walk too')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
