#!/usr/bin/env python
"""THE `explicit_consent` FLAG: the consent question exists exactly when the
flag says so — and the flag, not the recruitment profile, is what decides.

    python scripts/tests/explicit_consent_test.py

WHY THIS TEST EXISTS (DECISIONS.md, 2026-08-14). Whether the consent page asks
an explicit question used to be decided by `prolific_completion_redirects` —
platform plumbing standing in for an ethics decision. The split gave the
question its own flag: default ON in SESSION_CONFIG_DEFAULTS, resolved OFF by
the lab profile. This test pins all four corners of that:

  A. the two SHIPPED configs resolve the value the profiles intend — prolific
     ON (from the baseline default), lab OFF (from the profile) — as explicit
     keys on the stored session config, not as a runtime derivation;
  B. with the flag ON the radio is PRESENT and REQUIRED: an untouched submit
     is rejected, declining routes to the no-consent ending with exit code -1,
     consenting advances;
  C. with the flag OFF the radio is ABSENT, the implicit-consent sentence is
     what the participant reads, and plain Next advances (nothing to decline);
  D. FLAG DECIDES MECHANICS, RECRUITMENT DECIDES COPY: a prolific session with
     the flag forced OFF loses the radio, a lab session with it forced ON
     gains it — the profile only chooses the default, it is not consulted at
     runtime.

Driven over the in-process HTTP client against a throwaway database
(otree_inprocess.boot) in PRODUCTION mode. Assertions about copy are made on
rendered visible text; assertions about the radio are made on raw-HTML
structure (name="consent"), per docs/skills_claude/writing_tests.md.
"""
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)

from otree_inprocess import boot, page_name_of, path_of  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

import settings  # noqa: E402

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def visible_text(html):
    """Strip comments, script/style bodies and tags; collapse whitespace."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    return ' '.join(html.split())


def csrf_of(html):
    m = re.search(r'name="csrftoken"[^>]*value="([^"]+)"', html) \
        or re.search(r'value="([^"]+)"[^>]*name="csrftoken"', html)
    return m.group(1) if m else ''


def welcome_page(client, session):
    """Enter through /join/<anon> (the real door) and walk to `welcome`.

    Walking, not landing: the LAB flow has a hold screen (`startpage`) before
    the consent page, so entry does not arrive on `welcome` in every config.
    """
    r = client.get(f'/join/{ot.anon_code(session)}', allow_redirects=True)
    assert r.status_code == 200, r.status_code
    for _ in range(4):
        if page_name_of(path_of(r)) == 'welcome':
            return r
        r = client.post(path_of(r), data=dict(csrftoken=csrf_of(r.text)),
                        allow_redirects=True)
        assert r.status_code == 200, r.status_code
    raise AssertionError(f'never reached welcome; at {path_of(r)}')


HAS_RADIO = re.compile(r'name="consent"')
EXPLICIT_ASK = 'Please indicate whether you consent'
IMPLICIT_SENTENCE = 'By continuing to the next page you consent'


def submit(client, path, payload):
    r = client.get(path)
    data = dict(csrftoken=csrf_of(r.text), **payload)
    return client.post(path, data=data, allow_redirects=True)


def assert_explicit(client, session, label):
    """The flag-ON contract: present, required, decline routes, accept advances."""
    r = welcome_page(client, session)
    path = path_of(r)
    html, text = r.text, visible_text(r.text)
    check(bool(HAS_RADIO.search(html)),
          f'{label}: the consent radio is IN the form (name="consent")')
    check(EXPLICIT_ASK in text,
          f'{label}: the page asks the explicit question')
    check(IMPLICIT_SENTENCE not in text,
          f'{label}: …and does NOT also carry the implicit-consent sentence')
    # REQUIRED: an untouched submit (no consent key at all — the unticked
    # radio posts nothing) must be rejected, not defaulted.
    r2 = submit(client, path, {})
    check(page_name_of(path_of(r2)) == 'welcome'
          and 'otree-form-errors' in r2.text,
          f'{label}: an untouched submit is REJECTED back onto the page '
          f'(landed on {page_name_of(path_of(r2))})')
    # DECLINE: routes out of the study with the no-consent exit code.
    r3 = submit(client, path_of(r2), {'consent': 'False'})
    code = path_of(r3).split('/')[2]
    vars_ = ot.participant_vars(code)
    check(page_name_of(path_of(r3)) == 'Ended',
          f'{label}: declining lands on the ending page '
          f'(got {page_name_of(path_of(r3))})')
    check(vars_.get('exit_code') == settings.EXIT_CODES['no_consent'],
          f'{label}: …with exit code -1 no_consent '
          f'(got {vars_.get("exit_code")!r})')
    return path


def assert_accept_advances(client, session, label):
    """A fresh participant who consents leaves the welcome page forward."""
    r = welcome_page(client, session)
    r2 = submit(client, path_of(r), {'consent': 'True'})
    check(page_name_of(path_of(r2)) != 'welcome'
          and page_name_of(path_of(r2)) != 'Ended',
          f'{label}: consenting ADVANCES into the study '
          f'(now on {page_name_of(path_of(r2))})')


def assert_implicit(client, session, label):
    """The flag-OFF contract: no radio, implicit sentence, Next advances."""
    r = welcome_page(client, session)
    path = path_of(r)
    html, text = r.text, visible_text(r.text)
    check(not HAS_RADIO.search(html),
          f'{label}: NO consent radio anywhere in the page')
    check(IMPLICIT_SENTENCE in text,
          f'{label}: the implicit-consent sentence is what they read')
    check(EXPLICIT_ASK not in text,
          f'{label}: …and the explicit question is absent')
    r2 = submit(client, path, {})
    check(page_name_of(path_of(r2)) not in ('welcome', 'Ended'),
          f'{label}: plain Next advances — nothing to decline '
          f'(now on {page_name_of(path_of(r2))})')


def main():
    client = ot.client()

    section('A. The shipped configs resolve the value the profiles intend')
    s_prolific = ot.create_session('prolific')
    s_lab = ot.create_session('lab')
    check(s_prolific.config.get('explicit_consent') is True,
          f'prolific: explicit_consent resolves ON, as an explicit stored key '
          f'(got {s_prolific.config.get("explicit_consent")!r})')
    check(s_lab.config.get('explicit_consent') is False,
          f'lab: the profile resolves explicit_consent OFF, as an explicit '
          f'stored key (got {s_lab.config.get("explicit_consent")!r})')

    section('B. Flag ON (prolific default): present, required, routed')
    assert_explicit(client, s_prolific, 'prolific+on')
    assert_accept_advances(client, ot.create_session('prolific'),
                           'prolific+on')

    section('C. Flag OFF (lab default): absent, implicit, nothing to decline')
    assert_implicit(client, s_lab, 'lab+off')

    section('D. The FLAG decides, not the recruitment profile')
    s_prolific_off = ot.create_session(
        'prolific', modified_session_config_fields={'explicit_consent': False})
    assert_implicit(client, s_prolific_off, 'prolific+forced-off')
    s_lab_on = ot.create_session(
        'lab', modified_session_config_fields={'explicit_consent': True})
    assert_explicit(client, s_lab_on, 'lab+forced-on')

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
