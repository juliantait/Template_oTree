from otree.api import *
import numbers, json
import common
from settings import STATIC_VERSION
from .payment_rule import select_random_payouts

PROLIFIC_COMPLETE_URL = "https://app.prolific.com/submissions/complete?cc="


# One implementation, in common.flag (raw config.get — see its docstring for
# why it is NOT common.cfg).
_flag = common.flag


def is_lab(player) -> bool:
    """True in an experimenter-run session.

    Used ONLY for copy that is meaningless outside a physical lab — "stay
    seated" on the results page, "raise your hand" on the early-exit page. Read
    through common.cfg so a session config frozen before `recruitment` existed
    still renders.

    KEEP THIS LIST SHORT. Divergence between the lab and Prolific variants is a
    cost paid on every future change, so a branch has to earn its place: it is
    for things that cannot be true in both rooms, not for things that merely
    read differently. See the note on completion in Results.vars_for_template.
    """
    return common.cfg(player.session.config, 'recruitment') == 'lab'


def is_disqualified(player) -> bool:
    """True if the participant was removed by an integrity module."""
    v = player.participant.vars
    return bool(v.get('comprehension_disqualified') or v.get('ai_safety_disqualified'))


def declined_consent(player) -> bool:
    return player.participant.vars.get('exit_code') == common.EXIT_CODES['no_consent']


def was_screened_out(player) -> bool:
    """True for a participant the entry device gate removed (exit code -4).

    UNREACHABLE BY DESIGN in this template, and kept deliberately. The device
    gate HOLDS a screened-out participant on the entry page
    (`before.welcome`), where the screen-out is re-decidable, so they never
    advance into the outro at all. This is the belt to that brace: it keeps such
    a participant out of `is_completer` — no payment page, no completion code —
    if any future gate sets the flag later in the flow.
    """
    return common.is_screened_out(player.participant)


def is_completer(player) -> bool:
    """A participant who should walk the normal ending (task + payment)."""
    return not (is_disqualified(player) or declined_consent(player)
                or was_screened_out(player))


def completion_link(player) -> str:
    """Build the Prolific completion URL for this participant's outcome.

    THERE IS NO SCREENED-OUT BRANCH, and there must not be one: a screened-out
    participant gets a CODELESS link back to Prolific (see
    `common.screenout_return_url`), because a completion code closes their
    submission and a returned submission can never be retaken. `Ended` renders
    that link instead of this one for them.
    """
    cfg = player.session.config
    if is_disqualified(player):
        code = cfg.get('dq_code')
    elif declined_consent(player):
        code = cfg.get('noconsent_code')
    else:
        code = cfg.get('cc_code')
    return PROLIFIC_COMPLETE_URL + str(code)

doc = """
Outro.
"""
class C(BaseConstants):
    # Asset cache-buster for this BUILD (settings.STATIC_VERSION).
    # Templates read C.STATIC_VERSION, never session.config.static_version:
    # a session config is frozen at creation, so the template read 500s
    # for in-flight participants when the parameter post-dates them.
    STATIC_VERSION = STATIC_VERSION
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
# SEPA two-letter country codes (for flagging non-SEPA IBANs on the lab
# payment form).
SEPA_COUNTRY_CODES = frozenset([
    "FI", "AT", "PT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FR", "DE", "GI", "GR", "HU",
    "IS", "IE", "IT", "LV", "LI", "LT", "LU", "MT", "MC", "NL", "NO", "PL", "RO", "SK", "SI",
    "ES", "SE", "CH", "GB"
])


