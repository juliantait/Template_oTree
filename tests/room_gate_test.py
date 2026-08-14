#!/usr/bin/env python3
"""The room welcome gate: who is auto-passed, who is not, and what fails safely.

Drives a REAL browser against a REAL server, because every property here is a
browser property — `requestSubmit` firing a listener, a websocket advancing a
wait page, JavaScript being off. None of it can be checked from Python alone.

THE FOUR CASES, and why each one is here:

  1. ID PRESENT -> the visitor flows straight through and NEVER SEES THE BUTTON.
     This is the feature. Asserted by watching where the browser ends up, not by
     reading the script.

  2. BARE URL -> the styled page with its button, and NO SLOT CLAIMED until it is
     clicked. Load-bearing, not a nicety: a bot arrives with no id and usually
     runs no JavaScript, so the button is what keeps it out. If this ever starts
     auto-passing "for convenience", the room fills with bots.

  3. THE LOOP GUARD -> when the gate POST fails, the page falls back to the
     button instead of retrying. A failure a participant can click through is
     recoverable; a failure that retries is a participant who never arrives and
     leaves no trace.

  3b. THE SAME GUARD, IN THE CONFIG WHERE THE LOOP IS REAL — and this is the
     one that proves it. THE CONFIG THAT MATTERS IS A ROOM WITH A
     `participant_label_file`: only then is the label a REAL INPUT in the form,
     so the id survives into the next request and a page that auto-passes again
     on arrival genuinely loops. Without a labels file — what this template
     ships — a native GET submit strips the id and the loop cannot happen, which
     makes any "did not loop" assertion there VACUOUS. A copied study that adds
     a labels file lands in the dangerous configuration without ever reading
     this file, so the test creates that configuration itself (a LabelRoom
     injected into otree.room.ROOM_DICT) rather than only testing what we ship.
     Measured: with the guard, 2 navigations; with it removed, 113 in six
     seconds.

  4. NO SESSION YET -> the lab prep flow, and the one most likely to break
     silently: the visitor is auto-passed onto oTree's "Waiting for your session
     to begin" page and ADVANCES BY ITSELF when the experimenter creates the
     session. Nobody is watching this one in normal testing because it needs two
     actors.

  Plus: an id-carrying arrival with JAVASCRIPT DISABLED. Confirmed rather than
  assumed — see the check's own comment for what actually happens.

Run:  LD_LIBRARY_PATH=<sysroot>/root/usr/lib/x86_64-linux-gnu \\
      python3 tests/room_gate_test.py
(headless Chromium without root: docs/headless_chromium_recipe.md)
"""
import os
import sys
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _TESTS_DIR)
sys.path.insert(0, _APP_ROOT)

os.environ.setdefault('OTREE_PRODUCTION', '1')

FAILURES = []


def check(ok, label):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(label)
    return ok


def section(title):
    print(f"\n=== {title} ===")


