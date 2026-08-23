#!/usr/bin/env python3
"""MEASURED browser checks for the two features that live entirely in the
dashboard page's JavaScript (Julian, 2026-08-23):

  1. THE STALE-DATA BANNER. When a refresh fails, the status line must say WHEN
     the last good data is from (wall clock) AND how long ago that was, with the
     age COUNTING UP while the server stays down — so a blip and a dead server
     look different at a glance.
  2. THE TWO PER-PARTICIPANT TIMER PILLS. Pill 1 (intro) freezes at the intro
     boundary; pill 2 (total) keeps counting and includes the intro. A LIVE pill
     advances every second on the client (between the 2s polls AND while a poll
     is failing); a FROZEN pill does not; and total >= intro on every row.

WHY A MOCKED fetch RATHER THAN A REAL oTree SERVER. Both behaviours are pure
client JavaScript reacting to (a) the JSON a poll returns and (b) the poll
FAILING. Booting oTree cannot make a poll fail on demand, and cannot fast-forward
a clock. So this loads the dashboard's OWN page (its real `_PAGE_HTML`, the same
script the browser runs in production) and stubs `window.fetch`, which is exactly
the seam between "the poll" and "everything this test is about". The snapshot fed
in is `monitor_session.payload()` — the same fixture the public site preview is
built from, so this can never drift onto a shape the server never sends.

This is the presence half of CLAUDE.md's rule: a stale-banner test that only
asserts the failure text once would pass against a banner that never updates. So
the banner age and the live pill are each measured at TWO times and asserted to
have MOVED, and the frozen pill is asserted NOT to move in the same window.

Run: /home/dev/.venv-otree/bin/python scripts/tests/dashboard_timer_banner_test.py
(headless Chromium; needs no server and no database).
"""
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _APP_ROOT)
sys.path.insert(0, os.path.join(_APP_ROOT, 'scripts', 'site_previews'))

import experimenter_dashboard as ed      # noqa: E402
import monitor_session                   # noqa: E402  (the shared fixture)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def build_page():
    """The real dashboard shell, with the session placeholders filled and no
    external stylesheet (this test measures behaviour, not pixels — the pills
    are built by renderRow regardless of CSS)."""
    return (ed._PAGE_HTML
            .replace('__CSS_HREF__', '')
            .replace('__SESSION_CODE__', 'demo1234')
            .replace('__SESSION_TITLE__', 'Timer/banner test')
            .replace('__DATA_URL__', '/data')
            .replace('__POLL_MS__', '2000'))


