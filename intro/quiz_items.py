"""
Centralized quiz item definitions for the intro app.

Edit this file to change quiz questions, choices, and solutions.
"""

# Example quiz items; edit or replace as needed.
QUIZ_ITEMS = [
    dict(
        field='quiz1',
        prompt='Did you read and understand the instructions?',
        choices=['YES', 'NO'],
        answer='YES',
    ),
    dict(
        field='quiz2',
        prompt='If you fail the quiz twice, what happens?',
        choices=[
            'You proceed automatically',
            'You are asked to reread the instructions',
            'Nothing changes'
        ],
        answer='You are asked to reread the instructions',
    ),
    # dict(
    #     field='quiz3',
    #     prompt='How many rounds are in the main task?',
    #     choices=['1', '2', '4'],
    #     answer='4',
    # ),
    #     dict(
    #     field='quiz4',
    #     prompt='How many rounds are in the main task?',
    #     choices=['1', '2', '4'],
    #     answer='4',
    # ),
    #     dict(
    #     field='quiz5',
    #     prompt='How many rounds are in the main task?',
    #     choices=['1', '2', '4'],
    #     answer='4',
    # ),
]

