#!/usr/bin/env python
"""QUIZ-ATTEMPTS DISCLOSURE — the Prolific gate, the count, and the fallbacks.

The disclosure exists to keep one promise honest: a Prolific participant is told,
up front and again at the quiz, how many graded attempts they get before the
comprehension check ejects them with a RETURN REQUEST. It appears in four
config-driven places and NOWHERE in a lab session, where returning a submission
is meaningless (there is no platform to return to). This suite pins both halves,
which is the point — an absence-only test of the lab path is indistinguishable
from a test of a blank page (CLAUDE.md), so every "does not show" below is paired
with a "the page really rendered" and, on the Prolific side, a "DOES show".

THE COUNT IS THE THRESHOLD, NOT threshold+1. `intro.quiz.error_message` ejects at
`comprehension_failed_attempts >= quiz_comprehension_max_failures`, incrementing
first, so with the shipped 3 the third wrong submission is the ejecting one and a
participant has exactly THREE chances. `common.max_quiz_attempts` returns that
threshold; disclosing 3, counting down 2 -> 1, then ejecting on the 3rd is the
whole contract, asserted end to end below.

Run:  /home/dev/.venv-otree/bin/python scripts/tests/quiz_attempts_disclosure_test.py
Exit 0 = all checks passed. Boots no server and never touches the real database.
Production mode (DEBUG off) — the build participants actually get.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def visible_text(html):
    """What a participant can actually READ — tags, scripts, styles and comments
    stripped, whitespace collapsed. Copy wraps across source lines and keywords
    hide in scripts/comments, so copy is only ever asserted against this."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


# Consent True + the hidden telemetry/id fields (empty is fine — the no-JS
# submit). ConfirmProlificID needs the confirmed id; startpage/instructing/
# TabMonitorAgree just advance.
PAYLOAD = {
    'startpage': {},
    'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                'participant_id_url': ''},
    'ConfirmProlificID': {'participant_id_external': 'disclosure-test'},
    'TabMonitorAgree': {},
    'instructing': {},
}


def walk_to(client, code, target, limit=20):
    """Walk from entry, posting each page's payload, until `target` renders; return
    that response. Raises if it is never reached (so a broken walk fails loudly
    rather than asserting against the wrong page)."""
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(limit):
        page = page_name_of(path_of(resp))
        if page == target:
            return resp
        if page is None:
            raise AssertionError(f'reached the end before {target!r}')
        resp = client.post(path_of(resp), data=PAYLOAD.get(page, {}),
                           allow_redirects=True)
    raise AssertionError(f'never reached {target!r}')


