from otree.api import *
import numbers, json
import common
import participant_tab_monitor
from settings import INSTITUTION_NAME, STATIC_VERSION
from .payment_rule import select_random_payouts

PROLIFIC_COMPLETE_URL = "https://app.prolific.com/submissions/complete?cc="

# =============================================================================
# THE TAB MONITOR IN THIS APP: SAME COUNTING, DIFFERENT CONSEQUENCE (Julian,
# 2026-08-13). Every page below is monitored
# (participant_tab_monitor.OutroMonitoredPage) — but a violation here is RECORDED
# ONLY, in its own column
# (tab_monitor_focus_loss_count_outro), and NEVER disqualifies. That is not drift from the
# intro/main behaviour; it is the point: by this app the task is over and the
# data is already collected, so ejecting somebody who has completed the whole
# study — for tabbing away while typing bank details, or to fetch their
# Prolific tab — would cost a real participant for no benefit. The client is
# told the same (ejects: false) and shows no overlay and no warning modal, so
# a completer is never threatened with a consequence that does not exist.
# Full reasoning at common._apply_focus_loss; analyst-facing note in
# CODEBOOK.md (a nonzero outro count on a finished row does NOT mean they
# came close to ejection).
# =============================================================================


# One implementation, in common.flag (raw config.get — see its docstring for
# why it is NOT common.cfg).
_flag = common.flag


def is_lab(player) -> bool:
    """True in an experimenter-run session.

    Used ONLY for copy that is meaningless outside a physical lab — "stay
    seated" on the results page, "raise your hand" on the early-exit page.

    A thin wrapper on `common.is_lab`, which is the ONE implementation (the
    question is asked in three apps and must not be decided by two different
    config accessors — see the study-type rule there, and note that COPY like
    this is exactly what `recruitment` is for, never a module flag).

    KEEP THIS LIST SHORT. Divergence between the lab and Prolific variants is a
    cost paid on every future change, so a branch has to earn its place: it is
    for things that cannot be true in both rooms, not for things that merely
    read differently. See the note on completion in Results.vars_for_template.
    """
    return common.is_lab(player.session.config)


def dq_cause(player) -> str:
    """THE FINE CAUSE, AND THE ONLY SOURCE FOR BOTH THE MESSAGE AND THE CODE.

    ==================================================================
    DO NOT let the displayed reason and the completion code come from
    two different reads. Both MUST derive from this function.
    ==================================================================
    Since the per-ending codes landed (2026-08-15) a disqualified participant
    has a code that identifies WHICH module removed them. If the sentence they
    read were derived independently of the code they carry back, the two could
    silently disagree — a comprehension failure reading the quiz explanation
    while submitting the TAB code. Nothing would error, the data would look
    normal, and the population split would be corrupted at exactly the point it
    exists to be made, discoverable only by hand-reconciling submissions.

    That failure mode COULD NOT EXIST while one shared DQ code served both
    populations: splitting the code is what created it, which is worth noticing
    — the hazard is ours, introduced the same afternoon as the fix it belongs
    to.

    Today both consumers call THIS function and nothing else:
      * the message — `Ended.vars_for_template` passes `dq_cause=dq_cause(player)`
        and `outro/Ended.html` branches on it;
      * the code    — `completion_link` does `cause = dq_cause(player)`.
    Two calls to one deterministic function on the same player in the same
    request cannot disagree. TWO IMPLEMENTATIONS COULD. So do not "tidy" either
    call into a separate flag read, a template conditional on
    `tab_monitor_disqualified` / `comprehension_disqualified`, or a second lookup.
    """
    """WHICH integrity module removed this participant ('' if none).

    The ONE cause cascade (change_requests item 16): the ending's sentence is
    written from this, never from the exit code. If somehow both flags are set
    the tab monitor wins the message: it is the harder stop, and it is the one
    the participant was warned about on screen.
    """
    v = player.participant.vars
    if v.get('tab_monitor_disqualified'):
        return 'tab_monitor'
    if v.get('comprehension_disqualified'):
        return 'comprehension'
    return ''


