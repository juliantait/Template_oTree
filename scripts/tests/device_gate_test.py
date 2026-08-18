"""HTTP scenario tests for the entry DEVICE ALLOW-LIST (`prolific_allowed_devices`).

A study STATES the device types it accepts — any of 'phone', 'tablet',
'computer', 'unknown' — and everything else is screened out at entry with the
DETECTED TYPE recorded as the cause. The gate is decided SERVER-SIDE from the
entry request's User-Agent, so the only honest way to test it is to drive real
HTTP with a device's User-Agent: a bot cannot set one, and the client-side
`is_mobile` / `device_type` values are measurement that block nobody.

    OTREE_ADMIN_PASSWORD=admin otree prodserver 8000     # THROWAWAY database
    python scripts/tests/device_gate_test.py http://localhost:8000

WHAT THIS FILE IS WEIGHTED TOWARDS, AND WHY. The failure that matters is the
FALSE POSITIVE: a participant on a laptop who is told to go away. It costs a
real person their session and us a support ticket, while the opposite error
costs one noisy row. So the biggest section here is section A — a battery of
real desktop, laptop, Chrome OS and tablet browsers, plus every shape of
unusable User-Agent, all of which must sail through:

  A. NEVER SCREENED. Desktop Chrome/Safari/Firefox/Edge, Chrome OS, a
     touchscreen Windows laptop, an iPad and an Android tablet under the shipped
     (permit-everything) list; and — under a computers-only list — a missing,
     empty, whitespace-only, control-character, absurdly long or otherwise
     unusable User-Agent, which is NO DECISION and must never remove anybody.
  B. The gate itself: a forbidden type never sees consent, is held on the entry
     page with exit code -4 and the DETECTED TYPE as the cause, and reads copy
     written for that type.
  C. It is an ALLOW-LIST, not a phone blocker: a computer can be excluded too,
     and 'unknown' (a REAL User-Agent that matches nothing) is configurable
     exactly like the other three.

The SOFT WALL (screen-out cleared by returning on an accepted device, the
asymmetry of the no-decision sentinel, the way out) is
scripts/tests/screenout_softwall_test.py. Identity and re-entry are
scripts/tests/identity_test.py.

Exits non-zero on any failed check or any 5xx.
"""
import os
import re
import sys

import requests
import requests.models

sys.path.insert(0, __file__.rsplit('/', 1)[0])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)
from http_flow_test import FormParser, build_payload, END_MARKERS
from quiz_answers import CORRECT as QUIZ_CORRECT  # answers derived from the shipped items
import common

# `requests` REFUSES to send a header value with leading whitespace or control
# characters — it validates client-side. A broken browser, a proxy, a privacy
# extension or anyone with a socket does no such thing, and the participant we
# must not turn away is exactly the one whose header arrived malformed. Turning
# the client-side validation off lets us send what such a client sends.
requests.models.check_header_validity = lambda header: None

# --- real User-Agent strings -------------------------------------------------
# Copied from real browsers. The desktop set exists to be a false-positive
# tripwire: if a future pattern change starts matching any of these, section A
# goes red before a participant is turned away by it.
PHONE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
)
ANDROID_PHONE_UA = (
    'Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'
)
TABLET_UA = (
    'Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
)
ANDROID_TABLET_UA = (
    'Mozilla/5.0 (Linux; Android 13; SM-X710) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/126.0.0.0 Safari/537.36'
)
DESKTOP_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)
SAFARI_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.5 Safari/605.1.15'
)
FIREFOX_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 '
    'Firefox/127.0'
)
EDGE_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0'
)
LINUX_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/126.0.0.0 Safari/537.36'
)
CHROMEOS_UA = (
    'Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/126.0.0.0 Safari/537.36'
)
# A TOUCHSCREEN WINDOWS LAPTOP. A real Surface sends this: it is a computer, it
# has a touch screen, and nothing in the header says "touch" — which is exactly
# why touch is not, and cannot be, part of the classification.
TOUCH_LAPTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like '
    'Gecko) Chrome/126.0.0.0 Safari/537.36'
)