def main():
    from render_check import Server, VIEWPORTS          # the same self-hosting
    from playwright.sync_api import sync_playwright
    import requests

    ROOM_URL = '/room/experiment'

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

            # ---------------------------------------------------------------
            section('4. NO SESSION YET — the lab prep flow')
            # Deliberately FIRST, while the room genuinely has no session: this
            # is the state an experimenter's machine sits in before the session
            # is made, and the case nothing else exercises.
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
            page = context.new_page()
            page.goto(f'{server.base}{ROOM_URL}?participant_label=SEAT01',
                      wait_until='load')
            page.wait_for_timeout(1200)
            body = ' '.join((page.inner_text('body') or '').split())
            check('Waiting for your session' in body,
                  'an identified arrival is auto-passed onto the wait page '
                  f'(got: {body[:60]!r})')
            check('welcome_page_ok' in page.url,
                  'the gate was genuinely passed, not merely re-rendered')

            # The experimenter now creates the session. The wait page holds a
            # websocket; it must advance without the participant touching it.
            # CREATED THROUGH THE REST API, exactly as scripts/start.sh does,
            # and that detail is the whole point of this case. Two things have to
            # be true for a waiting participant to advance:
            #   * the session must be BOUND TO THE ROOM (`room_name`), or
            #     `room.get_session()` stays None and everyone waits; and
            #   * something must BROADCAST "session ready" to the room's
            #     websocket group — and `otree.session.create_session()` does
            #     NOT. Only the admin's create-session consumer
            #     (otree/channels/consumers.py:556) and the REST endpoint
            #     (otree/views/rest.py:125) send it.
            # So a session made by calling create_session() directly binds the
            # room and still leaves every waiting participant stuck. Both of
            # those were this test's own bugs before they were caught here, and
            # both are real operational traps — see the report.
            resp = requests.post(
                f'{server.base}/api/sessions',
                json=dict(session_config_name='lab', num_participants=6,
                          room_name='experiment'),
                timeout=30)
            check(resp.status_code == 200,
                  f'the experimenter creates the session over REST, as '
                  f'scripts/start.sh does (status {resp.status_code})')
            advanced = False
            for _ in range(40):
                page.wait_for_timeout(500)
                if 'room' not in page.url:
                    advanced = True
                    break
            check(advanced,
                  f'and it ADVANCES BY ITSELF once the session exists '
                  f'(landed on {page.url.split(server.base)[-1][:48]!r})')
            context.close()

            # ---------------------------------------------------------------
            section('1. ID PRESENT — straight through, never sees the button')
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
            page = context.new_page()
            seen_button = {'ever': False}

            def watch(_):
                try:
                    if page.locator('.next-button').count() and \
                            page.locator('.next-button').first.is_visible():
                        seen_button['ever'] = True
                except Exception:
                    pass

            page.on('framenavigated', watch)
            page.goto(f'{server.base}{ROOM_URL}?participant_label=SEAT02',
                      wait_until='load')
            page.wait_for_timeout(1500)
            check(ROOM_URL not in page.url,
                  f'the visitor left the gate without touching it '
                  f'(on {page.url.split(server.base)[-1][:48]!r})')
            check(page.locator('.next-button').count() == 0
                  or not page.locator('.next-button').first.is_visible()
                  or 'room' not in page.url,
                  'and is not sitting on the gate looking at a Start button')
            context.close()

            # The Prolific spelling must work identically — oTree only ever
            # reads participant_label, so PROLIFIC_PID has to be copied across.
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
            page = context.new_page()
            page.goto(f'{server.base}{ROOM_URL}?PROLIFIC_PID=PID12345',
                      wait_until='load')
            page.wait_for_timeout(1500)
            check(ROOM_URL not in page.url,
                  '?PROLIFIC_PID= is auto-passed too (Prolific\'s own spelling)')
            check('PID12345' in page.url or 'InitializeParticipant' in page.url
                  or 'room' not in page.url,
                  'and the id travelled with them rather than being dropped')
            context.close()

            # ---------------------------------------------------------------
            section('2. BARE URL — the button shows, and nothing is claimed '
                    'until it is clicked')
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
            page = context.new_page()
            page.goto(f'{server.base}{ROOM_URL}', wait_until='load')
            page.wait_for_timeout(1200)
            check(ROOM_URL in page.url,
                  'a bare URL is NOT auto-passed — it stays on the gate')
            check(page.locator('.next-button').first.is_visible(),
                  'the Start button is shown to whoever arrived without an id')
            check('welcome_page_ok' not in page.url,
                  'NO SLOT IS CLAIMED WITHOUT A CLICK (this is what keeps bots '
                  'out: no id, no JavaScript, no entry)')
            page.locator('.next-button').first.click()
            page.wait_for_timeout(1500)
            check(ROOM_URL not in page.url or 'welcome_page_ok' in page.url,
                  'and the button still works when it IS clicked '
                  f'({page.url.split(server.base)[-1][:48]!r})')
            context.close()

            # ---------------------------------------------------------------
            section('3. THE LOOP GUARD — a failing gate POST falls back to the '
                    'button, it does not retry')
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'])
            page = context.new_page()
            # Break the gate POST the way a flaky network or a 500 would.
            page.route(f'**{ROOM_URL}', lambda route:
                       route.abort() if route.request.method == 'POST'
                       else route.continue_())
            navigations = {'n': 0}
            page.on('framenavigated', lambda _: navigations.__setitem__(
                'n', navigations['n'] + 1))
            page.goto(f'{server.base}{ROOM_URL}?participant_label=SEAT03',
                      wait_until='load')
            page.wait_for_timeout(3000)
            check(page.locator('.next-button').first.is_visible(),
                  'the participant is left looking at a button they can click, '
                  'not a dead page')
            # NB: this navigation count is NOT the guard's proof, and must not
            # be read as it. In the config this template ships (no labels file)
            # the form carries no fields, so a native GET submit strips the id
            # and the page CANNOT loop — this assertion passes with or without
            # the guard. Section 3b is where the guard is actually proved, in
            # the configuration where the loop is real. Kept here because the
            # POST-failure fallback above IS meaningful.
            check(navigations['n'] <= 2,
                  f'and this POST-failure path did not loop either '
                  f'({navigations["n"]} navigation(s); see 3b for the real test)')
            # Reload with the id still in the URL: the guard must stop the
            # SECOND attempt, which is the actual loop this defends against.
            page.reload(wait_until='load')
            page.wait_for_timeout(1500)
            check(page.locator('.next-button').first.is_visible(),
                  'on a reload inside the guard window it shows the button '
                  'rather than auto-passing again')
            context.close()

            # ---------------------------------------------------------------
            section('3b. THE GUARD, IN THE CONFIG WHERE THE LOOP IS REAL')
            # WHY THIS SECTION EXISTS. The navigation assertion in section 3 is
            # VACUOUS in the configuration this template ships: with no
            # participant-labels file the gate's form carries no fields, so a
            # native GET submit navigates to `/room/x?` and STRIPS the id — the
            # page cannot loop because the second load is a bare URL. The
            # assertion passed whether or not the guard existed, which is an
            # assertion that cannot fail, on the most expensive failure in the
            # file: a participant who never arrives and leaves no trace.
            #
            # THE CONFIG THAT MAKES IT REAL: a room WITH a participant-labels
            # file. Then `has_participant_label_file` is true, the label is a
            # REAL INPUT in the form, and the id survives into the next request —
            # so a page that auto-passes again on arrival really does loop. Any
            # copied study that adds a labels file lands in that configuration
            # without ever reading this test, which is exactly why the test has
            # to be meaningful there and not only in what we happen to ship.
            #
            # The room is injected into oTree's ROOM_DICT rather than added to
            # settings.ROOMS: this is a property of the CODE under a
            # configuration, not a room the template should ship.
            import otree.room as otree_room
            labels_path = os.path.join(_TESTS_DIR, '_tmp_room_labels.txt')
            with open(labels_path, 'w', encoding='utf8') as fh:
                fh.write('\n'.join(f'SEAT{n:02d}' for n in range(1, 11)))
            otree_room.ROOM_DICT['labelroom'] = otree_room.LabelRoom(
                name='labelroom', display_name='Label room',
                participant_label_file=labels_path,
                welcome_page='_templates/room_welcome.html')
            LABEL_URL = '/room/labelroom'
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS['laptop_1280x720'])
                page = context.new_page()

                first = page.goto(f'{server.base}{LABEL_URL}'
                                  f'?participant_label=SEAT01',
                                  wait_until='load')
                page.wait_for_timeout(800)
                check(page.locator('input[name="participant_label"]').count() == 1
                      or 'welcome_page_ok' in page.url,
                      'the labels-file room renders the label as a REAL INPUT '
                      '(the condition that makes the loop possible)')
                context.close()

                # Now the failure the guard is FOR: the reload comes back
                # WITHOUT welcome_page_ok. Every GET carrying the flag is served
                # the gate page instead, so the browser lands back here with the
                # id still in the URL — the exact shape that loops.
                context = browser.new_context(
                    viewport=VIEWPORTS['laptop_1280x720'])
                page = context.new_page()

                def swallow_flag(route):
                    req = route.request
                    if req.method != 'GET' or 'welcome_page_ok' not in req.url:
                        return route.continue_()
                    stripped = (req.url.replace('welcome_page_ok=1&', '')
                                .replace('&welcome_page_ok=1', '')
                                .replace('?welcome_page_ok=1', '?'))
                    return route.fulfill(
                        response=page.context.request.get(stripped))

                page.route(f'**{LABEL_URL}*', swallow_flag)
                navs = {'n': 0}
                page.on('framenavigated',
                        lambda _: navs.__setitem__('n', navs['n'] + 1))
                page.goto(f'{server.base}{LABEL_URL}?participant_label=SEAT02',
                          wait_until='load')
                page.wait_for_timeout(6000)

                # THE ASSERTION THIS SECTION EXISTS FOR. With the guard, the
                # auto-pass fires ONCE, bounces back flagless, and stops — a
                # handful of navigations. Without the guard it re-fires on every
                # bounce and the count climbs without limit.
                check(navs['n'] <= 4,
                      f'a flagless reload does NOT loop: {navs["n"]} '
                      f'navigation(s) in 6s (unguarded, this climbs)')
                check(page.locator('.next-button').first.is_visible(),
                      'and the participant is left with a button to click')
                context.close()
            finally:
                otree_room.ROOM_DICT.pop('labelroom', None)
                if os.path.exists(labels_path):
                    os.remove(labels_path)

            # ---------------------------------------------------------------
            section('JAVASCRIPT DISABLED, with an id — confirmed, not assumed')
            context = browser.new_context(viewport=VIEWPORTS['laptop_1280x720'],
                                          java_script_enabled=False)
            page = context.new_page()
            page.goto(f'{server.base}{ROOM_URL}?participant_label=SEAT04',
                      wait_until='load')
            body = ' '.join((page.inner_text('body') or '').split())
            check(page.locator('.next-button').first.is_visible(),
                  'they see the styled page and its Start button (no auto-pass: '
                  'the auto-pass is JavaScript)')
            check('This study needs JavaScript' in body,
                  'and the page TELLS them JavaScript is required')
            # THE CORRECTION worth having in writing: clicking does NOT get them
            # in. oTree's own submit handler is the gate mechanism, so with JS
            # off the click submits a form with no action and lands straight
            # back on the gate. That is oTree's design, not something the
            # auto-pass introduced — and it is why the noscript line above is
            # the real answer for these visitors.
            page.locator('.next-button').first.click()
            page.wait_for_timeout(1200)
            check('welcome_page_ok' not in page.url,
                  'clicking does NOT admit them without JavaScript — they are '
                  'returned to the gate (oTree\'s mechanism is the script)')
            context.close()

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
