"""EXPERIMENTER DASHBOARD — a live, read-only, at-a-glance view of a running
session, served IN-PROCESS as extra routes on oTree's own Starlette app.

Import as ``import experimenter_dashboard``. Like ``identity`` and ``common``,
this file MUST stay at the project root: the install hook does a top-level
import and oTree puts the project root on ``sys.path``.

Open it at ``/experimenter_dashboard`` (session list) or
``/experimenter_dashboard/<session_code>`` (the dashboard itself), behind
oTree's OWN admin login.

THE TWO RULES EVERYTHING HERE SERVES
------------------------------------
1. **STRICTLY READ-ONLY.** No handler ever assigns to a model attribute,
   writes a participant var, creates a row, or migrates anything. oTree's
   CommitTransactionMiddleware wraps every request in this app with a
   ``db.commit()`` — which is exactly why nothing here may dirty the session:
   the commit must always have nothing to do.
2. **A BUG HERE BREAKS THE DASHBOARD, NEVER A PARTICIPANT PAGE.** The same
   rule as "instrumentation must never break a page" (CLAUDE.md). Every
   handler is wrapped: an exception renders an error panel (HTTP 200, so the
   middleware has nothing to roll back) instead of propagating; each
   participant ROW is additionally wrapped, so one poisoned row renders as an
   error row instead of killing the whole table. The ONE deliberate exception
   is the auth check: if deciding "is this an operator?" itself fails, the
   answer is DENY (403), never the error panel — fail soft after the login
   gate, fail CLOSED at it.

WHY IN-PROCESS IS ACCEPTABLE, AND ITS ONE REAL COST
---------------------------------------------------
``otree/asgi.py`` builds the Starlette app from ``otree.urls.routes``, a plain
module-level list built by ``get_urlpatterns()`` at import — so a route
appended to that list before ``otree.asgi`` is imported is served exactly like
oTree's own (the same monkeypatch shape as identity.py's duplicate-label
guard, and the same install discipline; see INSTALLING below). The cost:
oTree's CommitTransactionMiddleware serialises requests under a GLOBAL lock,
so a slow dashboard request delays participant pages behind it. Every query
here is therefore a walk of one session's few-hundred rows, nothing more, and
the poll floor (2s, client-side, skip-if-in-flight) keeps the request rate
bounded. Do not add anything per-request that scales past the session.

AUTH — REUSED, NOT INVENTED
---------------------------
The endpoints subclass ``otree.views.cbv.AdminView`` and reuse its login
cookie check (``_is_logged_in``), the very same mechanism
``url_patterns_from_builtin_module`` arms for oTree's own admin pages.
``_requires_login`` is True under AUTH_LEVEL 'STUDY' **and 'DEMO'** —
deliberately stricter than oTree's SessionMonitor, which demo mode leaves
open. This page shows earnings and per-participant conduct, and the brief is
"never reachable by a participant"; demo mode's convenience is not worth the
hole. With AUTH_LEVEL unset (local dev) there is no login, like the rest of
the admin.

INSTALLING — the identity.py discipline, with ONE deliberate difference
-----------------------------------------------------------------------
``install_dashboard_route()`` is quiet when ``otree.urls`` is legitimately
not importable yet (or is mid-import), and LOUD — a raise — when the module
loaded but ``routes`` / ``AdminView`` are not the shapes this file was
written against, which is version drift. THE DIFFERENCE FROM IDENTITY: the
call site (end of ``outro/__init__.py``) catches even the drift raise and
logs it instead of failing the boot. identity's guard protects participants
from a 500, so a boot-time failure is the right trade there; this module is
an OPERATOR CONVENIENCE, and no dashboard defect — drift included — may cost
participants their session. A missing dashboard is also self-evident to its
only user (the operator staring at a 404), which a missing identity guard
never was.

ADDING A COLUMN — the extension point, in one place
---------------------------------------------------
Row data is assembled in ``_participant_row``; every key it returns is
shipped verbatim in the /data JSON. To add a column:

  1. compute the value in ``_participant_row`` (marked ADD A COLUMN HERE),
     defensively — a failure must degrade to a blank cell, not a dead row;
  2. add a matching <th> to ``_COLGROUP_HTML`` and a cell renderer branch in
     the page's ``renderRow`` JS (marked ADD A COLUMN HERE (render));
  3. nothing else. The poll loop repaints whatever the row dict carries.

CONFIG — tuneable without touching this file
--------------------------------------------
Read from ``settings.py`` AT REQUEST TIME if present, else these defaults:

  DASHBOARD_STALL_SECONDS_BEFORE   (60)  — amber after this long on one page,
  DASHBOARD_STALL_SECONDS_INTRO    (480)   PER PHASE: the entry block, the whole
  DASHBOARD_STALL_SECONDS_TASK     (180)   intro app, ONE task round, the outro.
  DASHBOARD_STALL_SECONDS_OUTRO    (300)   See STALL_SETTING_BY_STEP for why one
  DASHBOARD_STALL_SECONDS_DEFAULT  (300)   number for the whole flow could not be
                                           right at both ends of it.
  DASHBOARD_POLL_SECONDS    (default 2)   — poll interval; 2s is also the
                            FLOOR, enforced server-side, whatever settings
                            says. The client skips a tick while the previous
                            request is in flight.
"""

import json
import logging
import re
import time
from html import escape

logger = logging.getLogger(__name__)

# --- config defaults (see the module docstring; settings.py overrides) -------
DEFAULT_STALL_SECONDS = 300
DEFAULT_POLL_SECONDS = 2
POLL_FLOOR_SECONDS = 2

# THE STALL THRESHOLD IS PER PHASE (Julian, 2026-08-13, round-2 item 6).
#
# One number for the whole flow was a collapsed distinction (CLAUDE.md): "too
# long on the consent page" and "too long reading the instructions" differ by an
# order of magnitude, so a single threshold is necessarily wrong for one of them
# — low enough to catch a stuck entry page and every reader is amber; high
# enough for the instructions and nobody stuck at entry is ever flagged. Both
# failures are silent: the operator just learns to ignore the colour.
#
# Maps a TIMELINE STEP to the settings.py name that governs it. Steps not listed
# (`done`, and UNMAPPED_STEP) fall back to DASHBOARD_STALL_SECONDS_DEFAULT —
# `done` never stalls anyway (a finished row is not active), and an unmapped app
# has no phase to have a threshold for, which is the honest answer.
#
# `entry` covers the whole `before` app, `instructions` and `quiz` are both the
# `intro` app and share ONE threshold (Julian asked for a threshold on INTRO,
# not on each of its halves), `task` is per SINGLE ROUND and `questionnaire` is
# the outro.
STALL_SETTING_BY_STEP = {
    'entry': 'DASHBOARD_STALL_SECONDS_BEFORE',
    'instructions': 'DASHBOARD_STALL_SECONDS_INTRO',
    'quiz': 'DASHBOARD_STALL_SECONDS_INTRO',
    'task': 'DASHBOARD_STALL_SECONDS_TASK',
    'questionnaire': 'DASHBOARD_STALL_SECONDS_OUTRO',
}
# Used only when settings.py defines neither the phase's own name nor the
# fallback — i.e. deleting every DASHBOARD_STALL_* line still works.
FALLBACK_STALL_SECONDS = {
    'entry': 60,
    'instructions': 480,
    'quiz': 480,
    'task': 180,
    'questionnaire': 300,
}

URL_BASE = '/experimenter_dashboard'

# =============================================================================
# THE SIX TIMELINE STEPS — DEFINED HERE, ONCE, AND NOWHERE ELSE
# =============================================================================
# In order, EQUAL SPACING (the CSS grid gives each the same track). Consent, the
# ID page and the AI-safety agreement all fold into ENTRY; the outro's
# ending/demographics/feedback pages are QUESTIONNAIRE.
#
# One concept, one definition (single-sourced 2026-08-12). It used to be stated
# SIX times — a STEPS tuple, a STEP_LABELS dict nothing rendered, the six
# <span>s in the table header, the STEPS array in the page's JavaScript, and two
# copies of the step COUNT in the CSS (the grid's track count and the
# connector's half-track inset) — which is the inverted collapsed-distinction
# rule in CLAUDE.md: one concept with several implementations, which drift, and
# the drift stays invisible until something changes. Renaming a step used to
# mean finding six places, and missing one gave a header that disagreed with the
# data, with nothing going red.
#
# EVERYTHING ELSE NOW DERIVES FROM THIS ORDERED MAPPING:
#   * STEPS               — the order, for the marker's position
#   * _COLGROUP_HTML      — the header cells (_step_header_html, below)
#   * the CSS grid        — one track per step, __STEP_COUNT__
#   * the connector inset — half a track, __TL_INSET__
#   * the page's JS STEPS — injected as JSON, never retyped
# Add, rename or reorder a step HERE and all five follow.
# `scripts/tests/dashboard_test.py` §D6 asserts they still agree — including that no
# placeholder survived unreplaced into the served page, which would be invalid
# CSS and would collapse the timeline with nothing in any log. A future edit that
# reintroduces a second copy fails there rather than drifting quietly.
#
# Dicts preserve insertion order (Python 3.7+), and that order IS the timeline
# order — do not sort it anywhere.
STEP_LABELS = {
    'entry': 'Entry',
    'instructions': 'Instructions',
    'quiz': 'Quiz',
    'task': 'Task',
    'questionnaire': 'Questionnaire',
    'done': 'Done',
}
STEPS = tuple(STEP_LABELS)

# =============================================================================
# THE APP → STEP MAP. **A STUDY THAT ADDS AN APP MUST ADD IT HERE.**
# =============================================================================
# This template exists to be COPIED, and adding an app is the likeliest thing a
# study does to it — so this map is the one place that decides where a new app's
# pages sit on the timeline. Adding an app to an EXISTING step is this one line.
# Adding a whole new STEP is one line too, in STEP_LABELS above: the header, the
# grid and the client-side step order all derive from it.
APP_STEPS = {
    'before': 'entry',           # startpage, consent, ID capture, AI-safety
    'intro': 'instructions',     # split by page below (instructions vs quiz)
    'main': 'task',
    'outro': 'questionnaire',
}

# Which step a page of `intro` belongs to. AN UNRECOGNISED PAGE HERE IS NOT THE
# SAME SITUATION AS AN UNRECOGNISED APP, and the two must not be merged: a page
# in `intro` is KNOWN to be inside the instructions/quiz block, just not which
# half of it, so it degrades to the first half. An unrecognised APP is not known
# to be anywhere at all, and degrading that to a step would be a guess (see
# UNMAPPED_STEP). Residual worth knowing: a study that adds a page to `intro`
# AFTER the quiz and does not list it here gets a marker that reads
# Instructions, i.e. one that appears to move BACKWARDS.
INTRO_PAGE_STEPS = {'instructing': 'instructions', 'quiz': 'quiz'}

# THE UNRECOGNISED-APP SENTINEL — deliberately NOT one of STEPS.
#
# Until 2026-08-12 an app this module had never heard of fell through the same
# `return 'entry'` as the `before` app, and the two were indistinguishable. They
# are not the same situation: `before` IS the entry block and Entry is the right
# answer, while an unknown app is not known to be anywhere — so reporting Entry
# is a claim, and a wrong one. Collapsed, the first study to copy this template
# and add an app got EVERY participant in that app rendered at Entry, looking
# like they had barely started, with nothing on screen to say otherwise and no
# test to catch it. Kept apart, such a row now shows no marker at all and says
# loudly which app it could not place, which is what sends somebody to
# APP_STEPS above. DO NOT "simplify" this back into a step.
UNMAPPED_STEP = 'unmapped'

