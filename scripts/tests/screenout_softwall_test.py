"""HTTP scenario tests for the SOFT WALL — the entry device screen-out that can
be lifted again.

    OTREE_ADMIN_PASSWORD=admin otree prodserver 8000     # THROWAWAY database
    python scripts/tests/screenout_softwall_test.py http://localhost:8000

WHY THE WALL IS SOFT. oTree rematches a returning participant to the SAME row by
participant label, so a screen-out that is recorded once and read for ever locks
somebody who reopens the study on a computer into the screen-out page
permanently — and on Prolific their submission stays open until they return it,
while returning it means they can never retake the study. So the verdict is
written immediately (a closed tab still exports as a screen-out, not as an
abandoner) and re-decided on every later PRE-CONSENT request.

WHAT IS CHECKED HERE

  1. WRITTEN IMMEDIATELY — the verdict is in the database as the screen-out page
     renders, with no further request from the participant.
  2. CLEARED — the same participant returning on an accepted device before
     consent reaches consent, with the terminal marking undone and BOTH verdicts
     in the audit history.
  3. RE-SCREENED — cleared, then back on a phone before consent: screened again,
     and `screenout_cleared` still records that a switch happened.
  4. ORDINARY AFTERWARDS — a cleared participant consents and completes with
     exit code 1, indistinguishable from anyone else except for the history.
  5. NEVER TOUCHED AFTER CONSENT — someone who consented on a computer and then
     switches to a phone is not screened out, whatever the allow-list says.
  6. THE WAY OUT — a real <a href> to the platform with NO completion code, that
     works with JavaScript disabled (it is not a scripted button), and pressing
     it changes no server state.
  7. RE-ENTRY AFTER PRESSING IT — the row is not silently revived: it is still
     screened, still -4, and the original decision is still in the history.
  8. THE ASYMMETRY, both directions, kept side by side: an unusable User-Agent
     ALLOWS a fresh participant (recording nothing) and does NOT clear an
     existing screen-out. Missing header, garbage header, and no request object
     at all.
  9. NEVER REACHES THE OUTRO — the deletion guard (Julian, 2026-08-14). The
     outro's Ended page no longer carries any screen-out copy: the live copy is
     before/screened_out.html and the soft wall holds a screened-out
     participant in `before`. That deletion rests on an unreachability claim,
     and this repo does not keep unreachability claims untested (the
     monitor-coverage gap of 2026-08-13 is what happens when it does), so this
     scenario ENFORCES it: forced submits and a direct outro URL must both
     re-serve the held page, never an ending. If a future change routes a
     screened-out participant into the outro, this goes red instead of a
     participant meeting Ended's neutral fallback where device copy used to be.

Exits non-zero on any failed check or any 5xx.
"""
import json
import os
import re
import sys

import requests
import requests.models

sys.path.insert(0, __file__.rsplit('/', 1)[0])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)
from http_flow_test import FormParser, build_payload, END_MARKERS
from device_gate_test import (PHONE_UA, TABLET_UA, DESKTOP_UA, NO_UA, BLANK_UA,
                              LONG_UA, CONSENT_MARKER, SCREENOUT_MARKER,
                              visible_text, page_name, participant_code,
                              create, session_vars, CODES, COMPLETION_URL_RE)
import common

# See device_gate_test: `requests` will not send a malformed header, and the
# participant we must not turn away is precisely the one whose header is.
requests.models.check_header_validity = lambda header: None

STATE_VARS = ['exit_code', 'screened_out', 'screenout_cleared',
              'consent_submitted', 'participant_extra']
ENTRY_OVERRIDES = {'consent': 'True', 'is_mobile': 'False',
                   'participant_id_external': 'SOFTWALL_TEST'}

FAILURES = []


def check(cond, label):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


def state(base, session_code, p_code):
    """The participant's screen-out state, read back over the REST API."""
    p = session_vars(base, session_code, p_code, STATE_VARS)
    extra = p.get('participant_extra') or {}
    return dict(
        exit_code=p.get('exit_code'),
        screened_out=p.get('screened_out'),
        screenout_cleared=p.get('screenout_cleared'),
        consent_submitted=p.get('consent_submitted'),
        cause=extra.get('screenout_cause'),
        device=extra.get('entry_device_type'),
        history=extra.get('screenout_history') or [],
    )


def actions(st):
    return [h.get('action') for h in st['history']]


def enter(base, url, ua, label=''):
    """One participant session (a browser) entering the study."""
    s = requests.Session()
    s.headers['User-Agent'] = ua
    r = s.get(url, allow_redirects=True)
    if r.status_code >= 500:
        check(False, f'{label}: HTTP {r.status_code} at entry')
    return s, r


