#!/usr/bin/env python
"""Pre-deploy UPGRADE check: boot the NEW build against a COPY of the LIVE DB.

WHICH CHECK IS THIS? (there are two, and they are complementary)
-----------------------------------------------------------------------------
  scripts/prelaunch_check.py  — STATIC, config-only, no server, instant. Asks
      "is this configuration safe to launch?": placeholder REPLACE_* completion
      codes, DEBUG still on, testing loosenings (verify_quiz=False) left in.
      Run it in the target environment BEFORE opening a study to participants.
  scripts/predeploy_check.py  — DYNAMIC, this file. Boots the candidate build
      against a COPY of the live database and drives real participants over
      real HTTP. Asks "will the running study survive being upgraded to this
      code?". Run it BEFORE every deploy that lands on a database with
      participants in it.
Neither replaces the other: prelaunch cannot detect a broken upgrade path, and
predeploy cannot tell you the completion codes are still placeholders.

WHY THIS EXISTS — it tests the UPGRADE, not the install
-----------------------------------------------------------------------------
Two live outages in the pilot study this template was distilled from shared one
root cause: the new code was only ever tested against a FRESH database. Both
failures could only occur for a participant whose state PREDATED the change:

  * an unset participant-vars key — old participants were created before the
    key existed, so the new code's read raised KeyError (and note that
    `getattr(participant, 'k', default)` does NOT save you: oTree's vars
    descriptor raises KeyError, which the getattr default does not catch);
  * a session config frozen before a parameter existed — `session.config` is
    snapshotted at session creation, so a parameter added in the new build is
    simply absent for every already-running session, and `session.config['x']`
    raises KeyError.

A FRESH session cannot reproduce either — it is created by the new code, with
the new keys, from the new defaults. `otree test` and fresh-database HTTP tests
are therefore structurally blind to this entire class of failure. This script
closes that gap: it boots the candidate build against a copy of the live
database and drives the participant shapes that actually broke.

HOW THE APP IS DRIVEN (deployment-image constraints)
----------------------------------------------------
An earlier version of this check drove oTree's ASGI app in-process through
starlette.testclient.TestClient. That was wrong twice over: TestClient needs the
third-party `requests` package, which a minimal deployment image does not ship
(`pip install otree` is its entire dependency list), so the gate itself died
with ModuleNotFoundError and every check FAILed for the wrong reason; and an
in-process client bypasses the real HTTP stack that both live outages went
through. So the gate now
  * boots a REAL `otree prodserver` (the same command a live server runs) as a
    SUBPROCESS on a free localhost port, cwd'd into the staged app so it opens
    the staged db.sqlite3 copy and nothing else (see next section), and
  * drives it with the PYTHON STANDARD LIBRARY ONLY: urllib.request with a
    cookie jar issuing real GETs and POSTs, redirects followed, each page's
    form controls parsed out of the returned HTML exactly as a scriptless
    browser would submit them, overlaid with the check's payload.
The server's stdout/stderr is captured into the --log file, which the log scan
greps. The subprocess (and the timeoutworker child prodserver spawns) is ALWAYS
torn down, pass or fail, via killpg on its own process group.

HOW THE DB IS SELECTED (an oTree 6 trap — verified against otree 6.0.15)
------------------------------------------------------------------------
For sqlite, oTree does NOT honour the path in DATABASE_URL: otree/database.py
creates the engine with `creator=lambda: sqlite_disk_conn`, a raw connection to
the literal file `db.sqlite3` in the CURRENT WORKING DIRECTORY at import time.
So for sqlite the cwd is the lever. The shell wrapper therefore stages a
pristine copy of the candidate build in a private temp dir, places the database
copy at `<staged app>/db.sqlite3`, and this helper chdirs there before importing
otree — and launches the server subprocess with that same cwd, so both
processes are on the staged copy.

The cwd is NOT trusted on its own, because it is only a lever for sqlite: an
inherited `DATABASE_URL=postgres://…` makes it inert, and the engine goes to the
Postgres. So `pin_database_url()` also forces the variable onto the staged copy
(refusing, rather than silently overriding, a URL that disagrees), and
`assert_engine_on()` then interrogates the engine oTree actually built —
`PRAGMA database_list` — and HARD-FAILS unless it resolves to that staged file.
Declaration, then measurement, before anything is written.

That proof has TWO callers on purpose: this helper at boot, and the shell
wrapper through `--assert-engine-on` before its degraded-mode `resetdb`. One
implementation, so a proof that passes for one decider cannot be missing for the
other — which is exactly the hole that let a degraded run drop a live Postgres
(fixed 2026-08-14, see DECISIONS.md). The live database is never opened.

DEGRADED MODE — a template has no live database
------------------------------------------------
This template ships with no live data, and a study built from it has none until
its first session runs. Run with NO database copy and the check runs the
FRESH-INSTALL checks only, marks every upgrade-path check NOT TESTED (never
PASS), and says so in the output, in the summary, and in the exit banner. It
must never read as if it had checked an upgrade it did not check. Pass
--require-db (or PREDEPLOY_REQUIRE_DB=1) to turn a degraded run into a hard
failure — that is what you want in a deploy pipeline for a study that HAS live
sessions.

WHAT IS STUDY-SPECIFIC HERE (and how it stays general)
------------------------------------------------------
Pages and fields differ in every study built from this template, so this check
does not hardcode a page script. It fills each page from the page's OWN HTML
plus the app's OWN model metadata (oTree's `form_props`: choices, min, max), so
an unknown page added by a study is still driven correctly. Only three pieces
of template knowledge are applied on top, and each degrades to the generic
filler if the study removed it: correct quiz answers from intro.quiz_items,
consenting on a `consent` field, and a value for the external participant-id
fields. Both recruitment profiles (lab and prolific) are exercised.

Invoked by scripts/predeploy_check.sh. Direct use:
    predeploy_check.py --app-dir <staged build with db.sqlite3 inside> \
                       --src-app-dir <original checkout, for the live guard> \
                       --log <server-log capture file> \
                       [--degraded] [--require-db] [--configs lab,prolific]

CHECKS (each independent; any FAIL -> exit non-zero)
----------------------------------------------------
  1. BOOT      the app imports against the DB copy, the engine is verified to
               be ON that copy, and a real prodserver subprocess comes up and
               answers HTTP on localhost; inventory printed.
  2. SCHEMA    every table/column the new build's models expect exists in the
               DB (oTree has NO migrations: a new Player column 500s every page
               that loads that model, and the export — a deploy that adds
               columns needs an explicit migration or RESET_DB decision).
               NOT TESTED in degraded mode: a fresh DB is by definition built
               from the new models, so comparing it proves nothing.
  2b. FROZEN   every EXISTING session's frozen config is compared against the
      CONFIGS  current settings. FAILS only on a key MISSING from the frozen
               config or a value still holding a REPLACE_* placeholder; every
               other difference is REPORTED as information, never failed (see
               the two-severity note in check_frozen_session_configs). The
               remedy for a failing session is to RECREATE it — a frozen config
               cannot be repaired by editing settings.py. NOT TESTED in
               degraded mode: a fresh DB has no pre-existing sessions to audit.
  3. RESUME    an EXISTING mid-flow participant from the live data (e.g.
               sitting on the quiz or a task round) is driven several more
               pages over real HTTP. THIS is the upgrade path that broke: their
               participant vars and their frozen session config predate the new
               code. NOT TESTED in degraded mode.
  4. FRESH     a brand-new participant per selected session config is driven
               from entry to an end page.
  5. NO-JS     a second fresh participant per config walks the whole study with
               every JS-produced hidden field posting EMPTY (the scriptless
               browser shape that can 500 a page whose code assumes JS ran).
  6. LOG SCAN  the captured server log is grepped for 5xx, tracebacks,
               KeyError/TypeError; any hit fails loudly, naming the page and
               the exception.
"""

import argparse
import atexit
import http.cookiejar
import os
import re
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse

# --------------------------------------------------------------------------
# refuse anything that looks like the live database (defense in depth; the
# shell wrapper already guards, but this file must be safe if run directly)
#
# GENERALISED from the pilot, which named its own docker volume here. A study
# built from this template names ITS live volume/host path in
# PREDEPLOY_LIVE_MARKERS (comma-separated) so the refusal keeps working for it.
# --------------------------------------------------------------------------
LIVE_MARKERS = ('/var/lib/docker/', 'docker/volumes')
LIVE_MARKERS += tuple(
    m.strip() for m in os.environ.get('PREDEPLOY_LIVE_MARKERS', '').split(',')
    if m.strip())


