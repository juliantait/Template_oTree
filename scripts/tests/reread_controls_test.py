#!/usr/bin/env python
"""WHAT THE QUIZ PAGE OFFERS EACH STUDY TYPE — real HTTP, PRODUCTION mode.

    python scripts/tests/reread_controls_test.py

Boots oTree in-process against a THROWAWAY database, serves it with uvicorn on a
free port, and walks real participants to the quiz in both study types. Exits
non-zero on any failed check.

WHY IT BOOTS ITS OWN SERVER: the whole question here is what a page carries in
PRODUCTION. Against a DEBUG server the quiz renders a "Skip quiz (testing)"
button and a solutions blob, so a suite that inherited a debug server's mode
would measure the developer's page and report the opposite of the truth on the
one assertion that matters most below (see §A).

THE REPORT THIS EXISTS FOR (2026-08-21). Julian reported being "offered an
option to skip the instructions and the quiz" in a PROLIFIC session and not in a
LAB one. The prolific quiz page does carry one control the lab's does not — the
at-will "Re-read the instructions" button — and until this change it sat in the
RIGHTMOST slot of the button row, where the primary action belongs, which is
what made it read as the way on rather than a way to look something up. This
file pins what that control actually is:

  A. NEITHER study type is offered a skip of any kind in production.
  B. The at-will control is PROLIFIC-ONLY, and it is a DIALOG, not a submit.
  C. It cannot advance anybody, EVEN IF THE POST IS HAND-CRAFTED: a prolific
     participant who posts `redoinstructions=1` is refused the re-read pass,
     while a lab participant with the offer open is granted it. That pairing is
     the actual answer to "can they skip?", and neither half means anything
     alone.
  D. THE ORDER: the primary "Next" is the LAST control in the button row, and
     the secondary re-read comes before it. Asserted here as document order
     (which is also the TAB order); the rendered GEOMETRY is measured in
     `scripts/tests/render_check.py` leg AI.

TWO RE-READ MECHANISMS, NOT ONE. The lab's `quiz_reread` PASS and the online
at-will DIALOG are deliberately different things on deliberately different axes
(see `intro.at_will_reread_available`). This file asserts BOTH exist, each in
its own modality, so a future change that "unifies" them fails here rather than
silently leaving one modality with no way to re-read at all.

NEVER AN ABSENCE ALONE (CLAUDE.md): every "control X is not on this page" below
is paired with a control that IS, on that same page, plus proof the walker
actually reached the quiz.
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

# Throwaway database + PRODUCTION, both before oTree loads. (The db trap: oTree
# opens the RELATIVE name 'db.sqlite3' in the CWD at import and ignores the path
# in a sqlite DATABASE_URL. The mode trap: DEBUG is derived from the PRESENCE of
# OTREE_PRODUCTION, so '' would still mean production.)
_TMPDIR = tempfile.mkdtemp(prefix='tmpl_reread_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_TMPDIR, 'db.sqlite3')}"
os.environ['OTREE_PRODUCTION'] = '1'
os.environ.setdefault('OTREE_SECRET_KEY', 'reread-controls')

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
from otree.settings import DEBUG as OTREE_DEBUG  # noqa: E402

from http_flow_test import FormParser, build_payload  # noqa: E402
from quiz_answers import CORRECT, WRONG  # noqa: E402

REREAD_LABEL = 'Re-read the instructions'
LAB_OFFER_TITLE = 'Having trouble with the quiz?'

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def visible_text(html):
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<script\b.*?</script>', ' ', html, flags=re.S | re.I)
    html = re.sub(r'<style\b.*?</style>', ' ', html, flags=re.S | re.I)
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def button_row(html):
    """The quiz page's button row, comments stripped — the markup under test."""
    m = re.search(r'<div class="button-row">(.*?)</div>', html, re.S)
    if not m:
        return ''
    return re.sub(r'<!--.*?-->', ' ', m.group(1), flags=re.S)


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


def p_vars(p_code):
    s = DBSession()
    try:
        return dict(s.query(Participant).filter_by(code=p_code).one().vars)
    finally:
        s.close()


def walk_to_quiz(base, session, limit=40):
    """Enter through the real front door and stop on the quiz page."""
    s = requests.Session()
    r = s.get(f'{base}/join/{anon_code(session.code)}', allow_redirects=True)
    for _ in range(limit):
        if r.status_code >= 500:
            raise AssertionError(f'HTTP {r.status_code} at {r.url}')
        if page_of(r.url) == 'quiz':
            return s, r
        fp = FormParser()
        fp.feed(r.text)
        if not fp.found_form:
            raise AssertionError(f'dead end before the quiz at {r.url}')
        r = s.post(r.url, data=build_payload(fp.inputs, {}, dict(CORRECT),
                                             warn=False),
                   allow_redirects=True)
    raise AssertionError('never reached the quiz')


def post_quiz(s, r, data):
    fp = FormParser()
    fp.feed(r.text)
    payload = build_payload(fp.inputs, {}, {}, warn=False)
    payload.update(data)
    return s.post(r.url, data=payload, allow_redirects=True)