def main():
    from quiz_answers import CORRECT, WRONG
    all_wrong = {f: WRONG[f] for f in CORRECT}
    all_wrong['redoinstructions'] = '0'

    # ================================================================== #
    section('PROLIFIC — the wording appears and the countdown is correct')
    # ================================================================== #
    client = ot.client()
    session = ot.create_session('prolific', num_participants=6)
    codes = ot.participant_codes(session)

    # (a) Consent page
    consent = walk_to(client, codes[0], 'welcome')
    check(consent.status_code == 200, 'consent page renders (no 500)')
    ctext = visible_text(consent.text)
    check('Fail a short comprehension check within 3 attempts' in ctext,
          'consent states the condition with the count (3 = shipped threshold)')
    check('you must return your submission' in ctext,
          'consent names the return request')
    check('This is a return request, not a rejection' in ctext,
          'consent carries the bold reassurance')
    # The consent page names Prolific in exactly ONE sentence (the contact
    # route); the disclosure deliberately does NOT add a second mention.
    check(ctext.count('Prolific') == 1,
          f'consent still names Prolific exactly once (got {ctext.count("Prolific")})')

    # (b)+(c) Instructions page carries BOTH the intro sentence and the pre-quiz
    # reminder (prequiz_text.html renders on this same page).
    instr = walk_to(client, codes[1], 'instructing')
    check(instr.status_code == 200, 'instructions page renders (no 500)')
    itext = visible_text(instr.text)
    check(itext.count('You have up to 3 attempts to pass the quiz') >= 2,
          'the attempts sentence appears in BOTH the intro and the pre-quiz prompt')

    # (d) Dynamic quiz error_message: countdown, then last-attempt warning, then DQ.
    quiz = walk_to(client, codes[2], 'quiz')
    check(quiz.status_code == 200, 'quiz page renders (no 500)')

    r1 = client.post(path_of(quiz), data=all_wrong, allow_redirects=True)
    check(page_name_of(path_of(r1)) == 'quiz', 'first wrong answer re-renders the quiz')
    t1 = visible_text(r1.text)
    check('You have 2 attempts remaining out of 3' in t1,
          'attempt 1 message: 2 of 3 remaining')
    check('return your submission' not in t1,
          'attempt 1 does not yet threaten removal')

    r2 = client.post(path_of(r1), data=all_wrong, allow_redirects=True)
    check(page_name_of(path_of(r2)) == 'quiz', 'second wrong answer re-renders the quiz')
    t2 = visible_text(r2.text)
    check('last attempt before removal' in t2,
          'attempt 2 message: warns this was the last tolerated attempt')
    check('return your submission on Prolific' in t2,
          'attempt 2 message: names the Prolific return request')
    check('This is a return request, not a rejection' in t2,
          'attempt 2 message: repeats the reassurance')
    check('remaining out of' not in t2,
          'attempt 2 drops the plain countdown for the warning')

    vars2 = ot.participant_vars(codes[2])
    check(vars2.get('comprehension_failed_attempts') == 2,
          f'two failures counted (got {vars2.get("comprehension_failed_attempts")!r})')

    r3 = client.post(path_of(r2), data=all_wrong, allow_redirects=True)
    check(r3.status_code == 200, 'third wrong answer does not 500')
    check(page_name_of(path_of(r3)) != 'quiz',
          f'third wrong answer ejects off the quiz (now {page_name_of(path_of(r3))})')
    vars3 = ot.participant_vars(codes[2])
    check(vars3.get('comprehension_disqualified') is True,
          'the third failure flags comprehension disqualification')

    # A fully correct first submission always passes — the cap never touches it.
    correct = dict(CORRECT, redoinstructions='0')
    quizc = walk_to(client, codes[3], 'quiz')
    passed = client.post(path_of(quizc), data=correct, allow_redirects=True)
    check(page_name_of(path_of(passed)) != 'quiz',
          'a fully correct submission advances immediately')

    # ================================================================== #
    section('LAB — no wording, no return-request threat, no 500')
    # ================================================================== #
    lclient = ot.client()
    lab = ot.create_session('lab', num_participants=3)
    lcodes = ot.participant_codes(lab)

    lconsent = walk_to(lclient, lcodes[0], 'welcome')
    check(lconsent.status_code == 200, 'lab consent renders (no 500)')
    lc = visible_text(lconsent.text)
    # matching-presence: the page really is the consent page...
    check('stored anonymously' in lc, 'lab consent really rendered (data-storage line present)')
    # ...and it carries none of the quiz-attempts disclosure.
    check('comprehension check' not in lc, 'lab consent omits the return-request condition')
    check('return request' not in lc, 'lab consent omits the reassurance')

    linstr = walk_to(lclient, lcodes[0], 'instructing')
    check(linstr.status_code == 200, 'lab instructions render (no 500)')
    li = visible_text(linstr.text)
    check('Stag Hunt' in li, 'lab instructions really rendered (game name present)')
    check('attempts to pass the quiz' not in li, 'lab instructions omit the attempts sentence')

    lquiz = walk_to(lclient, lcodes[0], 'quiz')
    lr = lclient.post(path_of(lquiz), data=all_wrong, allow_redirects=True)
    check(lr.status_code == 200, 'lab wrong answer does not 500')
    check(page_name_of(path_of(lr)) == 'quiz', 'lab wrong answer re-renders the quiz')
    lt = visible_text(lr.text)
    check('One or more quiz answers are wrong' in lt,
          'lab shows the plain wrong-answer message (matching presence)')
    check('remaining out of' not in lt, 'lab error omits the attempt countdown')
    check('return your submission' not in lt, 'lab error omits the return-request threat')

    # ================================================================== #
    section('FROZEN / OLD CONFIGS — safe fallbacks, never a 500')
    # ================================================================== #
    # A session created before `quiz_comprehension_max_failures` shipped: the
    # count must fall back to the shipped default, not 500 a Prolific participant.
    fclient = ot.client()
    fsession = ot.create_session('prolific', num_participants=2)
    fcodes = ot.participant_codes(fsession)
    removed = ot.strip_config_keys(fsession, ['quiz_comprehension_max_failures'])
    check('quiz_comprehension_max_failures' in removed,
          'stripped the threshold key from the stored config')
    fconsent = walk_to(fclient, fcodes[0], 'welcome')
    check(fconsent.status_code == 200,
          'consent still renders with the threshold key absent (no 500)')
    check('within 3 attempts' in visible_text(fconsent.text),
          'the count falls back to the shipped default (3)')

    # A session created before `recruitment` shipped: cfg falls back to
    # DEFAULT_RECRUITMENT (lab) -> is_prolific False -> no wording, no 500.
    rclient = ot.client()
    rsession = ot.create_session('prolific', num_participants=2)
    rcodes = ot.participant_codes(rsession)
    ot.strip_config_keys(rsession, ['recruitment'])
    rconsent = walk_to(rclient, rcodes[0], 'welcome')
    check(rconsent.status_code == 200,
          'consent renders with recruitment absent (no 500)')
    check('comprehension check' not in visible_text(rconsent.text),
          'a recruitment-less (pre-key) session shows no return-request wording')

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
