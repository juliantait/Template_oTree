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
  4. oTree's own per-round `player.payoff` setter does raise under
     AUTO_TABULATE_PAYOFFS=False — measured, because everything below depends
     on it. That raise is the FLOOR, not the guard: it fires inside a
     participant's request, so it is a dead page mid-round, which is why the
     enforcement moved to boot (§7/§8).
  5. The per-round `payoff` column is ABSENT from the export — deliberately
     gone, not accidentally empty — while `round_payoff` and the participant's
     `payoff_vector` still carry every round (no data lost).
  6. A non-completer's participant.payoff is 0: the one write runs only on the
     results page.
  7. RUNTIME: after a real walked journey, the underlying `_payoff` column is
     STILL UNTOUCHED on every round row of every app. This is the half a source
     scan cannot do — it catches a write reached through indirection
     (`setattr` with a computed name, a helper in a library), which
     `payoff_guard` is structurally blind to.
  8. BOOT: `payoff_guard` refuses a build that writes player.payoff — and does
     NOT refuse over the participant write, or over the many places this repo
     mentions `player.payoff` in prose. This is the half the walk cannot do —
     it covers code no walked path ever reaches.

§7 and §8 have DISJOINT blind spots and neither replaces the other; that is the
whole reason both are here (exp_pilots review, 2026-08-14).

