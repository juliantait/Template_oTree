#!/usr/bin/env python
"""WHICH SENTENCE A PARTICIPANT READS — flags decide MECHANICS, `recruitment`
decides COPY (docs/conventions.md).

    OTREE_ADMIN_PASSWORD=admin otree prodserver 8000     # THROWAWAY database
    python scripts/tests/copy_routing_test.py http://localhost:8000

THE FAILURE THIS FILE EXISTS FOR, and it produced no error and no failing test
of any other kind. "Is this participant on Prolific?" used to be answered by
whichever module flag was nearest: the consent page inferred it from
`prolific_capture_participant_id`, while the screen-out page next door inferred it from
`prolific_completion_redirects`. A `recruitment='prolific'` session with both of those
off — a friend test on a Prolific-shaped study, a perfectly legal config —
therefore:

  * told the participant on the consent page to contact the researchers
    *through Prolific*, and then
  * served a screen-out page whose only remaining content told them to switch
    device, with NO answer at all for somebody who cannot. A DEAD END, on the
    one page whose entire job is to give a stranded participant a way out.

WHAT IS ASSERTED IS THE IMPOSSIBILITY, NOT THE ROUTING (Julian, 2026-08-13). A
Prolific study MUST offer an exit — its participants have no experimenter to ask
— so the exit is not a consequence of the redirect flag but an obligation of the
study type, and the broken combination is now UNCONSTRUCTABLE rather than merely
handled:

  A. THE GUARD. `settings._prelaunch_problems` refuses a prolific config whose
     `prolific_screenout_return_url` is blank or unreplaced, so the combination cannot
     reach a participant. This is the mechanism; everything else is the belt.
  B. Every shape of study renders an exit on the screen-out page — a prolific
     one renders the real LINK whatever `prolific_completion_redirects` says, and the
     chain ends in a neutral fallback. A page that must say something to
     everybody needs a branch for everybody.
  C. The consent page's contact route follows the STUDY TYPE, and is unmoved by
     the module flags that used to stand in for it.

("Flags decide mechanics, `recruitment` decides copy" — docs/conventions.md — is the
reasoning behind all three. It is no longer the mechanism.)

Copy assertions are made against VISIBLE TEXT (script bodies and comments
stripped): the entry page's capture script legitimately contains the literal
`PROLIFIC_PID`, so "the word Prolific is on the page" is true of the source and
false of what anybody reads.

Exits non-zero on any failed check or any 5xx.
"""
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)
from http_flow_test import FormParser, build_payload

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'

PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 '
            'Mobile/15E148 Safari/604.1')
LAPTOP_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

# A study that HAS configured its way out. `prolific_screenout_return_url` ships as a
# REPLACE_* placeholder on purpose, and the pre-launch guard refuses to launch
# while it is unreplaced (see device_gate_test.py for the same note).
CONFIGURED_DEVICE_CODE = 'DEVICE-T3STC0'

SWITCH_HEADING = 'If you cannot switch devices'

_failures = []


def check(cond, msg):
    print(('  [PASS] ' if cond else '  [FAIL] ') + msg)
    if not cond:
        _failures.append(msg)


def section(title):
    print('\n=== ' + title + ' ===')


def visible_text(html):
    """What a participant actually reads: comments, <script>/<style> bodies and
    tags stripped, whitespace collapsed."""
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    html = re.sub(r'<script\b.*?</script>', ' ', html, flags=re.S | re.I)
    html = re.sub(r'<style\b.*?</style>', ' ', html, flags=re.S | re.I)
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def create(config, **modified):
    """A session of a NAMED config, with per-scenario overrides."""
    fields = {'prolific_device_code': CONFIGURED_DEVICE_CODE}
    fields.update(modified)
    r = requests.post(
        BASE + '/api/sessions',
        json={'session_config_name': config, 'num_participants': 2,
              'modified_session_config_fields': fields})
    r.raise_for_status()
    return r.json()


