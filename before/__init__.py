# The entry app: welcome, consent, and (online) external-ID / device capture.
# - example_screen: a DEBUG-only live preview of the shared design template.
# - startpage: lab hold screen shown only for experimenter-run (lab) sessions.
# - welcome: welcome + consent; captures the external participant id and device
#   info when those modules are enabled. Non-consenters are routed straight to
#   the outro (they never see the task).

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

    @staticmethod
    def get_form_fields(player):
        fields = []
        # Explicit consent (with no-consent routing) only when we redirect people
        # back to a platform; lab consent is implicit in clicking Next.
        if _flag(player, 'completion_redirects'):
            fields.append('consent')
        if _flag(player, 'capture_participant_id'):
            fields.append('participant_id_external')
        if _flag(player, 'capture_participant_id') or _flag(player, 'device_capture'):
            fields.append('is_mobile')
        if _flag(player, 'device_capture'):
            fields.append('device_info_json')
        return fields

    @staticmethod
    def vars_for_template(player):
        return dict(
            capture_participant_id=_flag(player, 'capture_participant_id'),
            device_capture=_flag(player, 'device_capture'),
            completion_redirects=_flag(player, 'completion_redirects'),
        )

    @staticmethod
    def error_message(player, values):
        # Block mobile devices (desktop-only tasks); show a link back to Prolific.
        if values.get('is_mobile'):
            return ("Sorry, this study cannot be completed on a mobile device. "
                    "Please return the submission on Prolific and open the study "
                    "on a desktop or laptop computer.")

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant_label = player.participant.label or ''
        # Copy the pre-assigned treatment onto the player for display/testing.
        # Read participant vars with .vars.get(), never getattr() (KeyError trap;
        # the oTree vars descriptor raises KeyError, so a getattr default does not
        # protect you — see conventions.md).
        player.treatment_group = player.participant.vars.get('treatment_group', '')

        if _flag(player, 'capture_participant_id') and player.participant_id_external:
            player.participant.participant_id_external = player.participant_id_external
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


page_sequence = [startpage, welcome]
