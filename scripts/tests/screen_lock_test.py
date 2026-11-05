#!/usr/bin/env python3
"""THE SCREEN LOCK END TO END: a real `otree prodserver` and real Chromium.

Session config `screen_lock` (settings.py, ON by default) makes participant pages
feel like a screen: no selecting text outside fields, no text cursor, no dragging
images, no right-click menu. Every check here is a real mouse or keyboard action
on a real page, read back from the browser; a rule being in a stylesheet proves
nothing, because a lock that fails to apply produces no error anywhere.

WHAT IT WALKS
  1. a LAB session and a PROLIFIC session on the shipped default, every page from
     consent to Results: locked on each page, and every control and field used on
     the way (radio, label, slider, checkbox, pager, dialog, accordion, typing,
     Ctrl+V, selecting inside a field, keyboard only);
  2. the `.selectable` way out: every way back to Prolific keeps its menu, and text
     with the class can really be selected and copied to the clipboard;
  3. integrity code: right-clicks, drags and selection attempts cause no tab-monitor
     violation, no focus-trace departure, no copy flag; a real Ctrl+C still flags;
  4. switch OFF: every page normal, and the script never requested;
  5. a session CREATED BEFORE THE KEY EXISTED, by the real route: a server on settings
     without the key creates it, a server on current settings serves it. OFF, and it
     reaches the ending;
  6. admin pages and the room's pages: not locked;
  7. a phone (emulated touch): tap works, long-press in a field keeps its menu;
  8. the pre-deploy audit reports a frozen session without failing on this key.

THE SERVER RUNS ON A THROWAWAY COPY of the project in a temp folder, so no run can
touch the project's db.sqlite3. It always starts in production mode.

Run (needs Playwright, requests and oTree):
    python scripts/tests/screen_lock_test.py
Optional environment:
    SCREEN_LOCK_SHOTS  where screenshots go (default _ai/screenshots/screen_lock/)
Exit 0 = all checks passed.
"""
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402

import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from quiz_answers import CORRECT  # noqa: E402
import bot_walker  # noqa: E402

PASSWORD = 'check-pass'
REST_KEY = 'check-rest-key'
PROLIFIC_ID = '5f3c9d2e1a7b4c6d8e9f0a1b'
IBAN = 'NL91ABNA0417164300'
CC_CODE = 'COMP-A1B2C3'
PHONE_UA = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36')
SHOTS = os.environ.get('SCREEN_LOCK_SHOTS') or os.path.join(
    REPO_ROOT, '_ai', 'screenshots', 'screen_lock')
os.makedirs(SHOTS, exist_ok=True)
SCRIPT = 'global/js/screen_lock.js'
KEY_LINE = re.compile(r'^\s*screen_lock=True,\s*$', re.M)

_failures = []


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}", flush=True)
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===', flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    """A real prodserver on a throwaway copy of the project."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='screen_lock_')
        self.app = os.path.join(self.tmp, 'app')
        shutil.copytree(REPO_ROOT, self.app, ignore=shutil.ignore_patterns(
            '.git', '_ai', 'previews', '__pycache__', 'db.sqlite3*'))
        self.otree = os.path.join(os.path.dirname(sys.executable), 'otree')
        self.log_path = os.path.join(self.tmp, 'server.log')
        self.proc = None
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith('OTREE_') and k != 'DATABASE_URL'}
        self.env.update(OTREE_PRODUCTION='1', OTREE_AUTH_LEVEL='STUDY',
                        OTREE_ADMIN_PASSWORD=PASSWORD, OTREE_REST_KEY=REST_KEY,
                        OTREE_SECRET_KEY='check-secret',
                        PATH=os.path.dirname(self.otree) + os.pathsep + os.environ['PATH'])
        subprocess.run([self.otree, 'resetdb', '--noinput'], cwd=self.app,
                       env=self.env, check=True, capture_output=True)

    def start(self):
        self.stop()
        log = open(self.log_path, 'ab')
        self.proc = subprocess.Popen(
            [self.otree, 'prodserver', f'127.0.0.1:{self.port}'], cwd=self.app,
            env=self.env, stdout=log, stderr=log, start_new_session=True)
        for _ in range(400):
            try:
                if requests.get(self.base + '/login', timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(f'server died; see {self.log_path}')
            time.sleep(0.25)
        raise RuntimeError('the server did not answer')

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(5)
        self.proc = None

    def destroy(self):
        self.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def settings_without_key(self):
        """Put the app on settings that predate the key. Returns the current text."""
        path = os.path.join(self.app, 'settings.py')
        with open(path, encoding='utf-8') as fh:
            current = fh.read()
        old, n = KEY_LINE.subn('', current)
        assert n == 1, 'the screen_lock line in settings.py was not found'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(old)
        return current

    def restore_settings(self, text):
        with open(os.path.join(self.app, 'settings.py'), 'w', encoding='utf-8') as fh:
            fh.write(text)


def api_session(server, config, n, **fields):
    r = requests.post(server.base + '/api/sessions', json={
        'session_config_name': config, 'num_participants': n,
        'modified_session_config_fields': fields},
        headers={'otree-rest-key': REST_KEY}, timeout=300)
    r.raise_for_status()
    return r.json()['code']


def session_detail(server, code):
    r = requests.get(f'{server.base}/api/sessions/{code}',
                     headers={'otree-rest-key': REST_KEY}, timeout=60)
    r.raise_for_status()
    return r.json()


def participant_codes(server, code):
    return [p['code'] for p in session_detail(server, code)['participants']]


def participant_vars(server, code, names):
    """{participant_code: {name: value}} over the REST API."""
    r = requests.post(f'{server.base}/api/get_session/{code}',
                      json={'participant_vars': list(names)},
                      headers={'otree-rest-key': REST_KEY}, timeout=60)
    r.raise_for_status()
    return {p['code']: p for p in r.json()['participants']}


# Runs before any page script, so it sees the outcome AFTER the page's own document
# listeners: an event at window has already been through document.
RECORDER = """
window.__lock = {menu: [], drag: []};
window.addEventListener('contextmenu', function (e) {
    window.__lock.menu.push({prevented: e.defaultPrevented, tag: e.target.tagName,
                             pointer: e.pointerType});
});
window.addEventListener('dragstart', function (e) {
    window.__lock.drag.push({prevented: e.defaultPrevented, tag: e.target.tagName});
});
"""

# The first visible stretch of plain page text: not a control, not `.selectable`.
FIND_TEXT = """() => {
    const seen = document.querySelectorAll(
        '.header-title, .section-text, .experimental-content p, .experimental-content li');
    for (const el of seen) {
        if (el.closest('a, button, label, .selectable')) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 20 && r.height > 5 && el.innerText.trim().length > 3) {
            el.setAttribute('data-lock-probe', '1');
            return true;
        }
    }
    return false;
}"""


def page_name(page):
    m = re.search(r'/p/[^/]+/[^/]+/([^/]+)/\d+', page.url)
    return m.group(1) if m else page.url


def clear_probe(page):
    page.evaluate("""() => {
        const s = window.getSelection(); if (s) s.removeAllRanges();
        window.__lock.menu.length = 0; window.__lock.drag.length = 0;
    }""")


def park_mouse(page):
    page.keyboard.press('Escape')
    page.mouse.move(1, 1)


def box_of(page, selector):
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed()
    return loc.bounding_box()


def right_click(page, x, y):
    before = page.evaluate('window.__lock.menu.length')
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(30)
    events = page.evaluate('window.__lock.menu')[before:]
    return events


def drag_image(page):
    """A real mouse drag on the logo. Returns (image found, dragstart events)."""
    if not page.locator('.logo-section img').count():
        return False, []
    box = box_of(page, '.logo-section img')
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2 + 40, box['y'] + box['height'] / 2 - 40, steps=6)
    page.wait_for_timeout(30)
    page.mouse.up()
    page.wait_for_timeout(30)
    return True, page.evaluate('window.__lock.drag')