# What the TIMING PILL calls the phase (Julian, 2026-08-13: the warning names
# the SECTION it applies to). Short, because it shares a pill with a time.
# `instructions` and `quiz` are one phase here exactly as they share one
# threshold in STALL_SETTING_BY_STEP; `task` says "round" because its
# threshold and its elapsed are PER ROUND, not per task block (_stall_elapsed).
STALL_SECTION_LABELS = {
    'entry': 'Entry',
    'instructions': 'Intro',
    'quiz': 'Intro',
    'task': 'Task round',
    'questionnaire': 'Questionnaire',
    UNMAPPED_STEP: 'Unplaced app',
}

# Terminal states OVERRIDE the timeline marker: the emoji + colour fill the
# marker wherever it had reached, and the row's state cell names the state.
# One emoji each, chosen to read across a room and to not look like each
# other: 📵 device screened out, ✋ declined consent, ❌ failed comprehension,
# 👀 tab-monitor disqualified.
TERMINAL_STATES = {
    'screened_out': dict(emoji='📵', label='Screened out'),
    'no_consent': dict(emoji='✋', label='Declined consent'),
    'comprehension': dict(emoji='❌', label='Comprehension DQ'),
    'tab_monitor': dict(emoji='👀', label='Tab monitor DQ'),
}

# Exit codes as shipped, used only if settings cannot be read (identity.py's
# `_finished` uses the same fallback idiom).
_FALLBACK_EXIT_CODES = dict(
    finished=1, abandoned=0, no_consent=-1, comprehension=-2,
    tab_monitor=-3, screened_out=-4,
)


def _setting(name, default):
    """A value from settings.py if it defines one, else `default`. Read at
    request time, so Julian can tune DASHBOARD_* between sessions with only a
    server restart, and a missing setting is never an error."""
    try:
        import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def stall_seconds_for(step) -> int:
    """The amber threshold for ONE timeline step, in seconds.

    Precedence: the step's own settings.py name, then
    DASHBOARD_STALL_SECONDS_DEFAULT, then this module's own fallback for that
    step. Never raises and never returns less than 1 — a zero or negative
    threshold would paint every row amber the instant it loaded, which is the
    same as having no signal at all.
    """
    fallback = FALLBACK_STALL_SECONDS.get(step, DEFAULT_STALL_SECONDS)
    try:
        default = _setting('DASHBOARD_STALL_SECONDS_DEFAULT', fallback)
        name = STALL_SETTING_BY_STEP.get(step)
        value = _setting(name, default) if name else default
        return max(1, int(value))
    except Exception:
        return fallback


def stall_seconds_map() -> dict:
    """Every step's threshold, resolved once per snapshot and shipped in the
    JSON so the operator screen and the tests can both see what is in force."""
    return {step: stall_seconds_for(step)
            for step in list(STEPS) + [UNMAPPED_STEP]}


# The PHASES as an operator thinks of them, for the header's threshold legend.
# NOT the same list as STEPS: `instructions` and `quiz` are two steps sharing
# ONE threshold (the intro app), and `done` has no threshold because a finished
# row cannot stall. Kept next to STALL_SETTING_BY_STEP, since that is the map it
# has to stay true to — a step added there needs a line here or it silently
# vanishes from the legend.
STALL_LEGEND_PHASES = (
    ('Entry', 'entry'),
    ('Intro (instructions + quiz)', 'instructions'),
    ('Task (one round)', 'task'),
    ('Questionnaire', 'questionnaire'),
)


def stall_legend() -> list:
    """The four phase thresholds as (label, seconds), for the STATE column's
    header affordance — "so we can see what the thresholds are" (Julian,
    2026-08-13, round-2 item 17) WITHOUT opening settings.py.

    Read from the settings at request time like every other threshold here, so
    tuning one updates what the operator sees on the next poll. Nothing about
    these numbers is written into the page's markup.
    """
    return [dict(label=label, seconds=stall_seconds_for(step))
            for label, step in STALL_LEGEND_PHASES]


def poll_seconds() -> float:
    """Poll interval with the 2s FLOOR enforced here, server-side, so no
    settings value can make the clients hammer the global lock."""
    try:
        return max(POLL_FLOOR_SECONDS,
                   float(_setting('DASHBOARD_POLL_SECONDS',
                                  DEFAULT_POLL_SECONDS)))
    except Exception:
        return float(DEFAULT_POLL_SECONDS)


def _exit_codes() -> dict:
    try:
        from settings import EXIT_CODES
        return dict(_FALLBACK_EXIT_CODES, **EXIT_CODES)
    except Exception:
        return dict(_FALLBACK_EXIT_CODES)


# =============================================================================
# DATA LAYER — pure reads, one dict per participant
# =============================================================================

# =============================================================================
# ROW ORDER — BY THE DISPLAYED NAME, NATURALLY SORTED, UNLABELLED LAST
# =============================================================================
# (Julian, 2026-08-13.) Rows used to come out in participant-row id order, which
# in a lab is roughly ARRIVAL order — so the screen and the room disagreed, and
# an operator looking for Seat 07 had to read every row. Sorted by label, the
# table reads down the room.
#
# NOT A PLAIN STRING SORT, and the difference bites in exactly the setting this
# feature exists for: a study labelling seats `a2` … `a10` would get a10 before
# a2 alphabetically. `Seat 01` happens to sort correctly because it is
# zero-padded, but the study does the padding and this module cannot assume it.
# So each label is split into digit and non-digit runs and the digit runs are
# compared AS NUMBERS.
#
# NB THE "DO NOT SORT IT ANYWHERE" NOTE ON STEP_LABELS IS ABOUT A DIFFERENT
# LIST and is untouched by this: that one says the STEP dict's insertion order
# IS the timeline order (Entry → … → Done), so sorting it would scramble the
# timeline. It says nothing about participant rows. Checked before writing this.
_NATURAL_RUN_RE = re.compile(r'\d+|\D+')


def natural_label_key(label):
    """Sort key for a participant label: digits compare as NUMBERS.

    Each run is a 3-tuple whose FIRST element is a type tag, so a numeric run
    and a text run never compare an int against a str (which would raise, on an
    operator screen, for a mixed label set). Text compares case-insensitively —
    `seat 2` and `Seat 2` are the same seat to the person holding the list.
    """
    key = []
    for run in _NATURAL_RUN_RE.findall(str(label or '')):
        if run.isdigit():
            key.append((0, int(run), ''))
        else:
            key.append((1, 0, run.casefold()))
    return key


def displayed_name(row) -> str:
    """THE STRING THE PARTICIPANT COLUMN ACTUALLY RENDERS, which is what the
    table is sorted by (Julian, 2026-08-13).

    It is the seat label in the lab and the platform id online; when neither
    exists — a bare-link entry before any id page — the column falls back to the
    participant CODE, and so does this. Sorting by anything else (the row id,
    the participant id) would order the screen by a value the operator cannot
    see, which is how it read as arrival-ordered before. `renderRow` must keep
    making the same choice: if the fallback there changes, change it here.
    """
    return str(row.get('label') or row.get('code') or '')


# THE ONE LINE TO FLIP — where rows with NO LABEL AT ALL go.
#
#   True  (chosen): they sort LAST, after every labelled row. An operator wants
#         the people in the room at the top; an unlabelled row is usually one
#         nobody has arrived at yet, and its displayed CODE is a random string
#         that would scatter such rows through the seat numbers.
#   False: strictly interleaved by displayed name, so the table is in exactly
#         the order the Participant column reads, with no special case.
#
# THIS IS A DEVIATION FROM "SORT BY THE DISPLAYED STRING", flagged as such: it
# is the one place the order is not purely what the column shows. Setting this
# to False is the whole change — the sort below needs no other edit.
UNLABELLED_LAST = True


def sort_rows_by_displayed_name(rows) -> None:
    """Order the table by the name the Participant column shows.

    Sorted IN PLACE and STABLY, on a list already in participant-id order, so
    id order survives as the tiebreak among rows whose displayed names tie.
    """
    rows.sort(key=lambda r: (
        1 if (UNLABELLED_LAST and not r.get('label')) else 0,
        natural_label_key(displayed_name(r)),
    ))


def session_snapshot(session) -> dict:
    """Everything the dashboard shows for one session, as JSON-able data.

    Each row is built inside its own try/except: one participant whose vars
    blob is poisoned renders as an error row while every other row stays live
    (the instrumentation rule, applied at row granularity).
    """
    now = time.time()
    ctx = _session_context(session)
    rows = []
    for pp in session.pp_set.order_by('id'):
        try:
            rows.append(_participant_row(pp, ctx, now))
        except Exception:
            logger.exception(
                '[dashboard] row build failed for participant '
                f'{getattr(pp, "code", "?")}')
            rows.append(dict(
                error=True,
                code=str(getattr(pp, 'code', '?')),
                label=str(getattr(pp, 'label', '') or ''),
            ))
    # The query above is ordered by id, which is arrival order; the table is
    # ordered by LABEL, so it reads down the room. Sorted here rather than in
    # SQL because a natural sort is not something the database can be asked for
    # portably — and because ordering by a value the DATABASE's collation
    # decides is the trap CLAUDE.md's inverted rule warns about (it behaved one
    # way on sqlite and another on postgres for the label lookup, once already).
    # One implementation, in Python, for every deployment.
    sort_rows_by_displayed_name(rows)
    return dict(
        ok=True,
        session=dict(
            code=session.code,
            config_name=str(session.config.get('name', '')),
            display_name=str(session.config.get('display_name', '')
                             or session.config.get('name', '')),
            num_participants=len(rows),
        ),
        rows=rows,
        rounds_total=ctx['rounds_total'],
        quiz_max_failures=ctx['quiz_max_failures'],
        # PER-PHASE now (round-2 item 6). Shipped as the whole map rather than
        # one number so the screen can say which threshold a row tripped.
        stall_seconds=ctx['stall_seconds'],
        # The same thresholds as a labelled, deduplicated list for the header
        # affordance (item 17). Derived from the map above, never typed.
        stall_legend=stall_legend(),
        poll_seconds=poll_seconds(),
        currency=str(_setting('REAL_WORLD_CURRENCY_CODE', '')),
        now=int(now),
    )


def _session_context(session) -> dict:
    """Session-constant values, computed once per snapshot, defensively."""
    import common
    try:
        # THIS session's round count (a config may run fewer than NUM_ROUNDS);
        # same source as the participant-facing progress strip (main.rounds_for
        # duplicates this min() but importing an app module here would be a
        # heavier dependency than the two lines).
        configured = int(common.cfg(session.config, 'num_experimental_rounds'))
        try:
            from otree.common import get_models_module
            imported_max = int(get_models_module('main').C.NUM_ROUNDS)
            rounds_total = min(configured, imported_max)
        except Exception:
            rounds_total = configured
    except Exception:
        rounds_total = None
    try:
        quiz_max = int(common.cfg(session.config, 'comprehension_max_failures'))
    except Exception:
        quiz_max = None
    # Module flags read raw (.get — common.flag's rule); thresholds through
    # the safe accessor, defensively.
    try:
        tab_monitor_max = int(common.cfg(session.config,
                                         'tab_monitor_max_violations'))
    except Exception:
        tab_monitor_max = None
    return dict(
        rounds_total=rounds_total,
        quiz_max_failures=quiz_max,
        stall_seconds=stall_seconds_map(),
        exit_codes=_exit_codes(),
        earnings=_earnings_map(session),
        quiz_outcomes=_quiz_outcome_map(session),
        non_sepa=_non_sepa_ids(session),
        completion_redirects=bool(
            session.config.get('prolific_completion_redirects')),
        tab_monitor_on=bool(session.config.get('tab_monitor')),
        tab_monitor_max=tab_monitor_max,
        return_grace=max(0, int(_setting('DASHBOARD_RETURN_GRACE_SECONDS',
                                         90))),
    )


