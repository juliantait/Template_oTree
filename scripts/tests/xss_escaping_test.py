#!/usr/bin/env python
"""SECURITY: participant- and URL-supplied values are HTML-escaped everywhere.

WHY THIS EXISTS
---------------
oTree's template engine (ibis) does NOT auto-escape `{{ value }}` — unlike
Django or Jinja, it prints raw. Any participant-controlled value interpolated by
hand into a page is therefore a reflected XSS until proven otherwise, and this
is not hypothetical: the pilot study this template was distilled from shipped
exactly that bug on its ID-confirmation page and it was found by fuzzing, after
launch. In this template the escaping is one `|escape` filter in
`before/confirm_prolific_id.html`; deleting it breaks nothing, fails no other
test, and silently reintroduces the hole. That is what this file is for.

Two attacker-controlled sources are covered, because both reach a page:
  * URL-SUPPLIED — the entry link carries `?participant_label=…`, which oTree
    stores as `participant.label` and the ID page pre-fills into an input value;
  * PARTICIPANT-SUPPLIED — whatever they then type into that field, which is
    stored and can be re-rendered later.

It runs in PRODUCTION mode (DEBUG off) on purpose: oTree's DEBUG-only var dump
would otherwise echo the payload at the foot of every page and make a
whole-page scan meaningless. Production is also the build that actually ships.

Run:  python scripts/tests/xss_escaping_test.py       (oTree must be importable)
Exit 0 = all checks passed. Boots no server and never touches the real database.
"""
import html
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main_contract import task_page_submits
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# Payloads confirmed against the live pilot page, plus a benign quote-bearing id
# (a data-fidelity case: an unescaped quote TRUNCATES the value at the quote) and
# a normal-looking id.
PAYLOADS = [
    '"><script>alert(1)</script>',
    '"><script>window.__xss=1</script><x y=',
    'x" onmouseover="alert(2)" a="',
    "'><img src=x onerror=alert(3)>",
    'ABC"DEF',
]
NORMAL_ID = '5f8a1b2c3d4e5f6a7b8c9d0e'

# Substrings that can ONLY come from a payload that survived unescaped. Generic
# fragments ('<script', '"><') are deliberately not used: they occur in every
# normal page, so they would fire on the page's own machinery.
INJECTION_MARKERS = [
    '<script>alert(1)',
    '<script>window.__xss=1',
    'onmouseover="alert(2)"',
    '<img src=x onerror=alert(3)>',
]

