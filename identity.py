"""Participant IDENTITY — one participant row per external (Prolific) id, and
never a 500 if that is ever violated anyway.

Import as ``import identity``. Like ``common``, this file MUST stay at the
project root: the apps do a top-level import and oTree puts the project root on
``sys.path``.

WHY THIS EXISTS
---------------
oTree resolves a RETURNING participant by their label
(``otree/views/participant.py``, verified against the installed oTree 6.0.15)::

    def get_participant_by_label(session, label):
        q = session.pp_set
        if label:
            try:
                return q.filter_by(label=label).one()
            except NoResultFound:
                pass
        return q.filter_by(visited=False).order_by('id').first()

``.one()`` raises ``MultipleResultsFound`` when two rows share a label, and only
``NoResultFound`` is caught — the two are siblings in SQLAlchemy's exception
hierarchy, neither being a subclass of the other. **So the moment two
participant rows in one session carry the same label, the next entry with that
id is an uncaught exception: a 500 on the front door, for the participant who
actually owns that id, for good.**

That matters more here than it looks, because the device screen-out is a SOFT
WALL (see `before._apply_device_gate`): its whole premise is that somebody can
leave on a phone and come back on a computer AND BE REJOINED TO THE SAME ROW.
Rejoining IS this label lookup. If the lookup can raise, the soft wall does not
work.

WHERE A DUPLICATE COULD COME FROM
---------------------------------
Not from oTree's own entry path: that looks a label up before it stamps it. It
comes from any FREE-TEXT route to a label — in this template, the confirm-your-
Prolific-ID page (`before.ConfirmProlificID`), where a participant can mistype
an id or paste a friend's. Somebody who entered on a bare room link holds an
unlabelled row; typing an id another row already owns would, without this
module, produce the duplicate that locks the owner out.

TWO DEFENCES, DELIBERATELY BOTH
-------------------------------
1. **Do not create duplicates** (`claim_label`). Every label write in this
   template goes through it, and it REFUSES a claim another row in the session
   already holds. Refusing rather than inventing a suffixed variant is
   deliberate: a suffixed label is a silent second identity, and joining — not
   forking — is what the soft wall depends on.
2. **Never raise even if one exists anyway** (`install_duplicate_label_guard`).
   Defence 1 cannot cover rows created before it shipped, rows an admin edited
   by hand, or any path inside oTree itself. The guard replaces oTree's
   ``.one()`` with "the earliest labelled row wins", so a duplicate degrades to
   JOINING THE FIRST ROW instead of locking everybody with that id out. With no
   duplicate present the two implementations return the same participant.

WHAT COUNTS AS THE SAME ID
--------------------------
Matching is WHITESPACE-COLLAPSED and CASE-FOLDED; storage is VERBATIM (minus
surrounding whitespace). A real Prolific id is 24 lowercase hex characters, but
the confirmation page lets a participant type one, and "  ABC…" is the same
person as "abc…". Comparing loosely means retyping an id in capitals rejoins
their own row instead of colliding with it; storing what was sent means the
exported label still byte-matches what the platform gave us, which is what
payment reconciliation is done against.

THE COMPARISON HAPPENS IN PYTHON, NEVER IN SQL. String case-sensitivity in a
WHERE clause is a property of the database collation — sqlite here, postgres in
the container — and a rule about who owns an identity must not change with the
database. A session is a few hundred rows; the cost is nothing.

SILENT TO THE PARTICIPANT, LOUD IN THE DATA
-------------------------------------------
A refused claim produces no message, no field error and no rendering
difference. The participant is not blocked (they keep their own row and finish
the study normally), they cannot fix a clash anyway, telling them would generate
support mail on a payment-related field, and it would invite fiddling with the
id. What it produces instead is data: `before.Player.prolific_label_conflict`
carries the OWNING ROW's participant code — the thing payment triage needs — and
`participant_extra['prolific_label_conflict']` carries the fuller record.

AND NEVER A MARKER IN ``participant.label`` ITSELF. That column is oTree's own:
it is what entry matches on, and it is what a human reads when paying, so its
invariant is that it holds the real id or nothing — never a decorated string
somebody has to interpret. An EMPTY label is not a clash signal either: it is
the normal state of anybody who entered on a bare link.
"""