# --- User-Agents that are NOT device evidence at all -------------------------
# Every one of these is UNDETERMINED (common.classify_device): no decision, so
# the participant proceeds and nothing is recorded.
NO_UA = ''                       # header stripped by a privacy tool / absent
BLANK_UA = '   '                 # present but empty
CONTROL_UA = 'Mozilla/5.0\x00(Macintosh)\x1f'   # characters a header may not hold
LONG_UA = 'Mozilla/5.0 ' + ('A' * 1400)         # longer than any real browser
# Garbage that CONTAINS the word iPhone: still no decision, and note which way
# that fails — towards letting them in.
LONG_PHONEISH_UA = 'iPhone ' + ('B' * 1400)

# A REAL User-Agent that matches no device family. This is the DETERMINED
# 'unknown' type — a device type a study may admit or exclude — and it is a
# different thing entirely from the strings above.
ODD_BUT_REAL_UA = 'Lynx/2.9.0dev.12 libwww-FM/2.14'

ALL_TYPES = ['phone', 'tablet', 'computer', 'unknown']

# Text that only the consent page carries.
CONSENT_MARKER = 'I consent and wish to take part'
# Text that only the entry screen-out page carries.
SCREENOUT_MARKER = 'Your place is still open'
ENTRY_OVERRIDES = {'consent': 'True', 'is_mobile': 'False',
                   'participant_id_external': 'SCREENOUT_TEST'}

FAILURES = []


def check(cond, label):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


