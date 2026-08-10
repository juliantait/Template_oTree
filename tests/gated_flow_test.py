"""HTTP scenario tests for the lab-vs-Prolific gated flow (shared apps).

Drives real HTTP against a running server backed by a THROWAWAY database
(same rationale as http_flow_test.py — bots cannot exercise raw POSTs or the
modal/redo mechanics). Scenarios:

  1. lab-reread     — a lab participant failing the quiz gets the re-read offer
                      modal (not consumed by opening/dismissing it), takes it
                      once, is returned through the instructions to the quiz,
                      and on a later failure gets the dismissible experimenter
                      notice (no re-read offer, no disqualification); the
                      consent page quotes the config show-up fee and duration
                      and shows the lab data sentence; the ending collects
                      demographics AND bank details.
  2. prolific-dq    — a Prolific participant sees the Prolific consent
                      sentence, never gets a re-read offer (including via a
                      hand-crafted redoinstructions=1 POST), and is
                      disqualified once failures exceed the cap.
  3. prolific-pass  — a Prolific completer never sees intro round 2 and never
                      sees the demographics/bank page.

Run:  python tests/gated_flow_test.py http://localhost:8000
"""
import sys
import re

import requests

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from http_flow_test import FormParser, build_payload, END_MARKERS

WRONG = {'quiz1': 'NO', 'quiz2': 'You proceed automatically'}
RIGHT = {'quiz1': 'YES', 'quiz2': 'You are asked to reread the instructions'}

REREAD_MARKER = 'value="Re-read the instructions"'
EXPERIMENTER_MARKER = 'raise your hand and speak to the experimenter'
MODAL_MARKER = 'id="quiz-modal-backdrop"'
DISMISS_MARKER = 'dismissQuizModal()'

FAILURES = []


def check(cond, label):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


def page_name(url):
    m = re.search(r'/p/[^/]+/([^/]+)/([^/]+)/(\d+)', url)
    return f"{m.group(1)}.{m.group(2)}" if m else url


def new_participant(base, config, modified=None):
    body = {'session_config_name': config, 'num_participants': 2}
    if modified:
        body['modified_session_config_fields'] = modified
    resp = requests.post(base + '/api/sessions', json=body).json()
    s = requests.Session()
    r = s.get(resp['session_wide_url'], allow_redirects=True)
    return s, r


def submit(s, r, overrides=None, answers=None):
    """POST the current page's form and return the next response."""
    fp = FormParser(); fp.feed(r.text)
    assert fp.found_form, f"no form at {r.url}"
    payload = build_payload(fp.inputs, overrides or {}, dict(answers or {}))
    return s.post(r.url, data=payload, allow_redirects=True)


def advance_until(s, r, name_fragment, limit=40, overrides=None, answers=None):
    """Submit pages generically until the URL contains name_fragment."""
    for _ in range(limit):
        if name_fragment in r.url or any(m in r.text for m in END_MARKERS):
            return r
        r = submit(s, r, overrides=overrides, answers=answers)
        assert r.status_code < 500, f"HTTP {r.status_code} at {r.url}"
    raise AssertionError(f"never reached {name_fragment}; stuck at {r.url}")


