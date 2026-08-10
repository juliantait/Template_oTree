from otree.api import *
import numbers, json
import common
from .payment_rule import select_random_payouts

PROLIFIC_COMPLETE_URL = "https://app.prolific.com/submissions/complete?cc="


def _flag(player, name):
    return bool(player.session.config.get(name))


def is_disqualified(player) -> bool:
    """True if the participant was removed by an integrity module."""
    v = player.participant.vars
    return bool(v.get('comprehension_disqualified') or v.get('ai_safety_disqualified'))


def declined_consent(player) -> bool:
    return player.participant.vars.get('exit_code') == common.EXIT_CODES['no_consent']


def was_screened_out(player) -> bool:
    """True for a participant the entry mobile screen-out removed (exit code -4)."""
    return common.is_screened_out(player.participant)


def is_completer(player) -> bool:
    """A participant who should walk the normal ending (task + payment)."""
    return not (is_disqualified(player) or declined_consent(player)
                or was_screened_out(player))


def completion_link(player) -> str:
    """Build the Prolific completion URL for this participant's outcome."""
    cfg = player.session.config
    if is_disqualified(player):
        code = cfg.get('dq_code')
    elif declined_consent(player):
        code = cfg.get('noconsent_code')
    elif was_screened_out(player):
        code = cfg.get('error_code')
    else:
        code = cfg.get('cc_code')
    return PROLIFIC_COMPLETE_URL + str(code)

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
    # Free-text pilot feedback; collected only when pilot_feedback is on.
    feedback = models.LongStringField(blank=True)
    # Spare columns (future-proofing) — never rename in place; see CODEBOOK.md.
    spare_str_1 = models.LongStringField(blank=True)
    spare_str_2 = models.LongStringField(blank=True)

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

class Ended(Page):
    """Finish screen for participants who did NOT complete normally.

    Shown to disqualified, non-consenting and screened-out participants (a phone
    stopped by the mobile_screenout gate lands here as its FIRST page — it never
    saw consent). When completion redirects are on it sends them back to
    Prolific with the matching code.
    """
    template_name = 'outro/Ended.html'

    @staticmethod
    def is_displayed(player):
        return not is_completer(player)

    @staticmethod
    def js_vars(player):
        return dict(completionlink=completion_link(player))

    @staticmethod
    def vars_for_template(player):
        return dict(
            reason=('disqualified' if is_disqualified(player)
                    else 'no_consent' if declined_consent(player)
                    else 'screened_out' if was_screened_out(player) else 'other'),
            completion_redirects=_flag(player, 'completion_redirects'),
        )


class Demographics(Page):
    form_model = 'player'

    @staticmethod
    def is_displayed(player):
        # Lab collects demographics and bank details here; Prolific collects
        # neither (Prolific supplies demographics with its own export), so with
        # both flags off the page is skipped entirely.
        return is_completer(player) and (
            _flag(player, 'collect_demographics') or _flag(player, 'collect_bank_details'))

    @staticmethod
    def get_form_fields(player):
        fields = []
        if _flag(player, 'collect_demographics'):
            fields += ['age', 'gender']
        # Bank / SEPA collection is the lab payment model; Prolific pays through
        # the platform, so these fields only appear when collect_bank_details is on.
        if _flag(player, 'collect_bank_details'):
            fields += ['bank', 'bank_confirmation', 'bic']
        return fields

    @staticmethod
    def vars_for_template(player):
        return dict(
            collect_demographics=_flag(player, 'collect_demographics'),
            collect_bank_details=_flag(player, 'collect_bank_details'),
        )

    def error_message(player, values):
        missing_fields = []
        if player.session.config.get('collect_demographics'):
            if not values.get('gender'):
                missing_fields.append('gender')
            if not values.get('age'):
                missing_fields.append('age')
        if player.session.config.get('collect_bank_details'):
            if not values.get('bank'):
                missing_fields.append('bank')
            if not values.get('bank_confirmation'):
                missing_fields.append('bank_confirmation')
            if missing_fields:
                return "Please answer all questions with an asterisk (*)."
            if values['bank'] != values['bank_confirmation']:
                return "Your bank numbers don't match. Please doublecheck them."
        if missing_fields:
            return "Please answer all questions with an asterisk (*)."

    def before_next_page(p, timeout_happened):
        # CHECK IF THE PARTICIPANT'S BANK ACCOUNT IS IN SEPA (lab payment only) ===
        if p.session.config.get('collect_bank_details') and p.bank:
            check_sepa_code(p)