def walk_on(base, s, r, label, budget=60):
    """Keep submitting forms until an ending, the screen-out page, or a dead end."""
    answers = {}
    for _ in range(budget):
        if r.status_code >= 500:
            check(False, f'{label}: HTTP {r.status_code} at {page_name(r.url)}')
            return r
        if SCREENOUT_MARKER in r.text or any(m in r.text for m in END_MARKERS):
            return r
        fp = FormParser(); fp.feed(r.text)
        if not fp.found_form:
            check(False, f'{label}: dead end at {page_name(r.url)}')
            return r
        if fp.solutions_json.strip():
            for item in json.loads(fp.solutions_json):
                answers[item['name']] = item['value']
        r = s.post(r.url, data=build_payload(fp.inputs, ENTRY_OVERRIDES, answers,
                                             warn=False), allow_redirects=True)
    check(False, f'{label}: exceeded step budget')
    return r


def entry_url(created, pid):
    """The study URL as Prolific would call it, carrying the participant id."""
    return f"{created['session_wide_url']}?participant_label={pid}"


# =============================================================================
def scenario_soft_wall(base):
    print('\n--- 1-4. screened -> cleared -> re-screened -> cleared -> completes ---')
    created = create(base, ['computer'])
    sc = created['code']
    url = entry_url(created, 'SOFTWALL1')

    # 1. SCREENED, and recorded THERE AND THEN. Nothing else is requested after
    #    this line — this is the "reads the page and closes the tab" case, and
    #    it must already export as a screen-out rather than as an abandoner.
    phone, r = enter(base, url, PHONE_UA, 'phone entry')
    p_code = participant_code(r.url)
    check(SCREENOUT_MARKER in r.text, 'phone entry: the screen-out page renders')
    check(CONSENT_MARKER not in r.text, 'phone entry: consent is NOT rendered')
    st = state(base, sc, p_code)
    check(st['screened_out'] is True, 'closed tab: screened_out True already')
    check(st['exit_code'] == -4, 'closed tab: exit code -4 already (not 0/abandoned)')
    check(st['cause'] == 'phone', "closed tab: cause is the detected type 'phone'")
    check(actions(st) == ['screened'], f"history: {actions(st)}")

    # 2. CLEARED by the same person returning on a computer, BEFORE consent.
    desktop, r2 = enter(base, url, DESKTOP_UA, 'desktop return')
    check(participant_code(r2.url) == p_code,
          'desktop return: rematched to the SAME participant row')
    check(CONSENT_MARKER in r2.text, 'desktop return: reaches the consent page')
    check(SCREENOUT_MARKER not in r2.text,
          'desktop return: the screen-out page is gone')
    st = state(base, sc, p_code)
    check(st['screened_out'] is False, 'cleared: screened_out back to False')
    check(st['exit_code'] == 0,
          f"cleared: exit code reverted to 0/abandoned (got {st['exit_code']})")
    check(not st['cause'], 'cleared: the screen-out cause is dropped')
    check(st['screenout_cleared'] is True,
          'cleared: screenout_cleared records the switch in its OWN column')
    check(actions(st) == ['screened', 'cleared'],
          f"history keeps BOTH verdicts, oldest first: {actions(st)}")
    check(st['history'][0]['device'] == 'phone' and st['history'][0]['screened_out'],
          'history: the original screen-out entry survives the clear')

    # 3. RE-SCREENED on returning to the phone, still before consent.
    _, r3 = enter(base, url, PHONE_UA, 'phone again')
    check(SCREENOUT_MARKER in r3.text, 'phone again: screened out a second time')
    st = state(base, sc, p_code)
    check(st['exit_code'] == -4 and st['screened_out'] is True,
          're-screened: terminal marking back')
    check(st['screenout_cleared'] is True,
          're-screened: screenout_cleared STAYS True — the switch still happened')
    check(actions(st) == ['screened', 'cleared', 'rescreened'],
          f"history: {actions(st)}")

    # 4. Cleared again, then consents and completes like anybody else.
    desktop, r4 = enter(base, url, DESKTOP_UA, 'desktop again')
    check(CONSENT_MARKER in r4.text, 'desktop again: cleared and back at consent')
    r5 = walk_on(base, desktop, r4, 'cleared participant completes')
    st = state(base, sc, p_code)
    check(st['exit_code'] == 1,
          f"completed: exit code 1, an ORDINARY participant (got {st['exit_code']})")
    check(st['screened_out'] is False, 'completed: not screened out')
    check(st['screenout_cleared'] is True,
          'completed: the audit column still shows a device switch happened')
    check(actions(st) == ['screened', 'cleared', 'rescreened', 'cleared'],
          f"history: the whole story is still there: {actions(st)}")