Run: python scripts/tests/payoff_ledger_test.py    (boots oTree in-process; no server)
"""
import os
import re
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# Locked-down mode so the admin Payments page is behind the real login.
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

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


def payload_for(page, quiz_answers):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        # Only reached by a PROLIFIC config (gated on
        # prolific_capture_participant_id); harmless for the lab walk, and here
        # rather than in a second helper so §9's prolific journey and §1's lab
        # journey go through the SAME walker.
        'ConfirmProlificID': {'participant_id_external': 'PROLIFICTEST01'},
        'instructing': {},
        'quiz': dict(quiz_answers),
        # The task pages' names and payloads come from the ONE contract
        # module (scripts/tests/main_contract.py) — a game swap edits it there.
        **task_page_submits(),
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
    from quiz_answers import CORRECT   # one derivation, from the shipped items
    from otree import settings as otree_settings
    correct = dict(CORRECT)

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

    # oTree's setter really does raise — measured rather than assumed, because
    # §7's "nothing wrote it" and the whole one-ledger argument rest on it.
    # It is NOT the enforcement: this raise happens inside a participant's
    # request, so on a live upgrade it is a dead page mid-round rather than a
    # bookkeeping error. That is what §8's boot guard exists to get in front of.
    section("4. oTree's own setter raises — the floor, not the guard")
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
            # The one deliberate player.payoff write in the repo. payoff_guard
            # does not scan scripts/tests/ — see its _EXCLUDED_DIRS note, which names
            # this line as the reason.
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

    # =========================================================================
    section('7. RUNTIME: a real walked journey left _payoff untouched')
    # THE HALF A SOURCE SCAN CANNOT DO (exp_pilots review, 2026-08-14).
    # payoff_guard reads source, so it sees every syntactic write but is blind
    # to indirection — `setattr(obj, name, v)` with a computed name, a write
    # inside a library. This reads the UNDERLYING COLUMN (`_payoff`, bypassing
    # the property) after a full walk: if anything wrote a round payoff by any
    # route the walk covered, the column is non-zero and this fails. Its own
    # blind spot is the mirror image — it only knows about paths the walk
    # reached — which is why §8 exists as well.
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=codes[0]).one()
        untouched, rows_read = [], 0
        for app in ('before', 'intro', 'main', 'outro'):
            Model = get_models_module(app).Player
            for row in (s.query(Model)
                        .filter(Model.participant_id == p.id).all()):
                rows_read += 1
                if float(row._payoff or 0) != 0:
                    untouched.append(f'{app} r{row.round_number}='
                                     f'{float(row._payoff)}')
        check(rows_read > 0,
              f'read the per-round rows of a walked participant ({rows_read} '
              f'across four apps)')
        check(not untouched,
              f'every row still has _payoff 0 — nothing wrote a per-round '
              f'payoff by ANY route the walk covered '
              f'({"; ".join(untouched) if untouched else "none touched"})')
        # …and the ledger really is elsewhere, so the zeros above are evidence
        # of a payment recorded once, not of a study that pays nobody.
        check(float(p.payoff) > 0,
              f'…while participant.payoff carries the actual payment '
              f'({float(p.payoff)}) — zero rows, one ledger')
    finally:
        s.close()

    # =========================================================================
    section('8. BOOT: payoff_guard refuses a build that writes player.payoff')
    # THE HALF THE WALK CANNOT DO. This is the check that actually protects a
    # participant: oTree's raise in §4 fires mid-request, so on a live upgrade
    # it is a dead page, not a data error. payoff_guard moves the failure to
    # boot. The cases below pin BOTH directions — what it must catch, and the
    # two things it must never refuse a boot over.
    import ast
    import textwrap
    import payoff_guard

    scanned = payoff_guard.assert_no_player_payoff_writes()
    check(scanned > 0,
          f'the SHIPPED tree passes the boot guard, and scanned real files '
          f'({scanned}) — a guard checking nothing would also "pass"')
    scanned_files = {os.path.relpath(f, REPO_ROOT)
                     for f in payoff_guard.files_to_scan()}
    check({'main/__init__.py', 'outro/__init__.py', 'common.py'}
          <= scanned_files,
          'the app modules that handle payment are among the files scanned')
    check(not any(f.startswith('scripts/tests/') for f in scanned_files),
          "…and scripts/tests/ is NOT scanned — this file's own deliberate "
          '`pl.payoff = 5` (§4) must never fail a boot')

    def caught(src):
        return payoff_guard._scan_tree(ast.parse(textwrap.dedent(src)), 'p.py')

    must_catch = {
        'a plain write': 'player.payoff = 5',
        'a write on self': 'self.payoff = 5',
        'an augmented write': 'pl.payoff += 5',
        'a tuple-unpacked write': 'pl.payoff, other = 5, 6',
        'a loop-target write': 'for pl.payoff in [1]:\n    pass',
        'setattr with a literal name': "setattr(pl, 'payoff', 5)",
    }
    for label, src in must_catch.items():
        check(bool(caught(src)), f'CAUGHT: {label} ({src.splitlines()[0]!r})')

    # The two false alarms that would each refuse a boot over something
    # correct. The participant write IS the one-ledger decision, and this repo
    # documents `player.payoff` in prose in six files — a regex-based guard
    # would fail on both, which is why the scan parses.
    must_allow = {
        'the ONE legitimate write (outro.compute_final_payoff)':
            'p.participant.payoff = cu(target)',
        'a bare participant write': 'participant.payoff = 5',
        'setattr on a participant': "setattr(p.participant, 'payoff', 5)",
        "the game's own per-round field": 'player.round_payoff = 5',
        'a READ, not a write': 'y = player.payoff',
        'the string in a COMMENT': '# player.payoff = 5 raises here\nx = 1',
        'the string in a DOCSTRING': "'''writing player.payoff raises'''\nx = 1",
    }
    for label, src in must_allow.items():
        check(not caught(src), f'ALLOWED: {label}')

    # The blind spot, asserted rather than hoped for: if this ever starts
    # being caught, §7 is no longer the only thing covering indirection and
    # payoff_guard's docstring needs updating.
    check(not caught('setattr(pl, name, 5)'),
          'DECLARED BLIND SPOT: setattr with a COMPUTED name is not caught '
          'here — §7 is what covers it')

    # "Cannot answer" is not "clean" — the third outing of the
    # cannot-import-yet vs symbol-drifted split (CLAUDE.md).
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        pkg = os.path.join(tmp, 'brokenapp')
        os.makedirs(pkg)
        with open(os.path.join(pkg, '__init__.py'), 'w') as fh:
            fh.write('def f(:\n')          # a syntax error, not a payoff write
        writes, unreadable = payoff_guard.find_player_payoff_writes(tmp)
        check(not writes and len(unreadable) == 1,
              f'an unparseable module is reported as UNREADABLE, not as a '
              f'payoff write ({unreadable})')
        try:
            payoff_guard.assert_no_player_payoff_writes(tmp)
            check(False, 'an unparseable module must still fail the boot')
        except RuntimeError as exc:
            check('CANNOT SAY' in str(exc),
                  '…and it still fails the boot, saying it cannot answer '
                  'rather than blaming payoff')

    # And the whole point: a build carrying a write is REFUSED.
    with tempfile.TemporaryDirectory() as tmp:
        pkg = os.path.join(tmp, 'someapp')
        os.makedirs(pkg)
        with open(os.path.join(pkg, '__init__.py'), 'w') as fh:
            fh.write('def before_next_page(player, timeout_happened):\n'
                     '    player.payoff = player.round_payoff\n')
        try:
            payoff_guard.assert_no_player_payoff_writes(tmp)
            check(False, 'a build writing player.payoff must not boot')
        except RuntimeError as exc:
            check('someapp/__init__.py:2' in str(exc),
                  f'a build writing player.payoff REFUSES TO BOOT, naming the '
                  f'file and line')

    # =========================================================================
    section('9. ITEMISATION: the BONUS figure survives on its own')
    # =========================================================================
    # THE RULE (exp_pilots bossman, 2026-08-14): **ANY PAYMENT COMPONENT PAID
    # OUTSIDE OTREE MUST STILL BE REPRESENTED INSIDE OTREE, OR THE ADMIN
    # PAYMENTS PAGE BECOMES A PARTIAL FIGURE THAT LOOKS LIKE A TOTAL.**
    # Corollary, and the reason this section walks a PROLIFIC session
    # specifically: on Prolific the components are paid by DIFFERENT
    # MECHANISMS — the base as the study reward, the bonus through the bonus
    # payment flow — so the total alone is not enough. The bonus must be
    # separately visible, and it is the number that has to survive intact.
    #
    # WHY §1's CHECKS DID NOT COVER THIS. §1 pins that the total is CORRECT and
    # that both ledgers agree on it. A study can pass all of that while making
    # the actionable number unreadable, which is exactly the state this
    # codebase and the reviewer's own were both in — ours totalled but not
    # itemised, theirs itemised but incomplete (their base never entered oTree
    # at all). Neither shape has the property that matters, which is
    # ITEMISATION, so it is asserted here directly.
    #
    # NOTHING ABOUT THE CONFIG IS CHANGED BY THIS SECTION. participation_fee
    # stays 0.00 and participant.payoff is still composed exactly as
    # outro.compute_final_payoff composes it — that is an open decision with
    # Julian, and it changes what exported columns MEAN. This measures the
    # current state so the decision can be made against real numbers.
    import common          # the config accessor — never session.config['…']
    psess = ot.create_session('prolific', num_participants=1)
    pcode = ot.participant_codes(psess)[0]
    pclient = ot.client()
    results_page = walk_to_results(pclient, pcode, correct)
    check(page_name_of(path_of(results_page)) == 'Results',
          'a PROLIFIC participant walks to Results (the config whose '
          'components are paid through two different mechanisms)')

    s = DBSession()
    try:
        pp = s.query(Participant).filter_by(code=pcode).one()
        OutroPlayer = get_models_module('outro').Player
        row = (s.query(OutroPlayer)
               .filter(OutroPlayer.participant_id == pp.id).one())
        cfg = pp.session.config
        base = float(common.cfg(cfg, 'payment_show_up'))
        decision_bonus = float(row.selected_sum)
        payment_quiz_bonus = float(row.quiz_bonus_awarded)
        total = float(row.earned)
        admin_total = float(pp.payoff_plus_participation_fee())
        # THE BONUS = everything Prolific would pay through the bonus flow,
        # i.e. everything that is not the platform-paid base. Named once,
        # here, and derived from the stored components rather than from the
        # total minus something — a bonus computed as `total - base` would be
        # right by construction and would prove nothing about itemisation.
        bonus = decision_bonus + payment_quiz_bonus

        # --- each component exists as its own recorded figure ---------------
        check(row.field_maybe_none('selected_sum') is not None,
              f'the decision bonus is recorded on its own '
              f'(outro.Player.selected_sum = {decision_bonus})')
        check(row.field_maybe_none('quiz_bonus_awarded') is not None,
              f'the quiz bonus is recorded on its own '
              f'(outro.Player.quiz_bonus_awarded = {payment_quiz_bonus})')
        check(base > 0,
              f'the base payment is inside oTree, not only on the platform '
              f'(config payment_show_up = {base}) — the reviewer\'s study failed '
              f'exactly here, with a base oTree never saw')

        # --- and they RECONSTRUCT the total exactly ------------------------
        # No residue: if the parts do not add up, an itemised figure is a
        # guess and the payer cannot trust any single one of them.
        residue = total - (base + decision_bonus + payment_quiz_bonus)
        check(abs(residue) < 1e-9,
              f'base + decision bonus + quiz bonus == earned exactly '
              f'({base} + {decision_bonus} + {payment_quiz_bonus} = {total}, residue '
              f'{residue!r}) — nothing is unaccounted for')

        # --- THE BONUS IN ISOLATION ----------------------------------------
        check(bonus > 0,
              f'the BONUS figure exists on its own: {bonus} '
              f'(decision {decision_bonus} + quiz {payment_quiz_bonus})')
        check(abs((total - bonus) - base) < 1e-9,
              f'…and the total EXCEEDS it by exactly the base ({total} − '
              f'{bonus} = {total - bonus}, base {base}) — so a payer who put '
              f'the admin total into the Prolific bonus flow would overpay '
              f'the bonus by {base} on top of the study reward already paid')
        check(bonus != total,
              f'…which means the admin total ({total}) is NOT the bonus '
              f'({bonus}): one number cannot serve both mechanisms')
        # Each half of the bonus separately, so a study that routes only one
        # of them through a different flow can still read its figure.
        check(decision_bonus > 0 and payment_quiz_bonus > 0
              and decision_bonus + payment_quiz_bonus == bonus,
              f'both halves of the bonus are separately readable '
              f'({decision_bonus} + {payment_quiz_bonus}), not merged into one field')

        # --- the itemisation reaches the EXPORT, where the payer reads it ---
        buf = io.StringIO()
        otree_export.export_app('outro', buf)
        lines = buf.getvalue().splitlines()
        cols = [c.strip() for c in lines[0].split(',')] if lines else []
        for column in ('player.selected_sum', 'player.quiz_bonus_awarded',
                       'player.earned'):
            check(column in cols,
                  f'the export carries {column} as its own column')
        check(not any(c.endswith('.payment_show_up') for c in cols),
              'KNOWN GAP, asserted so it cannot change unnoticed: the BASE is '
              'a session-config value, not a per-participant column, so the '
              'app export alone does not carry it — it is in the session '
              'config the admin shows, and the receipt renders it')

        # --- what the participant sees vs what the PAYER sees ---------------
        # The participant already gets the breakdown. The gap is on the payer's
        # side, which is the whole point of the finding.
        receipt = re.sub(r'<[^>]+>', ' ', results_page.text)
        receipt = re.sub(r'\s+', ' ', receipt)
        check('Base payment' in receipt and 'Quiz bonus' in receipt,
              'the PARTICIPANT\'s receipt itemises (Base payment / Quiz bonus '
              '/ the selected rounds) — the breakdown exists, it just does '
              'not reach the person who pays')

        # --- THE MEASURED GAP on the admin page ----------------------------
        # Recorded, not endorsed. This is the concrete state Julian's config
        # decision is about; if a later change puts the bonus on the admin
        # page, THIS CHECK IS EXPECTED TO GO RED and should be rewritten to
        # assert the new behaviour rather than deleted.
        admin = admin_client()
        pay_page = admin.get(f'/SessionPayments/{psess.code}')
        pay_body = re.sub(r'\s+', ' ', pay_page.text)
        # SEARCH FOR THE CURRENCY-PREFIXED STRING, NEVER A BARE NUMBER. DO NOT
        # SIMPLIFY THIS BACK TO A SUBSTRING SEARCH.
        #
        # Measured on 2026-08-14, on the first draft of this section: the page
        # rendered a total of €150.50 and the base is 2.50, and "150.50"
        # CONTAINS "2.50". A bare-number search therefore reported the base as
        # PRESENT on a page that never mentions it — the check passed while
        # asserting the opposite of the truth.
        #
        # That is worse than no check: the two negative assertions below are
        # the entire evidence for the itemisation finding, and a substring
        # search makes them A CHECK THAT CANNOT FAIL — it finds the component
        # inside the total every time the components sum to it, which is
        # always. Same class as every other test-that-cannot-fail this repo has
        # hit. The prefix is what makes the assertion able to be wrong.
        symbol = '€'
        check(pay_page.status_code == 200
              and f'{symbol}{admin_total:.2f}' in pay_body,
              f'the admin Payments page shows the single total '
              f'{symbol}{admin_total:.2f} (HTTP {pay_page.status_code})')
        check(f'{symbol}{bonus:.2f}' not in pay_body,
              f'MEASURED GAP: the BONUS figure {symbol}{bonus:.2f} appears '
              f'NOWHERE on the admin Payments page — the number a Prolific '
              f'payer actually needs is not on the page they would use')
        check(f'{symbol}{base:.2f}' not in pay_body,
              f'…and neither does the base {symbol}{base:.2f} on its own: the '
              f'page is one undifferentiated total, which is actionable only '
              f'where a single mechanism pays everything')
    finally:
        s.close()

    print(f'\n--- §9 concrete numbers, completed PROLIFIC participant '
          f'(for the participation_fee / payoff-composition decision) ---')
    print(f'    base (config payment_show_up, inside earned) : {base}')
    print(f'    decision bonus (selected_sum)       : {decision_bonus}')
    print(f'    quiz bonus (quiz_bonus_awarded)     : {payment_quiz_bonus}')
    print(f'    BONUS ALONE (what Prolific bonuses) : {bonus}')
    print(f'    earned / participant.payoff         : {total}')
    print(f'    ADMIN PAYMENTS PAGE SHOWS           : {symbol}{admin_total:.2f}'
          f'   (one figure; participation_fee 0.00)')

    print(f'\n{"FAILED: " + str(len(_failures)) + " check(s)" if _failures else "ALL CHECKS PASSED"}')
    for f in _failures:
        print(f'  - {f}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
