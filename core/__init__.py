"""The template's shared runtime modules, imported by the apps and settings.py.

Import them as ``from core import common`` (or ``from core.identity import
normalise_label``). oTree puts the project root on ``sys.path``, so ``core`` is
importable from every app, from settings.py and from the tools in scripts/
(which put the root on the path through ``scripts/tests/_repo.py``).

Only ``settings.py`` must sit at the project root: oTree requires it there. These
modules used to sit beside it; they live here so the root holds the apps and the
documents, not a dozen loose files.

``REPO_ROOT`` is the project root, found by walking UP from this file to the
directory holding ``settings.py`` — the same marker walk as
``scripts/tests/_repo.py`` (see .claude/DECISIONS.md, "The repo root is found by walking
up to `settings.py`, never by counting directories"). The modules here that need
the root (the build stamp in ``buildinfo``, the source scans in ``payoff_guard``
and ``fee_guard``) read it from here rather than from their own directory, which
since the move is ``core/`` and not the root.

Keep this file free of imports from the project: settings.py imports
``core.buildinfo`` and ``core.identity`` while it is itself being imported.
"""
import os

_ROOT_MARKER = 'settings.py'


def _find_repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    directory = here
    while True:
        if os.path.isfile(os.path.join(directory, _ROOT_MARKER)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            raise RuntimeError(
                f'could not locate {_ROOT_MARKER} above {here!r}: core/ is not '
                'inside an oTree project checkout')
        directory = parent


REPO_ROOT = _find_repo_root()