def drag_select(page, selector):
    """Drag across real text with the mouse. Returns what got selected."""
    box = box_of(page, selector)
    y = box['y'] + min(box['height'] / 2, 12)
    page.mouse.move(box['x'] + 1, y)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] - 2, y, steps=6)
    page.mouse.up()
    return page.evaluate('String(window.getSelection())')


def probe_page(page, locked, who):
    """The four promises on whichever page this is, by real actions.

    `locked` True is the lock; False is the paired proof that the same action on the
    same page does work without it, so no assertion is an absence of nothing."""
    name = page_name(page)
    tag = f'{who}/{name}'
    clear_probe(page)
    check(page.locator('link[href*="global/css/base.css"]').count() > 0,
          f'{tag}: the study bundle is on this page')
    has_script = page.locator(f'script[src*="{SCRIPT}"]').count() > 0
    has_class = page.evaluate("document.documentElement.classList.contains('screen-lock')")
    check(has_script == locked and has_class == locked,
          f'{tag}: script loaded and html class set: {has_script}, {has_class} (want {locked})')
    if not page.evaluate(FIND_TEXT):
        check(False, f'{tag}: found plain text to try this on')
        return
    probe = '[data-lock-probe]'
    selected = drag_select(page, probe)
    box = box_of(page, probe)
    menu = right_click(page, box['x'] + 5, box['y'] + min(box['height'] / 2, 10))
    page.keyboard.press('Escape')
    cursor = page.evaluate("getComputedStyle(document.querySelector('[data-lock-probe]')).cursor")
    found_img, drags = drag_image(page)
    page.evaluate('window.getSelection().removeAllRanges()')
    if locked:
        check(selected == '', f'{tag}: dragging across text selects nothing (got {selected[:30]!r})')
        check(cursor == 'default', f'{tag}: arrow cursor over text (got {cursor})')
        check(len(menu) == 1 and menu[0]['prevented'],
              f'{tag}: a real right-click on text fires and its menu is stopped ({menu})')
        if found_img:
            check(not any(not d['prevented'] for d in drags),
                  f'{tag}: the logo does not drag ({drags})')
    else:
        check(len(selected) > 3, f'{tag}: dragging across text selects it ({selected[:30]!r})')
        check(cursor == 'auto', f'{tag}: the normal cursor over text (got {cursor})')
        check(len(menu) == 1 and not menu[0]['prevented'],
              f'{tag}: a real right-click opens the normal menu ({menu})')
        if found_img:
            check(any(not d['prevented'] for d in drags),
                  f'{tag}: the logo drags as normal ({drags})')
    park_mouse(page)