def _earnings_map(session) -> dict:
    """participant_id -> final earnings (the outro's `earned`, which is the
    real total: show-up fee + selected rounds + quiz bonus), for everyone
    whose Results page has computed it. Defensive: no earnings, no cell —
    never a dead dashboard because a study renamed the outro."""
    out = {}
    try:
        from otree.common import get_models_module
        from otree.database import db
        Player = get_models_module('outro').Player
        for row in db.query(Player).filter(Player.session_id == session.id):
            earned = row.field_maybe_none('earned')
            if earned is not None:
                out[row.participant_id] = float(earned)
    except Exception:
        logger.exception('[dashboard] earnings read failed')
    return out


def _quiz_outcome_map(session) -> dict:
    """participant_id -> how their LAST graded quiz submission went.

    Values: True (the last graded attempt had nothing wrong — a real pass),
    False (the last graded attempt was wrong — they left the quiz WITHOUT
    passing), or absent (nothing graded at all).

    WHY THIS EXISTS — the collapsed distinction found answering Julian's
    question B (2026-08-13; see _ai/change_requests_round2.md — local only,
    _ai/ is gitignored — for the measured
    trace). `quiz_done` is stamped on ANY exit from the quiz page, so these two
    reached the same predicate and became indistinguishable:

      * a participant who answered correctly and moved on;
      * a participant an EXPERIMENTER pushed through with the admin panel's
        "advance slowest participants", who never answered at all.

    The second is not hypothetical: oTree's advance path
    (otree/models/participant.py `_submit_current_page`) posts an EMPTY form
    flagged as a timeout with the admin secret, oTree calls `error_message`
    anyway (otree/views/abstract.py, the `_process_auto_submitted_form`
    branch), our grading marks every item wrong and increments
    `failed_attempts` — and then the page ADVANCES regardless, because a
    timeout submission discards the error. Result: `quiz_done` stamped,
    `failed_attempts` 1, answers stored as empty strings. The dashboard used to
    paint that a green "passed on attempt 2", for every participant in the
    session at once, which is exactly what Julian saw.

    `quiz_attempt_log` already records what is needed and is the only thing that
    does: every graded submission with the items that were wrong at the time
    (intro.log_quiz_attempt). The LAST entry across rounds decides — round 2 is
    the lab re-read pass, so a participant who failed round 1 and passed round 2
    must read as a pass.

    Defensive throughout, like _earnings_map: an intro app that has been
    renamed, a log that will not parse, or a study that dropped the column all
    degrade to "no opinion" (absent), which renders exactly as the cell did
    before this existed.
    """
    out = {}
    try:
        from otree.common import get_models_module
        from otree.database import db
        Player = get_models_module('intro').Player
        rows = db.query(Player).filter(Player.session_id == session.id)
        # participant_id -> (round_number, passed) for the highest round that
        # actually recorded an attempt.
        best = {}
        for row in rows:
            try:
                raw = row.field_maybe_none('quiz_attempt_log') or ''
                entries = json.loads(raw) if raw else []
                if not isinstance(entries, list) or not entries:
                    continue
                last = entries[-1]
                passed = not (last.get('wrong') or [])
                rnd = int(row.round_number or 0)
                if rnd >= best.get(row.participant_id, (-1, None))[0]:
                    best[row.participant_id] = (rnd, bool(passed))
            except Exception:
                continue  # one unreadable log must not blank the whole column
        out = {pid: passed for pid, (_rnd, passed) in best.items()}
    except Exception:
        logger.exception('[dashboard] quiz outcome read failed')
    return out


def _non_sepa_ids(session) -> set:
    """participant_ids whose SEPA check came back NEGATIVE — the Non-SEPA
    CONDITION pill's data. **LAB SESSIONS ONLY** (Julian, 2026-08-13).

    The pill exists because a non-SEPA transfer may not work at all, which the
    operator wants to know BEFORE the participant leaves the room — including
    on a finished row, which is why it is a condition, not an outcome.

    Three deliberate narrowings, each Julian's call, none to be widened:
      * `sepa == 0` ONLY. `sepa` is nullable and NULL means the check NEVER
        RAN (every Prolific participant, and any config with
        collect_bank_details off — see CODEBOOK.md's three-state note). Null
        must read as NO PILL: absence of a check is not a payment problem.
      * NO pill for a non-Dutch but in-SEPA account (`sepa == 1`). There is no
        yellow payment state — the bank form's BIC rule already handled the
        non-Dutch case (outro.Demographics.error_message), and that rule is a
        DIFFERENT question from this one; do not collapse the two predicates.
      * Lab sessions only. Prolific participants are never asked for bank
        details, so even a hand-edited `sepa=0` row in a Prolific session gets
        no pill — payment there goes through the platform, and the pill would
        send an operator chasing a form that does not exist.

    Defensive like _earnings_map: any failure degrades to "no pills", never a
    dead dashboard."""
    out = set()
    try:
        import common
        if not common.is_lab(session.config):
            return out
        from otree.common import get_models_module
        from otree.database import db
        Player = get_models_module('outro').Player
        for row in db.query(Player).filter(Player.session_id == session.id):
            if row.field_maybe_none('sepa') == 0:
                out.add(row.participant_id)
    except Exception:
        logger.exception('[dashboard] sepa read failed')
    return out


def _participant_row(pp, ctx, now) -> dict:
    """ONE ROW of the dashboard, as a plain dict. THE extension point:
    everything returned here reaches the /data JSON verbatim.

    Reads participant vars via ``pp._vars``, NOT the ``pp.vars`` property —
    and that is rule 1, not style. The property is a WRITE in disguise:
    ``MixinVars.vars`` calls ``self._vars.changed()`` on every READ (verified
    against oTree 6.0.15, otree/database.py), flagging the pickled column
    dirty so the commit middleware would rewrite every participant row on
    every poll. Same bytes back, but thousands of pointless UPDATEs per
    session — and "writes nothing, ever" means nothing. The app-code rule
    ("always participant.vars.get()", CLAUDE.md) is about the KeyError
    descriptor trap and does not apply here: ``_vars`` is the same dict,
    minus the dirty flag. Field access like ``pp.vars.get(...)`` is still
    what everything OUTSIDE this module must use.
    """
    import common   # local, like every common/settings import in this
    # module — the dashboard must stay importable with oTree absent
    # (the _FALLBACK_EXIT_CODES reasoning); the stage-name constants
    # (common.STAGE_*) are only needed at request time.
    v = pp._vars or {}
    stamps = dict(v.get('stage_timestamps') or {})
    codes = ctx['exit_codes']
    exit_code = v.get('exit_code')

    # --- terminal state: checked FIRST, it overrides everything -------------
    # (A disqualified participant walks on to the Ended page, so their page
    # position alone would read as "questionnaire" — one situation, two
    # meanings. The flags are the authoritative record; position is not.)
    terminal = None
    if v.get('screened_out'):
        terminal = 'screened_out'
    elif v.get('ai_safety_disqualified'):
        terminal = 'tab_monitor'
    elif v.get('comprehension_disqualified'):
        terminal = 'comprehension'
    elif exit_code == codes['no_consent']:
        terminal = 'no_consent'

    # --- finished ------------------------------------------------------------
    # Only meaningful with no terminal state: a disqualified participant also
    # runs past the last page index once the ending is behind them, and that
    # must not read as DONE (the same collapsed-distinction as identity's
    # finished-vs-terminal).
    finished = False
    if terminal is None:
        idx, last = pp._index_in_pages, pp._max_page_index
        finished = (
            exit_code == codes['finished']
            or common.STAGE_FINISHED in stamps
            or (isinstance(idx, int) and isinstance(last, int)
                and pp.visited and idx > last)
        )

    # --- the timeline step the marker occupies -------------------------------
    if terminal is not None:
        step = _reached_step(terminal, stamps)
    elif finished:
        step = 'done'
    else:
        step = _position_step(pp)

    # --- task progress, carried inside the marker during TASK ----------------
    task_round = None
    if step == 'task' and terminal is None:
        r = pp._round_number
        task_round = int(r) if isinstance(r, int) and r >= 1 else 1
        if ctx['rounds_total']:
            task_round = min(task_round, ctx['rounds_total'])

    # --- quiz cell ------------------------------------------------------------
    quiz = _quiz_cell(v, stamps, step, terminal, ctx['quiz_max_failures'],
                      ctx['quiz_outcomes'].get(pp.id))

    # --- INTRO TIME: the whole intro app, both rounds -------------------------
    intro = _intro_seconds(stamps, step, terminal, finished, now)

    # --- amber: too long IN THIS PHASE, against the phase's threshold --------
    # _last_page_timestamp is stamped by oTree when the participant lands on a
    # page, so (now - it) is time on the CURRENT page. Only an ACTIVE row can
    # stall: terminal and finished rows are not waiting on anything, and a
    # never-arrived row has no page to be stuck on.
    # The threshold comes from the row's own step (round-2 item 6); the ELAPSED
    # it is compared against is per phase too (the pills change, 2026-08-13) —
    # see _stall_elapsed for which phase counts a page, a round or the whole
    # block, and why.
    seconds_on_page = None
    ts = pp._last_page_timestamp
    if pp.visited and isinstance(ts, int) and ts > 0:
        seconds_on_page = max(0, int(now) - ts)
    active = pp.visited and terminal is None and not finished
    stall_limit = ctx['stall_seconds'].get(step, DEFAULT_STALL_SECONDS)
    stall_elapsed = _stall_elapsed(step, stamps, intro, seconds_on_page, now)
    stalled = bool(active and stall_elapsed is not None
                   and stall_elapsed >= stall_limit)

    # --- finished HERE but never clicked back to the platform ----------------
    # A participant who reached Results is `finished` in our data — but on
    # Prolific their submission stays open until they click "Back to Prolific",
    # and an open submission is an UNPAID one that this table otherwise renders
    # as a normal finisher. The stamp is best-effort instrumentation
    # (outro.results_live_method), so this pill is a prompt to look, never a
    # verdict.
    #
    # GATED ON prolific_completion_redirects, EXPLICITLY, AND THE GATE IS THE
    # POINT (Julian, 2026-08-13) — do not "simplify" this to
    # finished-and-not-returned: with redirects off there is NO button to have
    # clicked, so the flag would be meaningless and would fire on every lab
    # participant forever. The grace period exists because a completer reading
    # their receipt has legitimately not clicked yet (see
    # DASHBOARD_RETURN_GRACE_SECONDS in settings.py). A legacy row whose
    # `finished` was derived without a stamp never flags — no clock to judge.
    awaiting_return = False
    if finished and ctx['completion_redirects']:
        fin_ts = stamps.get(common.STAGE_FINISHED)
        awaiting_return = bool(
            isinstance(fin_ts, (int, float))
            and (now - fin_ts) >= ctx['return_grace']
            and common.STAGE_PROLIFIC_RETURN_CLICKED not in stamps)

    # --- tab-monitor violations while they CLIMB -----------------------------
    # Until now the operator saw only the disqualification, after it happened.
    # Ship the server-authoritative count (common.focus_live_method's
    # focus_loss_count) with the configured limit next to it, so somebody at 2
    # of 3 can be spoken to BEFORE ejection. Active rows only: once terminal
    # the DQ pill says it, and a finisher is past intervening — the count
    # itself stays in the export either way. None (not 0) when there is
    # nothing to show, so the client renders no pill at all.
    monitor_count = None
    if ctx['tab_monitor_on'] and terminal is None and not finished:
        try:
            c = int(v.get('focus_loss_count') or 0)
        except Exception:
            c = 0
        if c >= 1:
            monitor_count = c

    # --- entry-only: de-emphasised, and hideable by the header toggle --------
    # NOT-ARRIVED ONLY (changed 2026-08-12 on review, from "anyone whose step
    # is entry"): a participant sitting on the consent page is a PRESENT
    # person, and dimming them makes them look absent — the opposite of what
    # an operator scanning the room needs. The dim treatment means "nobody is
    # here", nothing else. Terminal rows are still never entry-only — a
    # screen-out must not be hideable by accident.
    entry_only = terminal is None and not finished and not pp.visited

    row = dict(
        # Row identity: participant.label — the seat number in the lab, the
        # Prolific ID online. code is the fallback the operator can still act
        # on when no label exists yet (bare-link entry before the ID page).
        label=str(pp.label or ''),
        code=str(pp.code),
        arrived=bool(pp.visited),
        step=step,
        task_round=task_round,
        terminal=terminal,
        terminal_emoji=TERMINAL_STATES[terminal]['emoji'] if terminal else None,
        terminal_label=TERMINAL_STATES[terminal]['label'] if terminal else None,
        finished=finished,
        quiz=quiz,
        # INTRO TIME (round-2 item 5) — renamed from instructions_*, and a
        # different measurement, not just a different label: see _intro_seconds.
        intro_seconds=intro['seconds'],
        intro_live=intro['live'],
        earnings=ctx['earnings'].get(pp.id),
        seconds_on_page=seconds_on_page,
        stalled=stalled,
        # Which threshold this row is judged against, so the state cell can name
        # it — "8:12 on page" means nothing without "…and the limit here is 3m".
        stall_limit=stall_limit,
        # THE NUMBER THE THRESHOLD ACTUALLY JUDGED, which is also the number
        # the timing pill SHOWS — one value for display and detection, so the
        # pill can never say "Intro 12:00" about a verdict reached on some
        # other quantity. stall_section is the phase name written next to it.
        stall_elapsed=stall_elapsed,
        stall_section=STALL_SECTION_LABELS.get(
            step, STEP_LABELS.get(step, str(step))),
        # Non-SEPA CONDITION pill (lab only; sepa == 0 only — see
        # _non_sepa_ids for the three deliberate narrowings). A condition, not
        # an outcome: it stays True on a finished row.
        non_sepa=bool(pp.id in ctx['non_sepa']),
        # Finished but no "Back to Prolific" click recorded (redirect sessions
        # only — see the gate comment above, which is load-bearing).
        awaiting_return=awaiting_return,
        # Tab-monitor count while climbing, with the limit it climbs towards
        # (config value, never a number in the markup).
        monitor_count=monitor_count,
        monitor_max=ctx['tab_monitor_max'],
        entry_only=entry_only,
        current_page=str(pp._current_page_name or ''),
        # The app name ONLY when it could not be placed on the timeline, so the
        # operator is told which app to add to APP_STEPS. None on every normal
        # row: this is a "something is wrong with the dashboard's map" channel,
        # not a general-purpose app column.
        unmapped_app=(str(pp._current_app_name or '')
                      if step == UNMAPPED_STEP else None),
        # ADD A COLUMN HERE: compute it defensively (a failure must blank the
        # cell, not kill the row), add the <th> in _COLGROUP_HTML and the cell
        # branch at ADD A COLUMN HERE (render) in _PAGE_HTML below.
    )
    return row


