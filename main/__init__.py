from otree.api import *
import random

# Take NUM_ROUNDS from session defaults (static at import time for oTree).
from settings import SESSION_CONFIG_DEFAULTS, STATIC_VERSION
import common
num_experimental_rounds = SESSION_CONFIG_DEFAULTS['num_experimental_rounds']

doc = """
tasks
"""
manager = None
task_manager = None

class C(BaseConstants):
    # Asset cache-buster for this BUILD (settings.STATIC_VERSION).
    # Templates read C.STATIC_VERSION, never session.config.static_version:
    # a session config is frozen at creation, so the template read 500s
    # for in-flight participants when the parameter post-dates them.
    STATIC_VERSION = STATIC_VERSION
    NAME_IN_URL = 'main'
    PLAYERS_PER_GROUP = None
    # FIXED AT IMPORT: oTree builds its round tables from this constant, so it
    # cannot vary per session. A config may run FEWER rounds (set
    # num_experimental_rounds lower — the extra pages are skipped via
    # is_displayed) but NEVER MORE than were imported here.
    NUM_ROUNDS = num_experimental_rounds


def rounds_for(session) -> int:
    """How many rounds THIS session runs (config value, capped at NUM_ROUNDS)."""
    requested = min(int(common.cfg(session.config, 'num_experimental_rounds')), C.NUM_ROUNDS)
    return min(requested, C.NUM_ROUNDS)


class Subsession(BaseSubsession):
    pass
    
class Group(BaseGroup):
    pass

class Player(BasePlayer):
    # Passive measurement: time on page in ms, filled by a hidden field on the
    # page's OWN form (no side request). blank=True so an EMPTY submission (JS
    # disabled/blocked) is stored, not rejected. Only collected when the
    # passive_capture flag is on.
    client_ms = models.LongStringField(blank=True)
    # --- spare columns (future-proofing) -------------------------------------
    # Never rename in place. To repurpose one, record the mapping (with a date)
    # in CODEBOOK.md and add a rename-before-launch todo. See the repurpose
    # convention in CODEBOOK.md and conventions.md.
    spare_str_1 = models.LongStringField(blank=True)
    spare_str_2 = models.LongStringField(blank=True)


def creating_session(subsession: Subsession):
    # NUM_ROUNDS is fixed at import; a config must never request MORE rounds.
    requested = int(common.cfg(subsession.session.config, 'num_experimental_rounds'))
    if requested > C.NUM_ROUNDS:
        raise ValueError(
            f"num_experimental_rounds={requested} exceeds the imported "
            f"C.NUM_ROUNDS={C.NUM_ROUNDS}. NUM_ROUNDS is fixed at import; raise "
            f"the default in settings.py (SESSION_CONFIG_DEFAULTS) and restart, "
            f"or lower this config."
        )


def is_active_round(player) -> bool:
    """True while the round is within THIS session's (possibly shorter) count."""
    return player.round_number <= rounds_for(player.session)


def task_page_visible(player) -> bool:
    """Visibility for a task page: active round AND still in the study.

    Once the tab monitor disqualifies a participant (ai_safety_disqualified), or
    the entry mobile screen-out removed them (screened_out), every task page
    returns False, so a page reload lands them on the ending.
    """
    if player.participant.vars.get('ai_safety_disqualified'):
        return False
    if common.is_screened_out(player.participant):
        return False
    return is_active_round(player)


def ai_safety_js_vars(player):
    """Thresholds for the client monitor (read by ai_safety_monitor.js)."""
    cfg = player.session.config
    return dict(
        tab_monitor=bool(cfg.get('tab_monitor')),
        AI_SAFETY_CONFIG=dict(
            max_violations=int(common.cfg(cfg, 'tab_monitor_max_violations')),
            threshold_ms=int(common.cfg(cfg, 'tab_monitor_threshold_ms')),
            overlay_delay_ms=int(common.cfg(cfg, 'tab_monitor_overlay_delay_ms')),
        ),
    )

# FUNCTIONS

# PAGES

# Group matching helpers (previously RoundStartWaitPage) are now located in main/group_matching.py.
# class RoundStartWaitPage(WaitPage):
#     # Example group matching code is provided in main/group_matching.py
#     pass

# INSERT YOUR GAME PAGES HERE

class GameStart(Page):
    template_name = 'main/game.html'
    form_model = 'player'   # for the optional passive-capture hidden field
    # Skip rounds beyond this session's count AND skip once disqualified.
    is_displayed = staticmethod(task_page_visible)
    # Tab-switch monitor: the live handler records violations server-side. No-op
    # unless the tab_monitor flag is on (see common.focus_live_method).
    live_method = staticmethod(common.focus_live_method)
    js_vars = staticmethod(ai_safety_js_vars)

    @staticmethod
    def get_form_fields(player):
        # The passive-capture hidden field rides on this page's own form.
        return ['client_ms'] if player.session.config.get('passive_capture') else []

    def vars_for_template(self):
        return {
            'round_count': self.round_number,
            'tab_monitor': bool(self.session.config.get('tab_monitor')),
            'passive_capture': bool(self.session.config.get('passive_capture')),
        }

    def before_next_page(player, timeout_happened):
        # Generate a payoff for this round before showing the payoff page
        player.payoff = random.randint(1, 100)
        # Passive measurement: store the client-captured hidden fields (empty if
        # JS didn't run). No-op unless passive_capture is on.
        if player.session.config.get('passive_capture'):
            common.extra_set(player.participant, f'client_ms_round_{player.round_number}',
                             player.field_maybe_none('client_ms') or '')


class payoff(Page):
    template_name = 'main/payoff.html'
    is_displayed = staticmethod(task_page_visible)
    live_method = staticmethod(common.focus_live_method)
    js_vars = staticmethod(ai_safety_js_vars)

    def vars_for_template(self):
        return {
            'payoff': cu(self.payoff),
            'round_count': self.round_number,
            'tab_monitor': bool(self.session.config.get('tab_monitor')),
        }

    @staticmethod
    def before_next_page(player, timeout_happened):
        # On the LAST DISPLAYED round (which may be earlier than C.NUM_ROUNDS for
        # a shorter config), collect all payoffs into the participant vector.
        if player.round_number == rounds_for(player.session):
            payoff_vector = [pr.payoff for pr in player.in_rounds(1, player.round_number)]
            existing = common.pvar(player.participant, 'payoff_vector', None)
            if existing is None:
                existing = []
            existing.extend(payoff_vector)
            player.participant.payoff_vector = existing
            common.stamp_stage(player.participant, 'task_done')

page_sequence = [GameStart, payoff]