def scenario_lab_reread(base):
    print("[lab-reread]")
    s, r = new_participant(base, 'lab', modified={'showup': 7.5, 'expected_duration_minutes': 45})
    r = advance_until(s, r, '/welcome/')
    check('contact and bank details are used only to arrange your' in r.text,
          'consent shows the LAB data sentence')
    check('Prolific ID is used solely' not in r.text,
          'consent does NOT show the Prolific sentence')
    check('45' in r.text and '7.50' in r.text,
          'consent quotes config duration (45 min) and show-up fee (7.50)')
    r = advance_until(s, r, '/instructing/3')  # page index 3 = instructing round 1
    r = submit(s, r)                                   # leave instructions r1
    check('/quiz/4' in r.url, 'quiz round 1 reached')

    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check('/quiz/' in r.url and MODAL_MARKER not in r.text,
          'failure 1: error shown, no modal yet')
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check(REREAD_MARKER in r.text and DISMISS_MARKER in r.text,
          'failure 2 (threshold): dismissible re-read offer modal shown')
    check(EXPERIMENTER_MARKER not in r.text,
          'no experimenter notice while the offer is open')
    # Dismissing the modal is client-side; a further failure must re-offer —
    # proof the offer is NOT consumed by the modal having been shown.
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check(REREAD_MARKER in r.text, 'failure 3 without taking it: offer still open')

    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '1'})  # take it
    check('/instructing/6' in r.url,  # page index 6 = instructing round 2
          f'taking the offer returns to the instructions (round 2) [{page_name(r.url)}]')
    r = submit(s, r)                                   # leave instructions r2
    check('/quiz/7' in r.url, 'then back to the quiz (round 2)')

    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check('/quiz/7' in r.url, 'round-2 failure: still on the quiz (no DQ, no block)')
    check(EXPERIMENTER_MARKER in r.text and DISMISS_MARKER in r.text,
          'round-2 failure: dismissible experimenter notice shown')
    check(REREAD_MARKER not in r.text, 'round-2 failure: re-read no longer offered')
    # Hand-crafted redo POST after the offer is spent must NOT bypass validation.
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '1'})
    check('/quiz/7' in r.url, 'spent offer: redoinstructions=1 POST does not advance')

    r = submit(s, r, answers=RIGHT, overrides={'redoinstructions': '0'})
    check('/main/' in r.url, 'correct answers after all that: participant continues to the task')
    r = advance_until(s, r, '/Demographics/')
    check('name="age"' in r.text and 'name="gender"' in r.text,
          'lab ending collects demographics')
    check('name="bank"' in r.text, 'lab ending collects bank details')
    r = submit(s, r, answers={'age': '30', 'gender': 'Female',
                              'bank': 'NL91ABNA0417164300',
                              'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''})
    check('/Results/' in r.url, 'lab participant reaches results')


def scenario_prolific_dq(base):
    print("[prolific-dq]")
    s, r = new_participant(base, 'prolific')
    r = advance_until(s, r, '/welcome/')
    check('Prolific ID is used solely to handle your payment' in r.text,
          'consent shows the PROLIFIC data sentence')
    check('contact and bank details' not in r.text,
          'consent does NOT show the lab sentence')
    r = advance_until(s, r, '/instructing/3',
                      overrides={'consent': 'True', 'is_mobile': 'False',
                                 'participant_id_external': 'PROLIFIC_TEST_1'})
    r = submit(s, r)
    check('/quiz/4' in r.url, 'quiz round 1 reached')
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check('/quiz/4' in r.url and MODAL_MARKER not in r.text,
          'failure 1: no modal, no re-read offer online')
    # Hand-crafted redo POST must not bypass validation for Prolific.
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '1'})
    # This wrong submission is also failure 2 -> at the cap, DQ routes to outro.
    check('/outro/' in r.url and '/Ended/' in r.url,
          f'failure at the cap: disqualified straight to the ending [{page_name(r.url)}]')
    check('REPLACE_DQ' in r.text, 'ending carries the DQ completion code')
    check('/Introduction/' not in r.url, 'round 2 never seen')


def scenario_prolific_pass(base):
    print("[prolific-pass]")
    s, r = new_participant(base, 'prolific')
    r = advance_until(s, r, '/quiz/4',
                      overrides={'consent': 'True', 'is_mobile': 'False',
                                 'participant_id_external': 'PROLIFIC_TEST_2'})
    r = submit(s, r, answers=RIGHT, overrides={'redoinstructions': '0'})
    check('/AISafetyAgree/' in r.url or '/main/' in r.url,
          f'passing the quiz skips intro round 2 entirely [{page_name(r.url)}]')
    seen = []
    for _ in range(40):
        if any(m in r.text for m in END_MARKERS):
            break
        seen.append(page_name(r.url))
        r = submit(s, r)
        assert r.status_code < 500, f"HTTP {r.status_code} at {r.url}"
    check(not any('instructing' in p or 'quiz' in p for p in seen),
          'no intro page reappears after the round-1 quiz')
    check(not any('Demographics' in p for p in seen),
          'demographics/bank page never shown to a Prolific completer')
    check(not any('Feedback' in p for p in seen),
          'feedback page not shown when pilot_feedback is off')
    check(any('Results' in p for p in seen) or '/Results/' in r.url,
          'prolific completer reaches results')


def scenario_pilot_feedback(base):
    """pilot_feedback is its own axis: a PROLIFIC completer with the flag on
    gets the feedback page (before Results); with it off (scenario_prolific_pass)
    they do not. The lab walk (flag off) likewise never sees it."""
    print("[pilot-feedback]")
    s, r = new_participant(base, 'prolific', modified={'pilot_feedback': True})
    r = advance_until(s, r, '/quiz/4',
                      overrides={'consent': 'True', 'is_mobile': 'False',
                                 'participant_id_external': 'PROLIFIC_TEST_3'})
    r = submit(s, r, answers=RIGHT, overrides={'redoinstructions': '0'})
    r = advance_until(s, r, '/Feedback/')
    check('/Feedback/' in r.url and 'name="feedback"' in r.text,
          'feedback page shown to a prolific completer when the flag is on')
    r = submit(s, r, overrides={'feedback': 'pilot comment: all clear'})
    check('/Results/' in r.url, 'feedback submits through to results')


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
    scenario_lab_reread(base)
    scenario_prolific_dq(base)
    scenario_prolific_pass(base)
    scenario_pilot_feedback(base)
    print(f"\n{'ALL SCENARIOS PASS' if not FAILURES else 'FAILURES: ' + '; '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
