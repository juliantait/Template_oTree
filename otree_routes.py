"""APPENDING AN EXTRA ROUTE TO oTree's OWN APP — the ONE implementation.

Import as ``import otree_routes``. Like ``common``, ``identity``, ``buildinfo``
and ``experimenter_dashboard``, this file MUST stay at the project root: its
callers do top-level imports and oTree puts the project root on ``sys.path``.

WHY THIS FILE EXISTS
--------------------
Two things in this repo serve routes that are not oTree's — the experimenter
dashboard (``experimenter_dashboard.py``, since 2026-08-12) and the deploy
gate's health endpoint (``health.py``, since 2026-08-23). Appending a route to
oTree is ONE concept, and CLAUDE.md devotes a section to what happens when one
concept gets two implementations: they drift, and the drift stays invisible
until the environment changes — here, until an oTree upgrade moves the route
table and one of the two copies is updated. So the route-table half lives here
and both callers pass through it.

WHAT IS SHARED AND WHAT IS DELIBERATELY NOT
--------------------------------------------
SHARED (this file): importing ``otree.urls``, the mid-import versus
version-drift split, the shape check on ``routes``, idempotency by route name,
the path-shadow refusal, extending both ``otree.urls.routes`` and a live
``otree.asgi`` router, the INSTALLED / ALREADY / NOT_IMPORTABLE vocabulary, and
the global-lock exemption.

NOT SHARED, and the difference matters: **WHO MAY LOOK AT THE PAGE.** The
dashboard subclasses ``otree.views.cbv.AdminView`` and shape-checks that class's
login machinery before it will install — installing an admin page whose login
check has silently become a no-op is the loud-drift case that check exists for.
``/health`` has NO auth at all, on purpose, because Railway cannot present an
admin cookie. Those are different commitments, not one commitment two callers
happen to share, so the auth check stays in `experimenter_dashboard.py` where
its reason lives. This module knows about ROUTES; it knows nothing about who is
allowed to reach one.

HOW oTree'S ROUTE TABLE WORKS (verified against oTree 6.0.15)
--------------------------------------------------------------
``otree/asgi.py`` builds the Starlette app from ``otree.urls.routes``, a plain
module-level list built by ``get_urlpatterns()`` at import — so a route appended
to that list before ``otree.asgi`` is imported is served exactly like oTree's
own. If ``otree.asgi`` has ALREADY built the app (Starlette's Router does
``list(routes)``), the append must also reach the live router's own list, which
``Router.__call__`` iterates per request; both are done here.

THE ONE DISTINCTION THIS FILE MUST NEVER COLLAPSE
--------------------------------------------------
``otree.urls`` NOT IMPORTABLE YET is an ORDERING FACT and must fail QUIETLY;
``otree.urls`` imported but the wrong SHAPE is VERSION DRIFT and must be LOUD.
CLAUDE.md names collapsing exactly these two — with one ``except Exception``
around both — as a worked example of the bug class this repo hunts, because it
turns a missing guard into something nobody can see. `import_urls` raises for
the first; every drift path below raises ``RuntimeError`` with a message naming
what moved.

INSTALL POINT — WHY BOTH CALLERS INSTALL LATE, FROM ``outro/__init__.py``
--------------------------------------------------------------------------
Importing ``otree.urls`` builds the whole route table, which walks every app's
``page_sequence``, so it cannot be done before every app module is imported.
``otree.urls`` is NOT importable at ``settings.py`` time (identity.py's early
install point) and an attempt there would accomplish nothing. There is no window
to close either way: the routes only need to exist before ``otree.asgi`` builds
the app, which is after every app import on every supported boot path. So both
callers install from the tail of ``outro/__init__.py`` — the last lines of the
last app module — and NEITHER may raise there. See the note at that call site.
"""

import logging

logger = logging.getLogger(__name__)

# The install outcome vocabulary. Shared, so the dashboard and /health cannot
# describe the same three states with two sets of words.
INSTALLED = 'installed'            # newly appended
ALREADY = 'already'                # idempotent no-op
NOT_IMPORTABLE = 'not_importable'  # otree.urls not importable / mid-import


