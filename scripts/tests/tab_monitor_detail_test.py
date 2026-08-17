#!/usr/bin/env python3
"""Per-event tab-monitor detail, and the at-least evidence of dropped events.

WHAT THIS PROVES, and why each part is here rather than assumed:

  1. Two focus losses on DIFFERENT pages are recorded with the pages the SERVER
     believes the participant was on — not the pathname the client reported,
     which is the half a participant can edit.
  2. `tab_monitor_where` names those pages instead of the region alone, which is
     the entire point of recording them: 'questionnaire' spans four outro pages
     and cannot say which answers to distrust.
  3. The retrospective drop detector fires when the client's running total runs
     ahead of ours, and records an AT-LEAST rather than a count.
  4. It does NOT fire when the client's total is BEHIND ours — a cleared
     sessionStorage or a reused browser is not a lost event, and recording it as
     one would invent missing data out of an ordinary browser event.
  5. Nothing here is required for a focus loss to be COUNTED: the counters are
     written before the detail is, so instrumentation cannot cost a violation.

Run:  python3 scripts/tests/tab_monitor_detail_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

from otree_inprocess import boot  # noqa: E402

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         got  {got!r}\n         want {want!r}")
        FAILURES.append(label)


def section(title):
    print(f"\n=== {title} ===")


class FakePlayer:
    """Just enough player for common._apply_focus_loss.

    The counting core touches `player.session.config`, `player.participant` and
    `player.id_in_group`; a real oTree page is not needed to exercise it, and
    driving it directly is what lets the client payload be controlled exactly.
    """

    def __init__(self, participant, config):
        self.participant = participant
        self.session = type('S', (), dict(config=config))()
        self.id_in_group = 1


def main():
    ot = boot()
    import common  # importable once oTree's settings are loaded

    config = dict(tab_monitor=True, tab_monitor_max_violations=99)

    session = ot.create_session('prolific', num_participants=1)
    participant = session.get_participants()[0]
    player = FakePlayer(participant, config)

    section('two focus losses on DIFFERENT pages')
    # The SERVER's idea of the current page is what must be recorded. The client
    # payload deliberately claims something else, so a test that passed by
    # reading the client value would be visibly wrong.
    participant._current_page_name = 'Demographics'
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e1', count=1,
                     page='/spoofed/by/the/client'))
    participant._current_page_name = 'Feedback'
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e2', count=2,
                     page='/spoofed/by/the/client'))

    events = participant.vars.get('tab_monitor_focus_events') or []
    check('two events recorded', len(events), 2)
    check('pages come from the SERVER, not the client payload',
          [e['page'] for e in events], ['Demographics', 'Feedback'])
    check('region recorded on each', {e['region'] for e in events},
          {'questionnaire'})
    check('each event carries a server timestamp',
          all(isinstance(e.get('ts'), int) and e['ts'] > 0 for e in events), True)
    check('the counters still work exactly as before',
          participant.vars.get('tab_monitor_focus_loss_count_outro'), 2)
    check('and the ejecting counter was untouched',
          participant.vars.get('tab_monitor_focus_loss_count') or 0, 0)

    section('tab_monitor_where names the pages, not just the region')
    check('flag is the record-only verdict',
          common.derive_tab_monitor_flag(participant.vars), 'observed')
    check('where names the actual pages',
          common.derive_tab_monitor_where(participant.vars),
          'questionnaire: Demographics, Feedback')
    check('the region word is still the prefix, so filters keep working',
          common.derive_tab_monitor_where(participant.vars)
          .startswith('questionnaire'), True)

    section('a participant with no per-event detail degrades to the region')
    check('region alone when tab_monitor_focus_events is absent',
          common.derive_tab_monitor_where(dict(tab_monitor_focus_loss_count_outro=2)),
          'questionnaire')

    section('retrospective drop detection')
    check('no evidence of loss so far',
          participant.vars.get('tab_monitor_focus_losses_missed_at_least') or 0, 0)
    # Client says this is its 5th loss; we have counted 2. Two never arrived.
    participant._current_page_name = 'Results'
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e3', count=5))
    check('at-least evidence recorded (client 5 vs our 3)',
          participant.vars.get('tab_monitor_focus_losses_missed_at_least'), 2)

    # A LOWER client count is not a drop: cleared sessionStorage, reused
    # browser, second tab, replay. Recording it would invent missing data.
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e4', count=1))
    check('a client total BEHIND ours is not recorded as a loss',
          participant.vars.get('tab_monitor_focus_losses_missed_at_least'), 2)

    # It is a maximum, never a sum — otherwise one drop observed repeatedly
    # would multiply into many.
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e5', count=6))
    check('still a maximum, not a running sum',
          participant.vars.get('tab_monitor_focus_losses_missed_at_least'), 2)

    section('a missing or unusable client count says nothing')
    before = participant.vars.get('tab_monitor_focus_losses_missed_at_least')
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e6'))
    common.focus_live_method_outro(
        player, dict(type='focus_loss', event_id='e7', count='lots'))
    check('unusable counts leave the evidence untouched',
          participant.vars.get('tab_monitor_focus_losses_missed_at_least'), before)
    check('but the losses were still COUNTED',
          participant.vars.get('tab_monitor_focus_loss_count_outro'), 7)

    section('SUMMARY')
    if FAILURES:
        print(f"  {len(FAILURES)} CHECK(S) FAILED: {FAILURES}")
        return 1
    print('  ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
