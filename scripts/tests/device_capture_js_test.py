#!/usr/bin/env python
"""THE CLIENT-SIDE DEVICE CAPTURE, MEASURED IN A REAL BROWSER.

    OTREE_ADMIN_PASSWORD=admin otree prodserver 8000     # THROWAWAY database
    LD_LIBRARY_PATH=<sysroot>/usr/lib/x86_64-linux-gnu \
        python scripts/tests/device_capture_js_test.py http://localhost:8000

(Headless Chromium runs here without root — the recipe, including the exact
package list, is `docs/headless_chromium_recipe.md`.)

WHY A BROWSER IS THE ONLY HONEST TEST OF THIS. `device_info_json` is filled by
JavaScript. An HTTP test posts whatever it likes into that field and proves
nothing about what a participant's browser actually writes there; no bot runs
the script at all. So the one question this file asks — DOES THE BROWSER
CLASSIFY WITH THE SERVER'S RULES? — cannot be asked anywhere else.

WHAT IT IS PINNING (`common.device_ua_rules`, `_static/global/js/
device_capture.js`). The client used to carry its OWN copy of the User-Agent
patterns, and the copies had drifted: `Mobile/\\d`, `BB10` and `Nexus 7|9|10`
were server-only and the computer test was an unanchored `Linux`. An iOS in-app
browser was therefore recorded as "server says phone, client says unknown" —
INDISTINGUISHABLE from the genuine client/server disagreement the client's
classification exists to expose. There is now ONE list, shipped to the page via
js_vars, and the states that remain are kept apart and named:

    ua_rules            'server' | 'unavailable'
    device_type_ua      this browser's own UA under the SERVER's rules
    device_type         the final client answer (device_type_ua + client-only
                        signals such as touch)
    device_type_signals which of those signals fired

So the checks below are: the rules ARRIVE; the client's answer under them
MATCHES the server's for the same User-Agent (across several device shapes);
a client-only signal that genuinely disagrees is RECORDED AS SUCH; and the
no-rules case says 'unavailable' rather than guessing.

Exits non-zero on any failed check.
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'

_failures = []


def check(cond, msg):
    print(('  [PASS] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        _failures.append(msg)


def section(title):
    print('\n=== ' + title + ' ===')


# Real strings, and each is a DIFFERENT SHAPE of the problem — including the two
# the old client list got wrong (the iOS in-app browser via `Mobile/15E148`
# without "Safari", and a Nexus tablet).
UAS = {
    'laptop chrome': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/124.0.0.0 Safari/537.36'),
    'windows laptop': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/125.0.0.0 Safari/537.36'),
    'iphone safari': ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 '
                      'Mobile/15E148 Safari/604.1'),
    'ios in-app browser': ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
                           'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'),
    'ipad': ('Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) '
             'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 '
             'Mobile/15E148 Safari/604.1'),
    'nexus 7 tablet': ('Mozilla/5.0 (Linux; Android 6.0.1; Nexus 7 Build/MOB30X) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36'),
    'android phone': ('Mozilla/5.0 (Linux; Android 14; Pixel 8) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/125.0.0.0 Mobile Safari/537.36'),
    'unrecognised': 'SomeResearchTool/2.1 (+https://example.org/bot)',
}

CONFIGURED_RETURN_URL = 'https://app.prolific.com/'


def create(**modified):
    """A prolific session (device_capture on) with the gate wide open, so every
    User-Agent below reaches the consent page and runs the script."""
    fields = {'prolific_screenout_return_url': CONFIGURED_RETURN_URL,
              'allowed_devices': ['phone', 'tablet', 'computer', 'unknown']}
    fields.update(modified)
    r = requests.post(BASE + '/api/sessions',
                      json={'session_config_name': 'prolific',
                            'num_participants': len(UAS) + 4,
                            'modified_session_config_fields': fields})
    r.raise_for_status()
    return r.json()


def server_type(ua):
    """The server's own classification, from the module the gate uses."""
    import common
    return common.classify_device(ua)


def capture_in_browser(pw, url, ua, viewport=None):
    """Load the consent page in a REAL browser with this User-Agent and return
    the hidden fields exactly as they would be POSTed."""
    browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])
    try:
        ctx = browser.new_context(
            user_agent=ua, viewport=viewport or {'width': 1280, 'height': 720})
        page = ctx.new_page()
        page.goto(url, wait_until='networkidle')
        values = page.evaluate("""() => {
            const info = document.getElementById('device_info_json');
            const mob = document.getElementById('is_mobile');
            return {info: info ? info.value : null,
                    is_mobile: mob ? mob.value : null,
                    has_js_vars: typeof js_vars !== 'undefined'};
        }""")
        ctx.close()
        return values
    finally:
        browser.close()