def import_urls():
    """Import oTree's routing module. Separated so the IMPORT failure and the
    SYMBOL checks can be told apart (``identity._import_views`` is the model).

    THE MID-IMPORT CASE IS 'NOT IMPORTABLE': if something imports the app
    modules from INSIDE ``otree.urls``' own ``get_urlpatterns()`` (no supported
    boot path does — ``setup()``'s ``init_orm`` imports the apps first — but a
    bare ``uvicorn otree.asgi:app``, or a plain ``from otree import urls`` in a
    script, does), that module is in ``sys.modules`` WITHOUT its ``routes``
    attribute yet. That is an ordering fact, not drift: fail quiet.

    Raises rather than returning a sentinel, because a caller must not be able
    to use the result without having dealt with the failure.
    """
    from otree import urls
    if not hasattr(urls, 'routes'):
        raise ImportError('otree.urls is mid-import (no routes attribute yet)')
    return urls


def _routes_list(urls, who):
    """oTree's live route table, or a LOUD drift raise.

    ``who`` is the calling install function's dotted name; it leads every
    message so an operator reading a boot log knows which install spoke.
    """
    routes = getattr(urls, 'routes', None)
    if not isinstance(routes, list):
        raise RuntimeError(
            f'{who}: otree.urls.routes is {type(routes).__name__}, not the '
            f'plain module-level list that otree.asgi passes to Starlette '
            f'(verified against oTree 6.0.15). The installed oTree has '
            f'drifted: find where the route table is built now and re-point '
            f'this install at it.')
    return routes


def is_installed(names) -> bool:
    """Are routes carrying any of ``names`` in the table right now?

    NEVER raises — this is the question a test, a pre-launch check or an error
    message asks, and none of them wants an exception for an answer.
    """
    try:
        routes = _routes_list(import_urls(), 'otree_routes.is_installed')
    except Exception:                                          # noqa: BLE001
        return False
    return any(getattr(r, 'name', None) in names for r in routes)


def install(names, build_routes, who, log=None):
    """Append routes to ``otree.urls.routes``. Returns INSTALLED / ALREADY /
    NOT_IMPORTABLE, and RAISES only on VERSION DRIFT.

    ``names``         the route names this caller owns, as a tuple/set. They are
                      the idempotency key AND the correctness check below.
    ``build_routes``  a zero-argument callable returning the Starlette ``Route``
                      objects. A CALLABLE, not a list, so nothing is built on
                      the ALREADY path and so a caller may put its own
                      preconditions (the dashboard's AdminView shape check)
                      inside it, where they run only when an install is really
                      about to happen.
    ``who``           the caller's dotted name, for every message.
    ``log``           optional list; ``(outcome, detail)`` is appended for the
                      quiet paths, so a caller can report what it attempted.

    A caller at boot must catch the drift raise and log it: the feature must
    break, never the boot.
    """
    log = log if log is not None else []
    try:
        urls = import_urls()
    except Exception as exc:                                   # noqa: BLE001
        log.append((NOT_IMPORTABLE, f'{type(exc).__name__}: {exc}'))
        return NOT_IMPORTABLE

    routes = _routes_list(urls, who)

    if any(getattr(r, 'name', None) in names for r in routes):
        log.append((ALREADY, ''))
        return ALREADY

    new_routes = list(build_routes())

    # THE ROUTES MUST BE THE ROUTES THIS CALLER DECLARED. `names` is what
    # idempotency and `is_installed` are decided on, so a route built here
    # under a name not in that tuple is invisible to both: installing twice
    # would append it twice, and `is_installed` would report a working feature
    # as missing. This is an authoring slip in THIS repo rather than oTree
    # drift, and it is silent in exactly the way that matters — so it is raised,
    # which at boot becomes a loud log and a 404 rather than a broken table.
    undeclared = sorted(str(getattr(r, 'name', None)) for r in new_routes
                        if getattr(r, 'name', None) not in names)
    if undeclared:
        raise RuntimeError(
            f'{who}: built route(s) named {undeclared} which are not in the '
            f'declared route-name tuple {sorted(names)}. Add them there — that '
            f'tuple is what idempotency and the installed-check are decided on, '
            f'so a route missing from it installs twice and reports as absent.')

    # NOTHING MAY SHADOW, AND NOTHING MAY BE SHADOWED. Starlette matches the
    # FIRST route whose path matches, so two handlers on one path means the
    # answer depends on install order — and for /health that is a deploy gate
    # reading whichever one happened to be earlier. If oTree itself grows one of
    # our paths, that ambiguity is drift and has to be decided by a human, not
    # papered over by an append.
    taken = {getattr(r, 'path', None) for r in routes}
    clash = sorted(str(getattr(r, 'path', None)) for r in new_routes
                   if getattr(r, 'path', None) in taken)
    if clash:
        raise RuntimeError(
            f'{who}: {clash} is already served in otree.urls.routes under a '
            f'different name. Refusing to install a second handler on the same '
            f'path — whichever matched first would win, silently. Decide which '
            f'one should answer there.')

    routes.extend(new_routes)

    # If the Starlette app was ALREADY built, otree.asgi copied the list before
    # our append (Starlette's Router does list(routes)) — so append to the live
    # router's own list too. Router.__call__ iterates it per request, so this
    # works after construction.
    import sys
    asgi = sys.modules.get('otree.asgi')
    if asgi is not None:
        try:
            live = asgi.app.router.routes
            if not any(getattr(r, 'name', None) in names for r in live):
                live.extend(new_routes)
        except Exception as exc:
            raise RuntimeError(
                f'{who}: otree.asgi is already imported but its '
                f'app.router.routes could not be extended '
                f'({type(exc).__name__}: {exc}). The routes would silently '
                f'404. Starlette/oTree has drifted; re-check otree/asgi.py '
                f'against this install.') from exc

    log.append((INSTALLED, ''))
    return INSTALLED


