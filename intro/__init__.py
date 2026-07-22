from otree.api import *
from otree import settings as otree_settings
import json
from .quiz_items import QUIZ_ITEMS

doc = """
Intro
"""
class C(BaseConstants):
    NAME_IN_URL = 'Introduction'
    # Stag Hunt example is a 2-player game.
    PLAYERS_PER_GROUP = 2
    NUM_ROUNDS = 2
    # Fixed Stag Hunt payoffs (constants, not treatment-varied).
    STAG_PAYOFF = 4
    HARE_PAYOFF = 2
    STAG_ALONE = 0



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
    template_name = 'intro/templates/instructing.html'
    form_model = 'player'
    form_fields = ['redoinstructions']

    def vars_for_template(player):
        # Stag Hunt example: surface every variable referenced in
        # intro/instructions_text.html so the template ships as a working
        # demonstration of variable substitution and treatment-conditional
        # content. Replace this when you swap in your own instructions.
        cfg = player.session.config
        return {
            'showup': cfg.get('showup'),
            'quiz_bonus': cfg.get('quiz_bonus'),
            'num_experimental_rounds': cfg.get('num_experimental_rounds'),
            'treatment': getattr(player.participant, 'treatment_group', ''),
            'stag_payoff': C.STAG_PAYOFF,
            'hare_payoff': C.HARE_PAYOFF,
            'stag_alone': C.STAG_ALONE,
            # Testing-only skip button; False whenever OTREE_PRODUCTION is set.
            'is_debug': otree_settings.DEBUG,
        }

class quiz(Page):
    template_name = 'intro/templates/quiz.html'
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
        if not player.session.config.get('verify_quiz', True):
            return
        # A participant asking to re-read the instructions is not submitting
        # answers, so don't validate them (the solutions are not available in
        # the browser outside DEBUG, so they cannot be auto-filled there).
        if values.get('redoinstructions'):
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
        # Solutions reach the browser only under settings.DEBUG (i.e. when
        # OTREE_PRODUCTION is unset), where they power the testing skip
        # button. In production nothing is sent.
        is_debug = otree_settings.DEBUG
        solution_pairs = []
        if is_debug:
            solution_pairs = [
                dict(name=field, value=solution)
                for field, solution in zip(quiz.quiz_field_names, quiz.quiz_solutions)
            ]
        return {
            'quiz_solutions_json': json.dumps(solution_pairs),
            'is_debug': is_debug,
        }

    def app_after_this_page(player, app_sequence):
        if player.redoinstructions ==0:
            return app_sequence[0]
        
page_sequence = [instructing, quiz]

