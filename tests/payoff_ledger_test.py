"""ONE PAYMENT LEDGER (J1, Julian 2026-08-13) — the admin-visible number and
the participant-visible number must AGREE, because two numbers disagreeing is
the entire reason this change exists.

What is pinned, in order of importance:

  1. After a real walked journey, oTree's `participant.payoff` — the value the
     admin Payments page and the wide export show — EQUALS `outro.Player.
     earned`, the figure on the participant's receipt (template config:
     USE_POINTS=False, participation_fee=0, so the mapping is identity).
  2. The admin Payments PAGE itself (oTree's own view, fetched logged-in over
     the in-process app) renders that figure.
  3. The value STICKS: re-rendering Results does not recompute, double-write
     or drift it (the empirical answer to "does oTree fight back after
     compute_final_payoff" — source inspection says nothing recomputes
     participant.payoff, and this measures it).
  4. Writing oTree's per-round `player.payoff` now RAISES
     (AUTO_TABULATE_PAYOFFS=False): a study cannot silently drift back to two
     ledgers.
  5. The per-round `payoff` column is ABSENT from the export — deliberately
     gone, not accidentally empty — while `round_payoff` and the participant's
     `payoff_vector` still carry every round (no data lost).
  6. A non-completer's participant.payoff is 0: the one write runs only on the
     results page.

Run: python tests/payoff_ledger_test.py    (boots oTree in-process; no server)
"""
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, os.path.dirname(_TESTS_DIR))

# Locked-down mode so the admin Payments page is behind the real login.
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

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


def payload_for(page, quiz_answers):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'instructing': {},
        'quiz': dict(quiz_answers),
        'GameStart': {'client_ms': ''},
        'payoff': {},
        'Demographics': {'age': '30', 'gender': 'Female',
                         'bank': 'NL91ABNA0417164300',
                         'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def walk_to_results(client, code, quiz_answers, max_steps=120):
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None or page == 'Results':
            return resp
        resp = client.post(path_of(resp), data=payload_for(page, quiz_answers),
                           allow_redirects=True)
        assert resp.status_code == 200, f'walk: HTTP {resp.status_code}'
    raise AssertionError('never reached Results')


def admin_client():
    c = ot.client()
    r = c.get('/login')
    token = re.search(r'name="csrftoken" value="([^"]+)"', r.text).group(1)
    c.post('/login', data={'username': 'admin', 'password': 'admin',
                           'csrftoken': token}, allow_redirects=False)
    return c


def ledger_row(code):
    """(participant.payoff, payoff_plus_participation_fee, earned, vector)."""
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        OutroPlayer = get_models_module('outro').Player
        row = (s.query(OutroPlayer)
               .filter(OutroPlayer.participant_id == p.id).first())
        earned = row.field_maybe_none('earned') if row else None
        return (float(p.payoff), float(p.payoff_plus_participation_fee()),
                None if earned is None else float(earned),
                list(p.vars.get('payoff_vector') or []))
    finally:
        s.close()


def main():
    from intro.quiz_items import QUIZ_ITEMS
    from otree import settings as otree_settings
    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}

    section('0. the setting that removes the second ledger')
    check(otree_settings.AUTO_TABULATE_PAYOFFS is False,
          'AUTO_TABULATE_PAYOFFS is off (per-round player.payoff writes '
          'raise; per-round payoff column omitted from the export)')

    section('1. the two figures AGREE after a real journey')
    # 'test' config: 3 rounds, lab profile, bank/demographics off — the
    # shortest full walk. USE_POINTS=False and participation_fee=0, so
    # participant.payoff must equal `earned` exactly.
    sess = ot.create_session('test', num_participants=2)
    codes = ot.participant_codes(sess)
    client = ot.client()
    walk_to_results(client, codes[0], correct)
    payoff, admin_figure, earned, vector = ledger_row(codes[0])
    check(earned is not None and earned > 0,
          f'the walked participant has a computed earned ({earned})')
    check(payoff == earned,
          f'participant.payoff EQUALS earned ({payoff} vs {earned}) — one '
          f'number, both ledgers')
    check(admin_figure == earned,
          f'payoff_plus_participation_fee — the admin Payments figure — '
          f'equals earned ({admin_figure} vs {earned})')
    check(len(vector) == 3 and payoff != sum(float(v) for v in vector),
          f'…and it is earned, NOT the sum of raw round payoffs '
          f'(sum {sum(float(v) for v in vector)}, paid {payoff}) — the old '
          f'second ledger is gone, not coincidentally equal')

    section('2. the admin Payments PAGE shows the same figure')
    admin = admin_client()
    r = admin.get(f'/SessionPayments/{sess.code}')
    body = re.sub(r'\s+', ' ', r.text)
    figure = f'{earned:.2f}'
    check(r.status_code == 200 and figure in body,
          f"oTree's own SessionPayments page renders {figure} "
          f'(HTTP {r.status_code})')

    section('3. the value STICKS — no recompute after compute_final_payoff')
    # Re-render Results twice: the idempotence guard must hold, and nothing in
    # oTree may recompute participant.payoff from the (empty) per-round values.
    for _ in range(2):
        resp = client.get(f'/InitializeParticipant/{codes[0]}',
                          allow_redirects=True)
        assert page_name_of(path_of(resp)) == 'Results', 'expected Results'
    payoff2, admin2, earned2, _ = ledger_row(codes[0])
    check((payoff2, admin2, earned2) == (payoff, admin_figure, earned),
          f'two Results re-renders later the ledger is byte-identical '
          f'({payoff2}, {admin2}, {earned2})')

    section('4. the old habit is IMPOSSIBLE, not discouraged')
    from otree.common import get_models_module
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=codes[0]).one()
        MainPlayer = get_models_module('main').Player
        pl = (s.query(MainPlayer)
              .filter(MainPlayer.participant_id == p.id,
                      MainPlayer.round_number == 1).one())
        try:
            pl.payoff = 5
            check(False, 'writing player.payoff raises (it did not)')
        except Exception as exc:
            check('participant.payoff' in str(exc),
                  f'writing player.payoff raises, pointing at the one ledger '
                  f'({exc})')
        check(pl.field_maybe_none('round_payoff') is not None,
              "the game's own round_payoff column holds round 1's value")
    finally:
        s.close()

    section('5. the export: per-round payoff column ABSENT, data all present')
    from otree import export as otree_export
    import io
    buf = io.StringIO()
    otree_export.export_app('main', buf)
    header = buf.getvalue().splitlines()[0] if buf.getvalue() else ''
    cols = header.split(',')
    check(not any(c.strip() == 'player.payoff' for c in cols),
          'main export has NO player.payoff column (deliberately absent, '
          'not empty — see CODEBOOK "The payment record")')
    check(any('round_payoff' in c for c in cols),
          '…and DOES carry player.round_payoff, so no per-round data was lost')

    section('6. a non-completer is 0, not a running sum')
    payoff_nc, _, earned_nc, _ = ledger_row(codes[1])
    check(payoff_nc == 0 and earned_nc is None,
          f'a participant who never reached Results has participant.payoff 0 '
          f'and no earned ({payoff_nc}, {earned_nc})')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
