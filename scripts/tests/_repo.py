"""WHERE THE REPO ROOT IS — answered ONCE, for every suite and every tool.

WHY THIS EXISTS
===============
Until 2026-08-16, nineteen files each answered "where is the project root?" by
COUNTING DIRECTORY LEVELS up from their own location:

    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.path.dirname(_TESTS_DIR)
    pathlib.Path(__file__).resolve().parent.parent
    __file__.rsplit('/', 2)[0]

Every one of those encodes the same fragile assumption — *how deep this file
happens to sit* — and they encode it in four different spellings. Moving
`tests/` to `scripts/tests/` that day made all nineteen wrong at once:
eighteen were silently one level short, and the nineteenth (the `rsplit`
spelling) hid from the sweep that fixed the others and surfaced only as
`ModuleNotFoundError: No module named 'settings'` on the first full run.

That is one concept with nineteen implementations, which is the defect class
this repository is built around avoiding. This module is the single
implementation.

WHY THE MARKER WALK RATHER THAN A CORRECTED COUNT
=================================================
A count is only ever right for the layout it was written against; correcting
the number just re-arms the same trap for the next move. What actually DEFINES
this repo's root is that `settings.py` sits in it — oTree requires that, and
`common.py` documents that it can never move. So the root is found by walking
UP from this file until that marker appears. It is correct at any depth, from
any working directory, and it needs nobody to remember to update a number when
a directory moves again.

It also resolves correctly from a STAGED COPY of the repo (the HTTP suites boot
a throwaway checkout elsewhere on disk): the walk finds *that* copy's root,
because it starts from the file actually being executed.

HOW TO USE IT
=============
Bootstrap with your own directory — which is depth-free, unlike a count of how
far the root is — and import this module::

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _repo import REPO_ROOT          # also puts REPO_ROOT on sys.path

Importing it is enough to make ``import settings``, ``import common`` and the
app packages work; `REPO_ROOT` is exported for the tests that need to build
paths (fixtures, the asset manifest, relpath bases).

DO NOT reintroduce a level count anywhere, including in a comment as an
"equivalent" — the next reader will believe it.
"""

import os
import sys

# The file that defines the root. oTree requires settings.py at the project
# root, and common.py's own docstring records that it must stay there, so this
# marker cannot drift without the whole project breaking first.
_ROOT_MARKER = 'settings.py'


def find_repo_root(start=None):
    """Walk up from `start` (default: this file) to the directory holding
    settings.py. Raises rather than guessing — a wrong root silently imports
    the wrong settings, which is worse than stopping."""
    here = os.path.abspath(start or __file__)
    directory = here if os.path.isdir(here) else os.path.dirname(here)
    while True:
        if os.path.isfile(os.path.join(directory, _ROOT_MARKER)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:          # reached the filesystem root
            raise RuntimeError(
                f'could not locate {_ROOT_MARKER} above {here!r}: this file is '
                'not inside an oTree project checkout'
            )
        directory = parent


REPO_ROOT = find_repo_root()

# Importing this module is the whole bootstrap: a suite should not have to
# remember a second line to make `import settings` work.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
