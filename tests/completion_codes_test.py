#!/usr/bin/env python3
"""One journey per ending population, each asserting ITS OWN code and NOT the other four.

WHY ONE TEST PER PATH RATHER THAN ONE TEST WITH FIVE ASSERTIONS. The thing that
can go wrong is not "the wrong string was formatted" — it is **a page seeing a
code it has no business seeing**, which happens when a template gets handed the
whole config instead of one server-chosen value. That failure is invisible unless
each ending is driven for real, to the page a participant actually lands on, and
then checked for the ABSENCE of the four codes belonging to other populations.

THE DECISION BEING PROTECTED (DECISIONS.md, 2026-08-15). Every ending population
has its own completion code, because a shared code COLLAPSES TWO POPULATIONS
IRREVERSIBLY on Prolific's side: once a comprehension failure and a tab-monitor
ejection have both submitted under one `DQ-` code, the submission list cannot
tell them apart and nothing downstream recovers it. The five:

    prolific_cc_code         completed          -> auto-approve
    prolific_noconsent_code  declined consent   -> request return
    prolific_dq_quiz_code    comprehension DQ   -> request return
    prolific_dq_tab_code     tab-monitor DQ     -> request return
    prolific_device_code     device screen-out  -> request return

THE LEAK THAT MATTERS. A disqualified participant who can read the COMPLETED
code out of the page source can self-approve on Prolific and be paid. That is
money, not tidiness — so every path asserts the absence of all four others, not
just of the completed one.

Run:  LD_LIBRARY_PATH=<sysroot>/root/usr/lib/x86_64-linux-gnu \\
      python3 tests/completion_codes_test.py
(headless Chromium without root: docs/headless_chromium_recipe.md)
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, _APP_ROOT)
os.environ.setdefault('OTREE_PRODUCTION', '1')

FAILURES = []

CODE_KEYS = ('prolific_cc_code', 'prolific_noconsent_code',
             'prolific_dq_quiz_code', 'prolific_dq_tab_code',
             'prolific_device_code')


def check(ok, label):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(label)
    return ok


def section(t):
    print(f"\n=== {t} ===")


def assert_only_its_own(page_text, own_key, D, where):
    """The whole point of the file: its own code present, the other four absent."""
    check(D[own_key] in page_text,
          f'{where}: carries its OWN code ({own_key})')
    for other in CODE_KEYS:
        if other == own_key:
            continue
        check(D[other] not in page_text,
              f'{where}: does NOT carry {other}')


def main():
    from render_check import Server, VIEWPORTS
    from playwright.sync_api import sync_playwright
    import settings as _settings
    from otree.session import create_session
    from otree.database import db
    import common

    D = _settings.SESSION_CONFIG_DEFAULTS
    server = Server()
    server.start()
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as exc:
                print(f'headless Chromium did not launch ({exc}).\n'
                      f'See docs/headless_chromium_recipe.md')
                return 2

            def fresh_page(**ctx):
                context = browser.new_context(
                    viewport=VIEWPORTS['laptop_1280x720'], **ctx)
                return context, context.new_page()

            def body(page):
                # The RENDERED page plus its links: a code can hide in an href
                # as easily as in the copy, and the href is where it matters.
                hrefs = page.evaluate(
                    "() => Array.from(document.querySelectorAll('a'))"
                    ".map(a => a.getAttribute('href') || '').join(' ')")
                return (page.inner_text('body') or '') + ' ' + hrefs

            # ---------------------------------------------------------------
            section('1. DEVICE SCREEN-OUT — the entry gate, on a phone')
            # Its own path: never reaches the outro at all. The way out is the
            # device completion URL, built from prolific_device_code.
            # allowed_devices=['computer'] is what MAKES a phone a screen-out;
            # without it the gate admits every device and case 1 tests nothing.
            s = create_session('prolific', num_participants=4,
                               modified_session_config_fields={
                                   'allowed_devices': ['computer']})
            db.commit()
            codes = [p.code for p in s.get_participants()]
            context, page = fresh_page(
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                           'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                           'Version/17.0 Mobile/15E148 Safari/604.1')
            page.goto(f'{server.base}/InitializeParticipant/{codes[0]}',
                      wait_until='load')
            page.wait_for_timeout(300)
            txt = body(page)
            check('computer' in txt.lower() or 'phone' in txt.lower(),
                  'the phone is held at the screen-out page')
            assert_only_its_own(txt, 'prolific_device_code', D,
                                'device screen-out')
            context.close()

            # ---------------------------------------------------------------
            section('2. DECLINED CONSENT')
            context, page = fresh_page()
            page.goto(f'{server.base}/InitializeParticipant/{codes[1]}',
                      wait_until='load')
            page.wait_for_timeout(200)
            # Answer the consent question "no" and submit.
            page.evaluate("""() => {
                const no = document.querySelector('input[name="consent"][value="False"]');
                if (no) no.checked = true;
            }""")
            page.evaluate("() => document.querySelector('form').requestSubmit()")
            page.wait_for_timeout(800)
            txt = body(page)
            assert_only_its_own(txt, 'prolific_noconsent_code', D,
                                'declined consent')
            context.close()

            # ---------------------------------------------------------------
            section('3. COMPREHENSION DQ and 4. TAB-MONITOR DQ')
            s_dq = create_session('prolific', num_participants=2)
            db.commit()
            # Both endings are the same PAGE with a different cause, which is
            # exactly why they must not share a code — the page is where a
            # shared value would silently serve two populations.
            for key, flag, label, exit_name in (
                    ('prolific_dq_quiz_code', 'comprehension_disqualified',
                     'comprehension DQ', 'comprehension'),
                    ('prolific_dq_tab_code', 'ai_safety_disqualified',
                     'tab-monitor DQ', 'tab_monitor')):
                # WALK THEM PAST CONSENT FIRST. Setting the flag on a
                # participant still sitting at the consent page does not put
                # them on the ending — the flow routes forward from where they
                # ARE, so the flag alone left them at consent and the ending was
                # never rendered. (That is how this test first reported "does
                # not carry its own code": the page under test was the wrong
                # page.) Walk the real journey, THEN disqualify, then ask for
                # the next page.
                import requests as _rq
                from http_flow_test import FormParser as _FP, build_payload as _bp
                from gated_flow_test import RIGHT as _RIGHT
                # A SESSION WITHOUT the device restriction. Case 1's session
                # only admits `computer`, and the HTTP walker's User-Agent
                # (`python-requests/...`) classifies as `unknown` — so these two
                # were being SCREENED OUT at entry instead of walking the
                # journey. The codes still came out right, which is precisely
                # why the walk itself is asserted: without that check the case
                # would have been passing against the wrong page.
                pp = s_dq.get_participants()[0 if 'quiz' in key else 1]
                sess = _rq.Session()
                r = sess.get(f'{server.base}/InitializeParticipant/{pp.code}',
                             allow_redirects=True)
                for _ in range(40):
                    if '/main/' in r.url or '/outro/' in r.url:
                        break
                    fp = _FP(); fp.feed(r.text)
                    r = sess.post(r.url,
                                  data=_bp(fp.inputs, {'consent': 'True', **_RIGHT},
                                           {}, warn=False),
                                  allow_redirects=True)
                check('/main/' in r.url or '/outro/' in r.url,
                      f'{label}: walked past consent and the quiz '
                      f'({r.url.split("/p/")[-1][:34]!r})')

                setattr(pp, flag, True)
                common.set_exit_code(pp, _settings.EXIT_CODES[exit_name])
                db.commit()

                # Now ask for the next page: the flow routes a disqualified
                # participant to their ending.
                fp = _FP(); fp.feed(r.text)
                r = sess.post(r.url, data=_bp(fp.inputs, {}, {}, warn=False),
                              allow_redirects=True)
                for _ in range(8):
                    if '/outro/' in r.url:
                        break
                    fp = _FP(); fp.feed(r.text)
                    r = sess.post(r.url, data=_bp(fp.inputs, {}, {}, warn=False),
                                  allow_redirects=True)
                assert_only_its_own(r.text, key, D, label)

            # ---------------------------------------------------------------
            section('5. COMPLETED — the one that auto-approves')
            s2 = create_session('prolific', num_participants=2)
            db.commit()
            p = s2.get_participants()[0]
            # Drive the real journey with the HTTP walker the other suites use,
            # then render the ending in the browser and read it.
            from http_flow_test import FormParser, build_payload  # noqa: F401
            from gated_flow_test import RIGHT
            import requests
            sess = requests.Session()
            r = sess.get(f'{server.base}/InitializeParticipant/{p.code}',
                         allow_redirects=True)
            for _ in range(60):
                fp = FormParser()
                fp.feed(r.text)
                if 'Results' in r.url or 'Ended' in r.url:
                    break
                # RIGHT answers, or the walker fails the quiz and lands on the
                # comprehension DQ ending — which is how this case first
                # reported the QUIZ code on a "completed" page.
                payload = build_payload(
                    fp.inputs, {'consent': 'True', **RIGHT}, {}, warn=False)
                r = sess.post(r.url, data=payload, allow_redirects=True)
            check('Results' in r.url or 'Ended' in r.url,
                  f'the completer reached an ending ({r.url.split("/p/")[-1][:40]!r})')
            assert_only_its_own(r.text, 'prolific_cc_code', D, 'completed')

            browser.close()
    finally:
        server.stop()

    section('SUMMARY')
    if FAILURES:
        print(f'  {len(FAILURES)} CHECK(S) FAILED:')
        for f in FAILURES:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
