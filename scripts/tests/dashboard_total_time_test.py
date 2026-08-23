#!/usr/bin/env python3
"""The START and STOP of the TOTAL-time timer, unit-tested (Julian, 2026-08-23).

Pill 2 of the per-participant timer is `experimenter_dashboard._total_seconds`.
The brief asked that the moment it STARTS and the moment it STOPS — for someone
active, finished, screened out, comprehension-disqualified or tab-monitor
disqualified — be an explicit, tested choice rather than an accident. This is
that test, on the pure function, from crafted `stage_timestamps`:

  START  = the EARLIEST stage stamp (min) — the first page the participant
           advanced, i.e. when they began. Same anchor the overview EXPERIMENT
           figure uses, and always <= the intro start, so total >= intro always.
  STOP   active   -> now, and LIVE (keeps counting);
         finished -> the `finished` stamp (so it equals the experiment figure),
                     NOT the last stamp — a later prolific_return_clicked must not
                     be billed to the study;
         terminal -> the LAST stamp (max), the closest evidence of when an
                     ejected participant left (no ejection stamp exists);
         no usable stamps / incoherent -> no pill (None), never a raise.

Pure and offline: it drives the two time functions with dicts, so a wrong choice
(start at max, freeze at now, freeze a terminal at the finished stamp it does not
have) fails HERE, deterministically, with no browser and no database.

Run: /home/dev/.venv-otree/bin/python scripts/tests/dashboard_total_time_test.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _APP_ROOT)

import experimenter_dashboard as ed      # noqa: E402
import common                            # noqa: E402  (frozen STAGE_* names)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# Frozen stage names, referenced through common so a rename of the value breaks
# here too (the writer/reader-single-spelling rule).
CONSENT = common.STAGE_CONSENT
CONFIRM = common.STAGE_CONFIRM_ID
LEFT = common.LEFT_BEFORE_APP_STAGE
INSTR = common.STAGE_INSTRUCTIONS_DONE
QUIZ = common.STAGE_QUIZ_DONE
TASK = common.STAGE_TASK_DONE
FIN = common.STAGE_FINISHED
RETURN = common.STAGE_PROLIFIC_RETURN_CLICKED


def main():
    section('START = the earliest stamp; ACTIVE rows are LIVE')
    r = ed._total_seconds({CONSENT: 100, CONFIRM: 110, LEFT: 150},
                          terminal=None, finished=False, now=300)
    check(r == {'seconds': 200, 'live': True},
          f'active: from the FIRST stamp (100) to now (300), live ({r})')

    section('FINISHED freezes at the finished stamp, not the last stamp')
    r = ed._total_seconds({CONSENT: 100, LEFT: 150, QUIZ: 200, TASK: 400,
                           FIN: 500}, terminal=None, finished=True, now=9999)
    check(r == {'seconds': 400, 'live': False},
          f'finished: finished stamp (500) - first stamp (100) = 400, frozen '
          f'({r})')
    # A later "back to Prolific" click must NOT extend the total.
    r = ed._total_seconds({CONSENT: 100, LEFT: 150, FIN: 500, RETURN: 560},
                          terminal=None, finished=True, now=9999)
    check(r == {'seconds': 400, 'live': False},
          f'the receipt click after finishing is NOT billed to the study '
          f'(still 400, not 460) ({r})')

    section('TERMINAL freezes at the LAST stamp (no finished stamp exists)')
    # Comprehension DQ: quiz_done is the disqualifying submit, the last stamp.
    r = ed._total_seconds({CONSENT: 100, LEFT: 150, INSTR: 170, QUIZ: 220},
                          terminal='comprehension', finished=False, now=9999)
    check(r == {'seconds': 120, 'live': False},
          f'comprehension DQ: last stamp (220) - first (100) = 120, frozen '
          f'({r})')
    # Screen-out at entry: only entry stamps, a small frozen total.
    r = ed._total_seconds({CONSENT: 100, common.STAGE_SCREENED_OUT: 130},
                          terminal='screened_out', finished=False, now=9999)
    check(r == {'seconds': 30, 'live': False},
          f'screen-out: last entry stamp (130) - first (100) = 30, frozen ({r})')
    # `now` is NEVER consulted for a frozen row — a huge now must not change it.
    r_big = ed._total_seconds({CONSENT: 100, QUIZ: 220},
                              terminal='tab_monitor', finished=False, now=10 ** 9)
    check(r_big == {'seconds': 120, 'live': False},
          f'a terminal row ignores the wall clock — frozen whatever now is '
          f'({r_big})')

    section('DEFENSIVE: no pill, never a raise')
    check(ed._total_seconds({}, None, False, 300) == {'seconds': None,
                                                      'live': False},
          'no stamps at all -> no pill')
    r = ed._total_seconds({CONSENT: 'x', LEFT: None, QUIZ: 220},
                          terminal=None, finished=False, now=300)
    check(r == {'seconds': 80, 'live': True},
          f'non-numeric stamps are ignored, not fatal (first numeric 220? no — '
          f'only 220 is numeric, 300-220=80) ({r})')

    section('INVARIANT: total is never shorter than intro, on the same stamps')
    # A participant mid-intro: intro starts at LEFT (150), total at the first
    # stamp (100), so total includes the entry block and exceeds intro.
    stamps = {CONSENT: 100, CONFIRM: 120, LEFT: 150}
    intro = ed._intro_seconds(stamps, 'instructions', None, False, 300)
    total = ed._total_seconds(stamps, None, False, 300)
    check(intro['seconds'] == 150 and total['seconds'] == 200,
          f'mid-intro: intro from LEFT (150), total from the first stamp (200) '
          f'(intro={intro}, total={total})')
    check(total['seconds'] >= intro['seconds'],
          f'total ({total["seconds"]}) >= intro ({intro["seconds"]})')
    # And a finisher: total (whole run) exceeds intro (its first slice).
    stamps = {CONSENT: 100, LEFT: 150, QUIZ: 260, TASK: 500, FIN: 640}
    intro = ed._intro_seconds(stamps, 'done', None, True, 9999)
    total = ed._total_seconds(stamps, None, True, 9999)
    check(total['seconds'] >= intro['seconds'] and total['seconds'] == 540
          and intro['seconds'] == 110,
          f'finisher: intro 110 (LEFT 150 -> QUIZ 260) <= total 540 '
          f'(first 100 -> finished 640) (intro={intro}, total={total})')

    print()
    if _failures:
        print(f'FAILED: {len(_failures)} check(s)')
        for f in _failures:
            print(f'  - {f}')
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