def main():
    from playwright.sync_api import sync_playwright

    payload = monitor_session.payload()
    page_html = build_page()

    # THE MOCKED POLL, via request routing (the seam this test owns). `state`
    # lives here in Python: `fail` makes /data abort like a dead server; on a
    # good poll every LIVE timer's base is advanced by the whole seconds elapsed
    # since the page loaded, exactly as a real server recomputes `now - start`.
    state = {'fail': False, 'start': time.time()}

    def serve_page(route):
        route.fulfill(status=200, content_type='text/html', body=page_html)

    def serve_data(route):
        if state['fail']:
            route.abort()      # network error -> the page's fetch rejects
            return
        grew = int(time.time() - state['start'])
        snap = json.loads(json.dumps(payload))
        for r in snap['rows']:
            if r.get('total_live') and r.get('total_seconds') is not None:
                r['total_seconds'] += grew
            if r.get('intro_live') and r.get('intro_seconds') is not None:
                r['intro_seconds'] += grew
        route.fulfill(status=200, content_type='application/json',
                      body=json.dumps(snap))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={'width': 1512, 'height': 950})
        pg.route('**/data', serve_data)
        pg.route('**/dash', serve_page)
        pg.goto('http://localhost/dash')
        # reveal every row so the frozen/live rows this test needs are present.
        pg.wait_for_selector('#show-not-arrived', timeout=15000)
        pg.check('#show-not-arrived')
        pg.wait_for_selector('tbody tr td.c-instr .time-pill', timeout=15000)

        # ------------------------------------------------------------------
        section('TWO PILLS: intro and total, per participant')
        # Every arrived row with a time shows BOTH an intro and a total pill,
        # labelled so they are told apart. Read the (key -> value) pairs per row.
        rows = pg.evaluate("""() =>
            [...document.querySelectorAll('tbody tr')].map(tr => {
              const c = tr.querySelector('td.c-instr');
              if (!c) return null;
              return [...c.querySelectorAll('.time-pill')].map(p => ({
                key: (p.querySelector('i') || {}).textContent || '',
                val: (p.querySelector('em') || {}).textContent || '',
                live: p.hasAttribute('data-live'),
              }));
            }).filter(Boolean)""")
        with_pills = [r for r in rows if r]
        check(len(with_pills) >= 5,
              f'rows render time pills ({len(with_pills)} rows with pills)')
        both = [r for r in with_pills
                if [p['key'] for p in r] == ['intro', 'total']]
        check(len(both) == len(with_pills),
              f'every timed row shows an INTRO pill then a TOTAL pill, in that '
              f'order ({len(both)} of {len(with_pills)})')

        # total >= intro on every row, measured off the rendered m:ss text.
        def secs(t):
            m, s = t.split(':')
            return int(m) * 60 + int(s)
        bad = []
        for r in both:
            i = next(p['val'] for p in r if p['key'] == 'intro')
            t = next(p['val'] for p in r if p['key'] == 'total')
            if i and t and secs(t) < secs(i):
                bad.append((i, t))
        check(not bad,
              f'the total pill is never shorter than the intro pill '
              f'(violations: {bad})')

        # A row still IN the intro (intro_live) has a live INTRO pill; a row PAST
        # the intro has a frozen one. A finished row's TOTAL pill is frozen; an
        # active row's is live. These are the freeze/keep-counting rules.
        live_intro = pg.evaluate("""() =>
            [...document.querySelectorAll('tbody tr')].some(tr => {
              const p = tr.querySelector('td.c-instr .time-pill[data-live] i');
              return p && p.textContent === 'intro';
            })""")
        check(live_intro,
              'a participant still in the intro has a LIVE intro pill')
        frozen_intro = pg.evaluate("""() => {
            let frozen = 0;
            document.querySelectorAll('tbody tr').forEach(tr => {
              const pills = tr.querySelectorAll('td.c-instr .time-pill');
              pills.forEach(p => {
                if (p.querySelector('i').textContent === 'intro'
                    && !p.hasAttribute('data-live')) frozen++;
              });
            });
            return frozen; }""")
        check(frozen_intro > 0,
              f'a participant PAST the intro has a FROZEN intro pill '
              f'({frozen_intro} frozen)')

        # ------------------------------------------------------------------
        section('LIVE COUNTING and the FREEZE, measured over time')
        # Pick a finished row (total frozen) and a live row (total counting) and
        # read each total twice, ~2.6s apart, with the poll SUCCEEDING. The live
        # one must climb; the frozen one must not move.
        def total_of(kind):
            return pg.evaluate("""(kind) => {
              const trs = [...document.querySelectorAll('tbody tr')];
              for (const tr of trs) {
                const p = tr.querySelector('td.c-instr .time-pill:last-child');
                if (!p) continue;
                const live = p.hasAttribute('data-live');
                if ((kind === 'live') === live) {
                  return (p.querySelector('em') || {}).textContent || '';
                }
              }
              return '';
            }""", kind)
        live_a, frozen_a = total_of('live'), total_of('frozen')
        time.sleep(2.6)
        live_b, frozen_b = total_of('live'), total_of('frozen')
        check(live_a and live_b and secs(live_b) > secs(live_a),
              f'the LIVE total pill counts up on its own ({live_a} -> {live_b})')
        check(frozen_a and frozen_a == frozen_b,
              f'a FINISHED participant\'s total pill is FROZEN, not counting '
              f'({frozen_a} -> {frozen_b})')

        # ------------------------------------------------------------------
        section('STALE-DATA BANNER when a refresh fails')
        status = pg.text_content('#status')
        check(status and status.startswith('updated'),
              f'while polls SUCCEED the banner reads "updated <time>" '
              f'({status!r})')

        # Now the server "dies": every poll rejects. The banner must switch to
        # naming WHEN the last good data was and HOW LONG AGO.
        state['fail'] = True
        pg.wait_for_function(
            "() => /last good data/.test("
            "document.getElementById('status').textContent)", timeout=8000)
        stale = pg.text_content('#status')
        check('last good data' in stale,
              f'a failing refresh names the LAST GOOD DATA ({stale!r})')
        check(re.search(r'\d{1,2}:\d{2}', stale) is not None,
              f'…and gives the WALL-CLOCK TIME it is from ({stale!r})')
        check('ago' in stale,
              f'…and says how long AGO that was ({stale!r})')

        # THE AGE KEEPS COUNTING UP while the server stays down — the whole point
        # (a blip vs a dead server). Read the "(… ago)" twice, ~3s apart.
        def age_text():
            m = re.search(r'\(([^)]*ago)\)', pg.text_content('#status'))
            return m.group(1) if m else ''
        age_a = age_text()
        time.sleep(3.2)
        age_b = age_text()
        check(age_a and age_b and age_a != age_b,
              f'the age counts UP while the refresh keeps failing '
              f'({age_a!r} -> {age_b!r})')

        # And the live timer pill ALSO keeps counting while the server is down —
        # the same last-good clock feeds both features.
        live_c = total_of('live')
        time.sleep(2.2)
        live_d = total_of('live')
        check(live_c and live_d and secs(live_d) > secs(live_c),
              f'the live total pill keeps counting while the poll is failing '
              f'({live_c} -> {live_d})')

        # Recovery: once the poll succeeds again the banner returns to "updated".
        state['fail'] = False
        pg.wait_for_function(
            "() => document.getElementById('status').textContent"
            ".startsWith('updated')", timeout=8000)
        check(True, 'when the refresh recovers the banner returns to "updated"')

        browser.close()

    print()
    if _failures:
        print(f'FAILED: {len(_failures)} check(s)')
        for f in _failures:
            print(f'  - {f}')
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
