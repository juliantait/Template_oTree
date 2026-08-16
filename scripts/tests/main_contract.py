"""THE TASK-PAGE CONTRACT the test suite holds against `main` (review S3).

One module for the task pages' NAMES and FORM PAYLOADS, imported by every
test that walks the flow — so swapping the game (the template's core
operation) means updating this file plus the game itself, and a missed test
site becomes an ImportError instead of a test quietly walking pages that no
longer exist. Before this file the payload dict was retyped in seven test
files and the page names in more.

This is DATA, not a framework: each test file stays runnable on its own
(`python scripts/tests/<name>.py`), which is the suite's documented convention
(docs/skills_claude/writing_tests.md). scripts/predeploy_check.py's
RESUME_PREFERENCE also names these pages, but tolerates unknown ones by
design — update it with this file, it just will not break if you forget.
"""

# The task pages, in page_sequence order (main.page_sequence).
TASK_PAGES = ['GameStart', 'payoff']


def task_page_submits():
    """The form payload each task page needs for one walked round.

    `client_ms` is the passive-capture hidden field, submitted EMPTY — the
    no-JS submit every suite must tolerate (docs/conventions.md: an empty hidden
    field is stored, never rejected). A fresh dict per call, so one test's
    mutation cannot leak into another's walk.
    """
    return {
        'GameStart': {'client_ms': ''},
        'payoff': {},
    }