def scenario_after_consent(base):
    print('\n--- 5. after consent the check does not apply, ever ---')
    created = create(base, ['computer'])
    sc = created['code']
    url = entry_url(created, 'AFTERCONSENT1')
    desktop, r = enter(base, url, DESKTOP_UA, 'desktop entry')
    p_code = participant_code(r.url)
    check(CONSENT_MARKER in r.text, 'desktop entry: at consent')
    # Submit consent on the computer...
    fp = FormParser(); fp.feed(r.text)
    r = desktop.post(r.url, data=build_payload(fp.inputs, ENTRY_OVERRIDES, {},
                                               warn=False), allow_redirects=True)
    st = state(base, sc, p_code)
    check(st['consent_submitted'] is True,
          'the consent SUBMISSION is recorded as a durable participant flag')
    history_before = actions(st)

    # ...then carry on from a phone for the whole rest of the study.
    phone = requests.Session()
    phone.headers['User-Agent'] = PHONE_UA
    phone.cookies.update(desktop.cookies)
    r = phone.get(r.url, allow_redirects=True)
    check(SCREENOUT_MARKER not in r.text,
          'phone AFTER consent: not screened out on the next page')
    r = walk_on(base, phone, r, 'phone after consent')
    st = state(base, sc, p_code)
    check(st['screened_out'] is False, 'phone after consent: never screened out')
    check(st['exit_code'] == 1,
          f"phone after consent: completes normally (exit {st['exit_code']})")
    check(actions(st) == history_before,
          f'phone after consent: the gate wrote NOTHING at all ({actions(st)})')


def scenario_way_out(base):
    print('\n--- 6-7. the way out, with no JavaScript, and re-entry after it ---')
    created = create(base, ['computer'])
    sc = created['code']
    url = entry_url(created, 'WAYOUT1')
    phone, r = enter(base, url, PHONE_UA, 'phone entry')
    p_code = participant_code(r.url)
    html = r.text

    # A REAL LINK. Structure assertions belong on raw HTML.
    links = re.findall(r'<a\b[^>]*href="([^"]*)"[^>]*>', html)
    check(any(u.startswith('https://app.prolific.com') for u in links),
          f'the way out is an <a href> to the platform (found {links})')
    check('onclick' not in html,
          'no onclick anywhere: the way out cannot depend on JavaScript')
    # The bug this page was rebuilt to avoid: a scripted button with no href
    # left a participant without JS with NO way off the page at all.
    check('<button' not in html.lower(),
          'the way out is not a <button> that needs a script to do anything')
    check('class="exit-button"' in html,
          'it is NOT .next-button: global.js Enter-clicks the first one of '
          'those, and an irreversible exit must not be one keystroke away')
    # THE WAY OUT CARRIES THE SCREEN-OUT POPULATION'S OWN COMPLETION CODE.
    #
    # REWRITTEN 2026-08-15 — this assertion was RED ON MAIN. It read "no
    # completion code: their Prolific submission stays OPEN", which was the
    # rule until the screen-out was given its own code that day (DECISIONS.md;
    # the reasoning is on common.prolific_screenout_return_url). An open
    # submission was judged to be limbo rather than kindness: a REQUEST_RETURN
    # code prompts the return that frees the place.
    #
    # PRESENCE AND ABSENCE, as in device_gate_test: a page carrying SOME code
    # would satisfy a bare presence check while leaking another population's,
    # which is the thing per-population codes exist to prevent.
    #
    # IF THE CODELESS EXIT IS EVER RESTORED (the copy/ethics question put to
    # Julian on 2026-08-15 — the soft wall invites a return on an accepted
    # device, and a returned submission cannot be retaken), this assertion is
    # one of the two places that must flip back with it; the other is
    # device_gate_test.expect_screened_out.
    urls = COMPLETION_URL_RE.findall(html)
    check(set(urls) == {CODES['prolific_device_code']},
          f"the way out carries the DEVICE code and nothing else (got {sorted(set(urls))})")
    for key, code in CODES.items():
        if key != 'prolific_device_code':
            check(code not in html, f'no {key} anywhere on the page ({code})')
    flat = visible_text(html)
    check('you will be asked to return your submission' in flat,
          'the page says what pressing it does')
    # THE FINALITY SENTENCE NAMES THE ROUTE IT CLOSES (Julian, 2026-08-15).
    # The old copy — "you will not be able to take part later" — was true but
    # read as "not later today", on a page whose primary ask is to switch
    # device and come back. Asserting the accepted-device clause specifically
    # is what stops the sentence being softened back to something a
    # participant could read as compatible with the invitation above it.
    check('Once you return it you cannot take part again, even on an accepted device'
          in flat,
          'the page says the exit is FINAL, and that it closes the '
          'switch-device route it invites above')
    check('Do not press the button below' in flat,
          'the SWITCH-DEVICE path tells them not to press it')

    # PRESSING IT changes no server state: it is a plain navigation to another
    # site. (The URL is not fetched here — it is Prolific's.)
    before_state = state(base, sc, p_code)
    check(before_state['exit_code'] == -4, 'still -4 before the press')

    # 7. RE-ENTRY AFTER PRESSING IT. The row must not be silently revived:
    #    coming back on the same phone is still a screen-out, still -4, and the
    #    original decision is still the first entry in the history.
    _, r2 = enter(base, url, PHONE_UA, 'return on the phone after pressing')
    check(SCREENOUT_MARKER in r2.text, 'return on phone: still screened out')
    st = state(base, sc, p_code)
    check(st['exit_code'] == -4 and st['screened_out'] is True,
          'return on phone: still terminal, nothing revived')
    check(st['history'][0]['action'] == 'screened',
          'return on phone: the original decision is still the first history entry')
    check(actions(st) == ['screened'],
          f'return on phone: a reload adds no history noise ({actions(st)})')
    # Returning on a COMPUTER does clear them — that is the whole point of the
    # soft wall, and it is never silent: screenout_cleared plus the history say
    # so. Documented in README ("The device check") as an accepted consequence.
    _, r3 = enter(base, url, DESKTOP_UA, 'return on a computer after pressing')
    st = state(base, sc, p_code)
    check(st['screened_out'] is False and st['screenout_cleared'] is True,
          'return on a computer: cleared, and VISIBLY so (screenout_cleared)')
    check(actions(st) == ['screened', 'cleared'],
          f'return on a computer: the screen-out is still in the record '
          f'({actions(st)})')