def _position_step(pp) -> str:
    """Which step a LIVE participant's marker occupies, from oTree's own page
    cursor (app + page name, updated as each page renders). The marker
    advances exactly when a step completes, because completing it is what
    moves the cursor onto the next block's first page.

    THREE OUTCOMES, KEPT APART ON PURPOSE (see UNMAPPED_STEP):
      * a page in a KNOWN app          -> that app's step (APP_STEPS)
      * no cursor written yet          -> 'entry', which is where they are
      * a page in an UNRECOGNISED app  -> UNMAPPED_STEP, a visible non-answer
    """
    if not pp.visited:
        return 'entry'
    app = pp._current_app_name or ''
    page = pp._current_page_name or ''
    if not app:
        # Arrived, but oTree has not written a cursor yet. This is genuinely
        # the start of the flow, not an unknown position — 'entry' is a fact
        # here, which is why it is NOT the unmapped case.
        return 'entry'
    if app not in APP_STEPS:
        return UNMAPPED_STEP
    if app == 'intro':
        return INTRO_PAGE_STEPS.get(page, 'instructions')
    return APP_STEPS[app]


def _reached_step(terminal, stamps) -> str:
    """Where the marker HAD REACHED when a terminal state ended the session —
    the step the emoji fills. Stamps, not page position: a disqualified
    participant's position has already moved on to the ending pages.

    Screen-out and declined consent can only happen at entry. Comprehension
    DQ can only happen on the quiz (its quiz_done stamp fires on the same
    submit that disqualifies, so the stamp alone would claim 'task').
    The tab monitor is the one that can fire anywhere, so only it is derived.
    """
    import common   # local, like every common/settings import in this
    # module — the dashboard must stay importable with oTree absent
    # (the _FALLBACK_EXIT_CODES reasoning); the stage-name constants
    # (common.STAGE_*) are only needed at request time.
    if terminal in ('screened_out', 'no_consent'):
        return 'entry'
    if terminal == 'comprehension':
        return 'quiz'
    if common.STAGE_TASK_DONE in stamps:
        return 'questionnaire'
    if common.STAGE_QUIZ_DONE in stamps:
        return 'task'
    if common.STAGE_INSTRUCTIONS_DONE in stamps:
        return 'quiz'
    if common.STAGE_CONSENT in stamps:
        return 'instructions'
    return 'entry'


def _quiz_cell(v, stamps, step, terminal, max_failures, last_attempt_passed) -> dict:
    """The quiz-attempts cell: white before any attempt, filling as wrong
    attempts rise, RED at comprehension_max_failures, GREEN with the attempt
    count once passed (so 1 = passed first try), and VIOLET-BORDERED "forced"
    when the participant left the quiz without ever answering it correctly.

    `failed_attempts` counts WRONG submissions (intro.quiz.error_message), so
    the green count is failed_attempts + 1: the wrong ones plus the one that
    passed. `quiz_done` alone is not "passed": it is stamped on ANY exit from
    the quiz page, including the lab's re-read detour and the disqualifying
    submit — so passed additionally requires having moved past the
    instructions/quiz block with no comprehension DQ.

    THE FORCED STATE (added 2026-08-13; the full trace is question B in
    _ai/change_requests_round2.md, local only). Being past the quiz was ALSO
    not "passed":
    an experimenter using the admin panel's "advance slowest participants"
    pushes a participant past it having answered nothing, and the row then
    claimed a pass — for every participant at once, since that button advances
    everyone at the same index. `last_attempt_passed` (from
    _quiz_outcome_map) is the only thing that distinguishes them: it is
    False when the LAST graded submission still had items wrong.

    It is deliberately NOT rendered as a failure. Nothing is wrong with the
    PARTICIPANT — an operator did this on purpose — so the cell says "forced",
    in the same violet the dashboard already uses for "something here is not a
    participant behaviour". `None` (nothing graded, e.g. a DEBUG clickthrough
    with verify_quiz off) leaves the old behaviour exactly as it was: no
    evidence is not evidence of a force-advance.
    """
    import common   # local, like every common/settings import in this
    # module — the dashboard must stay importable with oTree absent
    # (the _FALLBACK_EXIT_CODES reasoning); the stage-name constants
    # (common.STAGE_*) are only needed at request time.
    attempts_wrong = int(v.get('failed_attempts', 0) or 0)
    past_quiz = (
        common.STAGE_QUIZ_DONE in stamps
        and terminal != 'comprehension'
        and step not in ('entry', 'instructions', 'quiz')
    )
    forced = bool(past_quiz and last_attempt_passed is False)
    passed = past_quiz and not forced
    if forced:
        state = 'forced'
    elif passed:
        state = 'green'
    elif terminal == 'comprehension' or (
            max_failures and attempts_wrong >= max_failures):
        state = 'red'
    elif attempts_wrong > 0:
        state = 'progress'
    else:
        state = 'idle'
    fill = 0.0
    if max_failures:
        fill = min(1.0, attempts_wrong / max_failures)
    return dict(
        state=state,
        attempts_wrong=attempts_wrong,
        display=(attempts_wrong + 1) if passed else attempts_wrong,
        fill=round(fill, 3),
    )


def _intro_seconds(stamps, step, terminal, finished, now) -> dict:
    """INTRO TIME: the WHOLE time inside the `intro` app, across BOTH rounds —
    from leaving the `before` app until the quiz is finished with (Julian,
    2026-08-13, round-2 item 5). Live while the participant is still in there.

    WHAT CHANGED, AND WHY IT IS A DIFFERENT STATISTIC, NOT A RENAME. The old
    measure ran to `instructions_done` and stopped, explicitly excluding the
    re-read; so a lab participant who read the instructions, failed the quiz,
    re-read everything and passed on the second pass was reported as having
    spent only the first read. The number Julian wants is the total cost of the
    comprehension block, which is precisely the part that a failed quiz makes
    longer. Under this definition a re-read after a failed quiz KEEPS COUNTING,
    which is the point of it.

    THE START is `left_before_app`, written by every page of the `before` app
    and overwritten each time (common.stamp_left_before_app), so it is the
    moment they left the entry block whichever pages that config shows.
    The max() over the three older entry stamps is kept as a FALLBACK for
    participants who were already mid-flow when this was deployed — they have
    no `left_before_app` stamp and never will, and the alternative is a blank
    column for exactly the people an operator is watching most closely. New
    participants never reach it.

    THE END is `quiz_done`, which `stamp_stage` OVERWRITES, so its value is the
    LAST exit from the quiz page — round 2's for a re-reader, round 1's for
    everybody else. But the stamp alone cannot end the measurement: a
    re-reader has a round-1 `quiz_done` while still sitting in the
    instructions. So the clock stops only once the participant is out of the
    intro block (or terminal, or finished), and runs live until then. That is
    the one subtlety in this function; do not "simplify" it to reading the
    stamp.
    """
    import common   # local, like every common/settings import in this
    # module — the dashboard must stay importable with oTree absent
    # (the _FALLBACK_EXIT_CODES reasoning); the stage-name constants
    # (common.STAGE_*) are only needed at request time.
    start = stamps.get(common.LEFT_BEFORE_APP_STAGE)
    if not isinstance(start, (int, float)):
        start = max(
            (t for k in (common.STAGE_CONSENT, common.STAGE_CONFIRM_ID,
                         common.STAGE_AI_SAFETY_AGREED)
             for t in [stamps.get(k)] if isinstance(t, (int, float))),
            default=None,
        )
    if start is None:
        return dict(seconds=None, live=False)
    in_intro = step in ('instructions', 'quiz')
    if in_intro and terminal is None and not finished:
        return dict(seconds=max(0, int(now - start)), live=True)
    end = stamps.get(common.STAGE_QUIZ_DONE)
    if isinstance(end, (int, float)) and end >= start:
        return dict(seconds=int(end - start), live=False)
    # Out of the intro block with no quiz stamp: a screen-out or a declined
    # consent never got there, and reporting 0 would be a claim about time they
    # never spent.
    return dict(seconds=None, live=False)


def _stall_elapsed(step, stamps, intro, seconds_on_page, now):
    """The elapsed time the phase threshold is judged against — and the number
    the timing pill SHOWS, so display and detection cannot disagree (the pills
    change, 2026-08-13: the warning names the SECTION and the elapsed IN it).

    PER PHASE, matching what each threshold MEANS in settings.py — the elapsed
    and the threshold must measure the same thing, or the colour is unreadable:

      * entry — time on the CURRENT page. The 60s entry threshold is a
        per-page number: cumulative time across the entry block includes
        reading the consent text, which legitimately takes minutes, so a
        block-level 60s would flag every careful reader.
      * instructions/quiz — the WHOLE intro app so far (the live intro clock,
        _intro_seconds — one implementation, not a second stopwatch). The 480s
        threshold is documented as "instructions + quiz, whole intro app";
        judging it against one page under-fired: somebody could sit 7 minutes
        on each half and never trip a per-page check.
      * task — time on the current page, because the threshold is PER SINGLE
        ROUND ("A STUDY WITH A LONGER TASK PAGE MUST RAISE THIS",
        settings.py) and a round has no start stamp; its decision page is
        where the time goes, so page time is the round to within a click.
      * questionnaire — since `task_done`, the block's start stamp. The 300s
        threshold is written for the whole outro (demographics + bank form).

    Falls back to page time wherever a stamp is missing (a participant already
    mid-flow when the stamp was deployed), which is the pre-pills behaviour.
    """
    import common   # local, like every common/settings import in this
    # module — the dashboard must stay importable with oTree absent
    # (the _FALLBACK_EXIT_CODES reasoning); the stage-name constants
    # (common.STAGE_*) are only needed at request time.
    if step in ('instructions', 'quiz'):
        if intro['live'] and intro['seconds'] is not None:
            return intro['seconds']
        return seconds_on_page
    if step == 'questionnaire':
        t = stamps.get(common.STAGE_TASK_DONE)
        if isinstance(t, (int, float)):
            return max(0, int(now - t))
        return seconds_on_page
    return seconds_on_page


