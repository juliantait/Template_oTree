from otree.api import *
import random

# Take NUM_ROUNDS from session defaults (static at import time for oTree).
from settings import INSTITUTION_NAME, SESSION_CONFIG_DEFAULTS, STATIC_VERSION
import common
import participant_tab_monitor
num_experimental_rounds = SESSION_CONFIG_DEFAULTS['num_experimental_rounds']

# One implementation, in common.flag (raw config.get — see its docstring for
# why it is NOT common.cfg).
_flag = common.flag

doc = """
tasks
"""

class C(BaseConstants):
    # Asset cache-buster for this BUILD (settings.STATIC_VERSION).
    # Templates read C.STATIC_VERSION, never session.config.build_static_version:
    # a session config is frozen at creation, so the template read 500s
    # for in-flight participants when the parameter post-dates them.
    STATIC_VERSION = STATIC_VERSION
    # The institution named in participant COPY. Defined once in
    # settings.INSTITUTION_NAME and re-exported here, exactly as
    # STATIC_VERSION is, because a template can only read page context.
    # NB the logo partials deliberately do NOT use it — see the note in
    # settings.py; the room page renders them with no `C` at all.
    INSTITUTION_NAME = INSTITUTION_NAME
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
    # (J1, Julian 2026-08-13). oTree automatically SUMS player.payoff across
    # rounds into participant.payoff — wrong here, where only `payment_num_rewarded`
    # randomly selected rounds are paid, so the per-round result and the
    # amount paid are different numbers and must not share a field.
    # The template pays from participant.payoff_vector
    # (collected from this field on the last round), and oTree's own ledger
    # (participant.payoff) is written ONCE, from `earned`, when the results
    # page computes payment — so the admin Payments page and the participant's
    # receipt show the same figure with nothing to disagree.
    #
    # WHAT STOPS A STUDY DRIFTING BACK, AND WHAT DOES NOT (exp_pilots review,
    # 2026-08-14 — this comment used to claim the wrong one). Writing oTree's
    # `player.payoff` does raise under settings.AUTO_TABULATE_PAYOFFS=False,
    # but that raise is NOT a safety feature: it is oTree's own code
    # (otree/models/player.py:41-46), we cannot change it, and it fires INSIDE
    # A PARTICIPANT'S REQUEST. oTree has no migrations, so a build carrying
    # such a write gets deployed over live sessions and the first person
    # mid-round to reach it gets a DEAD PAGE, not a bookkeeping error.
    # `payoff_guard.assert_no_player_payoff_writes()`, called at boot from
    # `before/__init__.py`, is what actually protects them: a build containing
    # the write refuses to START, so it is caught at deploy time while the old
    # build is still serving. oTree's raise stays underneath as the floor for
    # the indirection a source scan cannot see; scripts/tests/payoff_ledger_test.py
    # §7/§8 pin both halves.
    round_payoff = models.CurrencyField(blank=True)
    # Passive measurement: time on page in ms, filled by a hidden field on the
    # page's OWN form (no side request). blank=True so an EMPTY submission (JS
    # disabled/blocked) is stored, not rejected. Only collected when the
    # telemetry_passive_capture flag is on.
    client_ms = models.LongStringField(blank=True)
    # PASSIVE FOCUS TRACE — per-page MEASUREMENT, filled by hidden fields on this
    # page's OWN form (no side request), the same reliable path as client_ms. A
    # SEPARATE OBSERVER from the tab monitor (tab_monitor_* participant fields):
    # it only MEASURES, never enforces — see _static/global/js/focus_trace.js and
    # DECISIONS.md. Named under the non-colliding `focus_trace_` family
    # DELIBERATELY: `tab_monitor_focus_loss_count` already exists and means a
    # different thing (long departures on monitored pages that count toward
    # disqualification), so the bare name `focus_loss_count` is NOT reused.
    # Both blank=True so an EMPTY submission (JS disabled/blocked) is stored, not
    # rejected — read them with field_maybe_none, never bare (CLAUDE.md). Only
    # collected when the telemetry_focus_trace flag is on.
    #
    # focus_trace_departures is bounded (blank still passes): an unbounded
    # IntegerField accepts an integer too large for SQLite and 500s the page at
    # flush. No honest browser gets near the cap. (Mirrors exp_pilots' bound.)
    focus_trace_departures = models.IntegerField(blank=True, min=0, max=10_000)
    focus_trace_unfocused_ms = models.FloatField(blank=True)
    # --- spare columns (future-proofing) -------------------------------------
    # Never rename in place. To repurpose one, record the mapping (with a date)
    # in CODEBOOK.md and add a rename-before-launch todo. See the repurpose
    # convention in CODEBOOK.md and docs/conventions.md.
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

    The removal half is `common.removed_from_study` — the ONE downstream belt
    (whole-app review A1): any recorded removal (tab-monitor DQ, screen-out,
    comprehension DQ, declined consent) hides every task page, so a page
    reload lands the participant on the ending instead of a task screen. Some
    of those states cannot reach this app today (routing walks them to the
    outro) — belted anyway; the membership note lives on the predicate.
    """
    if common.removed_from_study(player.participant):
        return False
    return is_active_round(player)


# FUNCTIONS

# PAGES

def task_template_vars(player) -> dict:
    """The template vars EVERY task page needs: the progress strip's numbers
    (main.progress_vars — one source for the text line and the bar). A TaskPage
    subclass that overrides vars_for_template must SPREAD this dict in (see
    GameStart / payoff) rather than retype the keys.

    (The tab_monitor gate is NOT here any more: the monitor include ships
    through css_bundle.html and gates itself on session.config, so no page
    has to remember to pass it — the monitored-by-default inversion.)"""
    return dict(progress_vars(player))


class TaskPage(participant_tab_monitor.MonitoredPage):
    """THE BASE EVERY TASK PAGE SUBCLASSES — the task-specific wiring, once.

    THE MONITOR WIRING IS NOT HERE ANY MORE — it generalised upward
    (2026-08-13, whole-app review B1): TaskPage began as the template's one
    use of page inheritance (J2: a page silently not armed for the monitor is
    worse than the cost of a base class), and that same reasoning now covers
    EVERY page after the agreement screen through
    `participant_tab_monitor.MonitoredPage`, which this subclasses. live_method
    and js_vars are inherited from there;
    what stays HERE is what makes a page a TASK page:
      * ``is_displayed = task_page_visible`` — round capping plus the
        removed-from-study belt;
      * ``vars_for_template`` -> task_template_vars — the progress strip's
        numbers. A page needing MORE vars overrides it and spreads
        ``task_template_vars(self)`` in.
    The template side keeps one shared piece: include
    ``_static/global/html/task_progress_strip.html`` in the header. (The
    monitor's script/stylesheet ship to every page via css_bundle.html — no
    per-template include left to forget.)

    TWO GOTCHAS, still live — participant_tab_monitor.py's docstring carries the
    full set:
      * oTree resolves page attributes AT IMPORT: a page that must NOT be
        monitored cannot just omit something — it says ``monitored = False``
        (never ``js_vars = None``, which 500s at render);
      * SUBCLASS THIS; never copy its attributes into a new page class —
        the page whose copy goes stale is the silently-unarmed page again.

    ``scripts/tests/task_page_test.py`` proves the arming structurally — a fresh
    subclass is armed by subclassing alone, and the served page carries the
    monitor config end-to-end.
    """
    is_displayed = staticmethod(task_page_visible)

    def vars_for_template(self):
        return task_template_vars(self)


# GROUP MATCHING: this template ships NONE. Reference code from a DIFFERENT
# study (a RoundStartWaitPage with perfect-stranger matching) lives in
# docs/group_matching_reference.py — read its header first: it references names
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
        # Each telemetry module's hidden field(s) ride on this page's own form,
        # added ONLY when that module is on. Two independent modules, two
        # independent flags — the focus trace is never gated on passive capture.
        fields = []
        if _flag(player, 'telemetry_passive_capture'):
            fields.append('client_ms')
        if _flag(player, 'telemetry_focus_trace'):
            fields += ['focus_trace_departures', 'focus_trace_unfocused_ms']
        return fields

    def vars_for_template(self):
        return dict(
            task_template_vars(self),
            telemetry_passive_capture=_flag(self, 'telemetry_passive_capture'),
            telemetry_focus_trace=_flag(self, 'telemetry_focus_trace'),
        )

    @staticmethod
    def before_next_page(player, timeout_happened):
        # Generate a payoff for this round before showing the payoff page.
        # Into round_payoff, NEVER player.payoff — see the field's comment.
        player.round_payoff = random.randint(1, 100)
        # Passive measurement: store the client-captured hidden fields (empty if
        # JS didn't run). No-op unless telemetry_passive_capture is on.
        if _flag(player, 'telemetry_passive_capture'):
            common.extra_set(player.participant, f'client_ms_round_{player.round_number}',
                             player.field_maybe_none('client_ms') or '')


def finish_task_block(player):
    """EVERY study's LAST task page must call this from before_next_page —
    it is what hands the task's results to the rest of the template.

    On the last DISPLAYED round (which may be earlier than C.NUM_ROUNDS for a
    shorter config) it collects every round's payoff into
    `participant.payoff_vector` — what `outro.compute_final_payoff` pays from
    — and stamps `task_done`, which the dashboard's task/outro boundary and
    the export read.

    A MODULE-LEVEL FUNCTION, DELIBERATELY, so it survives the deletion of the
    placeholder pages (main review S2): it used to live inline in the
    placeholder `payoff` class, where deleting that class deleted it — and
    the failure is the silent kind this template hunts: an empty vector means
    `outro.extract_round_payoffs` returns [], `selected_sum` is 0, and every
    participant is paid show-up plus quiz bonus only, with NO ERROR ANYWHERE.
    Omit the `task_done` stamp and the dashboard misplaces everyone at the
    task/outro boundary, equally silently. If you replace the task pages,
    your last page's before_next_page calls this — one line.
    """
    if player.round_number == rounds_for(player.session):
        payoff_vector = [pr.field_maybe_none('round_payoff') or cu(0)
                         for pr in player.in_rounds(1, player.round_number)]
        existing = player.participant.vars.get('payoff_vector', None)
        if existing is None:
            existing = []
        existing.extend(payoff_vector)
        player.participant.payoff_vector = existing
        common.stamp_stage(player.participant, common.STAGE_TASK_DONE)


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
        # The payoff-vector collection and the task_done stamp — the two
        # duties every replacement task app must keep (its docstring).
        finish_task_block(player)

page_sequence = [GameStart, payoff]

# MONITORED BY DEFAULT — every page above must be a
# participant_tab_monitor.MonitoredPage subclass or explicitly opted out; a page
# that dodged the rule fails the BOOT here, never a participant (see
# participant_tab_monitor.py).
participant_tab_monitor.assert_monitored_page_sequence(__name__, page_sequence)
