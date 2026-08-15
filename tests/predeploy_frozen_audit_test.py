#!/usr/bin/env python
"""The predeploy FROZEN-SESSION CONFIG AUDIT reports exactly the stale session.

WHY THIS EXISTS (Julian, 2026-08-13)
------------------------------------
A session config is frozen at creation, so any parameter added or corrected
after a session was created is missing or stale FOR THAT SESSION while
settings.py looks perfectly correct. `scripts/predeploy_check.py` check 2b
audits every existing session against the current settings; this test pins its
contract with the acceptance case Julian named: a database containing one
session created BEFORE a key existed and one created AFTER must report exactly
the first.

It also pins the TWO-SEVERITY rule the audit must never lose: only a MISSING
key or a REPLACE_* placeholder FAILS; a plain value difference is reported as
information, never failed (static_version alone changes on nearly every
deploy — an audit failing on any difference would be ignored within a
fortnight and then catch nothing).

NB this is DETECTION of a stale session existing; tests/frozen_config_test.py
is RESILIENCE (a stripped config walks without a 500). Different things, both
worth having — see check_frozen_session_configs' docstring.

Run:  python tests/predeploy_frozen_audit_test.py    (oTree must be importable)
Exit 0 = all checks passed. Boots no server and never touches the real database.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otree_inprocess import boot  # noqa: E402

ot = boot(production=True)          # MUST come before any app import

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, 'scripts'))
import predeploy_check as pdc  # noqa: E402

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


class _StubLog:
    """The audit only write()s marker lines; capture them."""
    def __init__(self):
        self.lines = []

    def write(self, msg):
        self.lines.append(msg)

    def write_exc(self, prefix):
        import traceback
        self.lines.append(f'{prefix}: {traceback.format_exc()}')


def stored_sessions():
    """Gather (code, config_name, frozen_config) exactly as check 2b does."""
    from otree.database import DBSession
    from otree.models import Session
    s = DBSession()
    try:
        return [(sess.code, (sess.config or {}).get('name'),
                 dict(sess.config or {}))
                for sess in s.query(Session).all()]
    finally:
        s.close()


def run_audit():
    import settings
    current_configs = {c['name']: dict(c) for c in settings.SESSION_CONFIGS}
    return pdc.audit_frozen_session_configs(
        stored_sessions(), current_configs, settings.SESSION_CONFIG_DEFAULTS)


def main():
    # Real (non-placeholder) codes, so the only failures in play are the ones
    # each section deliberately constructs.
    REAL_CODES = dict(
        prolific_cc_code='C0FFEE01',
        prolific_noconsent_code='C0FFEE02',
        prolific_dq_quiz_code='C0FFEE03',
        prolific_dq_tab_code='C0FFEE04',
        prolific_device_code='C0FFEE05',
    )

    section('one session created BEFORE a key existed, one AFTER — '
            'report exactly the first')
    stale = ot.create_session('prolific', num_participants=1,
                              modified_session_config_fields=REAL_CODES)
    removed = ot.strip_config_keys(stale, ['prolific_cc_code'])
    check(removed == ['prolific_cc_code'],
          f'the stale session had prolific_cc_code deleted from its stored '
          f'config (removed={removed}) — the state of a session created '
          f'before the key existed')
    fresh = ot.create_session('prolific', num_participants=1,
                              modified_session_config_fields=REAL_CODES)

    problems, diffs = run_audit()
    check(len(problems) == 1,
          f'exactly ONE problem reported across both sessions '
          f'(got {len(problems)}: {problems})')
    if problems:
        code, key, kind, _extra = problems[0]
        check(code == stale.code,
              f'it names the STALE session ({stale.code}; got {code})')
        check(key == 'prolific_cc_code',
              f'it names the offending key (got {key!r})')
        check(kind == 'MISSING',
              f'and says which of the two problems it is (got {kind!r}) — '
              f'so the operator knows to RECREATE the session, not fix a value')
    check(not any(code == fresh.code for code, *_ in problems),
          f'the session created AFTER the key existed ({fresh.code}) is not '
          f'reported as a problem')

    section('plain value differences are REPORTED, never FAILED')
    # Both sessions carry real codes where the current settings ship REPLACE_*
    # placeholders — a genuine difference that is CORRECT, not broken.
    check(any(code == fresh.code and key == 'prolific_dq_quiz_code'
              for code, key, *_ in diffs),
          'the fresh session\'s real dq code differs from the shipped '
          'placeholder and appears in the informational diffs')
    check(not any(code == fresh.code and kind in ('MISSING', 'PLACEHOLDER')
                  for code, key, kind, *_ in problems),
          'and that difference produced no failure of either kind')

    section('a REPLACE_* placeholder in a FROZEN session fails, named')
    # A session created straight from the shipped config carries the REPLACE_*
    # codes — the "fixed the codes in settings but forgot to recreate the
    # session" case that prelaunch_check cannot see.
    placeholder = ot.create_session('prolific', num_participants=1)
    problems, _diffs = run_audit()
    mine = [(key, kind) for code, key, kind, _ in problems
            if code == placeholder.code]
    check(('prolific_cc_code', 'PLACEHOLDER') in mine,
          f'the placeholder session is reported, naming the key and the '
          f'PLACEHOLDER kind (got {mine})')
    check(all(kind in ('MISSING', 'PLACEHOLDER') for _key, kind in mine),
          'and only the two failure kinds exist — nothing else may fail '
          '(the two-severity rule)')
    check(not any(code == fresh.code for code, *_ in problems),
          'the fully-current session is still clean')

    section('the check records NOT TESTED in degraded mode (fresh database, '
            'no live sessions to audit)')
    before = len(pdc.RESULTS)
    pdc.check_frozen_session_configs(_StubLog(), degraded=True)
    added = pdc.RESULTS[before:]
    check(len(added) == 1 and added[0][1] is pdc.NOT_TESTED,
          f'degraded mode records NOT TESTED, never PASS '
          f'(got {[(n, ok) for n, ok, _ in added]})')

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
