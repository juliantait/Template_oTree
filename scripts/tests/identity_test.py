#!/usr/bin/env python
"""PARTICIPANT IDENTITY: one row per Prolific id, re-entry, and the duplicate
label that would otherwise be a permanent lockout.

    python scripts/tests/identity_test.py        (oTree must be importable)

Runs IN-PROCESS against a throwaway database (scripts/tests/otree_inprocess.py) because
two of these cases cannot be produced over HTTP against a running server: a
duplicate label has to be planted directly in the database, and rebinding a room
to a NEW session is an operation, not a request.

WHY IT MATTERS. oTree resolves a returning participant by label
(`otree/views/participant.py`): `q.filter_by(label=label).one()`, catching only
`NoResultFound`. Two rows sharing a label therefore raise `MultipleResultsFound`
— an uncaught 500 on the front door, for the participant who really owns that
id, permanently. And the device screen-out's whole premise is that somebody can
leave on a phone and come back on a computer AND BE REJOINED TO THE SAME ROW.
Rejoining IS that lookup.

WHAT IS CHECKED

  1. RE-ENTRY. The same id entering twice is ONE row, at the page they left.
     Case and whitespace differences are the same person. Two different ids stay
     two rows.
  2. TWO TABS AT ONCE. The same id entering twice, interleaved, must not create
     a second row, must not create a duplicate label, and must not 500.
  3. BARE LINK THEN AN ID. Somebody who entered on a bare room link holds an
     unlabelled row; the id they type on the confirmation page becomes their
     label, and a later entry carrying that id rejoins them.
  4. A CLASHING CLAIM IS REFUSED, SILENTLY. Typing an id another row already
     holds does not move the label, does not block the typist, stores their
     typed value verbatim anyway, records the OWNING row's participant code in
     `prolific_label_conflict`, and renders a page identical to a clean one.
  5. A DUPLICATE THAT EXISTS ANYWAY DOES NOT 500. With two rows planted on the
     same label, entry joins the earliest instead of raising.
  6. A ROOM REBOUND TO A NEW SESSION ORPHANS PEOPLE. Labels are matched WITHIN a
     session, so the same id lands on a fresh row in the new session. That is
     oTree's behaviour, not a bug we can fix — it is checked here so the
     operational rule in README ("Rebinding a room mid-study") stays true.

Exit 0 = all checks passed. Never touches a real database.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


DESKTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 '
            'Safari/604.1')


def browser(ua=DESKTOP_UA):
    """A fresh client with its own cookie jar — i.e. a different browser."""
    c = ot.client()
    c.headers['User-Agent'] = ua
    return c


def enter_room(client, room='study', label=None):
    """Enter through the room the way a Prolific link does.

    `welcome_page_ok=1` is what oTree's room welcome page adds when the
    participant clicks through it (otree/views/participant.py:
    AssignVisitorToRoom renders that page first and only assigns a row on the
    second request). Skipping the click, not the assignment.
    """
    url = f'/room/{room}?welcome_page_ok=1'
    if label is not None:
        url += f'&participant_label={label}'
    return client.get(url, allow_redirects=True)


def code_of(resp):
    parts = path_of(resp).strip('/').split('/')
    return parts[1] if len(parts) >= 2 and parts[0] == 'p' else None


def labels_in(session):
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        return [p.label for p in s.query(Participant)
                .filter_by(_session_code=session.code).order_by(Participant.id)
                if p.label]
    finally:
        s.close()


# =============================================================================
# PLANTED SETUP MUST BE VERIFIED BEFORE IT IS TRUSTED
# =============================================================================
# A SETUP THAT SILENTLY NO-OPS IS INDISTINGUISHABLE FROM A FEATURE THAT WORKS —
# the collapsed-distinction rule (CLAUDE.md) living in test code, where it is
# worse, because the failure is invisible: the suite goes GREEN and reports that
# it tested something it never set up.
#
# MEASURED HERE, 2026-08-12, not hypothesised. Stubbing `plant_label` to do
# nothing, and separately stubbing the terminal-state write to do nothing, was
# run against this suite. Most checks went red — but in BOTH experiments the
# screened-out tie-break below ("joins the SCREENED-OUT earliest row") stayed
# GREEN with no setup whatsoever, because with nothing planted oTree's own
# fallback (`filter_by(visited=False).first()`) hands back the earliest row,
# which is the same row the assertion expects. The one check that pins the soft
# wall's joinability could not tell "the guard chose this row" from "nothing was
# planted and oTree returned it by default".
#
# TWO FIXES, BOTH NEEDED:
#
#  1. PLANTED ROWS ARE MARKED VISITED, because that is what a row carrying a
#     duplicate label actually is: somebody who has been in the study. It also
#     removes the ambiguity at its root — oTree's fallback only ever returns
#     `visited=False` rows, so once a planted row is visited, an assertion that
#     names it can ONLY be satisfied by our guard's Python label match having
#     run. (This is the second trap the reference implementation hit: they
#     planted a FINISHED row that was still `visited=False`, so oTree handed it
#     to a fresh entrant and their not-finished tie-break was never exercised.)
#  2. EVERY PLANT IS ASSERTED, immediately, before the behaviour that depends
#     on it — `assert_planted` below.
# =============================================================================

def plant_label(code, label, visited=True):
    """Write a label straight onto a row — the hand-edited / legacy case.

    Marks the row VISITED by default: a row that carries a participant label in
    the wild is one somebody has actually entered on (oTree stamps the label in
    `mark_visited_and_record_label`, which sets `visited` in the same breath).
    Planting an unvisited row would leave oTree's own
    `filter_by(visited=False).first()` fallback able to return it, so a later
    assertion naming that row could be satisfied without our guard doing
    anything — see the note above.
    """
    ot.set_label(code, label)
    if visited:
        set_visited(code, True)


def set_visited(code, visited=True):
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        p.visited = visited
        s.commit()
    finally:
        s.close()


def set_exit_code(code, exit_code, screened_out=False):
    """Put a row into a terminal state directly, to test which duplicate row a
    returning participant joins."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        # `vars` is a read-only view; the participant FIELDS are attributes on
        # the row (settings.PARTICIPANT_FIELDS), which is what writes them.
        p.exit_code = exit_code
        p.screened_out = screened_out
        s.commit()
    finally:
        s.close()


