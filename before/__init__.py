from main import *
class C(BaseConstants):
    NAME_IN_URL = 'before'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    
class Subsession(BaseSubsession):
    pass

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    participant_label = models.StringField()

    def set_participant_label(self):
        self.participant_label = self.participant.label

# FUNCTIONS 

# PAGES
class startpage(Page):
    pass

class welcome(Page):
    # Initialise participant variables    
    def before_next_page(player, timeout_happened):
        if player.round_number == 1:
            player.participant.failed_attempts = 0
            player.participant.payoff_vector = []
        return


page_sequence = [startpage,welcome]