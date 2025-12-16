from otree.api import *
import random

# Take NUM_ROUNDS from session defaults (static at import time for oTree).
from settings import SESSION_CONFIG_DEFAULTS
_DEFAULT_NUM_ROUNDS = SESSION_CONFIG_DEFAULTS['num_experimental_rounds']

doc = """
tasks
"""
manager = None
task_manager = None

class C(BaseConstants):
    NAME_IN_URL = 'main'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = _DEFAULT_NUM_ROUNDS


class Subsession(BaseSubsession):
    pass
    
class Group(BaseGroup):
    pass

class Player(BasePlayer):
    pass

# FUNCTIONS 

# PAGES   
# Group matching helpers (previously RoundStartWaitPage) are now located in main/group_matching.py.
# class RoundStartWaitPage(WaitPage):
#     # Example group matching code is provided in main/group_matching.py
#     pass

class GameStart(Page):
    template_name = 'main/game.html'

    def vars_for_template(self):
        return {
            'round_count': self.round_number,
        }

    def before_next_page(player, timeout_happened):
        # Generate a payoff for this round before showing the payoff page
        player.payoff = random.randint(1, 100)

class payoff(Page):
    template_name = 'main/payoff.html'

    def vars_for_template(self):
        return {
            'payoff': cu(self.payoff),
            'round_count': self.round_number,
        }

class PayoffSummary(WaitPage):
    @staticmethod
    def is_displayed(player):
        return player.round_number == C.NUM_ROUNDS

    wait_for_all_groups = True

    @staticmethod
    def after_all_players_arrive(subsession):
        for p in subsession.get_players():
            # Calculate the payoff vector for this participant across all rounds in this app
            payoff_vector = [pr.payoff for pr in p.in_all_rounds()]
            # Initialize participant payoff_vector if needed
            if not hasattr(p.participant, 'payoff_vector') or p.participant.payoff_vector is None:
                p.participant.payoff_vector = []
            # Extend the single payoff_vector with these payoffs
            p.participant.payoff_vector.extend(payoff_vector)

page_sequence = [GameStart, payoff, PayoffSummary]
