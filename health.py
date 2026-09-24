"""/health — THE ONE UNAUTHENTICATED ANSWER TO "IS THIS DEPLOY ALIVE?"

Import as ``import health``. Like ``common``, ``identity``, ``buildinfo``,
``otree_routes`` and ``experimenter_dashboard``, this file MUST stay at the
project root: the install hook does a top-level import and oTree puts the
project root on ``sys.path``.

WHY THIS FILE EXISTS
--------------------
"Did the deploy work?" was unanswerable by anything except a human looking at
the site. A hosting platform's own check is "did the process open a port", which
a broken oTree container passes happily — the study this template feeds had a
deploy report SUCCESS with the container already exited (see
``docs/hosting_railway.md``). So this module serves ONE route,
``GET /health``, whose STATUS CODE is a verdict a machine can act on:

    200  the database answers AND a session is bound to the room
         -> a participant arriving at /room/<name> gets a study
    503  anything else
         -> promote this build and the room link is dead

It ships even though this repo deliberately contains no deploy configuration,
because it is HOST-AGNOSTIC: it is equally the thing a lab launcher curls before
opening the door and the thing the Mac mini's monitoring polls. Pointing a
platform healthcheck at it is a service SETTING, documented as a snippet in
``docs/hosting_railway.md``, not a file this repo ships.

WHAT "READY" MEANS HERE, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------------
READY = the two facts a participant's first click depends on:

  1. THE DATABASE ANSWERS. Not "the process is up" — an oTree container with an
     unreachable database serves a 500 on every participant page while its port
     is wide open, which is exactly the "deploy succeeded, app is dead" case.
  2. A SESSION IS BOUND TO THE ROOM. An unbound room is a dead /room/<name> for
     everybody (``scripts/start.sh``'s FATAL banner exists for the same reason),
     and it is the NORMAL state for the first minutes after a fresh database
     comes up while start.sh builds the session.

NOT part of readiness, on purpose, and both are REPORTED in the body instead:

  * THE PRE-LAUNCH CHECKLIST. A build running testing values is a perfectly
    healthy deployment — that is how every pilot and rehearsal runs, and it is
    the state this template itself ships in. If a testing value made this 503,
    a platform would refuse to promote every rehearsal build, and the check that
    is supposed to protect the real launch would be the check everybody
    disables. ``scripts/prelaunch_check.py`` is what refuses a bad launch, at
    the moment it should.
  * THE BUILD STAMP. An unstamped build is a local or hand-built run, not an
    unhealthy one — and PROVENANCE IS DOCUMENTATION, NEVER A GATE (Julian,
    2026-08-23; DECISIONS.md). Reported here, fatal nowhere except
    ``scripts/verify_deploy.py``, which a human runs by hand after a deploy.

**WHICH ROOM, AND THE FORK THAT HAS NONE.** This template's participant entry
point IS the room (``settings.ROOMS``), so an unbound or absent room is
correctly not-ready. ``HEALTH_ROOM`` in the environment names a different room
if a deployment ever grows a second one. A fork that hands out participant links
directly and uses no room at all should change the predicate in
``_readiness_reasons`` — one function, and this sentence is the pointer to it —
rather than reading a permanent 503 as a bug.

THE THREE RULES THIS FILE FOLLOWS
---------------------------------
1. **IT CANNOT 500.** A health endpoint that throws is worse than none: a
   platform reads a 500 the same as a 503 today and something subtler tomorrow,
   and an operator debugging an outage gets a stack trace instead of a verdict.
   Every read is individually wrapped and the whole payload builder sits inside
   one last-resort ``except``. There is no path out of ``health_payload()`` that
   raises.

2. **IT IS READ-ONLY, AND CHEAP ENOUGH TO POLL.** One indexed lookup
   (``RoomToSession`` -> ``Session``) which doubles as the database probe: if it
   answers at all the database is up, and oTree's ``room.get_session()`` catches
   ``NoResultFound`` internally and returns None, which means "up, but unbound".
   No participant walk, nothing that scales with the study. Nothing is written:
   oTree's CommitTransactionMiddleware commits after every request under 500, so
   a handler that dirtied a row would write it on every poll.

3. **IT IS UNAUTHENTICATED, SO IT SAYS ONLY WHAT IS SAFE TO SAY.** A platform
   healthcheck cannot present an admin cookie or a REST key, so the route must
   be open, and what it exposes is chosen with that in mind:
       build stamp         a commit SHA. It is the whole point of the endpoint —
                           ``scripts/verify_deploy.py`` asks the running server
                           which commit it is, and nothing else can answer.
       room + session code neither is a credential: the room name is already in
                           every participant's URL bar, and a session code
                           without an admin login grants nothing.
       prelaunch problems  **THE NAMES ONLY, NEVER THE VALUES.** The checklist's
                           values include Prolific completion codes, and a code
                           is worth money to whoever finds it — it is what a
                           participant submits to be paid. A name like
                           ``config 'prolific' prolific_cc_code`` tells an
                           operator where to look and tells an outsider nothing
                           they could use.
   Nothing about participants is read or reported at all — no labels, no counts,
   no payoffs.

WHAT THE CHECKLIST HERE IS, AND IS NOT
---------------------------------------
``prelaunch`` reports ``settings._prelaunch_problems()`` — the BOOT BANNER's
list, and only that. It is deliberately NOT the whole of
``scripts/prelaunch_check.py``, which also hashes every file under ``_static/``
and imports the app to build the route table: correct for a deploy-time command,
absurd on a route polled every few seconds. So this block is a POINTER, not a
launch verdict, and `scripts/verify_deploy.py` prints it as information and
fails on none of it for exactly that reason.

INSTALLING
----------
Through ``otree_routes.install`` — the one implementation, shared with
``experimenter_dashboard.py``; see that module for the route-table mechanics and
for why both callers install from the tail of ``outro/__init__.py``.
``install_health_route_or_note()`` NEVER raises: a health endpoint that could
fail a participant's boot would be a worse liability than the outage it exists
to catch. Drift is loud (logged and printed), never fatal.

READING IT
----------
    curl -s http://localhost:8000/health | python3 -m json.tool

    {"ok": true, "status": "ready", "reasons": [],
     "database": {"ok": true, "error": ""},
     "room": {"name": "study", "bound": true, "session_code": "91sbnj1j"},
     "build": {"stamped": true, "commit": "<40 hex>", "commit_short": "a1b2c3d",
               "build_number": 214, "built_at": "...",
               "label": "build 214 · a1b2c3d", "problem": null},
     "prelaunch": {"clean": true, "problems": []}}
"""