def scenario_asymmetry(base):
    """The rule that is easy to implement backwards, tested in both directions.

    Every pair below is: the SAME unusable User-Agent on a FRESH participant
    (must proceed, recording nothing) and on an ALREADY-SCREENED participant
    (must stay screened). They are kept next to each other on purpose.
    """
    print('\n--- 8. absence of evidence allows on ENTRY, but never CLEARS ---')
    for label, ua in [('missing header', NO_UA),
                      ('whitespace-only header', BLANK_UA),
                      ('absurdly long header', LONG_UA)]:
        created = create(base, ['computer'])
        sc = created['code']

        # (a) FRESH participant: allowed through, and nothing recorded.
        _, r = enter(base, entry_url(created, f'ASYM_A_{label}'), ua, label)
        p_code = participant_code(r.url)
        st = state(base, sc, p_code)
        check(CONSENT_MARKER in r.text,
              f'{label} on a FRESH participant: proceeds to consent')
        check(st['screened_out'] is False and st['exit_code'] == 0,
              f'{label} on a FRESH participant: no verdict recorded')
        check(st['device'] is None and st['history'] == [],
              f'{label} on a FRESH participant: nothing written at all')

        # (b) ALREADY-SCREENED participant: the same header must NOT lift it.
        phone, r = enter(base, entry_url(created, f'ASYM_B_{label}'), PHONE_UA,
                         label)
        p2 = participant_code(r.url)
        check(SCREENOUT_MARKER in r.text, f'{label}: (setup) screened out first')
        _, r2 = enter(base, entry_url(created, f'ASYM_B_{label}'), ua, label)
        check(participant_code(r2.url) == p2, f'{label}: same participant row')
        st2 = state(base, sc, p2)
        check(SCREENOUT_MARKER in r2.text,
              f'{label} on an ALREADY-SCREENED participant: STILL screened out')
        check(st2['screened_out'] is True and st2['exit_code'] == -4,
              f'{label} on an ALREADY-SCREENED participant: verdict unchanged')
        check(st2['screenout_cleared'] is False,
              f'{label}: it did not count as a device switch either')
        check(actions(st2) == ['screened'],
              f'{label}: no history entry for a non-decision ({actions(st2)})')


