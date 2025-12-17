from otree.api import *
import random

# Take NUM_ROUNDS from session defaults (static at import time for oTree).
from settings import SESSION_CONFIG_DEFAULTS
num_experimental_rounds = SESSION_CONFIG_DEFAULTS['num_experimental_rounds']

doc = """
tasks
"""
manager = None
task_manager = None

class C(BaseConstants):
    NAME_IN_URL = 'main'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = num_experimental_rounds


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

# INSERT YOUR GAME PAGES HERE

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

    @staticmethod
    def before_next_page(player, timeout_happened):
        # On the final round, collect all payoffs into the participant vector.
        if player.round_number == C.NUM_ROUNDS:
            payoff_vector = [pr.payoff for pr in player.in_all_rounds()]
            if not hasattr(player.participant, 'payoff_vector') or player.participant.payoff_vector is None:
                player.participant.payoff_vector = []
            player.participant.payoff_vector.extend(payoff_vector)

page_sequence = [GameStart, payoff]
