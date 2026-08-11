# The entry app: welcome, consent, and (online) external-ID / device capture.
# - example_screen: a DEBUG-only live preview of the shared design template.
# - startpage: lab hold screen shown only for experimenter-run (lab) sessions.
# - welcome: welcome + consent; captures the external participant id and device
#   info when those modules are enabled. Non-consenters are routed straight to
#   the outro (they never see the task). A server-side User-Agent gate runs
#   before this page renders and sends any device the study's `allowed_devices`
#   list excludes straight to the outro ending with exit code -4 (see
#   _apply_device_gate) — with the shipped list (all four types) it does
#   nothing at all.

from main import *
import common
from settings import STATIC_VERSION
from . import treatment_assignment

class C(BaseConstants):
    # Asset cache-buster for this BUILD (settings.STATIC_VERSION).
    # Templates read C.STATIC_VERSION, never session.config.static_version:
    # a session config is frozen at creation, so the template read 500s
    # for in-flight participants when the parameter post-dates them.
    STATIC_VERSION = STATIC_VERSION
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
    # NO `initial=` AND NO `blank=True`, both deliberate and both load-bearing
    # (`skills_claude/writing_welcome_consent.md`: "Consent is an explicit
    # affirmative action … never a pre-checked box"):
    #   * `initial=True` made oTree render the "I consent" radio with `checked`,
    #     so consent was pre-ticked — measured 2026-08-10, and on a 1280x720
    #     laptop the options were below the fold, so a participant could submit
    #     a consent they had never seen;
    #   * `blank=True` then accepted a submit with the field absent and stored
    #     the pre-ticked True anyway.
    # Required + unset means an untouched submit is REJECTED with oTree's own
    # validation message, so the choice cannot be skipped. It is only ever in
    # form_fields when completion_redirects is on (see get_form_fields), so the
    # lab variant is unaffected and leaves it null — read it with
    # field_maybe_none anywhere outside that branch.
    consent = models.BooleanField(
        # NO LABEL, deliberately (Julian, 2026-08-11, change_requests item 13).
        # oTree renders a field's label as a line above its options, and the
        # page already asks the question in bold directly above the group
        # ("Please indicate whether you consent…"). The label repeated it and
        # cost ~40px on the page where vertical space is tightest. An empty
        # string (not None) is what suppresses the line without oTree falling
        # back to the field NAME.
        label="",
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


def _apply_device_gate(player, user_agent):
    """DEVICE ALLOW-LIST GATE — decided BEFORE the consent page is rendered.

    The study STATES which device types it accepts (`allowed_devices`: any of
    'phone', 'tablet', 'computer', 'unknown'); anything else is screened out at
    entry. It replaced the old phones-only `mobile_screenout` flag.

    NO-OP BY DEFAULT. The shipped list is all four types, so every device is
    permitted and this function changes nothing a participant could see — the
    same safety property the old flag had at 0. (device_capture still RECORDS
    the device as measurement; it never blocks anyone.)

    THE SERVER DECIDES, from the entry request's User-Agent. The client's own
    idea of what it is arrives later, in the device-info JSON, and is kept
    beside this for comparison — but a client-side check is trivially bypassed,
    so it never gates. See common.device_gate_verdict.

    A screened-out participant never sees consent: the caller runs this on the
    consent page's own GET, before any HTML is produced, and
    `welcome.is_displayed` then returns False, so oTree redirects them onward.
    Every page in between is gated on `common.is_screened_out`, so they land on
    the outro ending.

    Idempotent — a refresh re-decides identically and never re-stamps.
    """
    participant = player.participant
    if common.is_screened_out(participant):
        return  # already decided (page reload)
    detected, allowed = common.device_gate_verdict(
        player.session.config, user_agent)
    # Measurement, recorded for EVERY participant including the ones let
    # through: it is the server's own classification of the entry request, and
    # analysis wants it whether or not the gate was narrowed.
    common.extra_set(participant, 'entry_device_type', detected)
    if allowed:
        return
    # Records the flag, exit code -4 AND the cause in one call. THE CAUSE IS THE
    # DETECTED TYPE, not the name of the gate: -4 alone is the generic "screened
    # out at entry" bucket, and the ending writes a different sentence for a
    # phone, a tablet, a computer and an unidentifiable device (see
    # common.SCREENOUT_CAUSES and outro/Ended.html).
    common.set_screened_out(participant, detected)
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
        """Run the entry device gate before this page renders.

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
            _apply_device_gate(
                self.player, self.request.headers.get('user-agent', ''))
        except Exception:
            pass
        return super().get()

    @staticmethod
    def is_displayed(player):
        # A screened-out participant (see _apply_device_gate) never sees
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
            # Rendered only when show_duration_and_fee is on (off by default).
            show_duration_and_fee=bool(common.cfg(cfg, 'show_duration_and_fee')),
            expected_duration_minutes=common.cfg(cfg, 'expected_duration_minutes'),
            showup_fee=cu(common.cfg(cfg, 'showup') or 0),
            # WHICH CONTACT ROUTE the closing sentence offers. `recruitment` is
            # an explicit resolved config key (settings.resolve_recruitment_
            # profile), read through common.cfg so a session created before the
            # key existed still renders. `capture_participant_id` is the flag
            # that means "this study runs on Prolific" — the same one that gates
            # the ID page — so exactly the studies that have a Prolific message
            # channel name it.
            is_lab=(common.cfg(cfg, 'recruitment') == 'lab'),
            names_prolific=_flag(player, 'capture_participant_id'),
        )

    # NB: there is deliberately no error_message here blocking `is_mobile`.
    # The client-side `is_mobile` field is MEASUREMENT (device_capture) and
    # never blocks anyone; screening devices out is the `allowed_devices`
    # gate's job alone, and it happens before this page (see
    # _apply_device_gate). Blocking here as well would give the device check a
    # participant-visible effect even when the allow-list permits everything.

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
