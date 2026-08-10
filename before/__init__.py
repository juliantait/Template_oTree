# The entry app: welcome, consent, and (online) external-ID / device capture.
# - example_screen: a DEBUG-only live preview of the shared design template.
# - startpage: lab hold screen shown only for experimenter-run (lab) sessions.
# - welcome: welcome + consent; captures the external participant id and device
#   info when those modules are enabled. Non-consenters are routed straight to
#   the outro (they never see the task). When the `mobile_screenout` option is
#   on, a server-side User-Agent gate runs before this page renders and sends a
#   phone straight to the outro ending with exit code -4 (see
#   _apply_mobile_screenout) — with the option off it does nothing at all.

from main import *
import common
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
    participant_label = models.StringField(blank=True)
    treatment_group = models.StringField(blank=True)
    consent = models.BooleanField(
        initial=True, blank=True,
        label="Do you consent to take part?",
        choices=[(True, "I consent and wish to take part"),
                 (False, "I do not consent")],
        widget=widgets.RadioSelect,
    )
    # Captured only when the relevant module flag is on (see get_form_fields).
    # BOTH sides of the id confirmation are recorded, separately, so a mismatch is
    # visible in the export and can settle a payment dispute later:
    #   participant_id_url      — the id as it ARRIVED (participant label, or the
    #                             consent page's hidden URL capture). Never edited.
    #   participant_id_external — what the participant CONFIRMED or corrected on
    #                             the confirmation page. This is the one payment
    #                             should use.
    participant_id_url = models.StringField(blank=True)
    participant_id_external = models.StringField(blank=True, label="Your Prolific ID")
    is_mobile = models.BooleanField(initial=False, blank=True)
    device_info_json = models.LongStringField(blank=True)
    # Spare columns (future-proofing) — never rename in place; see CODEBOOK.md.
    spare_str_1 = models.LongStringField(blank=True)
    spare_str_2 = models.LongStringField(blank=True)


def creating_session(subsession: Subsession):
    # Initialise every participant field once, at session creation, so no export
    # row is ever blank (exit_code starts at 0 = abandoned).
    for player in subsession.get_players():
        common.init_participant(player.participant)
    # Then assign treatments (see before/treatment_assignment.py).
    return treatment_assignment.assign_treatments(subsession)


def _flag(player, name):
    return bool(player.session.config.get(name))


def _apply_mobile_screenout(player, user_agent):
    """MOBILE SCREEN-OUT GATE — decided BEFORE the consent page is rendered.

    No-op unless the `mobile_screenout` config option is 1: with the option off
    (the default, in every recruitment profile) this function returns before
    touching anything, so the phone check has no participant-visible effect at
    all and every device proceeds normally.

    With the option on, a phone User-Agent is recorded as screened out
    (`participant.screened_out` + exit code -4) and never sees consent: the
    caller runs this on the consent page's own GET, before any HTML is
    produced, and `welcome.is_displayed` then returns False, so oTree redirects
    the participant onward. Every page in between is gated on the same flag, so
    they land on the outro ending.

    Idempotent — a refresh re-decides identically and never re-stamps.
    """
    participant = player.participant
    if not _flag(player, 'mobile_screenout'):
        return
    if common.is_screened_out(participant):
        return  # already decided (page reload)
    if not common.is_mobile_user_agent(user_agent):
        return
    # Records the flag, exit code -4 AND the cause in one call. The cause is what
    # picks the sentence on the ending — -4 alone is the generic "screened out at
    # entry" bucket and must never be assumed to mean "phone" (see
    # common.SCREENOUT_CAUSES).
    common.set_screened_out(participant, 'mobile')
    common.stamp_stage(participant, 'screened_out')
    # Keep the evidence for the decision (export only — never rendered).
    common.extra_set(participant, 'screenout_user_agent', (user_agent or '')[:300])


# PAGES
# NB: _static/global/html/template.html is a DESIGN REFERENCE (open it directly
# in a browser to preview the shell). It is intentionally NOT a flow page — it
# has no working Next control — so it is not in page_sequence.

class startpage(Page):
    # Lab hold screen: only meaningful when an experimenter starts the session.
    @staticmethod
    def is_displayed(player):
        return player.session.config.get('recruitment') == 'lab'


