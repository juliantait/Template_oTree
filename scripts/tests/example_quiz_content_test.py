#!/usr/bin/env python
"""EXAMPLE — a study-specific content test. COPY IT AND REWRITE IT.

============================================================================
THIS FILE IS A MODEL, NOT A SUITE MEMBER. It is written against the Stag Hunt
placeholder quiz that ships with the template, so the moment you write your own
`intro/quiz_items.py` most of its assertions become assertions about content
that no longer exists. That is the intended lifecycle: copy this file, keep the
SHAPE, and replace the expectations with your study's own. Do not "keep it
passing" by loosening it until it asserts nothing — a content test that survives
a content change unchanged was never testing the content.

The other tests in this folder are deliberately study-AGNOSTIC (flow, escaping,
frozen configs, rendering). This one is the counterexample: it is the shape a
test takes when it pins what a page SAYS, which is the only kind of test that
catches a wording edit that silently breaks comprehension — and every study has
a quiz, so the quiz is where that shape is easiest to learn.

WHAT THE SHAPE IS (the four parts worth copying)
------------------------------------------------
1. STRUCTURAL invariants of the item definitions that hold for ANY quiz —
   every `answer` is a character-for-character copy of one of its `choices`,
   fields are unique, no item is empty. These survive a rewrite; keep them.
2. The items actually REACH the participant: every prompt and every choice is in
   the page's RENDERED VISIBLE TEXT, in the written order (this template does
   not shuffle). Asserted against visible text, never raw HTML — see
   `visible_text` below for why that distinction has already cost real time.
3. The MECHANICS of grading: a correct submission advances, a wrong one comes
   back to the quiz and is counted.
4. What must NOT be in the page in production: the correct answers, and the
   DEBUG-only skip control. This is the leg that keeps a testing convenience
   from shipping into every participant's DOM.

Run:  python scripts/tests/example_quiz_content_test.py
Exit 0 = all checks passed. Boots no server and never touches the real database.
============================================================================
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main_contract import task_page_submits
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

# PRODUCTION mode: DEBUG off is the build participants get, and it is the only
# mode in which "the answers are not in the page" is a meaningful claim.
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
    """What a participant can actually READ: no tags, scripts, styles or
    comments, whitespace collapsed.

    ALWAYS assert copy against this, never against the raw HTML. Two traps this
    template has already hit:
      * body copy WRAPS ACROSS SOURCE LINES, so a sentence that reads fine on
        screen does not appear as a contiguous substring of the source, and a
        raw-HTML assertion fails on a newline rather than on the wording;
      * a keyword can appear in a SCRIPT or an HTML COMMENT — functional code,
        not prose — so a raw-HTML assertion passes on a page where the
        participant sees nothing of the sort. Both directions are false results.
    """
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


PAYLOAD = {
    'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                'participant_id_url': ''},
    'ConfirmProlificID': {'participant_id_external': 'quiz-example'},
    'instructing': {},
    'AISafetyAgree': {},
    # The task pages' names and payloads come from the ONE contract
    # module (scripts/tests/main_contract.py) — a game swap edits it there.
    **task_page_submits(),
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


def main():
    from intro.quiz_items import QUIZ_ITEMS

    client = ot.client()
    session = ot.create_session('lab', num_participants=4)
    codes = ot.participant_codes(session)

    # ---- 1. structural invariants (keep these when you rewrite) -----------
    section('1. Item definitions are internally consistent')
    fields = [i['field'] for i in QUIZ_ITEMS]
    check(len(fields) == len(set(fields)),
          f'every item has a unique field name ({fields})')
    for item in QUIZ_ITEMS:
        f = item['field']
        check(bool(item.get('prompt', '').strip()), f'{f}: has a prompt')
        check(len(item.get('choices', [])) >= 2, f'{f}: has 2+ choices')
        # The classic silent killer: reword a choice, forget the answer string,
        # and the item becomes unpassable with no error anywhere.
        check(item['answer'] in item['choices'],
              f'{f}: the marked answer is a character-for-character copy of one '
              f'choice ({item["answer"]!r})')
        check(len(set(item['choices'])) == len(item['choices']),
              f'{f}: no duplicate choices')

    # ---- 2. the items reach the participant, in order ---------------------
    section('2. Every prompt and choice is READABLE on the rendered page')
    resp = walk_to_quiz(client, codes[0])
    text = visible_text(resp.text)
    for item in QUIZ_ITEMS:
        check(item['prompt'] in text,
              f'{item["field"]}: the prompt is in the visible text')
        for choice in item['choices']:
            check(choice in text, f'{item["field"]}: choice {choice!r} is visible')
    # ORDER: this template renders items and options exactly as written, with no
    # shuffle. If your study adds one, delete this check rather than weakening it.
    positions = [text.index(i['prompt']) for i in QUIZ_ITEMS
                 if i['prompt'] in text]
    check(positions == sorted(positions),
          f'items appear in the order they are written (no shuffle) {positions}')
    for item in QUIZ_ITEMS:
        pos = [text.index(c) for c in item['choices'] if c in text]
        check(pos == sorted(pos),
              f'{item["field"]}: options render in the written order')

    # STUDY-SPECIFIC EXPECTATIONS START HERE. Everything above is generic;
    # everything below is about the shipped placeholder quiz (deliberately
    # trivial machinery-exercising items, see intro/quiz_items.py) and is
    # SUPPOSED to fail once you write your own items.
    section('3. Study-specific: what THIS quiz is about (rewrite per study)')
    check(len(QUIZ_ITEMS) == 2,
          f'the shipped placeholder quiz has exactly 2 items '
          f'(got {len(QUIZ_ITEMS)}) — change this number when you write yours')
    check(any('read and understand' in i['prompt'].lower() for i in QUIZ_ITEMS),
          'one item checks the participant read the instructions')
    check(any('ice' in i['prompt'].lower() for i in QUIZ_ITEMS),
          'one item is the trivial machinery placeholder (ice/water)')
    # A real study replaces the two above with its own load-bearing
    # comprehension items (prior, round independence, payment mechanics — see
    # docs/skills_claude/writing_quiz.md) and checks the WORDING that matters, e.g.
    #   check('two of the ten rounds are paid' in text, 'payment rule stated')

    # ---- 4. grading mechanics --------------------------------------------
    section('4. A correct submission advances; a wrong one comes back')
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}
    first = QUIZ_ITEMS[0]
    wrong = dict(correct)
    wrong[first['field']] = next(c for c in first['choices']
                                 if c != first['answer'])

    resp = walk_to_quiz(client, codes[1])
    after_wrong = client.post(path_of(resp), data=wrong, allow_redirects=True)
    check(page_name_of(path_of(after_wrong)) == 'quiz',
          f'a wrong answer re-renders the quiz '
          f'(now {page_name_of(path_of(after_wrong))})')
    check(ot.participant_vars(codes[1]).get('comprehension_failed_attempts') == 1,
          f'the failed attempt is counted '
          f'(comprehension_failed_attempts='
          f'{ot.participant_vars(codes[1]).get("comprehension_failed_attempts")!r})')
    after_right = client.post(path_of(after_wrong), data=correct,
                              allow_redirects=True)
    check(page_name_of(path_of(after_right)) != 'quiz',
          f'the correct answers advance past the quiz '
          f'(now {page_name_of(path_of(after_right))})')

    resp = walk_to_quiz(client, codes[2])
    straight = client.post(path_of(resp), data=correct, allow_redirects=True)
    check(page_name_of(path_of(straight)) != 'quiz',
          'a first-time correct submission advances immediately')
    check((ot.participant_vars(codes[2]).get('comprehension_failed_attempts') or 0) == 0,
          'and records no failed attempts')

    # ---- 5. nothing that gives the game away ships to production ----------
    section('5. In PRODUCTION the page carries no answers and no skip control')
    quiz_html = walk_to_quiz(client, codes[3]).text
    check('quiz-solutions-data' not in quiz_html,
          'the DEBUG-only solutions blob is absent')
    check('Skip quiz' not in quiz_html,
          'the DEBUG-only "Skip quiz (testing)" control is absent')
    # The answers must not be inferable from the markup either — e.g. a `checked`
    # attribute or a data- attribute carrying the right option.
    for item in QUIZ_ITEMS:
        pattern = (r'<input[^>]*name="%s"[^>]*value="%s"[^>]*checked'
                   % (re.escape(item['field']), re.escape(item['answer'])))
        check(re.search(pattern, quiz_html) is None,
              f'{item["field"]}: the correct option is not pre-selected')

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