def probe_field(page, selector, who, typed='hello there'):
    """A text field under the lock: typing, caret, selecting by mouse and keyboard,
    Ctrl+V, dragging selected text. All of it must work as normal."""
    tag = f'{who}/{page_name(page)} {selector}'
    field = page.locator(selector).first
    field.scroll_into_view_if_needed()
    was = field.input_value()
    field.click()
    page.keyboard.press('Control+a')
    page.keyboard.type(typed)
    check(field.input_value() == typed, f'{tag}: typing works ({field.input_value()!r})')
    check(field.evaluate('e => getComputedStyle(e).cursor') == 'text',
          f'{tag}: the text cursor stays over a field')
    box = field.bounding_box()
    page.mouse.dblclick(box['x'] + 12, box['y'] + box['height'] / 2)
    span = field.evaluate('e => e.value.slice(e.selectionStart, e.selectionEnd)')
    check(span.strip() != '', f'{tag}: a double click selects a word inside the field ({span!r})')
    page.keyboard.press('Control+a')
    span = field.evaluate('e => e.value.slice(e.selectionStart, e.selectionEnd)')
    check(span == typed, f'{tag}: Ctrl+A selects the field, not the page ({span!r})')
    page.evaluate("navigator.clipboard.writeText('PASTED-7')")
    page.keyboard.press('Control+v')
    check(field.input_value() == 'PASTED-7', f'{tag}: Ctrl+V pastes ({field.input_value()!r})')
    page.keyboard.press('Control+a')
    clear_probe_keep_selection(page)
    box = field.bounding_box()
    page.mouse.move(box['x'] + 12, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + 60, box['y'] + box['height'] / 2 + 3, steps=5)
    page.mouse.up()
    drags = page.evaluate('window.__lock.drag')
    check(all(not d['prevented'] for d in drags) and len(drags) >= 1,
          f'{tag}: dragging selected text in a field stays allowed ({drags})')
    box = field.bounding_box()
    menu = right_click(page, box['x'] + 12, box['y'] + box['height'] / 2)
    page.keyboard.press('Escape')
    check(len(menu) == 1 and menu[0]['prevented'],
          f'{tag}: right-click in a field is stopped, as accepted by Julian ({menu})')
    field.fill(was)


def clear_probe_keep_selection(page):
    page.evaluate('window.__lock.menu.length = 0; window.__lock.drag.length = 0;')


def label_of(page, control):
    return page.locator(f'label[for="{control.get_attribute("id")}"]')


def submit(page, selector='.button-row .next-button'):
    with page.expect_navigation(timeout=30000):
        page.locator(selector).last.click()


def check_controls_cursor(page, tag):
    """Radios, buttons and links keep their own cursor, not the text one."""
    facts = page.evaluate("""() => [...document.querySelectorAll(
        'input[type=radio], input[type=checkbox], input[type=submit], button, a[href], select')]
        .filter(e => e.getBoundingClientRect().width > 0)
        .map(e => e.tagName + ':' + (e.type || '') + ':' + getComputedStyle(e).cursor)""")
    check(not any(f.endswith(':text') for f in facts),
          f'{tag}: no control shows a text cursor ({sorted(set(facts))[:6]})')


