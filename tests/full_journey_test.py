#!/usr/bin/env python
"""THE FULL JOURNEY: one participant, room entry to the final page, over real HTTP.

    # server on a THROWAWAY database:
    OTREE_ADMIN_PASSWORD=admin otree devserver 8000
    # then:
    python tests/full_journey_test.py http://localhost:8000

=============================================================================
DO NOT TRIM THIS TEST FOR TIME, AND DO NOT DELETE IT.
=============================================================================
It is the slowest suite here — it walks every round of the real study, twice
over — and it will therefore be the first thing somebody proposes to shorten.
Do not. THIS IS THE ONLY TEST THAT PROVES A PARTICIPANT CAN ACTUALLY FINISH
THE STUDY.

Every other suite in this folder exercises a SLICE: the entry gate, the
screen-out lifecycle, the identity lookup, the layout, one config's flow to
"some ending page". A study can be broken in a way that no slice catches —
a page that only 500s on round 7, a flag that strands a participant between
apps, a page sequence that never actually reaches Results — and each slice
still reports PASS, because each one is looking somewhere else. The only way
to know a participant can get from the recruitment link to the end is to send
one, the whole way, and check where they landed.

Specifically, the three things it will not do if you shorten it:

  * RUN AT THE REAL ROUND COUNT. A three-round clickthrough proves nothing
    about a ten-round study; the round loop is the part of the flow that
    repeats, and repetition is where an off-by-one strands people.
  * FAIL THE QUIZ ONCE. This is part of the journey, not a separate case. A
    wrong submission RE-RENDERS a page mid-flow — the one moment the
    participant is bounced back instead of forward — and it is where a
    participant is most likely to get stuck. A journey that only ever answers
    correctly never touches that path.
  * ASSERT THE EXIT CODE. "Reached a page with an ending on it" is not
    finishing. `outro/Ended.html` (disqualified, no-consent) and
    `outro/Results.html` (finished) BOTH carry the words "Back to Prolific",
    so a text-matching walk cannot tell being thrown out from completing —
    `tests/http_flow_test.py` genuinely cannot distinguish them. This test
    asserts `participant.exit_code == EXIT_CODES['finished']` (1), read back
    over the REST API, which is the only unambiguous statement that the
    participant finished.

WHAT IT WALKS. One participant, entering through the ROOM the way a real
recruitment link does (`/room/<name>?participant_label=…`), which is also the
path that goes through oTree's label lookup — the one `identity.py` guards.
Then every page in the real order, at the config's real
`num_experimental_rounds`, with one deliberately failed quiz attempt on the
way, ending on Results with exit code 1.

Run for BOTH shipped real configs (`prolific` and `lab`), one participant
each, because the two have genuinely different page sequences: prolific has
the id confirmation and the monitor arming page, lab has the hold screen and
the bank/demographics page. Each journey completes before the next begins, so
rebinding the room between them strands nobody (see "Rebinding a room
mid-study" in README.md).

Exit 0 = the participant finished. Never touches a real database.
"""
import importlib.util
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http_flow_test import FormParser, build_payload  # noqa: E402
from main_contract import TASK_PAGES  # noqa: E402  (the one task-page contract)

