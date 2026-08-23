#!/usr/bin/env python3
"""POST-DEPLOY VERIFICATION — hit the live URL and prove it is the build you
just deployed, or exit non-zero.

    python3 scripts/verify_deploy.py --base-url https://your-study.example \\
        --build-info BUILD_INFO.json      # or --commit <sha> --build-number N

WHY THIS FILE EXISTS
--------------------
Everything else this repo checks, it checks about the SOURCE TREE or a staged
copy: `scripts/prelaunch_check.py` (static config), `scripts/predeploy_check.sh`
(the upgrade path against a copy of the live database),
`scripts/tests/build_context_test.py` (what reaches the image). NOTHING asked
the RUNNING DEPLOYMENT whether it is what you think you just put there — and two
things went wrong for the study this template feeds that only that question
catches:

  * a deploy reported SUCCESS while the container had already exited. The
    platform only ever checked that a port opened.
  * a build went out with its BUILD STAMP SILENTLY MISSING (`railway up` honours
    `.gitignore`, and the stamp is gitignored — see
    `docs/skills_claude/hosting_railway.md`). Everything looked healthy; the
    data simply could not say afterwards which code produced it.

THE ONE PLACE PROVENANCE IS ALLOWED TO FAIL ANYTHING
-----------------------------------------------------
Build provenance is DOCUMENTATION, NEVER A GATE — nothing in `settings.py`, the
boot banner, `/health` or any participant path may fail because a stamp is
missing (DECISIONS.md, 2026-08-23). THIS SCRIPT IS THE SANCTIONED EXCEPTION, and
the reason it is safe to make one here: it is a command a human runs BY HAND
after a deploy, it is not in the application path, and it cannot take a study
down. Comparing the running stamp against the one just deployed is the whole
reason the script exists.

THE ASSERTIONS, AND THE ONE THAT MATTERS MOST
----------------------------------------------
  SERVING       /health answers, with a body that parses as JSON and has the
                shape health.py publishes.
  BUILD_STAMP   *** THE IMPORTANT ONE. *** The RUNNING build's stamp equals the
                commit (and build number) just deployed. It is also what makes
                every other assertion mean anything: without it, a perfect
                result can be a perfect result about the PREVIOUS build — which
                is exactly what a platform that promoted nothing looks like from
                outside.
  ROOM_BINDING  GET /api/rooms reports a session bound to the expected room.
                Read from the REST API and NOT from /health, deliberately, even
                though /health also knows: two independent witnesses, so a bug
                in health.py cannot certify itself.
  ROOM_PAGE     the room URL returns 200 and RENDERS REAL CONTENT — the study's
                own markup, not an error page and not a stub. A stray symlink
                once shipped `_templates` EMPTY and 500'd a live welcome page
                while every source-tree test passed (CLAUDE.md).
  FROZEN_CONFIG the bound session's frozen config, audited against what this
                build ships. DELEGATED, NOT REIMPLEMENTED — see below.
  READY         /health returns 200, the exact verdict a platform healthcheck
                reads. Asserted LAST, so that when a deploy is not ready the
                specific reason is already on screen above it.

FROZEN CONFIG IS DELEGATED TO THE PRE-DEPLOY AUDIT
---------------------------------------------------
`scripts/predeploy_check.audit_frozen_session_configs` is already the one
implementation of "compare a frozen session config against the current
settings", it already carries the TWO-SEVERITY rule (only a MISSING key or a
REPLACE_* placeholder FAILS; every other difference is information, because
`static_version` alone changes on nearly every deploy and a check that fails on
any difference is ignored within a fortnight), and it already carries the one
NAMED exemption. A second implementation here would be the inverted
collapsed-distinction defect CLAUDE.md devotes a section to: one concept, two
implementations, drifting invisibly. So this script gathers the two inputs over
HTTP and hands them to that function, and honours both severities as it returns
them.

Two honest limits of doing it remotely, stated rather than papered over:
  * LIVENESS. The audit's 4th tuple element says whether anybody in a session
    can still reach an ending, which softens a failure to information. It cannot
    be computed over the REST API, and the audit's own rule is that unsure
    counts as LIVE — which is also the truthful answer for the session bound to
    the room right now. So 3-tuples are passed and every finding is live.
  * SCOPE. Only the BOUND session is audited, because it is the only one this
    script can name without walking participant data. Auditing EVERY session is
    `scripts/predeploy_check.sh <copy-of-live-db>`, which runs before the
    deploy, against a database copy, and is not replaced by this.

SAFE TO RUN AGAINST PRODUCTION — THE THREE RULES
-------------------------------------------------
1. **READ-ONLY.** Every request is a GET. There is no code path in this file
   that issues a POST, and `_http_get` is the only way out to the network.
2. **IT NEVER CONSUMES A PARTICIPANT SLOT.** oTree hands a real seat to whoever
   requests the room URL with `?participant_label=...`, and — the part that is
   easy to miss — also to a bare visitor once `?welcome_page_ok=1` is present,
   matching them by COOKIE (otree/views/participant.py: AssignVisitorToRoom). A
   gate that burned a seat on every deploy would eat the sample. So the
   forbidden query keys are refused by `_http_get` ITSELF rather than merely
   avoided by its callers, and REDIRECTS ARE NEVER FOLLOWED — a redirect out of
   the room page is the shape a slot handout takes, so it is reported instead of
   walked into.
3. **IT PRINTS NO PARTICIPANT DATA.** `/api/sessions/<code>` returns every
   participant's label, and a label is a seat number in the lab and a Prolific
   ID online. Only the `config` key is ever read out of that payload, and the
   payload itself is never printed or logged.

WHY IT RETRIES, AND WHAT IT WILL NOT WAIT FOR
-----------------------------------------------
A container still booting is not a failed deploy, and on a fresh database
`scripts/start.sh` can be minutes away from binding a session. So the assertions
are retried against one overall deadline, and a timeout fails with the LAST
thing it saw, named.

WHAT THIS SCRIPT DOES NOT DO. It does not deploy, roll back, restart or bind
anything, and it takes no action on failure beyond saying so and exiting
non-zero. It also does not fail on the pre-launch checklist: /health carries the
BOOT BANNER's subset of it (see health.py), and failing a deploy on a partial
checklist would be a check lying about its own coverage. The names are printed
as information; `scripts/prelaunch_check.py`, run in the launch environment, is
the complete guard and the one that refuses.

EXIT CODES
----------
  0  the live deployment is the build you deployed, and it is serving a study
  1  a named assertion failed (what it saw vs what it wanted, both printed)
  2  this script was called wrong (bad arguments, unreadable --build-info)
  3  this script refused to make a request it considers unsafe — a bug in THIS
     file, not a verdict about the deployment
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_HERE)

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_UNSAFE = 0, 1, 2, 3

REQUEST_TIMEOUT = 20          # seconds, one HTTP call
DEFAULT_DEADLINE = 300        # seconds, the whole verification
DEFAULT_INTERVAL = 5          # seconds between attempts at the same assertion
DEFAULT_ROOM = 'study'        # settings.ROOMS ships exactly this one

HEALTH_PATH = '/health'
ROOMS_PATH = '/api/rooms'
SESSION_CONFIGS_PATH = '/api/session_configs'
SESSION_PATH = '/api/sessions/{code}'
REST_KEY_HEADER = 'otree-rest-key'
REST_KEY_ENV = 'OTREE_REST_KEY'

# RULE 2, ENFORCED AT THE ONE EXIT TO THE NETWORK rather than trusted to
# callers. Any of these in a query string hands out or claims a participant
# slot; `welcome_page_ok` is the non-obvious one (it converts a bare visit into
# a cookie-matched seat).
FORBIDDEN_QUERY_KEYS = ('participant_label', 'welcome_page_ok', 'PROLIFIC_PID')

# WHAT "THE STUDY'S OWN MARKUP" LOOKS LIKE on the room welcome page
# (`_templates/room_welcome.html`, linked directly to base.css). Chosen to be
# things only OUR page has: oTree's stock RoomWelcomePage carries none of them,
# so this distinguishes "the study rendered" from "a framework page rendered",
# which is what an empty template directory produces.
ROOM_PAGE_MARKERS = ('experimental-screen', 'screen-card', 'base.css')
# An HTTP 200 that is actually an error page. oTree renders 500s as HTML.
ROOM_PAGE_FORBIDDEN = ('Server Error', 'Traceback (most recent call last)',
                       'IntegrityError', 'OperationalError')
ROOM_PAGE_MIN_BYTES = 800


class UnsafeRequest(Exception):
    """This script tried to make a request its own rules forbid. A bug HERE."""


# ==========================================================================
# HTTP — one exit to the network, GET only, redirects never followed
# ==========================================================================

class Response:
    def __init__(self, status=None, body='', headers=None, error=''):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.error = error

    @property
    def ok(self):
        return self.status == 200

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:                                      # noqa: BLE001
            return None

    def describe(self):
        if self.error:
            return f'no answer ({self.error})'
        snippet = ' '.join(self.body.split())[:160]
        return f'HTTP {self.status}, {len(self.body)} bytes: {snippet!r}'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are REPORTED, never followed (rule 2)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http_get(base_url, path, rest_key=None, timeout=REQUEST_TIMEOUT):
    """The ONLY way out to the network. GET, no redirects, no unsafe query."""
    parsed = urllib.parse.urlparse(path)
    for key in urllib.parse.parse_qs(parsed.query):
        if key in FORBIDDEN_QUERY_KEYS:
            raise UnsafeRequest(
                f'refusing to request {path!r}: the query key {key!r} makes '
                f'oTree hand this script a participant slot, which would eat '
                f'a seat on every deploy')
    url = f'{base_url}{path}'
    req = urllib.request.Request(url, method='GET')
    if rest_key:
        req.add_header(REST_KEY_HEADER, rest_key)
    try:
        with _OPENER.open(req, timeout=timeout) as fh:
            return Response(fh.status, fh.read().decode('utf-8', 'replace'),
                            dict(fh.headers))
    except urllib.error.HTTPError as exc:
        # A 4xx/5xx is an ANSWER, and its body usually says why.
        return Response(exc.code, exc.read().decode('utf-8', 'replace'),
                        dict(exc.headers or {}))
    except Exception as exc:                                   # noqa: BLE001
        return Response(None, '', {}, error=f'{type(exc).__name__}: {exc}')


# ==========================================================================
# THE ASSERTIONS
# ==========================================================================
# Each takes the run context and returns (passed, saw, wanted). None of them
# raises for a bad answer: a failure is a verdict with words, and an exception
# would lose the words.

class Ctx:
    def __init__(self, args):
        self.base_url = args.base_url.rstrip('/')
        self.room = args.room
        self.commit = (args.commit or '').lower()
        self.build_number = args.build_number
        self.rest_key = args.rest_key
        self.health = None            # last parsed /health body
        self.session_code = None      # from /api/rooms
        self.notes = []               # information, printed at the end

    def get(self, path, rest_key=False, timeout=REQUEST_TIMEOUT):
        return _http_get(self.base_url, path,
                         rest_key=self.rest_key if rest_key else None,
                         timeout=timeout)

    def note(self, line):
        if line not in self.notes:
            self.notes.append(line)


def a_serving(ctx):
    """SERVING — /health answers with the JSON health.py publishes. Every later
    assertion reads the body this caches."""
    resp = ctx.get(HEALTH_PATH)
    ctx.health = None
    wanted = f'a JSON body from {ctx.base_url}{HEALTH_PATH}'
    if resp.error:
        return False, resp.describe(), f'{ctx.base_url}{HEALTH_PATH} to answer at all'
    body = resp.json()
    if body is None:
        if resp.status == 404:
            return False, (
                f'HTTP 404 — nothing serves {HEALTH_PATH} on this deployment'
            ), (f'{wanted}. A 404 here usually means the build now live '
                f'PREDATES the health route, i.e. the deploy never promoted at '
                f'all — the failure this gate exists to catch, so it is not '
                f'skipped')
        return False, resp.describe(), wanted
    if not isinstance(body, dict) or 'build' not in body:
        shape = (sorted(body)[:8] if isinstance(body, dict)
                 else type(body).__name__)
        return False, f'JSON without a "build" key: {shape}', (
            'the /health payload shape from health.py (keys: ok, status, '
            'reasons, database, room, build, prelaunch)')
    ctx.health = body
    return True, f'HTTP {resp.status}, JSON payload from {HEALTH_PATH}', wanted


def a_build_stamp(ctx):
    """BUILD_STAMP — the running build IS the build just deployed. The check the
    inert-stamp bug would have failed, and the one place in this repo where
    provenance is allowed to fail anything."""
    if ctx.health is None:
        return False, 'no /health payload to read the build stamp from', \
            'a /health answer (see SERVING)'
    build = ctx.health.get('build') or {}
    running = build.get('commit') or ''
    running = running.lower() if isinstance(running, str) else ''
    label = build.get('label') or '(no label)'
    wanted = (f'commit {ctx.commit} and build number {ctx.build_number} — the '
              f'commit and build number that were just deployed')
    if not build.get('stamped'):
        return False, (
            f'the running build carries NO stamp ({label}; '
            f'{build.get("problem") or "no BUILD_INFO.json"})'), wanted
    if running != ctx.commit:
        return False, (
            f'the running build is commit {running or "(none)"} ({label}) — '
            f'NOT the one deployed'), wanted
    number = build.get('build_number')
    if ctx.build_number is not None and number != ctx.build_number:
        return False, (
            f'the running build is number {number!r} ({label}) while its '
            f'commit matches — BUILD_INFO.json was written with a mismatched '
            f'pair'), wanted
    return True, f'running {label} (commit {running})', wanted


def a_room_binding(ctx):
    """ROOM_BINDING — /api/rooms says a session is bound to the room. Read from
    the REST API on purpose, so /health is not the only witness."""
    resp = ctx.get(ROOMS_PATH, rest_key=True)
    wanted = (f'GET {ROOMS_PATH} to list room {ctx.room!r} with a non-empty '
              f'session_code, so /room/{ctx.room} is a live link')
    if resp.status == 403:
        return False, (
            f'HTTP 403 from {ROOMS_PATH} — the REST key was rejected or is '
            f'missing (pass --rest-key, or set {REST_KEY_ENV})'), wanted
    if not resp.ok:
        return False, resp.describe(), wanted
    rooms = resp.json()
    if not isinstance(rooms, list):
        return False, (f'{ROOMS_PATH} returned '
                       f'{type(rooms).__name__}, not a list'), wanted
    names = [r.get('name') for r in rooms if isinstance(r, dict)]
    room = next((r for r in rooms
                 if isinstance(r, dict) and r.get('name') == ctx.room), None)
    if room is None:
        return False, f'room {ctx.room!r} is not listed; rooms are {names!r}', \
            wanted
    code = room.get('session_code')
    if not code:
        return False, (
            f'room {ctx.room!r} exists but has NO session bound '
            f'(session_code={code!r}) — /room/{ctx.room} is a dead link'), wanted
    ctx.session_code = code
    return True, f'room {ctx.room!r} is bound to session {code}', wanted


def a_room_page(ctx):
    """ROOM_PAGE — the participant's front door renders the study.

    The BARE room URL, with no query string: with one, oTree hands out a seat
    (rule 2). Redirects are not followed, so a room page that starts redirecting
    is reported rather than walked into."""
    resp = ctx.get(f'/room/{ctx.room}')
    wanted = (f'HTTP 200 from /room/{ctx.room} carrying the study front door '
              f'(markers {", ".join(ROOM_PAGE_MARKERS)})')
    if resp.error:
        return False, resp.describe(), wanted
    if resp.status in (301, 302, 303, 307, 308):
        return False, (
            f'HTTP {resp.status} redirect to '
            f'{resp.headers.get("Location", "(no Location)")!r} — NOT followed: '
            f'a redirect out of the room page is how oTree hands a participant '
            f'a seat, and this gate must not consume one'), wanted
    if resp.status != 200:
        return False, resp.describe(), wanted
    hit = [m for m in ROOM_PAGE_FORBIDDEN if m in resp.body]
    if hit:
        return False, f'HTTP 200 but the body is an error page (contains {hit!r})', \
            wanted
    if len(resp.body) < ROOM_PAGE_MIN_BYTES:
        return False, (
            f'HTTP 200 with only {len(resp.body)} bytes — too small to be the '
            f'rendered page: {resp.describe()}'), wanted
    missing = [m for m in ROOM_PAGE_MARKERS if m not in resp.body]
    if missing:
        return False, (
            f'HTTP 200, {len(resp.body)} bytes, but missing {missing!r} — the '
            f'page rendered without the study\'s own markup (an empty template '
            f'directory or a broken include looks exactly like this)'), wanted
    return True, f'HTTP 200, {len(resp.body)} bytes, all markers present', wanted


def _audit():
    """`scripts/predeploy_check.audit_frozen_session_configs` — imported lazily
    and by path, so this script still runs from anywhere and so a failure to
    import it is a NAMED assertion failure rather than an import-time crash.

    THE ONE THING TAKEN FROM THE LOCAL TREE, and it is deliberate: the audit
    recognises a placeholder through `settings.is_placeholder`, a pure SHAPE
    predicate ("does this value look like an unreplaced `*_REPLACE`?"). That is
    repo convention, not deployment state, and using the shared implementation
    is better than spelling the shape a second time here. Every VALUE being
    compared still comes from the deployment.

    IMPORTING `settings` PRINTS THE LOCAL SERVER'S PRE-LAUNCH BANNER, which in
    the middle of a REMOTE verification reads exactly as if it described the
    deployment — it does not; it describes this checkout. So it is swallowed on
    purpose. The deployment's own checklist arrives through /health and is
    printed, clearly labelled, at the end.
    """
    import contextlib
    import io
    for path in (_HERE, _APP_ROOT):
        if path not in sys.path:
            sys.path.insert(0, path)
    import predeploy_check
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            import settings                                    # noqa: F401
        except Exception:                                      # noqa: BLE001
            # The audit falls back to the same shape rule on its own; a
            # placeholder that cannot be recognised must not read as a real
            # value, which is that fallback's rule too.
            pass
    return predeploy_check.audit_frozen_session_configs


def a_frozen_config(ctx):
    """FROZEN_CONFIG — what participants ACTUALLY get, audited against what this
    build ships, by the pre-deploy audit rather than by a second implementation
    (see the module docstring).

    BOTH SIDES ARE ASKED OF THE DEPLOYMENT, never computed from the local tree:
    the local tree is what we THINK we deployed, and comparing a deployment
    against our belief about it is the error this whole script exists to remove.
    `/api/session_configs` returns the running build's EFFECTIVE configs
    (oTree merges SESSION_CONFIG_DEFAULTS in at import — otree/session.py
    `get_session_configs_dict`), so the audit is handed `defaults={}` and there
    is no second merge here to get wrong.
    """
    wanted = ('the bound session\'s frozen config to carry no key MISSING from '
              'it and no REPLACE_* placeholder, per '
              'predeploy_check.audit_frozen_session_configs')
    if not ctx.session_code:
        return False, 'no bound session to inspect', wanted

    resp = ctx.get(SESSION_CONFIGS_PATH, rest_key=True)
    if not resp.ok:
        return False, f'{SESSION_CONFIGS_PATH}: {resp.describe()}', wanted
    shipped = resp.json()
    if not isinstance(shipped, list):
        return False, (f'{SESSION_CONFIGS_PATH} returned '
                       f'{type(shipped).__name__}, not a list'), wanted

    # RULE 3: this payload also carries every participant's label. Only `config`
    # is read out of it, and neither the payload nor any part of it but the
    # audit's own findings is ever printed.
    resp = ctx.get(SESSION_PATH.format(code=ctx.session_code), rest_key=True)
    if not resp.ok:
        return False, (f'{SESSION_PATH.format(code=ctx.session_code)}: '
                       f'{resp.describe()}'), wanted
    payload = resp.json()
    frozen = (payload or {}).get('config') if isinstance(payload, dict) else None
    if not isinstance(frozen, dict):
        return False, ('the bound session\'s payload carries no `config` '
                       'object'), wanted
    name = frozen.get('name')
    current = {c['name']: dict(c) for c in shipped
               if isinstance(c, dict) and c.get('name')}

    try:
        audit = _audit()
    except Exception as exc:                                   # noqa: BLE001
        return False, (f'could not import the pre-deploy audit '
                       f'({type(exc).__name__}: {exc})'), wanted
    # 3-tuples: liveness is not computable over REST, and the audit's own rule
    # is that unsure counts as LIVE — which is the truthful answer for the
    # session bound to the room right now.
    problems, diffs = audit([(ctx.session_code, name, frozen)], current, {})

    for code, key, frozen_value, current_value in diffs:
        ctx.note(f'frozen config (information, not a failure): session {code} '
                 f'{key} — session has {frozen_value!r}, this build ships '
                 f'{current_value!r}')
    if problems:
        detail = '; '.join(f'{key} {kind} ({extra})'
                           for _code, key, kind, extra in problems)
        return False, (
            f'session {ctx.session_code} (config {name!r}): {detail}. A frozen '
            f'config cannot be repaired by editing settings.py — the session '
            f'has to be RECREATED'), wanted
    return True, (f'session {ctx.session_code} (config {name!r}): no MISSING '
                  f'key and no placeholder; {len(diffs)} value difference(s) '
                  f'reported as information'), wanted


def a_ready(ctx):
    """READY — /health returns 200, the exact verdict a platform healthcheck
    reads. LAST, so an unready deploy has already printed its specific reason."""
    resp = ctx.get(HEALTH_PATH)
    wanted = f'HTTP 200 from {HEALTH_PATH} (status "ready")'
    body = resp.json() or {}
    if resp.status == 200 and body.get('ok'):
        return True, 'HTTP 200, status "ready"', wanted
    reasons = body.get('reasons') or []
    return False, (f'HTTP {resp.status}, status {body.get("status")!r}: '
                   f'{"; ".join(str(r) for r in reasons) or resp.describe()}'), \
        wanted


# (name, function, RETRY?). The third column is the question "can this become
# true on its own while the same build runs?", and it is not decoration:
#
#   RETRY     a container still booting, a platform mid-promotion, or a
#             `scripts/start.sh` still building a session all make these fail
#             for a while and then pass. Waiting is the right answer.
#   NO RETRY  FROZEN_CONFIG is a pure function of the bound session and the
#             running build, and NEITHER changes by itself. Waiting out the
#             deadline to be told the same thing again would only teach whoever
#             runs this to stop running it — the same argument that keeps the
#             pre-launch checklist out of /health's verdict.
ASSERTIONS = [
    ('SERVING', a_serving, True),
    ('BUILD_STAMP', a_build_stamp, True),
    ('ROOM_BINDING', a_room_binding, True),
    ('ROOM_PAGE', a_room_page, True),
    ('FROZEN_CONFIG', a_frozen_config, False),
    ('READY', a_ready, True),
]


def run(ctx, deadline_seconds, interval):
    """Every assertion, in order, each retried against ONE overall deadline.

    Ordered, and stopping at the first failure, on purpose: a deployment that is
    not serving has nothing to say about its build stamp, and printing six
    consequential failures would bury the one that matters.
    """
    deadline = time.time() + deadline_seconds
    for name, fn, retry in ASSERTIONS:
        attempt = 0
        while True:
            attempt += 1
            try:
                passed, saw, want = fn(ctx)
            except UnsafeRequest as exc:
                print(f'  [UNSAFE] {name}: {exc}')
                return EXIT_UNSAFE
            if passed:
                print(f'  [PASS] {name}: {saw}')
                break
            if not retry or time.time() >= deadline:
                print(f'  [FAIL] {name}')
                print(f'         saw:    {saw}')
                print(f'         wanted: {want}')
                if not retry:
                    print('         (not retried: this cannot become true '
                          'while the same build serves the same session)')
                elif attempt > 1:
                    print(f'         (retried for {deadline_seconds}s; this is '
                          f'the last thing it saw)')
                return EXIT_FAILED
            time.sleep(max(0.1, min(interval, deadline - time.time())))
    return EXIT_OK


# ==========================================================================
# ARGUMENTS
# ==========================================================================

def _expected_from_build_info(path):
    """(commit, build_number) from the BUILD_INFO.json that was just deployed.

    Read with THIS repo's own reader (`buildinfo.load`) so the file this script
    compares against is parsed by exactly the code the server parses it with —
    one implementation, so the two cannot disagree about what a stamp says.
    """
    if _APP_ROOT not in sys.path:
        sys.path.insert(0, _APP_ROOT)
    import buildinfo
    info = buildinfo.load(path)
    if not info['stamped']:
        print(f'FATAL: {path} is not a usable stamp: {info["problem"]}')
        print('  This script compares the RUNNING build against the one you '
              'just deployed, so it needs to know which that was. Pass '
              '--commit/--build-number instead, or write the stamp with '
              'scripts/write_build_info.py.')
        sys.exit(EXIT_USAGE)
    return info['commit'], info['build_number']


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Verify a deployment IS the build you just deployed.')
    p.add_argument('--base-url', required=True,
                   help='the deployment, e.g. https://your-study.example')
    p.add_argument('--room', default=DEFAULT_ROOM,
                   help=f'room whose binding is required (default {DEFAULT_ROOM})')
    p.add_argument('--build-info',
                   help='BUILD_INFO.json just deployed; supplies --commit and '
                        '--build-number')
    p.add_argument('--commit', help='the 40-char SHA just deployed')
    p.add_argument('--build-number', type=int,
                   help='the build number just deployed')
    p.add_argument('--rest-key', default=os.environ.get(REST_KEY_ENV),
                   help=f'oTree REST key (default: ${REST_KEY_ENV})')
    p.add_argument('--deadline', type=int, default=DEFAULT_DEADLINE,
                   help=f'seconds to keep retrying (default {DEFAULT_DEADLINE})')
    p.add_argument('--interval', type=int, default=DEFAULT_INTERVAL,
                   help=f'seconds between attempts (default {DEFAULT_INTERVAL})')
    args = p.parse_args(argv)

    if args.build_info:
        commit, number = _expected_from_build_info(args.build_info)
        args.commit = args.commit or commit
        if args.build_number is None:
            args.build_number = number
    if not args.commit:
        p.error('one of --build-info or --commit is required: without a commit '
                'to compare against, the assertion this script exists for '
                'cannot run')
    if _APP_ROOT not in sys.path:
        sys.path.insert(0, _APP_ROOT)
    import buildinfo
    if not buildinfo.is_real_sha(args.commit):
        # THE SAME PREDICATE THE WRITER AND THE READER USE — one implementation,
        # so this cannot demand a shape the stamp would never carry.
        p.error(f'--commit {args.commit!r} is not a 40-character hex SHA')
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    ctx = Ctx(args)
    print(f'VERIFY DEPLOY {ctx.base_url}')
    print(f'  expecting commit {ctx.commit} (build number {ctx.build_number})')
    code = run(ctx, args.deadline, args.interval)

    health = ctx.health or {}
    prelaunch = health.get('prelaunch') or {}
    if prelaunch.get('problems'):
        # INFORMATION, NEVER A FAILURE — see the module docstring. NAMES only;
        # /health does not publish the values and neither does this.
        ctx.note('pre-launch checklist on the running build is NOT clean: '
                 + ', '.join(str(p) for p in prelaunch['problems']))
        ctx.note('  (that is a launch question, not a deploy one — run '
                 'scripts/prelaunch_check.py in the launch environment for the '
                 'complete check; /health carries only the boot banner\'s '
                 'subset)')
    for line in ctx.notes:
        print(f'  [info] {line}')

    if code == EXIT_OK:
        print('VERIFY DEPLOY OK — the live deployment is the build you '
              'deployed, and it is serving a study.')
    elif code == EXIT_UNSAFE:
        print('VERIFY DEPLOY ABORTED — this script refused to make a request '
              'its own safety rules forbid. That is a bug in verify_deploy.py, '
              'not a verdict about the deployment.')
    else:
        print('VERIFY DEPLOY FAILED — see the assertion above. Nothing has '
              'been changed; deciding what to do about a bad deploy is yours.')
    return code


if __name__ == '__main__':
    sys.exit(main())