# --------------------------------------------------------------------------
# ONE PLACE DECIDES WHICH DATABASE THIS CHECK TOUCHES
#
# The rule, stated once and applied by every caller: THE DATABASE IS
# `db.sqlite3` INSIDE THE STAGED APP DIR. Never the live one, never whatever
# the ambient environment happens to name.
#
# This used to be decided in TWO places that could disagree, and the
# disagreement was destructive (fixed 2026-08-14, see DECISIONS.md):
#   * the shell wrapper ran its degraded-mode `otree resetdb` in a subshell that
#     INHERITED the environment, and only exported its own sqlite DATABASE_URL
#     afterwards; and
#   * this helper never set DATABASE_URL at all — it relied on `os.chdir` alone,
#     which selects the database for sqlite ONLY (see the trap in the module
#     docstring). Against an inherited `DATABASE_URL=postgres://…` the chdir
#     lever does nothing.
# So an operator with a live Postgres URL exported — the normal state of a
# deploy shell — running the documented degraded check had their live database
# dropped and recreated by `resetdb`, after which the run tested the staged
# sqlite file and reported PASS. Verified end to end before the fix.
#
# Hence the two functions below, and hence `--assert-engine-on`: the shell calls
# the SAME proof this helper uses, BEFORE it runs anything destructive. If the
# proof only covered the helper, the shell's decider would grow back the first
# time somebody edited it — which is exactly how it got there.
# --------------------------------------------------------------------------
def staged_db_path(app_dir):
    """The one expression of the rule. Everything else asks this."""
    return os.path.join(app_dir, 'db.sqlite3')


def pin_database_url(db_path):
    """Point DATABASE_URL at the staged copy — and REFUSE if the environment
    already pointed somewhere else.

    Overriding silently would be enough to be safe here, but it would hide the
    interesting case: an operator who believes this check is exercising their
    Postgres. Say so and stop, rather than testing something other than what
    they think they are testing. MUST be called before oTree is imported —
    otree.database builds its engine at import time.
    """
    want = os.path.realpath(db_path)
    inherited = os.environ.get('DATABASE_URL', '')
    if inherited:
        scheme = inherited.split('://', 1)[0]
        backend = scheme.split('+', 1)[0].lower()
        if backend != 'sqlite':
            # Never echo the URL itself: it usually carries a password.
            print(f'FATAL: DATABASE_URL in this environment names a '
                  f'{backend!r} database, and this check must only ever touch '
                  f'its own staged copy at {want}.')
            print('  This check stages a private copy and drives fake '
                  'participants through it. It is NOT safe to point at a real '
                  'database, and a `resetdb` in its degraded path would DROP '
                  'that database.')
            print('  Unset DATABASE_URL (or run this from a shell that has '
                  'not exported it) and try again.')
            sys.exit(2)
        got = inherited.split('://', 1)[1].split('?', 1)[0] if '://' in inherited else ''
        if got and os.path.realpath(got) != want:
            print(f'FATAL: DATABASE_URL names the sqlite file '
                  f'{os.path.realpath(got)}, but this run is staged on {want}.')
            print('  Two different answers to "which database?" — refusing '
                  'rather than picking one.')
            sys.exit(2)
    os.environ['DATABASE_URL'] = f'sqlite:///{want}'


def assert_engine_on(db_path, context=''):
    """PROOF, not a promise: interrogate the engine oTree ACTUALLY built and
    hard-fail unless it resolves to the staged copy.

    `pin_database_url` states the intent; this verifies it came true, from
    inside the engine, before anything is written. The two are not redundant —
    for sqlite oTree ignores the path in DATABASE_URL entirely and opens
    `db.sqlite3` relative to the cwd, so the environment variable is a
    declaration and this is the measurement.
    """
    want = os.path.realpath(db_path)
    where = f' ({context})' if context else ''
    from otree.database import engine

    backend = engine.url.get_backend_name()
    if backend != 'sqlite':
        # A DIFFERENT failure from "on the wrong file": this is the wrong
        # BACKEND, which no amount of cwd juggling would have fixed, and it is
        # the shape the destructive bug took.
        print(f'FATAL{where}: oTree built a {backend!r} engine, not sqlite. '
              f'This check only ever runs against its own staged copy '
              f'({want}) — aborting before anything is written.')
        sys.exit(2)

    raw = engine.raw_connection()
    try:
        dblist = raw.cursor().execute('PRAGMA database_list').fetchall()
    finally:
        raw.close()
    main_file = next((row[2] for row in dblist if row[1] == 'main'), '')
    if not main_file:
        print(f'FATAL{where}: the sqlite engine reports no file for its main '
              f'database (in-memory?) — expected {want}.')
        sys.exit(2)
    engine_file = os.path.realpath(main_file)
    if engine_file != want:
        print(f'FATAL{where}: the engine is on {engine_file!r}, NOT the staged '
              f'copy {want!r} — aborting before anything is written.')
        sys.exit(2)
    return engine_file


def assert_not_live(db_path, src_app_dir):
    rp = os.path.realpath(db_path)
    reasons = [f'path mentions {m!r}' for m in LIVE_MARKERS if m in rp]
    if rp.startswith('/app/'):
        reasons.append('path is under /app (the container tree)')
    for cand in (os.path.join(src_app_dir, 'db.sqlite3'),
                 os.path.join(src_app_dir, 'data', 'db.sqlite3')):
        if os.path.exists(cand) and os.path.realpath(cand) == rp:
            reasons.append(f'path IS the source app tree database {cand}')
    if reasons:
        print('FATAL: refusing to run against what looks like a LIVE database:')
        for r in reasons:
            print(f'  - {r}')
        print('Point this check at a COPY of the live database instead.')
        sys.exit(2)


# --------------------------------------------------------------------------
# tiny check harness
#
# THREE states, not two. `ok=None` means NOT TESTED — used for the upgrade-path
# checks in degraded mode. A not-tested check is never counted as a pass, and
# the summary shouts about it, because the whole point of this gate is that
# silence about the upgrade path is what caused the outages.
# --------------------------------------------------------------------------
RESULTS = []  # (name, ok, detail_lines)

PASS, FAIL, NOT_TESTED = True, False, None


def _label(ok):
    return 'PASS' if ok is True else ('FAIL' if ok is False else 'NOT TESTED')


def record(name, ok, detail):
    if isinstance(detail, str):
        detail = [detail]
    RESULTS.append((name, ok, detail))
    print(f'\n=== {name}: {_label(ok)} ===')
    for line in detail:
        print(f'  {line}')


# End pages of THIS template: reaching one means the walk is over. `Results` is
# the completer ending; `Ended` is the non-completer ending (disqualified,
# declined consent, screened out at entry). A study that adds an end page adds
# it here (or names it in PREDEPLOY_END_PAGES).
TERMINAL_PAGES = {'Results', 'Ended'}
TERMINAL_PAGES |= {p.strip() for p in
                   os.environ.get('PREDEPLOY_END_PAGES', '').split(',') if p.strip()}

# Preferred current pages for the mid-flow resume, most valuable first: the
# pages where a participant carries the most accumulated state (quiz answers,
# task rounds, participant vars set along the way) are the pages that a broken
# upgrade actually 500s. Unknown pages (anything a study added) simply sort
# last; they are still tried.
# NB the task-page names ('GameStart', 'payoff') also live in
# scripts/tests/main_contract.py — the one contract the test suite imports. Update
# them there on a game swap; this list only degrades (unknown names sort
# last), it does not break.
RESUME_PREFERENCE = ['quiz', 'GameStart', 'payoff', 'instructing',
                     'AISafetyAgree', 'ConfirmProlificID', 'Demographics',
                     'Feedback', 'welcome', 'startpage']
if os.environ.get('PREDEPLOY_RESUME_PAGES'):
    RESUME_PREFERENCE = [p.strip() for p in
                         os.environ['PREDEPLOY_RESUME_PAGES'].split(',') if p.strip()]

EXC_RE = re.compile(r'\b([A-Z][A-Za-z_]*(?:Error|Exception))\b')

# The log scan reads the log only up to this sentinel, so anything the dying
# server/timeoutworker prints DURING teardown cannot fail the scan.
END_SENTINEL = 'PREDEPLOY END OF CHECKS'

