# Models
from otree.api import *
import random
doc = """
Outro.
"""
class C(BaseConstants):
    NAME_IN_URL = 'outro'
    PLAYERS_PER_GROUP = 3
    NUM_ROUNDS = 1
    #TIMERS
    timer = 1.5
    #FINANCES
    players = 100
    prob = 0.8
    x_low = 10
    x_high = 20
    y = 4
    bonus = 1.00
    showup = 5
    punish_max = 2
    fail = 2
    numrewarded = 2
    quizbonus = 1



class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass

class Player(BasePlayer):
    bank = models.StringField(blank=True)
    bank_confirmation = models.StringField(blank=True)
    age = models.IntegerField(
        min=16,
        max=110,
        blank=True
    )
    gender = models.StringField(
        widget=widgets.RadioSelect,
        choices=['Male', 'Female', 'Other', 'Prefer not to say'], blank=True)
    bic = models.StringField(blank=True)
    selected_round1 = models.IntegerField()
    selected_round2 = models.IntegerField()
    pay1 = models.FloatField()
    pay2 = models.FloatField()
    selected_sum = models.FloatField()
    earned = models.FloatField()
    other = models.StringField(blank=True)  # Field to store the custom input for 'Other'
    completed = models.BooleanField(initial=False)
    sepa = models.IntegerField(initial=1)

# FUNCTIONS
# Function to check SEPA code
def check_sepa_code(self):
    # List of SEPA two-letter country codes
    sepa_country_codes = [
        "FI", "AT", "PT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FR", "DE", "GI", "GR", "HU", 
        "IS", "IE", "IT", "LV", "LI", "LT", "LU", "MT", "MC", "NL", "NO", "PL", "RO", "SK", "SI", 
        "ES", "SE", "CH", "GB"
    ]
    
    # Extract the first two characters from the player's bank field
    bank_country_code = self.bank[:2].upper()  # Get the first two characters, uppercase them
    
    # Check if the extracted code is in the SEPA list
    if bank_country_code not in sepa_country_codes:
        self.sepa = 0  # Set sepa to 0 if not in SEPA country list
    else:
        self.sepa = 1  # Set sepa to 1 if in SEPA country list


# PAGES
    
class Demographics(Page):
    form_model = 'player'
    form_fields = ['age', 'gender','bank','bank_confirmation', 'other','bic']
    def error_message(player, values):
        missing_fields = []
        if not values['gender']:
            missing_fields.append('gender')
        if not values['bank']:
            missing_fields.append('bank')
        if not values['bank_confirmation']:
            missing_fields.append('bank_confirmation')
        if not values['age']:
            missing_fields.append('age')
        # If any fields are missing, return the custom error message
        if missing_fields:
            return "Please answer all questions with an asterix (*)."
        if values['bank'] != values['bank_confirmation']:
            return "Your bank numbers don't match. Please doublecheck them."
            # Check if any of the required fields are missing or unanswered

    def before_next_page(p,timeout_happened):        
        # Get the value of the selected payoff attribute    
        # Calculate the total earnings
        payoff_vectors = [p.participant.payoff_r1,p.participant.payoff_r2, p.participant.payoff_r3,p.participant.payoff_r4]  # Add more vectors as needed
        # Initialize an empty list to hold the extracted numeric values
        extracted_values = []
        # Iterate over each item in the payoff_vectors list
        # Iterate over each item in the payoff_vectors list
        for item in payoff_vectors:
            if isinstance(item, list):
                # If the item is a list, iterate through each element in the list
                for sub_item in item:
                    # If sub_item is a string with 'cu', remove 'cu' and convert to float
                    if isinstance(sub_item, str) and 'cu' in sub_item:
                        cleaned_value = float(sub_item.replace('cu', ''))
                    else:
                        # If sub_item is already a number, use it directly
                        cleaned_value = float(sub_item)  # Convert to float to ensure consistency
                    extracted_values.append(cleaned_value)
            else:
                # If the item is already a number, append it directly
                extracted_values.append(float(item))  # Convert to float to ensure consistency
        round1, round2 = random.sample(range(len(extracted_values)), 2)  # Select 2 random rounds
        pay1 = extracted_values[round1]  # Pay from first selected round
        pay2 = extracted_values[round2]  # Pay from second selected round
        selected_sum = pay1 + pay2

        # Update participant earnings
        p.participant.earned = C.showup + selected_sum + p.participant.quiz_beast
        p.earned = p.participant.earned
        p.payoff = p.earned

        # Store the values at the player level to use them later in the template
        p.selected_round1 = round1 + 1  # Human-readable round number
        p.selected_round2 = round2 + 1
        p.pay1 = pay1
        p.pay2 = pay2
        p.selected_sum = selected_sum
        p.completed = 1
        check_sepa_code(p)

class Results(Page):
    def vars_for_template(self):
        return{
            'bonus': cu(C.bonus),
            'earned': cu(self.participant.earned),
            'numrewarded': C.numrewarded,
            'showup': cu(C.showup),
            'pay1': cu(self.pay1),
            'pay2': cu(self.pay2),
            'selected_round2' :  self.selected_round2,
            'selected_round1' :  self.selected_round1,
            'selected_sum': cu(self.selected_sum),
            'quiz_beast': self.participant.quiz_beast,
            'quizbonus': cu(C.quizbonus),
        }


page_sequence = [Demographics, Results]