def row_state(code):
    """(label, visited, exit_code, screened_out) as actually stored."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        return dict(label=p.label, visited=bool(p.visited),
                    exit_code=p.vars.get('exit_code'),
                    screened_out=bool(p.vars.get('screened_out')))
    finally:
        s.close()


def assert_planted(code, label=None, exit_code=None, screened_out=None,
                   visited=True, what=''):
    """Confirm a planted row REALLY holds the state the next assertion assumes.

    Call this after every plant, before testing the behaviour that depends on
    it. See the note above for the measured reason this exists.
    """
    st = row_state(code)
    if label is not None:
        check(identity_same(st['label'], label),
              f'SETUP {what}: row {code} really carries the label '
              f'{label!r} (stored {st["label"]!r})')
    if visited is not None:
        check(st['visited'] == visited,
              f'SETUP {what}: row {code} really has visited={visited} '
              f'(got {st["visited"]}) — an unvisited row would be returned by '
              f'oTree\'s own fallback, so the assertion below would not be '
              f'testing our guard at all')
    if exit_code is not None:
        check(st['exit_code'] == exit_code,
              f'SETUP {what}: row {code} really holds exit_code={exit_code} '
              f'(got {st["exit_code"]})')
    if screened_out is not None:
        check(st['screened_out'] == screened_out,
              f'SETUP {what}: row {code} really holds '
              f'screened_out={screened_out} (got {st["screened_out"]})')


def identity_same(a, b):
    import identity
    return identity.same_label(a, b)


def post_form(client, resp, data):
    from http_flow_test import FormParser, build_payload
    fp = FormParser(); fp.feed(resp.text)
    payload = build_payload(fp.inputs, data, {}, warn=False)
    return client.post(path_of(resp), data=payload, allow_redirects=True)


def before_player_label(code):
    """`before.Player.participant_label` for one participant — the EXPORT copy
    of the label, written unconditionally in `before.welcome.before_next_page`
    (i.e. not behind any Prolific flag)."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        row = s.query(Participant).filter_by(code=code).one()
        import before
        player = s.query(before.Player).filter_by(participant_id=row.id).one()
        return player.field_maybe_none('participant_label')
    finally:
        s.close()