TERMINAL = {'Results', 'Ended'}
# Everything a page might need posted, keyed by page. The ID field is filled per
# walk (that is the participant-supplied half of the test).
BASE_PAYLOAD = {
    'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                'participant_id_url': ''},
    'instructing': {},
    'quiz': {},
    'TabMonitorAgree': {},
    # The task pages' names and payloads come from the ONE contract
    # module (scripts/tests/main_contract.py) — a game swap edits it there.
    **task_page_submits(),
    'Demographics': {'age': '30', 'gender': 'Female',
                     'bank': 'NL91ABNA0417164300',
                     'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
    'Feedback': {'feedback': ''},
}


def walk(client, code, id_value, quiz_answers, max_steps=80):
    """Walk one participant to a terminal page, collecting every page's HTML."""
    pages = []
    statuses = []
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    statuses.append(resp.status_code)
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None:
            break
        pages.append((page, resp.text))
        if page in TERMINAL:
            break
        data = dict(BASE_PAYLOAD.get(page, {}))
        if page == 'ConfirmProlificID':
            data['participant_id_external'] = id_value
        if page == 'quiz':
            data.update(quiz_answers)
        resp = client.post(path_of(resp), data=data, allow_redirects=True)
        statuses.append(resp.status_code)
    return pages, statuses


def main():
    from quiz_answers import CORRECT   # one derivation, from the shipped items
    import before as before_app
    from otree.database import DBSession
    from otree.models import Participant

    correct_quiz = dict(CORRECT)
    client = ot.client()

    section('Setup (PRODUCTION mode: no DEBUG var dump to hide behind)')
    from otree import settings as otree_settings
    check(otree_settings.DEBUG is False,
          'oTree DEBUG is OFF, so the whole page can be scanned')
    session = ot.create_session('prolific',
                                num_participants=len(PAYLOADS) + 2)
    codes = ot.participant_codes(session)

    def stored_id(code):
        s = DBSession()
        try:
            part = s.query(Participant).filter_by(code=code).one()
            row = s.query(before_app.Player).filter_by(
                participant_id=part.id).one()
            return row.field_maybe_none('participant_id_external')
        finally:
            s.close()

    section('URL-supplied label: every payload renders inert on every page')
    for i, payload in enumerate(PAYLOADS):
        code = codes[i]
        # The real attack path: the value arrives in the entry URL. Setting the
        # label directly is the same state oTree reaches after ?participant_label=
        # (verified separately below through the actual /join/ URL).
        ot.set_label(code, payload)
        pages, statuses = walk(client, code, payload, correct_quiz)
        label = f'payload {i} ({payload[:22]!r})'
        check(all(s < 500 for s in statuses),
              f'{label}: no page 5xx across {len(statuses)} requests '
              f'(max {max(statuses)})')
        seen = [p for p, _ in pages]
        check('ConfirmProlificID' in seen,
              f'{label}: the ID page was reached ({" -> ".join(seen[:4])} …)')
        for page, page_html in pages:
            check(payload not in page_html,
                  f'{label}: the raw payload appears nowhere on {page}')
            for marker in INJECTION_MARKERS:
                check(marker not in page_html,
                      f'{label}: no injected {marker[:24]!r} on {page}')
        confirm_html = dict(pages)['ConfirmProlificID']
        check(f'value="{html.escape(payload, quote=True)}"' in confirm_html,
              f'{label}: the pre-fill holds the FULLY escaped value, intact')
        # Data fidelity, not just safety: an unescaped quote truncates the
        # attribute, so a round-trip proves the escaping preserved the value.
        check(stored_id(code) == payload,
              f'{label}: the submitted value round-trips into the database '
              f'un-truncated (got {stored_id(code)!r})')

    section('A normal id still pre-fills verbatim and submits')
    code = codes[len(PAYLOADS)]
    ot.set_label(code, NORMAL_ID)
    pages, statuses = walk(client, code, NORMAL_ID, correct_quiz)
    confirm_html = dict(pages)['ConfirmProlificID']
    check(all(s < 500 for s in statuses), 'normal id: no 5xx')
    check(f'value="{NORMAL_ID}"' in confirm_html,
          'normal id pre-fills verbatim (no entities, not truncated)')
    check(stored_id(code) == NORMAL_ID, 'normal id stored intact')
    check(pages[-1][0] in TERMINAL,
          f'the walk carried on to a terminal page (ended on {pages[-1][0]})')

    section('The payload through the REAL entry URL (?participant_label=…)')
    # The parameter is what an attacker actually controls, so the escaping is
    # also proven end to end from the URL rather than from a planted DB value.
    fresh = ot.create_session('prolific', num_participants=2)
    payload = PAYLOADS[0]
    from urllib.parse import quote
    resp = client.get(f'/join/{ot.anon_code(fresh)}?participant_label='
                      f'{quote(payload)}', allow_redirects=True)
    check(resp.status_code < 500, 'entry with a hostile label: no 5xx')
    check(payload not in resp.text,
          'the entry page does not reflect the raw label')
    resp = client.post(path_of(resp), data=dict(BASE_PAYLOAD['welcome']),
                       allow_redirects=True)
    check(page_name_of(path_of(resp)) == 'ConfirmProlificID',
          f'consent leads to the ID page '
          f'(got {page_name_of(path_of(resp))})')
    check(payload not in resp.text,
          'the ID page does not reflect the raw URL label')
    check(f'value="{html.escape(payload, quote=True)}"' in resp.text,
          'it pre-fills the escaped URL label')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print(f'  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
