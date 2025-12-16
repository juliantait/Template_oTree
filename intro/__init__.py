from otree.api import *
import json
from .quiz_items import QUIZ_ITEMS

doc = """
Intro
"""
class C(BaseConstants):
    NAME_IN_URL = 'Introduction'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 2
    verify_quiz = True # set to True to verify quiz answers, False to skip verification during testing



class Subsession(BaseSubsession):
    pass
      
class Group(BaseGroup):
    pass

# Dynamically generate Player fields from QUIZ_ITEMS
def make_quiz_fields():
    fields = {
        'participant_label': models.StringField(),
        'redoinstructions': models.BooleanField(initial=0, blank=True),
        'skiptoquiz': models.BooleanField(initial=0, blank=True),
        'num_failed_attempts': models.IntegerField(initial=0)
    }
    for item in QUIZ_ITEMS:
        fields[item['field']] = models.StringField(
            label=item['prompt'],
            widget=widgets.RadioSelect,
            choices=item['choices']
        )
    return fields

class Player(BasePlayer):
    # Add all quiz fields and standard fields dynamically
    locals().update(make_quiz_fields())


# FUNCTIONS 
def common_template_vars(session, group):
    return {
        
    }  

# PAGES    
class instructing(Page):
    pass

class prequiz(Page):
    form_model = 'player'
    form_fields = ['redoinstructions']
    def is_displayed(player):
        return player.group.round_number == 1
        
class quiz(Page):
    form_model = 'player'
    # Dynamically include only the quiz items that have corresponding Player fields
    quiz_items = [item for item in QUIZ_ITEMS if hasattr(Player, item['field'])]
    quiz_field_names = [item['field'] for item in quiz_items]
    quiz_solutions = [item['answer'] for item in quiz_items]

    def get_form_fields(player):
        # Use class attribute to avoid attribute errors when oTree passes the Player instance
        return quiz.quiz_field_names + ['redoinstructions']

    def is_displayed(player):
        return player.redoinstructions == 0

    def error_message(player, values):
        # Skip validation entirely when quiz verification is disabled
        if not C.verify_quiz:
            return
        # Define mapping of quiz fields to their correct answers
        solutions = dict(zip(quiz.quiz_field_names, quiz.quiz_solutions))
        # Check answers
        wrong = [
            key for key in solutions
            if values.get(key, '') != solutions[key]
        ]
        if wrong:
            player.num_failed_attempts += 1
            player.participant.failed_attempts += 1
            if player.num_failed_attempts >= 2:
                return "One or more quiz answers are wrong. Try re-reading the instructions."
            else:
                return "One or more quiz answers are wrong."

    def vars_for_template(self):
        solution_pairs = [
            dict(name=field, value=solution)
            for field, solution in zip(quiz.quiz_field_names, quiz.quiz_solutions)
        ]
        return {
            'quiz_solutions_json': json.dumps(solution_pairs)
        }  

    def app_after_this_page(player, app_sequence):
        if player.redoinstructions ==0:
            return app_sequence[0]
        
page_sequence = [instructing, prequiz, quiz]