# otree.models.Participant.label is Column(String(100)), and oTree's own
# set_label() 404s above that length. Our writes assign the attribute directly,
# so the cap is enforced here instead — a longer value is truncated rather than
# left to fail at flush time.
MAX_LABEL_LEN = 100

# The key inside participant_extra holding the refused-claim record, and the
# name of the `before.Player` column carrying the same fact as a first-class
# export field. ONE spelling, defined once: `prolific_label_conflict` rather
# than a bare `label_conflict`, so whoever is reconciling payments sees it next
# to `participant_id_url` / `participant_id_external` and can tell at a glance
# that it is about the recruitment id.
CONFLICT_KEY = 'prolific_label_conflict'
MAX_CONFLICTS_KEPT = 5


def normalise_label(raw) -> str:
    """The storable form of a supplied id: surrounding whitespace stripped,
    inner whitespace collapsed, capped at the column length. '' for anything
    empty. Case is NOT touched (see the module docstring)."""
    if not raw:
        return ''
    return ' '.join(str(raw).split())[:MAX_LABEL_LEN]


def same_label(a, b) -> bool:
    """Do these two spellings denote the same id? (case-folded, whitespace-collapsed)"""
    return normalise_label(a).casefold() == normalise_label(b).casefold()


def label_owner(session, label, exclude=None):
    """The participant in this session already holding `label`, or None.

    Compared in Python, not in SQL — see the module docstring. `exclude` is the
    row doing the claiming, which obviously does not count as somebody else.
    """
    target = normalise_label(label).casefold()
    if not target:
        return None                      # an empty label is nobody's identity
    for other in session.get_participants():
        if exclude is not None and other.id == exclude.id:
            continue
        if normalise_label(other.label).casefold() == target:
            return other
    return None


def claim_label(participant, raw_label):
    """Stamp `raw_label` on `participant` unless another row already owns it.

    Returns (outcome, owner_code):

        ('empty', None)      nothing supplied — no write
        ('unchanged', None)  they already hold this id (perhaps spelled
                             differently) — no write, their own spelling stands
        ('set', None)        the label was written
        ('conflict', code)   ANOTHER row in this session holds it — NOT written;
                             `code` is that participant's code

    The caller writes `code` into `before.Player.prolific_label_conflict`; the
    fuller record goes into participant_extra here. Nothing is raised and
    nothing is shown to the participant (see the module docstring).
    """
    label = normalise_label(raw_label)
    if not label:
        return 'empty', None
    if same_label(participant.label, label):
        # Same person, possibly a different spelling. Keep the spelling we were
        # given at entry: it is the one the platform sent.
        return 'unchanged', None
    owner = label_owner(participant.session, label, exclude=participant)
    if owner is not None:
        _record_conflict(participant, label, owner)
        return 'conflict', owner.code
    participant.label = label
    return 'set', None


def _record_conflict(participant, label, owner):
    """Durably note a refused claim in participant_extra. Defensive: a telemetry
    write must never break the page it rides on (CLAUDE.md)."""
    try:
        bucket = participant.vars.get('participant_extra') or {}
        conflicts = list(bucket.get(CONFLICT_KEY) or [])
        conflicts.append(dict(label=label, owner_code=owner.code))
        bucket[CONFLICT_KEY] = conflicts[-MAX_CONFLICTS_KEPT:]
        participant.participant_extra = bucket
    except Exception:
        pass