ROOM = 'experiment'
DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# A study that has configured its way out. `prolific_screenout_return_url` ships as a
# REPLACE_* placeholder on purpose (settings.SCREENOUT_RETURN_URL_PLACEHOLDER);
# no participant on this journey is ever screened out, but a real study has it
# set, so the journey is driven as a real study would be configured.
CONFIGURED_RETURN_URL = 'https://app.prolific.com/'

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def load_quiz_items():
    """The quiz items, loaded straight from the file.

    By path, not `from intro.quiz_items import …`: that would execute
    `intro/__init__.py`, which needs oTree configured, and this test drives a
    SEPARATE server process. Loading the module by path also means the correct
    answers do not come from the page under test — a quiz that stopped sending
    its DEBUG solutions, or sent the wrong ones, cannot make this test agree
    with it.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'intro', 'quiz_items.py')
    spec = importlib.util.spec_from_file_location('_quiz_items', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.QUIZ_ITEMS


QUIZ_ITEMS = load_quiz_items()
CORRECT = {i['field']: i['answer'] for i in QUIZ_ITEMS}
# A definite WRONG answer per item: any listed choice that is not the answer.
WRONG = {i['field']: next(c for c in i['choices'] if c != i['answer'])
         for i in QUIZ_ITEMS}


def page_name(url):
    """/p/<code>/<app>/<PageName>/<index> -> PageName (None off the flow)."""
    parts = str(url).split('?')[0].strip('/').split('/')
    # tolerate an absolute URL: find the '/p/' segment
    if 'p' in parts:
        i = parts.index('p')
        if len(parts) >= i + 5:
            return parts[i + 3]
    return None


def participant_code(url):
    parts = str(url).split('?')[0].strip('/').split('/')
    if 'p' in parts:
        i = parts.index('p')
        if len(parts) >= i + 2:
            return parts[i + 1]
    return None


def create_room_session(base, config, label):
    """Create a session BOUND TO THE ROOM, with one participant."""
    r = requests.post(base + '/api/sessions', json={
        'session_config_name': config,
        'num_participants': 1,
        'room_name': ROOM,
        'modified_session_config_fields': {
            'prolific_screenout_return_url': CONFIGURED_RETURN_URL},
    })
    r.raise_for_status()
    return r.json()


def session_config(base, session_code):
    r = requests.post(base + f'/api/get_session/{session_code}', json={})
    r.raise_for_status()
    return r.json()['config']


def participant_state(base, session_code, names):
    """Participant fields read back over the REST API (the authoritative record)."""
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': list(names)})
    r.raise_for_status()
    parts = r.json()['participants']
    return parts[0] if parts else {}


def enter_room(session_obj, label):
    """Enter through the room, exactly as a recruitment link does.

    `welcome_page_ok=1` is what oTree's own room welcome page adds when the
    participant clicks through it (otree/views/participant.py:
    AssignVisitorToRoom renders that page first and assigns a row only on the
    second request). This skips the click, not the assignment — and the
    assignment is the label lookup that identity.py guards.
    """
    s = requests.Session()
    s.headers['User-Agent'] = DESKTOP_UA
    base = session_obj['_base']
    r = s.get(f'{base}/room/{ROOM}?participant_label={label}&welcome_page_ok=1',
              allow_redirects=True)
    return s, r


def journey(base, config, label):
    """Drive ONE participant all the way through, and assert they finished."""
    section(f'{config}: one participant, room entry to the final page')
    created = create_room_session(base, config, label)
    created['_base'] = base
    session_code = created['code']
    cfg = session_config(base, session_code)
    rounds = int(cfg['num_experimental_rounds'])
    # THE REAL ROUND COUNT, read from the session's own config — never a
    # literal here, or this test silently stops matching the study it drives.
    check(rounds >= 1, f'the session runs its configured {rounds} round(s)')

    s, r = enter_room(created, label)
    check(r.status_code == 200, f'room entry: HTTP {r.status_code}')
    p_code = participant_code(r.url)
    check(p_code is not None,
          f'room entry assigned a participant row ({p_code}) at {r.url}')

    seen = []                 # every page name, in the order the participant met it
    quiz_failed_once = False
    answers = {}
    for step in range(400):
        if r.status_code >= 500:
            check(False, f'HTTP {r.status_code} on {page_name(r.url)}: '
                         f'{r.text[:300]}')
            return
        name = page_name(r.url)
        if name is None:
            check(False, f'walked off the participant flow at {r.url}')
            return
        seen.append(name)
        if name in ('Results', 'Ended'):
            break             # a terminal page: stop here and inspect the record

        fp = FormParser()
        fp.feed(r.text)
        if not fp.found_form:
            check(False, f'dead end: no form and no ending on {name} ({r.url})')
            return

        overrides = {}
        if name == 'quiz':
            if not quiz_failed_once:
                # THE DELIBERATE FAILURE — part of the journey, not a variant.
                overrides = dict(WRONG)
                overrides['redoinstructions'] = '0'
            else:
                overrides = dict(CORRECT)
                overrides['redoinstructions'] = '0'
        elif name == 'ConfirmProlificID':
            # CONFIRM THE PRE-FILLED ID, which is what a real participant does
            # (the field arrives filled from the room label; they submit it
            # as-is). Left to the generic walker this box gets filler text,
            # which the page then CLAIMS AS THE LABEL — so the journey would
            # end with a participant whose recruitment id had been overwritten
            # by the test. That is a walker artefact, not app behaviour, and
            # it must not be baked in here.
            check(f'value="{label}"' in r.text,
                  f'the id from the room link is pre-filled on the '
                  f'confirmation page ({label})')
            overrides['participant_id_external'] = label

        payload = build_payload(fp.inputs, overrides, answers, warn=False)
        post_url = fp.action if (fp.action and fp.action.startswith('http')) else r.url
        r = s.post(post_url, data=payload, allow_redirects=True)

        if name == 'quiz' and not quiz_failed_once:
            quiz_failed_once = True
            # THE FAILURE MUST HAVE ACTUALLY FAILED. A wrong submission that
            # sailed through would leave every later assertion here passing
            # while the retry path was never walked at all — the same
            # "did my setup take effect?" trap as in identity_test.py.
            check(page_name(r.url) == 'quiz',
                  f'a WRONG quiz submission re-renders the quiz rather than '
                  f'advancing (now on {page_name(r.url)})')
            check(r.status_code < 500,
                  f'the re-render is not an error page (HTTP {r.status_code})')
            check('otree-form-errors' in r.text,
                  'the re-rendered quiz carries oTree\'s validation error')
            st = participant_state(base, session_code,
                                   ['failed_attempts', 'comprehension_disqualified'])
            check(st.get('failed_attempts') == 1,
                  f'the failure was RECORDED (failed_attempts='
                  f'{st.get("failed_attempts")!r}, expected 1)')
            check(not st.get('comprehension_disqualified'),
                  'one failure does not disqualify (the threshold is higher)')
    else:
        check(False, 'exceeded the step budget without reaching an ending')
        return

    final = seen[-1]
    # NOT A TEXT MATCH. "Back to Prolific" appears on Ended.html as well as
    # Results.html, so the page NAME is what distinguishes finishing from
    # being thrown out.
    check(final == 'Results',
          f'the participant reached RESULTS, not an early ending (got {final})')

    # THE REAL ROUND COUNT, WALKED. Not "a task page appeared" — every round.
    check(seen.count('GameStart') == rounds,
          f'walked all {rounds} task rounds (saw {seen.count("GameStart")} '
          f'GameStart pages)')
    check(seen.count('payoff') == rounds,
          f'…and all {rounds} payoff pages (saw {seen.count("payoff")})')
    check(seen.count('quiz') == 2,
          f'the quiz was met twice: failed once, then passed '
          f'(saw {seen.count("quiz")})')

    # EVERY SCREEN IN THE REAL ORDER, asserted as the whole sequence rather
    # than a spot check, so a page that quietly stops being displayed (or a
    # new one that slips in) fails here.
    if config == 'prolific':
        # THE AGREEMENT PAGE COMES BEFORE THE INSTRUCTIONS AND THE QUIZ, not
        # after them (moved out of `intro` on 2026-08-12 — see
        # `before.AISafetyAgree`). If this list ever goes back to having
        # 'AISafetyAgree' after 'quiz', the tab monitor is once again arming
        # only once the comprehension check is over, and the instructions and
        # the quiz are unmonitored.
        expected = (['welcome', 'ConfirmProlificID', 'AISafetyAgree',
                     'instructing', 'quiz', 'quiz']
                    + TASK_PAGES * rounds + ['Results'])
    else:
        expected = (['startpage', 'welcome', 'instructing', 'quiz', 'quiz']
                    + TASK_PAGES * rounds
                    + ['Demographics', 'Results'])
    check(seen == expected,
          f'every screen in the real order\n'
          f'      expected: {expected}\n'
          f'      saw     : {seen}')

    # THE ASSERTION THE WHOLE TEST EXISTS FOR.
    st = participant_state(base, session_code,
                           ['exit_code', 'failed_attempts', 'payoff_vector',
                            'participant_id_external'])
    check(st.get('exit_code') == 1,
          f'EXIT CODE IS finished (1) — the participant actually completed '
          f'the study (got {st.get("exit_code")!r})')
    check(st.get('failed_attempts') == 1,
          f'exactly one quiz failure is on the record '
          f'(failed_attempts={st.get("failed_attempts")!r})')
    check(len(st.get('payoff_vector') or []) == rounds,
          f'a payoff was recorded for every round '
          f'({len(st.get("payoff_vector") or [])} of {rounds})')
    check(st.get('label') == label,
          f'the row still carries the id it entered with '
          f'({st.get("label")!r})')
    if config == 'prolific':
        # The id payment is reconciled against, end to end: room link ->
        # confirmation page -> participant field.
        check(st.get('participant_id_external') == label,
              f'the confirmed id reached the payment field '
              f'({st.get("participant_id_external")!r})')


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
    journey(base, 'prolific', 'JOURNEY_PRO_1')
    journey(base, 'lab', 'JOURNEY_LAB_1')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  THE PARTICIPANT FINISHED — all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
