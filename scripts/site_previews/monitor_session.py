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

THIS IS PLACEHOLDER DATA AND IT GOES ON A PUBLIC WEBSITE
--------------------------------------------------------
Nothing below came from a participant. The labels are seat numbers a lab
session assigns; there are NO Prolific IDs (a Prolific row's label IS the
participant's platform ID), no completion codes, no contact details and no bank
details — the dashboard has no column for any of those, and the one row that
touches money at all shows a euro total and a "Non-SEPA" flag against an
invented seat number. The single unlabelled row carries an obviously synthetic
oTree participant code.

IT IS A **LAB** SESSION, AS THE LAB PROFILE ACTUALLY RESOLVES
-------------------------------------------------------------
The generator's standing rule — EVERY SCREEN MUST BE THE PROFILE AS RESOLVED,
NOT AS REMEMBERED — decides which states may appear here, and it rules out the
most eye-catching ones. `RECRUITMENT_PROFILES['lab']` sets `tab_monitor=False`,
`comprehension_dq=False`, `device_capture=False` and `explicit_consent=False`,
and every one of the four TERMINAL states needs a module the lab profile turns
off:

    📵 screened out    needs the device/screen-out gate   (lab: off)
    ✋ declined consent needs the explicit consent radio   (lab: implicit)
    ❌ comprehension DQ needs comprehension_dq             (lab: off)
    👀 tab monitor DQ   needs tab_monitor                  (lab: off)

So a lab monitor shows NO terminal pills and no pink rows, and putting them
here to make the screenshot livelier would be inventing a configuration — the
same error that once shipped a consent preview with a radio button no lab
participant has ever seen. The note on the built file says this in as many
words, so nobody reads the absence as a missing feature.

Everything the lab profile DOES produce is exercised below, deliberately, one
row each: the six-step timeline with the marker at every phase, the round
counter inside Task, the ✓ done marker, green finished rows, the four quiz-cell
states (idle / filling / red at the limit / violet "forced"), live vs settled
intro timers, earnings pills, both amber stall phases, the Non-SEPA condition
pill riding a FINISHED row (outcome and condition in separate channels — the
point of the pill split), dimmed not-arrived rows, and the unlabelled-row code
fallback.

Usage: imported by build_site_previews.py. Not executable on its own.
"""

# --- the session-constant half of the payload --------------------------------
# These are the values the LAB config actually resolves (settings.py:
# SESSION_CONFIG_DEFAULTS num_experimental_rounds=10, comprehension_max_failures=3,
# REAL_WORLD_CURRENCY_CODE=EUR) and the shipped stall thresholds
# (experimenter_dashboard.stall_legend). They are restated here rather than
# imported because this file is a FIXTURE: the preview must keep showing a
# coherent session even if a copied study retunes its own thresholds, and a
# fixture that silently follows settings.py would produce rows whose "9:41"
# stopped being over the limit without anything saying so.
SESSION_TITLE = 'Lab session (CREED)'
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
        earnings=None,
        seconds_on_page=0,
        stalled=False,
        stall_limit=None,
        stall_elapsed=None,
        stall_section=None,
        non_sepa=False,
        awaiting_return=False,   # Prolific redirect sessions only — never lab
        monitor_count=None,      # tab monitor is off in the lab profile
        monitor_max=None,
        entry_only=False,
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
# Eighteen seats mid-session plus one not-yet-labelled arrival: most rows
# unremarkable, which is the truthful shape
# of a running session and the reason the amber tint has a job to do. Ordered by
# displayed name with the unlabelled row last, exactly as `sort_rows_by_displayed_name`
# would leave them — the preview skips the server, so the order is written out.
ROWS = [
    # On the consent page: present, nothing to report yet.
    _row('Seat 01', 'entry', current_page='Consent', quiz=_quiz('idle')),

    # STALLED IN INTRO: 9:41 against the 8:00 threshold. Amber row tint (find it
    # across the room) + the timing pill (which phase, how long) — the two
    # complementary channels the dashboard CSS argues for at length.
    _row('Seat 02', 'instructions', current_page='Instructions',
         quiz=_quiz('idle'), intro_seconds=581, intro_live=True,
         stalled=True, stall_elapsed=581, stall_limit=480,
         stall_section='Intro'),

    # Mid-quiz, one wrong attempt so far: the cell FILLS towards the limit.
    _row('Seat 03', 'quiz', current_page='Quiz', quiz=_quiz('progress', 1),
         intro_seconds=341, intro_live=True),

    _row('Seat 04', 'task', current_page='GameStart', task_round=2,
         quiz=_quiz('green', 0, 1), intro_seconds=204),
    _row('Seat 05', 'task', current_page='GameStart', task_round=6,
         quiz=_quiz('green', 1, 2), intro_seconds=172),
    _row('Seat 06', 'task', current_page='GameStart', task_round=9,
         quiz=_quiz('green', 2, 3), intro_seconds=380),

    _row('Seat 07', 'questionnaire', current_page='Feedback',
         quiz=_quiz('green', 0, 1), intro_seconds=195),

    # FINISHED: green row, ✓ done marker, earnings pill.
    _row('Seat 08', 'done', finished=True, quiz=_quiz('green', 0, 1),
         intro_seconds=210, earnings=18.50),

    # FINISHED **and** flagged: the green row says they completed, the red pill
    # says their IBAN is outside SEPA and the transfer needs checking. Outcome
    # and condition in separate channels — collapsing them (a red row) is the
    # thing the pill split exists to prevent.
    _row('Seat 09', 'done', finished=True, quiz=_quiz('green', 1, 2),
         intro_seconds=372, earnings=14.00, non_sepa=True),

    # FORCED past the quiz from the admin panel without ever answering it:
    # violet, and it says the word rather than a count, because nothing is
    # wrong with the participant.
    _row('Seat 10', 'task', current_page='GameStart', task_round=5,
         quiz=_quiz('forced'), intro_seconds=245),

    # Hit the three-failure limit. In a LAB session that is not a
    # disqualification — comprehension_dq is off — so the row runs on and the
    # red cell is the operator's cue to go and speak to them.
    _row('Seat 11', 'quiz', current_page='Quiz', quiz=_quiz('red', 3),
         intro_seconds=402, intro_live=True),

    # STALLED ON A TASK ROUND: the second amber phase, judged against the
    # per-round 3:00 threshold rather than the intro's 8:00.
    _row('Seat 12', 'task', current_page='GameStart', task_round=3,
         quiz=_quiz('green', 0, 1), intro_seconds=188,
         stalled=True, stall_elapsed=312, stall_limit=180,
         stall_section='Task round'),

    _row('Seat 13', 'task', current_page='GameStart', task_round=7,
         quiz=_quiz('green', 0, 1), intro_seconds=161),
    _row('Seat 14', 'instructions', current_page='Instructions',
         quiz=_quiz('idle'), intro_seconds=72, intro_live=True),
    _row('Seat 15', 'task', current_page='GameStart', task_round=4,
         quiz=_quiz('green', 1, 2), intro_seconds=258),
    _row('Seat 16', 'questionnaire', current_page='Feedback',
         quiz=_quiz('green', 0, 1), intro_seconds=178),
    _row('Seat 17', 'done', finished=True, quiz=_quiz('green', 0, 1),
         intro_seconds=182, earnings=16.25),

    # NOT ARRIVED: dimmed, and hideable by the header's toggle. The dim
    # treatment means "nobody is here" and nothing else.
    #
    # ONE such row, not two, and the reason is the canvas rather than the
    # design: nineteen rows is what fits 1920x1080 with the summary strip
    # still on screen. At twenty the strip fell 2px past the bottom edge and
    # the page scrolled — which the preview shell cannot show, because the
    # canvas is a fixed frame with nothing to scroll it. MEASURED 2026-08-16:
    # 49px per row, table top at y=53, strip ends at y=1033 with nineteen.
    # ADDING A ROW HERE MEANS MEASURING AGAIN.
    #
    # It carries an idle quiz cell like every other row: `_participant_row`
    # always builds one, so a row WITHOUT it would be a shape the server never
    # sends — the empty box is part of what a not-arrived row looks like.
    _row('Seat 18', 'entry', arrived=False, entry_only=True,
         quiz=_quiz('idle')),

    # NO LABEL YET (a bare-link arrival before the ID page): the row falls back
    # to the oTree participant code, which is what an operator can still act
    # on. Unlabelled rows sort last.
    _row('', 'entry', code='k7m2p9xr', current_page='Welcome',
         quiz=_quiz('idle')),
]


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
    return dict(
        ok=True,
        session=dict(code=SESSION_CODE, config_name='lab',
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