def scenario_no_request_object(base):
    """The third pair: NO REQUEST OBJECT AT ALL.

    oTree instantiates pages WITHOUT a request while it walks the skip chain
    (`views/abstract.py`: `instantiate_without_request()` then
    `page._is_displayed()`), so any code that reads a header there sees nothing.
    This template therefore decides ONCE, in `welcome.get()` — the one place a
    real request exists — and every other page reads the RECORD.

    HTTP cannot deliver "no request object" as a request, so this is asserted
    against the gate function itself, with the participant state read back over
    the REST API afterwards. Kept beside the other two pairs because it is the
    same rule.
    """
    print('\n--- 8c. no request object at all: same asymmetry ---')
    # What welcome.get() passes when there is no request to read from: its
    # header lookup raises, the gate is called with nothing, or is not called at
    # all. All three are the same answer — UNDETERMINED.
    for value in (None, '', 12345):
        got = common.classify_device(value)
        check(got == common.UNDETERMINED,
              f'no request -> classify_device({value!r}) is UNDETERMINED')
    narrow = {'allowed_devices': ['computer']}
    check(common.device_screens_out(narrow, common.UNDETERMINED) is False,
          'no request on a FRESH participant: cannot screen anybody out')
    check(common.device_clears_screenout(narrow, common.UNDETERMINED) is False,
          'no request on an ALREADY-SCREENED participant: cannot clear them')
    # And the shape of the predicate, not just its answer: `clears` must be
    # EXPLICIT membership of the allow-list. If somebody ever rewrites it as
    # "not screened out", this check is what goes red.
    for detected in ('phone', 'tablet', 'computer', 'unknown', common.UNDETERMINED):
        expected = detected in common.allowed_devices(narrow)
        check(common.device_clears_screenout(narrow, detected) is expected,
              f'clears({detected!r}) is membership of the allow-list, not a negation')


def scenario_never_reaches_outro(base):
    print('\n--- 9. a screened-out participant NEVER reaches the outro app ---')
    # THE DELETION GUARD — see item 9 in the module docstring. Ended.html's
    # screen-out branch was deleted as unreachable-by-design; this is the test
    # that makes "unreachable" a fact rather than a claim.
    created = create(base, ['computer'])
    sc = created['code']
    url = entry_url(created, 'NEVEROUTRO1')
    phone, r = enter(base, url, PHONE_UA, 'phone entry')
    p_code = participant_code(r.url)
    check(SCREENOUT_MARKER in r.text, 'held: the screen-out page renders')
    # Ended.html's title — the string a screened-out participant must never
    # read (the neutral fallback they WOULD hit if routing ever broke).
    ENDED_TITLE = 'Your participation has ended'

    # A determined participant hammering submit: the wall answers every POST
    # by re-serving the held page (WelcomePage.post -> self.get for a
    # screened-out participant), never by advancing them.
    advanced = False
    for i in range(6):
        fp = FormParser(); fp.feed(r.text)
        payload = (build_payload(fp.inputs, {}, {}, warn=False)
                   if fp.found_form else {})
        r = phone.post(r.url, data=payload, allow_redirects=True)
        if r.status_code >= 500 or SCREENOUT_MARKER not in r.text \
                or ENDED_TITLE in r.text:
            check(False, f'forced submit {i + 1}: expected the held screen-out '
                         f'page, got HTTP {r.status_code} at {page_name(r.url)}')
            advanced = True
            break
    if not advanced:
        check(True, '6 forced submits: every response is the held screen-out '
                    'page, never an ending')
    check(page_name(r.url) == 'before.welcome',
          f'still parked on the entry page index (at {page_name(r.url)})')

    # Typing the outro's own URL bounces straight back to the held page — the
    # outro is unreachable even by address bar.
    r2 = phone.get(f'{base}/p/{p_code}/outro/Ended/1', allow_redirects=True)
    check(r2.status_code < 500 and SCREENOUT_MARKER in r2.text
          and ENDED_TITLE not in r2.text,
          f'a direct outro URL re-serves the held screen-out page '
          f'(HTTP {r2.status_code} at {page_name(r2.url)})')

    # And the durable record is still the ENTRY screen-out, not an ending.
    st = state(base, sc, p_code)
    check(st['exit_code'] == -4 and st['screened_out'] is True,
          f"the record is still exit -4 / screened_out "
          f"(got {st['exit_code']}, {st['screened_out']})")
    check(st['consent_submitted'] is not True,
          'consent was never submitted along the way')


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
    scenario_soft_wall(base)
    scenario_after_consent(base)
    scenario_way_out(base)
    scenario_asymmetry(base)
    scenario_no_request_object(base)
    scenario_never_reaches_outro(base)
    print(f"\n{'ALL CASES PASS' if not FAILURES else 'FAILURES: ' + '; '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