def is_disqualified(player) -> bool:
    """True if the participant was removed by an integrity module."""
    return bool(dq_cause(player))


def declined_consent(player) -> bool:
    """True for a participant who answered the consent question with "no".

    THE POST-WRITE READING of the same fact `before._declined_consent` decides.
    The two are deliberately in different currencies and neither can replace the
    other: `before` must answer on the consent page's OWN request, from the form
    field, before any exit code has been written; every later app can only see
    the durable record, which is the exit code. If you change how a declined
    consent is recorded, both move together.
    """
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


def ending_reason(player) -> str:
    """WHY this participant is on the early ending ('' for a completer).

    THE COARSE cascade — the BUCKET a participant is in. There is now a second,
    FINER one (`dq_cause`: comprehension vs tab_monitor), and the two are not
    independent: this function asks `is_disqualified`, which asks `dq_cause`, so
    the bucket and the cause come off the same tree and cannot contradict each
    other. `Ended.is_displayed` and the template vars both read THIS, so the page
    cannot show for one reason and speak for another; the same guarantee at the
    finer grain is stated on `dq_cause`, which is where the message and the
    completion code both come from.
    Order is deliberate and mirrors severity — an integrity removal outranks a
    declined consent, which outranks the (unreachable-by-design) screen-out.
    """
    if is_disqualified(player):
        return 'disqualified'
    if declined_consent(player):
        return 'no_consent'
    if was_screened_out(player):
        return 'screened_out'
    return ''


def is_completer(player) -> bool:
    """A participant who should walk the normal ending (task + payment)."""
    return not ending_reason(player)


def completion_link(player) -> str:
    """Build the Prolific completion URL for this participant's outcome.

    THERE IS NO SCREENED-OUT BRANCH, and there must not be one — but NOT for
    the reason this docstring gave until 2026-08-15, which was that a
    screened-out participant gets a CODELESS link. They do not, and have not
    since that day: they get a completion URL carrying `prolific_device_code`,
    their own population's code (the why is on
    `common.prolific_screenout_return_url`, which builds it).
    The no-branch rule survives its old justification because it never depended
    on it: that URL is built in ONE place, and it is not this function. `Ended`
    renders it instead of this one for them, and adding a screened-out branch
    here would make two builders for one link.

    THE CODES ARE READ THROUGH `common.cfg`, NOT a raw `.get` — the repo's own
    accessor rule (see `common.flag`: raw `.get` is for module flags, `cfg` is
    for thresholds and CODES, which must keep working mid-study). For a session
    whose frozen config predates these keys, `cfg` falls back to the shipped
    `REPLACE_*` placeholder instead of building the string `None` into the URL.
    Julian's reasoning (2026-08-13), recorded because it IS the justification:
    The shipped placeholder (`COMP-XXXXXX_REPLACE`) is ALREADY of this shape, so
    this makes both failure modes present the SAME recognisable symptom —
    somebody seeing an unreplaced placeholder in
    a completion URL knows instantly what it means and what to do, while
    `?cc=None` looks like a bug in our own code and tells them nothing.

    THE ONE NUANCE, so nobody assumes more coverage than exists:
    `settings._prelaunch_problems` checks the CURRENT config at launch, so it
    catches a study that never set a real code — but it cannot catch this case.
    The session was created before the key existed, so its frozen config
    genuinely lacks it while the current config is fine; the placeholder
    therefore appears at RUNTIME for that participant, not at launch. Either
    way the submission is not auto-approved on Prolific and needs manual
    handling — the value is that the diagnosis is instant rather than an
    investigation. Pinned by scripts/tests/frozen_config_test.py.
    """
    config = player.session.config
    cause = dq_cause(player)
    if cause == 'tab_monitor':
        code = common.cfg(config, 'prolific_dq_tab_code')
    elif cause == 'comprehension':
        code = common.cfg(config, 'prolific_dq_quiz_code')
    elif declined_consent(player):
        code = common.cfg(config, 'prolific_noconsent_code')
    else:
        code = common.cfg(config, 'prolific_cc_code')
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
    # The institution named in participant COPY. Defined once in
    # settings.INSTITUTION_NAME and re-exported here, exactly as
    # STATIC_VERSION is, because a template can only read page context.
    # NB the logo partials deliberately do NOT use it — see the note in
    # settings.py; the room page renders them with no `C` at all.
    INSTITUTION_NAME = INSTITUTION_NAME
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
    selected_sum = models.FloatField()
    earned = models.FloatField()
    payouts = models.LongStringField(blank=True)
    all_round_payoffs = models.LongStringField(blank=True)
    quiz_bonus_awarded = models.FloatField(initial=0)
    # NULLABLE ON PURPOSE (Julian, 2026-08-13). Three states, not two:
    #   1     = IBAN checked and inside SEPA
    #   0     = IBAN checked and OUTSIDE SEPA (the Results page warns on this)
    #   empty = the check NEVER RAN — no bank details were collected (every
    #           Prolific participant, and any config with collect_bank_details
    #           off). It previously shipped as initial=1, which collapsed
    #           "checked, fine" with "never asked": every Prolific row exported
    #           as if a SEPA check had passed. See CODEBOOK.md.
    # A nullable field is read with field_maybe_none, NEVER bare (CLAUDE.md).
    # The warning fires on sepa == 0 and empty is not 0, so a participant who
    # was never asked can never match a warning that was never about them.
    sepa = models.IntegerField(blank=True)
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