# =============================================================================
# INSTALL — the identity.py discipline (see the module docstring for the one
# deliberate difference: the call site survives even the drift raise)
# =============================================================================

INSTALLED = 'installed'            # newly appended
ALREADY = 'already'                # idempotent no-op
NOT_IMPORTABLE = 'not_importable'  # otree.urls not importable / mid-import

# Route names, used for idempotency and by tests. Starlette exposes them for
# url_for, so they must not collide with oTree's own view names.
ROUTE_NAMES = ('ExperimenterDashboardIndex', 'ExperimenterDashboard',
               'ExperimenterDashboardData')

_install_log = []


def _import_urls():
    """Import oTree's routing module. Separated so the IMPORT failure and the
    SYMBOL checks can be told apart (identity._import_views is the model).

    THE MID-IMPORT CASE IS 'NOT IMPORTABLE': if something imports the app
    modules from INSIDE otree.urls' own get_urlpatterns() (no supported boot
    path does — setup()'s init_orm imports the apps first — but a bare
    `uvicorn otree.asgi:app` would), this module is in sys.modules WITHOUT its
    `routes` attribute yet. That is an ordering fact, not drift: fail quiet.
    """
    from otree import urls
    if not hasattr(urls, 'routes'):
        raise ImportError('otree.urls is mid-import (no routes attribute yet)')
    return urls


def install_dashboard_route():
    """Append the dashboard routes to otree.urls.routes (and to the live app
    router, if otree.asgi has somehow already built the app — Starlette's
    Router matches against that list per request, so a late append still
    serves). Returns INSTALLED / ALREADY / NOT_IMPORTABLE.

    RAISES only on VERSION DRIFT: otree.urls loaded but `routes` is not the
    list this file was written against, or AdminView no longer carries the
    login machinery the endpoints reuse. A caller at boot must catch that
    raise and log it — the dashboard must break, never the boot (module
    docstring).
    """
    try:
        urls = _import_urls()
    except Exception as exc:
        _install_log.append((NOT_IMPORTABLE, f'{type(exc).__name__}: {exc}'))
        return NOT_IMPORTABLE

    routes = getattr(urls, 'routes', None)
    if not isinstance(routes, list):
        raise RuntimeError(
            'experimenter_dashboard.install_dashboard_route: otree.urls.routes '
            f'is {type(routes).__name__}, not the plain module-level list that '
            'otree.asgi passes to Starlette (verified against oTree 6.0.15). '
            'The installed oTree has drifted: find where the route table is '
            'built now and re-point this install at it.')

    if any(getattr(r, 'name', None) in ROUTE_NAMES for r in routes):
        _install_log.append((ALREADY, ''))
        return ALREADY

    # SHAPE CHECK on the auth machinery the endpoints reuse. If AdminView no
    # longer has the login-cookie check, "reuse oTree's login" is silently
    # reusing nothing — an unauthenticated dashboard, which is exactly the
    # loud-drift case.
    from otree.views import cbv
    AdminView = getattr(cbv, 'AdminView', None)
    if AdminView is None or not callable(
            getattr(AdminView, '_is_logged_in', None)) or not callable(
            getattr(AdminView, 'inner_dispatch', None)):
        raise RuntimeError(
            'experimenter_dashboard.install_dashboard_route: '
            'otree.views.cbv.AdminView no longer provides _is_logged_in / '
            'inner_dispatch, which are the login machinery these endpoints '
            'reuse. The installed oTree has drifted; the dashboard has NOT '
            'been installed, because installing it without a login check '
            'would expose it to participants. Re-check the admin auth flow '
            'against the installed oTree and update experimenter_dashboard.py.')

    new_routes = _build_routes(AdminView)
    routes.extend(new_routes)

    # If the Starlette app was ALREADY built, otree.asgi copied the list
    # before our append (Starlette's Router does list(routes)) — so append to
    # the live router's own list too. Router.__call__ iterates it per
    # request, so this works after construction.
    import sys
    asgi = sys.modules.get('otree.asgi')
    if asgi is not None:
        try:
            live = asgi.app.router.routes
            if not any(getattr(r, 'name', None) in ROUTE_NAMES for r in live):
                live.extend(new_routes)
        except Exception as exc:
            raise RuntimeError(
                'experimenter_dashboard.install_dashboard_route: otree.asgi '
                'is already imported but its app.router.routes could not be '
                f'extended ({type(exc).__name__}: {exc}). The dashboard '
                'would silently 404. Starlette/oTree has drifted; re-check '
                'otree/asgi.py against this install.') from exc

    _install_log.append((INSTALLED, ''))
    return INSTALLED


def dashboard_is_installed() -> bool:
    """Are the routes actually in the table right now? Never raises."""
    try:
        urls = _import_urls()
    except Exception:
        return False
    routes = getattr(urls, 'routes', None)
    if not isinstance(routes, list):
        return False
    return any(getattr(r, 'name', None) in ROUTE_NAMES for r in routes)


def install_dashboard_route_or_note():
    """THE BOOT-TIME CALL SITE WRAPPER (used at the end of outro/__init__.py).

    Installs, and NEVER raises — not even on drift. identity's assert point
    rightly fails the boot, because what it guards is a participant 500; a
    dashboard that cannot install harms nobody but the operator, and failing
    every participant's boot over an operator page would invert the module's
    own first rule. Drift is still LOUD: logged at error level and printed,
    with the reason, so the operator who finds the 404 finds this next.
    """
    try:
        outcome = install_dashboard_route()
        if outcome == NOT_IMPORTABLE:
            message = (
                '[dashboard] EXPERIMENTER DASHBOARD NOT INSTALLED: otree.urls '
                'was not importable at the app-import install point, which no '
                'supported boot path should reach. Participants are '
                f'unaffected; {URL_BASE} will 404. '
                f'Attempts: {_install_log!r}')
            logger.error(message)
            print(message, flush=True)
        return outcome
    except Exception as exc:
        message = (
            '[dashboard] EXPERIMENTER DASHBOARD NOT INSTALLED (version '
            f'drift): {exc}\nParticipants are unaffected; {URL_BASE} will '
            '404 until experimenter_dashboard.py is updated for the '
            'installed oTree.')
        logger.error(message)
        print(message, flush=True)
        return 'drift'


def note_admin_tab_problems():
    """THE ADMIN-TAB SHAPE CHECK (the identity.py discipline, applied to the
    dashboard's admin "Report" tab; called from the end of outro/__init__.py
    right after the route install).

    The tab rides oTree's SUPPORTED admin-report extension point: at session
    creation, Session._set_admin_report_app_names scans each app for
    <app>/admin_report.html and Session.html renders a Report tab when one is
    found. That is data-driven — nothing is patched — which also means the
    failure mode is SILENT: if oTree renames the lookup or drops the feature,
    the tab just stops appearing and nobody notices. This check makes that
    drift LOUD (logged and printed, never raised — the tab is an operator
    convenience, and the standalone URL keeps working regardless), while
    staying QUIET when oTree is legitimately not importable yet.

    DELIBERATELY NO bare `except Exception` around the whole thing: the
    import failure (quiet), the missing symbols (loud drift) and the
    invisible template (loud) are three different situations and are handled
    apart — collapsing them is how a missing tab becomes something nobody can
    see (CLAUDE.md, the guard example).
    """
    try:
        from otree.models.session import Session
        from otree.templating import get_template_name_if_exists
        from otree.templating.errors import TemplateLoadError
    except ImportError as exc:
        # Legitimately not available (a bare import of this module outside
        # oTree). Not drift — note it and move on.
        logger.info('[dashboard] admin-tab check skipped: %s', exc)
        return 'not_importable'

    if not callable(getattr(Session, 'has_admin_report', None)) or not callable(
            getattr(Session, '_set_admin_report_app_names', None)):
        message = (
            '[dashboard] ADMIN TAB WILL NOT APPEAR (version drift): '
            'otree.models.session.Session no longer carries has_admin_report/'
            '_set_admin_report_app_names, the admin-report machinery the '
            'Report tab rides (verified against oTree 6.0.15). The dashboard '
            f'itself is unaffected and stays at {URL_BASE}/<session_code>; '
            'update outro/admin_report.html and this check for the installed '
            'oTree.')
        logger.error(message)
        print(message, flush=True)
        return 'drift'

    try:
        get_template_name_if_exists(['outro/admin_report.html',
                                     'outro/AdminReport.html'])
    except TemplateLoadError:
        message = (
            '[dashboard] ADMIN TAB WILL NOT APPEAR: oTree\'s template lookup '
            'cannot see outro/admin_report.html, so sessions created now get '
            'no Report tab. Either the file moved or the lookup convention '
            'drifted. The dashboard itself is unaffected and stays at '
            f'{URL_BASE}/<session_code>.')
        logger.error(message)
        print(message, flush=True)
        return 'template_invisible'

    return 'ok'


def assert_dashboard_route():
    """THE SINGLE PLACE A MISSING DASHBOARD IS A FAILURE — for TESTS, which
    boot oTree and must fail loudly if the install silently regressed.
    Deliberately NOT called at boot; see install_dashboard_route_or_note."""
    outcome = install_dashboard_route()
    if not dashboard_is_installed():
        raise RuntimeError(
            f'experimenter_dashboard.assert_dashboard_route: install reports '
            f'{outcome!r} but the routes are not in otree.urls.routes. '
            f'Attempts: {_install_log!r}')
    return outcome


# =============================================================================
# ENDPOINTS — built lazily, only when the install has oTree in hand
# =============================================================================

def _requires_login_now() -> bool:
    """The same AUTH_LEVEL mapping url_patterns_from_builtin_module applies to
    oTree's own views — except DEMO also requires login here (docstring)."""
    from otree import settings as otree_settings
    return {'STUDY': True, 'DEMO': True, '': False, None: False}[
        otree_settings.AUTH_LEVEL]


