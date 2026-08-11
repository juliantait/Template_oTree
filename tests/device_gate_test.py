"""HTTP scenario tests for the entry DEVICE ALLOW-LIST (`allowed_devices`).

Renamed from mobile_screenout_test.py on 2026-08-11: the gate is no longer
"screen phones out, yes/no". A study now STATES the device types it accepts —
any of 'phone', 'tablet', 'computer', 'unknown' — and everything else is
screened out at entry with the DETECTED TYPE recorded as the screen-out cause.

The gate is decided SERVER-SIDE from the entry request's User-Agent, before the
consent page is rendered, so the only honest way to test it is to drive real
HTTP with a device's User-Agent — a bot cannot set one, and the client-side
`is_mobile` / `device_type` values are measurement that block nobody. Run
against a server on a THROWAWAY database:

    OTREE_ADMIN_PASSWORD=admin otree devserver 8000
    python tests/device_gate_test.py http://localhost:8000

Cases, all on the `prolific` config, with `allowed_devices` set per session via
the REST API:

  1. DEFAULT list (all four types) + phone   — reaches consent and completes:
     with everything permitted the gate has NO visible effect whatsoever.
  2. DEFAULT list + desktop                  — same, the baseline.
  3. computer only + phone     — a FORBIDDEN type: never sees consent, first
     page is the outro ending with error_code, exit code -4, cause 'phone', and
     the ending's wording is the phone one.
  4. computer only + desktop   — a PERMITTED type passes and completes.
  5. computer only + tablet    — tablets are their own type, not "a big phone":
     screened out with cause 'tablet' and the tablet sentence.
  6. phone + tablet only + desktop — the gate is an ALLOW-LIST, not a
     phone-blocker: a computer is screened out here, with cause 'computer' and
     copy that names what IS accepted.
  7. computer only + NO User-Agent  — 'unknown' is its own type: screened out
     with cause 'unknown' and its own wording (which must not claim to know
     what the participant is using).
  8. computer + unknown + NO User-Agent — and admitting 'unknown' lets exactly
     that participant through, with no code change.

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
TABLET_UA = (
    'Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
)
DESKTOP_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)
# A stripped User-Agent: what a privacy tool (or a bare HTTP client) sends.
NO_UA = ''

ALL_TYPES = ['phone', 'tablet', 'computer', 'unknown']

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


def extra_of(base, session_code, p_code, key):
    """Read one key of participant_extra back over the REST API.

    Exit code -4 is the GENERAL entry screen-out bucket; `screenout_cause` is
    the field that says which DEVICE TYPE was detected and therefore which
    sentence the ending shows. `entry_device_type` is the same classification
    recorded for everyone, gate or no gate.
    """
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': ['participant_extra']})
    r.raise_for_status()
    for p in r.json()['participants']:
        if p['code'] == p_code:
            return (p.get('participant_extra') or {}).get(key)
    return None


def run(base, label, user_agent, allowed):
    """Walk one participant through the whole flow with the given User-Agent."""
    shown_ua = (user_agent[:38] + '...') if user_agent else '<none>'
    print(f"[{label}]  allowed_devices={allowed}  UA={shown_ua}")
    created = requests.post(
        base + '/api/sessions',
        json={'session_config_name': 'prolific', 'num_participants': 2,
              'modified_session_config_fields': {'allowed_devices': allowed}},
    ).json()
    session_code = created['code']

    s = requests.Session()
    if user_agent:
        s.headers['User-Agent'] = user_agent
    else:
        # requests sends its own UA unless it is removed outright, and "no
        # User-Agent at all" is exactly the case the 'unknown' type is for.
        s.headers.pop('User-Agent', None)
        s.headers['User-Agent'] = ''
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


def expect_screened_out(base, label, ua, allowed, cause, must_say, must_not_say=()):
    """A forbidden device: never sees consent, -4, the right cause and copy."""
    code, saw_consent, pages, r, session_code = run(base, label, ua, allowed)
    check(not saw_consent, f'{label}: consent page NEVER rendered')
    check(not any('welcome' in p for p in pages),
          f'{label}: before.welcome never shown')
    check(bool(pages) and pages[0] == 'outro.Ended',
          f'{label}: first page given is the outro ending '
          f'(got {pages[0] if pages else None})')
    check(not any('Introduction' in p or 'main' in p for p in pages),
          f'{label}: never enters the instructions/quiz/task')
    check(code == -4, f'{label}: exit code -4 (screened_out) recorded (got {code})')
    check('REPLACE_ERR' in r.text,
          f'{label}: ending carries the error_code completion code')
    p_code = participant_code(r.url)
    got = extra_of(base, session_code, p_code, 'screenout_cause')
    check(got == cause,
          f"{label}: screenout_cause is the DETECTED TYPE {cause!r} (got {got!r})")
    check(extra_of(base, session_code, p_code, 'entry_device_type') == cause,
          f'{label}: entry_device_type records the same classification')
    # Asserted on WHITESPACE-NORMALISED text: the copy wraps across source
    # lines, so a raw-HTML substring search silently fails to find a sentence
    # that is on the page (and would silently PASS if the sentence changed).
    flat = ' '.join(r.text.split())
    for phrase in must_say:
        check(phrase in flat, f'{label}: ending says {phrase!r}')
    for phrase in must_not_say:
        check(phrase not in flat, f'{label}: ending does NOT say {phrase!r}')
    check('not eligible to take part' not in flat,
          f'{label}: the neutral no-cause fallback is NOT used (a cause exists)')


def expect_admitted(base, label, ua, allowed, device_type):
    """A permitted device: consent as usual, completes, nothing visible."""
    code, saw_consent, pages, r, session_code = run(base, label, ua, allowed)
    check(saw_consent, f'{label}: reaches the consent page')
    check(code == 1, f'{label}: completes with exit code 1 (got {code})')
    check(not any('Ended' in p for p in pages),
          f'{label}: never sent to the Ended screen')
    got = extra_of(base, session_code, participant_code(r.url), 'entry_device_type')
    check(got == device_type,
          f'{label}: the device was still CLASSIFIED for the record '
          f'(entry_device_type={got!r})')


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')

    # --- 1/2. the shipped list permits everything: no visible effect ---------
    expect_admitted(base, 'default+phone', PHONE_UA, ALL_TYPES, 'phone')
    expect_admitted(base, 'default+desktop', DESKTOP_UA, ALL_TYPES, 'computer')

    # --- 3/4. computer-only: the forbidden type out, the permitted one in ----
    expect_screened_out(
        base, 'computer-only+phone', PHONE_UA, ['computer'], 'phone',
        must_say=('cannot be taken on a phone', 'desktop or laptop computer'),
        must_not_say=('cannot be taken on a tablet',))
    expect_admitted(base, 'computer-only+desktop', DESKTOP_UA, ['computer'],
                    'computer')

    # --- 5. a tablet is its own type, not "a big phone" ----------------------
    expect_screened_out(
        base, 'computer-only+tablet', TABLET_UA, ['computer'], 'tablet',
        must_say=('cannot be taken on a tablet',),
        must_not_say=('cannot be taken on a phone',))

    # --- 6. an ALLOW-LIST, not a phone blocker: computers can be excluded ----
    expect_screened_out(
        base, 'mobile-only+desktop', DESKTOP_UA, ['phone', 'tablet'], 'computer',
        must_say=('cannot be taken on a desktop or laptop computer',
                  'a phone or a tablet'),
        must_not_say=('cannot be taken on a phone',))

    # --- 7/8. 'unknown' is configurable exactly like the others -------------
    expect_screened_out(
        base, 'computer-only+no-UA', NO_UA, ['computer'], 'unknown',
        must_say=('could not identify the device',),
        # It must not claim to know what they are on.
        must_not_say=('cannot be taken on a phone',
                      'cannot be taken on a tablet'))
    expect_admitted(base, 'unknown-admitted+no-UA', NO_UA,
                    ['computer', 'unknown'], 'unknown')

    print(f"\n{'ALL CASES PASS' if not FAILURES else 'FAILURES: ' + '; '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
