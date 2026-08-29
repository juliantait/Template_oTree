#!/usr/bin/env python3
"""
monitor_session.py
==================

THE INVENTED SESSION the monitor preview is drawn from — the equivalent of a
`bodies/*.body.html` file for the one screen whose markup is not markup.

WHY THIS IS DATA AND NOT HTML
-----------------------------
Every other preview has a hand-written body composed of real shipped
components. The experimenter monitor cannot work that way: its rows do not
exist in any template. `experimenter_dashboard.py` ships a shell whose `<tbody>`
is literally `Waiting for first data…`, and every row, pill, marker and quiz
cell is built by that file's own `renderRow`/`stateHTML`/`timelineHTML` in
JavaScript, from the JSON the poll returns.

So writing the rows by hand would be a SECOND IMPLEMENTATION of renderRow —
the exact defect `CLAUDE.md` names ("one concept, two implementations… they
will drift, and the drift will be invisible"). Instead this file provides only
the DATA, in the shape `session_snapshot()` returns, and the preview is built
by running the dashboard's real JavaScript over it (see build_site_previews.py,
`build_monitor`). A change to how a pill is drawn reaches this preview on the
next rebuild; a change to the row SHAPE breaks it loudly, here, where the keys
are named.

THIS FIXTURE IS A DELIBERATE MIXED LAB-PLUS-ONLINE DEMO — READ THIS FIRST
-------------------------------------------------------------------------
This fixture DEPARTS ON PURPOSE from the generator's standing rule that every
screen must be a single profile AS RESOLVED. It is not a lab session and it is
not an online session: it is a SHOWCASE built to exercise as much of the
dashboard's vocabulary as fits one canvas, for the academic website. The four
red TERMINAL/ejection pills below (screened out, declined consent,
comprehension DQ, tab-monitor DQ), the live tab-monitor count, and the
awaiting-return pill can NEVER all appear in one real session — each needs a
module a given profile turns on, and a lab session (implicit consent, no device
gate, no comprehension DQ, no tab monitor) shows none of them. They are here
anyway, on invented ONLINE rows, so the website shows what the monitor CAN
display rather than the sparse subset one profile happens to reach.

**So do not read the terminal pills as a bug, and do not "correct" this back to
a strict lab session.** The earlier version of this file WAS a strict lab
session and said so at length; this one is not, by choice, because a preview
that shows only what the lab profile resolves leaves the monitor's most
important states — the ejections an operator scans for — off the website
entirely. The `build_site_previews.py` MONITOR_NOTE that ships in the built
file says the same thing in as many words, so a viewer does not mistake the mix
for a configuration this study runs.

WHAT IS INVENTED, AND WHAT IS NOT REAL DATA
-------------------------------------------
Nothing below came from a participant. The lab seats are cubicle-bank labels
(two banks, A1–A8 and B1–B5 — thirteen seats) a lab session assigns. The online
rows carry OBVIOUSLY FAKE placeholder ids — a run of zeros and the word "demo" —
not real Prolific platform ids (a Prolific row's label IS the participant's
platform id, so a real one would be someone's account). There are no completion
codes, no contact details and no bank details — the dashboard has no column for
any of those — and the few euro figures ride invented seat numbers. The single
unlabelled row carries a synthetic oTree participant code.

WHAT THE FIXTURE EXERCISES (one row each unless combined, per the row budget)
-----------------------------------------------------------------------------
    * the six-step timeline with the marker at every phase (entry → done);
    * the round counter inside Task, and the ✓ done marker on finished rows;
    * the four quiz-cell states: idle / filling / red at the limit / violet
      "forced";
    * live vs settled intro timers AND the second TOTAL timer beside each;
    * the earnings pill, and the lab-only Non-SEPA condition pill riding a
      FINISHED row (outcome and condition in separate channels);
    * both amber stall phases (Intro long, and a Task round long);
    * the dimmed not-arrived row and the unlabelled-row code fallback;
    * NEW: all four terminal/ejection pills (on the four online rows), a live
      tab-monitor count climbing towards its limit on an in-progress row, and
      the awaiting-return pill on a finished row with no "back" click recorded
      — the last two riding LAB seats (A7 and B3), because the demo shows the
      lab labels carrying the full pill vocabulary rather than spending a scarce
      online row on each.

THE ROW BUDGET IS A HARD CANVAS LIMIT — THIRTEEN SEATS STAY, ONLINE ROWS GIVE
-----------------------------------------------------------------------------
The preview is a FIXED 1920x1080 canvas with nothing to scroll: a row too many
is a row silently clipped off the bottom. MEASURED against this dashboard (the
overview block ~104px, the sticky header ~35px, ~49px a row, ~59px for a row
whose State cell carries two pills): EIGHTEEN rows fit and nineteen overflow by
~26px. check_site_previews.py asserts the table does not outgrow the canvas, so
eighteen is a hard ceiling — if a future edit adds a row, MEASURE AGAIN.

The THIRTEEN lab seats (two full banks, A1–A8 and B1–B5) are fixed and stay. So
of the eighteen rows, thirteen are the lab seats, one is the unlabelled
oTree-code fallback, and the remaining FOUR are online. The four online rows
carry the four terminal/ejection pills — the states most naturally read as
online. The other two online-only conditions (the live tab-monitor count and
the awaiting-return pill) DO NOT need their own rows: they ride LAB seats here,
because this demo shows the lab labels WITH the full pill vocabulary rather than
splitting the vocabulary off onto a separate cohort. States are also combined
onto single rows the way the dashboard naturally does (earnings + Non-SEPA on
one finished row; a tab-monitor count on a task row; awaiting-return on a
finished row), and at most two rows carry two State pills, because a third would
push the table past the canvas.

Usage: imported by build_site_previews.py. Not executable on its own.
"""

