#!/usr/bin/env python
"""THE ENDING PAGE'S COPY, over real HTTP, in PRODUCTION mode, both study types.

    LD_LIBRARY_PATH=... not needed — this suite is pure `requests`.
    python scripts/tests/ending_copy_test.py

It boots oTree in-process against a THROWAWAY database, serves it with uvicorn on
a free port, and walks a real participant all the way to the Results page in four
configurations. Exits non-zero on any failed check.

WHY IT BOOTS ITS OWN SERVER instead of taking a base URL like its neighbours.
A suite pointed at an externally started server inherits that server's MODE
(CLAUDE.md, Testing standard): against a DEBUG server, oTree's `vars_for_template`
debug panel dumps every template variable at the foot of the page, so
`is_lab=False` and the copy it gates are both in the HTML of a page the
participant never sees that way. A leak test run there measures the debug panel.
`OTREE_PRODUCTION` is set below, before oTree loads, so the mode cannot be
inherited or forgotten.

WHAT IS UNDER TEST (both added 2026-08-21; see DECISIONS.md)

  1. "Please leave up to 2 weeks for the payment to be processed" is a LAB
     sentence. The lab collects an IBAN and the institution transfers weeks
     later; a Prolific participant is paid through Prolific, so the sentence is
     false for them. Gated on the STUDY TYPE axis (`is_lab`).

  2. "Please click the button below to complete the study and return to
     Prolific" is CENTRED and sits directly under the receipt, above the
     completion button — not buried under the payment notes and the payoff
     table. The centring itself is geometry and is measured in
     `scripts/tests/render_check.py` leg AH; what is asserted HERE is the
     DOCUMENT ORDER and the presence of the shared `.closing-instruction`
     class the render leg measures.

NEVER AN ABSENCE ON ITS OWN (CLAUDE.md, Testing standard). Every "this sentence
is not on the page" below is paired with:

  * the matching PRESENCE — the same sentence asserted on the study type that
    must have it, on the same page of the same walk; and
  * proof the walker REACHED THE ENDING rather than being screened out or stalled
    earlier: the page is `Results`, its receipt renders, and the participant's
    numeric exit code is `finished`. An absence-only check passes against the
    consent page, the screen-out page and a blank response alike.

THE FLAGS ARE NOT THE STUDY TYPE, and rows 3 and 4 are the whole point of the
table: `prolific_completion_redirects` is MECHANICS (is there a way back?) while
`recruitment` decides COPY (docs/conventions.md). A prolific friend test with the
redirects off must still not be promised a bank transfer, and a lab session with
the redirects on must still get its payment line. Gating the payment sentence on
the nearest available flag would pass a two-row version of this table and fail
these two.
"""
import os
import re
import socket
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# --- throwaway database, PRODUCTION mode (both before oTree loads) -----------
# The db trap: oTree opens the RELATIVE name 'db.sqlite3' in the CURRENT
# directory at import time and ignores the path inside a sqlite DATABASE_URL, so
# `otree.database` is imported while chdir'd into the temp dir and the working
# directory is put back afterwards (_static/ and the template roots are equally
# CWD-relative). The mode trap: settings.py derives DEBUG from the PRESENCE of
# OTREE_PRODUCTION, so '' would still mean production — set it to '1'.
_TMPDIR = tempfile.mkdtemp(prefix='tmpl_ending_copy_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_TMPDIR, 'db.sqlite3')}"
os.environ['OTREE_PRODUCTION'] = '1'
os.environ.setdefault('OTREE_SECRET_KEY', 'ending-copy-check')

os.chdir(_TMPDIR)
import otree.database  # noqa: E402
os.chdir(REPO_ROOT)

import otree.main as otree_main  # noqa: E402
otree_main.setup()

from otree.database import engine, AnyModel, DBSession  # noqa: E402
AnyModel.metadata.create_all(engine)

import requests  # noqa: E402
import uvicorn  # noqa: E402
from otree.asgi import app  # noqa: E402
from otree.models import Participant, Session  # noqa: E402
from otree.session import create_session  # noqa: E402

from http_flow_test import FormParser, build_payload  # noqa: E402
# The quiz answered from the shipped items — the ONE derivation (quiz_answers.py).
# In production the page carries no solutions, so a walker that read them off the
# page would fail the quiz and, with `quiz_comprehension_dq` on for prolific, land
# on the comprehension-DQ ending instead of the Results page. That ending is also
# an ending, which is exactly why the exit code is asserted below.
from quiz_answers import CORRECT as QUIZ_CORRECT  # noqa: E402
from settings import EXIT_CODES  # noqa: E402

# The lab collects bank details and demographics; supply values that satisfy the
# form so the walk reaches Results instead of looping on a validation error.
LAB_ANSWERS = {'age': '30', 'gender': 'Female',
               'bank': 'NL91ABNA0417164300',
               'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''}

# The two sentences under test, as a participant reads them (whitespace
# collapsed — body copy wraps across source lines, so the raw source is not a
# contiguous match).
PAYMENT_LINE = 'Please leave up to 2 weeks for the payment to be processed.'
CLOSING_LINE = ('Please click the button below to complete the study and '
                'return to Prolific.')
# Proof the page really is the results page and really rendered: the receipt.
RECEIPT_GREETING = "Thank you, you're all done."
RECEIPT_TOTAL = 'Total earned'

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def visible_text(html):
    """What a participant actually reads: comments, <script>/<style> bodies and
    tags stripped, whitespace collapsed."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<script\b.*?</script>', ' ', html, flags=re.S | re.I)
    html = re.sub(r'<style\b.*?</style>', ' ', html, flags=re.S | re.I)
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


# --------------------------------------------------------------------------
# a real server on a real socket
# --------------------------------------------------------------------------
def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    def __init__(self):
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        cfg = uvicorn.Config(app, host='127.0.0.1', port=self.port,
                             log_level='error', lifespan='on')
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self):
        self._thread.start()
        deadline = time.time() + 30
        while time.time() < deadline:
            if getattr(self._server, 'started', False):
                return
            time.sleep(0.05)
        raise RuntimeError('uvicorn did not start')

    def stop(self):
        self._server.should_exit = True
        self._thread.join(timeout=10)


def anon_code(session_code):
    s = DBSession()
    try:
        return s.query(Session).filter_by(code=session_code).one()._anonymous_code
    finally:
        s.close()


def page_of(url):
    parts = urlparse(str(url)).path.strip('/').split('/')
    return parts[3] if len(parts) >= 5 and parts[0] == 'p' else None


def code_of(url):
    parts = urlparse(str(url)).path.strip('/').split('/')
    return parts[1] if len(parts) >= 3 and parts[0] == 'p' else None


def exit_code_of(p_code):
    """The participant's numeric outcome, read from the server's own record.

    THE POSITIVE HALF of every absence assertion below: it says the walk reached
    the ending it claims to have reached, not merely *an* ending. `finished` (1)
    is the only code the Results page writes; a screen-out, a comprehension DQ
    and an abandoned walk all carry their own.
    """
    s = DBSession()
    try:
        return s.query(Participant).filter_by(code=p_code).one().vars.get('exit_code')
    finally:
        s.close()


def walk_to_results(base, session, limit=90):
    """Enter through the real front door and post pages until Results."""
    s = requests.Session()
    r = s.get(f'{base}/join/{anon_code(session.code)}', allow_redirects=True)
    answers = dict(LAB_ANSWERS, **QUIZ_CORRECT)
    for _ in range(limit):
        if r.status_code >= 500:
            raise AssertionError(f'HTTP {r.status_code} at {r.url}\n{r.text[:600]}')
        if page_of(r.url) == 'Results':
            return code_of(r.url), r
        fp = FormParser()
        fp.feed(r.text)
        if not fp.found_form:
            raise AssertionError(f'dead end (no form, not Results) at {r.url}')
        r = s.post(r.url, data=build_payload(fp.inputs, {}, answers, warn=False),
                   allow_redirects=True)
    raise AssertionError(f'never reached Results; stuck at {r.url}')


# --------------------------------------------------------------------------
# the scenario table
# --------------------------------------------------------------------------
# `payment` — must the lab payment sentence be on the page?
# `closing` — must the "click the button below" sentence be on the page?
#             (that one IS the redirect flag's business: no button, no sentence)
SCENARIOS = [
    dict(label='lab                (the shipped lab profile)',
         config='lab', modified=None, payment=True, closing=False),
    dict(label='prolific           (the shipped online profile)',
         config='prolific', modified=None, payment=False, closing=True),
    # THE FLAG IS NOT THE STUDY TYPE — the two rows that a payment sentence
    # gated on the nearest module flag would fail. See the module docstring.
    dict(label='prolific, redirects OFF (a friend test)',
         config='prolific', modified={'prolific_completion_redirects': False},
         payment=False, closing=False),
    dict(label='lab, redirects ON       (a lab study wired to a code)',
         config='lab', modified={'prolific_completion_redirects': True},
         payment=True, closing=True),
]


def run():
    server = Server()
    server.start()
    print(f'server on {server.base} (PRODUCTION mode, throwaway db in {_TMPDIR})')
    try:
        for row in SCENARIOS:
            section(f'{row["label"]}')
            session = create_session(
                row['config'], num_participants=2,
                modified_session_config_fields=row['modified'])
            p_code, resp = walk_to_results(server.base, session)
            html = resp.text
            text = visible_text(html)

            # ---- THE WALKER REACHED THE ENDING (the positive half) ----------
            check(page_of(resp.url) == 'Results',
                  f'reached the Results page itself (page={page_of(resp.url)})')
            check(RECEIPT_GREETING in text and RECEIPT_TOTAL in text,
                  'the receipt rendered — the page is not blank and not another '
                  f'ending ({RECEIPT_GREETING!r} + {RECEIPT_TOTAL!r})')
            code = exit_code_of(p_code)
            check(code == EXIT_CODES['finished'],
                  f'exit_code={code} is `finished` ({EXIT_CODES["finished"]}) — '
                  f'not screened out, not disqualified, not abandoned')

            # ---- FIX 1: the payment sentence follows the STUDY TYPE ----------
            if row['payment']:
                check(PAYMENT_LINE in text,
                      f'the LAB payment line IS on the page ({PAYMENT_LINE!r})')
            else:
                check(PAYMENT_LINE not in text,
                      'the lab payment line is ABSENT — Prolific pays through '
                      'Prolific, so "up to 2 weeks" is not merely redundant '
                      'here, it is false')
                check('2 weeks' not in text,
                      '…and no reworded remnant of it survives either '
                      '(no "2 weeks" anywhere a participant can read)')

            # ---- FIX 2: the closing instruction, and WHERE it sits -----------
            if row['closing']:
                check(CLOSING_LINE in text,
                      f'the closing instruction IS on the page ({CLOSING_LINE!r})')
                # STRUCTURE, so the raw HTML is the right target (writing_tests).
                check('class="section-text closing-instruction"' in html,
                      'it carries the SHARED centring component '
                      '(.section-text .closing-instruction) — the class '
                      "render_check's leg AH measures, and the same one "
                      'outro/Ended.html uses')
                # ORDER IS ANCHORED ON THE SENTENCE ITSELF, not on the class:
                # a future edit that drops `.closing-instruction` must fail the
                # class check above and still be MEASURED here, rather than
                # exploding this leg with a ValueError from `.index`.
                i_greeting = html.find(RECEIPT_GREETING)
                i_total = html.rfind('payout-line total')
                i_line = html.find('Please click the button below')
                i_button = html.find('button-row')
                i_notes = html.find('results-notes')
                i_table = html.find('results-section')
                check(-1 < i_greeting < i_total < i_line < i_button,
                      f'DOCUMENT ORDER: thanks({i_greeting}) < receipt '
                      f'total({i_total}) < closing instruction({i_line}) < '
                      f'completion button({i_button})')
                # …and it is no longer below the payment notes and the table,
                # which is where it used to sit.
                check(-1 < i_line < i_notes and i_line < i_table,
                      f'it is ABOVE the payment notes({i_notes}) and the payoff '
                      f'table({i_table}), not buried under them')
            else:
                check(CLOSING_LINE not in text,
                      'no closing instruction, because there is no completion '
                      'button to point at')
                check('closing-instruction' not in html,
                      '…and the component is not rendered empty either')

    finally:
        server.stop()

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(run())