import logging
import os

import otree_routes

logger = logging.getLogger(__name__)

# The path a platform's healthcheck setting must point at. Stated ONCE, here,
# and read by the route, the tests, verify_deploy and the docs snippet.
URL_PATH = '/health'
ROUTE_NAME = 'TemplateHealth'
ROUTE_NAMES = (ROUTE_NAME,)

# Which room's binding decides readiness. Normally there is exactly one room and
# no operator ever sets this; the override exists so a deployment that grows a
# second room does not have to change code to say which one is the front door.
ROOM_ENV_VAR = 'HEALTH_ROOM'

_install_log = []


# =============================================================================
# THE PAYLOAD — every block degrades to an honest answer, none of them raises
# =============================================================================

def _build_block() -> dict:
    """The running build stamp, in the shape the body publishes it.

    Never raises: ``buildinfo`` already degrades to an honest 'unstamped' answer
    for an absent, truncated or corrupt BUILD_INFO.json, and if the module
    itself cannot be imported (which would mean something far worse) that is
    reported in the SAME SHAPE rather than thrown — so no reader of this body
    needs a branch for "the build block is missing".
    """
    try:
        import buildinfo
        info = buildinfo.current()
        return dict(stamped=bool(info['stamped']), commit=info['commit'],
                    commit_short=info['commit_short'],
                    build_number=info['build_number'],
                    built_at=info['built_at'], label=buildinfo.label(info),
                    problem=info['problem'])
    except Exception as exc:                                   # noqa: BLE001
        logger.exception('[health] build stamp unreadable')
        return dict(stamped=False, commit=None, commit_short='',
                    build_number=None, built_at='', label='unknown build',
                    problem=f'{type(exc).__name__}: {exc}')