def main():
    from playwright.sync_api import sync_playwright

    created = create()
    join = created['session_wide_url']

    section('A. THE RULES REACH THE BROWSER, AND ITS ANSWER IS THE SERVER\'S')
    with sync_playwright() as pw:
        for label, ua in UAS.items():
            vals = capture_in_browser(pw, join, ua)
            if not vals['info']:
                check(False, f'{label}: the device field was filled at all')
                continue
            info = json.loads(vals['info'])
            expected = server_type(ua)
            check(info.get('ua_rules') == 'server',
                  f"{label}: the browser applied the SERVER's rules "
                  f"(ua_rules={info.get('ua_rules')!r})")
            check(info.get('device_type_ua') == expected,
                  f'{label}: client reads its own UA as {info.get("device_type_ua")!r}, '
                  f'server reads the header as {expected!r} — they AGREE')

        section('B. A CLIENT-ONLY SIGNAL IS RECORDED AS ONE, NOT AS DRIFT')
        # An iPad that lies and calls itself a Macintosh: the server can only see
        # the UA and honestly says 'computer'; the browser has touch points and
        # says 'tablet'. THAT is the disagreement this measurement is for, and it
        # must be attributable — `device_type_ua` still matches the server, and
        # the named signal explains the difference.
        ipados_ua = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                     'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 '
                     'Safari/605.1.15')
        browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        try:
            ctx = browser.new_context(user_agent=ipados_ua,
                                      viewport={'width': 1024, 'height': 768},
                                      has_touch=True, is_mobile=False)
            page = ctx.new_page()
            # maxTouchPoints > 1 is what gives an iPadOS device away; Playwright's
            # has_touch sets it to 1, so raise it the way a real iPad reports.
            page.add_init_script(
                "Object.defineProperty(navigator, 'maxTouchPoints', "
                "{get: () => 5});")
            page.goto(join, wait_until='networkidle')
            raw = page.evaluate(
                "() => document.getElementById('device_info_json').value")
            ctx.close()
        finally:
            browser.close()
        info = json.loads(raw)
        check(info.get('device_type_ua') == 'computer',
              f'iPadOS-as-Macintosh: the UA still reads as the SERVER reads it '
              f'({info.get("device_type_ua")!r}) — so this is not list drift')
        check(info.get('device_type') == 'tablet',
              f'...but the client\'s final answer is {info.get("device_type")!r}, '
              f'from what only a browser can see')
        check('ipados_touch' in (info.get('device_type_signals') or []),
              f'...and the signal that moved it is NAMED '
              f'({info.get("device_type_signals")!r}), so the disagreement is '
              f'attributable rather than mysterious')

        section('C. NO RULES -> "unavailable", NEVER A GUESS')
        # The script is on the page but js_vars is not: the client must say it
        # learnt nothing, rather than fall back to a private copy of the list —
        # a silent fallback IS the second list this design removes.
        #
        # THE RULES ARE STRIPPED OUT OF THE SERVED HTML, not overwritten from an
        # init script: oTree emits `<script>var js_vars = {...}</script>` in the
        # page itself, so anything set before navigation is simply replaced by it
        # (measured — an earlier version of this check did exactly that and was
        # testing nothing). Rewriting the document is the faithful simulation of
        # "the rules never arrived".
        browser = pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])
        try:
            ctx = browser.new_context(user_agent=UAS['iphone safari'],
                                      viewport={'width': 390, 'height': 844})

            def strip_js_vars(route):
                resp = route.fetch()
                if 'text/html' not in (resp.headers.get('content-type') or ''):
                    route.fulfill(response=resp)
                    return
                body = re.sub(r'<script>\s*var js_vars\s*=.*?</script>', '',
                              resp.text(), flags=re.S)
                route.fulfill(response=resp, body=body)

            ctx.route(re.compile(r'.*'), strip_js_vars)
            page = ctx.new_page()
            page.goto(join, wait_until='networkidle')
            check(page.evaluate("() => typeof js_vars === 'undefined'"),
                  'the js_vars payload really was removed from the page '
                  '(otherwise this section proves nothing)')
            raw = page.evaluate(
                "() => document.getElementById('device_info_json').value")
            ctx.close()
        finally:
            browser.close()
        info = json.loads(raw)
        check(info.get('ua_rules') == 'unavailable',
              f'without the rules the client says so (ua_rules='
              f'{info.get("ua_rules")!r})')
        check(info.get('device_type') == 'unavailable'
              and info.get('device_type_ua') == 'unavailable',
              f'...and classifies NOTHING rather than guessing '
              f'(device_type={info.get("device_type")!r})')

    print('\n=== SUMMARY ===')
    if _failures:
        print(f'  {len(_failures)} FAILED:')
        for f in _failures:
            print('   - ' + f)
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