class welcome(Page):
    template_name = 'before/welcome+consent.html'
    form_model = 'player'

    def get(self):
        """Run the mobile screen-out gate before this page renders.

        This override is the ONE place the entry request is reachable
        server-side (oTree's page hooks receive the player, not the request), and
        it runs before a single byte of the consent page exists. `Page.get`
        re-checks `is_displayed` immediately below, so a participant screened out
        here is redirected onward instead of being shown consent — nothing is
        rendered to them here, not even briefly.

        Instrumentation must never break a page (conventions.md): if anything in
        the gate raises, the participant simply proceeds to consent.
        """
        try:
            _apply_mobile_screenout(
                self.player, self.request.headers.get('user-agent', ''))
        except Exception:
            pass
        return super().get()

    @staticmethod
    def is_displayed(player):
        # A screened-out participant (see _apply_mobile_screenout) never sees
        # the consent page; oTree walks them forward to the outro ending.
        return not common.is_screened_out(player.participant)

    @staticmethod
    def get_form_fields(player):
        fields = []
        # Explicit consent (with no-consent routing) only when we redirect people
        # back to a platform; lab consent is implicit in clicking Next.
        if _flag(player, 'completion_redirects'):
            fields.append('consent')
        # NB: the participant id is NOT collected here. It has its own page
        # (ConfirmProlificID) so this page stays platform-neutral and renders
        # identically in the lab. Only the invisible URL capture rides along.
        if _flag(player, 'capture_participant_id'):
            fields.append('participant_id_url')
        if _flag(player, 'capture_participant_id') or _flag(player, 'device_capture'):
            fields.append('is_mobile')
        if _flag(player, 'device_capture'):
            fields.append('device_info_json')
        return fields

    @staticmethod
    def vars_for_template(player):
        cfg = player.session.config
        return dict(
            capture_participant_id=_flag(player, 'capture_participant_id'),
            device_capture=_flag(player, 'device_capture'),
            completion_redirects=_flag(player, 'completion_redirects'),
            # Payment-mechanics wording only. Branching on collect_bank_details
            # (not on capture_participant_id) because the sentence is about HOW
            # the participant is paid — and it keeps this page from having any
            # notion of a recruitment platform.
            collect_bank_details=_flag(player, 'collect_bank_details'),
            # Consent quotes duration and payment from config, so a lab session
            # can state its own show-up fee (safe reads: defaults if unset).
            expected_duration_minutes=cfg.get('expected_duration_minutes', 30),
            showup_fee=cu(cfg.get('showup', 0) or 0),
        )

    # NB: there is deliberately no error_message here blocking `is_mobile`.
    # The client-side `is_mobile` field is MEASUREMENT (device_capture) and
    # never blocks anyone; screening phones out is the `mobile_screenout`
    # option's job alone, and it happens before this page (see
    # _apply_mobile_screenout). Blocking here as well would give the phone check
    # a participant-visible effect even with that option off.

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant_label = player.participant.label or ''
        # Copy the pre-assigned treatment onto the player for display/testing.
        # Read participant vars with .vars.get(), never getattr() (KeyError trap;
        # the oTree vars descriptor raises KeyError, so a getattr default does not
        # protect you — see conventions.md).
        player.treatment_group = player.participant.vars.get('treatment_group', '')

        # The id arrived in the URL (if at all). Keep it on the player for the
        # audit trail and seed participant.label from it when oTree has not
        # already resolved one, so the confirmation page can pre-fill.
        if _flag(player, 'capture_participant_id'):
            url_id = (player.field_maybe_none('participant_id_url') or '').strip()
            if url_id:
                player.participant_id_url = url_id
                if not player.participant.label:
                    player.participant.label = url_id
        if _flag(player, 'device_capture') and player.device_info_json:
            common.extra_set(player.participant, 'device_info_json', player.device_info_json)

        common.stamp_stage(player.participant, 'consent')

        # No-consent short-circuit: record the outcome; routing happens in
        # app_after_this_page so the participant never enters the task apps.
        if _flag(player, 'completion_redirects') and not player.consent:
            common.set_exit_code(player.participant, common.EXIT_CODES['no_consent'])

    @staticmethod
    def app_after_this_page(player, upcoming_apps):
        # Send non-consenters straight to the final app (outro), skipping intro
        # and main entirely.
        if _flag(player, 'completion_redirects') and not player.consent:
            return upcoming_apps[-1]


class ConfirmProlificID(Page):
    """Confirm the recruitment-platform id — the ONLY page that mentions Prolific.

    Everything platform-specific was moved off the shared consent page onto this
    one, so consent can render identically in the lab and online. Gated on
    `capture_participant_id`, so a lab session never sees it.

    The id normally arrives in the URL (oTree's ?participant_label=, or the
    consent page's hidden ?PROLIFIC_PID= capture) and is shown PRE-FILLED in an
    editable field: the participant either submits as-is to confirm, or corrects
    it. When NO id arrived — the normal case for a bare room link, which is what
    friend-testers use — the page shows a prominent we-have-no-id notice and an
    EMPTY field, and still submits fine: nothing is required, so it can never be
    a dead end.
    """
    template_name = 'before/confirm_prolific_id.html'
    form_model = 'player'
    form_fields = ['participant_id_external']

    @staticmethod
    def _url_id(player):
        """The id as it arrived: the participant label, or the URL capture."""
        return (player.participant.label
                or player.field_maybe_none('participant_id_url') or '')

    @staticmethod
    def is_displayed(player):
        # Never in the lab; never for a participant already screened out or one
        # who declined consent (they are on their way to the ending).
        if not _flag(player, 'capture_participant_id'):
            return False
        if common.is_screened_out(player.participant):
            return False
        if _flag(player, 'completion_redirects') and not player.consent:
            return False
        return True

    @staticmethod
    def vars_for_template(player):
        url_id = ConfirmProlificID._url_id(player)
        # prefill_id is participant-controlled; the template escapes it. See the
        # SECURITY note in before/confirm_prolific_id.html.
        return dict(prefill_id=url_id, has_prefill=bool(url_id))

    @staticmethod
    def before_next_page(player, timeout_happened):
        confirmed = (player.field_maybe_none('participant_id_external') or '').strip()
        player.participant_id_external = confirmed
        # The confirmed id is the one payment should use, so it becomes the
        # participant label the platform matches on. The URL-arrived value stays
        # in participant_id_url for the audit trail.
        if confirmed:
            player.participant.label = confirmed
            player.participant.participant_id_external = confirmed
        common.stamp_stage(player.participant, 'confirm_id')


# LAB      : startpage (the CREED gate) -> welcome/consent
# PROLIFIC : [phone screen-out, no page of its own] -> welcome/consent -> ConfirmProlificID
page_sequence = [startpage, welcome, ConfirmProlificID]