def run():
    server = Server()
    server.start()
    print(f'server on {server.base} (throwaway db in {_TMPDIR})')
    try:
        # ==================================================================
        section('A. PRODUCTION really is production, and nothing offers a skip')
        # ==================================================================
        # The precondition first, because every absence below depends on it: a
        # DEBUG page carries the skip buttons legitimately, so "no skip" would
        # be a statement about the server's mode, not about the study.
        check(OTREE_DEBUG is False,
              f'oTree DEBUG is off, so the testing affordances are not '
              f'rendered by definition (DEBUG={OTREE_DEBUG})')

        pages = {}
        for cfg in ('lab', 'prolific'):
            session = create_session(cfg, num_participants=2)
            s, r = walk_to_quiz(server.base, session)
            pages[cfg] = (session, s, r)
            text = visible_text(r.text)
            check(page_of(r.url) == 'quiz',
                  f'{cfg}: the walker reached the QUIZ page itself')
            check('Answer the questions below' in text,
                  f'{cfg}: …and the quiz rendered — not a blank page or '
                  f'another screen ({text[:70]!r})')
            check('Next' in button_row(r.text),
                  f'{cfg}: the primary "Next" control IS in the button row')
            check('Skip quiz' not in text and 'Skip instructions' not in text,
                  f'{cfg}: NO skip control of any kind is offered')

        # ==================================================================
        section('B. The at-will re-read is PROLIFIC-ONLY, and it is a DIALOG')
        # ==================================================================
        lab_html = pages['lab'][2].text
        pro_html = pages['prolific'][2].text

        check(REREAD_LABEL in visible_text(pro_html),
              f'prolific: the at-will control IS offered ({REREAD_LABEL!r})')
        check(REREAD_LABEL not in visible_text(lab_html),
              'lab: it is NOT — a lab participant has the supervised pass and '
              'an experimenter to ask (paired with the prolific presence above)')
        check('reread-backdrop' in pro_html and 'reread-backdrop' not in lab_html,
              'prolific carries the dialog markup and lab does not')

        # IT CANNOT SUBMIT. The button is type="button" and the dialog holds no
        # form control — that is the difference between "look at the
        # instructions" and "leave the quiz", and it is structure, so the raw
        # HTML is the right target.
        opener = re.search(r'<button[^>]*id="rereadOpen"[^>]*>', pro_html)
        check(opener is not None and 'type="button"' in opener.group(0),
              f'prolific: the opener is type="button" — it can never submit '
              f'the quiz form it sits inside ({opener.group(0) if opener else None})')
        # The dialog's own markup, sliced from its backdrop to the start of the
        # NEXT top-level block (the lab failure modals). A regex, not a parser,
        # because what is being asserted is the ABSENCE of a tag — so the slice
        # has to be visibly wide rather than cleverly narrow, and the paired
        # presence below is what proves it is not empty.
        start = pro_html.index('<div id="reread-backdrop"')
        end = pro_html.index('Lab quiz-failure modals', start)
        body = pro_html[start:end]
        check(body and not re.search(r'<input\b|<select\b|<textarea\b', body),
              'prolific: the dialog contains NO form control at all — nothing '
              'in it can advance the participant')
        check('modal-dismiss-button' in body and 'Back to the quiz' in body,
              '…and the only way out of it goes BACK TO THE QUIZ (paired '
              'presence: the dialog is not empty)')

        # ==================================================================
        section('C. THE ORDER: the primary is LAST in the row (tab order too)')
        # ==================================================================
        row = button_row(pro_html)
        i_reread = row.find('quiz-reread-btn')
        i_next = row.find('class="next-button"')
        check(-1 < i_reread < i_next,
              f'prolific: the secondary re-read ({i_reread}) comes BEFORE the '
              f'primary Next ({i_next}) in the markup — so the DOM order, the '
              f'tab order and the rendered order all agree')
        check('.button-row > .next-button:not(.ghost) { order: 1; }'
              in open(os.path.join(REPO_ROOT, '_static/global/css/base.css')).read(),
              'the rule is in the SHARED component (base.css), not patched '
              'onto this page')

        # ==================================================================
        section('D. CAN A PROLIFIC PARTICIPANT ACTUALLY SKIP? (hand-crafted POST)')
        # ==================================================================
        # The strongest form of the question, asked of the SERVER rather than of
        # the page: post the re-read flag directly, with wrong answers, and see
        # whether the study hands out a second pass. Both halves are needed —
        # "prolific is refused" is worthless without "lab is granted", which is
        # what proves the mechanism under test exists at all.
        _, s_pro, r_pro = pages['prolific']
        r2 = post_quiz(s_pro, r_pro, dict(WRONG, redoinstructions='1'))
        check(r2.status_code < 500,
              f'prolific: the hand-crafted POST does not 500 ({r2.status_code})')
        code_pro = urlparse(str(r_pro.url)).path.strip('/').split('/')[1]
        check(p_vars(code_pro).get('comprehension_reread_used') is not True,
              'prolific: `redoinstructions=1` did NOT consume a re-read pass — '
              'the module is off for this study type and the server says so, '
              'whatever the browser posts')
        check(page_of(r2.url) in ('quiz', 'Ended'),
              f'prolific: …and it did not jump them past the quiz '
              f'(now at {page_of(r2.url)})')

        # The lab half: fail to the threshold so the offer is genuinely open,
        # then take it.
        lab_sess, s_lab, r_lab = pages['lab']
        code_lab = urlparse(str(r_lab.url)).path.strip('/').split('/')[1]
        for _ in range(6):
            if LAB_OFFER_TITLE in visible_text(r_lab.text):
                break
            r_lab = post_quiz(s_lab, r_lab, dict(WRONG))
        check(LAB_OFFER_TITLE in visible_text(r_lab.text),
              f'lab: failing the quiz opens the one-time re-read OFFER '
              f'({LAB_OFFER_TITLE!r})')
        r_lab = post_quiz(s_lab, r_lab, {'redoinstructions': '1'})
        check(p_vars(code_lab).get('comprehension_reread_used') is True,
              'lab: taking it CONSUMES the pass — so the mechanism prolific was '
              'refused above is real, and the refusal is about the study type')
        check(page_of(r_lab.url) == 'instructing',
              f'lab: …and it sends them back through the instructions '
              f'(now at {page_of(r_lab.url)})')

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
