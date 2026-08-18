#!/usr/bin/env python
"""Every graded quiz submission reaches the data — in order, with correctness.

`intro.Player.quiz_attempt_log` exists to answer "which ITEMS do people get
wrong", which the failure COUNT cannot. That claim is only true if the log is
actually written on a submission that FAILS VALIDATION — the exact request in
which oTree re-renders the page with an error, and the one where a write that
was not persisted would go unnoticed (nothing 500s; the column is just short).

So this drives the real quiz over the ASGI stack: a wrong submission, then a
right one, then reads the column back through the ORM and asserts the ORDER and
the per-item CORRECTNESS FLAGS. It also pins that the log is
UNCAPPED (a determined clicker's attempts are all kept) and that the re-read
shortcut is not logged as an attempt.

Study-AGNOSTIC: it derives the answers from `intro/quiz_items.py`, so it keeps
working when you write your own quiz.

Run:  python scripts/tests/quiz_attempt_log_test.py
Exit 0 = all checks passed. Boots no server and never touches the real database.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

# PRODUCTION: DEBUG off is the build participants get, and quiz_verify=False
# would skip grading entirely (and so log nothing).
ot = boot(production=True)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


PAYLOAD = {
    'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                'participant_id_url': ''},
    'ConfirmProlificID': {'participant_id_external': 'attempt-log'},
    'instructing': {},
}


def walk_to_quiz(client, code, limit=20):
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(limit):
        page = page_name_of(path_of(resp))
        if page == 'quiz' or page is None:
            return resp
        resp = client.post(path_of(resp), data=PAYLOAD.get(page, {}),
                           allow_redirects=True)
    raise AssertionError('never reached the quiz')


def read_log(session_code, participant_code, round_number=1):
    """The parsed attempt log for one participant's intro round."""
    from otree.database import DBSession
    from otree.models import Participant
    from intro import Player
    s = DBSession()
    try:
        pid = s.query(Participant).filter_by(code=participant_code).one().id
        row = (s.query(Player)
               .filter_by(participant_id=pid, round_number=round_number).one())
        # field_maybe_none: the column is nullable until first written.
        raw = row.field_maybe_none('quiz_attempt_log') or ''
        return json.loads(raw) if raw else []
    finally:
        s.close()


def main():
    from intro.quiz_items import QUIZ_ITEMS

    client = ot.client()
    session = ot.create_session('lab', num_participants=4)
    codes = ot.participant_codes(session)

    from quiz_answers import CORRECT, WRONG   # one derivation, from the shipped items
    correct = dict(CORRECT)
    first = QUIZ_ITEMS[0]
    wrong_answer = WRONG[first['field']]
    wrong = dict(correct, **{first['field']: wrong_answer})

    # ---- 1. fail once, then pass: two entries, in order --------------------
    section('1. A participant who fails once then passes logs both attempts')
    resp = walk_to_quiz(client, codes[0])
    after_wrong = client.post(path_of(resp), data=wrong, allow_redirects=True)
    check(page_name_of(path_of(after_wrong)) == 'quiz',
          'the wrong submission re-rendered the quiz (it was graded)')
    after_right = client.post(path_of(after_wrong), data=correct,
                              allow_redirects=True)
    check(page_name_of(path_of(after_right)) != 'quiz',
          'the correct submission advanced past the quiz')

    log = read_log(session.code, codes[0])
    check(len(log) == 2, f'two attempts were logged (got {len(log)})')
    if len(log) == 2:
        a, b = log
        check([a['n'], b['n']] == [1, 2],
              f"numbered 1 then 2 in order (got {[a['n'], b['n']]})")
        check(a['wrong'] == [first['field']],
              f"attempt 1 records exactly the item that was wrong "
              f"(got {a['wrong']!r}, expected [{first['field']!r}])")
        check(a['answers'].get(first['field']) == wrong_answer,
              'attempt 1 records the WRONG value that was submitted')
        check(b['wrong'] == [],
              f"attempt 2 records no wrong items (got {b['wrong']!r})")
        check(b['answers'] == correct,
              'attempt 2 records the passing answers')
        check(set(a['answers']) == set(correct),
              'every item is present in the answers of an attempt')
        check(isinstance(a['t'], (int, float)) and a['t'] > 0
              and b['t'] >= a['t'],
              'both attempts carry a timestamp, non-decreasing')

    # ---- 2. a first-time pass logs exactly one attempt ---------------------
    section('2. A first-time pass logs one attempt, and it is a pass')
    resp = walk_to_quiz(client, codes[1])
    client.post(path_of(resp), data=correct, allow_redirects=True)
    log = read_log(session.code, codes[1])
    check(len(log) == 1, f'one attempt logged (got {len(log)})')
    check(bool(log) and log[0]['wrong'] == [],
          'and it is recorded as passing (wrong == [])')

    # ---- 3. uncapped: a determined clicker's attempts are ALL kept ---------
    section('3. The log is uncapped — every attempt is stored')
    resp = walk_to_quiz(client, codes[2])
    many = 25
    for _ in range(many):
        resp = client.post(path_of(resp), data=wrong, allow_redirects=True)
    log = read_log(session.code, codes[2])
    check(len(log) == many,
          f'all {many} submissions are stored, none dropped (got {len(log)})')
    check([e['n'] for e in log] == list(range(1, many + 1)),
          'numbered 1..N with no gaps')
    check(all(e['wrong'] == [first['field']] for e in log),
          'every one of them records the same wrong item')
    check(page_name_of(path_of(resp)) == 'quiz',
          f'and the participant is still on the quiz after {many} wrong '
          f'submissions — the lab never caps attempts')

    # ---- 4. the re-read shortcut is not an attempt -------------------------
    section('4. Taking the re-read offer is not logged as an attempt')
    # A lab session: quiz_reread is on, so crossing the threshold opens the
    # offer, and submitting redoinstructions=1 returns before grading.
    threshold = int(session.config['quiz_comprehension_max_failures'])
    resp = walk_to_quiz(client, codes[3])
    for _ in range(threshold):
        resp = client.post(path_of(resp), data=wrong, allow_redirects=True)
    before_log = read_log(session.code, codes[3])
    resp = client.post(path_of(resp), data=dict(wrong, redoinstructions='1'),
                       allow_redirects=True)
    after_log = read_log(session.code, codes[3])
    check(len(after_log) == len(before_log),
          f'the re-read submission added no entry '
          f'({len(before_log)} -> {len(after_log)} entries)')
    check(page_name_of(path_of(resp)) != 'quiz',
          f'and it moved the participant off the quiz '
          f'(now {page_name_of(path_of(resp))})')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
