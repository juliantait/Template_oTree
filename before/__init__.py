# This app consists of 2 pages:
# - startpage: welcome and wait screen before experimenter starts the experiment
# - welcome+consent: welcome message and consent form

from main import *
from . import treatment_assignment

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
    treatment_group = models.StringField(blank=True)


def creating_session(subsession: Subsession):
    # Delegate to the treatment assignment helper in this app
    return treatment_assignment.assign_treatments(subsession)

def set_participant_label(self):
    self.participant_label = self.participant.label
    return

# FUNCTIONS 

# PAGES
class startpage(Page):
    pass

class welcome(Page):
    template_name = 'before/welcome+consent.html'
    # Initialise participant variables    
    def before_next_page(player, timeout_happened):
        if player.round_number == 1:
            player.participant.failed_attempts = 0
            player.participant.payoff_vector = []
            # Copy the pre-assigned treatment from the participant to the player for display/testing.
            player.treatment_group = getattr(player.participant, 'treatment_group', '')
        return


page_sequence = [startpage,welcome]