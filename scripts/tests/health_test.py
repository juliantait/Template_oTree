#!/usr/bin/env python3
"""THE SHARED ROUTE INSTALLER and the /health ROUTE (otree_routes.py, health.py).

Run: python3 scripts/tests/health_test.py   (boots oTree in-process; no server)
Exit 0 = every check passed.

WHAT THIS FILE IS EVIDENCE OF, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------------------------
`/health` exists so a machine can act on its STATUS CODE, so nearly everything
below is asserted through a real HTTP request against oTree's own ASGI app
(the in-process client), not by calling `health_payload()` and believing it.
The exceptions are the failure modes a live server will not produce on demand —
a database that throws, a rooms table that is unreadable — which are staged
against `health_payload()` directly, and section E says so where it does it.

  A. THE SHARED INSTALLER (otree_routes.py). Both callers installed at boot;
     idempotent; QUIET when otree.urls is not importable; LOUD on drift; the
     two guards that only this module has (a route built under an undeclared
     name, and a path already served by something else); and the boot-time
     wrapper swallowing even the drift raise.
  B. THE VERDICT. 503 with a reason while the room is unbound, 200 once a
     session is bound, back to 503 when it is unbound again — the same process,
     so the flip is the room's doing and not a restart's.
  C. WHAT THE VERDICT MUST NOT DEPEND ON. An unstamped build and a NOT-clean
     pre-launch checklist both ride in the body of a 200. This is the check
     that stops somebody "improving" /health into the gate nobody can pass.
  D. WHAT AN UNAUTHENTICATED ROUTE MAY SAY. No login is needed (the point —
     a platform healthcheck has no cookie), and the body carries the pre-launch
     problem NAMES while containing NO placeholder VALUE anywhere in it. A
     completion code is money; this route is open.
  E. IT CANNOT 500. Every block is broken in turn — the rooms table, the
     database, buildinfo, the settings checklist — and the answer is still a
     503 verdict in the same shape. Paired with the positive each time, so
     "no 500" is never asserted about a route that simply did not run.

THE ABSENCE RULE (CLAUDE.md's testing section) is why D asserts the presence of
the problem NAMES in the same breath as the absence of the VALUES: "the body
does not contain COMP-XXXXXX_REPLACE" is equally true of an empty body, a 404,
and a route that was never installed.
"""
import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# Before boot: oTree freezes AUTH_LEVEL at import. STUDY is the locked-down mode
# a real launch uses, and section D's "no login needed" means nothing unless the
# rest of the admin genuinely does need one — which C1 pins.
os.environ['OTREE_AUTH_LEVEL'] = 'STUDY'

from otree_inprocess import boot  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

import buildinfo                    # noqa: E402
import experimenter_dashboard as ed  # noqa: E402
import health                       # noqa: E402
import otree_routes                 # noqa: E402
import settings                     # noqa: E402

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def bind(session):
    """Bind (or, with None, unbind) the study room, the way start.sh's POST
    does — through oTree's own Room object, so nothing here invents a second
    way to answer "is a session bound?".

    THE COMMIT IS LOAD-BEARING. oTree's request middleware starts a fresh
    identity map per request (NEW_IDMAP_EACH_REQUEST), so an uncommitted
    RoomToSession row is invisible to the very /health request this is staging —
    which reads as "binding a session does not make it ready", i.e. a false
    failure about the feature under test.
    """
    from otree.database import db
    from otree.room import ROOM_DICT
    ROOM_DICT['study'].set_session(session)
    db.commit()


def get_health(client):
    r = client.get(health.URL_PATH)
    try:
        return r.status_code, r.json(), r.text
    except Exception:                                          # noqa: BLE001
        return r.status_code, None, r.text


