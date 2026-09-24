#!/usr/bin/env python
"""WRITE THE DEPLOY BUILD STAMP — the ONE writer of ``BUILD_INFO.json``.

WHAT THIS IS FOR
----------------
A commit cannot contain its own SHA, so the SHA is stamped at DEPLOY time. At
deploy, extract the committed tree into a staging directory and run this script,
which writes ``BUILD_INFO.json`` at the app root; the Dockerfile's ``COPY . .``
then ships it into the image, and ``buildinfo.py`` reads it at boot.

**The file is NEVER committed** (it is in ``.gitignore``): it describes a build
OF a commit, so committing it would put a stale stamp in the tree of the NEXT
commit — worse than no stamp at all.

*** TWO TRAPS THAT COME WITH THAT, BOTH OF WHICH BITE. ***

  1. ``railway up`` HONOURS ``.gitignore``, so a gitignored stamp is silently
     never uploaded and the build deploys completely inert, reporting unstamped
     while looking perfectly healthy. The property that makes the file safe for
     git makes it invisible to that deploy. The fix — delete ``.gitignore`` from
     the throwaway staging tree and write a ``.railwayignore`` instead — is
     documented in ``docs/hosting_railway.md``.
  2. Not running this script at all is how you turn provenance OFF. There is no
     setting, because there is nothing to switch: with no ``BUILD_INFO.json``
     the whole feature is inert and everything reads ``unstamped``. That is the
     local-development path, exercised by every test run.

WHY IT TAKES EXPLICIT ARGUMENTS AND NEVER SHELLS OUT TO GIT
-----------------------------------------------------------
  * **It has to be testable HERE.** A container, a CI image or an agent working
    in a staged copy may have no git and no repository; a script that ran
    ``git rev-parse`` could only be exercised by running a real deploy.
  * **The caller already knows.** Whoever runs the deploy is standing in the
    repo at the right commit. Passing the values in keeps the "which commit"
    decision visible in the deploy script, instead of hiding it inside a helper
    that resolves HEAD at whatever moment it happens to run.

THE CONTRACT — exactly what the deploy step must produce
--------------------------------------------------------
    {
      "commit":       "<40-char sha>",       git rev-parse HEAD
      "commit_short": "<7 chars>",           derived; --commit-short to override
      "commit_date":  "<ISO 8601>",          git log -1 --format=%cI
      "subject":      "<commit subject>",    git log -1 --format=%s
      "build_number": <int>,                 git rev-list --count HEAD
      "built_at":     "<ISO 8601>",          when the image was built
      "tree_clean":   true                   was the working tree clean?
    }

``build_number`` is ``git rev-list --count HEAD``: monotonic, DERIVED rather
than stored, needing no counter file and no extra commit per deploy, and
reproducible from any checkout — and it is the half a human can say out loud,
because nobody reads a SHA aloud. (It is also the answer to "can I choose the
build number?": yes, because unlike a hash it is not derived from content.)

CALLED LIKE THIS, from the staging directory at deploy:

    python scripts/write_build_info.py \\
        --commit       "$(git rev-parse HEAD)" \\
        --commit-date  "$(git log -1 --format=%cI)" \\
        --subject      "$(git log -1 --format=%s)" \\
        --build-number "$(git rev-list --count HEAD)" \\
        --tree-clean   "$(test -z "$(git status --porcelain)" && echo true || echo false)"

Exit codes: 0 written, 2 refused.

IT REFUSES RATHER THAN WRITING SOMETHING PLAUSIBLE, AND THAT IS NOT A GATE.
Build provenance never fails anything in the application (DECISIONS.md) — but
this is a deploy-time WRITER refusing its own malformed ARGUMENTS, before
anything is deployed, and the study that results is simply an unstamped one,
which runs perfectly. A stamp that is not a real 40-character SHA would be
worse than no stamp: the data would carry a provenance value nothing can
resolve, and no later reader could tell it from a real one. The SHA test is
imported from ``buildinfo.is_real_sha`` — the same predicate the reader uses, so
the writer cannot produce what the reader would reject.

The write is ATOMIC (temp file + ``os.replace``): a deploy interrupted mid-write
leaves the previous file or no file, never half a JSON object — and half a JSON
object is exactly the state ``buildinfo.load`` would have to call unstamped.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# The app root, found the way everything else in this repo finds it: from THIS
# file, never from the working directory (scripts/tests/_repo.py has the full
# argument). One level up from scripts/ is the root only because that is where
# settings.py and buildinfo.py sit, which is checked below by the import.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from buildinfo import (BUILD_INFO_FILENAME, BUILD_INFO_KEYS,  # noqa: E402
                       is_real_sha)


def build_info_dict(commit, commit_date, subject, build_number,
                    built_at=None, tree_clean=True, commit_short=None) -> dict:
    """The stamp as a dict, in the contract's key order.

    PURE: no clock unless ``built_at`` is omitted, no filesystem, no git. That
    is what lets a test assert the exact bytes.
    """
    if not is_real_sha(commit):
        raise ValueError(
            f'commit must be a 40-character hex SHA (got {commit!r}). A stamp '
            f'that is not a real SHA is worse than no stamp: the data would '
            f'then carry provenance nothing can resolve, and no reader could '
            f'tell it from a real one.')
    commit = commit.lower()
    if commit_short is None:
        commit_short = commit[:7]
    if built_at is None:
        built_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return {
        'commit': commit,
        'commit_short': commit_short,
        'commit_date': str(commit_date or ''),
        'subject': str(subject or ''),
        'build_number': int(build_number),
        'built_at': str(built_at),
        'tree_clean': bool(tree_clean),
    }


def write_build_info(path, **values) -> dict:
    """Write the stamp to ``path`` ATOMICALLY. Returns the dict written."""
    info = build_info_dict(**values)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(info, fh, indent=2, sort_keys=False)
        fh.write('\n')
    os.replace(tmp, path)
    return info


def _bool(value) -> bool:
    """Accept what a shell produces: true/false, 1/0, yes/no, clean."""
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'clean')


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description='Write BUILD_INFO.json (the deploy build stamp).')
    p.add_argument('--commit', required=True,
                   help='git rev-parse HEAD (40-char SHA)')
    p.add_argument('--commit-date', default='',
                   help='git log -1 --format=%%cI')
    p.add_argument('--subject', default='', help='git log -1 --format=%%s')
    p.add_argument('--build-number', required=True, type=int,
                   help='git rev-list --count HEAD')
    p.add_argument('--built-at', default=None,
                   help='ISO 8601; defaults to now (UTC)')
    p.add_argument('--tree-clean', default='true',
                   help='true/false — was the working tree clean?')
    p.add_argument('--commit-short', default=None,
                   help='override the derived 7-character short SHA')
    p.add_argument('--out',
                   default=os.path.join(_APP_ROOT, BUILD_INFO_FILENAME),
                   help=f'where to write (default: the app root/'
                        f'{BUILD_INFO_FILENAME})')
    args = p.parse_args(argv)

    try:
        info = write_build_info(
            args.out, commit=args.commit, commit_date=args.commit_date,
            subject=args.subject, build_number=args.build_number,
            built_at=args.built_at, tree_clean=_bool(args.tree_clean),
            commit_short=args.commit_short)
    except Exception as exc:                                   # noqa: BLE001
        print(f'[build-info] REFUSED: {exc}', file=sys.stderr)
        print('[build-info] nothing was written. The deploy can proceed '
              'unstamped — provenance is documentation, never a gate.',
              file=sys.stderr)
        return 2
    # Cannot happen — a guard, not a formality. If build_info_dict ever stops
    # writing a contract key, this says so at the deploy rather than leaving a
    # reader to discover the gap months later.
    missing = [k for k in BUILD_INFO_KEYS if k not in info]
    if missing:
        print(f'[build-info] REFUSED: the written stamp is missing {missing}',
              file=sys.stderr)
        return 2
    print(f'[build-info] wrote {args.out}: build {info["build_number"]} · '
          f'{info["commit_short"]}'
          + ('' if info['tree_clean'] else '  (DIRTY WORKING TREE)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
