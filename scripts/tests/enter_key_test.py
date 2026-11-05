#!/usr/bin/env python3
"""ENTER DOES WHAT THE FOCUSED CONTROL SAYS: real prodserver, real Chromium, real keys.

global.js binds Enter to the page's forward action. On a Prolific Results page that
action is "Back to Prolific", so before this was fixed a keyboard user on the results
accordion was sent out of the study. The rule now: a control with its own Enter action
keeps it; Enter anywhere else still moves forward. See DECISIONS.md, "Enter belongs to
the focused control".

WHAT IT CHECKS
  A. Every kind of control, on a fixture page running the real global.js: each one
     either keeps its own action (the forward control untouched) or still presses
     forward exactly once, an empty required field held by the browser's validation.
     The two lists sit together so that neither can pass alone.
  B. A Prolific participant from consent to Results, moving on by Enter: an empty
     required consent holds them; radio, text, slider and body focus move forward, a focused forward
     control submits once (POSTs are counted; on a live page oTree's live.js would otherwise
     make that key do nothing, which the fixture cannot show),
     Back goes back, the re-read dialog opens and closes, a textarea takes its newline.
  C. Prolific Results: the accordion toggles and the participant stays; Enter elsewhere
     and on the link still goes back to Prolific, once.
  D. A lab participant: the quiz-failure dialog's two buttons do what they say, required
     Demographics fields hold, the warning dialog closes on Enter without a second POST.
  E. The other endings: a declined consent's link, and the screen-out, where the exit
     must take a deliberate press and a stray Enter must do nothing.

THE SERVER RUNS ON A THROWAWAY COPY of the project (screen_lock_test.Server), so no run
can touch db.sqlite3. It always starts in production mode.

Run (needs Playwright, requests and oTree):
    python scripts/tests/enter_key_test.py
Optional environment:
    ENTER_KEY_SHOTS  where screenshots go (default _ai/screenshots/2026-11-05_enter_key/)
Exit 0 = all checks passed.
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)
from _repo import REPO_ROOT  # noqa: E402

SHOTS = os.environ.get('ENTER_KEY_SHOTS') or os.path.join(
    REPO_ROOT, '_ai', 'screenshots', '2026-11-05_enter_key')
os.makedirs(SHOTS, exist_ok=True)
# Importing that suite makes its screenshot folder; keep this run's in one place.
os.environ.setdefault('SCREEN_LOCK_SHOTS', SHOTS)

from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

import bot_walker  # noqa: E402
from quiz_answers import CORRECT  # noqa: E402
from screen_lock_test import (  # noqa: E402
    CC_CODE, PHONE_UA, PROLIFIC_ID, Server, _failures, api_session, check,
    new_context, page_name, participant_codes, section, submit)

SETTLE_MS = 500
GLOBAL_JS = os.path.join(REPO_ROOT, '_static', 'global', 'js', 'global.js')

# A: the fixture. Every control is in the form, as it is on a real oTree page.
FIXTURE = """<!DOCTYPE html><html><body>
<div class="screen-card"><form id="form" action="#" method="post">
  <input type="text" id="text"><input type="number" id="number"><input type="email" id="email">
  <input type="password" id="password"><input type="search" id="search"><input type="tel" id="tel">
  <input type="url" id="url"><input type="date" id="date"><input type="range" id="range">
  <input type="checkbox" id="checkbox"><input type="radio" id="radio" name="r">
  <span class="popover-anchor" tabindex="0" id="anchor">?</span>
  <div tabindex="0" id="plain_div">focusable, nothing to do</div>
  <details id="open_details" open><summary id="other_summary">s</summary>
      <input type="text" id="text_in_details"></details>

  <button type="button" id="button">b</button>
  <input type="button" id="input_button" value="b">
  <input type="reset" id="input_reset" value="r">
  <input type="file" id="input_file">
  <input type="submit" id="second_submit" value="Return" formnovalidate>
  <a href="#here" id="link">l</a>
  <details id="details"><summary id="summary">s</summary>inside</details>
  <select id="select"><option>1</option><option>2</option></select>
  <textarea id="textarea"></textarea>
  <div contenteditable="true" id="editable">x</div>
  <div contenteditable="plaintext-only" id="editable_plain">x</div>
  <div tabindex="0" role="button" id="role_button">b</div>
  <div tabindex="0" role="link" id="role_link">l</div>
  <div tabindex="0" role="tab" id="role_tab">t</div>
  <div tabindex="0" role="menuitem" id="role_menuitem">m</div>
  <div tabindex="0" role="option" id="role_option">o</div>
  <div tabindex="0" role="switch" id="role_switch">s</div>
  <div tabindex="0" role="combobox" id="role_combobox">c</div>
  <div tabindex="0" id="custom_widget">handles its own keys</div>

  <input type="submit" id="forward" value="Next" class="next-button">
