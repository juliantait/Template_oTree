from otree.api import *
from otree import settings as otree_settings
import json
import common
from .quiz_items import QUIZ_ITEMS

doc = """
Intro
"""
class C(BaseConstants):
    NAME_IN_URL = 'Introduction'
    # Instructions + quiz are individual and shown once; no grouping.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    # Example figures referenced by intro/instructions_text.html to demonstrate
    # variable substitution. Replace with your own study's numbers.
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
        'participant_label': models.StringField(blank=True),
        'redoinstructions': models.BooleanField(initial=0, blank=True),
        'skiptoquiz': models.BooleanField(initial=0, blank=True),
        'num_failed_attempts': models.IntegerField(initial=0),
        # Spare columns (future-proofing) — never rename in place; see CODEBOOK.md.
        'spare_str_1': models.LongStringField(blank=True),
        'spare_str_2': models.LongStringField(blank=True),
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
            # Read participant vars with .vars.get(), never getattr() (KeyError trap).
            'treatment': player.participant.vars.get('treatment_group', ''),
            'stag_payoff': C.STAG_PAYOFF,
            'hare_payoff': C.HARE_PAYOFF,
            'stag_alone': C.STAG_ALONE,
            # Testing-only skip button; False whenever OTREE_PRODUCTION is set.
            'is_debug': otree_settings.DEBUG,
        }

    def before_next_page(player, timeout_happened):
        common.stamp_stage(player.participant, 'instructions_done')

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
            cfg = player.session.config
            # COMPREHENSION-FAILURE DISQUALIFICATION (module, off by default).
            # When enabled, a participant who fails too many times is not blocked
            # again — they are flagged and allowed through to the disqualified
            # ending (see app_after_this_page and the outro Disqualified page).
            if cfg.get('comprehension_dq'):
                max_fail = int(cfg.get('comprehension_max_failures', 2))
                if player.participant.failed_attempts >= max_fail:
                    player.participant.comprehension_disqualified = True
                    common.set_exit_code(
                        player.participant, common.EXIT_CODES['comprehension'])
                    return  # no error -> the page advances to the ending
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

    def before_next_page(player, timeout_happened):
        common.stamp_stage(player.participant, 'quiz_done')

    def app_after_this_page(player, upcoming_apps):
        # Route a comprehension-disqualified participant straight to the ending
        # app, skipping the task entirely.
        if player.participant.vars.get('comprehension_disqualified'):
            return upcoming_apps[-1]


class AISafetyAgree(Page):
    """Arms the tab-switch monitor. Shown only when tab_monitor is on.

    On submit the template sets sessionStorage.aiSafetyAgreed = '1'; the monitor
    JS stays dormant until then, so this page marks exactly where monitoring
    begins.
    """
    template_name = 'intro/templates/ai_safety.html'

    @staticmethod
    def is_displayed(player):
        return bool(player.session.config.get('tab_monitor'))


page_sequence = [instructing, quiz, AISafetyAgree]

