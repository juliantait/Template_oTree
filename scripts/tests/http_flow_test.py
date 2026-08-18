"""HTTP-driven flow tests for the oTree template.

WHY NOT BOTS: several pages carry hidden fields that JavaScript fills
(device info, time-on-page, the tab-monitor arming flag). The template must not
500 when those arrive EMPTY (JS disabled or blocked). Bots submit through the
Python API and never exercise a raw HTTP POST with empty JS-produced fields, so
we drive real HTTP here.

This script does NOT boot a server. Point it at a running server backed by a
THROWAWAY database:

    # in one shell (throwaway db):
    OTREE_ADMIN_PASSWORD=admin otree devserver 8000
    # in another:
    python scripts/tests/http_flow_test.py http://localhost:8000

It walks every shipped config's form pages to an end screen and, for the
Prolific config, also submits the entry page with the JS-produced hidden fields
deliberately EMPTY. Exits non-zero on any 500, dead-end, OR a walk that reaches
the WRONG ending (see below).

WHY THE ENDING IS CHECKED, NOT JUST "an end marker". Every happy-path walk here
means to prove the participant COMPLETED. Reaching *some* end screen does not
prove that: a walker that cannot pass the comprehension quiz is routed — on the
Prolific config, where `quiz_comprehension_dq` is on — to the comprehension-DQ ending
(exit -2), which is also an end screen, so an END_MARKER-only check reports PASS
against the wrong page (the collapsed-distinction fault in CLAUDE.md). And in the
`quiz_comprehension_dq`-off profiles a quiz-failing walker simply LOOPS on the quiz
until the step budget runs out. Both are why the quiz must be answered CORRECTLY,
from the shipped items rather than by guessing the first radio option — and why
each walk now asserts the exact exit code it claims to test.
"""
import os
import sys
import json
import re
from html.parser import HTMLParser

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402,F401  (also puts REPO_ROOT on sys.path)
# The quiz answers come from quiz_answers.py — the ONE derivation from the
# shipped intro/quiz_items.py, so a study that swaps its quiz items cannot leave
# a hardcoded map (or a first-option guess) here quietly answering the wrong
# quiz. In PRODUCTION the page carries no solutions to read, so this seed is the
# only thing that passes the quiz; under DEBUG the page's solutions re-affirm it.
from quiz_answers import CORRECT as QUIZ_CORRECT  # noqa: E402
from settings import EXIT_CODES  # noqa: E402  (a module import; does not start oTree)


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_form = False
        self.found_form = False
        self.action = None
        self.inputs = []
        self._cur_select = None
        self._in_solutions = False
        self.solutions_json = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.in_form = True
            self.found_form = True
            self.action = a.get('action')
        elif tag == 'input' and self.in_form:
            self.inputs.append(dict(type=(a.get('type') or 'text').lower(),
                                    name=a.get('name'), value=a.get('value', '')))
        elif tag == 'select' and self.in_form:
            self._cur_select = dict(type='select', name=a.get('name'), value=None, options=[])
            self.inputs.append(self._cur_select)
        elif tag == 'option' and self._cur_select is not None:
            self._cur_select['options'].append(a.get('value', ''))
        elif tag == 'textarea' and self.in_form:
            self.inputs.append(dict(type='textarea', name=a.get('name'), value=''))
        elif tag == 'script' and a.get('id') == 'quiz-solutions-data':
            self._in_solutions = True

    def handle_endtag(self, tag):
        if tag == 'form':
            self.in_form = False
        elif tag == 'select':
            self._cur_select = None
        elif tag == 'script':
            self._in_solutions = False

    def handle_data(self, data):
        if self._in_solutions:
            self.solutions_json += data


END_MARKERS = (
    'Back to Prolific',
    'Thank you for taking part',
    'participation has ended',
    'Please leave up to 2 weeks',
)


# Radio groups whose answer is a DECISION, not a formality. An unmapped radio
# group falls back to "pick the first option", which is fine for an opinion item
# and disastrous for a routing one: the consent radio ships unticked (it must be
# an affirmative act), so a first-option pick is only the consenting path by
# luck of the order the choices happen to be written in. Reorder them and every
# generic walk would quietly measure the NO-CONSENT flow and still report PASS.
DECISION_RADIOS = {
    'consent': 'True',
}


