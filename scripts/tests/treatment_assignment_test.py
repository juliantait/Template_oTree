#!/usr/bin/env python
"""TREATMENT ASSIGNMENT MOVED FROM SESSION CREATION TO ARRIVAL, balanced on
arrival, spent only by participants who actually reach the study.

    python scripts/tests/treatment_assignment_test.py

WHAT THIS PINS (the reason the item was real work, not a moved call — TODO.md,
DECISIONS.md). Treatment used to be dealt to every participant at session
creation, balanced by construction because `itertools.cycle` deals the whole
deck at once. It now assigns ON ARRIVAL at the first instructions page
(`intro.instructing`), which changes two things this test guards:

  A. CREATION SPENDS NOTHING. Every participant starts unassigned ('') — the
     column exists (never blank) but no cell is taken until someone arrives.
  B. ARRIVALS ARE BALANCED, on a different algorithm (least-filled + random
     tie-break). Six arrivals into two cells land exactly three and three, and
     the running order alternates to fill the current deficit — which is
     least-filled in action, not a lucky tie-break. A targeted pre-seed proves
     the same thing without relying on ties: seed an imbalance and the next
     arrival compensates.
  C. A CONSENT-DECLINED participant takes NO cell — they exit at -1 with
     treatment still ''.
  D. A DEVICE-GATED participant takes NO cell — they are held at the entry
     screen-out (-4) and never reach intro, treatment still ''.

C and D are the whole point of moving the assignment: post-randomisation dropout
is limited because the drop happens BEFORE randomisation. Each is asserted as a
PRESENCE + ABSENCE pair (CLAUDE.md): the participant IS in the declined /
screened-out state (exit code) AND holds no cell — an absence-only "treatment is
empty" would pass against any blank row, including one that never ran.

Driven over the in-process HTTP client against a throwaway database
(otree_inprocess.boot) in PRODUCTION mode — the assignment runs on a real page
GET, so it must be exercised over HTTP, not by calling the function. NOTE: a
FRESH client per participant. oTree's room sets a cookie that pins one browser
to one participant, so a shared client would re-enter the SAME participant every
time (and every walk after the first would early-return on the cell already
held) — a fresh client is a fresh browser, i.e. a distinct arrival.
"""
import os
import re
import sys
from collections import Counter

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)

from otree_inprocess import boot, page_name_of, path_of  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

import settings  # noqa: E402
from before import treatment_assignment  # noqa: E402

CELLS = treatment_assignment.CELLS

# A real phone User-Agent, so the entry device gate classifies it as 'phone'
# (copied from device_gate_test.py). The gate reads the entry request's header,
# so the only honest way to trip it is to send one.
PHONE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def csrf_of(html):
    m = re.search(r'name="csrftoken"[^>]*value="([^"]+)"', html) \
        or re.search(r'value="([^"]+)"[^>]*name="csrftoken"', html)
    return m.group(1) if m else ''


def code_of(resp):
    """The participant code from a /p/<code>/... URL."""
    return path_of(resp).split('/')[2]


def treatment_of(code):
    return ot.participant_vars(code).get('treatment_group', '')


def set_treatment(code, cell):
    """Pre-seed a participant's cell directly in the DB (for section B's
    pre-seed check). Writes through `.vars` so the mutable-dict change is
    flagged and committed, exactly as the app does."""
    from otree.database import DBSession
    from otree.models import Participant
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code).one()
        p.vars['treatment_group'] = cell
        s.commit()
    finally:
        s.close()


def walk(session, target, headers=None, payload=None, steps=8):
    """A FRESH-browser arrival: join the room and advance to `target`, POSTing
    the csrf token (plus any `payload`) at each page. Returns the response on
    `target`, or wherever it stalled."""
    cl = ot.client()                 # fresh client == fresh browser == new arrival
    r = cl.get(f'/join/{ot.anon_code(session)}',
               headers=headers or {}, allow_redirects=True)
    for _ in range(steps):
        if page_name_of(path_of(r)) == target:
            return r
        data = dict(csrftoken=csrf_of(r.text))
        if payload:
            data.update(payload)
        r = cl.post(path_of(r), data=data, headers=headers or {},
                    allow_redirects=True)
    return r


