#!/usr/bin/env python
"""The asset manifest must stay fresh — a stale one silently disables the guard.

WHY THIS EXISTS
---------------
`settings.STATIC_VERSION` is the cache-buster appended to every CSS/JS URL, and
`scripts/asset_manifest.json` records the sha256 of everything under `_static/`
against the version that was current when the files last changed. The pre-launch
guard (`scripts/prelaunch_check.py`) fails when the two disagree, so a redeploy
whose assets changed but whose version did not cannot ship stale-from-cache.

But bumping the version and RE-STAMPING the manifest are two separate manual
steps, and the second is easy to forget: on 2026-08-15 the logo rename bumped
`STATIC_VERSION` 14 -> 15 and nobody ran `--stamp-assets`, so the manifest sat
at 14. Nothing runs the pre-launch guard routinely, so that stale stamp lay
hidden for two days and was found by accident, not by a red test — exactly the
failure mode this repo cares about (CLAUDE.md, "a check that goes stale
silently"). A stale manifest is worse than cosmetic: it silently disables the
guard for the NEXT change, because `asset_problems()` compares against a hash
that no longer describes any real generation of the files.

WHAT IT COVERS
--------------
1. The manifest exists and is fresh: `prelaunch_check.asset_problems()` — the
   SAME function the pre-launch guard calls, not a re-implementation — reports
   nothing, and the stored version matches `settings.STATIC_VERSION`.
2. The matching PRESENCE for that absence (CLAUDE.md testing standard: never
   assert an absence without the paired presence): with the manifest monkeyed
   into each of its three stale shapes — missing, files-changed-same-version,
   and version-bumped-not-re-recorded — the guard actually FIRES. Without this,
   check 1 would pass just as happily against a guard that never reports
   anything, which is the very way this went unnoticed.

Run:  python scripts/tests/asset_manifest_test.py
Exit 0 = fresh and the guard demonstrably fires when it is not. Boots no server,
touches no database, needs no browser — pure filesystem plus a settings import.

If check 1 FAILS, the fix is one command, and it is the whole point of the guard:
    python scripts/prelaunch_check.py --stamp-assets
Run it whenever you change, add, rename or remove a file under `_static/` (and
after bumping `settings.STATIC_VERSION`). See DECISIONS.md, "The asset manifest
is re-stamped by hand, so a test asserts it actually was".
"""
import os
import sys

# prelaunch_check lives one directory up (scripts/), next to the manifest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import prelaunch_check as pc  # noqa: E402  (imports settings, prints the banner)
import settings  # noqa: E402

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def main():
    section('the committed manifest is fresh against the current _static/')
    stored = pc.read_manifest()
    check(stored is not None,
          f'{os.path.relpath(pc.MANIFEST, pc._ROOT)} exists and parses')

    # THE assertion, made through the guard's own function so there is one
    # implementation of "is the manifest fresh?", called by both the launch
    # gate and this test (CLAUDE.md: one concept, never two implementations).
    problems = pc.asset_problems()
    check(problems == [],
          'prelaunch_check.asset_problems() reports nothing — the files under '
          f'_static/ match the stamp (else run: python '
          f'scripts/prelaunch_check.py --stamp-assets){"" if not problems else " :: " + "; ".join(p[0] for p in problems)}')

    if stored is not None:
        check(str(stored.get('static_version')) == str(settings.STATIC_VERSION),
              f'the stamp records the current STATIC_VERSION '
              f'({stored.get("static_version")!r} vs settings '
              f'{settings.STATIC_VERSION!r})')

    section('the guard actually FIRES on a stale manifest (the paired presence)')
    # Prove check 1 is not vacuous: swap in each stale shape and confirm the
    # guard reports it. Restore the real reader afterwards no matter what.
    real_reader = pc.read_manifest
    real_digest, _ = pc.hash_static()
    try:
        pc.read_manifest = lambda: None
        check(len(pc.asset_problems()) == 1,
              'a MISSING manifest is reported')

        wrong_hash = 'deadbeef' * 8
        pc.read_manifest = lambda: {
            'static_version': str(settings.STATIC_VERSION),
            'static_sha256': wrong_hash}
        fired = pc.asset_problems()
        check(len(fired) == 1 and 'files under _static/ changed' in fired[0][0],
              'files changed on the SAME version is reported as the bump-me bug')

        pc.read_manifest = lambda: {
            'static_version': '0', 'static_sha256': wrong_hash}
        fired = pc.asset_problems()
        check(len(fired) == 1 and 'not re-recorded' in fired[0][0],
              'a version bumped but not re-recorded is reported (the 2026-08-15 '
              'case this test exists for)')

        # And when the stored hash IS the real one, no false positive.
        pc.read_manifest = lambda: {
            'static_version': str(settings.STATIC_VERSION),
            'static_sha256': real_digest}
        check(pc.asset_problems() == [],
              'a manifest matching the real hash is accepted (no false alarm)')
    finally:
        pc.read_manifest = real_reader

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
