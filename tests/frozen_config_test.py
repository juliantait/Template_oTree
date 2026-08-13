#!/usr/bin/env python
"""A session whose config PREDATES the current code must not 500.

WHY THIS EXISTS
---------------
oTree copies the session config onto the Session row when the session is CREATED
and never refreshes it. A parameter you add to `settings.SESSION_CONFIG_DEFAULTS`
in a later deploy therefore does not exist in the config of a session that is
already running. Reading it with square brackets — `player.session.config['x']` —
then raises KeyError, which reaches the participant as an HTTP 500, mid-study,
visible only in the container log. That is not a hypothetical: it took the quiz
page down in the pilot study this template was distilled from, the day after the
parameter was added, and CLAUDE.md's "never `session.config['name']`" rule comes
from it.

No fresh-database test can catch this, because a fresh session always carries
every key. So this test creates a session and DELETES parameters from its stored
config, reproducing a mid-flight participant on a build that predates them.

WHAT IT COVERS
--------------
1. Every shipped config walked end to end with a stripped config: no 5xx, and
   the participant still reaches an ending with the right exit code.
2. The same with the QUIZ FAILED first — the page and code path that actually
   went down in the pilot.
3. Module flags stripped as well as scalars: a missing flag must read as its
   shipped default rather than crashing or silently changing the study.
4. `common.cfg` itself: falls back to the SHIPPED default for a known key, and
   raises a clearly NAMED error for a key nobody ever shipped (so a typo is a
   loud, greppable failure and not a silent None).

Run:  python tests/frozen_config_test.py      (oTree must be importable)
Exit 0 = all checks passed. Boots no server and never touches the real database.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otree_inprocess import boot, path_of, page_name_of  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# Parameters a request-path page reads. Everything here is deleted from the
# stored config, which is the state of a session created before the parameter
# existed. KEEP THIS LIST GROWING with the study: a parameter that is never
# stripped here is a parameter whose frozen-config behaviour is untested.
STRIPPED = [
    # payment / display
    'showup', 'quiz_bonus', 'num_rewarded', 'expected_duration_minutes',
    'real_world_currency_per_point', 'participation_fee',
    # structure
    'num_experimental_rounds',
    # comprehension
    'comprehension_max_failures', 'quiz_reread', 'verify_quiz',
    # integrity modules and their thresholds
    'tab_monitor', 'comprehension_dq', 'tab_monitor_max_violations',
    'tab_monitor_threshold_ms', 'tab_monitor_overlay_delay_ms',
    # measurement
    'passive_capture', 'device_capture', 'collect_demographics',
    'collect_bank_details',
    # consent-page copy switches
    'show_duration_and_fee',
    # recruitment plumbing
    'prolific_capture_participant_id', 'prolific_completion_redirects', 'allowed_devices',
    'prolific_screenout_return_url',
    'prolific_cc_code', 'prolific_noconsent_code', 'prolific_dq_code',
    # misc
    'pilot_feedback', 'static_version',
]

TERMINAL = {'Results', 'Ended'}


def payload_for(page, quiz_answers):
    return {
        'welcome': {'consent': 'True', 'is_mobile': '', 'device_info_json': '',
                    'participant_id_url': ''},
        'ConfirmProlificID': {'participant_id_external': 'frozen-cfg-test'},
        'instructing': {},
        'quiz': dict(quiz_answers),
        'AISafetyAgree': {},
        'GameStart': {'client_ms': ''},
        'payoff': {},
        'Demographics': {'age': '30', 'gender': 'Female',
                         'bank': 'NL91ABNA0417164300',
                         'bank_confirmation': 'NL91ABNA0417164300', 'bic': ''},
        'Feedback': {'feedback': ''},
    }.get(page, {})


def drive(client, code, quiz_answers, wrong_quiz=None, max_steps=120):
    """Walk a participant; `wrong_quiz` is posted for the first quiz render."""
    statuses, visited = [], []
    resp = client.get(f'/InitializeParticipant/{code}', allow_redirects=True)
    statuses.append(resp.status_code)
    failed_once = False
    for _ in range(max_steps):
        page = page_name_of(path_of(resp))
        if page is None:
            break
        visited.append(page)
        if page in TERMINAL:
            break
        if page == 'quiz' and wrong_quiz and not failed_once:
            data, failed_once = dict(wrong_quiz), True
        else:
            data = payload_for(page, quiz_answers)
        try:
            resp = client.post(path_of(resp), data=data, allow_redirects=True)
            statuses.append(resp.status_code)
        except Exception:
            # An old TestClient cannot stream a 500 body; treat any transport
            # exception as the 500 it is, so a regression prints as a clean FAIL.
            statuses.append(500)
            break
    return visited, statuses


def main():
    from intro.quiz_items import QUIZ_ITEMS
    import common

    correct = {i['field']: i['answer'] for i in QUIZ_ITEMS}
    first = QUIZ_ITEMS[0]
    wrong = dict(correct)
    wrong[first['field']] = next(c for c in first['choices']
                                 if c != first['answer'])
    client = ot.client()

    for config in ('lab', 'prolific'):
        section(f'{config}: full walk on a FROZEN (stripped) session config')
        session = ot.create_session(config, num_participants=3)
        removed = ot.strip_config_keys(session, STRIPPED)
        check(len(removed) >= 20,
              f'{len(removed)} parameters stripped from the stored config '
              f'(of {len(STRIPPED)} asked for)')
        codes = ot.participant_codes(session)

        visited, statuses = drive(client, codes[0], correct)
        check(all(s < 500 for s in statuses),
              f'no page 5xx across {len(statuses)} requests '
              f'(max status {max(statuses)})')
        check(visited and visited[-1] in TERMINAL,
              f'the participant reached an ending (ended on '
              f'{visited[-1] if visited else None}; path '
              f'{" -> ".join(visited[:6])} …)')
        v = ot.participant_vars(codes[0])
        check(v.get('exit_code') == 1,
              f'exit code 1 (completed) recorded (got {v.get("exit_code")!r})')

        section(f'{config}: the QUIZ FAILURE path on a frozen config')
        # This is the exact shape of the outage: the quiz page reads the
        # comprehension threshold, and that parameter had just been added.
        visited, statuses = drive(client, codes[1], correct, wrong_quiz=wrong)
        check(all(s < 500 for s in statuses),
              f'a wrong quiz submit did not 5xx (max status {max(statuses)})')
        check(visited.count('quiz') >= 2,
              f'the quiz re-rendered after the wrong answer '
              f'({visited.count("quiz")} quiz renders)')
        v = ot.participant_vars(codes[1])
        check((v.get('failed_attempts') or 0) >= 1,
              f'the failure was counted (failed_attempts='
              f'{v.get("failed_attempts")!r})')
        check(visited[-1] in TERMINAL,
              f'and the participant still reached an ending ({visited[-1]})')

    section('common.cfg: shipped default for a known key, NAMED error otherwise')
    check(hasattr(common, 'cfg'),
          'common.cfg exists (the safe accessor CLAUDE.md requires)')
    if hasattr(common, 'cfg'):
        import settings
        for key in ('num_rewarded', 'showup', 'quiz_bonus'):
            check(common.cfg({}, key) == settings.SESSION_CONFIG_DEFAULTS[key],
                  f'a config missing {key!r} falls back to the SHIPPED value '
                  f'{settings.SESSION_CONFIG_DEFAULTS[key]!r}')
        check(common.cfg({'showup': 9.5}, 'showup') == 9.5,
              'a config that HAS the key still wins over the default')
        # The screen-out page is the one page a stranded participant needs, and
        # its way out comes from a parameter added in a later deploy. A session
        # frozen before it existed must still render a working link.
        import settings as _s
        check(common.prolific_screenout_return_url({}) ==
              _s.SESSION_CONFIG_DEFAULTS['prolific_screenout_return_url'],
              'a session frozen before prolific_screenout_return_url existed still gets '
              'the shipped URL (the screen-out page cannot be a dead end)')
        check(common.prolific_screenout_return_url({'prolific_screenout_return_url': ''}) == '',
              'and a study that deliberately blanks it gets no link, not a broken one')
        try:
            common.cfg({}, 'a_totally_unknown_param')
            check(False, 'an unknown key raises')
        except KeyError as exc:
            check('a_totally_unknown_param' in str(exc),
                  f'an unknown key raises an error that NAMES it ({exc})')

    section('SUMMARY')
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
