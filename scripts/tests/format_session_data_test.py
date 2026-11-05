#!/usr/bin/env python3
"""The lab session number through scripts/format_session_data.py.

The launcher's lab session number is short text in `session.config.lab_session`.
An analyst reads it from the files this script writes, so a value altered here is
a row filed under the wrong lab session with nothing to show for it. This runs the
REAL script as a subprocess on fixture exports (it needs pandas, not oTree) and
reads the output files as raw text, because reading them back through pandas'
type guessing would hide the very damage being tested for. It asserts:

  * 217b, 007, NA and `test` reach every row of the sensitive and anonymous files
    exactly as written;
  * a 217 next to an empty session stays 217, not 217.0, and the empty stays empty;
  * the payment file does not carry it, and still carries its own columns;
  * an older export without the column still runs and stays without it;
  * the other columns come out the same with the column present and absent;
  * the anonymous and payment files use the one list in data_columns.py, which the
    dashboard's Download data button uses too.

Run:  python scripts/tests/format_session_data_test.py
"""
import csv
import os
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _repo import REPO_ROOT  # noqa: E402

SCRIPT = os.path.join(REPO_ROOT, 'scripts', 'format_session_data.py')
LAB = 'session.config.lab_session'

_failures = []


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        _failures.append(msg)


def section(t):
    print(f"\n=== {t} ===")


def fixture_rows(lab_values):
    """A small export, one row per value. `None` for lab_values means an older
    export with no such column at all."""
    n = 3 if lab_values is None else len(lab_values)
    rows = []
    for i in range(n):
        row = {'participant.code': f'code{i}', 'participant.label': f'seat{i}'}
        if lab_values is not None:
            row[LAB] = lab_values[i]
        row.update({
            'session.config.payment_show_up': '7.5',
            'outro.1.player.earned': str(10 + i),
            'intro.1.player.quiz_attempt_log': '[{"a": 1}]',
        })
        rows.append(row)
    return rows


def run_script(lab_values):
    """Run the real script. Returns (returncode, stderr, {file: (header, rows)})."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'wide.csv')
        rows = fixture_rows(lab_values)
        with open(src, 'w', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        env = {k: v for k, v in os.environ.items()
               if k not in ('SESSION_DATA_OUT', 'SESSION_DATA_EMAIL')}
        done = subprocess.run(
            [sys.executable, SCRIPT, src, '1', '--out', os.path.join(tmp, 'out')],
            capture_output=True, text=True, env=env, cwd=tmp)
        files = {}
        for name in ('sensitive', 'anonymous', 'payments'):
            path = os.path.join(tmp, 'out', name, 'Session_1.csv')
            if os.path.exists(path):
                with open(path, newline='') as fh:
                    table = list(csv.reader(fh))
                files[name] = (table[0], [dict(zip(table[0], r)) for r in table[1:]])
        return done.returncode, done.stderr, files


def assert_lab_values(label, lab_values, expected):
    code, err, files = run_script(lab_values)
    check(code == 0, f'{label}: the script exits 0 (stderr: {err.strip()[-200:]!r})')
    for name in ('sensitive', 'anonymous'):
        got = [r.get(LAB) for r in files.get(name, ('', []))[1]]
        check(got == expected, f'{label}: {name} has {expected!r} (got {got!r})')
    return files


def main():
    section('values that do not survive type guessing reach every row verbatim')
    for value in ('217b', '007', 'NA', 'test', '217'):
        assert_lab_values(repr(value), [value] * 3, [value] * 3)

    section('a 217 next to an empty session: an export with two sessions')
    assert_lab_values('217 + empty', ['217', '217', ''], ['217', '217', ''])

    section('not used: the column is there and every cell is empty')
    files = assert_lab_values('all empty', ['', '', ''], ['', '', ''])
    check(LAB in files['sensitive'][0], 'all empty: sensitive has the column')
    check(LAB in files['anonymous'][0], 'all empty: anonymous has the column')

    section('the payment file: no lab session, its own columns intact')
    _, _, files = run_script(['217b'] * 3)
    header, rows = files['payments']
    check(LAB not in header, f'payments does not carry it (header {header!r})')
    check([r['outro.1.player.earned'] for r in rows] == ['10', '11', '12'],
          'payments still carries the earned amounts')

    section('an older export with no such column')
    code, err, old = run_script(None)
    check(code == 0, f'the script exits 0 (stderr: {err.strip()[-200:]!r})')
    check(LAB not in old['sensitive'][0], 'sensitive stays without the column')
    check(LAB not in old['anonymous'][0], 'anonymous stays without the column')
    check(len(old['sensitive'][1]) == 3 and len(old['anonymous'][1]) == 3,
          'every row is still written')

    section('nothing else moves: same export with and without the column')
    _, _, new = run_script(['217b'] * 3)
    for name in ('sensitive', 'anonymous'):
        new_header = [c for c in new[name][0] if c != LAB]
        check(new_header == old[name][0],
              f'{name}: the same other columns, same order ({new_header!r})')
        check([{k: v for k, v in r.items() if k != LAB} for r in new[name][1]]
              == old[name][1],
              f'{name}: the same values in every other column')
    check(new['sensitive'][1][0]['session.config.payment_show_up'] == '7.5',
          'another session.config column comes through as written')
    check('participant.label' in new['sensitive'][0]
          and 'participant.label' not in new['anonymous'][0],
          'the anonymous file still drops the participant label')
    check(new['sensitive'][1][0]['intro.1.player.quiz_attempt_log'] == '',
          'the attempt-log blob is still blanked')

    section('one set of rules: the same list as the dashboard button')
    sys.path.insert(0, REPO_ROOT)
    import data_columns
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'wide.csv')
        keep = ['participant.code', 'participant.payoff', LAB,
                'outro.1.player.age', 'participant.mturk_worker_id']
        header = keep + list(data_columns.ANON_DROP_COLUMNS)
        with open(src, 'w', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerow(['c1'] * len(header))
        done = subprocess.run(
            [sys.executable, SCRIPT, src, '1', '--out', os.path.join(tmp, 'out')],
            capture_output=True, text=True, cwd=tmp)
        check(done.returncode == 0, f'the script exits 0 ({done.stderr.strip()[-200:]!r})')
        with open(os.path.join(tmp, 'out', 'anonymous', 'Session_1.csv'), newline='') as fh:
            anon_header = next(csv.reader(fh))
        with open(os.path.join(tmp, 'out', 'payments', 'Session_1.csv'), newline='') as fh:
            pay_header = next(csv.reader(fh))
    check(anon_header == keep,
          f'the anonymous file drops exactly data_columns.ANON_DROP_COLUMNS ({anon_header})')
    check(tuple(pay_header) == tuple(c for c in data_columns.FORMAT_PAYMENT_COLUMNS
                                     if c in header),
          f'the payment file is data_columns.FORMAT_PAYMENT_COLUMNS ({pay_header})')
    source = open(SCRIPT).read()
    check('"participant.participant_id_external"' not in source.split('def main')[1]
          .split('required_columns')[0] and 'data_columns.ANON_DROP_COLUMNS' in source,
          'and the script has no second copy of the list')

    print("\n=== SUMMARY ===")
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED")
        for m in _failures:
            print(f"    - {m}")
        return 1
    print("  ALL CHECKS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
