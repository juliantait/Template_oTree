from main1 import *
import itertools
class C(BaseConstants):
    NAME_IN_URL = 'before'
    PLAYERS_PER_GROUP = 3
    NUM_ROUNDS = 1
    
class Subsession(BaseSubsession):
    pass

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    participant_label = models.StringField()
    redoinstructions = models.BooleanField()

    def set_participant_label(self):
        self.participant_label = self.participant.label

# FUNCTIONS 

# PAGES
class startpage(Page):
    pass

class welcome(Page):
    def before_next_page(player, timeout_happened):
        pass

page_sequence = [startpage,welcome]