def _prelaunch_block() -> dict:
    """The pre-launch checklist verdict — NAMES ONLY (rule 3, and see WHAT THE
    CHECKLIST HERE IS above for what it deliberately omits).

    The source is ``settings._prelaunch_problems()``, the same list the boot
    banner prints, so this can never drift from what the server said at startup.
    Values are DROPPED here rather than merely left out of a print: a Prolific
    completion code is money and this route is open.
    """
    try:
        import settings
        problems = settings._prelaunch_problems()
        return dict(clean=not problems,
                    problems=[str(name) for name, _current, _must_be
                              in problems])
    except Exception as exc:                                   # noqa: BLE001
        logger.exception('[health] pre-launch checklist could not be read')
        # A CHECK THAT CANNOT RUN IS NEVER REPORTED AS CLEAN. `clean: true` with
        # an empty list would be indistinguishable from a genuinely clean
        # launch — the absence-without-a-presence failure CLAUDE.md's testing
        # section names, in a payload rather than a test.
        return dict(clean=False,
                    problems=[f'checklist could not be read '
                              f'({type(exc).__name__})'])


def _room_name() -> str:
    """The room whose binding decides readiness: the ``HEALTH_ROOM`` override if
    set, else the first room oTree actually has (ROOM_DICT preserves the order
    of ``settings.ROOMS``). '' when no room is configured, which is itself a
    not-ready answer — see the module docstring."""
    override = os.environ.get(ROOM_ENV_VAR)
    if override:
        return override
    from otree.room import ROOM_DICT
    return next(iter(ROOM_DICT), '')


def _rollback_quietly():
    """Leave the request's database session clean after a failed read, so the
    middleware's commit/rollback afterwards has nothing broken to trip over. Own
    try/except: on a dead database even the rollback can complain, and this
    endpoint answers 503 either way."""
    try:
        from otree.database import db
        db.rollback()
    except Exception:                                          # noqa: BLE001
        pass


def _room_block() -> tuple:
    """``(block, db_ok, db_error)`` for the room binding.

    ONE QUERY ANSWERS BOTH QUESTIONS, and the two answers must not collapse.
    ``room.get_session()`` catches ``NoResultFound`` internally and returns
    None, so an EXCEPTION out of it means THE DATABASE DID NOT ANSWER — not that
    the room is unbound. Those are different deployments: "still booting,
    nothing has bound a session yet" is normal and self-healing, while "the
    database is unreachable" is the dead-application case this endpoint exists
    for, and an operator reading a 503 needs to know which one they have.
    """
    try:
        name = _room_name()
    except Exception as exc:                                   # noqa: BLE001
        return (dict(name='', bound=False, session_code=None),
                False, f'rooms unreadable ({type(exc).__name__}: {exc})')

    if not name:
        # No room configured is not a database failure; db_ok stays True and the
        # not-ready reason says what is actually wrong.
        return (dict(name='', bound=False, session_code=None), True, '')

    try:
        from otree.room import ROOM_DICT
        room = ROOM_DICT.get(name)
        if room is None:
            # A configured HEALTH_ROOM that does not exist: not a database
            # problem, and never ready — reporting some OTHER room's binding
            # instead would be silently wrong in the one case somebody set the
            # variable on purpose.
            return (dict(name=name, bound=False, session_code=None), True, '')
        session = room.get_session()
    except Exception as exc:                                   # noqa: BLE001
        logger.warning('[health] database did not answer: %s: %s',
                       type(exc).__name__, exc)
        _rollback_quietly()
        return (dict(name=name, bound=False, session_code=None),
                False, f'{type(exc).__name__}: {exc}')

    if session is None:
        return (dict(name=name, bound=False, session_code=None), True, '')
    try:
        code = session.code
    except Exception as exc:                                   # noqa: BLE001
        _rollback_quietly()
        return (dict(name=name, bound=False, session_code=None),
                False, f'{type(exc).__name__}: {exc}')
    return (dict(name=name, bound=True, session_code=code), True, '')