# --- defence 2: entry must never raise ---------------------------------------
#
# THREE THINGS THIS SECTION HAS TO GET RIGHT, and they pull against each other:
#
#   * the PARTICIPANT must degrade gracefully — a duplicate must join a row, not
#     produce a 500;
#   * WE must not degrade silently — a duplicate existing at all means something
#     we did not anticipate has already damaged data integrity, and this is the
#     only code in the system that can see it happen. So the graceful path is
#     LOUD in the log and on the row;
#   * and the INSTALL itself must be knowable. A guard you cannot tell is
#     missing is not a guard.
#
# THE DISTINCTION THE INSTALL TURNS ON — write it down, because the two states
# reach identical code if you catch bare Exception, which is exactly how this
# used to return False for both:
#
#   CANNOT IMPORT YET   — `otree.views.participant` is not importable at this
#                         moment. EXPECTED at the early (settings) install
#                         point, and it must NEVER raise: raising would turn a
#                         benign ordering fact into a guaranteed boot crash,
#                         which is strictly worse than the rare gap it guards.
#   IMPORTED, WRONG SHAPE — the module loaded and `get_participant_by_label` is
#                         missing, not callable, or no longer takes
#                         (session, label). That is VERSION DRIFT, it is never
#                         benign, and it is LOUD wherever it is seen.
#
# (Same lesson as `unknown` vs `UNDETERMINED` in common.py: the dangerous state
# is the one where two genuinely different situations become indistinguishable.)

import logging

logger = logging.getLogger(__name__)

# Install outcomes, returned rather than raised (except DRIFT, see above).
INSTALLED = 'installed'          # newly patched
ALREADY = 'already'              # idempotent no-op, the guard was in place
NOT_IMPORTABLE = 'not_importable'  # expected early; try again later

# The key under participant_extra recording that a duplicate was OBSERVED.
DUPLICATE_SEEN_KEY = 'duplicate_label_seen'

# Where the last install attempt got to, for the assert point and for tests.
_install_log = []


def _import_views():
    """Import oTree's participant views. Separated so the IMPORT failure and
    the SYMBOL check can be told apart (and so a test can simulate the early
    'not importable yet' case without breaking anything else)."""
    from otree.views import participant as pv
    return pv


# THE SPLIT IS BY WHERE THE FAILURE HAPPENS, NOT BY EXCEPTION TYPE — measured,
# and it is not obvious. Importing `otree.views.participant` from settings.py at
# boot fails with an **AttributeError**, not an ImportError: oTree's own
# `otree/settings.py` reads `settings.SESSION_CONFIGS` back out of this
# half-executed module ("partially initialized module 'settings' has no
# attribute 'SESSION_CONFIGS'"). Catching only ImportError there would crash
# every boot. So ANY failure of the import step is treated as "not importable
# yet"; the loudness lives entirely in the SYMBOL checks below, which only run
# when the module did load.


def _finished(participant) -> bool:
    """Has this row COMPLETED the study?

    Used only to pick between duplicate rows. FINISHED, NOT TERMINAL — the
    distinction is load-bearing:

      * a finished row is a DEAD END to join: the returning participant lands on
        a completed session's ending with no way forward;
      * a SCREENED-OUT row (exit code -4) is terminal but must stay joinable,
        because joining it is exactly what lifts the screen-out (the soft wall
        in `before._apply_device_gate`). Excluding "terminal" rows generally
        would break that feature outright.

    So this asks one question only: did they finish? Both by our exit code and
    by oTree's own page cursor, since a row can be past the last page without
    our code having stamped anything.
    """
    try:
        try:
            from settings import EXIT_CODES
            finished_code = EXIT_CODES['finished']
        except Exception:
            finished_code = 1        # the shipped value; see settings.EXIT_CODES
        if participant.vars.get('exit_code') == finished_code:
            return True
        idx = getattr(participant, '_index_in_pages', None)
        last = getattr(participant, '_max_page_index', None)
        if isinstance(idx, int) and isinstance(last, int) and idx > last:
            return True
    except Exception:
        pass
    return False