def exempt_from_global_lock(name, who) -> bool:
    """Ask oTree to run the route called ``name`` OUTSIDE its global request
    lock. Returns True if the exemption was registered.

    WHY ANY ROUTE WOULD WANT THIS. oTree serialises every request behind one
    asyncio lock (``otree.middleware.CommitTransactionMiddleware``), so a health
    poll queues behind whatever participant page is in flight. On a busy session
    that turns a 20ms check into a timeout, a platform health check reads the
    timeout as UNHEALTHY, and the container gets restarted for being BUSY — an
    outage manufactured by its own monitoring. oTree supports exempting a route
    by name (``otree.urls.VIEWS_WITHOUT_LOCK``, present in 6.0.15), so this adds
    to that set and clears the middleware's memoised path prefixes.

    THE DASHBOARD DELIBERATELY DOES NOT USE THIS. Its handlers read a whole
    session's rows and it is explicitly documented as accepting the lock's cost
    (see experimenter_dashboard.py). Running it unlocked would mean an operator
    poll reading half-committed state. Cheap-and-unlocked is a property of the
    endpoint, not of "extra routes", which is why this is a separate call a
    caller makes rather than something ``install`` does.

    BEST-EFFORT BY DESIGN, and this one really is a quiet degrade rather than a
    collapsed distinction: on an oTree without the mechanism the route still
    works, just serialised — which is exactly how it behaved before oTree
    offered the exemption. Nothing is silently disabled; only a latency
    optimisation is declined, and the caller is told so it can say so.

    It must happen BEFORE the first request: oTree computes the path set once,
    lazily, and caches it in ``otree.middleware.PATHS_WITHOUT_LOCK``. Install
    runs at app import, which is before any request; the cache is cleared here
    anyway so a late install (a test, a reload) is not silently un-exempted.
    """
    try:
        from otree import urls as otree_urls
        views_without_lock = getattr(otree_urls, 'VIEWS_WITHOUT_LOCK', None)
        if not isinstance(views_without_lock, set):
            logger.info('[%s] oTree has no VIEWS_WITHOUT_LOCK set; the route '
                        'will run under the global lock', who)
            return False
        views_without_lock.add(name)
        from otree import middleware as otree_middleware
        otree_middleware.PATHS_WITHOUT_LOCK = None      # recompute on next use
        return True
    except Exception as exc:                                   # noqa: BLE001
        logger.info('[%s] could not exempt route %r from the global lock (%s); '
                    'it will run under the lock', who, name, exc)
        return False