def main():
    import common
    import identity

    # =====================================================================
    section('1. one row per id; case and whitespace are the same person')
    session = ot.create_session('prolific', num_participants=12,
                                room_name='study')
    a = browser()
    r = enter_room(a, label='abc123xyz')
    first_code = code_of(r)
    check(r.status_code == 200 and first_code, f'entry with an id: 200, {first_code}')

    # The same id, a different browser (a different machine, even): same row.
    b = browser()
    r2 = enter_room(b, label='abc123xyz')
    check(code_of(r2) == first_code, 'the same id in another browser is the SAME row')

    # SPELLED DIFFERENTLY — the same person, and they must reach the SAME ROW.
    # oTree's own lookup is `filter_by(label=…)`, i.e. SQL, so it matches (or
    # does not) according to the DATABASE COLLATION: `ABC123XYZ` misses a row
    # holding `abc123xyz` on postgres, takes a fresh row, and then the id typed
    # on the confirmation page is refused as a conflict with the very row it
    # just failed to match. Our guard matches in Python instead, with the same
    # normalisation conflict detection uses, so the answer cannot differ between
    # sqlite here and postgres in production.
    c = browser()
    r3 = enter_room(c, label='ABC123XYZ')
    check(r3.status_code == 200, 'a differently-CASED id does not error')
    check(code_of(r3) == first_code,
          f'entry as ABC123XYZ REJOINS the row holding abc123xyz '
          f'({code_of(r3)} vs {first_code})')
    d0 = browser()
    r3b = enter_room(d0, label='  abc123xyz  ')
    check(code_of(r3b) == first_code,
          f'entry with surrounding whitespace rejoins the same row '
          f'({code_of(r3b)} vs {first_code})')
    check(len([l for l in labels_in(session)
               if identity.same_label(l, 'abc123xyz')]) == 1,
          'and still exactly ONE row holds that identity, in any spelling')
    check(identity.same_label('  ABC123XYZ  ', 'abc123xyz'),
          'identity.same_label: whitespace-collapsed and case-folded match')
    check(identity.normalise_label('  abc  123  ') == 'abc 123',
          'identity.normalise_label collapses inner whitespace, strips the ends')

    # A DIFFERENT id is a different person: two rows.
    d = browser()
    r4 = enter_room(d, label='different99')
    check(code_of(r4) != first_code, 'a different id gets a DIFFERENT row')

    # =====================================================================
    section('2. the same id in two tabs at once')
    t1, t2 = browser(), browser()
    r1 = enter_room(t1, label='twotabs01')
    r2 = enter_room(t2, label='twotabs01')          # interleaved, same id
    r1b = t1.get(path_of(r1), allow_redirects=True)
    r2b = t2.get(path_of(r2), allow_redirects=True)
    check(code_of(r1) == code_of(r2), 'both tabs are the SAME participant row')
    check(max(r1.status_code, r2.status_code, r1b.status_code,
              r2b.status_code) < 500, 'no 5xx in either tab')
    labels = labels_in(session)
    check(labels.count('twotabs01') == 1,
          f'exactly ONE row carries the label (got {labels.count("twotabs01")})')

    # =====================================================================
    section('3. bare link, then an id typed on the confirmation page')
    bare = browser()
    r = enter_room(bare)                            # no id at all
    bare_code = code_of(r)
    check(bare_code is not None, f'a bare link still admits a participant ({bare_code})')
    check(not (ot.participant_vars(bare_code).get('label') or ''),
          'a bare-link participant has NO label (normal, not a clash)')
    # consent -> confirmation page -> type an id
    r = post_form(bare, r, {'consent': 'True', 'is_mobile': '',
                            'device_info_json': '', 'participant_id_url': ''})
    check(page_name_of(path_of(r)) == 'ConfirmProlificID',
          f'reached the id page (got {page_name_of(path_of(r))})')
    r = post_form(bare, r, {'participant_id_external': 'typedid77'})
    check(labels_in(session).count('typedid77') == 1,
          'the typed id became this row\'s label')
    back = browser()
    r = enter_room(back, label='typedid77')
    check(code_of(r) == bare_code,
          'a later entry carrying that id REJOINS the same row')
    check(page_name_of(path_of(r)) not in (None, 'welcome'),
          f'and resumes where they left off (at {page_name_of(path_of(r))}), '
          f'not back at the start')

    # =====================================================================
    section('4. a clashing claim is REFUSED, and the participant is told nothing')
    # A second participant enters on a bare link and types an id that the row
    # from section 3 already owns — a typo, or a friend's id.
    clash = browser()
    r = enter_room(clash)
    clash_code = code_of(r)
    r = post_form(clash, r, {'consent': 'True', 'is_mobile': '',
                             'device_info_json': '', 'participant_id_url': ''})
    clash_page_html = r.text
    r = post_form(clash, r, {'participant_id_external': 'TYPEDID77'})   # same id
    check(max(r.status_code, 0) < 500, 'the clashing submit does not 5xx')
    check(labels_in(session).count('typedid77') == 1,
          'still exactly ONE row holds that label — no duplicate was created')
    v = ot.participant_vars(clash_code)
    check(not (v.get('label') or ''),
          'the clashing row keeps its OWN (empty) label — no marker written into it')

    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        row = s.query(Participant).filter_by(code=clash_code).one()
        import before
        player = s.query(before.Player).filter_by(participant_id=row.id).one()
        typed = player.field_maybe_none('participant_id_external')
        conflict = player.field_maybe_none('prolific_label_conflict')
    finally:
        s.close()
    check(typed == 'TYPEDID77',
          f'their typed value is stored VERBATIM anyway (got {typed!r})')
    check(conflict == bare_code,
          f'prolific_label_conflict carries the OWNING row\'s participant code '
          f'(got {conflict!r}, owner is {bare_code})')
    extra = (v.get('participant_extra') or {}).get('prolific_label_conflict')
    check(bool(extra) and extra[0].get('label') == 'TYPEDID77',
          f'the fuller record says WHICH id was refused ({extra})')
    # SILENT: the participant is not blocked and not told. They are on the next
    # page, with no error text anywhere.
    check(page_name_of(path_of(r)) != 'ConfirmProlificID',
          f'they were NOT held on the id page (now at {page_name_of(path_of(r))})')
    check('otree-form-errors' not in r.text and 'conflict' not in r.text.lower(),
          'no error, no warning, no mention of a conflict on the page they get')

    # =====================================================================
    section('5. a duplicate that exists anyway must not 500')
    dup_session = ot.create_session('prolific', num_participants=4)
    codes = ot.participant_codes(dup_session)
    plant_label(codes[0], 'dupe0001')
    plant_label(codes[1], 'dupe0001')      # the state oTree cannot survive
    check(labels_in(dup_session).count('dupe0001') == 2,
          'two rows planted on the same label (a hand-edited / legacy database)')
    assert_planted(codes[0], label='dupe0001', what='dupe/earliest')
    assert_planted(codes[1], label='dupe0001', what='dupe/later')
    anon = ot.anon_code(dup_session)
    dupe_browser = browser()
    r = dupe_browser.get(f'/join/{anon}?participant_label=dupe0001',
                         allow_redirects=True)
    check(r.status_code < 500,
          f'entry with the duplicated id does NOT 500 (got {r.status_code}) — '
          f'without the guard this is MultipleResultsFound')
    check(code_of(r) == codes[0],
          f'it joins the EARLIEST row holding the label (got {code_of(r)})')
    # And oTree's own function is the thing that was made safe.
    from otree.views import participant as pv
    check(getattr(pv.get_participant_by_label, '_duplicate_label_guarded', False),
          'identity.install_duplicate_label_guard is installed at import')

    # =====================================================================
    section('5b. WHICH duplicate row a returning participant joins')
    # EARLIEST THAT IS NOT FINISHED. Earliest is the row they will have been
    # using — but a FINISHED row is a dead end to join (a completed session's
    # ending, with no way forward), which is the very failure this guard exists
    # to prevent.
    fin_session = ot.create_session('prolific', num_participants=4)
    fcodes = ot.participant_codes(fin_session)
    plant_label(fcodes[0], 'dupefin01')
    plant_label(fcodes[1], 'dupefin01')
    set_exit_code(fcodes[0], 1)             # the EARLIEST row has finished
    # THE SETUP, ASSERTED BEFORE THE BEHAVIOUR (see the note at plant_label):
    # both rows really hold the label and are really visited, and the earliest
    # really is finished. Without this, a plant that quietly did nothing would
    # be tested as if it had worked.
    assert_planted(fcodes[0], label='dupefin01', exit_code=1,
                   what='finished/earliest')
    assert_planted(fcodes[1], label='dupefin01', what='finished/later')
    r = browser().get(f'/join/{ot.anon_code(fin_session)}'
                      f'?participant_label=dupefin01', allow_redirects=True)
    check(r.status_code < 500, 'finished-earliest duplicate: no 500')
    check(code_of(r) == fcodes[1],
          f'joins the later UNFINISHED row ({code_of(r)}), not the finished '
          f'earliest one ({fcodes[0]})')

    # ...but SCREENED OUT is terminal and NOT finished, and it must stay
    # joinable: joining that row is exactly what lifts the screen-out. If this
    # ever picks the later row instead, the soft wall is broken — the returning
    # participant lands on a fresh row and their cleared verdict is lost.
    so_session = ot.create_session('prolific', num_participants=4)
    scodes = ot.participant_codes(so_session)
    plant_label(scodes[0], 'dupeso001')
    plant_label(scodes[1], 'dupeso001')
    set_exit_code(scodes[0], -4, screened_out=True)   # earliest is SCREENED OUT
    # THIS IS THE CHECK THAT WENT GREEN ON AN EMPTY SETUP (see plant_label).
    # Both plants are asserted, and both rows are VISITED, so the assertion
    # below can no longer be satisfied by oTree's unvisited-row fallback
    # returning the earliest row by default — it can only pass if our guard
    # matched the label in Python and `_choose_row` kept a screened-out (i.e.
    # terminal but NOT finished) row joinable.
    assert_planted(scodes[0], label='dupeso001', exit_code=-4,
                   screened_out=True, what='screenedout/earliest')
    assert_planted(scodes[1], label='dupeso001', what='screenedout/later')
    r = browser().get(f'/join/{ot.anon_code(so_session)}'
                      f'?participant_label=dupeso001', allow_redirects=True)
    check(r.status_code < 500, 'screened-out-earliest duplicate: no 500')
    check(code_of(r) == scodes[0],
          f'joins the SCREENED-OUT earliest row ({code_of(r)} vs {scodes[0]}) — '
          f'terminal is not finished, and joining it is what clears the wall')

    # A CASE-DIFFERING PAIR IS A DUPLICATE. Two rows holding `MiXeD01` and
    # `mixed01` are one person, so the guard must see them as the duplicate it
    # exists for — not as two unrelated rows it never compares.
    mx_session = ot.create_session('prolific', num_participants=4)
    mcodes = ot.participant_codes(mx_session)
    plant_label(mcodes[0], 'MiXeD01')
    plant_label(mcodes[1], 'mixed01')
    assert_planted(mcodes[0], label='MiXeD01', what='mixedcase/earliest')
    assert_planted(mcodes[1], label='mixed01', what='mixedcase/later')
    r = browser().get(f'/join/{ot.anon_code(mx_session)}'
                      f'?participant_label=MIXED01', allow_redirects=True)
    check(r.status_code < 500, 'case-differing duplicate: no 500')
    check(code_of(r) in (mcodes[0], mcodes[1]),
          f'a third spelling joins one of the two existing rows ({code_of(r)})')
    seen_mx = (ot.participant_vars(code_of(r)).get('participant_extra')
               or {}).get('duplicate_label_seen')
    check(bool(seen_mx) and len(seen_mx[0].get('rows') or []) == 2,
          f'…and BOTH spellings are recorded as the same duplicate identity '
          f'({seen_mx})')

    section('5c. the guard is LOUD when it actually sees a duplicate')
    # Graceful for the participant, never silent for us.
    v = ot.participant_vars(fcodes[1])
    seen = (v.get('participant_extra') or {}).get('duplicate_label_seen')
    check(bool(seen), f'the joined row records that a duplicate was SEEN ({seen})')
    if seen:
        check(seen[0].get('label') == 'dupefin01' and len(seen[0].get('rows') or []) == 2,
              f'…naming the label and BOTH rows for an operator ({seen[0]})')
    # …and says nothing at all on an ordinary, single-row lookup.
    clean = browser()
    r = enter_room(clean, label='notadupe01')
    v = ot.participant_vars(code_of(r))
    check((v.get('participant_extra') or {}).get('duplicate_label_seen') is None,
          'an ordinary lookup records NOTHING (the loud path is duplicates only)')
    check((v.get('participant_extra') or {}).get('duplicate_label_guard_missing')
          is None,
          'and does not flag a missing guard, because the guard is installed')

    section('5d. the install: benign early failure vs version drift')
    from otree.views import participant as pv
    # (a) CANNOT IMPORT YET — what settings.py hits at boot. Must NOT raise, and
    #     must leave a later install free to succeed. If somebody hardens this
    #     into a raise, the boot goes down with it.
    real_import = identity._import_views
    # BOTH SHAPES of "not importable yet". The second is the one that actually
    # happens: importing otree.views from settings.py raises AttributeError
    # ("partially initialized module 'settings' …"), because oTree's own
    # settings module reads SESSION_CONFIGS back out of ours mid-execution. A
    # guard that only caught ImportError would crash every boot — this pair is
    # here so nobody narrows it back.
    for exc_type, why in ((ImportError, 'otree.views not importable yet'),
                          (AttributeError,
                           "partially initialized module 'settings' has no "
                           "attribute 'SESSION_CONFIGS'")):
        identity._import_views = (
            lambda e=exc_type, m=why: (_ for _ in ()).throw(e(m)))
        try:
            outcome = identity.install_duplicate_label_guard()
            check(outcome == identity.NOT_IMPORTABLE,
                  f'an early install failing with {exc_type.__name__} returns '
                  f'NOT_IMPORTABLE, quietly (got {outcome!r})')
        except Exception as exc:
            check(False, f'an early install must NOT raise, even on '
                         f'{exc_type.__name__} (raised {exc!r})')
        finally:
            identity._import_views = real_import
    # The REAL boot proves it too: settings.py's early install records why it
    # could not run, and the app-module install then succeeds.
    check(any(o == identity.NOT_IMPORTABLE for o, _ in identity._install_log),
          f'the real boot took the benign early-failure path at least once '
          f'({[o for o, _ in identity._install_log]})')
    check(identity.install_duplicate_label_guard() == identity.ALREADY,
          'and the real install still succeeds afterwards (idempotent)')
    check(identity.guard_is_installed(),
          'the guard is in place and detectable — not something you have to '
          'take on faith')

    # (b) IMPORTED, WRONG SHAPE — version drift. Loud, wherever it happens.
    original = pv.get_participant_by_label
    try:
        pv.get_participant_by_label = None
        try:
            identity.install_duplicate_label_guard()
            check(False, 'a missing entry lookup must RAISE (it did not)')
        except RuntimeError as exc:
            check('get_participant_by_label' in str(exc),
                  'a MISSING entry lookup raises, naming the symbol')

        def wrong_shape(sess, participant_label):    # renamed parameter
            return None
        pv.get_participant_by_label = wrong_shape
        try:
            identity.install_duplicate_label_guard()
            check(False, 'a changed signature must RAISE (it did not)')
        except RuntimeError as exc:
            check('signature' in str(exc) or 'takes' in str(exc),
                  'a CHANGED SIGNATURE raises rather than installing a wrapper '
                  'written for the old one')
        # …and the same drift is a hard failure at the asserting point.
        try:
            identity.assert_duplicate_label_guard()
            check(False, 'assert_duplicate_label_guard must raise on drift')
        except RuntimeError:
            check(True, 'assert_duplicate_label_guard raises on drift too')
    finally:
        pv.get_participant_by_label = original
    check(identity.guard_is_installed(),
          'the real guard is restored after the drift simulation')

    # =====================================================================
    section('6. rebinding the room to a NEW session orphans people')
    # Labels are matched WITHIN a session (session.pp_set), so a participant
    # mid-study in the old session is not rejoined after a rebind: they get a
    # fresh row in the new session and start again. Operational rule, not a bug.
    old_code = None
    mover = browser()
    r = enter_room(mover, label='mover0001')
    old_code = code_of(r)
    check(old_code is not None, f'the mover entered the OLD session ({old_code})')
    new_session = ot.create_session('prolific', num_participants=4,
                                    room_name='study')      # REBIND
    r2 = enter_room(browser(), label='mover0001')
    check(r2.status_code < 500, 'entry after a rebind does not 500')
    check(code_of(r2) != old_code,
          'the same id gets a NEW row in the NEW session (they are orphaned)')
    check('mover0001' in labels_in(new_session),
          'the id is now held by a row in the new session')
    check('mover0001' in labels_in(session),
          'and the old row still holds it, in the old session, with their data')

    section('7. LAB SEAT LABELS ARE NATIVE oTree, AND NEED NO PROLIFIC FLAG')
    # -------------------------------------------------------------------------
    # Julian's lab room links carry a SEAT as the participant label
    # (`/room/study?participant_label=a2`), and the question is whether
    # `prolific_capture_participant_id` has anything to do with that. It does
    # not, and this section is here so that stays true — the label machinery was
    # touched twice recently (identity.py's duplicate guard, and the
    # 2026-08-13 `prolific_` rename), and lab seating is not what either was
    # about.
    #
    # THE TWO ARE INDEPENDENT MECHANISMS:
    #   * the LABEL is oTree's own. `AssignVisitorToRoom` reads
    #     `?participant_label=` from the query string and `InitializeParticipant`
    #     calls `participant.set_label(label)` (otree/views/participant.py, oTree
    #     6.0.15) — no flag of ours is consulted anywhere on that path;
    #   * `prolific_capture_participant_id` gates only the PROLIFIC id plumbing:
    #     the ConfirmProlificID page, the hidden `participant_id_url` field, and
    #     the script that reads `?PROLIFIC_PID=` (or `?participant_label=`) into
    #     it. With the flag off, none of that renders — and the label is already
    #     set regardless, by oTree, before our code sees the request.
    lab = ot.create_session('lab', num_participants=4, room_name='study')
    check(lab.config.get('prolific_capture_participant_id') is False,
          'the lab profile really does ship prolific_capture_participant_id OFF '
          '(so this section is evidence about the flag being off, not a config '
          'that quietly turned it on)')

    seat = browser()
    r = enter_room(seat, label='a2')
    seat_code = code_of(r)
    check(r.status_code < 500 and seat_code is not None,
          f'a lab participant enters on a seat link (row {seat_code})')
    check(labels_in(lab) == ['a2'],
          f'the row carries the SEAT as its label (got {labels_in(lab)})')

    # Walk them off the entry pages, so `before.welcome.before_next_page` runs:
    # the seat must reach the EXPORT column too, not only participant.label.
    for _ in range(4):
        if page_name_of(path_of(r)) not in ('startpage', 'welcome'):
            break
        r = post_form(seat, r, {})
    check(r.status_code < 500, 'the entry pages submit without a 5xx')
    seat_export = before_player_label(seat_code)
    check(seat_export == 'a2',
          'and before.Player.participant_label holds the seat as well, so the '
          f'seat reaches the EXPORT (got {seat_export!r})')

    # RE-ENTRY on the same seat link — a lab participant whose browser was
    # closed, or who was moved to another machine, must land back on THEIR row.
    again = browser()
    r2 = enter_room(again, label='a2')
    check(code_of(r2) == seat_code,
          'the same seat link re-enters the SAME row, not a fresh one')
    check(labels_in(lab) == ['a2'],
          'and no second row has taken the seat label')

    # THE DASHBOARD ROW SHOWS THE SEAT. It keys its rows on participant.label
    # and falls back to the participant CODE when there is none, so a broken
    # seat label would show as an opaque code — which is exactly what an
    # experimenter scanning a room must not get.
    try:
        import experimenter_dashboard
        snapshot = experimenter_dashboard.session_snapshot(lab)
        row = next((x for x in snapshot['rows'] if x.get('code') == seat_code),
                   None)
        check(row is not None and row.get('label') == 'a2',
              'the dashboard row shows the SEAT (a2), not a fallback code '
              f'(got {row.get("label")!r} / code {row.get("code")!r})'
              if row else 'the dashboard has a row for the seated participant')
    except Exception as exc:
        # NOT silently skipped: a check that cannot run is not a check that
        # passed. If another worker is mid-edit in experimenter_dashboard.py,
        # re-run this suite rather than reading this as a real failure.
        check(False, f'could not read the dashboard snapshot ({type(exc).__name__}: '
                     f'{exc}) — re-run if experimenter_dashboard.py is mid-edit')

    # AND THE OTHER DIRECTION, so this is evidence of INDEPENDENCE rather than
    # of "the lab happens to work": the same kind of seat link into a session
    # with `prolific_capture_participant_id` turned ON gets the same label. The
    # flag moves the Prolific ID plumbing; it never moves the seat.
    #
    # LAST IN THIS SECTION because there is only one room and binding a session
    # to it REBINDS it (see section 6) — everything asserted above is already
    # done, and the dashboard snapshot above reads its session directly from the
    # database rather than through the room.
    flag_on = ot.create_session(
        'lab', num_participants=2, room_name='study',
        modified_session_config_fields={'prolific_capture_participant_id': True})
    r3 = enter_room(browser(), label='b7')
    check(r3.status_code < 500 and labels_in(flag_on) == ['b7'],
          'with prolific_capture_participant_id ON, a seat link still labels the '
          f'row with the seat (got {labels_in(flag_on)})')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'   - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