def _build_routes(AdminView):
    """The three Route objects. Endpoint classes are defined HERE, not at
    module scope, so importing this module can never drag oTree in (rule 2:
    nothing at module scope may be able to fail and take the app down)."""
    from starlette.responses import HTMLResponse, JSONResponse, Response
    from starlette.routing import Route

    requires_login = _requires_login_now()

    class _DashboardBase(AdminView):
        _requires_login = requires_login

        def inner_dispatch(self, request):
            # AUTH FIRST, FAIL CLOSED: if the check itself breaks, deny.
            try:
                if self._is_unauthorized():
                    return self.redirect('Login')
            except Exception:
                logger.exception('[dashboard] auth check failed — denying')
                return Response(status_code=403, content='Forbidden')
            # READ-ONLY: GET is the only verb. (AdminView's POST/CSRF
            # machinery is deliberately never reached.)
            if request.method.lower() != 'get':
                return Response(status_code=405, content='read-only',
                                headers={'Allow': 'GET'})
            # FAIL SOFT: any handler bug renders the error panel, HTTP 200,
            # so nothing propagates into oTree's error machinery and the
            # commit middleware has nothing to roll back.
            try:
                return self.dashboard_get(request, **request.path_params)
            except Exception as exc:
                logger.exception('[dashboard] handler failed')
                return self.error_response(exc)

        def error_response(self, exc):
            return HTMLResponse(_error_panel_html(exc), status_code=200)

    class ExperimenterDashboardIndex(_DashboardBase):
        url_pattern = URL_BASE

        def dashboard_get(self, request):
            from otree.database import db
            from otree.models import Session
            items = []
            for s in db.query(Session).order_by(Session.id.desc()):
                items.append(
                    f'<li><a href="{URL_BASE}/{escape(s.code)}">'
                    f'<strong>{escape(s.code)}</strong></a>'
                    f' — {escape(str(s.config.get("name", "")))}'
                    f' ({s.num_participants} participants)</li>')
            body = ('<ul class="dash-sessions">' + ''.join(items) + '</ul>'
                    if items else '<p>No sessions yet.</p>')
            return HTMLResponse(_index_html(body))

    class ExperimenterDashboard(_DashboardBase):
        url_pattern = URL_BASE + '/{code}'

        def dashboard_get(self, request, code):
            from otree.database import db
            from otree.models import Session
            session = db.query(Session).filter_by(code=code).one_or_none()
            if session is None:
                return HTMLResponse(_error_panel_html(
                    LookupError(f'no session with code {code!r}')))
            return HTMLResponse(_page_html(session))

    class ExperimenterDashboardData(_DashboardBase):
        url_pattern = URL_BASE + '/{code}/data'

        def dashboard_get(self, request, code):
            from otree.database import db
            from otree.models import Session
            # The JSON leg fails soft as JSON, not as an HTML panel: the
            # poller shows the error strip and keeps the last good table.
            try:
                session = db.query(Session).filter_by(code=code).one_or_none()
                if session is None:
                    return JSONResponse(
                        dict(ok=False, error=f'no session {code!r}'))
                return JSONResponse(session_snapshot(session))
            except Exception as exc:
                logger.exception('[dashboard] data build failed')
                return JSONResponse(
                    dict(ok=False, error=f'{type(exc).__name__}: {exc}'))

    return [
        Route(ExperimenterDashboardIndex.url_pattern,
              ExperimenterDashboardIndex, name='ExperimenterDashboardIndex'),
        Route(ExperimenterDashboard.url_pattern,
              ExperimenterDashboard, name='ExperimenterDashboard'),
        Route(ExperimenterDashboardData.url_pattern,
              ExperimenterDashboardData, name='ExperimenterDashboardData'),
    ]


# =============================================================================
# HTML — the operator screen. Density beats elegance; readable across a room.
# =============================================================================

def _base_css_href() -> str:
    v = _setting('STATIC_VERSION', '')
    return f'/static/global/css/base.css?v={escape(str(v))}'