# --- the session-constant half of the payload --------------------------------
# These are the values the shipped config resolves (settings.py:
# SESSION_CONFIG_DEFAULTS num_experimental_rounds, quiz_comprehension_max_failures,
# REAL_WORLD_CURRENCY_CODE=EUR) and the shipped stall thresholds
# (experimenter_dashboard.stall_legend). They are restated here rather than
# imported because this file is a FIXTURE: the preview must keep showing a
# coherent session even if a copied study retunes its own thresholds, and a
# fixture that silently followed settings.py would produce rows whose "9:41"
# stopped being over the limit without anything saying so.
SESSION_TITLE = 'Demo session — lab + online (CREED)'
SESSION_CODE = 'demo1234'      # invented; a real oTree session code is 8 chars
CURRENCY = 'EUR'
ROUNDS_TOTAL = 10
QUIZ_MAX_FAILURES = 3
STALL_LEGEND = [
    {'label': 'Entry', 'seconds': 60},
    {'label': 'Intro (instructions + quiz)', 'seconds': 480},
    {'label': 'Task (one round)', 'seconds': 180},
    {'label': 'Questionnaire', 'seconds': 300},
]

# THE FOUR TERMINAL/EJECTION states, restated in the shape the server derives
# from settings.EXIT_CODE_META (see experimenter_dashboard._FALLBACK_EXIT_CODE_META,
# which these mirror). Restated for the same fixture reason as the thresholds
# above: the preview must keep drawing the four pills even against a study that
# retunes its own exit table. The `when` groups the ending in the overview
# exactly as ending_when() does on the server: an ENTRY turn-away vs an ejection
# after STARTING. Emoji are the literal glyphs the dashboard ships.
_TERMINAL_META = {
    'screened_out':  dict(emoji='\U0001f4f5', label='Screened out',   when='entry'),
    'no_consent':    dict(emoji='✋',     label='Declined consent', when='entry'),
    'comprehension': dict(emoji='❌',     label='Comprehension DQ', when='started'),
    'tab_monitor':   dict(emoji='\U0001f440', label='Tab monitor DQ',   when='started'),
}


def _row(label, step, **kw):
    """One row in `_participant_row`'s shape, with the keys that are None on an
    ordinary row defaulted — so each row below states only what is TRUE of it
    and a reader can see the differences rather than the boilerplate."""
    row = dict(
        label=label,
        code=kw.pop('code', ''),
        arrived=True,
        step=step,
        task_round=None,
        terminal=None,
        terminal_emoji=None,
        terminal_label=None,
        finished=False,
        quiz=None,
        intro_seconds=None,
        intro_live=False,
        # TOTAL TIME (pill 2 of the per-participant timer, 2026-08-23). Defaults
        # None like intro_seconds; the derivation loop below fills it for rows
        # that have an intro time, holding total >= intro (see _total_seconds).
        total_seconds=None,
        total_live=False,
        earnings=None,
        seconds_on_page=0,
        stalled=False,
        stall_limit=None,
        stall_elapsed=None,
        stall_section=None,
        non_sepa=False,
        awaiting_return=False,   # finished, no "back" click — redirect sessions
        monitor_count=None,      # tab-monitor count while it climbs
        monitor_max=None,
        entry_only=False,
        # THE OVERVIEW's inputs, in _participant_row's shape. `treatment` feeds
        # the per-cell FINISHED split; `waiting_for` is [] for everybody because
        # this template ships no wait page (see DECISIONS.md); the ending fields
        # are None on an ordinary row and filled by the derivation loop on a
        # terminal one.
        treatment='',
        waiting_for=[],
        terminal_when=None,
        ending_undeclared=False,
        ending_mismatch=False,
        current_page='',
        unmapped_app=None,
    )
    row.update(kw)
    return row


