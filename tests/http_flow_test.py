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
    python tests/http_flow_test.py http://localhost:8000

It walks every shipped config's form pages to an end screen and, for the
Prolific config, also submits the entry page with the JS-produced hidden fields
deliberately EMPTY. Exits non-zero on any 500 or dead-end.
"""
import sys
import json
import re
from html.parser import HTMLParser

import requests


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


def walk(base, config, overrides=None, answers=None, label=''):
    overrides = overrides or {}
    answers = dict(answers or {})
    s = requests.Session()
    resp = requests.post(base + '/api/sessions',
                         json={'session_config_name': config, 'num_participants': 2}).json()
    if 'session_wide_url' not in resp:
        print(f"[{label}] could not create session: {resp}")
        return False
    r = s.get(resp['session_wide_url'], allow_redirects=True)
    for step in range(80):
        if r.status_code >= 500:
            print(f"[{label}] HTTP {r.status_code} at {r.url}\n{r.text[:600]}")
            return False
        if any(m in r.text for m in END_MARKERS):
            print(f"[{label}] reached end after {step} steps: {r.url.split('/p/')[-1]}")
            return True
        fp = FormParser(); fp.feed(r.text)
        if not fp.found_form:
            print(f"[{label}] dead-end (no form, no end marker): {r.url}")
            return False
        # If this page (DEBUG) exposes the quiz solutions, answer correctly.
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