def main():
    section('A. Session creation spends no cell — everyone starts unassigned')
    s = ot.create_session('lab', num_participants=10)
    at_creation = [treatment_of(c) for c in ot.participant_codes(s)]
    check(all(t == '' for t in at_creation),
          f'every participant is unassigned (empty) at creation '
          f'(got {sorted(set(at_creation))!r})')

    section('B. Arrivals are balanced (least-filled + random tie-break)')
    arrivals = []
    for _ in range(6):
        r = walk(s, 'instructing')
        check(page_name_of(path_of(r)) == 'instructing',
              f'arrival reached the instructions page '
              f'(at {page_name_of(path_of(r))})')
        arrivals.append(treatment_of(code_of(r)))
    check(all(t in CELLS for t in arrivals),
          f'every arrival holds a real cell from {CELLS} (got {arrivals!r})')
    counts = Counter(arrivals)
    check(len(CELLS) == 2 and max(counts.values()) == min(counts.values()) == 3,
          f'six arrivals into two cells split exactly 3/3 (got {dict(counts)})')
    # The two participants nobody walked are still unassigned — assignment is an
    # arrival event, not a creation event.
    unwalked = [treatment_of(c) for c in ot.participant_codes(s)[6:]]
    check(all(t == '' for t in unwalked),
          f'participants who never arrived still hold no cell (got {unwalked!r})')

    section('B2. Least-filled is COUNTED, not guessed: a seeded imbalance is '
            'compensated')
    s2 = ot.create_session('lab', num_participants=6)
    # Seed the LAST two rows into CELLS[0] without them ever arriving, so the
    # deck is lopsided before anyone counts it. The last rows, deliberately:
    # /join hands out the first UNVISITED participant, so seeding the earliest
    # rows would just make the arrival BE a seeded row (it would keep its own
    # cell and prove nothing). Seeding the tail leaves an early, unassigned row
    # to be the actual arrival.
    seeded = ot.participant_codes(s2)[-2:]
    for c in seeded:
        set_treatment(c, CELLS[0])
    r = walk(s2, 'instructing')
    got = treatment_of(code_of(r))
    check(got == CELLS[1],
          f'the next arrival takes the UNDER-filled cell {CELLS[1]!r}, '
          f'not a tie-broken guess (got {got!r})')

    section('C. A consent-declined participant takes no cell')
    s3 = ot.create_session('prolific', num_participants=4)   # explicit consent on
    cl = ot.client()
    r = cl.get(f'/join/{ot.anon_code(s3)}', allow_redirects=True)
    check(page_name_of(path_of(r)) == 'welcome',
          f'prolific entry lands on the consent page (at {page_name_of(path_of(r))})')
    r = cl.post(path_of(r), data=dict(csrftoken=csrf_of(r.text), consent='False'),
                allow_redirects=True)
    v = ot.participant_vars(code_of(r))
    check(page_name_of(path_of(r)) == 'Ended'
          and v.get('exit_code') == settings.EXIT_CODES['no_consent'],
          f'declining routes to the ending with exit code -1 '
          f'(page {page_name_of(path_of(r))}, exit {v.get("exit_code")!r})')
    check(v.get('treatment_group', '') == '',
          f'…and it took NO treatment cell (got {v.get("treatment_group")!r})')

    section('D. A device-gated participant takes no cell')
    s4 = ot.create_session(
        'prolific', num_participants=4,
        modified_session_config_fields={'prolific_allowed_devices': ['computer']})
    r = walk(s4, 'instructing', headers={'user-agent': PHONE_UA})
    v = ot.participant_vars(code_of(r))
    # Presence: they are held at the entry gate (screened out, -4), never in intro.
    check(page_name_of(path_of(r)) == 'welcome'
          and v.get('exit_code') == settings.EXIT_CODES['screened_out'],
          f'a phone is screened out and held at entry with exit code -4 '
          f'(page {page_name_of(path_of(r))}, exit {v.get("exit_code")!r})')
    check(v.get('treatment_group', '') == '',
          f'…and it took NO treatment cell (got {v.get("treatment_group")!r})')

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