def main():
    client = ot.client()

    # ------------------------------------------------------------------ A
    section('A. the SHARED installer (otree_routes.py), used by both callers')
    check(health.health_is_installed(),
          '/health installed at boot by outro/__init__.py')
    check(ed.dashboard_is_installed(),
          'and the dashboard is still installed by the same tail — one '
          'installer, two callers, neither displacing the other')
    check(health.install_health_route() == otree_routes.ALREADY,
          'a second /health install is an idempotent no-op (ALREADY)')
    check(health.assert_health_route() == otree_routes.ALREADY,
          'assert_health_route passes when installed')

    from otree import urls as otree_urls
    named = [r for r in otree_urls.routes
             if getattr(r, 'name', None) == health.ROUTE_NAME]
    check(len(named) == 1,
          f'exactly ONE route carries {health.ROUTE_NAME!r} in otree.urls.routes '
          f'after two installs (got {len(named)}) — the idempotency key works')

    # THE GLOBAL-LOCK EXEMPTION, asserted where oTree actually reads it. A
    # health poll queueing behind a participant page is how a busy container
    # gets restarted for being busy (otree_routes.exempt_from_global_lock).
    check(health.ROUTE_NAME in otree_urls.VIEWS_WITHOUT_LOCK,
          'the route is registered in oTree\'s VIEWS_WITHOUT_LOCK')
    check(health.URL_PATH in otree_urls.get_paths_without_lock(),
          f'and oTree resolves that to the path {health.URL_PATH} — asserted '
          f'through oTree\'s OWN resolver, since that is what the middleware '
          f'calls, not through the set we just added to')
    check('/experimenter_dashboard' not in otree_urls.get_paths_without_lock(),
          'the dashboard is NOT exempt — it reads a whole session under the '
          'lock on purpose, so the exemption is per-endpoint, not per-installer')

    # QUIET vs LOUD, the distinction CLAUDE.md names as a worked example. Both
    # staged on the SHARED implementation, because that is where it now lives.
    real_import = otree_routes.import_urls
    otree_routes.import_urls = lambda: (_ for _ in ()).throw(
        ImportError('simulated'))
    try:
        check(health.install_health_route() == otree_routes.NOT_IMPORTABLE,
              'not-importable-yet is QUIET for /health too (returned, not '
              'raised)')
        check(health.health_is_installed() is False,
              'and health_is_installed answers False rather than raising')
    finally:
        otree_routes.import_urls = real_import

    class _Drifted:                     # imported fine, wrong shape
        routes = None
    otree_routes.import_urls = lambda: _Drifted
    try:
        try:
            health.install_health_route()
            check(False, 'version drift raises (LOUD) for /health')
        except RuntimeError as exc:
            check('routes' in str(exc) and 'health' in str(exc),
                  'version drift raises (LOUD), naming both the drifted symbol '
                  'and which install spoke')
        check(health.install_health_route_or_note() == 'drift',
              'the boot-time wrapper swallows even the drift raise (a boot '
              'must never die over a health endpoint)')
    finally:
        otree_routes.import_urls = real_import

    check(health.install_health_route() == otree_routes.ALREADY,
          'and after all that the real route is untouched and still installed')

    # THE TWO GUARDS THAT ARE NEW WITH THE SHARED INSTALLER. Both are silent
    # failures otherwise: a route under an undeclared name installs twice and
    # reports absent, and a shadowed path answers from whichever handler
    # happened to be registered first.
    def _undeclared():
        from starlette.routing import Route
        return [Route('/never_installed_probe', lambda r: None,
                      name='NotInMyRouteNames')]
    try:
        otree_routes.install(('SomethingElse',), _undeclared,
                             'health_test.undeclared_probe')
        check(False, 'a route built under an undeclared name is refused')
    except RuntimeError as exc:
        check('NotInMyRouteNames' in str(exc),
              'a route built under a name outside the declared tuple is '
              'REFUSED, naming it (it would install twice and read as absent)')

    def _shadow():
        from starlette.routing import Route
        return [Route(health.URL_PATH, lambda r: None, name='SecondHealth')]
    try:
        otree_routes.install(('SecondHealth',), _shadow,
                             'health_test.shadow_probe')
        check(False, 'a second handler on an occupied path is refused')
    except RuntimeError as exc:
        check(health.URL_PATH in str(exc),
              f'a second handler on {health.URL_PATH} is REFUSED rather than '
              f'appended — two answers at one path is a deploy gate reading '
              f'whichever matched first')
    check(len([r for r in otree_urls.routes
               if getattr(r, 'path', None) == health.URL_PATH]) == 1,
          'and after both refusals the table still holds exactly one /health')

    # ------------------------------------------------------------------ B
    section('B. the VERDICT: 503 unbound, 200 bound, 503 unbound again')
    bind(None)
    status, body, _ = get_health(client)
    check(status == 503, f'unbound room -> HTTP 503 (got {status})')
    check(body and body.get('status') == 'not_ready' and body.get('ok') is False,
          f'and the body agrees with the status code (ok={body and body.get("ok")}, '
          f'status={body and body.get("status")!r}) — a machine reads the code, '
          f'a human reads the body, and they must not disagree')
    reasons = ' '.join((body or {}).get('reasons') or [])
    check('no session is bound' in reasons and 'study' in reasons,
          f'the reason NAMES the room and what is wrong, in a sentence an '
          f'operator can act on: {reasons[:90]!r}')
    check((body or {}).get('database', {}).get('ok') is True,
          'and it says the DATABASE is fine — "unbound" and "database down" '
          'are different deployments and must not collapse into one 503')

    session = ot.create_session('lab', num_participants=2)
    bind(session)
    status, body, _ = get_health(client)
    check(status == 200, f'a session bound to the room -> HTTP 200 (got {status})')
    check(body.get('ok') is True and body.get('status') == 'ready'
          and body.get('reasons') == [],
          'ready, with no reasons')
    check(body['room'] == dict(name='study', bound=True,
                               session_code=session.code),
          f'and the room block names the bound session ({session.code})')

    bind(None)
    status, _body, _ = get_health(client)
    check(status == 503,
          'unbinding the room flips it back to 503 in the SAME process — so '
          'the verdict tracks the room, not the boot')
    bind(session)

    # THE VERBS. A health endpoint is a read, and the route says so.
    # HEAD is asserted through the ROUTE TABLE rather than through this client:
    # starlette 0.14.1's TestClient rides an old `requests`, which crashes
    # reading a bodyless HEAD response before it can be asserted on. Measured
    # against a real uvicorn prodserver instead — `curl -I /health` answers
    # 200 — and that transcript is in phase2_test_output/health_over_real_http.txt.
    route = next(r for r in otree_urls.routes
                 if getattr(r, 'name', None) == health.ROUTE_NAME)
    check(set(route.methods or ()) >= {'GET', 'HEAD'},
          f'the route declares GET and HEAD (got {sorted(route.methods or ())})')
    check('POST' not in (route.methods or ()),
          'and NOT POST — the write verbs never reach the handler at all')
    check(client.post(health.URL_PATH).status_code == 405,
          'POST really is 405 over HTTP (Starlette enforces it at the Route, '
          'which is why health.py carries no method check of its own)')

    # ------------------------------------------------------------------ C
    section('C. what the verdict must NOT depend on')
    status, body, _ = get_health(client)
    check(status == 200 and body['build']['stamped'] is False,
          'an UNSTAMPED build is 200: provenance is documentation, never a '
          'gate (this run has no BUILD_INFO.json, which is the normal state)')
    check(body['build']['label'] == 'unstamped build'
          and body['build']['problem'],
          f'and the body still says so honestly, with the reason '
          f'({body["build"]["label"]!r})')
    check(status == 200 and body['prelaunch']['clean'] is False
          and body['prelaunch']['problems'],
          f'a NOT-clean pre-launch checklist is also 200 '
          f'({len(body["prelaunch"]["problems"])} problems reported) — a build '
          f'running testing values is a healthy deployment, and a check that '
          f'503d on that is the check everybody disables')

    # THE PAIRED POSITIVE for "the stamp does not change the verdict": with a
    # real stamp the verdict is the same 200 and the block finally carries a
    # SHA, so the two checks together say the stamp is read and ignored rather
    # than not read at all.
    stamp_path = os.path.join(ot.tmpdir, 'BUILD_INFO_probe.json')
    with open(stamp_path, 'w') as fh:
        json.dump(dict(commit='a' * 40, commit_short='aaaaaaa',
                       commit_date='2026-08-23T10:00:00+02:00',
                       subject='probe', build_number=137,
                       built_at='2026-08-23T10:05:00+02:00',
                       tree_clean=True), fh)
    real_build_info = buildinfo.BUILD_INFO
    buildinfo.BUILD_INFO = buildinfo.load(stamp_path)
    try:
        status, body, _ = get_health(client)
        check(status == 200 and body['build']['stamped'] is True
              and body['build']['commit'] == 'a' * 40
              and body['build']['build_number'] == 137,
              'a STAMPED build is the same 200, and the block now carries the '
              'commit and build number verify_deploy compares against')
    finally:
        buildinfo.BUILD_INFO = real_build_info

    # ------------------------------------------------------------------ D
    section('D. what an unauthenticated route may say')
    # THE PAIRED PRESENCE: /health being reachable without a login means
    # nothing unless the admin genuinely requires one in this process.
    admin = client.get('/experimenter_dashboard', allow_redirects=False)
    check(admin.status_code in (302, 303, 307),
          f'AUTH_LEVEL=STUDY really is in force — the dashboard redirects an '
          f'anonymous request to login (got {admin.status_code})')
    status, body, raw = get_health(client)
    check(status == 200,
          'and /health answers that SAME anonymous client 200 — no cookie, no '
          'REST key, which is the point: a platform healthcheck has neither')

    names = body['prelaunch']['problems']
    check(any('prolific_cc_code' in n for n in names),
          f'the checklist NAMES are published, so an operator knows where to '
          f'look (e.g. {next((n for n in names if "prolific_cc_code" in n), None)!r})')
    # ...and the VALUES are not. A completion code is what a participant submits
    # to be paid; it is worth money to whoever finds it, and this route is open.
    leaked = [v for v in settings.PROLIFIC_CODE_PLACEHOLDERS if v in raw]
    check(not leaked,
          f'and NO placeholder VALUE appears anywhere in the body (leaked='
          f'{leaked}) — names tell an operator what to fix and an outsider '
          f'nothing they could use')
    check(all(isinstance(n, str) for n in names),
          'every reported problem is a plain string, so no tuple can smuggle '
          'a value through as a repr')
    # NOTHING ABOUT PARTICIPANTS, asserted as a CLOSED key set rather than by
    # hunting for words: `"label"` occurs in the build block quite innocently,
    # and a substring hunt both false-alarms on that and would miss a key
    # nobody thought to search for. A closed set fails on ANY new key, which is
    # the point — the next person adding one to an open route has to come here
    # and say it is safe to publish.
    check(set(body) == {'ok', 'status', 'reasons', 'database', 'room', 'build',
                        'prelaunch'},
          f'the body is exactly the seven declared blocks, nothing else '
          f'(got {sorted(body)}) — no participant count, label, payoff or '
          f'anything else can arrive on this open route unnoticed')
    check(set(body['room']) == {'name', 'bound', 'session_code'},
          f'and the room block is only the room and its session code, both of '
          f'which a participant already sees (got {sorted(body["room"])})')

    # ------------------------------------------------------------------ E
    section('E. it cannot 500 — every block broken in turn')
    # STAGED AGAINST health_payload() DIRECTLY, deliberately: a live server will
    # not produce an unreadable rooms table or a database that throws on demand,
    # and the point of splitting the payload out of the route was to make these
    # drivable at all. The route itself is exercised over HTTP everywhere above.
    payload, status = health.health_payload()
    check(status == 200 and payload['ok'],
          'baseline: the real payload is ready (the paired positive, without '
          'which every "still answers" below is a statement about nothing)')

    def broken(*_a, **_k):
        raise RuntimeError('simulated failure')

    for name, attr in (('the rooms lookup', '_room_name'),
                       ('the room/database read', '_room_block')):
        real = getattr(health, attr)
        setattr(health, attr, broken)
        try:
            payload, status = health.health_payload()
            check(status == 503 and payload['ok'] is False,
                  f'{name} raising -> a 503 VERDICT, not an exception')
            check(any('simulated failure' in str(r) or 'RuntimeError' in str(r)
                      for r in payload['reasons']),
                  f'  ...and the reason names what actually broke: '
                  f'{payload["reasons"]}')
            check(set(payload) == {'ok', 'status', 'reasons', 'database',
                                   'room', 'build', 'prelaunch'},
                  '  ...in the SAME shape, so no reader needs a branch for it')
        finally:
            setattr(health, attr, real)

    real_current = buildinfo.current
    buildinfo.current = broken
    try:
        payload, status = health.health_payload()
        check(status == 200 and payload['build']['stamped'] is False
              and 'RuntimeError' in str(payload['build']['problem']),
              'buildinfo raising costs the BUILD BLOCK only — the verdict is '
              'still 200, because provenance may not decide health')
    finally:
        buildinfo.current = real_current

    real_problems = settings._prelaunch_problems
    settings._prelaunch_problems = broken
    try:
        payload, status = health.health_payload()
        check(payload['prelaunch']['clean'] is False
              and payload['prelaunch']['problems'],
              'a checklist that CANNOT RUN reports clean=False with a reason — '
              'never clean=True with an empty list, which would be '
              'indistinguishable from a genuinely clean launch')
        check(status == 200,
              'and that still does not change the verdict')
    finally:
        settings._prelaunch_problems = real_problems

    status, body, _ = get_health(client)
    check(status == 200 and body['ok'],
          'after every one of those, the real route is healthy again over HTTP')

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