def build_payload(inputs, overrides, answers, warn=True):
    payload = {}
    radios = {}
    for f in inputs:
        name = f.get('name')
        if not name or f['type'] in ('submit', 'button', 'reset'):
            continue
        if (f['type'] == 'radio' and name in DECISION_RADIOS
                and name not in overrides and name not in answers):
            payload[name] = DECISION_RADIOS[name]
            continue
        if name in overrides:
            payload[name] = overrides[name]
            continue
        if name in answers:
            payload[name] = answers[name]
            continue
        t = f['type']
        if t == 'radio':
            radios.setdefault(name, f['value'])
        elif t == 'checkbox':
            pass
        elif t == 'hidden':
            payload[name] = f['value']
        elif t == 'select':
            opts = [o for o in f.get('options', []) if o != '']
            if opts:
                payload[name] = opts[0]
        else:
            # A value that satisfies common constraints (e.g. age min=16); IBAN
            # confirmation matches because every text field gets the same value.
            payload.setdefault(name, '25')
    for name, val in radios.items():
        # Say so out loud rather than picking silently: a group nobody has
        # decided about is answered by document order, which is not a decision.
        if warn and name not in DECISION_RADIOS:
            print(f"    [walker] no answer given for radio {name!r}; taking the "
                  f"first option {val!r}. If this choice ROUTES the "
                  f"participant, add it to DECISION_RADIOS or override it.")
        payload.setdefault(name, val)
    return payload


def participant_code(url):
    """/p/<code>/... -> the participant code (used to read the exit code back)."""
    m = re.search(r'/p/([^/]+)/', str(url))
    return m.group(1) if m else None


def read_exit_code(base, session_code, p_code):
    """The participant's numeric outcome, read back over the REST API.

    This is the POSITIVE half of the assertion: the walk did not merely reach
    *an* end screen, it reached the ending whose exit code it claims to test.
    Read from the server's own record rather than inferred from the page copy,
    which several endings share.
    """
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': ['exit_code']})
    r.raise_for_status()
    for p in r.json().get('participants', []):
        if p.get('code') == p_code:
            return p.get('exit_code')
    return None


def walk(base, config, overrides=None, answers=None, label='', expect_exit='finished'):
    overrides = overrides or {}
    # Seed the passing quiz answers from the shipped items (see the module
    # header). A caller may still override a specific field via `answers`.
    answers = dict(QUIZ_CORRECT, **(answers or {}))
    expected_code = EXIT_CODES[expect_exit]
    s = requests.Session()
    resp = requests.post(base + '/api/sessions',
                         json={'session_config_name': config, 'num_participants': 2}).json()
    if 'session_wide_url' not in resp or 'code' not in resp:
        print(f"[{label}] could not create session: {resp}")
        return False
    session_code = resp['code']
    r = s.get(resp['session_wide_url'], allow_redirects=True)
    for step in range(80):
        if r.status_code >= 500:
            print(f"[{label}] HTTP {r.status_code} at {r.url}\n{r.text[:600]}")
            return False
        if any(m in r.text for m in END_MARKERS):
            page = r.url.split('/p/')[-1]
            code = read_exit_code(base, session_code, participant_code(r.url))
            if code != expected_code:
                print(f"[{label}] reached AN ending after {step} steps but "
                      f"exit_code={code}, expected {expected_code} "
                      f"({expect_exit}); page={page}")
                return False
            print(f"[{label}] reached the {expect_exit} ending "
                  f"(exit_code={code}) after {step} steps: {page}")
            return True
        fp = FormParser(); fp.feed(r.text)
        if not fp.found_form:
            print(f"[{label}] dead-end (no form, no end marker): {r.url}")
            return False
        # If this page (DEBUG) exposes the quiz solutions, they RE-AFFIRM the
        # seed above; in production the blob is absent and the seed stands alone.
        if fp.solutions_json.strip():
            try:
                for item in json.loads(fp.solutions_json):
                    answers[item['name']] = item['value']
            except Exception:
                pass
        payload = build_payload(fp.inputs, overrides, answers)
        post_url = fp.action if (fp.action and fp.action.startswith('http')) else r.url
        r = s.post(post_url, data=payload, allow_redirects=True)
    print(f"[{label}] exceeded step budget")
    return False


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
    results = {}
    # 1) Happy paths for each shipped config.
    results['test'] = walk(base, 'test', label='test')
    results['lab'] = walk(base, 'lab', label='lab')
    results['prolific'] = walk(base, 'prolific', label='prolific')
    # 2) The key case bots can't do: JS-produced hidden fields submitted EMPTY.
    results['prolific+empty-hidden'] = walk(
        base, 'prolific',
        overrides={'is_mobile': '', 'device_info_json': '', 'client_ms': ''},
        label='prolific+empty-hidden')

    print("\n=== RESULTS ===")
    ok = True
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