def _quiz(state, wrong=0, display=0):
    """The quiz cell in `_quiz_cell`'s shape. `fill` is derived here the way the
    server derives it, so the filling bar's width is never a typed number."""
    return dict(state=state, attempts_wrong=wrong, display=display,
                fill=round(min(1.0, wrong / QUIZ_MAX_FAILURES), 3))


# --- the room ----------------------------------------------------------------
# EIGHTEEN rows (the canvas ceiling — see the row-budget note in the docstring):
# FOUR online rows with obviously-fake ids that sort FIRST because a digit-leading
# label precedes a letter-leading one under natural_label_key, then the two full
# lab banks A1–A8 and B1–B5 (thirteen seats), then the unlabelled arrival LAST.
# This is exactly the order sort_rows_by_displayed_name would leave them in — the
# preview skips the server, so the order is written out. Most rows carry more
# than one state, because a running session's rows do.
#
# The fake online id: eighteen zeros then "demoNN". It reads as a 24-character
# platform id (a Prolific label's length) while the run of zeros and the word
# "demo" make it OBVIOUSLY not a real account. The four sort among themselves by
# the trailing number and all sort ahead of the lettered seats.
_OID = '000000000000000000demo%02d'

ROWS = [
    # ===== ONLINE COHORT (fake ids, sort first) =============================
    # The four terminal/ejection states — each needs a module (device gate,
    # explicit consent, comprehension DQ, tab monitor) the lab profile turns
    # off, so they read most naturally on online rows. The other two online-only
    # conditions (a climbing tab-monitor count, awaiting-return) ride LAB seats
    # below; see the module docstring on the deliberate mix and the row budget.

    # SCREENED OUT at the device/screen-out gate: red terminal pill, 📵 marker
    # at the entry step. An ENTRY turn-away.
    _row(_OID % 1, 'entry', current_page='DeviceCheck',
         terminal='screened_out', quiz=_quiz('idle')),

    # DECLINED CONSENT: ✋ terminal, also an ENTRY turn-away. Needs the explicit
    # consent radio (online); the lab consents implicitly, so it can never show.
    _row(_OID % 2, 'entry', current_page='Consent',
         terminal='no_consent', quiz=_quiz('idle')),

    # COMPREHENSION DQ: ❌ terminal, ejected DURING the quiz after too many
    # wrong attempts — an ejection after STARTING. The quiz cell still shows the
    # red at-limit count that got them ejected.
    _row(_OID % 3, 'quiz', current_page='Quiz',
         terminal='comprehension', quiz=_quiz('red', 3), intro_seconds=356),

    # TAB-MONITOR DQ: 👀 terminal, ejected mid-task for leaving the tab too many
    # times — an ejection after STARTING. Once terminal the DQ pill says it; the
    # BEFORE-state (a count still climbing) rides lab seat A7 below.
    _row(_OID % 4, 'task', current_page='GameStart', task_round=4,
         terminal='tab_monitor', quiz=_quiz('green', 0, 1), intro_seconds=228),

    # ===== LAB COHORT — bank A (cubicles A1–A8) ============================
    # On the consent page: present, nothing to report yet, idle quiz cell.
    _row('A1', 'entry', current_page='Consent', quiz=_quiz('idle')),

    # STALLED IN INTRO: 9:41 against the 8:00 threshold. Amber row tint (find it
    # across the room) + the timing pill (which phase, how long) — the two
    # complementary channels the dashboard CSS argues for at length. Live intro
    # timer, so the TOTAL beside it keeps counting too.
    _row('A2', 'instructions', current_page='Instructions',
         quiz=_quiz('idle'), intro_seconds=581, intro_live=True,
         stalled=True, stall_elapsed=581, stall_limit=480,
         stall_section='Intro'),

    # Mid-quiz, one wrong attempt so far: the cell FILLS towards the limit.
    _row('A3', 'quiz', current_page='Quiz', quiz=_quiz('progress', 1),
         intro_seconds=341, intro_live=True),

    # In the task at successive rounds — the round-of-total counter on the
    # marker. Settled intro timers now (they have left the intro).
    _row('A4', 'task', current_page='GameStart', task_round=2,
         quiz=_quiz('green', 0, 1), intro_seconds=204),

    # HIT THE THREE-FAILURE LIMIT. In a LAB session that is not a
    # disqualification (quiz_comprehension_dq off) — so a lab row runs on with a
    # red cell as the operator's cue, distinct from the online comprehension DQ
    # above where the SAME red count DID eject. That contrast is the point.
    _row('A5', 'quiz', current_page='Quiz', quiz=_quiz('red', 3),
         intro_seconds=402, intro_live=True),

    # FORCED past the quiz from the admin panel without ever answering it:
    # violet, and it says the word rather than a count, because nothing is wrong
    # with the participant. Now in the task; settled intro timer.
    _row('A6', 'task', current_page='GameStart', task_round=5,
         quiz=_quiz('forced'), intro_seconds=245),

    # TAB-MONITOR CLIMBING (not yet ejected): the live count "2 of 3" in the
    # State cell — the operator's cue to speak to them BEFORE the DQ. Riding a
    # LAB seat by choice (see the row budget): the demo shows the lab labels
    # carrying the full pill vocabulary. Green quiz, settled intro timer.
    _row('A7', 'task', current_page='GameStart', task_round=6,
         quiz=_quiz('green', 1, 2), intro_seconds=172,
         monitor_count=2, monitor_max=3),

    # STALLED ON A TASK ROUND: the second amber phase, judged against the
    # per-round 3:00 threshold rather than the intro's 8:00.
    _row('A8', 'task', current_page='GameStart', task_round=3,
         quiz=_quiz('green', 0, 1), intro_seconds=188,
         stalled=True, stall_elapsed=312, stall_limit=180,
         stall_section='Task round'),

    # ===== LAB COHORT — bank B (cubicles B1–B5) ============================
    # In the questionnaire, having passed the quiz.
    _row('B1', 'questionnaire', current_page='Feedback',
         quiz=_quiz('green', 0, 1), intro_seconds=195),

    # FINISHED: green row, ✓ done marker, earnings pill.
    _row('B2', 'done', finished=True, quiz=_quiz('green', 0, 1),
         intro_seconds=210, earnings=18.50),

    # FINISHED BUT AWAITING RETURN: green ✓ finished AND the amber "↩ no return
    # click" condition — completed the study but no "back to the platform" click
    # recorded, so their submission may still be open. Riding a LAB seat like the
    # tab-monitor count above: the demo puts the online-only conditions on lab
    # labels rather than spending a scarce online row on each.
    _row('B3', 'done', finished=True, quiz=_quiz('green', 0, 1),
         intro_seconds=243, earnings=12.75, awaiting_return=True),

    # FINISHED **and** flagged: the green row says they completed, the red pill
    # says their IBAN is outside SEPA and the transfer needs checking. Outcome
    # and condition in separate channels — collapsing them (a red row) is the
    # thing the pill split exists to prevent. Non-SEPA is lab-only.
    _row('B4', 'done', finished=True, quiz=_quiz('green', 1, 2),
         intro_seconds=372, earnings=14.00, non_sepa=True),

    # NOT ARRIVED: dimmed, and hideable by the header's toggle. The dim
    # treatment means "nobody is here" and nothing else. It still carries an
    # idle quiz cell, because `_participant_row` always builds one — a row
    # WITHOUT it would be a shape the server never sends.
    _row('B5', 'entry', arrived=False, entry_only=True, quiz=_quiz('idle')),

    # NO LABEL YET (a bare-link arrival before the ID page): the row falls back
    # to the oTree participant code, which is what an operator can still act on.
    # Unlabelled rows sort last.
    _row('', 'entry', code='k7m2p9xr', current_page='Welcome',
         quiz=_quiz('idle')),
]


