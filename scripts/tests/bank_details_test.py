"""LAB BANK FORM — the non-Dutch-IBAN-needs-a-BIC rule, and the SEPA flag it
must NOT be collapsed into (Julian, 2026-08-13).

THE TWO PREDICATES ARE DIFFERENT QUESTIONS, deliberately, and this file pins
both halves of the asymmetry so nobody "simplifies" them into one:

  * BIC REQUIRED  — the IBAN is NOT DUTCH, whether in-SEPA or not. A German
    IBAN fails the form without a BIC exactly like an American one.
  * NON-SEPA FLAG — `sepa == 0` from check_sepa_code, recorded for the
    dashboard's red pill. A German IBAN (in SEPA) records 1 and is never
    flagged; only the genuinely non-SEPA account is.

Both read the country through `outro.iban_country_code` — one implementation,
two questions on top of it.

Driven over the in-process ASGI client (real HTTP POSTs against the real form,
per docs/skills_claude/writing_tests.md — no bots): each case walks a real lab
participant to the Demographics page and submits the exact payload a browser
would. There are no JS-filled hidden fields on this form, so the no-JS variant
is the same POST.

Run: python scripts/tests/bank_details_test.py     (boots oTree in-process; no server)
"""
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

from main_contract import task_page_submits
from otree_inprocess import boot, path_of, page_name_of

ot = boot(production=True)          # MUST come before any app import

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def visible_text(html):
    """Participant-visible text only (see gated_flow_test.py for why raw HTML
    is the wrong target for copy assertions)."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


NL_IBAN = 'NL91ABNA0417164300'
DE_IBAN = 'DE89370400440532013000'   # non-Dutch, IN SEPA
US_IBAN = 'US64SVBKUS6S3300958879'   # non-Dutch, NOT in SEPA


def bank_payload(iban, bic='', confirmation=None):
    return {'age': '30', 'gender': 'Female', 'bank': iban,
            'bank_confirmation': iban if confirmation is None else confirmation,
            'bic': bic}


def to_demographics(code):
    """Walk a lab participant over real HTTP to the Demographics page and
    return (client, response) with the page open."""
    from quiz_answers import CORRECT   # one derivation, from the shipped items
    correct = dict(CORRECT)
    payloads = {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'instructing': {},
        'quiz': dict(correct),
        # The task pages' names and payloads come from the ONE contract
        # module (scripts/tests/main_contract.py) — a game swap edits it there.
        **task_page_submits(),
    }
    client = ot.client()
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(60):
        page = page_name_of(path_of(resp))
        if page == 'Demographics' or page is None:
            break
        resp = client.post(path_of(resp), data=payloads.get(page, {}),
                           allow_redirects=True)
        assert resp.status_code == 200, f'walk to Demographics: {resp.status_code}'
    assert page_name_of(path_of(resp)) == 'Demographics', \
        f'expected Demographics, got {page_name_of(path_of(resp))}'
    return client, resp


def submit(client, resp, payload):
    """POST the Demographics form; return (page_now, response)."""
    r = client.post(path_of(resp), data=payload, allow_redirects=True)
    assert r.status_code == 200, f'Demographics POST: {r.status_code}'
    return page_name_of(path_of(r)), r


def sepa_of(code):
    """The recorded sepa column — field_maybe_none, never a bare read."""
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        Player = get_models_module('outro').Player
        row = s.query(Player).filter(Player.participant_id == p.id).first()
        return row.field_maybe_none('sepa')
    finally:
        s.close()


BIC_MSG = 'not Dutch'
MATCH_MSG = "don't match"


def main():
    # The 'lab' config: collect_outro_bank_details and collect_outro_demographics both on
    # (RECRUITMENT_PROFILES['lab']) — named explicitly, not "whatever the first
    # config is".
    sess = ot.create_session('lab', num_participants=5)
    codes = ot.participant_codes(sess)

    section('1. Dutch IBAN: no BIC needed, in SEPA, no flag')
    client, resp = to_demographics(codes[0])
    page, r = submit(client, resp, bank_payload(NL_IBAN, bic=''))
    check(page != 'Demographics',
          f'NL IBAN with an EMPTY BIC advances (now on {page})')
    check(sepa_of(codes[0]) == 1,
          f'…and records sepa=1 (in SEPA; got {sepa_of(codes[0])})')

    section('2. non-Dutch, IN-SEPA (DE): BIC required — the asymmetry, half 1')
    client, resp = to_demographics(codes[1])
    page, r = submit(client, resp, bank_payload(DE_IBAN, bic=''))
    check(page == 'Demographics',
          'a GERMAN IBAN with an empty BIC does NOT advance — the BIC rule is '
          'about non-DUTCH, not non-SEPA')
    check(BIC_MSG in visible_text(r.text),
          'the participant is asked for a BIC in visible text')
    page, r = submit(client, resp, bank_payload(DE_IBAN, bic='COBADEFFXXX'))
    check(page != 'Demographics',
          f'the same IBAN WITH a BIC advances (now on {page})')
    check(sepa_of(codes[1]) == 1,
          f'…and records sepa=1: in-SEPA gets NO dashboard flag even though a '
          f'BIC was required — two predicates, not one (got {sepa_of(codes[1])})')

    section('3. non-Dutch, NON-SEPA (US): BIC required AND flagged')
    client, resp = to_demographics(codes[2])
    page, r = submit(client, resp, bank_payload(US_IBAN, bic=''))
    check(page == 'Demographics' and BIC_MSG in visible_text(r.text),
          'a US IBAN with an empty BIC is refused with the BIC message')
    page, r = submit(client, resp, bank_payload(US_IBAN, bic='SVBKUS6S'))
    check(page != 'Demographics',
          f'US IBAN + any non-empty BIC advances — non-empty is the WHOLE '
          f'requirement, no format validation (now on {page})')
    check(sepa_of(codes[2]) == 0,
          f'…and records sepa=0 (non-SEPA — the dashboard pill, and only this '
          f'case; got {sepa_of(codes[2])})')

    section('4. error precedence: mismatch beats the BIC ask')
    client, resp = to_demographics(codes[3])
    page, r = submit(client, resp,
                     bank_payload(DE_IBAN, bic='', confirmation=US_IBAN))
    text = visible_text(r.text)
    check(page == 'Demographics' and MATCH_MSG in text,
          'mismatched IBANs show the mismatch error')
    check(BIC_MSG not in text,
          '…and NOT the BIC ask at the same time — one problem at a time, and '
          'the BIC question is not even well-posed until the IBAN is settled')
    # Fix the mismatch but keep the BIC empty: NOW the BIC ask appears.
    page, r = submit(client, resp, bank_payload(DE_IBAN, bic=''))
    check(page == 'Demographics' and BIC_MSG in visible_text(r.text),
          'with the mismatch fixed, the BIC ask surfaces on the next submit')
    page, r = submit(client, resp, bank_payload(DE_IBAN, bic='COBADEFF'))
    check(page != 'Demographics', 'and with a BIC the participant proceeds')

    section('5. a lower-case / spaced IBAN is read by country, not by bytes')
    # iban_country_code strips and uppercases — ' nl91…' is a DUTCH account
    # typed untidily, not a foreign one, so no BIC demand and no sepa=0.
    client, resp = to_demographics(codes[4])
    page, r = submit(client, resp, bank_payload(' nl91ABNA0417164300', bic=''))
    check(page != 'Demographics',
          f'a spaced, lower-case NL IBAN still counts as Dutch (now on {page})')
    check(sepa_of(codes[4]) == 1,
          f'…and as in-SEPA (got {sepa_of(codes[4])})')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