def _error_panel_html(exc) -> str:
    """The error panel every wrapped handler degrades to. Plain, safe,
    self-contained; says what broke and that participants are unaffected."""
    detail = escape(f'{type(exc).__name__}: {exc}')
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Dashboard error</title>
<link rel="stylesheet" href="{_base_css_href()}">
<style>
 body {{ padding: 40px; }}
 .dash-error-panel {{ max-width: 720px; margin: 0 auto; background: var(--card-bg, #fff);
   border: 2px solid var(--danger, #c2384a); border-radius: var(--r-md, 12px); padding: 24px 28px; }}
 .dash-error-panel h1 {{ color: var(--danger, #c2384a); font-size: 1.2rem; margin: 0 0 .5em; }}
 .dash-error-panel code {{ background: var(--sunken, #f4f6fa); padding: 2px 6px; border-radius: 4px; }}
</style></head><body>
<div class="dash-error-panel">
  <h1>Experimenter dashboard error</h1>
  <p>The dashboard hit a bug while building this view. <strong>The study
  itself is unaffected</strong> — participant pages do not run this code.</p>
  <p><code>{detail}</code></p>
  <p>The full traceback is in the server log. Reload to retry.</p>
</div></body></html>"""


def _index_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Experimenter dashboard</title>
<link rel="stylesheet" href="{_base_css_href()}">
<style> body {{ padding: 40px; }} .dash-wrap {{ max-width: 720px; margin: 0 auto; }}
 .dash-sessions {{ line-height: 2; }} </style></head>
<body><div class="dash-wrap">
<h1>Experimenter dashboard</h1>
<p>Pick the running session to supervise:</p>
{body}
</div></body></html>"""


def _page_html(session) -> str:
    """The dashboard shell. Data arrives only via the poll (the first paint
    happens on the first tick), so this page carries no per-participant state
    and never goes stale."""
    code = escape(session.code)
    title = escape(str(session.config.get('display_name', '')
                       or session.config.get('name', '')))
    return (_PAGE_HTML
            .replace('__CSS_HREF__', _base_css_href())
            .replace('__SESSION_CODE__', code)
            .replace('__SESSION_TITLE__', title)
            .replace('__DATA_URL__', f'{URL_BASE}/{code}/data')
            .replace('__POLL_MS__', str(int(poll_seconds() * 1000))))


# The column headers. ADD A COLUMN HERE: one <th>, in the position the cell
# branch in renderRow (below) will fill.
def _step_header_html() -> str:
    """The timeline's header cells, DERIVED from STEP_LABELS — one <span> per
    step, in definition order.

    Joined with NO whitespace between the spans, deliberately: `.tl-header` is a
    CSS grid, and while whitespace-only text between grid items generates no
    boxes, emitting none at all means the item count cannot depend on how this
    string happens to be formatted. Labels go through escape() like every other
    interpolated value in this file, even though they are developer-authored —
    the rule is not conditional on where the text came from.
    """
    return ''.join(f'<span>{escape(label)}</span>'
                   for label in STEP_LABELS.values())


_COLGROUP_HTML = f"""
  <th class="c-label">Participant</th>
  <th class="c-timeline">
    <div class="tl-header">{_step_header_html()}</div>
  </th>
  <th class="c-quiz" title="Quiz attempts">Quiz</th>
  <th class="c-instr" title="Whole time in the intro app, both rounds: from
leaving the entry pages until the quiz is finished with">Intro time</th>
  <th class="c-earn">Earnings</th>
  <th class="c-state">State
    <!-- THE THRESHOLD LEGEND (item 17). A `title` tooltip, which is the pattern
         the other headers on this table already use — no second mechanism.
         The text is written by the poll from `stall_legend` in the JSON, so the
         values come from settings.py and a tuned threshold shows up on the next
         tick; nothing here is a number in the markup. It sits on a NORMAL row's
         header rather than on the amber rows alone, because the point is being
         able to SEE what the thresholds are, not only to explain an amber row
         after the fact. -->
    <span class="th-info" id="stall-info" tabindex="0"
          title="loading thresholds…">&#9432;</span>
  </th>
"""

_PAGE_HTML = ("""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Dashboard — __SESSION_TITLE__</title>
<link rel="stylesheet" href="__CSS_HREF__">
<style>
/* OPERATOR SCREEN. base.css supplies the tokens (colours, radii, shadow) so
   this looks like the study's control room, not a debug page — but density
   and across-the-room legibility outrank the participant pages' whitespace. */
body { padding: 18px 22px; font-size: 15px; line-height: 1.35; }
.dash-top { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  margin-bottom: 10px; }
.dash-top h1 { font-size: 1.15rem; margin: 0; }
.dash-top .session-code { color: var(--ink-mute); font-size: .9rem; }
.dash-counts { color: var(--ink-soft); font-size: .9rem; }
.dash-status { margin-left: auto; font-size: .85rem; color: var(--ink-mute); }
.dash-status.err { color: var(--danger); font-weight: 650; }
.dash-controls { font-size: .85rem; color: var(--ink-soft); user-select: none; }

table.dash { width: 100%; border-collapse: collapse; background: var(--card-bg);
  border: 1px solid var(--line); border-radius: var(--r-md); overflow: hidden;
  box-shadow: var(--shadow); }
table.dash th { text-align: left; font-size: .78rem; text-transform: uppercase;
  letter-spacing: .04em; color: var(--ink-mute); background: var(--sunken);
  padding: 7px 10px; border-bottom: 1px solid var(--line-strong); }
table.dash td { padding: 6px 10px; border-bottom: 1px solid var(--line);
  vertical-align: middle; }
table.dash tr:last-child td { border-bottom: none; }

tr.entry-only td { opacity: .45; }        /* de-emphasised, still there */
/* AMBER ROW TINT: KEPT alongside the yellow timing pill, deliberately (the
   pills change, 2026-08-13). The two are complementary, not duplicate: the
   tint is the across-the-room salience — what makes a stalled row findable in
   a 20-row table without reading it — and the pill carries the FACTS (which
   phase, how long). Dropping the tint would leave a small pill in the last
   column as the only signal; dropping the pill would restore "something is
   slow" with no what-or-how-much. If the pair ever reads as noisy on a real
   lab monitor, the tint is the one to drop — the pill holds the information. */
tr.stalled td { background: #fff3e0; }
tr.stalled td.c-label { box-shadow: inset 4px 0 0 var(--dash-amber); }
tr.terminal-row td { background: #fdf1f2; }
/* ROW TINT IS OUTCOME, PILLS ARE CONDITIONS (Julian, 2026-08-13). The tint is
   ONE consistent signal, readable across the room: GREEN finished, RED ended
   early, AMBER stalled, untinted still going. The four are mutually exclusive
   by construction (stalled requires an active row; finished requires no
   terminal state), so there is no precedence to resolve — but the rule to
   hold when adding the next state is the channel split: a CONDITION never
   touches the row. A finished non-SEPA participant keeps the GREEN row and
   the RED pill — the row says they completed, the pill says something about
   them still needs attention. Turning that row red would collapse outcome and
   condition back into one channel, which is exactly what the pills separated.
   The green is deliberately LIGHTER than the green pills' own background
   (#eaf6ef) so the finished tick, the earnings pill and the green quiz cell
   keep their edges against it instead of dissolving into a monotone row —
   the row colour only has to be scannable, not loud. */
tr.finished-row td { background: #f1faf4; }
tr.error-row td { color: var(--danger); }
/* UNRECOGNISED APP: its own colour, not amber and not the terminal pink — it is
   neither a slow participant nor an ended one, it is a gap in APP_STEPS. */
tr.unmapped-row td { background: #f5f1fd; }
tr.unmapped-row td.c-label { box-shadow: inset 4px 0 0 var(--dash-unmapped); }

.c-label { width: 15%; font-weight: 650; color: var(--ink);
  font-variant-numeric: tabular-nums; }
.c-label .code-fallback { color: var(--ink-mute); font-weight: 400;
  font-size: .85em; }
.c-label .page-hint { display: block; color: var(--ink-mute);
  font-weight: 400; font-size: .72rem; }

/* --- the timeline: EQUAL SPACING via one track per step -------------------
   BOTH numbers below are DERIVED from STEP_LABELS, not typed: the track count
   is len(STEPS), and the connector's inset is half a track (100/steps/2) so the
   line starts and ends at the centre of the first and last markers. Hard-coding
   them was two more copies of "how many steps are there" — add a seventh step
   and a fixed 6-track grid would silently drop it off the end of the row. */
/* 46%, NOT LESS: narrowing this (44% was tried when the state column became
   pills) squeezes the header grid until the long step labels hit their
   min-content floor and the six tracks stop being equal — measured as a 3.8px
   spread by dashboard_render_check. The pills wrap inside their own cell
   instead (.state-pills is flex-wrap), so they need no width ceded to them. */
.c-timeline { width: 46%; }
.tl-header, .tl { display: grid;
  grid-template-columns: repeat(__STEP_COUNT__, 1fr); }
.tl-header span { font-size: .68rem; text-align: center; }
.tl { align-items: center; position: relative; height: 30px; }
.tl::before { content: ''; position: absolute; left: __TL_INSET__;
  right: __TL_INSET__;
  top: 50%; height: 2px; background: var(--line-strong); }
.tl .stepcell { position: relative; display: flex; justify-content: center; }
.tl .dot { width: 8px; height: 8px; border-radius: 50%;
  background: var(--card-bg); border: 2px solid var(--line-strong); z-index: 1; }
.tl .stepcell.donestep .dot { background: var(--accent);
  border-color: var(--accent); }
/* The marker: occupies ONE step, advances when the step completes. During
   TASK it carries the round ("3 of 10") and advances INSIDE the step. */
.tl .marker { z-index: 2; min-width: 26px; height: 22px; padding: 0 7px;
  border-radius: 11px; background: var(--accent); color: #fff;
  font-size: .78rem; font-weight: 650; display: flex; align-items: center;
  justify-content: center; white-space: nowrap;
  font-variant-numeric: tabular-nums; }
.tl .marker.done-marker { background: var(--ok); }
/* Terminal override: the emoji + state colour fill the marker wherever the
   participant had reached. */
.tl .marker.terminal-marker { background: #fdeaec;
  border: 2px solid var(--danger); font-size: .95rem; padding: 0 5px; }

.c-quiz { width: 8%; }
.quizcell { position: relative; min-width: 52px; height: 22px;
  border: 1px solid var(--line-strong); border-radius: 6px; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  font-size: .8rem; font-weight: 650; background: var(--card-bg);
  font-variant-numeric: tabular-nums; }
.quizcell .fillbar { position: absolute; inset: 0; right: auto;
  background: var(--accent-soft); }
.quizcell span { position: relative; }
.quizcell.q-red { background: var(--danger); color: #fff;
  border-color: var(--danger); }
.quizcell.q-red .fillbar { display: none; }
.quizcell.q-green { background: var(--ok); color: #fff;
  border-color: var(--ok); }
.quizcell.q-green .fillbar { display: none; }
/* FORCED: an experimenter advanced them past the quiz without an answer (see
   _quiz_cell). Violet — the colour this screen already means "not a participant
   behaviour" by — and NOT red: nothing is wrong with the participant. */
.quizcell.q-forced { background: #f5f1fd; color: var(--dash-unmapped);
  border-color: var(--dash-unmapped); font-size: .72rem; }
.quizcell.q-forced .fillbar { display: none; }

/* --- PILLS: intro time and earnings (round-2 item 7) ----------------------
   These two are the QUANTITIES on this screen — the numbers an operator reads
   off rather than a state they glance at — so they get a shape of their own
   instead of sitting as bare text in a cell. Same pill for both, so the summary
   strip's averages below are visibly the same kind of thing.
   Times and money must NEVER truncate or wrap: an unreadable number is worse
   than no column (review, 2026-08-12). nowrap + tabular numerals, on the pill
   itself so it holds whatever the cell width does. */
.pill { display: inline-block; padding: 2px 9px; border-radius: 999px;
  background: var(--sunken); border: 1px solid var(--line);
  font-size: .82rem; font-weight: 650; color: var(--ink);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.pill.pill-live { background: var(--accent-soft); border-color: var(--accent);
  color: var(--accent); }
.pill.pill-earn { background: #eaf6ef; border-color: #bfe3cd; color: #1f7a46; }
.c-instr { width: 10%; white-space: nowrap; }
.c-earn { width: 10%; white-space: nowrap; }

/* --- the summary strip, BELOW the table (round-2 item 7) -------------------
   NOT a table row, deliberately and by instruction: a row of averages under a
   column of per-participant numbers reads as one more participant. It is its
   own strip, outside the table, and each pill is LABELLED "average" in words —
   the label is the part that makes it unmistakable, not the placement. */
.dash-summary { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin: 12px 2px 0; font-size: .85rem; color: var(--ink-mute); }
.dash-summary .sum-item { display: inline-flex; align-items: baseline; gap: 6px;
  background: var(--card-bg); border: 1px solid var(--line);
  border-radius: 999px; padding: 4px 12px 4px 10px; box-shadow: var(--shadow); }
.dash-summary .sum-label { text-transform: uppercase; letter-spacing: .04em;
  font-size: .68rem; font-weight: 650; }
.dash-summary .sum-n { font-size: .72rem; }

/* The header's threshold affordance (item 17): quiet, but obviously hoverable,
   and focusable so it is reachable without a mouse. */
.th-info { cursor: help; color: var(--ink-mute); font-size: .95rem;
  margin-left: 4px; }
.th-info:hover, .th-info:focus { color: var(--accent); }
/* --- THE STATE COLUMN: A COLLECTION OF PILLS (Julian, 2026-08-13) ----------
   Not a single state: OUTCOME pills (a terminal state, the green finished
   tick) and CONDITION pills (the timing warning, the lab's Non-SEPA flag)
   ACCUMULATE in one cell — a finished row keeps its condition pills, because
   finishing does not make a condition go away. See stateHTML for the order.
   flex-wrap, so several pills stack to a second line instead of clipping
   (times and money must never truncate — the same rule as .pill above). */
.c-state { width: 13%; font-size: .85rem; }
.state-pills { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.spill { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px;
  border-radius: 999px; font-size: .78rem; font-weight: 650;
  white-space: nowrap; border: 1px solid transparent;
  font-variant-numeric: tabular-nums; }
.spill .emoji { font-size: .95rem; }
.spill-finished { background: #eaf6ef; border-color: #bfe3cd; color: #1f7a46; }
.spill-terminal { background: #fdeaec; border-color: var(--danger);
  color: var(--danger); }
/* TIMING: yellow, filled. The pill names WHICH phase is slow and by how much;
   the amber row tint (above) is what makes the row findable at a glance. */
.spill-stall { background: #fff3c9; border-color: #eab308;
  color: var(--dash-amber); }
/* NON-SEPA: red background, white text (Julian's spec) — the one pill about
   money possibly not arriving, so it outshouts everything else in the cell. */
.spill-nonsepa { background: var(--danger); border-color: var(--danger);
  color: #fff; }
/* MONITOR CLIMBING: outlined red — the DQ's own colour and its own 👀, at
   reduced weight, because it is that state approaching rather than arrived. */
.spill-monitor { background: var(--card-bg); border-color: var(--danger);
  color: var(--danger); }
/* NO RETURN CLICK: outlined amber — a payment-flow worry, not a certainty
   (the stamp is best-effort), so quieter than the filled pills. */
.spill-return { background: var(--card-bg); border-color: var(--dash-amber);
  color: var(--dash-amber); }
.spill-unmapped { background: #f5f1fd; border-color: var(--dash-unmapped);
  color: var(--dash-unmapped); }

/* The two colours base.css has no token for: an operator-screen amber and the
   unrecognised-app violet. Declared as tokens rather than inlined so the row
   background and the text stay one decision. */
:root { --dash-amber: #b45309; --dash-unmapped: #6b21a8; }
</style></head>
<body>
<div class="dash-top">
  <h1>__SESSION_TITLE__</h1>
  <span class="session-code">session __SESSION_CODE__</span>
  <span class="dash-counts" id="counts"></span>
  <label class="dash-controls"><input type="checkbox" id="hide-entry">
    hide not-arrived rows</label>
  <span class="dash-status" id="status">connecting…</span>
</div>
<table class="dash">
  <thead><tr>__COLGROUP__</tr></thead>
  <tbody id="rows"><tr><td colspan="6">Waiting for first data…</td></tr></tbody>
</table>
<!-- THE AVERAGES, as pills under the table rather than as a final row: see
     .dash-summary. Filled by the poll; empty until there is something to
     average, so it never shows "average: 0:00" over an empty session. -->
<div class="dash-summary" id="summary"></div>
<script>
'use strict';
var DATA_URL = '__DATA_URL__';
var POLL_MS = Math.max(2000, parseInt('__POLL_MS__', 10) || 2000);
/* INJECTED from STEP_LABELS (see the top of experimenter_dashboard.py), never
   retyped here: the client's idea of the step order must be the server's. */
var STEPS = __STEPS_JSON__;
var inFlight = false;      // skip a tick while the previous one is running
var lastGood = null;

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function fmtSecs(s) {
  if (s == null) return '';
  var m = Math.floor(s / 60), r = s % 60;
  return m + ':' + (r < 10 ? '0' : '') + r;
}

function timelineHTML(row, meta) {
  var stepIdx = STEPS.indexOf(row.step);
  var cells = '';
  for (var i = 0; i < STEPS.length; i++) {
    var inner;
    if (i === stepIdx) {
      if (row.terminal) {
        inner = '<span class="marker terminal-marker" title="' +
                esc(row.terminal_label) + '">' + row.terminal_emoji + '</span>';
      } else if (row.step === 'done') {
        inner = '<span class="marker done-marker">✓</span>';
      } else if (row.step === 'task' && row.task_round != null) {
        inner = '<span class="marker">' + row.task_round +
                (meta.rounds_total ? ' of ' + meta.rounds_total : '') + '</span>';
      } else {
        inner = '<span class="marker">●</span>';
      }
    } else {
      inner = '<span class="dot"></span>';
    }
    cells += '<div class="stepcell' + (i < stepIdx ? ' donestep' : '') + '">' +
             inner + '</div>';
  }
  return '<div class="tl">' + cells + '</div>';
}

function quizHTML(q) {
  if (!q) return '';
  var cls = 'quizcell q-' + q.state, body, title = '';
  /* U+00D7 multiplication sign, not U+2717 ballot X: the ballot X is tofu in
     several Linux system fonts (measured in the render check's Chromium). */
  if (q.state === 'green') body = '<span>✓ ' + q.display + '</span>';
  /* FORCED: advanced past the quiz by an experimenter without answering it.
     Says the WORD rather than a count — a count here would be read as attempts
     the participant made, which is the very confusion this state exists to
     end. The tooltip carries the explanation. */
  else if (q.state === 'forced') {
    body = '<span>forced</span>';
    title = 'advanced past the quiz from the admin panel — no correct answer ' +
            'was ever submitted';
  }
  else if (q.state === 'red') body = '<span>' + q.attempts_wrong + '×</span>';
  else if (q.state === 'progress')
    body = '<div class="fillbar" style="width:' + (q.fill * 100) + '%"></div>' +
           '<span>' + q.attempts_wrong + '×</span>';
  else body = '<span>&nbsp;</span>';
  return '<div class="' + cls + '"' +
         (title ? ' title="' + esc(title) + '"' : '') + '>' + body + '</div>';
}

/* THE STATE COLUMN IS A COLLECTION OF PILLS (Julian, 2026-08-13), not one
   state. Two kinds share the cell and ACCUMULATE:
     * OUTCOME pills — how the row ended: a terminal state, or the green
       finished tick. At most one of these.
     * CONDITION pills — facts that persist REGARDLESS of outcome: the yellow
       timing warning while a phase runs long, the lab's red Non-SEPA payment
       flag, the violet unplaced-app notice. A FINISHED participant with a
       flagged condition shows BOTH the tick and the condition pill — finishing
       does not make the condition go away.
   Order: outcome first, then conditions, so a row reads "what happened, then
   what to know about it". */
function stateHTML(row) {
  var pills = [];
  if (row.terminal)
    pills.push('<span class="spill spill-terminal"><span class="emoji">' +
               row.terminal_emoji + '</span>' + esc(row.terminal_label) +
               '</span>');
  else if (row.finished)
    pills.push('<span class="spill spill-finished">✓ finished</span>');
  /* UNRECOGNISED APP: the timeline shows no marker for this row, so this cell
     has to say WHY — otherwise a row with no marker reads as a glitch. Names
     the app, because that is what somebody types into APP_STEPS. Other pills
     accumulate next to it: both facts matter. */
  if (row.step === 'unmapped')
    pills.push('<span class="spill spill-unmapped" title="add this app to ' +
               'APP_STEPS in experimenter_dashboard.py">⁉️ app “' +
               esc(row.unmapped_app) + '” not on the timeline</span>');
  /* THE TIMING PILL names WHICH phase is slow and by how much: the section,
     and the elapsed IN that section — which is exactly the number the
     per-phase threshold judged (row.stall_elapsed, see _stall_elapsed), never
     a second measurement that could disagree with the verdict. The threshold
     it tripped is in the tooltip; the header's ⓘ lists all four. */
  if (row.stalled)
    pills.push('<span class="spill spill-stall" title="' +
               fmtSecs(row.stall_elapsed) + ' in this phase — amber past ' +
               fmtSecs(row.stall_limit) + ' (tune in settings.py; all ' +
               'thresholds under the State header’s ⓘ)">⚠️ ' +
               esc(row.stall_section) + ' ' + fmtSecs(row.stall_elapsed) +
               '</span>');
  /* TAB-MONITOR COUNT WHILE IT CLIMBS: count and limit TOGETHER (a bare "2"
     is unreadable; "2 of 3" is somebody about to be ejected). The limit is
     the configured tab_monitor_max_violations, shipped in the row — never a
     number written into this markup. Active rows only: after the DQ the
     terminal pill says it. */
  if (row.monitor_count != null)
    pills.push('<span class="spill spill-monitor" title="Tab/focus losses ' +
               'counted by the server monitor — disqualified on reaching ' +
               'the limit (tab_monitor_max_violations). Someone to speak to ' +
               'BEFORE that happens.">👀 ' + row.monitor_count +
               (row.monitor_max != null ? ' of ' + row.monitor_max : '') +
               '</span>');
  /* FINISHED BUT NO RETURN CLICK (redirect sessions only — the server sends
     awaiting_return only when prolific_completion_redirects is on, because
     with no button there is nothing to have clicked; see _participant_row's
     gate comment). Best-effort: the stamp rides the live socket, so treat as
     "go look", not proof. */
  if (row.awaiting_return)
    pills.push('<span class="spill spill-return" title="Finished the study ' +
               'but no “Back to Prolific” click was recorded — their ' +
               'submission may still be open (unpaid) on the platform">' +
               '↩ no return click</span>');
  /* NON-SEPA (lab only): the bank form's SEPA check recorded a NO. The server
     sends non_sepa only for sepa === 0 in a lab session — null (the check
     never ran: every Prolific row, and any lab config not collecting bank
     details) is NO pill, and a non-Dutch but in-SEPA account is NO pill
     either (see _non_sepa_ids for all three narrowings). */
  if (row.non_sepa)
    pills.push('<span class="spill spill-nonsepa" title="This participant’s ' +
               'IBAN is outside the SEPA area — check the transfer will work ' +
               'before they leave">Non-SEPA</span>');
  if (!pills.length)
    return row.arrived ? ''
         : '<span style="color:var(--ink-mute)">not arrived</span>';
  return '<div class="state-pills">' + pills.join('') + '</div>';
}

function renderRow(row, meta) {
  if (row.error) {
    return '<tr class="error-row"><td class="c-label">' +
      esc(row.label || row.code) + '</td><td colspan="5">row failed to ' +
      'build — see server log (participant unaffected)</td></tr>';
  }
  var cls = [];
  if (row.entry_only) cls.push('entry-only');
  if (row.stalled) cls.push('stalled');
  if (row.terminal) cls.push('terminal-row');
  if (row.finished) cls.push('finished-row');
  if (row.step === 'unmapped') cls.push('unmapped-row');
  var label = row.label
    ? esc(row.label)
    : '<span class="code-fallback">' + esc(row.code) + '</span>';
  var pageHint = row.arrived && !row.finished
    ? '<span class="page-hint">' + esc(row.current_page) + '</span>' : '';
  /* PILLS, not bare cells (round-2 item 7). Money keeps its currency; the
     pill is what makes the two quantity columns read as quantities. */
  var earn = row.earnings != null
    ? '<span class="pill pill-earn">' + row.earnings.toFixed(2) +
      (meta.currency ? ' ' + esc(meta.currency) : '') + '</span>'
    : '';
  /* The live timer is marked by COLOUR (+ tooltip), never by a suffix: an
     appended "…" read as a truncated value on review (2026-08-12), on the
     amber row where the number matters most. The value must always read as
     a clean time. */
  var intro = row.intro_seconds != null
    ? '<span class="pill' + (row.intro_live ? ' pill-live' : '') + '"' +
      (row.intro_live ? ' title="still in the intro app"' : '') +
      '>' + fmtSecs(row.intro_seconds) + '</span>'
    : '';
  return '<tr class="' + cls.join(' ') + '">' +
    '<td class="c-label">' + label + pageHint + '</td>' +
    '<td class="c-timeline">' + timelineHTML(row, meta) + '</td>' +
    '<td class="c-quiz">' + quizHTML(row.quiz) + '</td>' +
    '<td class="c-instr">' + intro + '</td>' +
    '<td class="c-earn">' + earn + '</td>' +
    '<td class="c-state">' + stateHTML(row) + '</td>' +
    /* ADD A COLUMN HERE (render): one more td, matching the <th> you added
       to the header and the key you added in _participant_row. */
    '</tr>';
}

/* THE AVERAGES (round-2 item 7, denominators corrected under item 18).

   THE TWO PILLS AVERAGE OVER DIFFERENT POPULATIONS, DELIBERATELY. It looks like
   an inconsistency, so it is stated here, in the tooltips and in the labels:

     * INTRO TIME — everyone who has COMPLETED INTRO, whatever they are doing
       now. Somebody in round 4 of the task finished the intro long ago, so
       their intro time is a COMPLETED MEASUREMENT and belongs in the mean; it
       would be wrong to withhold it until they finish the whole study, which
       would leave the pill empty for most of a session and then jump.
     * EARNINGS — finished participants only, and not by choice: `earned` does
       not exist until the Results page computes it, so there is no number to
       average for anyone else.

   WHAT IS STILL EXCLUDED, and why that reason survives the correction: a LIVE
   intro timer, i.e. somebody still inside the intro. That number is still going
   up, so averaging it in would drag the mean around every two seconds and make
   it fall as people finish — an average that moves on its own is not readable.
   Anyone PAST intro is not live, so this excludes exactly the right rows.

   ALWAYS OVER THE WHOLE SESSION, never over the filtered view: the "hide
   not-arrived" toggle changes what is on screen and must not silently change
   what the average means.

   The count and its POPULATION are shown next to each pill, because "average
   intro time 4:12" over two of twenty participants is a different fact from the
   same number over twenty — and because two pills side by side with different
   denominators would otherwise be read as having the same one. */
function summaryHTML(data) {
  var times = [], money = [];
  data.rows.forEach(function (r) {
    if (r.intro_seconds != null && !r.intro_live) times.push(r.intro_seconds);
    if (r.earnings != null) money.push(r.earnings);
  });
  var out = '';
  function mean(a) {
    return a.reduce(function (x, y) { return x + y; }, 0) / a.length;
  }
  if (times.length)
    out += '<span class="sum-item" title="Mean intro time over everyone who ' +
           'has COMPLETED the intro app, whatever they are doing now. Anyone ' +
           'still inside intro is excluded: their timer is still running.">' +
           '<span class="sum-label">avg intro time</span>' +
           '<span class="pill">' + fmtSecs(Math.round(mean(times))) +
           '</span><span class="sum-n">of ' + times.length +
           ' past intro</span></span>';
  if (money.length)
    out += '<span class="sum-item" title="Mean earnings over FINISHED ' +
           'participants only — earnings do not exist until the results page ' +
           'computes them. A different denominator from the intro-time pill.">' +
           '<span class="sum-label">avg earnings</span>' +
           '<span class="pill pill-earn">' + mean(money).toFixed(2) +
           (data.currency ? ' ' + esc(data.currency) : '') +
           '</span><span class="sum-n">of ' + money.length +
           ' finished</span></span>';
  return out;
}

/* The STATE header's threshold legend (item 17), written from the JSON so the
   numbers are always the ones settings.py is currently serving. */
function paintStallLegend(data) {
  var el = document.getElementById('stall-info');
  if (!el || !data.stall_legend) return;
  /* NB the newlines are written '\\n' HERE because this whole page is a Python
     string literal in experimenter_dashboard.py: a bare '\n' would be turned
     into a REAL newline by Python, inside a single-quoted JS string, which is a
     syntax error — and a syntax error anywhere in this script means the poll
     never runs and the table never paints at all. (Measured: it did exactly
     that on the first attempt.) */
  var NL = '\\n';
  el.title = 'A row turns amber after too long in one PHASE. Entry and Task ' +
    'count the current page/round; Intro and Questionnaire count the whole ' +
    'phase. The limits:' + NL + data.stall_legend.map(function (p) {
      return '  • ' + p.label + ': ' + fmtSecs(p.seconds);
    }).join(NL) +
    NL + 'Tune them in settings.py (DASHBOARD_STALL_SECONDS_*).';
}

function repaint(data) {
  var hideEntry = document.getElementById('hide-entry').checked;
  var rows = data.rows.filter(function (r) {
    return !(hideEntry && r.entry_only);
  });
  var html = rows.map(function (r) { return renderRow(r, data); }).join('');
  document.getElementById('rows').innerHTML =
    html || '<tr><td colspan="6">No rows to show.</td></tr>';
  document.getElementById('summary').innerHTML = summaryHTML(data);
  paintStallLegend(data);
  var n = data.rows.length,
      /* ARRIVAL COUNT (Julian, 2026-08-13): how full the room is, at a
         glance. 👤 (bust-in-silhouette) rather than a person emoji: it
         renders as a solid neutral glyph with no face and no skin tone, so
         it stays legible at header size — with the standing caveat that
         emoji rendering depends on the operator machine's fonts
         (_ai/dashboard_notes.md, local only: _ai/ is gitignored). */
      arrived = data.rows.filter(function (r) { return r.arrived; }).length,
      fin = data.rows.filter(function (r) { return r.finished; }).length,
      term = data.rows.filter(function (r) { return r.terminal; }).length,
      stalled = data.rows.filter(function (r) { return r.stalled; }).length,
      /* Counted in the header too, not only per row: an unplaced app is a
         DASHBOARD defect, and it must be visible even when the affected row
         has scrolled out of sight. */
      unmapped = data.rows.filter(function (r) {
        return r.step === 'unmapped'; }).length;
  document.getElementById('counts').textContent =
    n + ' participants · 👤 ' + arrived + ' of ' + n + ' arrived · ' +
    fin + ' finished · ' + term + ' ended early' +
    (stalled ? ' · ' + stalled + ' stalled' : '') +
    (unmapped ? ' · ⁉️ ' + unmapped + ' in an app not on the timeline' : '');
}

function tick() {
  if (inFlight) return;              // 2s is a floor, not a promise
  inFlight = true;
  fetch(DATA_URL, {credentials: 'same-origin'})
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (!data.ok) throw new Error(data.error || 'server error');
      lastGood = data;
      repaint(data);
      var st = document.getElementById('status');
      st.textContent = 'updated ' + new Date().toLocaleTimeString();
      st.className = 'dash-status';
    })
    .catch(function (err) {
      var st = document.getElementById('status');
      st.textContent = 'update failed (' + err.message +
        ') — showing last good data';
      st.className = 'dash-status err';
    })
    .then(function () { inFlight = false; });
}

document.getElementById('hide-entry').addEventListener('change', function () {
  if (lastGood) repaint(lastGood);
});
tick();
setInterval(tick, POLL_MS);
</script>
</body></html>"""
             # THE FOUR DERIVATIONS OF THE STEP LIST, all resolved once at
             # import: the header cells, the grid's track count, the connector
             # inset (half a track) and the client's step order. Every one of
             # them comes from STEP_LABELS; none is typed twice.
             .replace('__COLGROUP__', _COLGROUP_HTML)
             .replace('__STEP_COUNT__', str(len(STEPS)))
             .replace('__TL_INSET__', f'{100 / len(STEPS) / 2:.2f}%')
             .replace('__STEPS_JSON__', json.dumps(list(STEPS))))
