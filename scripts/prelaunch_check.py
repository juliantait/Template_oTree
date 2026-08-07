#!/usr/bin/env python3
"""Machine-checked PRE-LAUNCH guard, as a standalone command (exit code aware).

`settings.py` prints the same banner on every server start, but that is
advisory. Run THIS in CI or a launcher to get a non-zero exit when anything is
still a testing/placeholder value, so a bad launch can be blocked automatically.

Run it in the SAME environment you will launch in (it reads OTREE_PRODUCTION,
etc.):

    OTREE_PRODUCTION=1 python scripts/prelaunch_check.py
"""
import os
import sys

# Make the project root importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settings  # noqa: E402  (importing prints the banner)


def main():
    problems = settings._prelaunch_problems()
    if not problems:
        print("PRE-LAUNCH OK — no testing/placeholder values detected.")
        return 0
    print("PRE-LAUNCH FAILED — fix these before launching:")
    for label, current, must_be in problems:
        print(f"  {label}: currently {current!r}, MUST BE {must_be}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