def iban_country_code(iban) -> str:
    """The IBAN's first two characters, uppercased — the ONE implementation of
    "which country is this IBAN from". Two different questions read it (is it
    Dutch? is it in SEPA?) and neither may re-derive it: one concept decided in
    two places is the drift trap CLAUDE.md's inverted rule describes.
    Stripped first, so a leading space cannot make ' N' read as a country."""
    return str(iban or '').strip()[:2].upper()


def check_sepa_code(player):
    # Flag a bank account outside the SEPA area so payment knows a transfer may
    # not work. The country comes from iban_country_code — shared with the BIC
    # rule in Demographics.error_message, which asks a DIFFERENT question of
    # the same two letters (see the asymmetry note there).
    player.sepa = 1 if iban_country_code(player.bank) in SEPA_COUNTRY_CODES else 0

# THE MISSING-PAYOFF SENTINELS — a CONTRACT WITH THE GAME THE STUDY AUTHOR
# WRITES IN `main`, hoisted to a named constant so it can be found from there
# (main review S2b; it used to be a local inside compute_final_payoff, i.e. a
# contract defined in one app and honoured — or not — in another, invisible
# from `main`). A round whose payoff is one of these values is treated as
# "no payoff recorded" and skipped by the payment selection. Edit this list if
# your study uses different codes for "no payoff" in its data.
MISSING_PAYOFF_SENTINELS = [-333, -111, -999]


def extract_round_payoffs(payoffs_vector, missing_values):
    """Ordered (round_number, payoff) tuples, skipping missing sentinels.

    The vector has ONE writer (`main.payoff.before_next_page`) and is always a
    FLAT LIST; `common.init_participant` starts it as []. Anything else is a
    broken write and pays NOTHING, loudly (empty payouts, visible in `earned`
    and the export) — deliberately not "tolerated": the flattening fallback
    this replaces traversed nested input in LIFO order, so if it ever ran it
    would have paid the WRONG ROUNDS silently, the round number being nothing
    but the position in this list.
    """
    if not isinstance(payoffs_vector, (list, tuple)):
        return []
    return [(idx + 1, float(value))
            for idx, value in enumerate(payoffs_vector)
            if isinstance(value, numbers.Number) and value not in missing_values]

