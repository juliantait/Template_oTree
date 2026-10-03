"""THE MONITOR'S TIMELINE LAYOUT, MEASURED, for any number of steps.

The timeline is built per session from its app_sequence, so the operator
screen must hold together for step counts and label lengths nobody has seen
yet. Layout failures produce no error anywhere (CLAUDE.md, "a layout change
needs a MEASURED render check"), so this drives real headless Chromium over
the dashboard's OWN page and JavaScript — `page_template_for_steps`, fetch
stubbed with the shared fixture (scripts/site_previews/monitor_session.py),
exactly as the site preview and dashboard_timer_banner_test do — for 4 to 9
steps, including raw app names like `belief_elicitation_task`, at 1024, 1152,
1280 and 1440px, and asserts on geometry:

  1. every header label is centred on its column's dots (±1px) in every row —
     the header drift that `1fr` tracks used to produce (up to 40px);
  2. every row's tracks are equal (a wide marker cannot widen its track);
  3. no label is cut off WITHOUT its full text in a tooltip, and the cut-off
     is confined to the extreme cases (≥7 steps at ≤1152px) — elsewhere the
     fitting ladder makes every label fit;
  4. a two-pill state cell ("✓ finished" + "Non-SEPA") stays on ONE line, and
     every row has the same height (±2px);
  5. no horizontal PAGE scroll at any of these widths;
  6. the stock six steps at 1440px use NO fitting rung (the shipped look), and
     the marker reads "2 of 10" there but "2/10" where tracks are narrow —
     each asserted with its counterpart, never an absence alone.

What it is NOT evidence of: the numbers in the cells (dashboard_test.py), a
real session's column widths (the real-HTTP pass in _ai/monitor_dynamic/ did
that once), or emoji fonts on an operator's machine.

Run: python scripts/tests/dashboard_timeline_render_check.py   (no server)
"""
import copy
import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts', 'site_previews'))

import experimenter_dashboard as dash  # noqa: E402  (stdlib-only at import)
import monitor_session as ms           # noqa: E402  (the shared fixture)

WIDTHS = (1024, 1152, 1280, 1440)
STOCK = ms.TIMELINE
EXTRA = [('belief_elicitation_task', 'belief_elicitation_task'),
         ('practice', 'Practice'), ('survey_part_two', 'survey_part_two'),
         ('risk_preferences_holt_laury', 'risk_preferences_holt_laury')]

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def timeline(n):
    """n steps: the stock six, fewer (apps dropped) or more (apps inserted
    between the quiz and the task, the likeliest place a study adds one)."""
    if n == 4:
        return [STOCK[0], STOCK[3], STOCK[4], STOCK[5]]
    if n == 5:
        return [STOCK[0], STOCK[1], STOCK[3], STOCK[4], STOCK[5]]
    extra = [{'id': i, 'label': lab} for i, lab in EXTRA[:n - 6]]
    return STOCK[:3] + extra + STOCK[3:]


def payload(steps):
    pl = copy.deepcopy(ms.payload())
    ids = [s['id'] for s in steps]
    for r in pl['rows']:
        if r['step'] not in ids:
            r['step'] = ids[0]
    # Somebody inside each inserted app, at the widest marker ("10 of 10").
    model = [r for r in pl['rows'] if r['label'] == 'A4'][0]
    for k, sid in enumerate(ids[3:-3]):
        row = copy.deepcopy(model)
        row.update(label=f'C{k + 1}', step=sid, round=10, round_total=10)
        pl['rows'].append(row)
    pl['timeline'] = steps
    return pl


def page_for(steps):
    css = open(os.path.join(REPO_ROOT, '_static/global/css/base.css')).read()
    live = (dash.page_template_for_steps(steps)
            .replace('<link rel="stylesheet" href="__CSS_HREF__">',
                     '<style>%s</style>' % css)
            .replace('__SESSION_TITLE__', 'layout').replace(
                '__SESSION_CODE__', 'layout')
            .replace('__DATA_URL__', 'about:blank')
            .replace('__POLL_MS__', '2000'))
    stub = ('<script>window.fetch=function(){return Promise.resolve('
            '{json:function(){return %s;}});};'
            'window.setInterval=function(){return 0};</script>'
            % json.dumps(payload(steps)))
    return live.replace('<html><head><meta charset="utf-8">',
                        '<html><head><meta charset="utf-8">' + stub, 1)