def _record_duplicate_seen(participant, label, rows):
    """LOUDLY note that a duplicate label was observed. Never raises.

    Only ever called when MORE THAN ONE row carries the label — never on the
    ordinary single-row lookup, which is silent by design. Two channels, because
    they are found by different people at different times: the log (an operator
    watching the server, and the pre-deploy log scan) and the participant row
    itself (whoever opens the export afterwards)."""
    codes = [getattr(r, 'code', '?') for r in rows]
    message = (f"[identity] DUPLICATE PARTICIPANT LABEL {label!r} in session "
               f"{getattr(participant, '_session_code', '?')}: {len(rows)} rows "
               f"{codes} share it; joined {getattr(participant, 'code', '?')}. "
               f"Entry did NOT 500, but the data needs a human: something "
               f"created a second row for one identity.")
    try:
        logger.error(message)
    except Exception:
        pass
    try:
        print(message, flush=True)
    except Exception:
        pass
    try:
        bucket = participant.vars.get('participant_extra') or {}
        seen = list(bucket.get(DUPLICATE_SEEN_KEY) or [])
        entry = dict(label=label, rows=codes,
                     joined=getattr(participant, 'code', ''))
        if entry not in seen:
            seen.append(entry)
        bucket[DUPLICATE_SEEN_KEY] = seen[-5:]
        participant.participant_extra = bucket
    except Exception:
        pass


def install_duplicate_label_guard():
    """Replace oTree's `get_participant_by_label` with one that cannot raise
    MultipleResultsFound. Returns INSTALLED / ALREADY / NOT_IMPORTABLE.

    RAISES only on VERSION DRIFT (imported, wrong shape) — see the note above.
    Idempotent via the `_duplicate_label_guarded` marker, and a no-op in every
    case except the one that would otherwise be a 500.

    Installed from TWO places, deliberately: `settings.py` (because the room's
    entry views can be reached before any app module has been imported, which
    would leave a window open) and `before/__init__.py`. The settings call may
    legitimately hit NOT_IMPORTABLE and that is fine — it records why and
    returns. `assert_duplicate_label_guard()` is the single place that treats a
    missing guard as a failure.
    """
    try:
        pv = _import_views()
    except Exception as exc:
        # EXPECTED at the early install point, and NOT only as ImportError —
        # see the note above `_import_views`. Recorded, never raised.
        _install_log.append((NOT_IMPORTABLE, f'{type(exc).__name__}: {exc}'))
        return NOT_IMPORTABLE

    original = getattr(pv, 'get_participant_by_label', None)
    if original is None or not callable(original):
        raise RuntimeError(
            "identity.install_duplicate_label_guard: this oTree has no callable "
            "otree.views.participant.get_participant_by_label. That function is "
            "what resolves a returning participant by label, and without our "
            "guard two rows sharing a label are an uncaught MultipleResultsFound "
            "— a 500 on the front door that locks the id's owner out for good. "
            "The installed oTree has drifted: find the new entry lookup and "
            "re-point this guard at it.")
    if getattr(original, '_duplicate_label_guarded', False):
        _install_log.append((ALREADY, ''))
        return ALREADY

    # SHAPE CHECK. Signature drift is the quiet half of version drift: a
    # renamed or reordered parameter would make the wrapper below call oTree
    # wrongly, and nothing would say so.
    try:
        import inspect
        params = list(inspect.signature(original).parameters)
    except (TypeError, ValueError):
        params = ['session', 'label']      # a builtin/C function: accept it
    if params[:2] != ['session', 'label']:
        raise RuntimeError(
            f"identity.install_duplicate_label_guard: "
            f"otree.views.participant.get_participant_by_label now takes "
            f"{params!r}, not (session, label). The guard has not been "
            f"installed, because a wrapper written for the old signature would "
            f"be worse than none. Re-check the entry lookup against the "
            f"installed oTree and update identity.py.")

    def get_participant_by_label(session, label):
        try:
            if label:
                rows = session.pp_set.filter_by(label=label).order_by('id').all()
                if rows:
                    chosen = _choose_row(rows)
                    if len(rows) > 1:
                        # Graceful for them, LOUD for us.
                        _record_duplicate_seen(chosen, label, rows)
                    return chosen
            # No label, or no row holds it: oTree's own behaviour, unchanged.
            # Called with label=None so its `.one()` branch is never reached.
            return original(session, None)
        except Exception:
            # Never worse than not installing: fall back to oTree's own.
            return original(session, label)

    get_participant_by_label._duplicate_label_guarded = True
    pv.get_participant_by_label = get_participant_by_label
    _install_log.append((INSTALLED, ''))
    return INSTALLED


