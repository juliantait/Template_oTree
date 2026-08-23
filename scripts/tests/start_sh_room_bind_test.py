#!/usr/bin/env python3
"""scripts/start.sh — the room binding, its two timeout classes, and the orphan.

WHAT THIS DRIVES. The real `scripts/start.sh`, as a subprocess, against a stub
oTree REST server that answers `/api/rooms` and `POST /api/sessions`. Nothing is
re-implemented and nothing is read: the assertions are on the script's exit
status, on what it printed, and — the one that matters most — on HOW MANY
`POST /api/sessions` requests the server actually received.

WHY A STUB AND NOT A REAL OTREE SERVER. Two of the four interesting cases are
about a server that is SLOW or that answers and is not heard, and neither can be
staged against a real oTree: you cannot ask a real `create_session` to take
exactly three seconds, or to bind the room and then withhold its reply. A stub
can, and the thing under test here is the script's behaviour when it is treated
that way. `room_gate_test.py` covers the real REST creation path (in-process,
through oTree itself), and a lab run exercises the happy path daily.

THE FOUR PROPERTIES, and the failure each one is about:

  1. AN EXISTING BINDING IS REUSED AND NO POST IS SENT. The reuse rule is the
     whole reason this script exists: a second session bound over a live one
     strands every participant already mid-experiment, because the room now
     points somewhere their links do not. Asserted on the server's POST COUNT,
     not on the wording — "reusing it" printed while a POST went out anyway is
     exactly the bug the message would hide.

  2. THE TWO TIMEOUT CLASSES ARE GENUINELY SEPARATE. A creation that takes
     longer than the READ timeout must still succeed. This is the ported lesson
     from exp_pilots, where a 220-seat session creation ran through the same
     15-second timeout as the millisecond health checks, a slow SUCCESS was read
     as a failure, and the container exited. Driven here by making the read
     timeout SHORTER than the creation actually takes, so a script that shared
     one timeout fails this and a script with two classes passes it.

  3. A CLIENT TIMEOUT IS NOT PROOF THE POST FAILED. The server binds the room
     and then withholds its reply past the client's patience — the exp_pilots
     ORPHAN SESSION, exactly. The script must re-read the room, find the
     binding, keep it, and exit 0 having sent EXACTLY ONE POST. A retry that
     does not re-check binds a second session over a good one.

  4. A REAL FAILURE IS STILL FATAL. The re-read must not become a way of
     passing: when creation fails AND the room is still unbound, the script
     exits non-zero and says so. Property 3 without this one would be a script
     that never reports anything.

  Plus: a hung read is bounded (the script cannot wait forever), an unreachable
  server fails fast, and the missing-REST-key refusal still refuses before any
  request is made.

Run:  python3 scripts/tests/start_sh_room_bind_test.py
No oTree, no database, no browser — a stdlib HTTP server, bash and curl. Takes
about fifteen seconds, most of it deliberate sleeping.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402

START_SH = os.path.join(REPO_ROOT, 'scripts', 'start.sh')
ROOM = 'study'

FAILURES = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        FAILURES.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# ---------------------------------------------------------------------------
# The stub oTree REST server
# ---------------------------------------------------------------------------
class Stub:
    """Just enough of oTree's REST API for start.sh, plus the ability to be slow.

    `bound_code` is the room's binding, which is the single piece of state the
    script reads and writes. `posts` is what the assertions are really made
    against: it is the only way to tell "reused the session" from "said it was
    reusing the session".
    """

    def __init__(self):
        self.bound_code = None          # None = room exists, nothing bound
        self.posts = []                 # one entry per POST /api/sessions
        self.reads = 0
        self.rest_keys_seen = []
        self.require_key = None         # set to a string to demand the header
        self.create_mode = 'ok'         # 'ok' | 'error' | 'no_code'
        self.bind_after = 0.0           # bind the room this long into the POST
        self.respond_after = 0.0        # ...and answer this long into it
        self.hang_reads = 0.0           # make GET /api/rooms take this long
        self.next_code = 'sess0001'
        self.httpd = None
        self.port = None

    def start(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):          # keep the test output readable
                pass

            def _json(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # The client gave up. THIS IS THE ORPHAN CASE and it is not
                    # an error here: the server did its work either way.
                    pass

            def _auth_ok(self):
                key = self.headers.get('otree-rest-key')
                stub.rest_keys_seen.append(key)
                if stub.require_key is None:
                    return True
                if key == stub.require_key:
                    return True
                self._json(401, {'detail': 'bad rest key'})
                return False

            def do_GET(self):
                if not self.path.startswith('/api/rooms'):
                    return self._json(404, {'detail': 'not found'})
                if not self._auth_ok():
                    return
                stub.reads += 1
                if stub.hang_reads:
                    time.sleep(stub.hang_reads)
                self._json(200, [{'name': ROOM,
                                  'session_code': stub.bound_code}])

            def do_POST(self):
                if not self.path.startswith('/api/sessions'):
                    return self._json(404, {'detail': 'not found'})
                if not self._auth_ok():
                    return
                length = int(self.headers.get('Content-Length') or 0)
                raw = self.rfile.read(length) if length else b'{}'
                try:
                    stub.posts.append(json.loads(raw))
                except ValueError:
                    stub.posts.append({'unparsed': raw.decode('utf-8', 'replace')})
                if stub.create_mode == 'error':
                    return self._json(500, {'detail': 'boom'})
                code = stub.next_code
                if stub.bind_after:
                    time.sleep(stub.bind_after)
                # The room is bound BEFORE the reply goes out — which is what
                # makes an unheard reply an orphan rather than a no-op.
                stub.bound_code = code
                if stub.respond_after:
                    time.sleep(stub.respond_after)
                if stub.create_mode == 'no_code':
                    return self._json(200, {'detail': 'created, but no code'})
                self._json(200, {'code': code})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()


def run_start(base_url, env=None, timeout=120):
    """Run the REAL scripts/start.sh and hand back (rc, stdout+stderr, seconds)."""
    environ = dict(os.environ)
    environ['OTREE_BASE_URL'] = base_url
    environ['OTREE_ROOM'] = ROOM
    environ.update(env or {})
    started = time.time()
    proc = subprocess.run(['bash', START_SH], env=environ, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (proc.returncode,
            proc.stdout.decode('utf-8', 'replace'),
            time.time() - started)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
def main():
    check(os.path.exists(START_SH), f'{START_SH} exists')

    # ------------------------------------------------------------------
    section('1. an existing binding is REUSED, and no POST is sent')
    stub = Stub().start()
    try:
        stub.bound_code = 'live0001'
        rc, out, _ = run_start(stub.base)
        check(rc == 0, f'exit 0 (got {rc})')
        check('reusing it' in out,
              f'says it is reusing the live session ({out.strip().splitlines()[-1:]})')
        check('live0001' in out, 'and names the session it found')
        # THE assertion. A script that printed the right thing and posted anyway
        # would strand every participant already holding a link to live0001.
        check(stub.posts == [],
              f'NO session was created ({len(stub.posts)} POST(s) reached the '
              f'server)')
        check(stub.bound_code == 'live0001',
              'the room is still bound to the session it was bound to')

        # ------------------------------------------------------------------
        section('2. the two timeout CLASSES are separate — a slow creation still wins')
        # The creation takes 3s. The READ timeout is 1s. A script with ONE
        # timeout — the exp_pilots bug — fails here; two classes pass.
        stub.bound_code = None
        stub.posts = []
        stub.next_code = 'slow0002'
        stub.bind_after = 0.0
        stub.respond_after = 3.0
        rc, out, secs = run_start(stub.base, {
            'OTREE_START_READ_TIMEOUT': '1',
            'OTREE_START_CREATE_TIMEOUT': '30',
        })
        check(rc == 0,
              f'exit 0 for a creation that took 3s under a 1s READ timeout '
              f'(got {rc}) — the classes did not share a value')
        check(len(stub.posts) == 1,
              f'exactly one session was created ({len(stub.posts)})')
        check('slow0002' in out and stub.bound_code == 'slow0002',
              'and the room is bound to it')
        check(secs >= 3, f'the run really did wait for it ({secs:.1f}s)')

        # ------------------------------------------------------------------
        section('3. THE ORPHAN — a client timeout is not proof the POST failed')
        # The server binds the room, then withholds its reply for longer than
        # the client will wait. This is exp_pilots' crash, staged.
        stub.bound_code = None
        stub.posts = []
        stub.next_code = 'orphan03'
        stub.bind_after = 0.2
        stub.respond_after = 6.0
        rc, out, secs = run_start(stub.base, {
            'OTREE_START_READ_TIMEOUT': '10',
            'OTREE_START_CREATE_TIMEOUT': '2',
        })
        check(rc == 0,
              f'exit 0 — the room IS bound, so this is not a failure (got {rc})')
        check('CLIENT TIMEOUT' in out,
              'the log names the client timeout rather than claiming the server '
              'refused')
        check('orphan03' in out and 'NO second session' in out,
              'it reports the session the server really created, and says it '
              'created no second one')
        # THE assertion this whole case exists for.
        check(len(stub.posts) == 1,
              f'EXACTLY ONE POST reached the server ({len(stub.posts)}) — a '
              f'retry without a re-read would have bound a second session over '
              f'a good one')
        check(stub.bound_code == 'orphan03',
              'the binding that survived is the server\'s, untouched')

        # ------------------------------------------------------------------
        section('4. a REAL failure is still FATAL — the re-read is not an escape')
        stub.bound_code = None
        stub.posts = []
        stub.create_mode = 'error'
        stub.bind_after = stub.respond_after = 0.0
        rc, out, _ = run_start(stub.base, {'OTREE_START_CREATE_TIMEOUT': '10'})
        check(rc != 0, f'non-zero exit (got {rc})')
        check('FATAL' in out and 'still unbound' in out,
              'it says the room is still unbound rather than passing quietly')
        check(stub.bound_code is None,
              'and nothing was bound')
        stub.create_mode = 'ok'

        # ------------------------------------------------------------------
        section('4b. a reply that parses to no code takes the same re-read path')
        # "No code came back" is a fact about the RESPONSE. Here the server did
        # bind the room, so the honest answer is the binding, not a failure.
        stub.bound_code = None
        stub.posts = []
        stub.create_mode = 'no_code'
        stub.next_code = 'nocode04'
        rc, out, _ = run_start(stub.base, {'OTREE_START_CREATE_TIMEOUT': '10'})
        check(rc == 0, f'exit 0 (got {rc})')
        check('nocode04' in out and len(stub.posts) == 1,
              f'the room\'s real binding is found and reported, from one POST '
              f'({len(stub.posts)})')
        stub.create_mode = 'ok'

        # ------------------------------------------------------------------
        section('5. a hung read is BOUNDED — the script cannot wait forever')
        # The opposite risk to exp_pilots': this script had no timeouts at all,
        # so a server that accepts the connection and never answers hangs the
        # lab machine's launcher with no message.
        stub.bound_code = None
        stub.posts = []
        stub.hang_reads = 60.0
        rc, out, secs = run_start(stub.base,
                                  {'OTREE_START_READ_TIMEOUT': '3'},
                                  timeout=45)
        stub.hang_reads = 0.0
        check(rc != 0, f'non-zero exit (got {rc})')
        check(secs < 20,
              f'it gave up after {secs:.1f}s rather than hanging (the read '
              f'timeout was 3s)')
        check('FATAL' in out and 'cannot reach' in out,
              'and said which call it could not complete')
        check(stub.posts == [],
              f'nothing was created off the back of an unanswered read '
              f'({len(stub.posts)})')

        # ------------------------------------------------------------------
        section('6. the REST key is sent when the study demands one')
        stub.bound_code = 'keyed005'
        stub.posts = []
        stub.rest_keys_seen = []
        stub.require_key = 'sekrit'
        rc, out, _ = run_start(stub.base, {'OTREE_AUTH_LEVEL': 'STUDY',
                                           'OTREE_REST_KEY': 'sekrit'})
        check(rc == 0, f'exit 0 against a server demanding the key (got {rc})')
        check('sekrit' in stub.rest_keys_seen,
              f'the header actually arrived ({stub.rest_keys_seen})')

        section('6b. ...and it refuses to run without one, before any request')
        stub.rest_keys_seen = []
        reads_before, posts_before = stub.reads, len(stub.posts)
        env = {k: v for k, v in os.environ.items() if k != 'OTREE_REST_KEY'}
        env['OTREE_AUTH_LEVEL'] = 'STUDY'
        env['OTREE_BASE_URL'] = stub.base
        env['OTREE_ROOM'] = ROOM
        proc = subprocess.run(['bash', START_SH], env=env, timeout=30,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode()
        check(proc.returncode != 0, f'non-zero exit (got {proc.returncode})')
        check('OTREE_REST_KEY is unset' in out, 'and says why')
        # The paired PRESENCE for that absence: it refused BEFORE talking to
        # anything, so an unauthenticated call never went out to be rejected.
        check(stub.reads == reads_before and len(stub.posts) == posts_before,
              'no request of any kind reached the server')
        stub.require_key = None
    finally:
        stub.stop()

    # ------------------------------------------------------------------
    section('7. an unreachable server fails fast and loudly')
    dead = f'http://127.0.0.1:{free_port()}'
    rc, out, secs = run_start(dead, {'OTREE_START_READ_TIMEOUT': '20'},
                              timeout=60)
    check(rc != 0, f'non-zero exit (got {rc})')
    check(secs < 15,
          f'refused in {secs:.1f}s — a closed port is answered by the connect '
          f'timeout, not by the read timeout')
    check('FATAL' in out and 'is the server up' in out,
          'and the message tells the operator what to look at')

    # ------------------------------------------------------------------
    section('8. every curl in the script states a timeout class')
    # The structural half of the fix, asserted structurally: a call site that
    # goes back to bare `curl` — or an `api` with no class — is the way the
    # exp_pilots bug returns, and it would pass every behavioural check above.
    src = open(START_SH, encoding='utf-8').read()
    # Comments and log lines mention curl by name (the WARNING quotes its exit
    # code), and neither is a call site — so they are skipped rather than
    # matched, which is why this looks at the start of the command.
    bare = [ln.strip() for ln in src.splitlines()
            if re.search(r'\bcurl\b', ln)
            and not re.match(r'\s*(#|echo\b|printf\b)', ln)
            and '--max-time' not in ln]
    check(not bare, f'no bare curl call site ({bare})')
    check('--max-time "$max_time"' in src,
          'the one curl lives behind api(), which takes its timeout as an '
          'argument — there is no default for a new call site to inherit')
    api_calls = re.findall(r'\bapi "(\$[A-Z_]+)"', src)
    check(len(api_calls) >= 4,
          f'{len(api_calls)} api() call(s), each naming its class {sorted(set(api_calls))}')
    check(all(c in ('$READ_MAX_TIME', '$CREATE_MAX_TIME') for c in api_calls),
          f'and every one of them uses a declared class, not a literal '
          f'({sorted(set(api_calls))})')

    print(f'\n{"FAILED: " + str(len(FAILURES)) + " check(s)" if FAILURES else "ALL CHECKS PASSED"}')
    for f in FAILURES:
        print(f'  - {f}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