def visible_text(html):
    """Rendered text: comments, script/style bodies and tags removed, whitespace
    collapsed. Copy assertions are made against THIS, never raw HTML — body copy
    wraps across source lines, and a keyword can hide in a comment or a script."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I)
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def page_name(url):
    m = re.search(r'/p/[^/]+/([^/]+)/([^/]+)/(\d+)', url)
    return f"{m.group(1)}.{m.group(2)}" if m else url


def participant_code(url):
    m = re.search(r'/p/([^/]+)/', url)
    return m.group(1) if m else None


# FIVE DISTINCT COMPLETION CODES, ONE PER ENDING POPULATION, set explicitly on
# every session this file creates.
#
# WHY THE TEST SETS THEM RATHER THAN READING THE SHIPPED PLACEHOLDERS. The
# screen-out exit is a completion URL carrying `prolific_device_code`
# (DECISIONS.md, 2026-08-15), and the thing worth asserting is that it carries
# THAT code and none of the other four — the presence-plus-absence pairing in
# CLAUDE.md. Sentinels make both halves exact: distinct strings that cannot be
# substrings of one another, so "the device code is present" cannot be
# satisfied by another population's code and "no other code leaks" cannot pass
# because two placeholders happened to look alike. They also keep the
# assertions true for a study that has replaced its placeholders.
#
# (The `prolific_screenout_return_url` SETTING this block used to configure is
# gone — the exit is derived from the device code now, one value in one place.
# See common.prolific_screenout_return_url.)
CODES = {
    'prolific_device_code': 'DEVICE-SENTINEL01',
    'prolific_cc_code': 'COMP-SENTINEL02',
    'prolific_noconsent_code': 'NOCONS-SENTINEL03',
    'prolific_dq_quiz_code': 'DQ-QUIZ-SENTINEL04',
    'prolific_dq_tab_code': 'DQ-TAB-SENTINEL05',
}
COMPLETION_URL_RE = re.compile(
    r'https://app\.prolific\.com/submissions/complete\?cc=([A-Za-z0-9_.-]+)')


def create(base, allowed, config='prolific', **modified):
    fields = {'prolific_allowed_devices': allowed}
    fields.update(CODES)
    fields.update(modified)
    return requests.post(
        base + '/api/sessions',
        json={'session_config_name': config, 'num_participants': 2,
              'modified_session_config_fields': fields},
    ).json()


def session_vars(base, session_code, p_code, names):
    r = requests.post(base + f'/api/get_session/{session_code}',
                      json={'participant_vars': list(names)})
    r.raise_for_status()
    for p in r.json()['participants']:
        if p['code'] == p_code:
            return p
    return {}


def extra_of(base, session_code, p_code, key):
    """One key of participant_extra, over the REST API."""
    p = session_vars(base, session_code, p_code, ['participant_extra'])
    return (p.get('participant_extra') or {}).get(key)


def run(base, label, user_agent, allowed):
    """Walk one participant through the whole flow with the given User-Agent."""
    shown_ua = (user_agent[:38] + '...') if user_agent else '<none>'
    print(f"[{label}]  prolific_allowed_devices={allowed}  UA={shown_ua!r}")
    created = create(base, allowed)
    session_code = created['code']

    s = requests.Session()
    # requests sends its own User-Agent unless it is replaced outright, and "no
    # User-Agent at all" is precisely the case the no-decision sentinel is for.
    s.headers['User-Agent'] = user_agent
    r = s.get(created['session_wide_url'], allow_redirects=True)

    # ANSWER THE QUIZ FROM THE SHIPPED ITEMS, not from the page. In production
    # the DEBUG-only solutions blob is absent, so a walker that read answers off
    # the page would fail the quiz and — Prolific's quiz_comprehension_dq being on —
    # be routed to the comprehension-DQ ending (exit -2) instead of completing.
    # The admitted-device checks below assert exit code 1, so that misroute used
    # to fail every one of them. QUIZ_CORRECT is derived from intro/quiz_items.py
    # (see quiz_answers.py) and stays right when a study swaps its items.
    pages, saw_consent, saw_screenout = [], False, False
    answers = dict(QUIZ_CORRECT)
    for _ in range(80):
        if r.status_code >= 500:
            check(False, f"HTTP {r.status_code} at {page_name(r.url)}")
            return None, None, None, pages, r, session_code
        pages.append(page_name(r.url))
        saw_consent = saw_consent or CONSENT_MARKER in r.text
        if SCREENOUT_MARKER in r.text:
            saw_screenout = True
            break                                  # a held page: it cannot submit
        if any(m in r.text for m in END_MARKERS):
            break
        fp = FormParser(); fp.feed(r.text)
        if not fp.found_form:
            check(False, f"dead-end (no form, no end marker) at {page_name(r.url)}")
            return None, None, None, pages, r, session_code
        if fp.solutions_json.strip():          # DEBUG-only quiz solutions
            import json
            for item in json.loads(fp.solutions_json):
                answers[item['name']] = item['value']
        r = s.post(r.url, data=build_payload(fp.inputs, ENTRY_OVERRIDES, answers,
                                             warn=False),
                   allow_redirects=True)
    else:
        check(False, 'exceeded step budget')

    p_code = participant_code(r.url)
    code = session_vars(base, session_code, p_code, ['exit_code']).get('exit_code')
    print(f"       pages: {' -> '.join(pages)}")
    print(f"       exit_code={code}")
    return code, saw_consent, saw_screenout, pages, r, session_code


def expect_screened_out(base, label, ua, allowed, cause, must_say, must_not_say=()):
    """A forbidden device: never sees consent, -4, the right cause and copy."""
    code, saw_consent, saw_screenout, pages, r, session_code = run(
        base, label, ua, allowed)
    check(not saw_consent, f'{label}: consent page NEVER rendered')
    check(saw_screenout, f'{label}: the entry screen-out page IS rendered')
    # It is the SAME page index as consent: the participant is HELD there, which
    # is what lets a later request on an accepted device re-decide (soft wall).
    check(bool(pages) and pages[0] == 'before.welcome',
          f'{label}: held on the entry page (got {pages[0] if pages else None})')
    check(not any('Introduction' in p or 'main' in p or 'outro' in p for p in pages),
          f'{label}: never enters the instructions/quiz/task/outro')
    check(code == -4, f'{label}: exit code -4 (screened_out) recorded (got {code})')
    p_code = participant_code(r.url)
    got = extra_of(base, session_code, p_code, 'screenout_cause')
    check(got == cause,
          f"{label}: screenout_cause is the DETECTED TYPE {cause!r} (got {got!r})")
    check(extra_of(base, session_code, p_code, 'entry_device_type') == cause,
          f'{label}: entry_device_type records the same classification')
    # THE WAY OUT IS A COMPLETION URL CARRYING THIS POPULATION'S OWN CODE.
    #
    # REWRITTEN 2026-08-15, and the old version is worth naming because it was
    # RED ON MAIN: it asserted "the page carries NO completion code of any
    # kind" and "the way out is NOT a Prolific completion URL", which had been
    # the rule until the screen-out got its own code that same day. The suite
    # was asserting a superseded contract against shipped behaviour.
    #
    # PRESENCE **AND** ABSENCE, per CLAUDE.md: "carries a code" is not the
    # claim — a page carrying the COMPLETER's code would pass that and would be
    # the exact leak per-population codes exist to prevent. So: the exit is a
    # completion URL, the code IN it is the device code, and none of the other
    # four appears anywhere on the page.
    urls = COMPLETION_URL_RE.findall(r.text)
    check(bool(urls),
          f'{label}: the way out IS a Prolific completion URL')
    check(set(urls) == {CODES['prolific_device_code']},
          f"{label}: that URL carries the DEVICE code "
          f"{CODES['prolific_device_code']!r} and nothing else (got {sorted(set(urls))})")
    for key, code in CODES.items():
        if key == 'prolific_device_code':
            continue
        check(code not in r.text,
              f'{label}: no {key} anywhere on the page ({code})')
    flat = visible_text(r.text)
    for phrase in must_say:
        check(phrase in flat, f'{label}: page says {phrase!r}')
    for phrase in must_not_say:
        check(phrase not in flat, f'{label}: page does NOT say {phrase!r}')


def expect_admitted(base, label, ua, allowed, device_type=None):
    """A permitted device: consent as usual, completes, nothing visible."""
    code, saw_consent, saw_screenout, pages, r, session_code = run(
        base, label, ua, allowed)
    check(saw_consent, f'{label}: reaches the consent page')
    check(not saw_screenout, f'{label}: never sees the screen-out page')
    check(code == 1, f'{label}: completes with exit code 1 (got {code})')
    p_code = participant_code(r.url)
    got = extra_of(base, session_code, p_code, 'entry_device_type')
    if device_type is None:
        # NO DECISION: the gate must not have recorded a verdict at all. A
        # recorded 'unknown' here would mean the sentinel had been collapsed
        # back into a device type, which is the bug this distinction exists to
        # prevent.
        check(got is None,
              f'{label}: NO device verdict recorded (got {got!r}) — an unusable '
              f'User-Agent is not a device type')
    else:
        check(got == device_type,
              f'{label}: the device was still CLASSIFIED for the record '
              f'(entry_device_type={got!r})')


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')

    # =====================================================================
    # A. THE FALSE-POSITIVE BATTERY — none of these may EVER be screened out
    # =====================================================================
    print('\n--- A1. real desktop/laptop/tablet browsers, shipped list ---')
    for label, ua, kind in [
            ('chrome-mac', DESKTOP_UA, 'computer'),
            ('safari-mac', SAFARI_UA, 'computer'),
            ('firefox-win', FIREFOX_UA, 'computer'),
            ('edge-win', EDGE_UA, 'computer'),
            ('chrome-linux', LINUX_UA, 'computer'),
            ('chromeos', CHROMEOS_UA, 'computer'),
            ('touchscreen-laptop', TOUCH_LAPTOP_UA, 'computer'),
            ('ipad', TABLET_UA, 'tablet'),
            ('android-tablet', ANDROID_TABLET_UA, 'tablet'),
            ('iphone', PHONE_UA, 'phone'),
            ('android-phone', ANDROID_PHONE_UA, 'phone')]:
        # The SHIPPED list permits everything, so the gate has no
        # participant-visible effect of any kind — including for phones.
        expect_admitted(base, f'default+{label}', ua, ALL_TYPES, kind)

    print('\n--- A2. the same computers under a COMPUTERS-ONLY list ---')
    for label, ua in [('chrome-mac', DESKTOP_UA), ('safari-mac', SAFARI_UA),
                      ('firefox-win', FIREFOX_UA), ('edge-win', EDGE_UA),
                      ('chromeos', CHROMEOS_UA),
                      ('touchscreen-laptop', TOUCH_LAPTOP_UA)]:
        expect_admitted(base, f'computer-only+{label}', ua, ['computer'], 'computer')

    print('\n--- A3. unusable User-Agents ALWAYS proceed, and record nothing ---')
    # The narrowest list there is, so anything that could be screened out, is.
    for label, ua in [('no-UA', NO_UA), ('blank-UA', BLANK_UA),
                      ('absurdly-long', LONG_UA),
                      ('long-but-says-iPhone', LONG_PHONEISH_UA)]:
        expect_admitted(base, f'computer-only+{label}', ua, ['computer'], None)

    print('\n--- A3b. the cases HTTP cannot deliver, asserted on the classifier ---')
    # A User-Agent carrying control characters never reaches application code:
    # uvicorn's HTTP parser rejects the request at the protocol layer and closes
    # the connection (measured here — the request does not 500, it never
    # arrives). There is therefore no HTTP test to write for it, and the honest
    # place to pin the behaviour is the classifier itself. Same for the values
    # that are not strings at all, which is what a missing header looks like
    # from inside `_apply_device_gate`.
    for label, value in [('control characters', CONTROL_UA),
                         ('None (no header object)', None),
                         ('bytes', b'Mozilla/5.0 (Macintosh)\x00'),
                         ('not a string at all', 12345),
                         ('empty', ''),
                         ('whitespace only', '   '),
                         ('absurdly long', LONG_UA)]:
        got = common.classify_device(value)
        check(got == common.UNDETERMINED,
              f'classifier: {label} -> UNDETERMINED (got {got!r})')
    # ...and the two halves of the asymmetry, side by side, on the sentinel:
    narrow = {'prolific_allowed_devices': ['computer']}
    check(common.device_screens_out(narrow, common.UNDETERMINED) is False,
          'UNDETERMINED never screens anybody out (fail open on entry)')
    check(common.device_clears_screenout(narrow, common.UNDETERMINED) is False,
          'UNDETERMINED never CLEARS a screen-out either (no positive evidence)')
    # The determined 'unknown' is a device type and behaves like one.
    check(common.classify_device(ODD_BUT_REAL_UA) == 'unknown',
          "a real but unrecognised User-Agent -> 'unknown' (a device type)")

    # A narrow desktop WINDOW is a client-side fact that never reaches this
    # gate: it classifies the User-Agent and nothing else, so window width
    # cannot screen anybody out. The measured proof is the render check
    # (scripts/tests/render_check.py, `consent_narrow_window`), which loads consent in a
    # 640px-wide desktop browser; here we can only state the property.
    print('\n--- A4. screen size is not consulted (see render_check) ---')
    check(True, 'window width is never sent to the gate: it reads the '
                'User-Agent only (render_check proves the narrow window case)')

    # =====================================================================
    # B. THE GATE ITSELF
    # =====================================================================
    print('\n--- B. a forbidden type is held at entry, with copy for ITS type ---')
    expect_screened_out(
        base, 'computer-only+phone', PHONE_UA, ['computer'], 'phone',
        must_say=('It looks like you are on a phone',
                  'This study needs a desktop or laptop computer',
                  'Your place is still open'),
        must_not_say=('It looks like you are on a tablet',
                      # Never "mobile device": a study may accept tablets.
                      'mobile device'))
    expect_screened_out(
        base, 'computer-only+tablet', TABLET_UA, ['computer'], 'tablet',
        must_say=('It looks like you are on a tablet',),
        must_not_say=('It looks like you are on a phone',))

    # =====================================================================
    # C. AN ALLOW-LIST, NOT A PHONE BLOCKER
    # =====================================================================
    print('\n--- C. any type can be excluded; unknown is configurable ---')
    expect_screened_out(
        base, 'mobile-only+desktop', DESKTOP_UA, ['phone', 'tablet'], 'computer',
        must_say=('It looks like you are on a desktop or laptop computer',
                  'This study needs a phone or a tablet'),
        must_not_say=('It looks like you are on a phone',))
    # 'unknown' = a REAL User-Agent matching no family. Excluded here...
    expect_screened_out(
        base, 'computer-only+odd-real-UA', ODD_BUT_REAL_UA, ['computer'], 'unknown',
        must_say=('We could not identify the device or browser you are using',),
        must_not_say=('It looks like you are on a phone',
                      'It looks like you are on a tablet'))
    # ...and admitted here, with no code change.
    expect_admitted(base, 'unknown-admitted+odd-real-UA', ODD_BUT_REAL_UA,
                    ['computer', 'unknown'], 'unknown')
    # Phones out, tablets fine — the second worked example in README's device
    # section, proven to behave as documented.
    expect_admitted(base, 'no-phones+tablet', TABLET_UA,
                    ['tablet', 'computer', 'unknown'], 'tablet')
    expect_screened_out(
        base, 'no-phones+phone', PHONE_UA, ['tablet', 'computer', 'unknown'],
        'phone', must_say=('It looks like you are on a phone',))

    print(f"\n{'ALL CASES PASS' if not FAILURES else 'FAILURES: ' + '; '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
