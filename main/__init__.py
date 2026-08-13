from otree.api import *
import random

# Take NUM_ROUNDS from session defaults (static at import time for oTree).
from settings import SESSION_CONFIG_DEFAULTS, STATIC_VERSION
import common
num_experimental_rounds = SESSION_CONFIG_DEFAULTS['num_experimental_rounds']

doc = """
tasks
"""

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
    return min(int(common.cfg(session.config, 'num_experimental_rounds')), C.NUM_ROUNDS)


class Subsession(BaseSubsession):
    pass
    
class Group(BaseGroup):
    pass

class Player(BasePlayer):
    # THE GAME'S OWN per-round result — deliberately NOT oTree's player.payoff
    # (J1, Julian 2026-08-13). The template pays from participant.payoff_vector
    # (collected from this field on the last round), and oTree's own ledger
    # (participant.payoff) is written ONCE, from `earned`, when the results
    # page computes payment — so the admin Payments page and the participant's
    # receipt show the same figure with nothing to disagree. Writing oTree's
    # player.payoff instead now RAISES (settings.AUTO_TABULATE_PAYOFFS=False),
    # so a study cannot drift back into two ledgers by habit.
    round_payoff = models.CurrencyField(blank=True)
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


def progress_vars(player) -> dict:
    """Round-of-total progress for the task screens (change_requests item 7).

    ONE source for the strip's text line AND its bar, so the two can never
    disagree. The total is THIS session's round count (`rounds_for`), not
    C.NUM_ROUNDS: a config may run fewer rounds, and telling a participant
    "Round 3 of 10" in a 5-round session would be a lie in the one place they
    are counting.
    """
    total = rounds_for(player.session)
    current = min(player.round_number, total)
    return dict(
        round_count=player.round_number,
        rounds_total=total,
        # Whole percent, clamped: a fill of 100.4% would overflow its track.
        progress_pct=max(0, min(100, round(100 * current / total))) if total else 0,
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

# GROUP MATCHING: this template ships NONE. Reference code from a DIFFERENT
# study (a RoundStartWaitPage with perfect-stranger matching) lives in
# _ai/group_matching_reference.py — read its header first: it references names
# this template does not have, so it is a shape to learn from, not a block to
# uncomment. The design questions around it (matching cannot be designed
# independently of WHEN treatment/role assignment happens) are in TODO.md
# under "Group matching".

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
        return dict(
            progress_vars(self),
            tab_monitor=bool(self.session.config.get('tab_monitor')),
            passive_capture=bool(self.session.config.get('passive_capture')),
        )

    def before_next_page(player, timeout_happened):
        # Generate a payoff for this round before showing the payoff page.
        # Into round_payoff, NEVER player.payoff — see the field's comment.
        player.round_payoff = random.randint(1, 100)
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
        return dict(
            progress_vars(self),
            # round_payoff is nullable, so field_maybe_none, never bare
            # (CLAUDE.md) — though GameStart always writes it first.
            payoff=cu(self.field_maybe_none('round_payoff') or 0),
            tab_monitor=bool(self.session.config.get('tab_monitor')),
        )

    @staticmethod
    def before_next_page(player, timeout_happened):
        # On the LAST DISPLAYED round (which may be earlier than C.NUM_ROUNDS for
        # a shorter config), collect all payoffs into the participant vector.
        if player.round_number == rounds_for(player.session):
            payoff_vector = [pr.field_maybe_none('round_payoff') or cu(0)
                             for pr in player.in_rounds(1, player.round_number)]
            existing = common.pvar(player.participant, 'payoff_vector', None)
            if existing is None:
                existing = []
            existing.extend(payoff_vector)
            player.participant.payoff_vector = existing
            common.stamp_stage(player.participant, 'task_done')

page_sequence = [GameStart, payoff]
