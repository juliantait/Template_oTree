"""The correct — and a definite wrong — answer to the SHIPPED quiz, derived from
the item set itself. The ONE place a test learns what the quiz answers are.

WHY THIS EXISTS. Every HTTP walker that has to drive a participant PAST the quiz
needs the right answers. In PRODUCTION mode the page does not carry them — the
DEBUG-only `quiz-solutions-data` blob is emitted only under `settings.DEBUG`
(see intro/templates/quiz.html) — so a walker that reads its answers off the
page fails the quiz. On a Prolific config that is not a dead end: `quiz_comprehension_dq`
is on, so the failed walker is routed to the COMPREHENSION-DQ ending instead of
the ending it meant to reach, and every assertion aimed at the intended ending
is now being made against the wrong page. (That is exactly what left
device_gate_test and screenout_softwall_test red for a while: their admitted /
completing walks landed on exit code -2.) The cure is to answer the quiz from
the item DEFINITIONS, which are present whatever the server's DEBUG state is.

WHY NOT HARDCODE `{'quiz1': 'YES', ...}` IN EACH TEST. This template ships its
quiz items to be REPLACED WHOLESALE by a real study (intro/quiz_items.py, and
the writing_quiz skill). A hardcoded answer map is a SECOND source of truth for
"what is the right answer", and it drifts silently the moment the items change:
the walker then fails the new quiz, and — worst of all — a test that means to
prove "the participant COMPLETED" quietly starts proving something about the
comprehension-DQ ending instead, still green because both are real endings.
That is the one-concept-two-implementations defect this repository is built to
avoid (CLAUDE.md). One implementation, derived from the items, called by every
walker, cannot drift from the items it is derived from.

WHY BY PATH, not `from intro.quiz_items import ...`. Importing the package runs
`intro/__init__.py`, which needs oTree configured; the HTTP suites drive a
SEPARATE server process and must not configure oTree in the test process.
Loading the module file directly by its path sidesteps that. It also means the
answers never come from the server under test — a quiz that started sending the
WRONG solutions could not make a test agree with it. (This is the loader
full_journey_test.py carried; it lives here now so it is not re-implemented once
per suite.)
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)


def load_quiz_items():
    """The shipped quiz items, loaded straight from the file by path."""
    path = os.path.join(REPO_ROOT, 'intro', 'quiz_items.py')
    spec = importlib.util.spec_from_file_location('_quiz_items', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.QUIZ_ITEMS


def _a_wrong_choice(item):
    """Any listed choice that is not the answer.

    Asserts there IS one rather than defaulting: an item with a single choice
    would silently make WRONG == CORRECT, and a "fail the quiz once" walk would
    then pass the quiz without noticing. Fail loudly here instead."""
    for choice in item['choices']:
        if choice != item['answer']:
            return choice
    raise ValueError(
        f"quiz item {item['field']!r} offers no choice other than its answer, "
        f"so a definite WRONG answer cannot be built from it")


QUIZ_ITEMS = load_quiz_items()

# The field -> value map that PASSES the quiz.
CORRECT = {i['field']: i['answer'] for i in QUIZ_ITEMS}

# A definite WRONG answer per item (used by the walks that fail the quiz on
# purpose): each maps to a choice that is not the answer.
WRONG = {i['field']: _a_wrong_choice(i) for i in QUIZ_ITEMS}