def check_sepa_code(player):
    # The IBAN's first two characters are its country code; flag a bank account
    # outside the SEPA area so payment knows a transfer may not work.
    bank_country_code = player.bank[:2].upper()
    player.sepa = 1 if bank_country_code in SEPA_COUNTRY_CODES else 0

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
    stopped by the allowed_devices gate lands here as its FIRST page — it never
    saw consent). When completion redirects are on it sends them back to
    Prolific with the matching code.
    """
    template_name = 'outro/Ended.html'

    @staticmethod
    def is_displayed(player):
        return not is_completer(player)

    # NO js_vars. The completion URL is a TEMPLATE var (below) because the
    # button is a real link: a participant whose JavaScript never ran must still
    # be able to leave. Passing it to the browser as a js_var that nothing reads
    # would be dead weight — and it is what made the scripted button look
    # necessary in the first place.

    @staticmethod
    def vars_for_template(player):
        return dict(
            completionlink=completion_link(player),
            reason=('disqualified' if is_disqualified(player)
                    else 'no_consent' if declined_consent(player)
                    else 'screened_out' if was_screened_out(player) else 'other'),
            # WHICH DEVICE TYPE the entry gate detected ('phone' / 'tablet' /
            # 'computer' / 'unknown'), or '' if a study set exit code -4 without
            # recording a cause. `reason` alone is too coarse to write copy
            # from: -4 is the general screened-out bucket, so the template picks
            # its sentence from this — the participant is told something true
            # about their own case instead of everyone being told the study
            # needs a computer. `allowed_devices_phrase` says what the study DOES
            # accept, built from the same list the gate enforces so the two
            # cannot drift apart. (There is no 'laptop' type and cannot be one —
            # see the allow-list note in settings.py.)
            screenout_cause=common.screenout_cause(player.participant),
            allowed_devices_phrase=common.device_types_phrase(
                common.allowed_devices(player.session.config)),
            # A screened-out participant is returned to Prolific WITHOUT a
            # completion code (see completion_link). Only relevant on the
            # unreachable-by-design fallback path — the entry gate holds such a
            # participant on before.welcome and they never get here.
            screenout_return_url=common.screenout_return_url(player.session.config),
            # Lab-only closing line ("raise your hand"); see is_lab().
            is_lab=is_lab(player),
            # WHICH integrity module removed them (change_requests item 16).
            # `reason='disqualified'` is the bucket; this is the cause, and the
            # template writes a different sentence for each so the participant
            # is told WHY the study ended instead of "cannot continue".
            # If somehow both flags are set the tab monitor wins the message: it
            # is the harder stop, and it is the one the participant was warned
            # about on screen.
            dq_cause=(
                'tab_monitor'
                if player.participant.vars.get('ai_safety_disqualified')
                else 'comprehension'
                if player.participant.vars.get('comprehension_disqualified')
                else ''),
            completion_redirects=_flag(player, 'completion_redirects'),
        )


class Demographics(Page):
    form_model = 'player'
    # KEEP THE ANSWERS ON A VALIDATION ERROR (change_requests item 10). oTree
    # implements this client-side: it stores each named input in sessionStorage
    # as it is typed and restores it on the next render of the same page, so a
    # participant who trips one error (a mistyped IBAN confirmation) does not
    # have to retype everything else. It therefore needs the inputs to be real
    # named form inputs — which is why Demographics.html renders them all with
    # {% formfield %} — and, being JS, it degrades quietly if scripts are
    # blocked: the page still validates and still submits, the boxes are just
    # empty again.
    preserve_unsubmitted_inputs = True

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
    # common.cfg, never []-indexing: a session created before a parameter
    # existed does not carry it, and a KeyError here is a 500 on the payment
    # page — the worst possible place (CLAUDE.md).
    num_rewarded = common.cfg(p.session.config, 'num_rewarded')
    payouts = select_random_payouts(round_payoffs, num_rewarded)

    # Calculate the experiment payoff from i) the selected payoffs, ii) the quiz bonus and iii) the showup fee
    p.selected_sum = sum(float(pay) for _, pay in payouts)
    # Quiz bonus awarded only if no failed attempts and quiz_bonus is positive
    # (.vars.get() rather than getattr()/attribute access — KeyError trap.)
    participant_failed_attempts = p.participant.vars.get('failed_attempts', 0) or 0
    quiz_bonus = common.cfg(p.session.config, 'quiz_bonus')
    quiz_bonus_awarded = quiz_bonus if (participant_failed_attempts == 0 and quiz_bonus > 0) else 0
    p.quiz_bonus_awarded = quiz_bonus_awarded
    showup_fee = common.cfg(p.session.config, 'showup')
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

    # NO js_vars here either — same reason as on Ended: the completion redirect
    # is a real link built server-side (so the code is authoritative) and
    # rendered into the page, not handed to a script that has to run first.

    def vars_for_template(self):
        # REACHING THIS PAGE IS COMPLETION: the exit code becomes `finished`
        # when the page LOADS — identically in the lab and on Prolific.
        # Idempotent, so re-rendering never corrupts it.
        #
        # IT IS DELIBERATELY *NOT* TIED TO THE "Back to Prolific" CLICK (Julian,
        # 2026-08-12, reversing an earlier request). Moving it there would make
        # completion mean one thing online and another in the lab — and the
        # principle behind the reversal is worth more than the detail:
        # DIVERGENCES BETWEEN THE LAB AND PROLIFIC VARIANTS ARE MINIMISED, AND
        # KEPT ONLY WHERE GENUINELY ESSENTIAL. Every one of them is a thing that
        # can be true in one variant and quietly wrong in the other, forever.
        # A participant who closes the tab without clicking the button has still
        # finished the study; the completion CODE is what Prolific needs from
        # the click, and that is a separate concern from the exit code.
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
        # THE BREAKDOWN IS REAL MONEY, not decoration (change_requests item 11).
        # Every line of the receipt on Results.html is one of these figures, and
        # they must add up to `earned` exactly as compute_final_payoff computed
        # it: base (the show-up fee) + quiz bonus + the selected rounds.
        # `base_payment` is the show-up fee under the name the receipt uses;
        # `decision_bonus` is the sum of the randomly selected rounds.
        showup_fee = cu(common.cfg(self.session.config, 'showup'))
        selected_sum = cu(self.selected_sum)
        return{
            # The completion URL, rendered into the page's own link. EVERY
            # Prolific completer leaves through it, so it must not need a script
            # to exist: a completer with JS blocked would otherwise finish the
            # study, see this page, and have no way to submit their completion
            # code — unpaid, and looking like an abandoner in the data.
            'completionlink': completion_link(self),
            'earned': cu(self.earned),
            'showup': showup_fee,
            'base_payment': showup_fee,
            'selected_sum': selected_sum,
            'decision_bonus': selected_sum,
            'quiz_bonus': cu(self.quiz_bonus_awarded),
            'show_quiz_bonus': self.quiz_bonus_awarded > 0,
            'has_rounds': bool(payout_rows),
            'sepa': self.sepa,
            'payouts': payouts,
            'payout_rows': payout_rows,
            'num_rewarded': common.cfg(self.session.config, 'num_rewarded'),
            # Lab-only closing line ("stay seated"); see is_lab().
            'is_lab': is_lab(self),
            'completion_redirects': bool(self.session.config.get('completion_redirects')),
        }

page_sequence = [Ended, Demographics, Feedback, Results]