def walk(page, server, who, code, locked, label=None, probe=True, fields=False):
    """A real participant, by real clicks, from the entry link to the ending.
    Returns the list of pages seen, ending in the terminal page, which stays open."""
    url = f'{server.base}/InitializeParticipant/{code}'
    if label:
        url += f'?participant_label={label}'
    page.goto(url)
    seen = []
    for _ in range(60):
        page.wait_for_load_state('load')
        name = page_name(page)
        seen.append(name)
        if probe:
            probe_page(page, locked, who)
            check_controls_cursor(page, f'{who}/{name}')
        if name in ('Results', 'Ended', 'NeutralReturn'):
            return seen
        if name == 'startpage':
            # The lab's hold screen has no button: the experimenter moves everyone
            # on. Its own form is what that submits.
            with page.expect_navigation():
                page.evaluate("document.getElementById('form').submit()")
        elif name == 'welcome':
            consent = page.locator('input[name=consent][value=True]')
            if consent.count():
                # By the visible label, not the input: labels must still click.
                label_of(page, consent).click()
                check(consent.is_checked(), f'{who}/welcome: clicking the consent label ticks the radio')
            if fields:
                page.screenshot(path=os.path.join(SHOTS, f'{who}_welcome.png'))
            submit(page)
        elif name == 'ConfirmProlificID':
            if fields:
                probe_field(page, '#participant_id_external', who)
                page.locator('#participant_id_external').fill(PROLIFIC_ID)
            submit(page)
        elif name == 'DotBiGate':
            variant = page.locator('input[name=bot_dotbi_variant]').get_attribute('value')
            answer = bot_walker.dotbi_from_variant(variant)['bot_dotbi_answer']
            if fields:
                probe_field(page, '#bot_dotbi_answer', who, typed='12 34')
            page.locator('#bot_dotbi_answer').fill(answer)
            submit(page, '.dotbi-js .next-button, .button-row .next-button:visible')
        elif name == 'instructing':
            for _step in range(60):
                # Both pager routes: a click, and the arrow keys the page offers.
                next_btn = page.locator('#nextBtn')
                before = page.url
                if _step == 1:
                    counter = page.locator('#instruction-counter').inner_text()
                    # The page ignores arrows while a button holds focus.
                    page.evaluate('document.activeElement.blur()')
                    page.keyboard.press('ArrowRight')
                    page.wait_for_timeout(30)
                    check(page.locator('#instruction-counter').inner_text() != counter
                          or page.url != before,
                          f'{who}/instructing: the arrow key still pages')
                    if page.url != before:
                        break
                    continue
                next_btn.click()
                page.wait_for_timeout(40)
                if page.url != before:
                    break
                try:
                    page.wait_for_url(lambda u: u != before, timeout=150)
                    break
                except Exception:
                    pass
        elif name == 'quiz':
            if page.locator('#rereadOpen').count():
                page.locator('#rereadOpen').click()
                check(page.locator('#reread-backdrop').is_visible(),
                      f'{who}/quiz: the re-read dialog opens')
                page.locator('#rereadClose').click()
                check(not page.locator('#reread-backdrop').is_visible(),
                      f'{who}/quiz: the re-read dialog closes')
            for field, answer in CORRECT.items():
                radio = page.locator(f'input[name={field}][value="{answer}"]')
                label_of(page, radio).click()
                check(radio.is_checked(), f'{who}/quiz: clicking the label picks {field}')
            submit(page)
        elif name == 'GameStart':
            if page.locator('#focus_trace_departures').count():
                value = page.locator('#focus_trace_departures').input_value()
                check(value in ('0', ''), f'{who}/GameStart: the probes above left no focus-trace departure ({value!r})')
            slider = page.locator('#slider_payoff_points')
            slider.scroll_into_view_if_needed()
            box = slider.bounding_box()
            page.mouse.move(box['x'] + box['width'] * .2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] * .7, box['y'] + box['height'] / 2, steps=8)
            page.mouse.up()
            v = int(slider.input_value())
            check(55 <= v <= 85, f'{who}/GameStart: the slider follows a mouse drag ({v})')
            page.keyboard.press('ArrowRight')
            check(int(slider.input_value()) == v + 1,
                  f'{who}/GameStart: the slider follows the keyboard')
            check(page.evaluate("window.getSelection().toString()") == '',
                  f'{who}/GameStart: dragging the slider selected nothing')
            submit(page)
        elif name == 'Demographics':
            if page.locator('#id_age').count():
                # A number field by real keys; selecting inside one is not exposed.
                page.locator('#id_age').click()
                page.keyboard.type('30')
                check(page.locator('#id_age').input_value() == '30', f'{who}/Demographics: typing a number works')
                page.locator('select[name=gender], input[name=gender]').first.wait_for(state='attached')
                if page.locator('select[name=gender]').count():
                    page.locator('select[name=gender]').select_option('Female')
                else:
                    page.locator('input[name=gender][value=Female]').check(force=True)
            if page.locator('#id_bank').count():
                if fields:
                    # The study's own rule stays: the confirmation cannot be pasted.
                    page.locator('#id_bank_confirmation').click()
                    page.evaluate("navigator.clipboard.writeText('PASTED-7')")
                    page.keyboard.press('Control+v')
                    check(page.locator('#id_bank_confirmation').input_value() == '',
                          f'{who}/Demographics: the IBAN confirmation still refuses a paste')
                    probe_field(page, '#id_bic', who)
                page.locator('#id_bank').fill(IBAN)
                page.locator('#id_bank_confirmation').fill(IBAN)
            submit(page)
        elif name == 'Feedback':
            if fields:
                probe_field(page, '#feedback', who)
            page.locator('#feedback').fill('')
            submit(page)
        else:
            submit(page)
    raise AssertionError(f'{who}: never reached an ending; pages: {seen}')


def check_results_controls(page, who):
    """The terminal page: the accordion, the checkbox and the keyboard."""
    toggle = page.locator('#results-toggle')
    was = toggle.get_attribute('aria-expanded')
    toggle.click()
    check(toggle.get_attribute('aria-expanded') != was, f'{who}/Results: the accordion opens and closes')
    toggle.focus()
    # Space here; Enter on this control is pinned by enter_key_test.py.
    page.keyboard.press('Space')
    check(toggle.get_attribute('aria-expanded') == was, f'{who}/Results: the accordion works by keyboard')
    label = page.locator('label[for=results_completed]')
    label.click(position={'x': 40, 'y': 8})
    check(page.locator('#results_completed').is_checked(), f'{who}/Results: clicking the label ticks the box')
    page.locator('#results_completed').focus()
    page.keyboard.press('Space')
    check(not page.locator('#results_completed').is_checked(), f'{who}/Results: Space works on the box')
    page.keyboard.press('Shift+Tab')
    active = page.evaluate('document.activeElement.id')
    check(active == 'results-toggle', f'{who}/Results: Tab moves between the controls ({active})')
    page.locator('#results_completed').focus()
    page.keyboard.press('Space')


