#!/usr/bin/env python3
"""Bot-detection feature tests (§10 of _ai/ai_bot_detection_spec.md).

Drives oTree IN-PROCESS in PRODUCTION mode (the switch a participant hits; the
disarm must work here, not only under DEBUG) via the ASGI TestClient — real HTTP
requests, real form POSTs, JS-filled hidden fields sent empty. Asserts PRESENCE
alongside every absence (an absence-only "not ejected" would pass against a study
that never armed the gate). Reads state back over the ORM (participant.vars).

Covered here (the automated half; the LIVE adversarial run is a separate later
step):
  1. ARMED prolific — the welcome decoy ejects -5/honeypot_welcome; a wrong
     DOT-BI answer ejects -5/dot_bi; a correct answer completes. Both ejections
     land on the ONE shared NeutralReturn screen and never reach intro.
  2. NO-JS DOT-BI — a JS-off submit is the gentle no_javascript (-6), never -5,
     with the nojs return code; a wrong-answer -5 carries the bot return code.
  3. DISARMED IN PRODUCTION — our bot testers (trip the decoy AND submit a wrong
     DOT-BI answer) reach intro and COMPLETE; the verdicts are still RECORDED.
  4. LAB INVISIBILITY — no DOT-BI page, no decoy control, never -5; but bucket-B
     (results checkbox, welcome/quiz telemetry) IS recorded in the lab.
  5. OPAQUE-ID GUARD — the answer number and any original filename are absent
     from the DOT-BI page; the media URL uses the opaque id.
  6. HONEYPOTS eyeball at participant level (0 / 1 / 10); the derived bot_* flags
     are NOT live participant fields.
  7. PRELAUNCH — armed default is clean; disarmed loud-fails; the explicit
     override lets it through with an acknowledged waiver.

Run:  python scripts/tests/bot_detection_test.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)     # DEBUG off — what a participant hits

import common                  # noqa: E402
import dot_bi                  # noqa: E402
import bot_walker              # noqa: E402
from quiz_answers import CORRECT as QUIZ_CORRECT  # noqa: E402
from main_contract import task_page_submits       # noqa: E402
from settings import EXIT_CODES  # noqa: E402

_failures = []


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        _failures.append(msg)


def section(t):
    print(f"\n=== {t} ===")


TERMINAL = {'Results', 'Ended', 'NeutralReturn'}


class FakeParticipant:
    """A dict-backed stand-in for a participant, so a live_method's record logic
    can be unit-tested without a websocket. oTree's participant syncs attribute
    access with its `vars` blob; this mimics just that (attribute set/get <->
    the same dict that `.vars` exposes), which is all common.* reads/writes."""
    def __init__(self, **kw):
        object.__setattr__(self, '_v', dict(kw))

    @property
    def vars(self):
        return self._v

    def __getattr__(self, name):
        return self._v.get(name)

    def __setattr__(self, name, value):
        self._v[name] = value


def set_stored_config(session, **kw):
    """Set keys on a session's STORED (frozen) config — used to make a disarmed
    session without a dedicated SESSION_CONFIG entry."""
    from otree.database import DBSession
    from otree.models import Session
    s = DBSession()
    try:
        row = s.query(Session).filter_by(code=session.code).one()
        cfg = dict(row.config)
        cfg.update(kw)
        row.config = cfg
        s.commit()
    finally:
        s.close()


def payload_for(page, code, *, decoy=False, dotbi='correct',
                tick_completed=True, welcome_blob='', quiz_blob=''):
    if page == 'welcome':
        p = {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
             'participant_id_url': '', 'telemetry_welcome': welcome_blob}
        if decoy:
            p['honeypot_welcome'] = 'on'      # an agent that ticks every control
        return p
    if page == 'ConfirmProlificID':
        return {'participant_id_external': 'bot-test'}
    if page == 'DotBiGate':
        if dotbi == 'nojs':
            return {'bot_dotbi_answer': '', 'bot_dotbi_js': '', 'bot_dotbi_ms': ''}
        return bot_walker.dotbi_payload(code, correct=(dotbi == 'correct'))
    if page == 'quiz':
        return dict(QUIZ_CORRECT, telemetry_quiz=quiz_blob)
    if page == 'Demographics':
        return {'age': '30', 'gender': 'Female', 'bank': 'NL91ABNA0417164300',
                'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''}
    if page == 'Feedback':
        return {'feedback': ''}
    return {**task_page_submits()}.get(page, {})


def drive(client, code, **opts):
    """Walk a participant to a terminal page; return (visited, htmls)."""
    visited, htmls = [], {}
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    for _ in range(80):
        if resp.status_code >= 500:
            visited.append(f'HTTP{resp.status_code}')
            break
        page = page_name_of(path_of(resp))
        if page is None:
            break
        visited.append(page)
        htmls[page] = resp.text
        if page in TERMINAL:
            break
        resp = client.post(path_of(resp),
                           data=payload_for(page, code, **opts),
                           allow_redirects=True)
    return visited, htmls


def new_prolific(**stored):
    s = ot.create_session('prolific', num_participants=6)
    if stored:
        set_stored_config(s, **stored)
    return s, ot.participant_codes(s)


def main():
    client = ot.client()

    # ----------------------------------------------------------------------
    section('1. ARMED prolific — the welcome decoy EJECTS gently (-5)')
    s, codes = new_prolific()
    visited, htmls = drive(client, codes[0], decoy=True)
    v = ot.participant_vars(codes[0])
    check(v.get('exit_code') == EXIT_CODES['bot_return'],
          f"welcome decoy trip -> exit bot_return (-5) (got {v.get('exit_code')!r})")
    check(v.get('bot_detection_cause') == 'honeypot_welcome',
          f"cause is honeypot_welcome (got {v.get('bot_detection_cause')!r})")
    check(v.get('honeypot_welcome_failed') == 1,
          f"honeypot_welcome_failed == 1 (got {v.get('honeypot_welcome_failed')!r})")
    check(v.get('bot_flag') == 'screened',
          f"bot_flag == 'screened' (got {v.get('bot_flag')!r})")
    check(visited and visited[-1] == 'NeutralReturn',
          f"landed on the shared NeutralReturn screen (path {' -> '.join(visited)})")
    check('instructing' not in visited,
          "and NEVER reached intro (no cell spent)")

    section('1b. ARMED prolific — a WRONG DOT-BI answer EJECTS gently (-5/dot_bi)')
    visited, htmls = drive(client, codes[1], dotbi='wrong')
    v = ot.participant_vars(codes[1])
    check(v.get('exit_code') == EXIT_CODES['bot_return'],
          f"wrong DOT-BI -> exit bot_return (-5) (got {v.get('exit_code')!r})")
    check(v.get('bot_detection_cause') == 'dot_bi',
          f"cause is dot_bi — distinct from the welcome decoy (got {v.get('bot_detection_cause')!r})")
    check(v.get('bot_dotbi_passed') is False,
          f"bot_dotbi_passed recorded False (got {v.get('bot_dotbi_passed')!r})")
    check(v.get('exit_code') != EXIT_CODES['no_javascript'],
          "and it is NOT the no_javascript code")
    check(visited and visited[-1] == 'NeutralReturn' and 'instructing' not in visited,
          f"hard stop to NeutralReturn, no retry, never reached intro (path {' -> '.join(visited)})")
    nr = htmls.get('NeutralReturn', '')
    check('no penalty' in nr and 'Return to Prolific' in nr,
          "NeutralReturn shows the no-punishment message AND a prominent RETURN button")
    check('RETURN-XXXXXX_REPLACE' in nr,
          "the RETURN button carries the bot-return completion code")

    section('1c. ARMED prolific — a CORRECT DOT-BI answer COMPLETES')
    visited, htmls = drive(client, codes[2])
    v = ot.participant_vars(codes[2])
    check(v.get('bot_dotbi_passed') is True,
          f"bot_dotbi_passed True (got {v.get('bot_dotbi_passed')!r})")
    check(v.get('exit_code') == EXIT_CODES['finished'] and visited[-1] == 'Results',
          f"reached the finished ending (exit {v.get('exit_code')!r}, path ...{visited[-3:]})")

    # ----------------------------------------------------------------------
    section('2. NO-JS DOT-BI — the gentle no_javascript return (-6), never -5')
    visited, htmls = drive(client, codes[3], dotbi='nojs')
    v = ot.participant_vars(codes[3])
    check(v.get('exit_code') == EXIT_CODES['no_javascript'],
          f"JS-off DOT-BI -> exit no_javascript (-6) (got {v.get('exit_code')!r})")
    check(v.get('exit_code') != EXIT_CODES['bot_return'],
          "and NEVER the bot return code (-5) — a capability fact, not a bot signal")
    check(visited and visited[-1] == 'NeutralReturn',
          f"same gentle NeutralReturn screen (path {' -> '.join(visited)})")
    nr = htmls.get('NeutralReturn', '')
    check('NOJS-XXXXXX_REPLACE' in nr,
          "the RETURN button carries the no-JS completion code, not the bot one")

    # ----------------------------------------------------------------------
    section('3. DISARMED IN PRODUCTION — bot testers pass through, verdicts recorded')
    s, codes = new_prolific(bot_detection_armed=False)
    visited, htmls = drive(client, codes[0], decoy=True, dotbi='wrong')
    v = ot.participant_vars(codes[0])
    check('instructing' in visited,
          f"a walker that trips the decoy AND fails DOT-BI still REACHES intro (path {' -> '.join(visited[:8])} …)")
    check(v.get('exit_code') == EXIT_CODES['finished'],
          f"and COMPLETES (exit finished) — no -5, no -6 (got {v.get('exit_code')!r})")
    check(v.get('honeypot_welcome_failed') == 1 and v.get('bot_dotbi_passed') is False,
          "the verdicts are STILL RECORDED (welcome trip 1, dotbi False) even disarmed")
    check(v.get('bot_flag') == 'flag',
          f"bot_flag == 'flag' (recorded, not screened) (got {v.get('bot_flag')!r})")

    # ----------------------------------------------------------------------
    section('4. LAB INVISIBILITY + bucket-B still recorded in the lab')
    labs = ot.create_session('lab', num_participants=4)
    lcodes = ot.participant_codes(labs)
    # A clean lab walk, posting a telemetry blob on welcome & quiz, ticking the box.
    visited, htmls = drive(client, lcodes[0],
                           welcome_blob='{"keydown_count":3,"key_times":[0,200,400]}',
                           quiz_blob='{"keydown_count":4,"key_times":[0,210,420,650]}')
    v = ot.participant_vars(lcodes[0])
    check('DotBiGate' not in visited,
          "the lab renders NO DOT-BI page (bucket A inert)")
    check('honeypot_welcome' not in htmls.get('welcome', ''),
          "and NO welcome decoy control in the consent page HTML")
    check(v.get('exit_code') == EXIT_CODES['finished'] and visited[-1] == 'Results',
          f"the normal lab flow still completes (paired presence; path ...{visited[-3:]})")
    check(v.get('exit_code') != EXIT_CODES['bot_return'],
          "the lab never writes a bot return code")
    # BUCKET B — the results-stage checkbox honeypot. It lives ON the terminal
    # Results page as a LIVE-DATA field (no form submit), so the DEFAULT is the
    # TRIP: reaching Results records 10, and only a socket-pushed TICK records 0.
    # This walker never pushes a tick (it is a form walker, not a browser), so a
    # completer here lands at the default 10 — exactly a participant who did not
    # tick. The visible "Completed" checkbox IS rendered in the LAB (bucket B is
    # not inert there).
    check(v.get('honeypot_results_failed') == 10,
          f"bucket B: reaching Results defaults the honeypot to the trip 10 "
          f"(un-pushed) (got {v.get('honeypot_results_failed')!r})")
    check('id="results_completed"' in htmls.get('Results', ''),
          "the 'Completed' checkbox is rendered on the lab Results page (bucket B present)")
    check(v.get('telemetry_welcome') and v.get('telemetry_quiz'),
          "bucket B: telemetry_welcome AND telemetry_quiz fill in the LAB")
    check(v.get('exit_code') == EXIT_CODES['finished'],
          "and it NEVER ejects — record-only, a completer still finishes")
    # The COMPLIANT push (ticked -> 0) rides the websocket, which a form walker
    # cannot drive, so test the live_method's record logic directly on a
    # dict-backed fake participant: a pushed tick records 0, an un-tick records
    # the trip 10 (record-only either way). This is the SAME live channel the tab
    # monitor uses (outro.results_live_method delegates to it for other messages).
    import outro as _outro, types as _t
    fp = FakeParticipant(exit_code=EXIT_CODES['finished'], honeypot_results_failed=10)
    fpl = _t.SimpleNamespace(participant=fp,
                             session=_t.SimpleNamespace(config={'recruitment': 'lab'}))
    _outro.results_live_method(fpl, {'type': 'results_completed', 'value': True})
    check(fp.vars['honeypot_results_failed'] == 0,
          "results_live_method: a pushed TICK records 0 (compliant)")
    _outro.results_live_method(fpl, {'type': 'results_completed', 'value': False})
    check(fp.vars['honeypot_results_failed'] == 10,
          "results_live_method: an un-tick records the trip 10 (record-only, never ejects)")

    # ----------------------------------------------------------------------
    section('5. OPAQUE-ID GUARD — the answer/number never reaches the client')
    s, codes = new_prolific()
    # GET the DOT-BI page for a participant and inspect its HTML.
    resp = client.get(f'/InitializeParticipant/{codes[0]}', allow_redirects=True)
    dot_html = ''
    for _ in range(20):
        page = page_name_of(path_of(resp))
        if page == 'DotBiGate':
            dot_html = resp.text
            break
        if page in TERMINAL or page is None:
            break
        resp = client.post(path_of(resp), data=payload_for(page, codes[0]),
                           allow_redirects=True)
    variant = dot_bi.choose_variant(codes[0])
    answer = dot_bi.answer_for(variant)
    check(bool(dot_html), "reached and captured the DOT-BI page HTML")
    check(str(answer) not in dot_html,
          f"the hidden number ({answer}) is ABSENT from the page HTML")
    check(variant in dot_html,
          f"the OPAQUE variant id ({variant}) IS the served image reference")
    check('answers.json' not in dot_html,
          "no reference to the server-side answer key leaks into the page")
    check('/_ai/' not in dot_html and 'dotbi_bundle' not in dot_html,
          "no original bundle path leaks into the page")

    # ----------------------------------------------------------------------
    section('6. Honeypots eyeball at participant level; no live derived flags')
    # A prolific completer who left the welcome decoy untouched: welcome honeypot
    # 0. The results honeypot defaults to the trip 10 on reaching Results (a form
    # walker never pushes the compliant tick over the socket) — that IS the
    # eyeball property: the results column is a block of 10s among completers,
    # cleared to 0 only by an active tick, and 0-for-a-non-completer means "never
    # reached" (cross-check exit_code).
    visited, _ = drive(client, codes[1])
    vc = ot.participant_vars(codes[1])
    check(vc.get('honeypot_welcome_failed') == 0,
          f"welcome decoy left untouched eyeballs as 0 (got {vc.get('honeypot_welcome_failed')!r})")
    check(vc.get('honeypot_results_failed') == 10,
          f"a completer who never pushed a tick sits at the results default 10 "
          f"(got {vc.get('honeypot_results_failed')!r})")
    check(not any(k.startswith('bot_welcome_') or k.startswith('bot_quiz_') for k in vc),
          "no DERIVED bot_<page>_* telemetry flag is written LIVE (those are downstream)")
    check('telemetry_welcome' in vc and 'telemetry_quiz' in vc,
          "only the RAW telemetry blobs are live participant fields")

    # ----------------------------------------------------------------------
    section('7. PRELAUNCH — armed clean; disarmed loud-fails; override waives')
    import settings as st
    def has_disarm_problem():
        return any('bot_detection_armed' in p[0] for p in st._prelaunch_problems())
    os.environ.pop('ALLOW_DISARMED_BOT_DETECTION', None)
    check(not has_disarm_problem(),
          "the ARMED default (shipped configs) produces NO disarm problem")
    st.SESSION_CONFIGS.append(dict(
        name='_botdev_probe', recruitment='prolific', bot_detection_armed=False,
        app_sequence=['before', 'intro', 'main', 'outro'], num_demo_participants=2))
    try:
        check(has_disarm_problem() and st._disarmed_waiver_line() is None,
              "a disarmed config LOUD-FAILS the prelaunch check (no waiver without the override)")
        os.environ['ALLOW_DISARMED_BOT_DETECTION'] = '1'
        check(not has_disarm_problem() and st._disarmed_waiver_line() is not None,
              "the explicit override turns it into an acknowledged waiver line, exit clean")
    finally:
        st.SESSION_CONFIGS.pop()
        os.environ.pop('ALLOW_DISARMED_BOT_DETECTION', None)

    print("\n=== SUMMARY ===")
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for m in _failures:
            print(f"    - {m}")
        return 1
    print("  ALL CHECKS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