def _readiness_reasons(room, db_ok, db_error) -> list:
    """THE VERDICT PREDICATE, in one place. Empty list = 200.

    A fork whose participants do not arrive through a room changes THIS
    function and nothing else (module docstring). Each reason is a sentence an
    operator can act on, not a code — this is the text that appears in a
    deploy log at 3am.
    """
    if not db_ok:
        return [f'the database did not answer ({db_error})']
    if not room['name']:
        return ['no room is configured in settings.ROOMS, so there is no '
                'participant entry point to be ready']
    if not room['bound']:
        return [f'no session is bound to room {room["name"]!r} — '
                f'/room/{room["name"]} would be a dead link '
                f'(scripts/start.sh binds one; on a fresh database, building a '
                f'large session legitimately takes minutes)']
    return []


def health_payload() -> tuple:
    """``(payload_dict, http_status)``. THE WHOLE ANSWER, AND IT NEVER RAISES.

    Split out from the route so it can be driven directly in a test — including
    the failure modes a live server will not produce on demand (a database that
    throws, a rooms table that is unreadable) — and so the route itself has
    nothing in it that can go wrong.
    """
    try:
        room, db_ok, db_error = _room_block()
        reasons = _readiness_reasons(room, db_ok, db_error)
        payload = dict(
            ok=not reasons,
            status='ready' if not reasons else 'not_ready',
            reasons=reasons,
            database=dict(ok=db_ok, error=db_error),
            room=room,
            # NEITHER OF THESE TOUCHES THE VERDICT ABOVE. See the module
            # docstring: a build running testing values, or carrying no stamp at
            # all, is a healthy deployment.
            build=_build_block(),
            prelaunch=_prelaunch_block(),
        )
        return payload, (200 if payload['ok'] else 503)
    except Exception as exc:                                   # noqa: BLE001
        # THE LAST RESORT. Nothing above should reach here, and if something
        # does the answer is still a verdict in the same shape, never a stack
        # trace and never a 500.
        logger.exception('[health] payload build failed')
        _rollback_quietly()
        return (dict(ok=False, status='not_ready',
                     reasons=[f'the health check itself failed '
                              f'({type(exc).__name__}: {exc})'],
                     database=dict(ok=False, error=''),
                     room=dict(name='', bound=False, session_code=None),
                     build=dict(stamped=False, commit=None, commit_short='',
                                build_number=None, built_at='',
                                label='unknown build', problem=None),
                     prelaunch=dict(clean=False, problems=[])),
                503)


# =============================================================================
# INSTALL — through the shared installer; never fatal to a boot
# =============================================================================

# Re-exported so a reader of this module, and its tests, use one vocabulary.
INSTALLED = otree_routes.INSTALLED
ALREADY = otree_routes.ALREADY
NOT_IMPORTABLE = otree_routes.NOT_IMPORTABLE


