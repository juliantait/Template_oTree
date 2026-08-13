"""
Centralized quiz item definitions for the intro app.

Edit this file to change quiz questions, choices, and solutions.
"""

# PLACEHOLDERS FOR MACHINERY TESTING, deliberately trivial (Julian,
# 2026-08-13). These shipped items exist so the template's quiz machinery can
# be exercised — wrong answers, retries, the attempt log, the thresholds — not
# to be exemplary comprehension items. They are expected to be replaced
# WHOLESALE by a real study; see skills_claude/writing_quiz.md for what a real
# item should look like (and for why an item must never quiz the study's own
# mechanics or the measured effect).
QUIZ_ITEMS = [
    dict(
        field='quiz1',
        prompt='Did you read and understand the instructions?',
        choices=['YES', 'NO'],
        answer='YES',
    ),
    dict(
        field='quiz2',
        prompt='What is ice when it melts?',
        choices=['Metal', 'Water', 'Nothing'],
        answer='Water',
    ),
]
