#!/usr/bin/env python3
"""THE POST-DEPLOY GATE (scripts/verify_deploy.py), driven as a real subprocess.

Run: python3 scripts/tests/verify_deploy_test.py
Exit 0 = every check passed. Boots no oTree, touches no database, and needs
nothing but the standard library — which is deliberate: this is the check you
want to be able to run on a deploy box.

WHY A STUB SERVER RATHER THAN A REAL oTree
--------------------------------------------
`verify_deploy.py` exists to catch a DEPLOYMENT THAT IS WRONG, and a healthy
oTree will not be wrong on demand. The states that matter here — a 404 at
/health because the build now live predates the route, a running build stamped
with somebody else's commit, a room page that returns 200 and renders an error,
a room page that redirects (the shape a participant-slot handout takes) — cannot
be staged on a real server without breaking it. So the assertions are driven
against a programmable stub that answers exactly those bodies, and the script is
run AS A SUBPROCESS, so what is measured is its real exit code and its real
output, not a function call.

This is the same division Phase 3 used for `start.sh`: the stub proves the
decisions, and a transcript against a REAL oTree prodserver
(`_ai/build_provenance/phase2_test_output/verify_deploy_live.txt`) proves the
two halves agree about a real deployment.

THE GREEN PATH IS ASSERTED FIRST AND RE-ASSERTED AT THE END. Every red case
below is one field changed from that green baseline, so a case that goes red
for some unrelated reason (a stub that stopped answering, a script that cannot
start) cannot be mistaken for the assertion working — CLAUDE.md's rule that an
absence is only evidence when paired with the matching presence.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

VERIFY = os.path.join(REPO_ROOT, 'scripts', 'verify_deploy.py')

COMMIT = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
OTHER_COMMIT = '0' * 40
BUILD_NUMBER = 137
ROOM = 'study'
SESSION = 'k9zz0jnc'
REST_KEY = 'stub-rest-key'

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# ==========================================================================
# THE STUB DEPLOYMENT
# ==========================================================================
# One mutable `STATE` dict decides every answer, so a red case is literally one
# field different from the green baseline and the diff is visible in the test.

def green_state():
    return dict(
        health_status=200,
        health_body=dict(
            ok=True, status='ready', reasons=[],
            database=dict(ok=True, error=''),
            room=dict(name=ROOM, bound=True, session_code=SESSION),
            build=dict(stamped=True, commit=COMMIT, commit_short=COMMIT[:7],
                       build_number=BUILD_NUMBER, built_at='2026-08-23T10:05:00',
                       label=f'build {BUILD_NUMBER} · {COMMIT[:7]}',
                       problem=None),
            prelaunch=dict(clean=True, problems=[]),
        ),
        rooms=[dict(name=ROOM, session_code=SESSION, url='/room/study')],
        # A body long enough and marked enough to be the real front door.
        room_page=('<!DOCTYPE html><html><head>'
                   '<link rel="stylesheet" href="/static/global/css/base.css">'
                   '</head><body><div class="experimental-screen">'
                   '<div class="screen-card">' + ('x' * 1200) +
                   '</div></div></body></html>'),
        room_page_status=200,
        room_page_headers=None,
        session_configs=[dict(name='lab', num_participants=6,
                              real_world_currency_per_point=1)],
        frozen_config=dict(name='lab', num_participants=6,
                           real_world_currency_per_point=1),
        require_rest_key=True,
        seen=[],           # every path requested, so rule 2 can be asserted
    )


STATE = green_state()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass                                   # silence; the test prints

    def _send(self, status, body, content_type='application/json',
              headers=None):
        raw = body if isinstance(body, bytes) else str(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload))

    def do_GET(self):                          # noqa: N802 (stdlib name)
        path = self.path
        STATE['seen'].append(path)
        has_key = self.headers.get('otree-rest-key') == REST_KEY

        if path == '/health':
            status = STATE['health_status']
            if status == 404:
                return self._send(404, 'Not Found', 'text/plain')
            body = STATE['health_body']
            return self._send(status, body if isinstance(body, str)
                              else json.dumps(body))

        if STATE['require_rest_key'] and path.startswith('/api/') and not has_key:
            return self._send(403, 'forbidden', 'text/plain')

        if path == '/api/rooms':
            return self._json(200, STATE['rooms'])
        if path == '/api/session_configs':
            return self._json(200, STATE['session_configs'])
        if path.startswith('/api/sessions/'):
            # The real payload also carries every participant's label; the stub
            # includes some so section E can assert the script never prints it.
            return self._json(200, dict(
                code=SESSION, config=STATE['frozen_config'],
                participants=[dict(code='pppppppp', label='SECRET_LABEL_007')]))
        if path.startswith(f'/room/{ROOM}'):
            return self._send(STATE['room_page_status'], STATE['room_page'],
                              'text/html', STATE['room_page_headers'])
        return self._send(404, 'Not Found', 'text/plain')

    def do_POST(self):                         # noqa: N802
        STATE['seen'].append(f'POST {self.path}')
        self._send(405, 'no', 'text/plain')


def run_verify(*extra, expect_key=True):
    """Run the REAL script as a subprocess. Returns (exit_code, output)."""
    env = dict(os.environ)
    if expect_key:
        env['OTREE_REST_KEY'] = REST_KEY
    else:
        env.pop('OTREE_REST_KEY', None)
    argv = [sys.executable, VERIFY, '--base-url', BASE_URL,
            '--deadline', '2', '--interval', '1',
            '--commit', COMMIT, '--build-number', str(BUILD_NUMBER), *extra]
    proc = subprocess.run(argv, capture_output=True, text=True, env=env,
                          timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    global STATE
    section('A. the GREEN path — a deployment that IS the build we deployed')
    STATE = green_state()
    code, out = run_verify()
    check(code == 0, f'exit 0 (got {code})')
    check('VERIFY DEPLOY OK' in out, 'and it says so')
    for name in ('SERVING', 'BUILD_STAMP', 'ROOM_BINDING', 'ROOM_PAGE',
                 'FROZEN_CONFIG', 'READY'):
        check(f'[PASS] {name}' in out, f'  {name} passed')

    section('B. BUILD_STAMP — the assertion the whole script exists for')
    STATE = green_state()
    STATE['health_body']['build'].update(
        stamped=True, commit=OTHER_COMMIT, commit_short=OTHER_COMMIT[:7],
        label=f'build {BUILD_NUMBER} · {OTHER_COMMIT[:7]}')
    code, out = run_verify()
    check(code == 1 and '[FAIL] BUILD_STAMP' in out,
          f'a deployment serving ANOTHER commit fails (exit {code})')
    check('NOT the one deployed' in out and OTHER_COMMIT in out,
          'naming the commit it actually found — the "platform promoted '
          'nothing" case')

    STATE = green_state()
    STATE['health_body']['build'].update(
        stamped=False, commit=None, commit_short='', build_number=None,
        label='unstamped build', problem='no BUILD_INFO.json')
    code, out = run_verify()
    check(code == 1 and '[FAIL] BUILD_STAMP' in out
          and 'carries NO stamp' in out,
          f'an UNSTAMPED deployment fails, named as such (exit {code}) — this '
          f'is the gitignored-stamp trap, and the ONE place provenance is '
          f'allowed to fail anything')

    STATE = green_state()
    STATE['health_body']['build']['build_number'] = 999
    code, out = run_verify()
    check(code == 1 and 'mismatched pair' in out,
          'a matching commit with the WRONG build number fails as a mismatched '
          'pair, rather than passing on the commit alone')

    section('C. SERVING / READY — the deployment is not there, or not ready')
    STATE = green_state()
    STATE['health_status'] = 404
    code, out = run_verify()
    check(code == 1 and '[FAIL] SERVING' in out and 'PREDATES' in out,
          'a 404 at /health fails and explains that the live build predates '
          'the route — it is NOT skipped as "no health endpoint here"')

    STATE = green_state()
    STATE['health_body'] = 'this is not json'
    code, out = run_verify()
    check(code == 1 and '[FAIL] SERVING' in out,
          'a 200 that is not JSON fails too (a proxy error page answers 200)')

    STATE = green_state()
    STATE['health_status'] = 503
    STATE['health_body'].update(
        ok=False, status='not_ready',
        reasons=['no session is bound to room \'study\''])
    STATE['rooms'] = [dict(name=ROOM, session_code=SESSION)]
    code, out = run_verify()
    check(code == 1 and '[FAIL] READY' in out,
          'a 503 from /health fails at READY — the exact verdict a platform '
          'healthcheck reads')
    check(out.index('[PASS] BUILD_STAMP') < out.index('[FAIL] READY'),
          'and READY is asserted LAST, so the specific reason is already on '
          'screen above it')

    section('D. ROOM_BINDING and ROOM_PAGE — the participant front door')
    STATE = green_state()
    STATE['rooms'] = [dict(name=ROOM, session_code=None)]
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_BINDING' in out and 'dead link' in out,
          'an UNBOUND room fails, read from /api/rooms and not from /health — '
          'two witnesses, so a bug in health.py cannot certify itself')

    STATE = green_state()
    STATE['health_body']['room'] = dict(name=ROOM, bound=True,
                                        session_code=SESSION)
    STATE['rooms'] = [dict(name=ROOM, session_code=None)]
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_BINDING' in out,
          'and it fails EVEN THOUGH /health claims the room is bound — which '
          'is the whole reason the second witness exists')

    STATE = green_state()
    STATE['room_page'] = '<html><body>Server Error</body></html>' + 'x' * 1200
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_PAGE' in out and 'error page' in out,
          'an HTTP 200 whose body is an error page fails')

    STATE = green_state()
    STATE['room_page'] = '<html><body>ok</body></html>'
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_PAGE' in out and 'too small' in out,
          'a 200 too small to be the rendered page fails')

    STATE = green_state()
    STATE['room_page'] = '<html><body>' + ('x' * 1200) + '</body></html>'
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_PAGE' in out
          and 'without the study' in out,
          'a big 200 MISSING the study\'s own markup fails — an empty template '
          'directory looks exactly like this (it shipped once, on a real study)')

    STATE = green_state()
    STATE['room_page_status'] = 302
    STATE['room_page_headers'] = {'Location': '/InitializeParticipant/xyz'}
    code, out = run_verify()
    check(code == 1 and '[FAIL] ROOM_PAGE' in out and 'NOT followed' in out,
          'a REDIRECT out of the room page fails and is NOT followed — that is '
          'the shape a participant-slot handout takes')

    section('E. safe against production')
    STATE = green_state()
    code, out = run_verify()
    unsafe = [p for p in STATE['seen']
              if any(k in p for k in ('participant_label', 'welcome_page_ok',
                                      'PROLIFIC_PID'))]
    check(code == 0 and not unsafe,
          f'a whole green run requested nothing that consumes a slot '
          f'(unsafe={unsafe})')
    check(not any(p.startswith('POST ') for p in STATE['seen']),
          f'and issued no POST of any kind — every request is a GET '
          f'({len([p for p in STATE["seen"] if p.startswith("POST ")])} POSTs)')
    check('SECRET_LABEL_007' not in out,
          'the participant label the session payload carries is NEVER printed, '
          'even though the script reads that payload for its config')

    # THE REFUSAL IS IN `_http_get` ITSELF, not merely in its callers: a caller
    # that one day builds a URL with a label must be stopped by the transport.
    # The stub is told to LIST that room, so ROOM_BINDING passes and the run
    # actually reaches the request that has to be refused — otherwise this would
    # "pass" on an unrelated failure two assertions earlier.
    weird = f'{ROOM}?participant_label=SEAT01'
    STATE = green_state()
    STATE['rooms'] = [dict(name=weird, session_code=SESSION)]
    code, out = run_verify('--room', weird)
    check('[PASS] ROOM_BINDING' in out,
          '  (the run really did get as far as the room page request)')
    check(code == 3 and 'UNSAFE' in out,
          f'and a request carrying participant_label is REFUSED by the '
          f'transport with its own exit code 3 — "a bug in this file, not a '
          f'verdict about the deployment" (exit {code})')

    section('F. FROZEN_CONFIG — delegated to the pre-deploy audit')
    STATE = green_state()
    del STATE['frozen_config']['real_world_currency_per_point']
    code, out = run_verify()
    check(code == 1 and '[FAIL] FROZEN_CONFIG' in out and 'MISSING' in out,
          'a key MISSING from the bound session\'s frozen config fails, with '
          'the audit\'s own vocabulary')
    check('RECREATED' in out,
          'and says the remedy is to RECREATE the session — a frozen config '
          'cannot be repaired by editing settings.py')
    check('not retried' in out,
          'and it is NOT retried: it cannot become true while the same build '
          'serves the same session, and waiting out the deadline would only '
          'teach people to stop running the gate')

    STATE = green_state()
    STATE['frozen_config']['prolific_cc_code'] = 'COMP-XXXXXX_REPLACE'
    STATE['session_configs'][0]['prolific_cc_code'] = 'COMP-A1B2C3'
    code, out = run_verify()
    check(code == 1 and 'PLACEHOLDER' in out,
          'a live session still carrying a REPLACE_* completion code fails — '
          'the case prelaunch_check CANNOT see, because settings.py is already '
          'correct')

    STATE = green_state()
    STATE['frozen_config']['num_participants'] = 4
    code, out = run_verify()
    check(code == 0 and 'information, not a failure' in out,
          'a plain VALUE difference is reported as information and does NOT '
          'fail — the two-severity rule, inherited from the audit rather than '
          'restated here')

    STATE = green_state()
    STATE['frozen_config'].pop('build_at_creation', None)
    STATE['session_configs'][0]['build_at_creation'] = dict(
        commit=None, commit_short='', build_number=None, built_at='',
        stamped=False)
    code, out = run_verify()
    check(code == 0 and 'EXEMPT' in out and 'build_at_creation' in out,
          'and a session created BEFORE build stamping existed passes, with '
          'the named exemption shown rather than silently skipped — provenance '
          'never fails anything (DECISIONS.md)')

    section('G. the green path still passes at the end')
    STATE = green_state()
    code, out = run_verify()
    check(code == 0 and 'VERIFY DEPLOY OK' in out,
          'so every red case above was the field that was changed, not the '
          'harness falling over')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 0), _Handler)
    BASE_URL = f'http://127.0.0.1:{server.server_address[1]}'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        rc = main()
    finally:
        server.shutdown()
    sys.exit(rc)