def _build_routes():
    """The one Route object. Defined HERE, inside a function, so importing this
    module can never drag oTree in — nothing at module scope may be able to fail
    and take the app down (the same rule experimenter_dashboard.py builds its
    endpoints under)."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health_endpoint(request):
        # ONLY EVER ENTERED FOR GET AND HEAD — enforced by `methods=` on the
        # Route below, not here. This was written with its own method check
        # first; MEASURED against starlette 0.14.1, that branch is UNREACHABLE
        # (`Route.handle` raises HTTPException(405) before the endpoint is
        # called), so it was deleted rather than left looking like the thing
        # that protects this route. Inert code that appears to be a guard is
        # worse than no code: the next reader believes it.
        payload, status = health_payload()
        return JSONResponse(payload, status_code=status)

    # `methods=` is the enforcement AND the declaration: a health endpoint is a
    # read, and anything else gets Starlette's 405 without touching the
    # database. NB this Starlette sends that 405 with no `Allow` header; that is
    # its behaviour, not something this file can set from here.
    return [Route(URL_PATH, health_endpoint, name=ROUTE_NAME,
                  methods=['GET', 'HEAD'])]


def install_health_route():
    """Append ``GET /health`` to oTree's route table. Returns INSTALLED /
    ALREADY / NOT_IMPORTABLE, and RAISES only on version drift — the boot-time
    caller catches that.

    The global-lock exemption is asked for AFTER the append, and only on a fresh
    install: it is a latency optimisation, so a failure to get it is logged and
    ignored rather than allowed to fail the install (see
    ``otree_routes.exempt_from_global_lock``).
    """
    outcome = otree_routes.install(ROUTE_NAMES, _build_routes,
                                   'health.install_health_route', _install_log)
    if outcome == INSTALLED:
        otree_routes.exempt_from_global_lock(ROUTE_NAME, 'health')
    return outcome


def health_is_installed() -> bool:
    """Is the route actually in the table right now? Never raises."""
    return otree_routes.is_installed(ROUTE_NAMES)


def install_health_route_or_note():
    """THE BOOT-TIME CALL SITE (the tail of ``outro/__init__.py``). Installs,
    and NEVER raises — not even on drift, which it logs loudly instead.

    A missing /health costs a deploy gate and a platform healthcheck; raising
    here would cost every participant their boot. Same severity split as the
    dashboard install next to it, and for the same reason: neither of these is
    worth a participant's session.

    THE MESSAGES USE THE LITERAL '/health' RATHER THAN INTERPOLATING
    ``URL_PATH``, for the reason spelled out at
    ``experimenter_dashboard.install_dashboard_route_or_note``: a rename or
    deletion of that very constant is a likely cause of the failure being
    reported, and a reporter that can fail on the thing it is reporting is no
    reporter at all.
    """
    try:
        outcome = install_health_route()
        if outcome == NOT_IMPORTABLE:
            message = (
                '[health] /health NOT INSTALLED: otree.urls was not importable '
                'at the app-import install point, which no supported boot path '
                'should reach. Participants are unaffected; the deploy gate '
                '(scripts/verify_deploy.py) and any platform healthcheck will '
                f'see a 404. Attempts: {_install_log!r}')
            logger.error(message)
            print(message, flush=True)
        return outcome
    except Exception as exc:                                   # noqa: BLE001
        message = (
            f'[health] /health NOT INSTALLED (version drift): {exc}\n'
            'Participants are unaffected; the deploy gate '
            '(scripts/verify_deploy.py) and any platform healthcheck will see '
            'a 404 until health.py is updated for the installed oTree.')
        logger.error(message)
        print(message, flush=True)
        return 'drift'


def assert_health_route():
    """THE SINGLE PLACE A MISSING /health IS A FAILURE — for TESTS, which boot
    oTree and must fail loudly if the install silently regressed. Deliberately
    NOT called at boot; see install_health_route_or_note."""
    outcome = install_health_route()
    if not health_is_installed():
        raise RuntimeError(
            f'health.assert_health_route: install reports {outcome!r} but '
            f'{URL_PATH} is not in otree.urls.routes. '
            f'Attempts: {_install_log!r}')
    return outcome
