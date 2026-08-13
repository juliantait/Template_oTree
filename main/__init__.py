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

def task_template_vars(player) -> dict:
    """The template vars EVERY task page needs: the progress strip's numbers
    (main.progress_vars — one source for the text line and the bar) and the
    tab_monitor gate the shared script include branches on. A TaskPage
    subclass that overrides vars_for_template must SPREAD this dict in (see
    GameStart / payoff) rather than retype the keys."""
    return dict(
        progress_vars(player),
        tab_monitor=bool(player.session.config.get('tab_monitor')),
    )


class TaskPage(Page):
    """THE BASE EVERY TASK PAGE SUBCLASSES — the task wiring lives here, once.

    WHY INHERITANCE — recorded because it is the justification for the
    indirection (Julian, 2026-08-13, review item J2): a task page that is
    SILENTLY NOT ARMED for the tab monitor is a worse outcome than the cost of
    a base class. Somebody adding a page and forgetting the wiring gets no
    error anywhere — the failure is monitoring that simply never fires on that
    page, discovered from the data rather than from a test. With the wiring
    here, "add a task page" is subclass-and-write-content, and forgetting is
    structurally impossible.

    WHAT IT CARRIES — the monitor CONTRACT is untouched; this changes who
    TYPES the wiring, not what it is (same bindings, names and thresholds):
      * ``is_displayed = task_page_visible`` — round capping plus the
        disqualified / screened-out gate;
      * ``live_method = common.focus_live_method`` — the server-authoritative
        violation counter (a no-op unless the tab_monitor flag is on);
      * ``js_vars = ai_safety_js_vars`` — the client monitor's thresholds;
      * ``vars_for_template`` -> task_template_vars — the progress strip's
        numbers and the tab_monitor gate. A page needing MORE vars overrides
        it and spreads ``task_template_vars(self)`` in.
    The template side has its own two shared pieces: include
    ``_static/global/html/task_progress_strip.html`` in the header and
    ``_static/global/html/tabmonitor_assets.html`` at the end of the template.

    TWO GOTCHAS THAT MAKE THIS PATTERN BITE LATER — read before adding pages:
      * oTree resolves page attributes AT IMPORT. A future page that must NOT
        bind the monitor cannot just omit something — it INHERITS the binding,
        and needs an explicit override (``live_method = None`` and
        ``js_vars = None``, with a comment saying why) to unbind.
      * SUBCLASS THIS; never copy its attributes into a new page class.
        Copying reintroduces exactly the per-page drift this removes — the
        page whose copy goes stale is the silently-unarmed page again.

    Page-class inheritance is NOT an idiom this template uses anywhere else —
    every other page is written out explicitly. It is deliberate HERE, and
    only here, for the reason above: the task block is the one place where a
    missing binding fails silently and costs monitoring data.
    ``tests/task_page_test.py`` proves the arming structurally — a fresh
    subclass is armed by subclassing alone, and the served page carries the
    monitor config end-to-end.
    """
    is_displayed = staticmethod(task_page_visible)
    live_method = staticmethod(common.focus_live_method)
    js_vars = staticmethod(ai_safety_js_vars)

    def vars_for_template(self):
        return task_template_vars(self)


# GROUP MATCHING: this template ships NONE. Reference code from a DIFFERENT
# study (a RoundStartWaitPage with perfect-stranger matching) lives in
# _ai/group_matching_reference.py — read its header first: it references names
# this template does not have, so it is a shape to learn from, not a block to
# uncomment. The design questions around it (matching cannot be designed
# independently of WHEN treatment/role assignment happens) are in TODO.md
# under "Group matching".

# INSERT YOUR GAME PAGES HERE

class GameStart(TaskPage):
    # The task wiring (gating, monitor binding, js_vars, base template vars)
    # is INHERITED from TaskPage — subclass it, never copy it (see its
    # docstring for the two gotchas).
    template_name = 'main/game.html'
    form_model = 'player'   # for the optional passive-capture hidden field

    @staticmethod
    def get_form_fields(player):
        # The passive-capture hidden field rides on this page's own form.
        return ['client_ms'] if player.session.config.get('passive_capture') else []

    def vars_for_template(self):
        return dict(
            task_template_vars(self),
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


class payoff(TaskPage):
    # Wiring inherited from TaskPage — subclass, never copy (its docstring).
    template_name = 'main/payoff.html'

    def vars_for_template(self):
        return dict(
            task_template_vars(self),
            # round_payoff is nullable, so field_maybe_none, never bare
            # (CLAUDE.md) — though GameStart always writes it first.
            payoff=cu(self.field_maybe_none('round_payoff') or 0),
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