def _choose_row(rows):
    """Which of several rows sharing a label a returning participant JOINS.

    THE EARLIEST ROW THAT IS NOT FINISHED, falling back to the earliest overall
    if they all are. Earliest is the right instinct — it is the row they will
    have been using — but earliest is not always joinable: sending somebody into
    a COMPLETED session shows them an ending with no way forward, which is the
    dead end this guard exists to avoid in the first place.

    FINISHED, not terminal (see `_finished`): a screened-out row stays joinable
    on purpose, because joining it is what lifts the screen-out.
    """
    for row in rows:
        if not _finished(row):
            return row
    return rows[0]


def guard_is_installed() -> bool:
    """Is the guard actually in place right now? Never raises."""
    try:
        pv = _import_views()
    except ImportError:
        return False
    return bool(getattr(getattr(pv, 'get_participant_by_label', None),
                        '_duplicate_label_guarded', False))


def assert_duplicate_label_guard():
    """THE SINGLE PLACE A MISSING GUARD IS A FAILURE. Raises if it is not in.

    WHERE THIS IS CALLED, AND WHY THERE. From `before/__init__.py`, the LAST
    install point: by the time an app module is imported, oTree has loaded the
    app modules at boot, so `otree.views.participant` must be importable and a
    failure here cannot be the benign "not importable yet" case. It also fails
    the BOOT, before a single participant is served — which is what loud should
    mean for a server.

    Deliberately NOT at first participant entry, which was the other candidate.
    A missing guard is a CONDITIONAL risk (it only matters if a duplicate
    exists); raising on the entry path would turn it into a CERTAIN outage for
    every participant, which is the same trade the early install point must not
    make. First entry instead gets `note_guard_state()` below — loud in the log
    and on the row, never a raise — so the "both installs failed for a reason
    nobody anticipated" case is still visible without being a participant's
    problem.
    """
    outcome = install_duplicate_label_guard()      # idempotent
    if outcome == NOT_IMPORTABLE:
        raise RuntimeError(
            "identity.assert_duplicate_label_guard: otree.views.participant is "
            "still not importable at app-module import time, which should be "
            "impossible — oTree imports the apps at boot. The duplicate-label "
            "guard is NOT installed, so two rows sharing a participant label "
            "would be an uncaught MultipleResultsFound (a 500 at entry). "
            f"Attempts so far: {_install_log!r}")
    if not guard_is_installed():
        raise RuntimeError(
            "identity.assert_duplicate_label_guard: the guard reports "
            f"{outcome!r} but is not in place on otree.views.participant. "
            "Something is replacing the function after us. Do not launch: a "
            "duplicate participant label would 500 at entry.")
    return outcome


def note_guard_state(participant=None):
    """First-real-use verification: loud, never fatal. Returns True if in place.

    Belt to `assert_duplicate_label_guard`'s braces, for the case where both
    installs somehow failed at boot in a way nobody anticipated — a monkeypatch
    from another library, an import order we did not predict. It records and
    carries on: at this point we are inside a participant's request, and a raise
    would make a conditional risk into their certain outage.
    """
    try:
        if guard_is_installed():
            return True
        message = ("[identity] DUPLICATE-LABEL GUARD IS NOT INSTALLED at "
                   "participant entry. Entry works, but two rows sharing a "
                   "participant label would 500 and lock that id's owner out. "
                   f"Install attempts: {_install_log!r}")
        logger.error(message)
        print(message, flush=True)
        if participant is not None:
            bucket = participant.vars.get('participant_extra') or {}
            bucket['duplicate_label_guard_missing'] = True
            participant.participant_extra = bucket
    except Exception:
        pass
    return False