MEASURE = '''() => {
  const hdr = document.querySelector('.tl-header');
  const cells = [...hdr.children];
  const centres = cells.map(e => { const r = e.getBoundingClientRect();
                                   return r.left + r.width / 2; });
  const rows = [...document.querySelectorAll('#rows tr')]
                 .filter(tr => tr.querySelector('.tl'));
  let drift = 0, spread = 0;
  rows.forEach(tr => {
    const sc = [...tr.querySelectorAll('.tl .stepcell')]
                 .map(c => c.getBoundingClientRect());
    const ws = sc.map(c => c.width);
    spread = Math.max(spread, Math.max(...ws) - Math.min(...ws));
    sc.forEach((c, i) => { drift = Math.max(drift,
                 Math.abs(c.left + c.width / 2 - centres[i])); });
  });
  const cut = cells.filter(c => { const t = c.firstElementChild || c;
      return t.scrollWidth > t.clientWidth + 1 ||
             t.scrollHeight > t.clientHeight + 1; })
    .map(c => ({label: c.textContent, title: c.getAttribute('title')}));
  const twoPill = rows.filter(tr =>
      tr.querySelectorAll('td.c-state .spill').length === 2);
  const wrapped = twoPill.filter(tr => { const p = tr.querySelectorAll(
      'td.c-state .spill'); return p[1].offsetTop > p[0].offsetTop + 2; });
  const hs = rows.map(tr => tr.getBoundingClientRect().height);
  return {n_cells: cells.length, n_rows: rows.length, drift: drift,
          spread: spread, cut: cut, two_pill: twoPill.length,
          wrapped: wrapped.length, h_spread: Math.max(...hs) - Math.min(...hs),
          page_hscroll: document.documentElement.scrollWidth > innerWidth,
          rung: hdr.className,
          markers: [...document.querySelectorAll('.tl .marker')]
                     .map(m => m.textContent.trim())};
}'''


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for n in range(4, 10):
            steps = timeline(n)
            html = page_for(steps)
            print(f'\n=== {n} steps ===')
            for w in WIDTHS:
                pg = browser.new_page(viewport={'width': w, 'height': 900})
                pg.set_content(html)
                pg.wait_for_function('() => document.querySelectorAll('
                                     '"#rows td.c-timeline").length > 0')
                pg.evaluate("() => { const b = document.getElementById("
                            "'show-not-arrived'); b.checked = true; "
                            "b.dispatchEvent(new Event('change')); }")
                pg.wait_for_timeout(150)
                m = pg.evaluate(MEASURE)
                pg.close()
                tag = f'{n} steps @{w}px'
                check(m['n_cells'] == n and m['n_rows'] >= 10,
                      f'{tag}: {n} header cells over {m["n_rows"]} painted '
                      f'rows (otherwise nothing below measures anything)')
                check(m['drift'] <= 1,
                      f'{tag}: header labels centred on their dots '
                      f'(worst {m["drift"]:.1f}px)')
                check(m['spread'] <= 1,
                      f'{tag}: equal tracks in every row '
                      f'(spread {m["spread"]:.1f}px)')
                check(all(c['title'] == c['label'] for c in m['cut']),
                      f'{tag}: any cut-off label keeps its full text in a '
                      f'tooltip ({m["cut"]})')
                check(not m['cut'] or (n >= 7 and w <= 1152),
                      f'{tag}: labels fit without cutting, outside the '
                      f'extreme ≥7-steps-at-≤1152px case '
                      f'(cut: {[c["label"] for c in m["cut"]]})')
                check(m['two_pill'] >= 1 and m['wrapped'] == 0,
                      f'{tag}: {m["two_pill"]} two-pill state cells, none '
                      f'wrapped onto a second line')
                check(m['h_spread'] <= 2,
                      f'{tag}: one row height (spread {m["h_spread"]:.1f}px)')
                check(not m['page_hscroll'], f'{tag}: no horizontal page scroll')
                if n == 6 and w == 1440:
                    check(m['rung'] == 'tl-header',
                          f'{tag}: the stock look — no fitting rung '
                          f'({m["rung"]!r})')
                    check('2 of 10' in m['markers']
                          and not any('/' in x for x in m['markers']),
                          f'{tag}: full "2 of 10" markers '
                          f'({sorted(set(m["markers"]))})')
                if n == 9 and w == 1024:
                    check('2/10' in m['markers']
                          and not any(' of ' in x for x in m['markers']),
                          f'{tag}: narrow tracks get the compact "2/10" '
                          f'marker ({sorted(set(m["markers"]))})')
        browser.close()
    print()
    if _failures:
        print(f'{len(_failures)} CHECK(S) FAILED')
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