def entry(config, user_agent, **modified):
    """Open a session as a participant and return (response, session).

    A lab session's first page is the `startpage` hold screen, and the device
    gate fires on `welcome.get()` — so a lab participant is NOT screened by the
    bare entry GET; the startpage has to be submitted first. Doing that here
    (rather than in each caller) is what lets the same scenario table cover both
    study types.
    """
    created = create(config, **modified)
    s = requests.Session()
    s.headers['User-Agent'] = user_agent
    r = s.get(created['session_wide_url'], allow_redirects=True)
    if r.status_code < 500 and '/startpage/' in r.url:
        fp = FormParser()
        fp.feed(r.text)
        r = s.post(r.url, data=build_payload(fp.inputs, {}, {}, warn=False),
                   allow_redirects=True)
    return r, created


# =============================================================================
section('A. THE MECHANISM: a Prolific study with no exit CANNOT BE LAUNCHED')
# =============================================================================
# The static guard, driven directly. This is the check that makes the rest belt
# rather than braces: a config that would strand a screened-out participant is
# refused before a server ever serves it.
import settings                                    # noqa: E402  (after argv)

REAL_CODE = CONFIGURED_DEVICE_CODE
PLACEHOLDER = settings.SESSION_CONFIG_DEFAULTS['prolific_device_code']


def guard_problems(**config):
    """`settings._prelaunch_problems()` run against ONE synthetic config.

    The function reads the module-level SESSION_CONFIGS, so the list is swapped
    for the duration and restored — never left mutated for a later check.
    """
    entry = dict(name='guard_probe', app_sequence=['before'],
                 num_demo_participants=1)
    entry.update(config)
    original = settings.SESSION_CONFIGS
    try:
        settings.SESSION_CONFIGS = [entry]
        return [label for label, _cur, _must in settings._prelaunch_problems()]
    finally:
        settings.SESSION_CONFIGS = original


def mentions_device_code(problems):
    return any('prolific_device_code' in p for p in problems)


# THE SCREENED-OUT EXIT IS NOW A CODE, not a URL setting (2026-08-15; see
# DECISIONS.md). The guarantee under test is unchanged: a Prolific study that
# could screen somebody out must have a working way out for them.
check(mentions_device_code(guard_problems(
          recruitment='prolific', prolific_device_code=PLACEHOLDER)),
      'prolific + the unreplaced DEVICE placeholder is REFUSED by the guard')
check(mentions_device_code(guard_problems(
          recruitment='prolific', prolific_device_code=PLACEHOLDER,
          prolific_completion_redirects=False)),
      'and refused with prolific_completion_redirects OFF too — the exit is '
      'owed by the STUDY TYPE, not by the redirect flag')
check(not mentions_device_code(guard_problems(
          recruitment='prolific', prolific_device_code=REAL_CODE)),
      'prolific + a real device code passes')
check(not mentions_device_code(guard_problems(
          recruitment='lab', prolific_device_code=PLACEHOLDER)),
      'lab + placeholder passes: a lab participant raises a hand, and there is '
      'no platform to return to')

# =============================================================================
section('B. The screen-out page ALWAYS answers "what if I cannot switch?"')
# =============================================================================
# One row per shape of study. The heading must be present in every one of them:
# that is the rule, and the row that used to break it is the second.
#
# `expect` is a phrase from the sentence that row's participant should read; it
# is what stops the check from passing on an empty section.
SCREENOUT_ROWS = [
    dict(label='prolific, redirects ON',
         config='prolific', modified={},
         expect='takes you back to Prolific',
         link=True),
    dict(label='prolific, redirects OFF (WAS THE DEAD END)',
         config='prolific', modified={'prolific_completion_redirects': False},
         expect='takes you back to Prolific',
         # THE LINK IS STILL THERE. It carries no completion code, so it never
         # had anything to do with `prolific_completion_redirects`; a launchable prolific
         # config always has the URL (section A), so it always has the exit.
         link=True),
    dict(label='lab                     (an experimenter is in the room)',
         config='lab', modified={},
         expect='raise your hand',
         link=False),
    dict(label='neither lab nor prolific (the neutral fallback)',
         config='prolific',
         modified={'prolific_completion_redirects': False, 'recruitment': 'other'},
         expect='simply close it',
         link=False),
]