</form></div>
<script>
window.__c = {};
window.__submits = 0;
window.__prevented = null;
document.addEventListener('click', function (e) {
    var id = e.target.id; if (id) { window.__c[id] = (window.__c[id] || 0) + 1; }
});
document.getElementById('form').addEventListener('submit', function (e) {
    e.preventDefault(); window.__submits += 1;
});
document.getElementById('custom_widget').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); window.__c.custom_widget = 1; }
});
// At window, so it reads the outcome after the page's document listeners.
window.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { window.__prevented = e.defaultPrevented; }
});
</script>
<script src="/global.js"></script>
</body></html>"""

# Enter must still press forward from these, exactly once.
FORWARD_FROM = ('text', 'number', 'email', 'password', 'search', 'tel', 'url', 'date', 'range',
                'checkbox', 'radio', 'anchor', 'plain_div', 'text_in_details')
# These fire their own click once; the forward control stays untouched.
OWN_CLICK = ('button', 'input_button', 'input_reset', 'input_file', 'second_submit', 'link',
             'role_button_handled')
# global.js must keep its hands off these: no forward click from the handler, and the
# browser's default left alone (not prevented), since that default IS the control's action.
HANDS_OFF = ('textarea', 'editable', 'editable_plain', 'role_button', 'role_link',
             'role_tab', 'role_menuitem', 'role_option', 'role_switch', 'role_combobox')


def reset_fixture(page):
    page.evaluate("""() => {
        window.__c = {}; window.__submits = 0; window.__prevented = null;
        if (document.activeElement) { document.activeElement.blur(); }
        document.getElementById('details').open = false;
        document.getElementById('textarea').value = '';
        location.hash = '';
    }""")


def counts(page):
    return page.evaluate('() => ({c: window.__c, s: window.__submits, p: window.__prevented})')


def press_on(page, element_id):
    reset_fixture(page)
    page.locator(f'#{element_id}').focus()
    check(page.evaluate('document.activeElement.id') == element_id, f'fixture: #{element_id} took focus')
    page.keyboard.press('Enter')
    page.wait_for_timeout(30)
    return counts(page)


def scenario_fixture(browser):
    section('A. EVERY KIND OF CONTROL, on the real global.js')
    context = browser.new_context()
    with open(GLOBAL_JS, encoding='utf-8') as fh:
        script = fh.read()
    context.route('http://fixture.test/global.js', lambda r: r.fulfill(
        status=200, content_type='text/javascript', body=script))
    context.route('http://fixture.test/', lambda r: r.fulfill(
        status=200, content_type='text/html', body=FIXTURE))
    page = context.new_page()
    page.goto('http://fixture.test/')

    for el in FORWARD_FROM:
        got = press_on(page, el)
        check(got['c'].get('forward') == 1 and got['s'] == 1,
              f'#{el}: Enter presses forward exactly once ({got})')

    reset_fixture(page)
    page.keyboard.press('Enter')
    page.wait_for_timeout(30)
    got = counts(page)
    check(got['c'].get('forward') == 1 and got['s'] == 1,
          f'nothing focused: Enter presses forward exactly once ({got})')

    # The browser's own check still decides: the press happens, the submit does not.
    page.evaluate("document.getElementById('text').required = true")
    got = press_on(page, 'text')
    check(got['c'].get('forward') == 1 and got['s'] == 0,
          f'an empty required field: Enter presses forward and validation holds it ({got})')
    page.evaluate("document.getElementById('text').value = 'filled'")
    got = press_on(page, 'text')
    check(got['s'] == 1, f'the same field filled: Enter submits, once ({got})')
    page.evaluate("document.getElementById('text').required = false")

    got = press_on(page, 'forward')
    check(got['c'].get('forward') == 1 and got['s'] == 1,
          f'#forward, focused: one click and one submit, no double ({got})')

    page.evaluate("""() => {
        const el = document.getElementById('role_button');
        const twin = el.cloneNode(true);
        twin.id = 'role_button_handled';
        el.after(twin);
        twin.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); twin.click(); }
        });
    }""")
    for el in OWN_CLICK:
        got = press_on(page, el)
        check(got['c'].get(el) == 1 and not got['c'].get('forward'),
              f'#{el}: Enter fires its own click once and not forward ({got})')
    got = press_on(page, 'second_submit')
    check(got['s'] == 1, f'#second_submit: the form is submitted by THAT control, once ({got})')

    got = press_on(page, 'summary')
    check(page.locator('#details').evaluate('el => el.open') and not got['c'].get('forward'),
          f'summary: Enter opens the details, not forward ({got})')
    got = press_on(page, 'textarea')
    check(page.locator('#textarea').input_value() == '\n' and not got['c'].get('forward'),
          f'textarea: Enter makes a new line, not forward ({got})')
    for el in ('editable', 'editable_plain'):
        before = page.locator(f'#{el}').evaluate('e => e.innerHTML')
        got = press_on(page, el)
        after = page.locator(f'#{el}').evaluate('e => e.innerHTML')
        check(after != before and not got['c'].get('forward'),
              f'#{el}: Enter edits the text, not forward ({before!r} to {after!r})')
    got = press_on(page, 'custom_widget')
    check(got['c'].get('custom_widget') == 1 and not got['c'].get('forward'),
          f'a widget that handled the key itself is not overridden ({got})')
    for el in HANDS_OFF:
        got = press_on(page, el)
        check(not got['c'].get('forward') and got['p'] is False,
              f'#{el}: global.js leaves Enter to the control ({got})')

    # A real Chromium may submit from a closed select by itself (implicit submission).
    # That is the browser's own behaviour; what must never happen is the handler adding
    # a second press on top, or swallowing the key from an open list.
    got = press_on(page, 'select')
    check(got['p'] is False and (got['c'].get('forward') or 0) <= 1 and got['s'] <= 1,
          f'select: global.js leaves Enter to the browser, at most one submit ({got})')

    # An IME commits its composition with Enter. Sent synthetically: headless Chromium
    # has no IME, and the flag on the event is the only thing the handler reads.
    reset_fixture(page)
    page.locator('#text').focus()
    page.evaluate("""() => document.getElementById('text').dispatchEvent(new KeyboardEvent(
        'keydown', {key: 'Enter', bubbles: true, cancelable: true, isComposing: true}))""")
    got = counts(page)
    check(not got['c'].get('forward'), f'an IME committing a word is not a forward press ({got})')

    # The dialogs rely on this: every forward control disabled means Enter finds nothing.
    reset_fixture(page)
    page.evaluate("""() => { setForwardControlsDisabled(true);
        document.querySelectorAll('.next-button, input[type=submit]').forEach(e => { e.disabled = true; }); }""")
    page.locator('#text').focus()
    page.keyboard.press('Enter')
    page.wait_for_timeout(30)
    got = counts(page)
    check(not got['c'].get('forward') and got['s'] == 0, f'forward disabled: Enter presses nothing ({got})')
    context.close()


class Posts:
    """Page POSTs seen on the wire: a double submit shows up here and nowhere else,
    because oTree answers the second POST with a redirect that looks like success."""

    def __init__(self, page):
        self.seen = []
        page.on('request', lambda r: self.seen.append(r.url)
                if r.method == 'POST' and '/p/' in r.url else None)

    def clear(self):
        self.seen.clear()


def enter_moves(page, posts, who):
    """Enter leaves this page for the next one, on exactly one POST."""
    before = page.url
    posts.clear()
    try:
        with page.expect_navigation(timeout=8000):
            page.keyboard.press('Enter')
    except PlaywrightTimeout:
        return check(False, f'{who}: Enter moved the page on (stayed on {page_name(page)})')
    page.wait_for_load_state('load')
    page.wait_for_timeout(250)
    moved = check(page.url != before, f'{who}: Enter moved the page on (now {page_name(page)})')
    check(len(posts.seen) == 1, f'{who}: exactly one POST ({len(posts.seen)})')
    return moved


def enter_holds(page, posts, who, why):
    """Enter leaves the participant on this page, with no POST at all."""
    before = page.url
    posts.clear()
    page.keyboard.press('Enter')
    page.wait_for_timeout(SETTLE_MS)
    page.wait_for_load_state('load')
    check(page.url == before and not posts.seen,
          f'{who}: {why} (on {page_name(page)}, {len(posts.seen)} POST)')


def counter(page):
    # Read without waiting on the element: a wrong press may already have left the page.
    page.wait_for_timeout(40)
    page.wait_for_load_state('load')
    return page.evaluate("(document.getElementById('instruction-counter') || {}).textContent || ''")


def fill_quiz(page):
    for field, answer in CORRECT.items():
        page.locator(f'input[name={field}][value="{answer}"]').check(force=True)


def drag_slider(page):
    slider = page.locator('#slider_payoff_points')
    slider.scroll_into_view_if_needed()
    box = slider.bounding_box()
    page.mouse.move(box['x'] + box['width'] * .2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] * .7, box['y'] + box['height'] / 2, steps=5)
    page.mouse.up()
    return slider


def check_instructions(page, posts, who):
    next_btn, prev_btn = page.locator('#nextBtn'), page.locator('#prevBtn')
    first = counter(page)
    next_btn.focus()
    page.keyboard.press('Enter')
    second = counter(page)
    check(second != first, f'{who}/instructing: Next, focused, moves on ({first} to {second})')
    page.keyboard.press('Enter')
    third = counter(page)
    check(third != second and third != first,
          f'{who}/instructing: one Enter on Next is one page, not two ({second} to {third})')
    prev_btn.focus()
    page.keyboard.press('Enter')
    check(counter(page) == second, f'{who}/instructing: Back, focused, goes back ({third} to {counter(page)})')
    page.evaluate('document.activeElement.blur()')
    page.keyboard.press('Enter')
    check(counter(page) == third, f'{who}/instructing: Enter with nothing focused moves on ({counter(page)})')
    page.evaluate('document.activeElement.blur()')
    for _ in range(30):
        if not counter(page):      # the pager hides its counter on the last step
            break
        page.keyboard.press('Enter')
        page.wait_for_timeout(20)
    if not check(page_name(page) == 'instructing' and next_btn.inner_text().strip() == 'Go to quiz',
                 f'{who}/instructing: reached the step before the quiz ({page_name(page)})'):
        return
    # The last step's Back is "Re-read instructions". It returns to page 1, where Back
    # is disabled while it still holds focus: Enter must not go dead there.
    prev_btn.focus()
    page.keyboard.press('Enter')
    page.wait_for_timeout(SETTLE_MS)
    if not check(counter(page) == first,
                 f'{who}/instructing: "Re-read instructions", focused, goes to page 1 ({page_name(page)}, {counter(page)!r})'):
        return
    page.keyboard.press('Enter')
    check(counter(page) not in (first, ''),
          f'{who}/instructing: Enter after Back disabled itself still moves on ({counter(page)!r})')
    page.evaluate('document.activeElement.blur()')
    for _ in range(30):
        if not counter(page):
            break
        page.keyboard.press('Enter')
        page.wait_for_timeout(20)
    next_btn.focus()
    if not enter_moves(page, posts, f'{who}/instructing, "Go to quiz" focused'):
        for _ in range(30):         # already failed above; let the walk go on
            if page_name(page) != 'instructing':
                break
            next_btn.click()
            page.wait_for_timeout(50)


def check_quiz_dialog(page, posts, who):
    opener = page.locator('#rereadOpen')
    backdrop = page.locator('#reread-backdrop')
    if not check(opener.count() == 1, f'{who}/quiz: the re-read button is on the page'):
        return
    opener.focus()
    enter_holds(page, posts, f'{who}/quiz, re-read button', 'Enter does not submit the quiz')
    check(backdrop.is_visible(), f'{who}/quiz: Enter on the re-read button opens the dialog')
    if not backdrop.is_visible():
        return
    enter_holds(page, posts, f'{who}/quiz, close button', 'Enter does not submit from behind the dialog')
    check(not backdrop.is_visible(), f'{who}/quiz: Enter closes the dialog')
    check(page.evaluate('document.activeElement.id') == 'rereadOpen',
          f'{who}/quiz: focus returns to the re-read button')
    check(page.locator('.button-row input.next-button').is_enabled(),
          f'{who}/quiz: the forward control is enabled again after the dialog')


def scenario_prolific(browser, server):
    section('B. A PROLIFIC PARTICIPANT, consent to Results, moving on by Enter')
    code = api_session(server, 'prolific', 2, num_experimental_rounds=2, prolific_cc_code=CC_CODE,
                       pilot_feedback=True, prolific_noconsent_code='NOCONS-A1B2C3')
    participant, declined = participant_codes(server, code)
    context = new_context(browser)
    context.route('**/*prolific*/**', lambda route: route.fulfill(status=200, body='ok'))
    page = context.new_page()
    posts = Posts(page)
    page.goto(f'{server.base}/InitializeParticipant/{participant}?participant_label={PROLIFIC_ID}')
    seen = []
    for _ in range(40):
        page.wait_for_load_state('load')
        name = page_name(page)
        seen.append(name)
        who = f'prolific/{name}'
        if name == 'Results':
            break
        if name == 'welcome':
            page.evaluate('document.activeElement && document.activeElement.blur()')
            enter_holds(page, posts, who, 'Enter with the required consent empty stays put')
            radio = page.locator('input[name=consent][value=True]')
            radio.check(force=True)
            radio.focus()
            moved = enter_moves(page, posts, f'{who}, radio focused')
        elif name == 'ConfirmProlificID':
            field = page.locator('#participant_id_external')
            field.fill(PROLIFIC_ID)
            field.focus()
            moved = enter_moves(page, posts, f'{who}, text field focused')
        elif name == 'DotBiGate':
            variant = page.locator('input[name=bot_dotbi_variant]').get_attribute('value')
            field = page.locator('#bot_dotbi_answer')
            field.fill(bot_walker.dotbi_from_variant(variant)['bot_dotbi_answer'])
            field.focus()
            moved = enter_moves(page, posts, f'{who}, text field focused')
        elif name == 'instructing':
            check_instructions(page, posts, 'prolific')
            moved = page_name(page) != name
        elif name == 'quiz':
            check_quiz_dialog(page, posts, 'prolific')
            if page_name(page) != 'quiz':
                moved = True
            else:
                fill_quiz(page)
                page.locator(f'input[name={next(iter(CORRECT))}]').first.focus()
                moved = enter_moves(page, posts, f'{who}, radio focused')
        elif name == 'GameStart':
            slider = drag_slider(page)
            if seen.count('GameStart') == 1:
                slider.focus()
                moved = enter_moves(page, posts, f'{who}, slider focused')
            else:
                page.locator('.button-row .next-button').focus()
                moved = enter_moves(page, posts, f'{who}, forward button focused')
        elif name == 'Feedback':
            box = page.locator('#feedback')
            box.fill('line')
            box.focus()
            enter_holds(page, posts, who, 'Enter in the textarea does not submit')
            check(box.input_value() == 'line\n', f'{who}: Enter in the textarea makes a new line')
            page.locator('.button-row .next-button').focus()
            moved = enter_moves(page, posts, f'{who}, forward button focused')
        else:
            if page.locator('.button-row .next-button').count() != 1:
                raise AssertionError(f'{who}: no single forward control to press')
            page.locator('.button-row .next-button').focus()
            moved = enter_moves(page, posts, f'{who}, forward button focused')
        if not moved and page_name(page) == name:
            # Already failed above; press it by mouse so the walk can reach what is left.
            if name == 'quiz':
                fill_quiz(page)
            submit(page)
    check(seen and seen[-1] == 'Results', f'the Enter-driven walk reached Results ({seen})')
    check(set(seen) >= {'welcome', 'ConfirmProlificID', 'DotBiGate', 'instructing', 'quiz', 'GameStart',
                        'Feedback'},
          f'the walk went through the pages it claims to ({seen})')
    if seen[-1] == 'Results':
        check_prolific_results(page, context)
    context.close()

    section('E1. ANOTHER ENDING: a declined consent has the same way back')
    context = new_context(browser)
    context.route('**/*prolific*/**', lambda route: route.fulfill(status=200, body='ok'))
    page = context.new_page()
    posts = Posts(page)
    page.goto(f'{server.base}/InitializeParticipant/{declined}?participant_label=x{declined}')
    page.wait_for_load_state('load')
    radio = page.locator('input[name=consent][value=False]')
    radio.check(force=True)
    radio.focus()
    enter_moves(page, posts, 'declined/welcome, radio focused')
    check(page_name(page) == 'Ended', f'declining reaches Ended ({page_name(page)})')
    link = page.locator('.button-row a.next-button')
    if check(link.count() == 1, 'Ended: the way back is on the page'):
        link.focus()
        with page.expect_navigation():
            page.keyboard.press('Enter')
        check('NOCONS-A1B2C3' in page.url, f'Ended: Enter on the link goes to its own code ({page.url})')
    context.close()


def check_prolific_results(page, context):
    section('C. PROLIFIC RESULTS: the page this bug was reported on')
    results_url = page.url
    toggle = page.locator('#results-toggle')
    wrapper = page.locator('#results-table-wrapper')
    link = page.locator('.button-row a.next-button')
    href = link.get_attribute('href')
    check(CC_CODE in (href or ''), f"the forward action here is the way back to Prolific ({href})")

    toggle.focus()
    was = toggle.get_attribute('aria-expanded')
    page.keyboard.press('Enter')
    page.wait_for_timeout(SETTLE_MS)
    left = page.url != results_url
    check(not left, f'Enter on the accordion does not leave the study (url {page.url})')
    if left:
        page.screenshot(path=os.path.join(SHOTS, 'red_left_for_prolific.png'))
        page.goto(results_url)
        page.wait_for_load_state('load')
    else:
        now = toggle.get_attribute('aria-expanded')
        check(now != was, f'Enter on the accordion toggles it, once ({was} to {now})')
        check(wrapper.evaluate("e => e.classList.contains('is-hidden')") == (now == 'false'),
              'the table on screen agrees with what the toggle announces')
        page.screenshot(path=os.path.join(SHOTS, 'green_results_accordion_after_enter.png'))
        page.keyboard.press('Enter')
        page.wait_for_timeout(100)
        check(toggle.get_attribute('aria-expanded') == was and page.url == results_url,
              'a second Enter toggles it back, still on the page')
    toggle.focus()
    was = toggle.get_attribute('aria-expanded')
    page.keyboard.press('Space')
    check(toggle.get_attribute('aria-expanded') != was, 'Space still toggles it, once')

    def navigations():
        got = []
        page.on('request', lambda r: got.append(r.url)
                if r.is_navigation_request() and CC_CODE in r.url else None)
        return got

    went = navigations()
    link.focus()
    with page.expect_navigation():
        page.keyboard.press('Enter')
    page.wait_for_timeout(250)
    check(page.url == href and len(went) == 1,
          f'Enter on the link itself goes back to Prolific, once ({page.url}, {len(went)})')

    page.goto(results_url)
    page.wait_for_load_state('load')
    page.evaluate('document.activeElement && document.activeElement.blur()')
    with page.expect_navigation():
        page.keyboard.press('Enter')
    check(page.url == href, f'Enter with nothing focused is still the forward action ({page.url})')

    # Kept as it was on purpose, and open to a decision: DECISIONS.md, same entry.
    page.goto(results_url)
    page.wait_for_load_state('load')
    page.locator('#results_completed').focus()
    with page.expect_navigation():
        page.keyboard.press('Enter')
    check(page.url == href, f'Enter on the "completed" checkbox is still the forward action ({page.url})')


def scenario_lab(browser, server):
    section('D. A LAB PARTICIPANT: the quiz-failure dialog, required fields, the warning dialog')
    code = api_session(server, 'lab', 2, num_experimental_rounds=1, quiz_comprehension_max_failures=1)
    first, second = participant_codes(server, code)
    context = new_context(browser)

    def to_quiz_failed(page):
        page.goto(f'{server.base}/InitializeParticipant/{page.participant}')
        for _ in range(12):
            page.wait_for_load_state('load')
            name = page_name(page)
            if name == 'quiz':
                break
            if name == 'startpage':
                with page.expect_navigation():
                    page.evaluate("document.getElementById('form').submit()")
            elif name == 'instructing':
                page.locator('#nextBtn').focus()
                before = page.url
                for _i in range(60):
                    page.keyboard.press('Enter')
                    page.wait_for_timeout(40)
                    if page.url != before:
                        break
            else:
                if page.locator('input[name=consent][value=True]').count():
                    page.locator('input[name=consent][value=True]').check(force=True)
                submit(page)
        for field, answer in CORRECT.items():
            wrong = page.locator(f'input[name={field}]:not([value="{answer}"])').first
            wrong.check(force=True)
        submit(page)
        page.wait_for_load_state('load')

    page = context.new_page()
    page.participant = second
    posts = Posts(page)
    to_quiz_failed(page)
    offer = page.locator('#quiz-modal-backdrop')
    check(offer.is_visible(), 'lab/quiz: a wrong answer brings up the re-read offer')
    primary = offer.locator('input.next-button')
    if check(primary.count() == 1 and page.evaluate('document.activeElement.value') == primary.get_attribute('value'),
             'lab/quiz: focus starts on the offer'):
        enter_moves(page, posts, 'lab/quiz, offer focused')
        check(page_name(page) == 'instructing',
              f'lab/quiz: Enter on "Re-read the instructions" goes to the instructions ({page_name(page)})')
    page.close()

    page = context.new_page()
    page.participant = first
    posts = Posts(page)
    to_quiz_failed(page)
    offer = page.locator('#quiz-modal-backdrop')
    keep = offer.locator('.modal-dismiss-button')
    if check(offer.is_visible() and keep.count() == 1, 'lab/quiz: the second participant gets the offer too'):
        keep.focus()
        enter_holds(page, posts, 'lab/quiz, Keep trying', 'Enter does not submit the quiz or spend the re-read')
        check(not offer.is_visible(), 'lab/quiz: Enter on "Keep trying" dismisses the offer')
    if page_name(page) == 'quiz':
        if offer.is_visible():     # only if the step above failed
            page.evaluate('dismissQuizModal()')
        fill_quiz(page)
        page.locator(f'input[name={next(iter(CORRECT))}]').first.focus()
        enter_moves(page, posts, 'lab/quiz, after dismissing, radio focused')

    for _ in range(12):
        page.wait_for_load_state('load')
        name = page_name(page)
        if name == 'quiz':     # only if the step above failed
            fill_quiz(page)
            submit(page)
        elif name == 'instructing':
            page.locator('#nextBtn').click()
            page.wait_for_timeout(40)
        elif name == 'GameStart':
            drag_slider(page)
            submit(page)
        elif name in ('Demographics', 'Results'):
            break
        else:
            submit(page)
    check(page_name(page) == 'Demographics', f'lab: reached Demographics ({page_name(page)})')
    # These fields are checked by the server, not the browser: the POST comes back to
    # the same page with a warning dialog, whose own Enter must only close it.
    age = page.locator('#id_age')
    if check(age.count() == 1, 'lab/Demographics: the required age field is on the page'):
        age.focus()
        url = page.url
        with page.expect_navigation():
            page.keyboard.press('Enter')
        page.wait_for_load_state('load')
        check(page_name(page) == 'Demographics', f'an empty required field holds them ({page_name(page)}, {page.url == url})')
        warning = page.locator('.modal-backdrop:not([hidden])')
        if check(warning.count() == 1, 'the warning dialog says what is missing'):
            enter_holds(page, posts, 'lab/Demographics, warning dialog', 'Enter on its OK does not submit again')
            check(warning.count() == 0, 'lab/Demographics: Enter closes the warning dialog')
        page.locator('#id_age').fill('30')
        select = page.locator('select[name=gender]')
        if select.count():
            select.select_option('Female')
        else:
            page.locator('input[name=gender][value=Female]').check(force=True)
    if page.locator('#id_bank').count():
        page.locator('#id_bank').fill('NL91ABNA0417164300')
        page.locator('#id_bank_confirmation').fill('NL91ABNA0417164300')
        page.locator('#id_bank').focus()
    moved = enter_moves(page, posts, 'lab/Demographics, all filled, text field focused')
    if moved:
        check(page_name(page) == 'Results', f'lab: Demographics moved on to Results ({page_name(page)})')
        toggle = page.locator('#results-toggle')
        toggle.focus()
        was = toggle.get_attribute('aria-expanded')
        results_url = page.url
        page.keyboard.press('Enter')
        page.wait_for_timeout(SETTLE_MS)
        check(toggle.get_attribute('aria-expanded') != was and page.url == results_url,
              'lab/Results: Enter toggles the accordion')
    context.close()


def scenario_screened_out(browser, server):
    section('E2. THE SCREEN-OUT: an irreversible exit is never one stray Enter away')
    code = api_session(server, 'prolific', 1, prolific_allowed_devices=['computer'],
                       prolific_device_code='DEVICE-A1B2C3')
    context = new_context(browser, user_agent=PHONE_UA)
    context.route('**/*prolific*/**', lambda route: route.fulfill(status=200, body='ok'))
    page = context.new_page()
    page.goto(f'{server.base}/InitializeParticipant/{participant_codes(server, code)[0]}')
    page.wait_for_load_state('load')
    url = page.url
    link = page.locator('a.exit-button')
    if not check(link.count() == 1 and link.is_visible(), 'screen-out: the exit is on the page'):
        context.close()
        return
    page.evaluate('document.activeElement && document.activeElement.blur()')
    page.keyboard.press('Enter')
    page.wait_for_timeout(SETTLE_MS)
    check(page.url == url, f'screen-out: a stray Enter leaves them there ({page.url})')
    link.focus()
    with page.expect_navigation():
        page.keyboard.press('Enter')
    check(page.url != url, f'screen-out: Enter on the focused exit does press it ({page.url})')
    context.close()


def main():
    server = Server()
    try:
        server.start()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                scenario_fixture(browser)
                scenario_prolific(browser, server)
                scenario_lab(browser, server)
                scenario_screened_out(browser, server)
            finally:
                browser.close()
        section('the server log')
        with open(server.log_path, errors='replace') as fh:
            lines = fh.read().splitlines()
        # As in screen_lock_test: a websocket closed by a fast navigation logs a traceback.
        bad = [line for i, line in enumerate(lines)
               if ' 500 ' in line
               or ('Traceback' in line and (i == 0 or 'closing handshake failed' not in lines[i - 1]))]
        check(not bad, f'no 500 and no traceback in the server log ({bad[:3]})')
    finally:
        server.destroy()
    print(f"\n{'FAILED: ' + str(len(_failures)) if _failures else 'ALL PASSED'}")
    for failure in _failures:
        print(f'  - {failure}')
    sys.exit(1 if _failures else 0)


if __name__ == '__main__':
    main()
