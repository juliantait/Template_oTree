#!/usr/bin/env python3
"""EX-POST behaviour-capture derivation (bucket B / §D / §8.10 of the bot spec).

The live WELCOME/QUIZ pages store ONLY the raw telemetry blob; the AI-likelihood
flags are derived DOWNSTREAM in scripts/format_session_data.py, the way Mission
Possible derives them in Cleaning_Tracker.R. This tests that derivation over
FIXTURE blobs — unit-testable without a browser, which is the point of keeping
capture and judgement separate. It asserts:

  * a PASTED answer yields bot_*_paste_detected / bot_*_input_jump;
  * a scripted FAST type yields bot_*_typing_fast (median <= 75 ms);
  * a HUMAN-paced blob yields NEITHER;
  * a BLANK (no-JS) blob yields no measured flags ("not measured", not "clean");
  * add_telemetry_derivation emits the per-page columns AND blanks the raw JSON.

Run:  python scripts/tests/telemetry_derivation_test.py
"""
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _repo import REPO_ROOT  # noqa: E402

# Load the cleaning script by path (it needs pandas but NOT oTree).
_spec = importlib.util.spec_from_file_location(
    'fsd', os.path.join(REPO_ROOT, 'scripts', 'format_session_data.py'))
fsd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fsd)

_failures = []


def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        _failures.append(msg)


def section(t):
    print(f"\n=== {t} ===")


def blob(**kw):
    return json.dumps(kw)


def main():
    section('a PASTED answer: paste + a big single input jump, no typing')
    d = fsd.derive_telemetry(blob(
        paste_detected=True, max_input_jump=120, keydown_count=0, key_times=[]))
    check(d['paste_detected'] is True, 'bot_paste_detected is True')
    check(d['input_jump'] is True,
          f'bot_input_jump is True (jump 120 > {fsd.INPUT_JUMP_MIN_CHARS})')
    check(d['typing_fast'] is False,
          'bot_typing_fast is False (no keystrokes to be fast)')

    section('a scripted FAST type: keystrokes 40 ms apart (<= 75)')
    d = fsd.derive_telemetry(blob(
        keydown_count=6, key_times=[0, 40, 80, 120, 160, 200], max_input_jump=1))
    check(d['typing_median_ms'] == 40.0,
          f'median inter-keystroke interval is 40 ms (got {d["typing_median_ms"]})')
    check(d['typing_fast'] is True,
          f'bot_typing_fast is True (40 <= {fsd.TYPING_FAST_MAX_MS})')
    check(d['input_jump'] is False, 'bot_input_jump is False (one char at a time)')

    section('a HUMAN-paced blob: keystrokes ~220 ms apart, typed not pasted')
    d = fsd.derive_telemetry(blob(
        paste_detected=False, keydown_count=5,
        key_times=[0, 210, 430, 660, 900], max_input_jump=1,
        mouse_move_count=37, click_count=3))
    check(d['typing_fast'] is False,
          f'bot_typing_fast is False (median {d["typing_median_ms"]} > {fsd.TYPING_FAST_MAX_MS})')
    check(d['paste_detected'] is False and d['input_jump'] is False,
          'neither paste nor input-jump flagged for a human-paced typed answer')
    check(d['mouse_move_count'] == 37 and d['click_count'] == 3,
          'the raw interaction counts pass through')

    section('a BLANK (no-JS) blob is "not measured", never "clean"')
    check(fsd.derive_telemetry('') == {},
          'an empty blob derives to {} (no flags), so it cannot read as a clean human')
    check(fsd.derive_telemetry('not json') == {},
          'an unparseable blob derives to {} too, and never raises')

    section('add_telemetry_derivation emits per-page columns AND blanks the raw JSON')
    import pandas as pd
    df = pd.DataFrame({
        'participant.code': ['a', 'b'],
        'participant.telemetry_welcome': [
            blob(paste_detected=True, max_input_jump=90, key_times=[]), ''],
        'participant.telemetry_quiz': [
            blob(keydown_count=4, key_times=[0, 30, 60, 90]), ''],
    })
    out = fsd.add_telemetry_derivation(df.copy())
    check('participant.bot_welcome_paste_detected' in out.columns,
          'a bot_welcome_* column is emitted')
    check('participant.bot_quiz_typing_fast' in out.columns,
          'a bot_quiz_* column is emitted')
    check(bool(out['participant.bot_welcome_input_jump'].iloc[0]) is True,
          'row a: welcome input-jump flagged from the pasted blob')
    check(bool(out['participant.bot_quiz_typing_fast'].iloc[0]) is True,
          'row a: quiz typing-fast flagged (30 ms median)')
    check((out['participant.telemetry_welcome'] == '').all()
          and (out['participant.telemetry_quiz'] == '').all(),
          'the raw JSON blobs are BLANKED in the analysis-ready frame')

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