def compute_final_payoff(p):
    """Determine the experimental payoff. Idempotent, and independent of the
    demographics/bank page (which is skipped entirely for Prolific), so it runs
    when the participant reaches Results — the one page every completer sees.
    """
    if p.field_maybe_none('earned') is not None:
        return  # already computed (e.g. Results re-rendered)

    # List of values that indicate missing payoff values in the participant's payoff vector. Edit this list if you are using different codes for "no payoff" in your data.
    missing_payoff_values = [
        -333,
        -111,
        -999]
    # Extract RANDOM selected payoffs from the participant's payoff vector as ordered tuples (round_number, payoff)
    # Read participant vars with .vars.get(), never getattr() (KeyError trap; see conventions.md).
    payoffs_vector = p.participant.vars.get('payoff_vector', []) or []
    round_payoffs = extract_round_payoffs(payoffs_vector, missing_payoff_values)
    num_rewarded = p.session.config['num_rewarded']
    payouts = select_random_payouts(round_payoffs, num_rewarded)

    # Calculate the experiment payoff from i) the selected payoffs, ii) the quiz bonus and iii) the showup fee
    p.selected_sum = sum(float(pay) for _, pay in payouts)
    # Quiz bonus awarded only if no failed attempts and quiz_bonus is positive
    # (.vars.get() rather than getattr()/attribute access — KeyError trap.)
    participant_failed_attempts = p.participant.vars.get('failed_attempts', 0) or 0
    quiz_bonus = p.session.config['quiz_bonus']
    quiz_bonus_awarded = quiz_bonus if (participant_failed_attempts == 0 and quiz_bonus > 0) else 0
    p.quiz_bonus_awarded = quiz_bonus_awarded
    showup_fee = p.session.config['showup']
    p.earned = showup_fee + p.selected_sum + p.quiz_bonus_awarded
    p.payouts = json.dumps(payouts)
    p.all_round_payoffs = json.dumps(round_payoffs)


class Feedback(Page):
    """Free-text pilot feedback (pilot_feedback axis).

    Shown to completers when the pilot_feedback flag is on — a pilot or friend
    test — regardless of study type or DEBUG. Placed BEFORE Results so Prolific
    completers see it before the completion redirect. The answer is optional
    (blank=True) and is never re-rendered to any participant.
    """
    template_name = 'outro/Feedback.html'
    form_model = 'player'
    form_fields = ['feedback']

    @staticmethod
    def is_displayed(player):
        return is_completer(player) and _flag(player, 'pilot_feedback')


class Results(Page):

    @staticmethod
    def is_displayed(player):
        return is_completer(player)

    @staticmethod
    def js_vars(player):
        # Completion redirect (Prolific): the participant clicks a button that
        # sends them to this URL. Built server-side so the code is authoritative.
        return dict(completionlink=completion_link(player))

    def vars_for_template(self):
        # Reaching this page IS completion: record the clean outcome. Idempotent,
        # so re-rendering never corrupts it.
        compute_final_payoff(self)
        common.set_exit_code(self.participant, common.EXIT_CODES['finished'])
        common.stamp_stage(self.participant, 'finished')
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
            'num_rewarded': self.session.config['num_rewarded'],
            'completion_redirects': bool(self.session.config.get('completion_redirects')),
        }

page_sequence = [Ended, Demographics, Feedback, Results]