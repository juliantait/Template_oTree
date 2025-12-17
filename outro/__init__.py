from otree.api import *
import numbers, json
from .payment_rule import select_random_payouts

doc = """
Outro.
"""
class C(BaseConstants):
    NAME_IN_URL = 'outro'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

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
    payouts = models.LongStringField(blank=True)
    all_round_payoffs = models.LongStringField(blank=True)
    quiz_bonus_awarded = models.FloatField(initial=0)
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

# Function to extract round payoffs from a list of payoffs as ordered tuples (round_number, payoff)
def extract_round_payoffs(payoffs_vector, missing_values):
    """Return ordered (round_number, payoff) tuples, skipping missing sentinels."""
    if isinstance(payoffs_vector, (list, tuple)):
        raw = list(payoffs_vector)
    else:
        # attempt to flatten arbitrarily nested structures into numbers
        raw = []
        stack = [payoffs_vector]
        while stack:
            current = stack.pop()
            if isinstance(current, numbers.Number):
                raw.append(current)
            elif isinstance(current, str):
                try:
                    raw.append(float(current))
                except Exception:
                    pass
            elif isinstance(current, (list, tuple)):
                stack.extend(current)
            elif isinstance(current, dict):
                stack.extend(current.values())

    round_payoffs = []
    for idx, value in enumerate(raw):
        if isinstance(value, numbers.Number) and value not in missing_values:
            round_payoffs.append((idx + 1, float(value)))
    return round_payoffs

# PAGES
    
class Demographics(Page):
    form_model = 'player'
    form_fields = ['age', 'gender','bank','bank_confirmation','bic']

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
        if missing_fields:
            return "Please answer all questions with an asterix (*)."
        if values['bank'] != values['bank_confirmation']:
            return "Your bank numbers don't match. Please doublecheck them."

    def before_next_page(p, timeout_happened):
        # CHECK IF THE PARTICIPANT'S BANK ACCOUNT IS IN SEPA ======================================
        check_sepa_code(p)

        # DETERMINE EXPERIMENTAL PAYOFF ========================================================
        # List of values that indicate missing payoff values in the participant's payoff vector. Edit this list if you are using different codes for "no payoff" in your data.
        missing_payoff_values = [
            -333, 
            -111, 
            -999]
        # Extract RANDOM selected payoffs from the participant's payoff vector as ordered tuples (round_number, payoff)
        payoffs_vector = getattr(p.participant, 'payoff_vector', [])
        round_payoffs = extract_round_payoffs(payoffs_vector, missing_payoff_values)
        num_rewarded = p.session.config['num_rewarded']
        payouts = select_random_payouts(round_payoffs, num_rewarded)

        # Calculate the experiment payoff from i) the selected payoffs, ii) the quiz bonus and iii) the showup fee
        p.selected_sum = sum(float(pay) for _, pay in payouts)
        # Quiz bonus awarded only if no failed attempts and quiz_bonus is positive
        try:
            participant_failed_attempts = p.participant.failed_attempts
        except KeyError:
            participant_failed_attempts = 0
        quiz_bonus = p.session.config['quiz_bonus']
        quiz_bonus_awarded = quiz_bonus if (participant_failed_attempts == 0 and quiz_bonus > 0) else 0
        p.quiz_bonus_awarded = quiz_bonus_awarded
        showup_fee = p.session.config['showup']
        p.earned = showup_fee + p.selected_sum + p.quiz_bonus_awarded
        p.payouts = json.dumps(payouts)
        p.all_round_payoffs = json.dumps(round_payoffs)

class Results(Page):
    def vars_for_template(self):
        # Convert the selected payoffs to a JSON string to view as table in Results.html
        try:
            payouts = json.loads(self.payouts) if self.payouts else []
        except Exception:
            payouts = []
        try:
            round_payoffs = json.loads(self.all_round_payoffs) if self.all_round_payoffs else []
        except Exception:
            round_payoffs = []
        selected_round_numbers = {int(r) for r, _ in payouts}
        payout_rows = [
            {
                'round': int(round_no),
                'payoff': cu(payoff),
                'selected': int(round_no) in selected_round_numbers,
            }
            for round_no, payoff in round_payoffs
        ]
        return{
            'earned': cu(self.earned),
            'showup': cu(self.session.config['showup']),
            'selected_sum': cu(self.selected_sum),
            'quiz_bonus': cu(self.quiz_bonus_awarded),
            'show_quiz_bonus': self.quiz_bonus_awarded > 0,
            'sepa': self.sepa,
            'payouts': payouts,
            'payout_rows': payout_rows,
        }

page_sequence = [Demographics, Results]