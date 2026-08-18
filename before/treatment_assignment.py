"""PLACEHOLDER treatment assignment — balance-on-arrival.

WHAT A COPIER CHANGES vs WHAT IS REAL. The cells themselves are a PLACEHOLDER and
live in `settings.TREATMENT_CELLS` (shipped `['row', 'column']`); swap them for
your study's real cells there. The ALGORITHM in this file — assign the
least-filled cell on arrival, ties broken at random, atomically per session — is
REAL and is the point of the module. Keep the mechanism, change the cells.

WHY ON ARRIVAL, NOT AT SESSION CREATION (moved 2026-08-18; see DECISIONS.md).
Treatment used to be dealt to EVERY participant in `before.creating_session` with
`itertools.cycle`. That is balanced only because it deals the whole session at
once, like cards from a known deck — and it spent a cell on anyone who then
abandoned at consent or was turned away by the device gate. Assigning as late as
the first instructions page means a cell is spent only by someone who ACTUALLY
REACHED THE STUDY, so the balance is over ARRIVALS, not over rows created. Intro
is the latest safe point because instructions may themselves be treatment- or
role-specific and rendering them needs the cell to exist (TODO.md).

BALANCE-ON-ARRIVAL — a different algorithm, not a moved call. Once the deck is no
longer dealt at once, `cycle` cannot keep balance: each arrival must be given a
cell from only what has happened so far, and balance has to hold at every
intermediate moment of a session that may never fill. So on each arrival we COUNT
the cells already taken by participants IN THIS SESSION and assign the
LEAST-FILLED, breaking ties RANDOMLY. The random tie-break is load-bearing: a
deterministic one (first cell, or round-robin) makes the next assignment
guessable from the running order, which a participant could act on.

PERMANENT — we balance ARRIVALS, not completers (Julian). An assignment is never
released or reassigned, even if that participant abandons half-way. Idempotent: a
refresh of the instructions page re-enters this and returns the cell already
held, never a second draw. A real MULTI-CELL study that would rather balance
COMPLETERS (release an abandoned cell so it can be re-dealt) can revisit
release-on-abandon here — it is a statistical decision about the study, recorded
as deliberately deferred in DECISIONS.md, not an oversight.

RACE-SAFE per session — concurrency matters. Two participants can reach the
instructions page in the same instant. If both counted first and assigned second,
both would read the same least-filled cell and grab it, skewing the balance by
exactly the thing this algorithm exists to prevent. So the count-and-assign runs
under a DATABASE ROW LOCK on the session row (`SELECT ... FOR UPDATE`): a second
concurrent arrival blocks until the first has COMMITTED its cell, then counts a
state that already includes it.

  * On Postgres that row lock is what serialises arrivals — including across
    separate worker processes, which a process-local lock cannot.
  * On the sqlite dev database `FOR UPDATE` is a no-op (SQLAlchemy's sqlite
    dialect omits it), but sqlite serialises writes with a database-wide lock and
    oTree additionally funnels every ordinary page request through one
    process-wide lock (`otree/middleware.py`), so the critical section is
    single-threaded there too.

Belt and braces, and the DB lock does not depend on the process lock being
present — which is the point, because the process lock is the kind of "one
implementation decided by the environment" this codebase distrusts (CLAUDE.md).
"""
import random

import settings

# The PLACEHOLDER cells, from the one place they are defined (settings.py). A
# list copy so a caller cannot mutate the settings constant through us.
CELLS = list(settings.TREATMENT_CELLS)


def init_unassigned(subsession):
    """At session creation, stamp every participant as NOT YET assigned ('').

    Treatment is a PARTICIPANT_FIELD, and this template initialises every such
    field at creation so no export row is ever blank (`common.init_participant`
    does the rest). Empty string is the meaningful "reached creation but never
    took a cell" value — exactly what an abandoner at consent or a device
    screen-out exports now that a cell is spent only on arrival. Round 1 only
    (`before` has NUM_ROUNDS = 1 anyway), and via the participant, so the value
    survives across apps.
    """
    if subsession.round_number != 1:
        return
    for player in subsession.get_players():
        # Read/written through the participant: treatment_group lives in
        # participant.vars and must outlive the `before` app.
        player.participant.treatment_group = ''


def assigned_cell(participant) -> str:
    """The cell this participant holds, or '' if none yet.

    Read via `.vars.get`, NEVER `getattr(..., default)` — the vars descriptor
    raises KeyError, which a getattr default does not catch (CLAUDE.md).
    """
    return participant.vars.get('treatment_group', '') or ''


def _lock_session_row(session):
    """Take a row-level write lock on the session for the rest of THIS request's
    transaction — the atomicity boundary for count-and-assign (see the module
    docstring). Released when oTree commits the page (`otree/middleware.py`), so
    a concurrent arrival is held only for the few milliseconds of one assignment.

    Imported lazily: `otree.database` / `otree.models` are core and importable by
    now, but keeping the import at call time matches this codebase's habit
    (identity.py) and avoids any app-import-order surprise.
    """
    from otree.database import db
    from otree.models import Session
    db.query(Session).filter_by(id=session.id).with_for_update().one()


def _cell_counts(session) -> dict:
    """How many participants in this session currently hold each cell.

    Reads each row's raw vars blob (`_vars`) rather than `.vars`, deliberately:
    the `.vars` property calls `.changed()` on every access, which would mark
    every participant row dirty and rewrite every blob at commit — O(n) needless
    writes per arrival. This is a read-only tally, so it must not touch the dirty
    flag. Unassigned rows ('') and any stale/foreign value simply do not count
    toward a cell — only the current CELLS are tallied.
    """
    counts = {cell: 0 for cell in CELLS}
    for row in session.pp_set:
        cell = (row._vars or {}).get('treatment_group')
        if cell in counts:
            counts[cell] += 1
    return counts


def assign_on_arrival(player) -> str:
    """Give this participant a treatment cell if they do not have one, balancing
    the session's cells on arrival. Returns the cell held (existing or new).

    Call at the very START of intro, before anything reads treatment_group
    (intro.instructing.get). Idempotent and PERMANENT: an already-assigned
    participant keeps their cell and is never re-drawn.
    """
    participant = player.participant
    existing = assigned_cell(participant)
    if existing:
        return existing
    # Serialise concurrent arrivals in this session BEFORE counting (see the
    # module docstring). A second arrival blocks here until the first commits.
    _lock_session_row(player.session)
    counts = _cell_counts(player.session)
    fewest = min(counts.values())
    least_filled = [cell for cell, n in counts.items() if n == fewest]
    # RANDOM tie-break — a deterministic one makes the assignment guessable.
    cell = random.choice(least_filled)
    participant.treatment_group = cell
    return cell
