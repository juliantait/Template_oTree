"""HTTP scenario tests for the mobile screen-out gate (`mobile_screenout`).

The gate is decided SERVER-SIDE from the entry request's User-Agent, before the
consent page is rendered, so the only honest way to test it is to drive real
HTTP with a phone User-Agent — a bot cannot set one, and the client-side
`is_mobile` field is measurement that blocks nobody. Both settings of the option
are exercised against a running server on a THROWAWAY database:

    OTREE_ADMIN_PASSWORD=admin otree devserver 8000
    python tests/mobile_screenout_test.py http://localhost:8000

Four cases, all on the `prolific` config (the option lives in the Prolific
block), with `mobile_screenout` flipped per session via the REST API:

  1. option 0 + phone   — reaches consent and completes (exit code 1): with the
                          option off the phone check has NO visible effect.
  2. option 0 + desktop — reaches consent and completes (exit code 1).
  3. option 1 + phone   — NEVER sees consent; the first page it is given is the
                          outro ending, carrying error_code, and exit code -4
                          (screened_out) is recorded. Also asserts the gate
                          recorded screenout_cause='mobile' and that the ending's
                          wording was selected BY THAT CAUSE (-4 alone is the
                          general entry screen-out bucket, so the phone copy must
                          not be reachable without the cause).
  4. option 1 + desktop — unaffected: consent as usual, completes (exit code 1).

Exits non-zero on any failed check or any 5xx.
"""
import re
import sys

import requests

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from http_flow_test import FormParser, build_payload, END_MARKERS

PHONE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
)
DESKTOP_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

# Text that only the consent page carries.
CONSENT_MARKER = 'I consent and wish to take part'
ENTRY_OVERRIDES = {'consent': 'True', 'is_mobile': 'False',
                   'participant_id_external': 'SCREENOUT_TEST'}

FAILURES = []


def check(cond, label):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


def page_name(url):
    m = re.search(r'/p/[^/]+/([^/]+)/([^/]+)/(\d+)', url)
    return f"{m.group(1)}.{m.group(2)}" if m else url


def participant_code(url):
    m = re.search(r'/p/([^/]+)/', url)
    return m.group(1) if m else None


def exit_code_of(base, session_code, p_code):
    """Read the recorded exit_code back over the REST API."""
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': ['exit_code']})
    r.raise_for_status()
    for p in r.json()['participants']:
        if p['code'] == p_code:
            return p.get('exit_code')
    return None


def screenout_cause_of(base, session_code, p_code):
    """Read participant_extra['screenout_cause'] back over the REST API.

    Exit code -4 is the GENERAL entry screen-out bucket; this is the field that
    says which gate fired and therefore which sentence the ending shows.
    """
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': ['participant_extra']})
    r.raise_for_status()
    for p in r.json()['participants']:
        if p['code'] == p_code:
            return (p.get('participant_extra') or {}).get('screenout_cause')
    return None


def run(base, label, user_agent, screenout):
    """Walk one participant through the whole flow with the given User-Agent."""
    print(f"[{label}]  mobile_screenout={screenout}  UA={user_agent[:38]}...")
    created = requests.post(
        base + '/api/sessions',
        json={'session_config_name': 'prolific', 'num_participants': 2,
              'modified_session_config_fields': {'mobile_screenout': screenout}},
    ).json()
    session_code = created['code']

    s = requests.Session()
    s.headers['User-Agent'] = user_agent
    r = s.get(created['session_wide_url'], allow_redirects=True)

    pages, saw_consent, answers = [], False, {}
    for _ in range(80):
        if r.status_code >= 500:
            check(False, f"HTTP {r.status_code} at {page_name(r.url)}")
            return None, None, pages, r, session_code
        pages.append(page_name(r.url))
        saw_consent = saw_consent or CONSENT_MARKER in r.text
        if any(m in r.text for m in END_MARKERS):
            break
        fp = FormParser(); fp.feed(r.text)
        if not fp.found_form:
            check(False, f"dead-end (no form, no end marker) at {page_name(r.url)}")
            return None, None, pages, r, session_code
        if fp.solutions_json.strip():          # DEBUG-only quiz solutions
            import json
            for item in json.loads(fp.solutions_json):
                answers[item['name']] = item['value']
        r = s.post(r.url, data=build_payload(fp.inputs, ENTRY_OVERRIDES, answers),
                   allow_redirects=True)
    else:
        check(False, 'exceeded step budget')

    code = exit_code_of(base, session_code, participant_code(r.url))
    print(f"       pages: {' -> '.join(pages)}")
    print(f"       exit_code={code}")
    return code, saw_consent, pages, r, session_code


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')

    # --- 1. option OFF + phone: the check must have no effect at all ---------
    code, saw_consent, pages, r, session_code = run(base, 'off+phone', PHONE_UA, 0)
    check(saw_consent, 'off+phone: phone still reaches the consent page')
    check(any('welcome' in p for p in pages), 'off+phone: before.welcome was rendered')
    check(code == 1, f'off+phone: completes with exit code 1 (got {code})')
    check(not any('Ended' in p for p in pages), 'off+phone: never sent to the Ended screen')

    # --- 2. option OFF + desktop: baseline ----------------------------------
    code, saw_consent, pages, r, session_code = run(base, 'off+desktop', DESKTOP_UA, 0)
    check(saw_consent, 'off+desktop: reaches the consent page')
    check(code == 1, f'off+desktop: completes with exit code 1 (got {code})')

    # --- 3. option ON + phone: screened out before consent -------------------
    code, saw_consent, pages, r, session_code = run(base, 'on+phone', PHONE_UA, 1)
    check(not saw_consent, 'on+phone: consent page NEVER rendered')
    check(not any('welcome' in p for p in pages), 'on+phone: before.welcome never shown')
    check(pages and pages[0] == 'outro.Ended',
          f'on+phone: first page given is the outro ending (got {pages[0] if pages else None})')
    check(not any('Introduction' in p or 'main' in p for p in pages),
          'on+phone: never enters the instructions/quiz/task')
    check(code == -4, f'on+phone: exit code -4 (screened_out) recorded (got {code})')
    check('REPLACE_ERR' in r.text, 'on+phone: ending carries the error_code completion code')
    check('desktop or laptop' in r.text, 'on+phone: ending explains the desktop-only rule')

    # The ending's wording is chosen by the CAUSE, not by the bare -4 code (-4 is
    # the general "screened out at entry" bucket). Assert the cause was recorded
    # AND that it is the cause that selected the phone branch: the neutral
    # fallback sentence must NOT be on the page.
    cause = screenout_cause_of(base, session_code, participant_code(r.url))
    check(cause == 'mobile',
          f"on+phone: screenout_cause 'mobile' recorded (got {cause!r})")
    check('This study needs a computer' in r.text,
          'on+phone: cause-driven mobile heading shown')
    check('not eligible to take part' not in r.text,
          'on+phone: neutral no-cause fallback NOT shown when a cause is present')

    # --- 4. option ON + desktop: unaffected ---------------------------------
    code, saw_consent, pages, r, session_code = run(base, 'on+desktop', DESKTOP_UA, 1)
    check(saw_consent, 'on+desktop: desktop still reaches the consent page')
    check(code == 1, f'on+desktop: completes with exit code 1 (got {code})')
    check(not any('Ended' in p for p in pages), 'on+desktop: never sent to the Ended screen')

    print(f"\n{'ALL CASES PASS' if not FAILURES else 'FAILURES: ' + '; '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