for row in SCREENOUT_ROWS:
    modified = dict(row['modified'], allowed_devices=['computer'])
    r, created = entry(row['config'], PHONE_UA, **modified)
    label = row['label']
    if r.status_code >= 500:
        check(False, f"{label}: HTTP {r.status_code} on the screen-out page")
        continue
    text = visible_text(r.text)
    # It really is the screen-out page, held on the entry index (not consent).
    check('/welcome/' in r.url and 'has ended' not in text,
          f"{label}: held on the entry page (url {r.url.rsplit('/', 3)[-3:][0]})")
    check(SWITCH_HEADING in text,
          f'{label}: the page answers "{SWITCH_HEADING}"')
    check(row['expect'] in text,
          f'{label}: ...and says what to do ("{row["expect"]}")')
    # MECHANICS, separately: the exit link exists exactly when a completion
    # redirect does, and is never a link to nowhere.
    has_link = 'exit-button' in r.text
    check(has_link == row['link'],
          f'{label}: way-out LINK present={row["link"]} (mechanics, not copy)')
    if has_link:
        check(CONFIGURED_DEVICE_CODE in r.text,
              f'{label}: ...and it points at the configured return URL')

# =============================================================================
section('C. The consent page follows the STUDY TYPE, not a module flag')
# =============================================================================
# Each row turns OFF the flag that used to be read as "this study is on
# Prolific", so a check that still passes is evidence the copy follows
# `recruitment` alone.
r, _ = entry('prolific', LAPTOP_UA, prolific_capture_participant_id=False)
text = visible_text(r.text)
check(r.status_code == 200, f'prolific consent renders (HTTP {r.status_code})')
check('contact the researchers through Prolific' in text,
      'prolific + prolific_capture_participant_id OFF: still names Prolific as the '
      'contact route (it is where the participant IS, not a flag)')
check('raise your hand' not in text,
      'prolific: never offers a hand to raise')

r, _ = entry('lab', LAPTOP_UA, prolific_capture_participant_id=True)
text = visible_text(r.text)
check(r.status_code == 200, f'lab consent renders (HTTP {r.status_code})')
check('raise your hand to speak to the experimenter' in text,
      'lab + prolific_capture_participant_id ON: still sends them to the experimenter')
check('Prolific' not in text,
      'lab: the word Prolific appears nowhere a lab participant can read it')

# =============================================================================
section('D. The original dead end, walked end to end')
# =============================================================================
# The exact combination that produced it: a Prolific study with neither the id
# capture nor the completion redirects. Both halves, one session config.
DEAD_END = dict(prolific_capture_participant_id=False, prolific_completion_redirects=False)

r, _ = entry('prolific', LAPTOP_UA, **DEAD_END)
consent = visible_text(r.text)
check('contact the researchers through Prolific' in consent,
      'friend-test config: consent names Prolific as the contact route')

r, _ = entry('prolific', PHONE_UA, allowed_devices=['computer'], **DEAD_END)
screenout = visible_text(r.text)
check(SWITCH_HEADING in screenout,
      'friend-test config: ...and the screen-out page is NOT a dead end')
check('exit-button' in r.text and CONFIGURED_DEVICE_CODE in r.text,
      '...it offers the real, codeless way out — owed by the study type, not '
      'by the redirect flag')

print('\n=== SUMMARY ===')
if _failures:
    print(f'  {len(_failures)} FAILED:')
    for f in _failures:
        print('   - ' + f)
    sys.exit(1)
print('  ALL CHECKS PASSED')