# PAGES

def _screenout_context(player) -> dict:
    """`common.screenout_vars`, with the exit URL withheld from everybody who is
    not actually screened out.

    The device facts (what device, what the study accepts) are harmless and the
    ending's copy may use them. The EXIT URL is not: it is a completion URL
    carrying `prolific_device_code`, so handing it to every ending would put one
    population's code in another population's page source — the thing
    per-ending codes exist to prevent.
    """
    ctx = dict(common.screenout_vars(player.participant, player.session.config))
    if ending_reason(player) != 'screened_out':
        ctx['prolific_screenout_return_url'] = ''
    return ctx


class Ended(participant_tab_monitor.OutroMonitoredPage):
    """Finish screen for participants who did NOT complete normally: the two
    integrity disqualifications and a declined consent. When completion
    redirects are on it sends them back to Prolific with the matching code.

    A SCREENED-OUT PARTICIPANT DOES NOT NORMALLY REACH IT. (Corrected
    2026-08-13: this used to say a phone stopped by the allowed_devices gate
    "lands here as its FIRST page", which contradicted `was_screened_out` twelve
    lines above and described the behaviour the soft wall replaced.) The gate
    HOLDS them on `before.welcome` instead, because the verdict has to stay
    re-decidable. The screened-out branch below is the unreachable-by-design
    fallback for any future gate that sets the flag later in the flow.
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
            # The device facts come from common.screenout_vars, the same
            # builder before/screened_out.html uses. THIS PAGE NO LONGER WRITES
            # SCREEN-OUT COPY (the duplicate device-sentence branch was
            # deleted 2026-08-14 — a screened-out participant is held in
            # `before`, enforced by scripts/tests/screenout_softwall_test.py). The
            # spread is kept because the shared footer include reads
            # `prolific_screenout_return_url` from it to pick the CODELESS
            # exit for reason == 'screened_out' — the second line of defence
            # for a future gate that sets the flag later in the flow.
            # PER-PAGE INJECTION, NEVER A SHARED BUNDLE. The device facts come
            # from common.screenout_vars, the same builder
            # before/screened_out.html uses — but the screened-out EXIT URL is
            # stripped below for anybody who is not screened out. It carries
            # `prolific_device_code`, and a comprehension-DQ participant has no
            # business receiving another population's code: found by
            # scripts/tests/gated_flow_test.py when the per-ending codes landed
            # (2026-08-15), which is what that assertion is for.
            **_screenout_context(player),
            completionlink=completion_link(player),
            # The ONE reason cascade (`ending_reason`); is_displayed guarantees
            # it is non-empty here, and `or 'other'` keeps the template's
            # neutral fallback wired if that ever stops being true.
            reason=ending_reason(player) or 'other',
            # Lab-only closing line ("raise your hand"); see is_lab().
            is_lab=is_lab(player),
            # WHICH integrity module removed them: `reason='disqualified'` is
            # the bucket, this is the cause, and the template writes a
            # different sentence for each so the participant is told WHY the
            # study ended instead of "cannot continue". See dq_cause() for the
            # both-flags priority.
            dq_cause=dq_cause(player),
            prolific_completion_redirects=_flag(player, 'prolific_completion_redirects'),
        )


class Demographics(participant_tab_monitor.OutroMonitoredPage):
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
        # Missing-field errors beat the mismatch error: the mismatch is only
        # judged once both bank boxes actually hold something.
        required = []
        if _flag(player, 'collect_demographics'):
            required += ['gender', 'age']
        if _flag(player, 'collect_bank_details'):
            required += ['bank', 'bank_confirmation']
        if any(not values.get(f) for f in required):
            return "Please answer all questions with an asterisk (*)."
        if _flag(player, 'collect_bank_details') and values['bank'] != values['bank_confirmation']:
            return "Your bank numbers don't match. Please doublecheck them."
        # A NON-DUTCH IBAN NEEDS A BIC (Julian, 2026-08-13). Dutch (NL)
        # accounts are routed without one; for ANY other country the transfer
        # needs the BIC, so an empty one fails the form here — after the match
        # check, so a participant fixes one problem at a time. NON-EMPTY IS THE
        # WHOLE REQUIREMENT, deliberately: no format validation, because a
        # rejected valid-but-unusual BIC strands a lab participant at the one
        # page that pays them.
        #
        # THE ASYMMETRY WITH THE DASHBOARD'S Non-SEPA PILL IS DELIBERATE — two
        # different questions, and they must NOT be collapsed into one
        # predicate (Julian, 2026-08-13):
        #   * BIC required  = the IBAN is NOT DUTCH, in-SEPA or not. A German
        #     IBAN needs a BIC here and gets NO pill on the dashboard.
        #   * Non-SEPA pill = the SEPA check recorded 0 (check_sepa_code):
        #     the transfer may not work at all, which is worth an operator's
        #     eye even for a participant who typed a perfectly good BIC.
        # Both read the country through iban_country_code — ONE implementation
        # of "which country", two predicates on top of it.
        if (_flag(player, 'collect_bank_details')
                and iban_country_code(values.get('bank')) != 'NL'
                and not str(values.get('bic') or '').strip()):
            return ("Your IBAN is not Dutch (NL), so we also need your "
                    "bank's BIC. Please enter it in the BIC field.")

    def before_next_page(p, timeout_happened):
        # CHECK IF THE PARTICIPANT'S BANK ACCOUNT IS IN SEPA (lab payment only) ===
        if _flag(p, 'collect_bank_details') and p.bank:
            check_sepa_code(p)


def compute_final_payoff(p):
    """Determine the experimental payoff. Idempotent, and independent of the
    demographics/bank page (which is skipped entirely for Prolific), so it runs
    when the participant reaches Results — the one page every completer sees.
    """
    if p.field_maybe_none('earned') is not None:
        return  # already computed (e.g. Results re-rendered)

    # Extract RANDOM selected payoffs from the participant's payoff vector as ordered tuples (round_number, payoff)
    # Read participant vars with .vars.get(), never getattr() (KeyError trap; see docs/conventions.md).
    payoffs_vector = p.participant.vars.get('payoff_vector', []) or []
    # The "no payoff recorded" codes are the module-level MISSING_PAYOFF_SENTINELS
    # — a contract with the game in `main`; see the constant's comment.
    round_payoffs = extract_round_payoffs(payoffs_vector, MISSING_PAYOFF_SENTINELS)
    # common.cfg, never []-indexing: a session created before a parameter
    # existed does not carry it, and a KeyError here is a 500 on the payment
    # page — the worst possible place (CLAUDE.md).
    num_rewarded = common.cfg(p.session.config, 'num_rewarded')
    payouts = select_random_payouts(round_payoffs, num_rewarded)

    # Calculate the experiment payoff from i) the selected payoffs, ii) the quiz bonus and iii) the showup fee
    p.selected_sum = sum(float(pay) for _, pay in payouts)
    # Quiz bonus awarded only if no failed attempts and quiz_bonus is positive
    # (.vars.get() rather than getattr()/attribute access — KeyError trap.)
    participant_failed_attempts = p.participant.vars.get('comprehension_failed_attempts', 0) or 0
    quiz_bonus = common.cfg(p.session.config, 'quiz_bonus')
    quiz_bonus_awarded = quiz_bonus if (participant_failed_attempts == 0 and quiz_bonus > 0) else 0
    p.quiz_bonus_awarded = quiz_bonus_awarded
    showup_fee = common.cfg(p.session.config, 'showup')
    p.earned = showup_fee + p.selected_sum + p.quiz_bonus_awarded
    p.payouts = json.dumps(payouts)
    p.all_round_payoffs = json.dumps(round_payoffs)

    # ONE LEDGER (J1, option 2 — Julian, 2026-08-13): oTree's own
    # participant.payoff is written HERE, once, from `earned`, so the admin
    # Payments page shows exactly the figure this participant's receipt shows.
    # It is oTree's ONLY payoff entry: nothing writes the per-round
    # player.payoff any more — enforced at BOOT by
    # `payoff_guard.assert_no_player_payoff_writes()`, not by
    # AUTO_TABULATE_PAYOFFS=False, whose raise would land on a participant's
    # page mid-round (exp_pilots review, 2026-08-14; see payoff_guard.py). And
    # nothing in oTree recomputes participant.payoff afterwards (verified
    # against oTree 6.0.15: the player.payoff setter's delta is the only other
    # writer; scripts/tests/payoff_ledger_test.py pins that this value sticks, and §7
    # pins that a walked journey leaves every round row's _payoff at 0).
    #
    # The admin page displays payoff.to_real_world_currency(session) +
    # participation_fee, so the value stored is (earned − participation_fee),
    # de-converted from points when USE_POINTS is on — the one formula that
    # lands the ADMIN-VISIBLE real-world figure exactly on `earned` under any
    # currency config. (This template ships USE_POINTS=False and
    # participation_fee=0, where it reduces to `earned` itself. `showup` is
    # already inside `earned`; participation_fee is oTree's own separate
    # add-on, shipped 0.00.)
    # Guarded by the `earned` idempotence check above, so a Results re-render
    # never writes twice. Deliberately UNWRAPPED, like the rest of this
    # function: this is the payment record, not instrumentation — failing
    # loudly beats recording the wrong number quietly.
    from otree import settings as otree_settings
    fee = float(common.cfg(p.session.config, 'participation_fee') or 0)
    target = float(p.earned) - fee
    if otree_settings.USE_POINTS:
        rate = float(common.cfg(p.session.config,
                                'real_world_currency_per_point') or 0) or 1.0
        target = target / rate
    p.participant.payoff = cu(target)


class Feedback(participant_tab_monitor.OutroMonitoredPage):
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


def results_live_method(player, data):
    """The Results page's live channel — a DISPATCHER, because a page has
    exactly ONE live_method and this page needs two things on it: the
    return-click stamp below, and the tab monitor's focus messages, which are
    DELEGATED to the outro's record-only handler at the end (the
    four-pieces-travel-together rule: overriding the monitored base's
    live_method must keep delegating, or this page's monitoring silently dies —
    see participant_tab_monitor.py's gotcha list, and the test that pins this).

    THE CLICK STAMP: records the click on the "Back to Prolific" link, so the
    dashboard can flag a finisher who never went back to the platform (their
    submission sits open there, unpaid, while our data says finished).

    INSTRUMENTATION ONLY, NEVER IN THE EXIT PATH. The link stays a real href
    that works with this handler broken, unbound, or unreached (JS off) — see
    prolific_return_footer.html's invariants. All this does is stamp; wrapped,
    because instrumentation must never break a page (CLAUDE.md).

    WHY A LIVE MESSAGE and not the hidden-field convention: the hidden-field
    rule (docs/conventions.md) rides measurement on the page's OWN form POST — but
    Results is the LAST page; there is no further submit to ride on. The live
    socket is the template's one sanctioned server-side channel that exists
    without a submit (the tab monitor already uses it). BEST-EFFORT by nature:
    the click navigates away, so the message can be lost with the socket —
    absence of the stamp means "no click RECORDED", not "no click", and the
    dashboard pill built on it is a prompt to look, never a verdict.

    Gated on prolific_completion_redirects (module flag): with redirects off
    there is no link to click and nothing to record.
    """
    try:
        if (_flag(player, 'prolific_completion_redirects')
                and isinstance(data, dict)
                and data.get('type') == 'prolific_return_click'):
            stamps = player.participant.vars.get('stage_timestamps') or {}
            # First click wins: keep the FIRST time they left, not the last
            # reload.
            if common.STAGE_PROLIFIC_RETURN_CLICKED not in stamps:
                common.stamp_stage(player.participant,
                                   common.STAGE_PROLIFIC_RETURN_CLICKED)
            return
    except Exception:
        pass  # measurement only: never block the participant
    # Everything else on this channel is the monitor's. Record-only here, like
    # the rest of the outro (the phase note at the top of this file).
    return common.focus_live_method_outro(player, data)


class Results(participant_tab_monitor.OutroMonitoredPage):

    @staticmethod
    def is_displayed(player):
        return is_completer(player)

    # OVERRIDES the monitored base's live_method — legitimately, because it
    # DELEGATES the monitor's messages (see results_live_method). The
    # return-click stamp is instrumentation only; the link itself is a plain
    # href and works with all of this dead.
    live_method = staticmethod(results_live_method)

    # NO js_vars here either — same reason as on Ended: the completion redirect
    # is a real link built server-side (so the code is authoritative) and
    # rendered into the page, not handed to a script that has to run first.

    @staticmethod
    def vars_for_template(player):
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
        compute_final_payoff(player)
        common.set_exit_code(player.participant, common.EXIT_CODES['finished'])
        common.stamp_stage(player.participant, common.STAGE_FINISHED)
        # Parse the stored JSON back into rows for the per-round table.
        try:
            payouts = json.loads(player.payouts) if player.payouts else []
        except Exception:
            payouts = []
        try:
            round_payoffs = json.loads(player.all_round_payoffs) if player.all_round_payoffs else []
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
        # `decision_bonus` is the sum of the randomly selected rounds. ONE name
        # per figure — the old duplicate keys (`showup`, `selected_sum`, the raw
        # `payouts` list) were dead template vars and are gone, so the receipt
        # cannot be "fixed" against a name the template does not read.
        return{
            # The completion URL, rendered into the page's own link. EVERY
            # Prolific completer leaves through it, so it must not need a script
            # to exist: a completer with JS blocked would otherwise finish the
            # study, see this page, and have no way to submit their completion
            # code — unpaid, and looking like an abandoner in the data.
            'completionlink': completion_link(player),
            'earned': cu(player.earned),
            'base_payment': cu(common.cfg(player.session.config, 'showup')),
            'decision_bonus': cu(player.selected_sum),
            'quiz_bonus': cu(player.quiz_bonus_awarded),
            'show_quiz_bonus': player.quiz_bonus_awarded > 0,
            'has_rounds': bool(payout_rows),
            # NULLABLE, so field_maybe_none, never a bare read (CLAUDE.md).
            # Empty means the SEPA check never ran (no bank details collected);
            # the template warns on == 0 only, and empty is not 0, so a
            # participant who was never asked never sees the warning.
            'sepa': player.field_maybe_none('sepa'),
            'payout_rows': payout_rows,
            'num_rewarded': common.cfg(player.session.config, 'num_rewarded'),
            # The shared ending footer include branches on `reason` (Ended's
            # variant carries the codeless screened-out exit). This page has no
            # early-ending reason by definition; '' is passed EXPLICITLY rather
            # than relying on the template engine's treatment of an undefined
            # name.
            'reason': '',
            # Lab-only closing line ("stay seated"); see is_lab().
            'is_lab': is_lab(player),
            # THE PER-ROUND TABLE IS OPEN FROM THE START IN THE LAB (Julian,
            # 2026-08-13, round-2 item 10): there is an experimenter in the
            # room, the screens are the lab's own, and a participant asked to
            # check what they earned should not have to find a disclosure
            # control first. Online it stays collapsed — a phone screen is the
            # argument for the accordion, and only the online study meets one.
            #
            # DERIVED FROM THE STUDY TYPE, not from a new flag: this is a
            # property of where the study runs, and a flag would be a fourth
            # thing to remember to set. The accordion itself is UNCHANGED and
            # still present in both — this decides its initial state only, so
            # a lab participant can still collapse the table if they want to.
            'results_open': is_lab(player),
            'prolific_completion_redirects': _flag(player, 'prolific_completion_redirects'),
        }

def vars_for_admin_report(subsession):
    """Context for outro/admin_report.html — the admin "Report" TAB that
    embeds the experimenter dashboard (Julian, 2026-08-13).

    A CONVENIENCE LAYER over the dashboard's own URL, never a replacement:
    the standalone /experimenter_dashboard/<code> must keep working unchanged
    with this whole mechanism deleted. The tab exists purely so an operator
    who opens the session admin page FINDS the dashboard without being told a
    URL (see the template's header for how oTree's supported admin-report
    extension point carries it — no oTree page is templated over or patched).

    INTERNALLY DEFENSIVE, deliberately: oTree calls this UNGUARDED
    (otree/views/admin.py, AdminReport.get_context_data), so a raise here
    500s the Report tab. The only thing that can fail is the import, so that
    is the only thing caught — no bare except across the function. The
    fallback literal duplicates URL_BASE on purpose: it is the belt for the
    one state where the shared constant is unreachable, and a tab that still
    links to the right place beats one that is down because an import broke.
    """
    try:
        import experimenter_dashboard
        base = experimenter_dashboard.URL_BASE
    except ImportError:
        base = '/experimenter_dashboard'
    return dict(dashboard_url=f'{base}/{subsession.session.code}')


# THE COMPLETER GATE IS A PER-PAGE DUTY (whole-app review, 2026-08-13, kept
# explicit deliberately — no base class, because Ended INVERTS the predicate
# and every other page ANDs its own flags onto it): every page added to this
# sequence must compose `is_completer` into its is_displayed — positively for
# a normal page, negated for an ending. Forgetting it fails SILENTLY: a
# disqualified participant reaching a payment or feedback page produces no
# error, just wrong pages served and wrong data collected.
page_sequence = [Ended, Demographics, Feedback, Results]

# MONITORED BY DEFAULT — every page above must be a
# participant_tab_monitor.MonitoredPage subclass (here, OutroMonitoredPage:
# record-only — the phase note at the top
# of this file) or explicitly opted out; a page that dodged the rule fails the
# BOOT here, never a participant (see participant_tab_monitor.py).
participant_tab_monitor.assert_monitored_page_sequence(__name__, page_sequence)

# EXPERIMENTER DASHBOARD INSTALL — deliberately the LAST lines of the LAST app
# module, and deliberately in `outro` rather than `before` or `settings.py`:
#
#   * it must run AFTER this module's own `page_sequence` exists, because
#     importing `otree.urls` builds the whole route table, and that walks every
#     app's page_sequence — including this one, mid-import;
#   * an early install from settings.py (identity.py's other install point)
#     would accomplish NOTHING here: `otree.urls` is never importable at
#     settings time, and unlike the label guard there is no window to close —
#     the routes only need to exist before `otree.asgi` builds the app, which
#     is after every app import on every supported boot path.
#
# `install_dashboard_route_or_note` NEVER raises — not even on version drift,
# which it logs loudly instead. That is the one deliberate difference from
# identity's asserting install point, and it is the dashboard's own first rule
# applied to its install: a dashboard that cannot install harms nobody, but a
# boot that dies over an operator page fails every participant. See the
# docstrings in experimenter_dashboard.py.
import experimenter_dashboard

experimenter_dashboard.install_dashboard_route_or_note()
# The admin "Report" tab's drift check (loud when the machinery it rides has
# moved, quiet when oTree is legitimately absent, never a raise) — see
# note_admin_tab_problems and outro/admin_report.html.
experimenter_dashboard.note_admin_tab_problems()