# Form controls never blanked by the no-JS walk: they are the framework's, not
# JavaScript's.
NOJS_KEEP_FIELDS = {'csrfmiddlewaretoken', 'csrf_token'}

# Generic filler value for a free-text field with no other constraint. The SAME
# constant everywhere on purpose: a confirm-this-field pair (e.g. an account
# number and its confirmation) then matches without this check knowing the
# pair exists.
GENERIC_TEXT = 'PREDEPLOY'


class Log:
    """The single capture file: the server subprocess writes its stdout and
    stderr into it, and this process appends PREDEPLOY marker lines through the
    same file object, so the log scan can attribute server output to the page
    that was in flight."""

    def __init__(self, path):
        self.path = path
        self.fh = open(path, 'w', buffering=1, errors='replace')

    def write(self, msg):
        self.fh.write(msg.rstrip('\n') + '\n')
        self.fh.flush()

    def write_exc(self, prefix):
        self.write(f'PREDEPLOY {prefix}:\n{traceback.format_exc()}')

    def tail(self, n=25):
        self.fh.flush()
        try:
            with open(self.path, errors='replace') as fh:
                return [ln.rstrip() for ln in fh][-n:]
        except OSError:
            return []

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# the real server subprocess
# --------------------------------------------------------------------------
def find_free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ServerUnderTest:
    """`otree prodserver` (what a live server runs) as a subprocess, cwd'd into
    the staged app so it opens ONLY the staged db.sqlite3 copy."""

    def __init__(self, python, app_dir, log: Log, debug=False):
        self.python = python
        self.app_dir = app_dir
        self.log = log
        self.debug = debug
        self.port = find_free_port()
        self.base_url = f'http://127.0.0.1:{self.port}'
        self.proc = None

    def start(self, timeout=120):
        """Launch and wait for HTTP. Returns None on success, else an error
        string describing why the server never answered."""
        env = os.environ.copy()
        # DEBUG axis: default to the PRODUCTION shape, because production is
        # what this build is about to be deployed into and debug loosenings
        # (verify_quiz=False) would mask a broken gate. --debug flips it.
        # NB oTree treats OTREE_PRODUCTION as set-or-not, so an EMPTY string
        # still means production — the variable has to be removed, not blanked.
        if self.debug:
            env.pop('OTREE_PRODUCTION', None)
        else:
            env['OTREE_PRODUCTION'] = '1'
        # No admin auth in the way of participant pages.
        for k in ('OTREE_AUTH_LEVEL', 'OTREE_IN_MEMORY', 'OTREE_REST_KEY',
                  'RESET_DB'):
            env.pop(k, None)
        # informational only for sqlite (cwd is what binds the DB — docstring)
        env['DATABASE_URL'] = \
            f"sqlite:///{os.path.join(self.app_dir, 'db.sqlite3')}"
        # prodserver spawns `otree timeoutsubprocess` BY NAME; make sure the
        # launcher that belongs to our interpreter is first on PATH. (Without
        # this the server dies at boot with FileNotFoundError: 'otree'.)
        env['PATH'] = (os.path.dirname(self.python) + os.pathsep
                       + env.get('PATH', ''))
        shim = (f"import sys; sys.argv = ['otree', 'prodserver', "
                f"'127.0.0.1:{self.port}']; "
                f"from otree.main import execute_from_command_line; "
                f"execute_from_command_line()")
        self.proc = subprocess.Popen(
            [self.python, '-c', shim], cwd=self.app_dir, env=env,
            stdout=self.log.fh, stderr=subprocess.STDOUT,
            start_new_session=True)
        deadline = time.monotonic() + timeout
        last_exc = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return (f'server process exited with code '
                        f'{self.proc.returncode} before answering HTTP')
            try:
                with urllib.request.urlopen(self.base_url + '/', timeout=2):
                    return None
            except urllib.error.HTTPError:
                return None  # an HTTP status of any kind means it is up
            except Exception as e:
                last_exc = e
                time.sleep(0.25)
        return (f'server did not answer on {self.base_url} within {timeout}s '
                f'(last error: {last_exc!r})')

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        """Always-runs teardown: TERM then KILL the whole process group, so the
        timeoutworker child prodserver spawned dies with it."""
        if self.proc is None:
            return
        if self.proc.poll() is None:
            for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
                try:
                    os.killpg(self.proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    self.proc.terminate()
                try:
                    self.proc.wait(wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
        self.proc = None


# --------------------------------------------------------------------------
# stdlib-only browser: urllib + cookie jar, redirects followed (urllib
# re-issues a redirected POST as a GET, exactly as browsers do)
# --------------------------------------------------------------------------
class Browser:
    def __init__(self, base_url):
        self.base = base_url.rstrip('/')
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def open(self, path, data=None, timeout=60):
        """GET (data is None) or form-POST `path`. Returns
        (status, final_path_after_redirects, body_text). A transport-level
        failure (server died, connection refused) returns status 599 with the
        exception text as the body."""
        url = path if path.startswith('http') else self.base + path
        payload = urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=payload)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return (resp.status, urlparse(resp.geturl()).path,
                        resp.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', 'replace')
            except Exception:
                body = ''
            return e.code, urlparse(e.geturl() or url).path, body
        except Exception as e:
            return 599, urlparse(url).path, f'(transport error: {e!r})'


# --------------------------------------------------------------------------
# scriptless-browser form parsing: collect what a browser with no JS would
# submit from the page's own HTML (hidden inputs with their server-rendered
# values, csrf token if any, checked radios/boxes, selects, textareas) AND the
# full control inventory, which the payload builder needs to know which fields
# are hidden (the no-JS walk blanks exactly those) and what a radio/select may
# legally be set to.
# --------------------------------------------------------------------------
class _FormsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self._form = None
        self._select = None
        self._textarea_name = None
        self._textarea_chunks = None

    def _control(self, name):
        controls = self._form['controls']
        if name not in controls:
            controls[name] = dict(name=name, kind='text', hidden=False,
                                  options=[])
        return controls[name]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self._form = dict(attrs=a, fields={}, controls={})
            self.forms.append(self._form)
            return
        if self._form is None:
            return
        name = a.get('name')
        if tag == 'input' and name:
            typ = (a.get('type') or 'text').lower()
            if typ in ('submit', 'button', 'image', 'reset', 'file'):
                return  # only the clicked button posts; ours has no name
            ctl = self._control(name)
            if typ in ('radio', 'checkbox'):
                ctl['kind'] = typ
                ctl['options'].append(a.get('value') or 'on')
                if 'checked' in a:
                    self._form['fields'][name] = a.get('value') or 'on'
                return
            ctl['kind'] = 'hidden' if typ == 'hidden' else typ
            ctl['hidden'] = typ == 'hidden'
            self._form['fields'][name] = a.get('value') or ''
        elif tag == 'select' and name:
            ctl = self._control(name)
            ctl['kind'] = 'select'
            self._select = (name, [])
        elif tag == 'option' and self._select is not None:
            self._select[1].append((a.get('value') or '', 'selected' in a))
        elif tag == 'textarea' and name:
            ctl = self._control(name)
            ctl['kind'] = 'textarea'
            self._textarea_name, self._textarea_chunks = name, []

    def handle_endtag(self, tag):
        if tag == 'form':
            self._form = None
        elif tag == 'select' and self._form and self._select:
            name, options = self._select
            chosen = next((v for v, sel in options if sel),
                          options[0][0] if options else '')
            self._form['fields'][name] = chosen
            self._control(name)['options'] = [v for v, _ in options]
            self._select = None
        elif tag == 'textarea' and self._form and self._textarea_name:
            self._form['fields'][self._textarea_name] = \
                ''.join(self._textarea_chunks)
            self._textarea_name, self._textarea_chunks = None, None

    def handle_data(self, data):
        if self._textarea_chunks is not None:
            self._textarea_chunks.append(data)


def parse_form(html):
    """(default submission, control inventory) for the page's wizard form.

    oTree renders it with id="form"; falls back to the first POST form."""
    parser = _FormsParser()
    try:
        parser.feed(html or '')
    except Exception:
        pass
    forms = parser.forms
    chosen = None
    for f in forms:
        if f['attrs'].get('id') == 'form':
            chosen = f
            break
    if chosen is None:
        for f in forms:
            if (f['attrs'].get('method') or '').lower() == 'post':
                chosen = f
                break
    if chosen is None:
        chosen = forms[0] if forms else dict(fields={}, controls={})
    return dict(chosen['fields']), dict(chosen['controls'])


def page_name_of(path):
    parts = (path or '').strip('/').split('/')
    return parts[3] if len(parts) >= 5 and parts[0] == 'p' else None


def url_app_of(path):
    """The NAME_IN_URL segment of a participant page path."""
    parts = (path or '').strip('/').split('/')
    return parts[2] if len(parts) >= 5 and parts[0] == 'p' else None


# --------------------------------------------------------------------------
# the HTTP flow driver (module-level so verification harnesses can reuse it)
# --------------------------------------------------------------------------
def drive(browser, code, payload_fn, *, log, server=None,
          server_errors_of=None, max_steps=200, label='', stop_after=None):
    """Walk participant `code` from their CURRENT page over real HTTP.

    Each page is submitted as a browser would: the form's own parsed fields
    (hidden inputs, csrf token if present) overlaid with
    payload_fn(page, controls, defaults). Returns a dict with: last (page),
    statuses, visited, advances, stuck_on, blanked (list of "page.field" the
    no-JS payload posted empty), err (None, or a dict naming
    page/status/exceptions).
    """
    out = dict(last=None, statuses=[], visited=[], advances=0, stuck_on=None,
               blanked=[], err=None)

    def fail_5xx(page, status, body):
        # WHERE THE EXCEPTION NAME COMES FROM. oTree's 500 page renders the
        # traceback as HTML but does not reliably name the exception class in
        # text we can grep, so the authoritative source is the server's own
        # traceback in the captured log. Give the subprocess a moment to flush
        # it, then take the last `SomeError: message` line — that is the line
        # that names the actual failure.
        excs = sorted(set(EXC_RE.findall(body or '')))
        time.sleep(0.5)
        for line in reversed(log.tail(120)):
            m = re.match(r'\s*((?:[A-Za-z_][\w.]*\.)?[A-Z]\w*'
                         r'(?:Error|Exception))\b\s*:?(.*)', line)
            if m:
                excs.insert(0, f'{m.group(1)}:{m.group(2)}'.strip()[:200])
                break
        if server_errors_of:
            # Optional hook: a study that records server errors into its
            # participant_extra bucket gets them quoted here too.
            for e in server_errors_of(code)[-2:]:
                excs.append(f"{e.get('exc_class')}: {e.get('msg')}")
        if status == 599 and server is not None and not server.alive():
            excs.append('the server process DIED mid-check (exit code '
                        f'{server.proc.returncode if server.proc else "?"})')
        log.write(f'PREDEPLOY 5XX status={status} page={page} '
                  f'participant={code} '
                  f'exceptions={excs or ["(none extracted)"]}')
        if body:
            log.write(f'PREDEPLOY 5XX body excerpt (page={page}): '
                      + re.sub(r'\s+', ' ', body)[:3000])
        out['err'] = dict(page=page, status=status,
                          exceptions=excs or ['(unidentified)'])

    log.write(f'PREDEPLOY >> InitializeParticipant {code} ({label})')
    status, path, body = browser.open(f'/InitializeParticipant/{code}')
    out['statuses'].append(status)
    if status >= 500:
        fail_5xx('InitializeParticipant', status, body)
        return out

    # Stuck detection compares the FULL path, not the page name: a multi-round
    # page (the task rounds) legitimately repeats its name with a new page
    # index in the URL on every advance.
    same_path_posts = 0
    for _ in range(max_steps):
        page = page_name_of(path)
        if page is None or page in TERMINAL_PAGES:
            out['last'] = page
            return out
        out['visited'].append(page)

        defaults, controls = parse_form(body)
        data = dict(defaults)
        overlay, blanked = payload_fn(page, controls, defaults, path)
        data.update(overlay)
        out['blanked'] += [f'{page}.{f}' for f in blanked]

        log.write(f'PREDEPLOY >> POST {page} (participant {code})')
        prev_path = path
        status, path, body = browser.open(prev_path, data=data)
        out['statuses'].append(status)
        if status >= 500:
            fail_5xx(page, status, body)
            out['last'] = page
            return out
        if path != prev_path:
            out['advances'] += 1
            same_path_posts = 0
            if page == stop_after:
                out['last'] = page_name_of(path)
                return out
        else:
            same_path_posts += 1
            if same_path_posts >= 3:
                out['stuck_on'] = page
                out['last'] = page
                # a validation loop is not a 5xx; keep a body hint so a stuck
                # check is diagnosable from the log
                hint = ' | '.join(re.findall(
                    r'invalid-feedback[^>]*>\s*([^<]{1,120})', body or ''))
                log.write(f'PREDEPLOY STUCK on {page} (participant {code}); '
                          f'body hint: {hint or "(no form error text found)"}')
                return out

    out['last'] = page_name_of(path)
    return out


# --------------------------------------------------------------------------
# payload building — model-driven, so a study's own pages are driven too
# --------------------------------------------------------------------------
class PayloadBuilder:
    """Chooses what to submit for every field of every page.

    Order of preference for one field:
      1. TEMPLATE KNOWLEDGE — the few semantic values this check must get right
         (correct quiz answers, consent, the external participant id). Each is
         resolved defensively: if a study removed the thing, the rule simply
         does not apply.
      2. THE PAGE'S OWN HTML — a checked radio / selected option / hidden value
         the server rendered is what a scriptless browser would send back.
      3. THE APP'S MODEL METADATA — oTree's form_props (choices, min, max) and
         the column type, so an unknown field a study added still gets a legal
         value instead of an empty string.
    Anything filled by rule 3 is reported, so the output never implies this
    check understood a page it merely guessed its way through.
    """

    def __init__(self, log):
        self.log = log
        self.guessed = set()          # "app.field" filled by the generic rule
        self.quiz_answers = {}        # field -> correct answer
        self._columns = {}            # NAME_IN_URL -> {field: column}
        self._load_quiz()
        self._load_models()

    # -- template knowledge, all optional -----------------------------------
    def _load_quiz(self):
        """Correct answers, so the comprehension gate is passed rather than
        tripped. A study that renames or drops quiz_items just loses this."""
        try:
            from intro.quiz_items import QUIZ_ITEMS
            self.quiz_answers = {i['field']: i['answer'] for i in QUIZ_ITEMS}
        except Exception:
            self.log.write('PREDEPLOY note: intro.quiz_items not importable; '
                           'quiz answers fall back to the generic filler')

    def _load_models(self):
        """NAME_IN_URL -> the app's model columns, for the generic filler."""
        try:
            from otree import settings as otree_settings
            from otree.common import get_models_module
        except Exception:
            return
        for app in getattr(otree_settings, 'OTREE_APPS', []) or []:
            try:
                mm = get_models_module(app)
                cols = {}
                for model_name in ('Player', 'Group', 'Subsession'):
                    model = getattr(mm, model_name, None)
                    table = getattr(model, '__table__', None)
                    if table is None:
                        continue
                    for col in table.columns:
                        cols.setdefault(col.name, col)
                self._columns[mm.C.NAME_IN_URL] = cols
            except Exception:
                self.log.write_exc(f'could not introspect models of app {app!r}')

    # -- the generic, model-driven filler -----------------------------------
    def _from_model(self, url_app, field):
        col = self._columns.get(url_app, {}).get(field)
        if col is None:
            return None
        props = getattr(col, 'form_props', None) or {}
        choices = props.get('choices')
        if choices:
            first = choices[0]
            # choices may be [value] or [(value, label)]
            return str(first[0] if isinstance(first, (list, tuple)) else first)
        typename = str(getattr(col, 'type', '')).upper()
        if 'BOOLEAN' in typename:
            return 'True'
        if 'INT' in typename or 'FLOAT' in typename or 'NUMERIC' in typename:
            low, high = props.get('min'), props.get('max')
            value = low if low is not None else 1
            if high is not None and value > high:
                value = high
            return str(value)
        return GENERIC_TEXT

    def _generic(self, url_app, field, control):
        """A legal value for a field nothing else covered."""
        kind = (control or {}).get('kind')
        options = [o for o in (control or {}).get('options', []) if o != '']
        if kind in ('radio', 'select') and options:
            return options[0]
        if kind == 'checkbox':
            return options[0] if options else 'on'
        from_model = self._from_model(url_app, field)
        if from_model is not None:
            return from_model
        if kind == 'textarea':
            return 'predeploy check'
        return GENERIC_TEXT

    # -- the two payload functions ------------------------------------------
    def _base(self, page, controls, defaults, path, nojs):
        """Shared body of both walks. Returns (overlay, blanked_fields)."""
        url_app = url_app_of(path)
        overlay, blanked = {}, []
        for field, control in controls.items():
            if field in NOJS_KEEP_FIELDS or field.startswith('_'):
                continue
            hidden = control.get('kind') == 'hidden' or control.get('hidden')
            if nojs and hidden:
                # THE POINT OF THE NO-JS WALK: every hidden field on the page
                # is one JavaScript would have filled in a real browser. A
                # scriptless browser posts it exactly as rendered — empty.
                overlay[field] = ''
                blanked.append(field)
                continue
            # 1. template knowledge
            if field in self.quiz_answers:
                overlay[field] = self.quiz_answers[field]
                continue
            if field == 'consent':
                overlay[field] = 'True'
                continue
            if field in ('participant_id_external', 'participant_id_url'):
                overlay[field] = '' if nojs else 'predeploy'
                continue
            # 2. the page's own HTML already supplied something usable
            if defaults.get(field):
                continue
            if hidden:
                continue  # a hidden field the server rendered empty stays empty
            # 3. the generic, model-driven filler
            value = self._generic(url_app, field, control)
            overlay[field] = value
            self.guessed.add(f'{url_app}.{field}')
        return overlay, blanked

    def js(self, page, controls, defaults, path):
        return self._base(page, controls, defaults, path, nojs=False)

    def nojs(self, page, controls, defaults, path):
        return self._base(page, controls, defaults, path, nojs=True)


# ==========================================================================
# the checks
# ==========================================================================
def check_boot(server, log, db_path, degraded):
    """Check 1: in-process import proves the engine is on the staged copy and
    prints the inventory; then the REAL server subprocess must answer HTTP."""
    try:
        import otree.main as otree_main
        otree_main.setup()
        from otree.database import DBSession
        from otree.models import Participant, Session

        # PROOF the engine is on our staged copy and nothing else, before ANY
        # write happens. The same function the shell wrapper calls through
        # --assert-engine-on before its own destructive step, so the two
        # processes cannot be proved against different rules. The server
        # subprocess runs with the same cwd and the same DATABASE_URL, so
        # proving this process's engine proves the server's too.
        engine_file = assert_engine_on(db_path, context='in-process boot')

        s = DBSession()
        try:
            sessions = s.query(Session).all()
            n_parts = s.query(Participant).count()
            inventory = [
                f'mode: {"DEGRADED (fresh database — NO live data)" if degraded else "UPGRADE (copy of a live database)"}',
                f'engine verified on the staged copy: {engine_file}',
                f'{len(sessions)} session(s), {n_parts} participant(s) '
                f'in the database:']
            for sess in sessions[:10]:
                inventory.append(
                    f'  session {sess.code} config={sess.config.get("name")!r} '
                    f'({sess.num_participants} slots)')
            if len(sessions) > 10:
                inventory.append(f'  ... and {len(sessions) - 10} more')
        finally:
            s.close()
    except SystemExit:
        raise
    except Exception as e:
        log.write_exc('boot failed (in-process import)')
        record('1. BOOT (new build against the database)', False,
               f'the app failed to boot against the database: {e!r}')
        return False

    err = server.start()
    if err:
        log.write(f'PREDEPLOY BOOT: {err}')
        record('1. BOOT (new build against the database)', False,
               [f'the real server did not come up: {err}',
                'last server-log lines:']
               + [f'  | {ln}' for ln in log.tail(15)])
        return False
    inventory.append(f'real prodserver subprocess answering on '
                     f'{server.base_url} (pid {server.proc.pid})')
    record('1. BOOT (new build against the database)', True, inventory)
    return True


def check_schema(log, degraded):
    """Check 2: every table/column the new models expect must exist."""
    name = '2. SCHEMA (new models vs live data)'
    if degraded:
        record(name, NOT_TESTED,
               ['no live database was supplied, and the fresh database was '
                'built FROM these models — comparing them proves nothing.',
                'A real schema check needs a copy of the live database.'])
        return
    try:
        from sqlalchemy import inspect as sqla_inspect
        from otree.database import engine, AnyModel
        insp = sqla_inspect(engine)
        db_tables = set(insp.get_table_names())
        missing, extra = [], []
        for tname, table in AnyModel.metadata.tables.items():
            if tname not in db_tables:
                missing.append(f'TABLE {tname} is missing from the DB')
                continue
            db_cols = {c['name'] for c in insp.get_columns(tname)}
            for col in table.columns:
                if col.name not in db_cols:
                    missing.append(
                        f'COLUMN {tname}.{col.name} is missing from the DB')
            extra += [f'{tname}.{c}' for c in
                      db_cols - {col.name for col in table.columns}]
        detail = []
        if missing:
            detail.append('the NEW build expects schema the LIVE data does not '
                          'have (oTree has no migrations — these pages/exports '
                          'would 500):')
            detail += [f'  - {m}' for m in missing]
            detail.append('=> this deploy needs an explicit migration '
                          '(ALTER TABLE ... ADD COLUMN on the live DB) or a '
                          'deliberate RESET_DB decision BEFORE going live.')
            for m in missing:
                log.write(f'PREDEPLOY SCHEMA MISMATCH: {m}')
        else:
            detail.append(f'all {len(AnyModel.metadata.tables)} model tables '
                          f'and their columns exist in the database copy')
        if extra:
            detail.append(f'(info: {len(extra)} column(s) exist in the DB but '
                          f'not in the new models — old data, harmless)')
        record(name, not missing, detail)
    except Exception as e:
        log.write_exc('schema comparison failed')
        record(name, False, f'comparison failed: {e!r}')


def session_can_still_reach_an_ending(participants) -> bool:
    """Could ANYBODY in this session still be sent to an ending — and so to a
    completion code — from now on?

    THE ASYMMETRY IS THE POINT, and it is deliberately not symmetric (adopted
    from the exp_pilots frozen-config audit, 2026-08-14). Answering YES when the
    truth is no blocks a deploy, and the printed per-session line says exactly
    which session and why, so it is diagnosable in seconds. Answering NO when
    the truth is yes lets a live session through carrying a REPLACE_*
    completion code, and costs a real participant their payment. Those two
    wrong answers are not equally bad, so **UNSURE COUNTS AS YES.**

    "Done" is therefore only ever concluded from positive evidence: oTree's own
    page cursor showing the participant at or past the last page
    (`_index_in_pages >= _max_page_index`). Anything else — an unstarted
    participant who might still arrive, a cursor that is None, an attribute that
    does not exist on this oTree version, an exception while reading — is live.
    """
    if participants is None:
        return True
    any_seen = False
    for p in participants:
        any_seen = True
        try:
            index = getattr(p, '_index_in_pages', None)
            last = getattr(p, '_max_page_index', None)
            if index is None or last is None:
                return True          # cannot tell -> live
            if int(index) < int(last):
                return True          # positively still has pages to go
        except Exception:
            return True              # cannot tell -> live
    # Two ways to reach here, both meaning "nobody can be sent anywhere":
    # every participant is positively at or past the last page, or the query
    # positively returned no participants at all.
    return False


def _is_placeholder(value) -> bool:
    """settings.is_placeholder, imported late so the pure analysis below stays
    drivable from a test without booting the app. Falls back to the same rule
    rather than to `False`: a placeholder that cannot be recognised must not
    read as a real value."""
    try:
        from settings import is_placeholder
        return is_placeholder(value)
    except Exception:
        return 'REPLACE' in str(value)


def audit_frozen_session_configs(stored, current_configs, defaults):
    """The pure analysis behind check 2b, separable so a test can drive it.

    `stored`          iterable of (session_code, config_name, frozen_config)
                      or (session_code, config_name, frozen_config, live)
    `current_configs` {name: current SESSION_CONFIGS entry} (profile-resolved —
                      resolve_recruitment_profile writes explicit keys at import)
    `defaults`        current SESSION_CONFIG_DEFAULTS

    Returns (problems, diffs).

    `problems` — the ONLY two kinds that FAIL the check:
      * MISSING     the key is absent from the frozen config: the session was
                    created before the key existed. Its participants run
                    without it — common.cfg falls back to the shipped default,
                    a raw config.get reads None/off — while settings.py looks
                    perfectly correct. This is CLAUDE.md's frozen-config rule
                    surfacing operationally.
      * PLACEHOLDER the frozen value still holds a REPLACE_* placeholder
                    (settings ships COMP-XXXXXX_REPLACE / NOCONS-XXXXXX_REPLACE
                    / DQ-XXXXXX_REPLACE / REPLACE_SCREENOUT_RETURN_URL; matched
                    BY SHAPE via settings.is_placeholder, never by exact string
                    — see that function for why). Catches the case prelaunch_check CANNOT: the
                    codes were fixed in settings but the session was never
                    recreated, so a live session still carries the placeholder.

    `diffs` — every other difference, REPORTED as information and NEVER failed.
    WHY TWO SEVERITIES (Julian, 2026-08-13 — do not later promote everything to
    a failure): a session legitimately running an older threshold is normal,
    and static_version alone changes on nearly every deploy, so a check that
    fails on ANY difference fails every single time — within a fortnight it is
    run with the failure ignored, at which point it catches nothing, including
    the real cases. Two severities keep the loud failure meaningful while still
    showing the operator everything.
    """
    problems, diffs = [], []
    for row in stored:
        # A 4th element carries liveness. Absent means UNSURE, and unsure
        # counts as live — a caller that has not been taught to answer the
        # question must not thereby silence the failure.
        code, name, frozen = row[0], row[1], row[2]
        live = row[3] if len(row) > 3 else True
        entry = current_configs.get(name)
        if entry is None:
            diffs.append((code, f'(config {name!r})',
                          '(this config name is no longer in settings — '
                          'compared against the defaults alone)', ''))
            entry = {}
        current = {**defaults, **entry}
        # A finished session cannot send anybody anywhere, so its stale keys
        # cannot cost anybody a payment. They are still SHOWN — silence would
        # hide a real difference — but as information, not as a deploy blocker.
        # See session_can_still_reach_an_ending for why the doubt goes the
        # other way.
        def flag(kind, key, extra):
            if live:
                problems.append((code, key, kind, extra))
            else:
                diffs.append((code, key, extra,
                              f'({kind} — but no participant in this session '
                              f'can still reach an ending, so it blocks '
                              f'nothing)'))

        for key in sorted(current):
            if key not in frozen:
                flag('MISSING', key, f'current setting {current[key]!r}')
                continue
            frozen_value = frozen[key]
            # SHAPE, NOT PREFIX — via settings.is_placeholder, the one
            # implementation. This used to be `startswith('REPLACE_')`, which
            # the 2026-08-14 placeholder change (`REPLACE_CC` ->
            # `COMP-XXXXXX_REPLACE`) would have silently disarmed: the audit
            # would have kept passing while a live session carried a code that
            # pays nobody.
            if isinstance(frozen_value, str) and _is_placeholder(frozen_value):
                flag('PLACEHOLDER', key, repr(frozen_value))
            elif frozen_value != current[key]:
                diffs.append((code, key, frozen_value, current[key]))
        for key in sorted(set(frozen) - set(current)):
            diffs.append((code, key, frozen[key],
                          '(key no longer in the current settings)'))
    return problems, diffs


def check_frozen_session_configs(log, degraded):
    """Check 2b: do any EXISTING sessions run a stale or broken frozen config?

    A session config is frozen at creation, so ANY parameter added or corrected
    after a session was created is missing or stale for that session while
    settings.py looks perfectly correct. This check compares each existing
    session's stored config against the current settings and reports every
    difference — failing only on the two genuinely broken kinds (see
    audit_frozen_session_configs).

    NOT ALREADY TESTED ELSEWHERE, though it looks like it might be:
    scripts/tests/frozen_config_test.py proves RESILIENCE — it strips keys from a
    session's stored config and walks a participant to prove nothing 500s. It
    never asks whether a stale session actually EXISTS in the live data.
    Resilience to the problem and detection of it are different things, and
    both are worth having.

    DOCUMENTED LIMITATION: nothing triggers this automatically, because there
    is no event to hang it on — editing settings.py is not an event the running
    system can observe. It therefore runs at a deliberate moment (this
    pre-deploy gate), NOT continuously; do not assume something is always
    watching for stale sessions.

    MUST RUN BEFORE run_http_checks, which creates fresh sessions in the staged
    copy — those are this build's own and would pollute the audit.
    """
    name = '2b. FROZEN SESSION CONFIGS (existing sessions vs current settings)'
    if degraded:
        record(name, NOT_TESTED,
               ['no live database was supplied; a fresh database has no '
                'pre-existing sessions to audit.',
                'A real audit needs a copy of the live database.'])
        return
    try:
        from otree.database import DBSession
        from otree.models import Session
        from settings import SESSION_CONFIGS, SESSION_CONFIG_DEFAULTS
        s = DBSession()
        try:
            stored = []
            liveness = []
            for sess in s.query(Session).all():
                try:
                    live = session_can_still_reach_an_ending(
                        sess.get_participants())
                except Exception:
                    live = True      # cannot tell -> live (see that function)
                stored.append((sess.code, (sess.config or {}).get('name'),
                               dict(sess.config or {}), live))
                liveness.append((sess.code, live))
        finally:
            s.close()
        current_configs = {c['name']: dict(c) for c in SESSION_CONFIGS}
        problems, diffs = audit_frozen_session_configs(
            stored, current_configs, SESSION_CONFIG_DEFAULTS)

        detail = [f'{len(stored)} existing session(s) audited against the '
                  f'current settings']
        # The per-session line: whether each session can still send somebody to
        # an ending is what decides failure-vs-information below, so it is
        # printed rather than left implicit. A wrong LIVE verdict blocks a
        # deploy, and this line is how somebody diagnoses that in seconds.
        for code, live in liveness:
            detail.append(
                f'  session {code}: '
                + ('CAN still reach an ending — stale keys here FAIL'
                   if live else
                   'nobody can still reach an ending — stale keys here are '
                   'reported only'))
        if problems:
            detail.append(
                'BROKEN — a frozen session cannot be repaired by editing '
                'settings.py: it has to be RECREATED (retire it, create a new '
                'session from the corrected config):')
            for code, key, kind, extra in problems:
                detail.append(f'  - session {code}: {key} — {kind} ({extra})')
                log.write(f'PREDEPLOY FROZEN CONFIG: session {code} '
                          f'{key} {kind}')
            detail.append(
                '  MISSING => recreate the session (its participants run '
                'without the key); PLACEHOLDER => fix the value in settings '
                'AND recreate the session — editing settings alone changes '
                'nothing for a session that already exists.')
        if diffs:
            detail.append(
                f'info: {len(diffs)} value difference(s) — reported so nothing '
                f'is hidden, but NOT failures (a session legitimately runs the '
                f'values it was created with):')
            for code, key, frozen_value, current_value in diffs:
                detail.append(f'  ~ session {code}: {key} — session has '
                              f'{frozen_value!r}, current setting is '
                              f'{current_value!r}')
        if not problems and not diffs:
            detail.append('every existing session matches the current '
                          'settings exactly')
        record(name, not problems, detail)
    except Exception as e:
        log.write_exc('frozen-session config audit failed')
        record(name, False, f'audit failed: {e!r}')


def pick_configs(requested):
    """Which session configs to drive fresh participants through.

    Default: one per recruitment profile actually present in settings — so the
    lab flow AND the prolific flow are both exercised, which is the point of
    the study-type axis. A config NAMED after its profile wins (the shipped
    'lab' and 'prolific' configs), otherwise the first config with that
    profile. --configs overrides entirely.
    """
    from settings import SESSION_CONFIGS
    by_name = {c['name']: c for c in SESSION_CONFIGS}
    if requested:
        chosen, missing = [], []
        for name in requested:
            (chosen if name in by_name else missing).append(name)
        return chosen, missing
    chosen = []
    for profile in sorted({c.get('recruitment') for c in SESSION_CONFIGS}):
        if profile in by_name and by_name[profile].get('recruitment') == profile:
            chosen.append(profile)
            continue
        for c in SESSION_CONFIGS:
            if c.get('recruitment') == profile:
                chosen.append(c['name'])
                break
    return chosen, []


def run_http_checks(server, log, degraded, config_names):
    """Checks 3-5, all over real HTTP against the server subprocess."""
    from otree.database import DBSession
    from otree.models import Participant

    builder = PayloadBuilder(log)

    def read_vars(code):
        """Fresh DBSession per read; reads happen between requests, while the
        server is idle, so the two processes never contend."""
        s = DBSession()
        try:
            return dict(s.query(Participant).filter_by(code=code).one().vars)
        finally:
            s.close()

    def server_errors_of(code):
        try:
            extra = read_vars(code).get('participant_extra') or {}
            return extra.get('server_errors') or []
        except Exception:
            return []

    def drive_one(code, payload_fn, label):
        # a fresh cookie jar per participant, like a fresh browser
        return drive(Browser(server.base_url), code, payload_fn, log=log,
                     server=server, server_errors_of=server_errors_of,
                     label=label)

    def err_lines(r):
        e = r['err']
        return [f"500 on page {e['page']} (status {e['status']})",
                f"exception(s): {'; '.join(e['exceptions'])}",
                f"pages walked before the failure: {r['visited'] or ['(none)']}"]

    # ---------------------------------------------------------------------
    # 3. RESUME an existing mid-flow participant (THE upgrade path)
    # ---------------------------------------------------------------------
    resume_name = '3. RESUME an existing mid-flow participant (upgrade path)'
    if degraded:
        record(resume_name, NOT_TESTED, [
            'NO DATABASE COPY WAS SUPPLIED, so there is no participant whose '
            'state predates this build.',
            'THE UPGRADE PATH WAS NOT TESTED. The two failure modes this check '
            'exists for (an unset participant-vars key; a session config frozen '
            'before a parameter existed) CANNOT occur for a fresh participant '
            'and are therefore not covered by anything above.',
            'Supply a copy of the live database to test them: '
            'scripts/predeploy_check.sh /tmp/db_live_copy.sqlite3'])
    else:
        try:
            s = DBSession()
            try:
                all_parts = s.query(Participant).order_by(Participant.id).all()
                midflow = [
                    dict(code=p.code, page=p._current_page_name, id=p.id)
                    for p in all_parts
                    if p.visited
                    and 0 < (p._index_in_pages or 0) < (p._max_page_index or 0)
                    and p._current_page_name not in TERMINAL_PAGES]
                unstarted = [dict(code=p.code, page='(not started)', id=p.id)
                             for p in all_parts if not p.visited]
            finally:
                s.close()

            def pref(c):
                page = c['page']
                rank = (RESUME_PREFERENCE.index(page)
                        if page in RESUME_PREFERENCE else len(RESUME_PREFERENCE))
                return (rank, -c['id'])

            midflow.sort(key=pref)
            detail, ok = [], False
            if not all_parts:
                detail = ['the database copy contains NO participants at all — '
                          'is this really a copy of the live database?']
            else:
                candidates = midflow[:5]
                if not midflow:
                    detail.append(
                        'no mid-flow participant found; falling back to an '
                        'UNSTARTED participant of an existing (old) session — '
                        'this still exercises old-session state under new code')
                    candidates = unstarted[:2]
                if not candidates:
                    detail.append('no resumable participant found in the '
                                  'database copy')
                for cand in candidates:
                    r = drive_one(cand['code'], builder.js,
                                  f"resume from {cand['page']}")
                    if r['err']:
                        detail += [f"existing participant {cand['code']} (was on "
                                   f"{cand['page']}):"] + err_lines(r)
                        ok = False
                        break
                    progressed = r['advances'] >= 3 or r['last'] in TERMINAL_PAGES
                    if progressed:
                        detail += [
                            f"resumed participant {cand['code']} from page "
                            f"{cand['page']}",
                            f"advanced {r['advances']} page(s): "
                            f"{r['visited'][:12]}"
                            f"{'...' if len(r['visited']) > 12 else ''}",
                            f"ended on {r['last']!r}, no 5xx across "
                            f"{len(r['statuses'])} requests (max status "
                            f"{max(r['statuses'])})"]
                        ok = True
                        break
                    detail.append(f"participant {cand['code']} could not advance "
                                  f"past {r['stuck_on']!r} (no 5xx; trying next "
                                  f"candidate)")
                else:
                    if candidates:
                        detail.append('no candidate could be driven several '
                                      'pages forward')
            record(resume_name, ok, detail)
        except Exception as e:
            log.write_exc('resume check failed')
            record(resume_name, False, f'check crashed: {e!r}')

    # ---------------------------------------------------------------------
    # 4 + 5. fresh participants per config: the JS flow, then the all-empty
    #        no-JS flow. Sessions are created IN THE COPY, never live.
    # ---------------------------------------------------------------------
    for config_name in config_names:
        fresh_name = f'4. FRESH participant, config {config_name!r} (entry -> end)'
        nojs_name = (f'5. NO-JS submits, config {config_name!r} '
                     f'(JS-produced hidden fields EMPTY)')
        fresh_codes = []
        try:
            from otree.database import db
            from otree.session import create_session
            session = create_session(config_name, num_participants=2)
            session_code = session.code
            db.commit()  # make the new session visible to the server process
            s = DBSession()
            try:
                fresh_codes = [p.code for p in s.query(Participant).filter_by(
                    _session_code=session_code).order_by(Participant.id).all()]
            finally:
                s.close()
        except Exception as e:
            log.write_exc(f'create_session({config_name!r}) failed')
            record(fresh_name, False,
                   f'could not create a fresh session in the database: {e!r}')
            record(nojs_name, False, 'skipped: no fresh session')
            continue

        try:
            code = fresh_codes[0]
            r = drive_one(code, builder.js, f'fresh JS flow ({config_name})')
            if r['err']:
                record(fresh_name, False, err_lines(r))
            else:
                v = read_vars(code)
                exit_code = v.get('exit_code')
                done = r['last'] == 'Results' and exit_code == 1
                record(fresh_name, done, [
                    f"walked {len(r['visited'])} pages: {r['visited'][:14]}"
                    f"{'...' if len(r['visited']) > 14 else ''}",
                    f"ended on {r['last']!r}, no 5xx across "
                    f"{len(r['statuses'])} requests (max status "
                    f"{max(r['statuses'])})",
                    f"exit_code recorded: {exit_code!r} (1 = finished)"]
                    + ([] if done else
                       [f"expected to end on 'Results' with exit_code 1; "
                        f"stuck_on={r['stuck_on']!r}"]))
        except Exception as e:
            log.write_exc(f'fresh flow ({config_name}) failed')
            record(fresh_name, False, f'check crashed: {e!r}')

        try:
            code = fresh_codes[1]
            r = drive_one(code, builder.nojs, f'fresh NO-JS flow ({config_name})')
            if r['err']:
                record(nojs_name, False,
                       err_lines(r) + [f"hidden fields posted EMPTY before the "
                                       f"failure: {r['blanked'] or ['(none)']}"])
            else:
                v = read_vars(code)
                exit_code = v.get('exit_code')
                # A page with no hidden fields at all would make this check
                # vacuous, so say how many were actually blanked.
                done = (r['last'] in TERMINAL_PAGES and exit_code is not None
                        and bool(r['blanked']))
                record(nojs_name, done, [
                    f"{len(r['blanked'])} hidden field submission(s) posted "
                    f"EMPTY: {r['blanked'][:12]}"
                    f"{'...' if len(r['blanked']) > 12 else ''}",
                    f"ended on {r['last']!r}, no 5xx across "
                    f"{len(r['statuses'])} requests (max status "
                    f"{max(r['statuses'])})",
                    f"exit_code recorded: {exit_code!r}"]
                    + ([] if done else
                       ['expected an end page reached with at least one hidden '
                        'field posted empty; '
                        f"stuck_on={r['stuck_on']!r}"]))
        except Exception as e:
            log.write_exc(f'no-JS flow ({config_name}) failed')
            record(nojs_name, False, f'check crashed: {e!r}')

    if builder.guessed:
        print('\n  note: fields filled by the generic model-driven filler '
              '(no template knowledge applies to them):')
        for f in sorted(builder.guessed):
            print(f'    - {f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-dir', required=True,
                    help='STAGED candidate build containing db.sqlite3')
    ap.add_argument('--src-app-dir', default='',
                    help='original checkout, used only for the live-DB guard')
    ap.add_argument('--log', required=True, help='server-log capture file')
    ap.add_argument('--degraded', action='store_true',
                    help='no live database was supplied: run the fresh-install '
                         'checks only and report the upgrade path NOT TESTED')
    ap.add_argument('--require-db', action='store_true',
                    default=bool(os.environ.get('PREDEPLOY_REQUIRE_DB')),
                    help='make a degraded run a FAILURE (use this in a deploy '
                         'pipeline for a study that has live sessions)')
    ap.add_argument('--debug', action='store_true',
                    help='drive the app with DEBUG on; the default is the '
                         'PRODUCTION shape, which is what you are deploying')
    ap.add_argument('--configs', default='',
                    help='comma-separated session configs for the fresh walks '
                         '(default: one per recruitment profile)')
    ap.add_argument('--assert-engine-on', action='store_true',
                    help='PROOF MODE, run by scripts/predeploy_check.sh BEFORE '
                         'it runs anything destructive: pin DATABASE_URL to the '
                         'staged database, prove oTree resolves to it, exit 0 '
                         'or 2. Runs no checks and writes nothing.')
    args = ap.parse_args()

    app_dir = os.path.realpath(args.app_dir)
    src_app_dir = os.path.realpath(args.src_app_dir or app_dir)
    db_path = staged_db_path(app_dir)
    log_path = os.path.abspath(args.log)

    # PROOF MODE. Deliberately ahead of the is-there-a-database check below:
    # the shell calls this BEFORE its degraded-mode `resetdb`, when the staged
    # file does not exist yet. That is the whole point — the proof has to come
    # before the destructive step, not after it.
    if args.assert_engine_on:
        assert_not_live(db_path, src_app_dir)
        os.chdir(app_dir)
        sys.path.insert(0, app_dir)
        pin_database_url(db_path)
        engine_file = assert_engine_on(db_path, context='pre-flight')
        print(f'predeploy_check: engine proof OK — oTree resolves to '
              f'{engine_file}')
        return

    if not os.path.isfile(db_path):
        print(f'FATAL: no database at {db_path} '
              f'(run via scripts/predeploy_check.sh, which stages it).')
        sys.exit(2)
    assert_not_live(db_path, src_app_dir)

    # The DEBUG axis for THIS process too (it imports the app). Production
    # shape by default — see ServerUnderTest.start for why, and note that oTree
    # reads OTREE_PRODUCTION as set-or-not, so blanking it is not unsetting it.
    if args.debug:
        os.environ.pop('OTREE_PRODUCTION', None)
    else:
        os.environ['OTREE_PRODUCTION'] = '1'
    os.environ.pop('OTREE_AUTH_LEVEL', None)
    os.environ.pop('OTREE_IN_MEMORY', None)

    # WHICH DATABASE: the staged build becomes both cwd (=> ./db.sqlite3 is the
    # copy) and the importable app — for this process AND the server subprocess
    # it launches. cwd is what actually binds oTree's sqlite engine, but it is
    # NOT relied on alone: an inherited `DATABASE_URL=postgres://…` would make
    # the cwd lever inert, so the URL is pinned here too (and a disagreeing one
    # is refused, not overridden in silence). Both must happen before oTree is
    # imported. Called even though the shell wrapper pins it as well — this
    # helper must be safe when run directly, which is how it is documented.
    os.chdir(app_dir)
    sys.path.insert(0, app_dir)
    pin_database_url(db_path)

    log = Log(log_path)
    server = ServerUnderTest(sys.executable, app_dir, log, debug=args.debug)
    atexit.register(server.stop)

    print(f'app under test : {app_dir}')
    print(f'database       : {db_path}'
          f'{"  (FRESH — degraded mode)" if args.degraded else "  (copy of live data)"}')
    print(f'server log     : {log_path}')

    booted = False
    config_names, missing = [], []
    try:
        booted = check_boot(server, log, db_path, args.degraded)
        if booted:
            check_schema(log, args.degraded)
            # BEFORE run_http_checks: that creates fresh sessions, which are
            # this build's own and must not pollute the frozen-config audit.
            check_frozen_session_configs(log, args.degraded)
            config_names, missing = pick_configs(
                [c.strip() for c in args.configs.split(',') if c.strip()])
            if missing:
                record('4. FRESH participant', False,
                       f'unknown session config(s) requested: {missing}')
                config_names = []
            print(f'\nsession configs driven fresh: {config_names}')
            run_http_checks(server, log, args.degraded, config_names)
    finally:
        log.write(END_SENTINEL)
        server.stop()
        log.close()
    finish(log_path, args.degraded, args.require_db, skip_rest=not booted)


def finish(log_path, degraded, require_db, skip_rest=False):
    if skip_rest:
        for name in ('2. SCHEMA (new models vs live data)',
                     '2b. FROZEN SESSION CONFIGS (existing sessions vs '
                     'current settings)',
                     '3. RESUME an existing mid-flow participant (upgrade path)',
                     '4. FRESH participant (entry -> end)',
                     '5. NO-JS submits (JS-produced hidden fields EMPTY)'):
            record(name, False, 'skipped: the app did not boot')

    # ---------------------------------------------------------------------
    # 6. LOG SCAN — grep the captured server log for 5xx / tracebacks /
    #    KeyError / TypeError, attributing each hit to the page in flight.
    #    Scanning stops at the sentinel so teardown noise cannot fail it.
    # ---------------------------------------------------------------------
    hits, page = [], '(before any request)'
    try:
        with open(log_path, errors='replace') as fh:
            for line in fh:
                if END_SENTINEL in line:
                    break
                m = re.search(
                    r'PREDEPLOY >> (?:POST (\S+)|InitializeParticipant (\S+))',
                    line)
                if m:
                    page = m.group(1) or f'InitializeParticipant/{m.group(2)}'
                    continue
                if re.search(r'PREDEPLOY 5XX|PREDEPLOY SCHEMA MISMATCH'
                             r'|Traceback \(most|\bKeyError\b|\bTypeError\b'
                             r'|Internal Server Error', line):
                    hits.append((page, line.strip()[:240]))
    except OSError as e:
        hits.append(('(log unreadable)', repr(e)))

    seen, uniq = set(), []
    for pg, line in hits:
        m = EXC_RE.search(line)
        key = (pg, m.group(1) if m else line[:60])
        if key not in seen:
            seen.add(key)
            uniq.append((pg, line))
    if uniq:
        detail = [f'{len(uniq)} distinct problem(s) in the server log:']
        detail += [f'  [page {pg}] {line}' for pg, line in uniq[:12]]
        detail.append(f'full log: {log_path}')
    else:
        detail = ['server log clean: no 5xx, no tracebacks, '
                  'no KeyError/TypeError']
    record('6. SERVER-LOG SCAN (5xx / Traceback / KeyError / TypeError)',
           not uniq, detail)

    # ---------------------------------------------------------------------
    # summary
    # ---------------------------------------------------------------------
    failed = [name for name, ok, _ in RESULTS if ok is False]
    untested = [name for name, ok, _ in RESULTS if ok is None]
    print('\n' + '=' * 74)
    print('PRE-DEPLOY UPGRADE CHECK — SUMMARY')
    print('=' * 74)
    for name, ok, _ in RESULTS:
        print(f'  [{_label(ok):^10}] {name}')
    print('-' * 74)

    if degraded:
        bar = '#' * 74
        print(bar)
        print('##  DEGRADED RUN — THE UPGRADE PATH WAS NOT TESTED.')
        print('##  No copy of a live database was supplied, so every check '
              'above ran')
        print('##  against a FRESH database. A fresh database CANNOT reproduce '
              'the two')
        print('##  failures this gate exists for:')
        print('##    - a participant-vars key that old participants never had;')
        print('##    - a session config frozen before a parameter existed.')
        print('##  Not tested here: ' + ('; '.join(untested) or '(none)'))
        print('##  Before deploying onto a database that HAS participants, '
              'rerun as:')
        print('##      scripts/predeploy_check.sh <copy-of-live-db.sqlite3>')
        print(bar)

    if failed:
        print(f'RESULT: FAIL ({len(failed)}/{len(RESULTS)} checks failed) — DO '
              f'NOT DEPLOY this build onto the live database.')
        for name in failed:
            print(f'  failed: {name}')
        print(f'Server log kept at: {log_path}')
        sys.exit(1)
    if degraded and require_db:
        print('RESULT: FAIL — the fresh-install checks passed, but --require-db '
              '(PREDEPLOY_REQUIRE_DB) was set and the UPGRADE PATH WAS NOT '
              'TESTED.')
        sys.exit(1)
    if degraded:
        print('RESULT: PASS (DEGRADED) — the fresh-install checks passed. '
              'THE UPGRADE PATH WAS NOT TESTED; this run says nothing about '
              'deploying onto existing participants.')
        sys.exit(0)
    print('RESULT: PASS — the new build survives the live data '
          '(upgrade path, fresh path, no-JS path all clean).')
    sys.exit(0)


if __name__ == '__main__':
    main()