# --- fill the derived per-row fields, so the overview has something to tally ---
# Done here rather than on each _row(...) call above so the row definitions stay
# readable: each states what is TRUE of that participant, and the mechanical
# consequences are applied once. TERMINAL rows get their emoji/label/when from
# _TERMINAL_META, exactly as the server reads them from EXIT_CODE_META, so the
# preview groups the endings the way the real screen does rather than by a second
# hand-written map. TREATMENT alternates across the rows that reached the
# instructions — an invented but balanced assignment, matching what
# balance-on-arrival produces.
_n = 0
for _r in ROWS:
    _t = _r.get('terminal')
    if _t:
        _m = _TERMINAL_META[_t]
        _r['terminal_emoji'] = _m['emoji']
        _r['terminal_label'] = _m['label']
        _r['terminal_when'] = _m['when']
    # A cell is spent only by somebody who reached the instructions — so not by
    # a never-arrived row, and not by one still at ENTRY or turned away there.
    if _r.get('arrived') and _r.get('step') not in ('entry',):
        _r['treatment'] = ('row', 'column')[_n % 2]
        _n += 1
    # TOTAL TIME (pill 2): derived from the intro time so the invariant total >=
    # intro is visibly held rather than typed row by row (see _total_seconds).
    # A live row's total keeps counting in the browser; a finished/terminal
    # row's is frozen; a row with no intro time yet gets none.
    _it = _r.get('intro_seconds')
    if _it is not None:
        if _r.get('finished') or _r.get('terminal'):
            _r['total_seconds'] = _it + 1130   # + the whole task and outro
            _r['total_live'] = False
        elif _r.get('intro_live'):
            _r['total_seconds'] = _it + 40      # + the entry block before intro
            _r['total_live'] = True
        else:
            _r['total_seconds'] = _it + (_r.get('stall_elapsed') or 260)
            _r['total_live'] = True