def check_selectable(page, who, want_href):
    """The way out. The completion link keeps its menu, and text carrying the class
    really reaches the clipboard, with no typing."""
    link = page.locator('.button-row a.selectable')
    check(link.count() == 1, f'{who}: the way back carries .selectable')
    href = link.get_attribute('href') or ''
    check(want_href in href, f'{who}: the link carries the completion code ({href})')
    clear_probe(page)
    box = box_of(page, '.button-row a.selectable')
    menu = right_click(page, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.keyboard.press('Escape')
    check(len(menu) == 1 and not menu[0]['prevented'],
          f'{who}: right-click on the link keeps its menu, so Copy link address is there ({menu})')
    style = link.evaluate('e => [getComputedStyle(e).userSelect, getComputedStyle(e).cursor]')
    check(style == ['text', 'pointer'], f'{who}: the link is selectable and keeps its pointer ({style})')

    # A study that shows a code as text, which is what the class is for: the same
    # rendered page with such a line in it, as in the specimen in template.html.
    page.evaluate(f"""() => {{
        const p = document.createElement('p');
        p.className = 'section-text';
        p.innerHTML = 'Your code: <span class="selectable" id="lock-code">{CC_CODE}</span>';
        document.querySelector('.experimental-content').prepend(p);
        document.querySelector('.experimental-content').scrollTop = 0;
    }}""")
    page.evaluate("navigator.clipboard.writeText('UNTOUCHED')")
    selected = drag_select(page, '#lock-code')
    check(selected == CC_CODE, f'{who}: dragging across a .selectable code selects it ({selected!r})')
    page.keyboard.press('Control+c')
    page.wait_for_timeout(50)
    clip = page.evaluate('navigator.clipboard.readText()')
    check(clip == CC_CODE, f'{who}: Ctrl+C puts the code on the clipboard ({clip!r})')
    box = box_of(page, '#lock-code')
    menu = right_click(page, box['x'] + 5, box['y'] + box['height'] / 2)
    page.keyboard.press('Escape')
    check(len(menu) == 1 and not menu[0]['prevented'], f'{who}: the code keeps its right-click menu ({menu})')
    check(page.locator('#lock-code').evaluate('e => getComputedStyle(e).cursor') == 'text',
          f'{who}: a text cursor over the code says it can be selected')
    page.screenshot(path=os.path.join(SHOTS, f'{who}_results_with_selectable_code.png'))
    page.evaluate("document.getElementById('lock-code').parentElement.remove();"
                  "window.getSelection().removeAllRanges()")

    # The paired negative: the same action on locked text copies nothing.
    page.evaluate("navigator.clipboard.writeText('UNTOUCHED')")
    page.evaluate(FIND_TEXT)
    drag_select(page, '[data-lock-probe]')
    page.keyboard.press('Control+c')
    page.wait_for_timeout(50)
    clip = page.evaluate('navigator.clipboard.readText()')
    check(clip == 'UNTOUCHED', f'{who}: the same on locked text copies nothing ({clip!r})')


def new_context(browser, **kwargs):
    context = browser.new_context(viewport=kwargs.pop('viewport', {'width': 1280, 'height': 720}), **kwargs)
    context.add_init_script(RECORDER)
    context.grant_permissions(['clipboard-read', 'clipboard-write'])
    return context


def scenario_on(browser, server):
    section('1. LAB, shipped default: locked on every page, every control works')
    lab = api_session(server, 'lab', 1, num_experimental_rounds=2)
    detail = session_detail(server, lab)
    check(detail['config'].get('screen_lock') is True,
          f"the lab session got the shipped default ({detail['config'].get('screen_lock')})")
    context = new_context(browser)
    page = context.new_page()
    seen = walk(page, server, 'lab', participant_codes(server, lab)[0], True, fields=True)
    check(seen[-1] == 'Results', f'the lab walk reached Results ({seen})')
    check(set(seen) >= {'welcome', 'instructing', 'quiz', 'GameStart', 'payoff', 'Demographics'},
          f'the lab walk went through the real pages ({seen})')
    check_results_controls(page, 'lab')
    page.screenshot(path=os.path.join(SHOTS, 'lab_results.png'))
    context.close()

    section('2. PROLIFIC, shipped default: the full gated flow, and the way out')
    prolific = api_session(server, 'prolific', 3, num_experimental_rounds=2,
                           prolific_cc_code=CC_CODE, telemetry_focus_trace=True,
                           pilot_feedback=True)
    codes = participant_codes(server, prolific)
    context = new_context(browser)
    page = context.new_page()
    seen = walk(page, server, 'prolific', codes[0], True, label=PROLIFIC_ID, fields=True)
    check(seen[-1] == 'Results', f'the Prolific walk reached Results ({seen})')
    check(set(seen) >= {'welcome', 'ConfirmProlificID', 'DotBiGate', 'TabMonitorAgree', 'quiz', 'GameStart'},
          f'the Prolific walk went through the gated pages ({seen})')
    check_results_controls(page, 'prolific')
    check_selectable(page, 'prolific', CC_CODE)
    page.screenshot(path=os.path.join(SHOTS, 'prolific_results.png'))
    href = page.locator('.button-row a.selectable').get_attribute('href')
    # Prolific itself is answered locally: this proves the click, not their site.
    context.route('**/*prolific*/**', lambda route: route.fulfill(status=200, body='ok'))
    with page.expect_navigation():
        page.locator('.button-row a.selectable').click()
    check(page.url == href, f'a click on the link goes to the completion URL ({page.url})')
    context.close()

    section('3. INTEGRITY: the lock itself raises no violation and no copy flag')
    names = ['tab_monitor_focus_loss_count', 'tab_monitor_focus_loss_count_outro',
             'tab_monitor_disqualified', 'exit_code', 'telemetry_welcome', 'telemetry_quiz']
    got = participant_vars(server, prolific, names)[codes[0]]
    # Five pages of right-clicks, drags and selection attempts behind this walk.
    check(got.get('tab_monitor_focus_loss_count') in (0, None),
          f"no tab-monitor violation after every probe ({got.get('tab_monitor_focus_loss_count')})")
    check(got.get('tab_monitor_focus_loss_count_outro') in (0, None),
          f"none on the outro pages either ({got.get('tab_monitor_focus_loss_count_outro')})")
    check(got.get('exit_code') == 1, f"the participant finished normally ({got.get('exit_code')})")

    # A clean walk with no Ctrl+C and one with a real Ctrl+C, each with the same
    # selection attempts: the flag follows the key press, not the lock.
    context = new_context(browser)
    page = context.new_page()
    walk_to_quiz_then(page, server, codes[1], press_copy=False)
    context.close()
    context = new_context(browser)
    page = context.new_page()
    walk_to_quiz_then(page, server, codes[2], press_copy=True)
    # The monitor is alive on these pages, so the zero above means something: a real
    # departure on the same kind of page is counted.
    page.wait_for_load_state('load')
    check(page_name(page) == 'GameStart', f'on a monitored page ({page_name(page)})')
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    counted = 0
    for _ in range(40):
        page.wait_for_timeout(250)
        counted = participant_vars(server, prolific, ['tab_monitor_focus_loss_count'])[codes[2]].get(
            'tab_monitor_focus_loss_count')
        if counted:
            break
    check(counted == 1, f'a real departure on a monitored page is counted ({counted})')
    context.close()
    got = participant_vars(server, prolific, ['telemetry_quiz'])
    clean, pressed = str(got[codes[1]].get('telemetry_quiz')), str(got[codes[2]].get('telemetry_quiz'))
    check('"copy_detected":false' in clean.replace(' ', ''),
          f'selection attempts and right-clicks alone raise no copy flag ({clean[:60]})')
    check('"copy_detected":true' in pressed.replace(' ', ''),
          f'a real Ctrl+C on the locked page still records the copy flag ({pressed[:60]})')
    return prolific


def walk_to_quiz_then(page, server, code, press_copy):
    page.goto(f'{server.base}/InitializeParticipant/{code}?participant_label={code}')
    for _ in range(30):
        page.wait_for_load_state('load')
        name = page_name(page)
        if name == 'quiz':
            page.evaluate(FIND_TEXT)
            drag_select(page, '[data-lock-probe]')
            box = box_of(page, '[data-lock-probe]')
            right_click(page, box['x'] + 5, box['y'] + 5)
            page.keyboard.press('Escape')
            if press_copy:
                page.keyboard.press('Control+c')
            for field, answer in CORRECT.items():
                page.locator(f'input[name={field}][value="{answer}"]').check(force=True)
            submit(page)
            return
        if name == 'welcome':
            if page.locator('input[name=consent][value=True]').count():
                page.locator('input[name=consent][value=True]').check(force=True)
            submit(page)
        elif name == 'ConfirmProlificID':
            page.locator('#participant_id_external').fill(code)
            submit(page)
        elif name == 'DotBiGate':
            variant = page.locator('input[name=bot_dotbi_variant]').get_attribute('value')
            page.locator('#bot_dotbi_answer').fill(bot_walker.dotbi_from_variant(variant)['bot_dotbi_answer'])
            submit(page, '.button-row .next-button:visible')
        elif name == 'instructing':
            for _step in range(60):
                before = page.url
                page.locator('#nextBtn').click()
                try:
                    page.wait_for_url(lambda u: u != before, timeout=150)
                    break
                except Exception:
                    pass
        else:
            submit(page)
    raise AssertionError('never reached the quiz')


def scenario_other_endings(browser, server):
    section('3b. EVERY OTHER WAY BACK TO PROLIFIC keeps its menu under the lock')
    # Declined consent, the DOT-BI return and the device screen-out.
    code = api_session(server, 'prolific', 2, prolific_noconsent_code='NOCONS-A1B2C3',
                       prolific_bot_return_code='RETURN-A1B2C3')
    declined, wrong = participant_codes(server, code)
    screened = api_session(server, 'prolific', 1, prolific_allowed_devices=['computer'],
                           prolific_device_code='DEVICE-A1B2C3')
    context = new_context(browser)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{declined}?participant_label=x{declined}')
    page.wait_for_load_state('load')
    page.locator('input[name=consent][value=False]').check(force=True)
    submit(page)
    check(page_name(page) == 'Ended', f'declining reaches Ended ({page_name(page)})')
    check_way_back(page, '.button-row a.selectable', 'NOCONS-A1B2C3', 'Ended')
    context.close()

    context = new_context(browser)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{wrong}?participant_label=x{wrong}')
    for _ in range(6):
        page.wait_for_load_state('load')
        name = page_name(page)
        if name == 'NeutralReturn':
            break
        if name == 'welcome':
            page.locator('input[name=consent][value=True]').check(force=True)
        elif name == 'ConfirmProlificID':
            page.locator('#participant_id_external').fill(f'x{wrong}')
        elif name == 'DotBiGate':
            page.locator('#bot_dotbi_answer').fill('0')
            submit(page, '.button-row .next-button:visible')
            continue
        submit(page)
    check(page_name(page) == 'NeutralReturn', f'a wrong DOT-BI answer reaches NeutralReturn ({page_name(page)})')
    check_way_back(page, '.button-row a.selectable', 'RETURN-A1B2C3', 'NeutralReturn')
    context.close()

    context = new_context(browser, user_agent=PHONE_UA)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{participant_codes(server, screened)[0]}')
    page.wait_for_load_state('load')
    check_way_back(page, 'a.selectable', 'DEVICE-A1B2C3', 'screen-out')
    context.close()


def check_way_back(page, selector, code, who):
    link = page.locator(selector)
    check(link.count() == 1 and code in (link.get_attribute('href') or ''),
          f'{who}: the link is there and carries its own code')
    check(page.evaluate("document.documentElement.classList.contains('screen-lock')"),
          f'{who}: the page is locked')
    clear_probe(page)
    box = box_of(page, selector)
    menu = right_click(page, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.keyboard.press('Escape')
    check(len(menu) == 1 and not menu[0]['prevented'], f'{who}: the link keeps its right-click menu ({menu})')


def scenario_off(browser, server):
    section('4. SWITCH OFF: every page normal, and the script never requested')
    lab = api_session(server, 'lab', 1, num_experimental_rounds=2, screen_lock=False)
    prolific = api_session(server, 'prolific', 1, num_experimental_rounds=2, screen_lock=False,
                           prolific_cc_code=CC_CODE)
    for who, code, label in (('off-lab', lab, None), ('off-prolific', prolific, PROLIFIC_ID)):
        context = new_context(browser)
        page = context.new_page()
        requested = []
        page.on('request', lambda r: requested.append(r.url))
        seen = walk(page, server, who, participant_codes(server, code)[0], False, label=label)
        check(seen[-1] == 'Results', f'{who}: reached Results ({seen})')
        check(any('global/css/base.css' in u for u in requested), f'{who}: the study CSS was requested')
        check(not any('screen_lock' in u for u in requested), f'{who}: screen_lock.js was never requested')
        page.screenshot(path=os.path.join(SHOTS, f'{who}_results.png'))
        context.close()

    section('4b. ON and OFF lay out identically, so the lock moves no geometry')
    on = api_session(server, 'lab', 1, num_experimental_rounds=1)
    off = api_session(server, 'lab', 1, num_experimental_rounds=1, screen_lock=False)
    boxes = []
    for code in (on, off):
        context = new_context(browser)
        page = context.new_page()
        page.goto(f'{server.base}/InitializeParticipant/{participant_codes(server, code)[0]}')
        page.wait_for_load_state('load')
        with page.expect_navigation():
            page.evaluate("document.getElementById('form').submit()")   # past the hold screen
        check(page_name(page) == 'welcome', f'on the consent page ({page_name(page)})')
        boxes.append(page.evaluate("""() => [...document.querySelectorAll(
            '.screen-card, .experimental-header, .experimental-content, .button-row, .logo-section, label, p')]
            .map(e => { const r = e.getBoundingClientRect();
                        return [e.tagName, r.x, r.y, r.width, r.height].join(); })"""))
        context.close()
    check(len(boxes[0]) > 5 and boxes[0] == boxes[1],
          f'the consent page has the same {len(boxes[0])} boxes with the switch on and off')


def scenario_frozen(browser, server):
    section('5. A SESSION CREATED BEFORE THE KEY EXISTED, by the real route')
    current = server.settings_without_key()
    server.start()
    frozen = api_session(server, 'lab', 1, num_experimental_rounds=2)
    detail = session_detail(server, frozen)
    check('screen_lock' not in detail['config'],
          'a server on the old settings made a session with no screen_lock key')
    server.stop()
    server.restore_settings(current)
    server.start()
    detail = session_detail(server, frozen)
    check(detail['code'] == frozen and 'screen_lock' not in detail['config'],
          'on the current build that session still has no key, while the shipped default is ON')
    fresh = api_session(server, 'lab', 1, num_experimental_rounds=1)
    check(session_detail(server, fresh)['config'].get('screen_lock') is True,
          'a session created now on the same server does have the lock on')
    context = new_context(browser)
    page = context.new_page()
    seen = walk(page, server, 'frozen', participant_codes(server, frozen)[0], False)
    check(seen[-1] == 'Results', f'the frozen session walks to Results, unlocked ({seen})')
    context.close()


def scenario_not_locked(browser, server, prolific):
    section('6. ADMIN PAGES AND THE ROOM: not locked')
    context = new_context(browser)
    page = context.new_page()
    page.goto(server.base + '/login')
    page.fill('input[name=username]', 'admin')
    page.fill('input[name=password]', PASSWORD)
    page.click('button[type=submit], input[type=submit]')
    page.wait_for_load_state('load')
    for path, text in ((f'/SessionMonitor/{prolific}', 'th, td, h2, h3, a, p'),
                       (f'/SessionData/{prolific}', 'th, td, h2, h3, a, p'),
                       (f'/SessionPayments/{prolific}', 'th, td, h2, h3, a, p'),
                       (f'/AdminReport/{prolific}', 'th, td, h2, h3, a, p'),
                       (f'/experimenter_dashboard/{prolific}', 'th, td, h1, h2, h3, a, p, span')):
        resp = page.goto(server.base + path)
        page.wait_for_load_state('load')
        page.wait_for_timeout(200)
        check(resp.status == 200, f'{path}: an admin page answers ({resp.status})')
        state = page.evaluate(f"""() => {{
            const shown = [...document.querySelectorAll('{text}')].filter(
                e => e.getBoundingClientRect().width > 10 && e.innerText && e.innerText.trim().length > 2);
            return {{script: !!document.querySelector('script[src*="screen_lock"]'),
                     cls: document.documentElement.classList.contains('screen-lock'),
                     shown: shown.length,
                     select: shown.length ? getComputedStyle(document.body).userSelect : null}};
        }}""")
        check(state['shown'] > 0 and not state['script'] and not state['cls'] and state['select'] != 'none',
              f'{path}: real content, no script, no class, body selectable ({state})')
        clear_probe(page)
        menu = right_click(page, 300, 200)
        page.keyboard.press('Escape')
        check(len(menu) == 1 and not menu[0]['prevented'], f'{path}: the right-click menu is normal ({menu})')
    page.goto(f'{server.base}/room/study')
    page.wait_for_load_state('load')
    state = page.evaluate("""() => ({start: !!document.querySelector('.next-button'),
        script: !!document.querySelector('script[src*="screen_lock"]'),
        cls: document.documentElement.classList.contains('screen-lock')})""")
    # The room has no session, so a per-session switch cannot reach it. DECISIONS.md.
    check(state['start'] and not state['script'] and not state['cls'],
          f'the room gate, before any session, carries no lock ({state})')
    context.close()


def scenario_phone(browser, server):
    section('7. A PHONE (emulated touch, not a real device)')
    code = api_session(server, 'prolific', 1, num_experimental_rounds=1)
    pid = participant_codes(server, code)[0]
    context = new_context(browser, viewport={'width': 390, 'height': 800}, has_touch=True,
                          is_mobile=True, user_agent=PHONE_UA, device_scale_factor=2)
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{pid}?participant_label={pid}')
    page.wait_for_load_state('load')
    check(page_name(page) == 'welcome', f'the phone reached consent ({page_name(page)})')
    cdp = context.new_cdp_session(page)

    def long_press(x, y):
        cdp.send('Input.synthesizeTapGesture', {'x': x, 'y': y, 'duration': 1100, 'tapCount': 1,
                                                'gestureSourceType': 'touch'})
        page.wait_for_timeout(100)

    def menu_stopped(selector, pointer):
        # Headless Chromium fires no contextmenu on a long-press, so this hands the
        # page the event an Android browser sends. It proves the rule, not a phone.
        return page.evaluate("""([selector, pointer]) => {
            const e = new PointerEvent('contextmenu', {bubbles: true, cancelable: true, pointerType: pointer});
            document.querySelector(selector).dispatchEvent(e);
            return e.defaultPrevented;
        }""", [selector, pointer])

    page.evaluate(FIND_TEXT)
    box = box_of(page, '[data-lock-probe]')
    long_press(box['x'] + 10, box['y'] + 6)
    check(page.evaluate('String(window.getSelection())') == '', 'a long-press on text selects nothing')
    check(menu_stopped('[data-lock-probe]', 'touch'), 'the menu a long-press raises on text is stopped')
    consent = page.locator('input[name=consent][value=True]')
    if consent.count():
        label_of(page, consent).tap()
        check(consent.is_checked(), 'a tap on the consent label picks it')
    page.screenshot(path=os.path.join(SHOTS, 'phone_welcome.png'))
    with page.expect_navigation():
        page.locator('.button-row .next-button').last.tap()
    check(page_name(page) == 'ConfirmProlificID', f'a tap on Next moves on ({page_name(page)})')
    field = page.locator('#participant_id_external')
    check(not menu_stopped('#participant_id_external', 'touch'),
          'a long-press in a field keeps its menu, the only way to paste on a phone')
    check(menu_stopped('#participant_id_external', 'mouse'),
          'while a right-click with a mouse in the same field is stopped')
    field.tap()
    page.keyboard.type('abc')
    check('abc' in field.input_value(), f'typing into the field works ({field.input_value()!r})')
    context.close()


def scenario_audit():
    section('8. THE PRE-DEPLOY AUDIT: reported, not failed, and only this key')
    sys.path.insert(0, _TESTS_DIR)
    from otree_inprocess import boot
    boot(production=True)
    sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
    import predeploy_check as pdc
    defaults = {'screen_lock': True, 'tab_monitor': False}
    stored = [('OLD', 'lab', {'name': 'lab', 'tab_monitor': False}, True)]
    problems, diffs = pdc.audit_frozen_session_configs(stored, {'lab': {'name': 'lab'}}, defaults)
    check(not problems, f'a live session lacking screen_lock does not fail the audit ({problems})')
    check(any(key == 'screen_lock' and 'EXEMPT' in str(extra) for _, key, _f, extra in diffs),
          f'and it is reported, with the named reason ({[d[1] for d in diffs]})')
    stored = [('OLD', 'lab', {'name': 'lab', 'screen_lock': True}, True)]
    problems, _ = pdc.audit_frozen_session_configs(stored, {'lab': {'name': 'lab'}}, defaults)
    check([p[1] for p in problems] == ['tab_monitor'], f'another missing key still fails ({problems})')


def main():
    server = Server()
    try:
        server.start()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                prolific = scenario_on(browser, server)
                scenario_other_endings(browser, server)
                scenario_not_locked(browser, server, prolific)
                scenario_phone(browser, server)
                scenario_off(browser, server)
                scenario_frozen(browser, server)
            finally:
                browser.close()
        with open(server.log_path, errors='replace') as fh:
            log = fh.read()
        section('the server log')
        # uvicorn logs a websocket closed by a fast navigation as a traceback; it is
        # noise, named by the line before it. Any other traceback counts.
        lines = log.splitlines()
        bad = [line for i, line in enumerate(lines)
               if ' 500 ' in line
               or ('Traceback' in line and (i == 0 or 'closing handshake failed' not in lines[i - 1]))]
        check(not bad, f'no 500 and no traceback in the server log ({bad[:3]})')
    finally:
        server.destroy()
    scenario_audit()
    print(f"\n{'FAILED: ' + str(len(_failures)) if _failures else 'ALL PASSED'}")
    for failure in _failures:
        print(f'  - {failure}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
