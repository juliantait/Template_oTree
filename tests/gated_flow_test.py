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


def visible_text(html):
    """The participant-visible text of a page: no scripts, styles, tags or
    comments, with whitespace collapsed.

    The two-variant copy rule ("a page either mentions Prolific or it does not")
    is about what a participant READS, so it must be asserted against this rather
    than the raw HTML. Two reasons the raw source is the wrong target:
      * the capture script legitimately contains the literal parameter name
        PROLIFIC_PID — that is functional code, not prose;
      * body copy wraps across source lines, so a sentence assertion against raw
        HTML fails on the newline rather than on the wording.
    """
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def page_index(url):
    """The trailing page index in an oTree participant URL (/App/Page/<i>).

    Used to tell intro ROUND 1 from ROUND 2, which share a page name and differ
    only by index. Compared RELATIVELY (round 2 > round 1) rather than against
    hardcoded numbers: the index is a position in the whole page sequence, so
    adding a page to an earlier app (e.g. before.ConfirmProlificID) shifts every
    later index and would silently break a hardcoded assertion.
    """
    m = re.search(r'/(\d+)/?$', url)
    return int(m.group(1)) if m else -1


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
    # show_duration_and_fee is switched ON for this scenario ONLY, because the
    # flag ships OFF (change_requests item 1) and this is the one place the
    # duration/fee sentence can be exercised at all. The prolific scenario below
    # asserts the shipped default: no such sentence.
    s, r = new_participant(base, 'lab', modified={'showup': 7.5,
                                                  'expected_duration_minutes': 45,
                                                  'show_duration_and_fee': True})
    r = advance_until(s, r, '/welcome/')
    check('contact and bank details are used only to arrange your payment'
          in visible_text(r.text), 'consent shows the LAB payment sentence')
    # Asserted on the RENDERED TEXT, not on the raw HTML: '45' and '7.50' occur
    # in markup for all sorts of reasons, so an HTML-level check passes even
    # when the sentence is not on the page at all.
    text = ' '.join(visible_text(r.text).split())
    check('45 minutes' in text and '7.50' in text,
          f'with the flag ON, consent quotes the config duration (45 min) and '
          f'show-up fee (7.50)')
    # THE TWO-VARIANT RULE, as amended 2026-08-11 (items 12 + 14): the shared
    # consent page still carries no Prolific PLUMBING (no ID field, no code) and
    # never the CREED header, and the LAB variant never says the word at all —
    # it points the participant at the experimenter in the room instead. Only
    # the online variant's contact sentence names the platform (asserted below).
    check('Prolific' not in visible_text(r.text),
          'lab consent: participant never reads the word Prolific')
    check('raise your hand to speak to the experimenter' in text,
          'lab consent: the contact sentence points at the experimenter')
    check('Welcome to' not in visible_text(r.text),
          'lab consent: no CREED welcome header')
    check('name="participant_id_external"' not in r.text,
          'lab consent: no participant-ID field')
    r = advance_until(s, r, '/instructing/')           # instructing, round 1
    i_instr1 = page_index(r.url)
    r = submit(s, r)                                   # leave instructions r1
    check('/quiz/' in r.url, 'quiz round 1 reached')
    i_quiz1 = page_index(r.url)

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
    check('/instructing/' in r.url and page_index(r.url) > i_instr1,
          f'taking the offer returns to the instructions (round 2) [{page_name(r.url)}]')
    r = submit(s, r)                                   # leave instructions r2
    check('/quiz/' in r.url and page_index(r.url) > i_quiz1,
          'then back to the quiz (round 2)')
    i_quiz2 = page_index(r.url)

    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check(page_index(r.url) == i_quiz2, 'round-2 failure: still on the quiz (no DQ, no block)')
    check(EXPERIMENTER_MARKER in r.text and DISMISS_MARKER in r.text,
          'round-2 failure: dismissible experimenter notice shown')
    check(REREAD_MARKER not in r.text, 'round-2 failure: re-read no longer offered')
    # Hand-crafted redo POST after the offer is spent must NOT bypass validation.
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '1'})
    check(page_index(r.url) == i_quiz2, 'spent offer: redoinstructions=1 POST does not advance')

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
    check('kept separate from your responses' in visible_text(r.text),
          'consent shows the NON-LAB payment sentence')
    check('contact and bank details' not in r.text,
          'consent does NOT show the lab sentence')
    # Same rule from the other side, as amended 2026-08-11 (change_requests
    # items 13 + 14): the ID FIELD still belongs on ConfirmProlificID and
    # nothing platform-specific may leak onto this page — but the CONTACT
    # sentence now names Prolific, because online that is the only way to reach
    # a researcher. Exactly once, and only there.
    ptext = ' '.join(visible_text(r.text).split())
    check(ptext.count('Prolific') == 1,
          f'prolific consent: Prolific is named exactly once '
          f'(got {ptext.count("Prolific")})')
    check('contact the researchers through Prolific' in ptext,
          'prolific consent: …and that once is the contact sentence')
    check('raise your hand' not in ptext.lower(),
          'prolific consent: no lab wording online')
    # The duration/fee sentence ships OFF (item 1) — this config does not turn
    # it on, so it must not be here.
    check('takes about' not in ptext and 'You will receive a payment' not in ptext,
          'prolific consent: the duration/fee paragraph is hidden by default')
    # The redundant field label above the consent options is gone (item 13),
    # while the bold prompt above it stays.
    check('Do you consent to take part?' not in ptext,
          'prolific consent: the redundant question line is gone')
    check('Please indicate whether you consent' in ptext,
          'prolific consent: …but the bold prompt above the options stays')
    check('Welcome to' not in visible_text(r.text),
          'prolific consent: no CREED welcome header')
    check('name="participant_id_external"' not in r.text,
          'prolific consent: ID field is NOT on the consent page')
    # The ID page itself: next, and it IS allowed to say Prolific.
    r = submit(s, r, overrides={'consent': 'True', 'is_mobile': 'False'})
    check('/confirm_prolific_id/' in r.url.lower() or '/ConfirmProlificID/' in r.url,
          f'consent is followed by the Prolific-ID page [{page_name(r.url)}]')
    check('name="participant_id_external"' in r.text,
          'ID page carries the participant-ID field')
    check('Prolific ID' in visible_text(r.text),
          'ID page names Prolific (the one page that may)')
    r = advance_until(s, r, '/instructing/',
                      overrides={'consent': 'True', 'is_mobile': 'False',
                                 'participant_id_external': 'PROLIFIC_TEST_1'})
    r = submit(s, r)
    check('/quiz/' in r.url, 'quiz round 1 reached')
    i_quiz1 = page_index(r.url)
    r = submit(s, r, answers=WRONG, overrides={'redoinstructions': '0'})
    check(page_index(r.url) == i_quiz1 and MODAL_MARKER not in r.text,
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
    r = advance_until(s, r, '/quiz/',
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
    r = advance_until(s, r, '/quiz/',
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