def payload():
    """The `/data` JSON, in `session_snapshot()`'s shape."""
    # TOTAL PAYMENTS, summed here from the SAME row earnings the preview
    # renders, exactly as _earnings_total does server-side (over the FINISHED
    # rows — those that carry an `earnings` figure). Without it the merged
    # EARNINGS pill, which is gated on data.earnings_total, would degrade to
    # nothing and the website's monitor preview would silently drop the payment
    # figures — the stale-preview trap CLAUDE.md warns about.
    _earned = [r['earnings'] for r in ROWS if r.get('earnings') is not None]
    earnings_total = (dict(total=float(sum(_earned)), n=len(_earned))
                      if _earned else dict(total=None, n=0))
    # THE FOUR OVERVIEW PILLS, tallied here from the SAME rows the preview
    # renders — the same discipline as earnings_total above, and for the same
    # reason: a pill gated on a key this file forgets degrades to NOTHING, and
    # the website's monitor preview then silently shows a dashboard without its
    # overview.
    _live = [r for r in ROWS if not r.get('error')]
    _fin = [r for r in _live if r.get('finished')]
    _term = [r for r in _live if r.get('terminal')]
    endings = dict(
        in_progress=len([r for r in _live if r.get('arrived')
                         and not r.get('finished') and not r.get('terminal')]),
        stalled=len([r for r in _live if r.get('stalled')]),
        finished=len(_fin),
        ended_early=len(_term),
        groups=[dict(when=w, label=lab,
                     n=len([r for r in _term if r.get('terminal_when') == w]),
                     reasons=[])
                for w, lab in (('entry', 'turned away at entry'),
                               ('started', 'ejected after starting'),
                               (None, 'unclassified'))],
        undeclared=[],
    )
    # The treatment split. Invented cells matching settings.TREATMENT_CELLS, so
    # the preview shows the shipped placeholder study rather than inventing a
    # design the template does not have.
    _cells = ['row', 'column']
    treatments = dict(
        cells=[dict(cell=c,
                    assigned=len([r for r in _live if r.get('treatment') == c]),
                    finished=len([r for r in _fin if r.get('treatment') == c]))
               for c in _cells],
        unassigned=len([r for r in _live if not r.get('treatment')]),
        off_scheme=[],
    )
    # TIME: two averages over two DIFFERENT populations (intro over everyone
    # whose intro time is settled, experiment over finishers) — the split is the
    # point, so the preview must not print one denominator for both.
    _intro = [r['intro_seconds'] for r in _live
              if r.get('intro_seconds') is not None and not r.get('intro_live')]
    time_summary = dict(intro_n=len(_intro), experiment_n=len(_fin))
    if _intro:
        time_summary['intro_avg'] = sum(_intro) / len(_intro)
    if _fin:
        time_summary['experiment_avg'] = 1338.0
    return dict(
        treatments=treatments,
        endings=endings,
        time_summary=time_summary,
        ok=True,
        session=dict(code=SESSION_CODE, config_name='demo',
                     display_name=SESSION_TITLE, num_participants=len(ROWS)),
        rows=ROWS,
        rounds_total=ROUNDS_TOTAL,
        quiz_max_failures=QUIZ_MAX_FAILURES,
        stall_seconds={p['label']: p['seconds'] for p in STALL_LEGEND},
        stall_legend=STALL_LEGEND,
        poll_seconds=2,
        currency=CURRENCY,
        earnings_total=earnings_total,
        now=0,
    )
