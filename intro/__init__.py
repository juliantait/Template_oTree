from otree.api import *
from otree import settings as otree_settings
import json
import time
import common
import monitoring
from settings import STATIC_VERSION
from .quiz_items import QUIZ_ITEMS

# One implementation, in common.flag (raw config.get — see its docstring for
# why it is NOT common.cfg).
_flag = common.flag

doc = """
Intro
"""
class C(BaseConstants):
    # Asset cache-buster for this BUILD (settings.STATIC_VERSION).
    # Templates read C.STATIC_VERSION, never session.config.static_version:
    # a session config is frozen at creation, so the template read 500s
    # for in-flight participants when the parameter post-dates them.
    STATIC_VERSION = STATIC_VERSION
    NAME_IN_URL = 'Introduction'
    # Instructions + quiz are individual; no grouping.
    PLAYERS_PER_GROUP = None
    # Round 1 is the normal instructions + quiz pass. Round 2 is the lab
    # re-read pass (quiz_reread module): reachable only after a participant
    # takes the one-time re-read offer, so for everyone else every round-2
    # page returns is_displayed False (empty export rows, by design).
    NUM_ROUNDS = 2
    # Example figures referenced by intro/instructions_text.html to demonstrate
    # variable substitution. Replace with your own study's numbers.
    STAG_PAYOFF = 4
    HARE_PAYOFF = 2
    STAG_ALONE = 0



class Subsession(BaseSubsession):
    pass
      
class Group(BaseGroup):
    pass

# THE QUIZ, derived ONCE from QUIZ_ITEMS. make_quiz_item_fields builds a
# Player field for every entry of the same list these two are derived from, so
# every name here has a field by construction.
QUIZ_FIELD_NAMES = [item['field'] for item in QUIZ_ITEMS]
QUIZ_SOLUTIONS = {item['field']: item['answer'] for item in QUIZ_ITEMS}


def make_quiz_item_fields():
    """One radio StringField per QUIZ_ITEMS entry (the dynamic Player fields)."""
    return {
        item['field']: models.StringField(
            label=item['prompt'],
            widget=widgets.RadioSelect,
            choices=item['choices'],
        )
        for item in QUIZ_ITEMS
    }


class Player(BasePlayer):
    # True on the quiz POST that takes the lab's one-time re-read offer.
    redoinstructions = models.BooleanField(initial=0, blank=True)
    # Wrong quiz submissions THIS ROUND (the participant-level total lives in
    # participant.failed_attempts; see quiz_modal_state for why both exist).
    num_failed_attempts = models.IntegerField(initial=0)
    # EVERY GRADED QUIZ SUBMISSION, as a JSON list (see log_quiz_attempt and
    # CODEBOOK.md for the shape). It answers "which items do people get
    # wrong a lot", which the failure COUNT cannot. A real named field
    # rather than a participant var — a participant var reaches the export
    # only via PARTICIPANT_FIELDS, and participant_extra would mix this in
    # with everything else in that bucket — and rather than a spare column:
    # the spares exist to avoid a schema change on a LIVE study, and this
    # template has no data yet. Being a PER-ROUND player field, it separates
    # the first pass from the post-re-read pass (round 2) for free.
    quiz_attempt_log = models.LongStringField(blank=True)
    # Spare columns (future-proofing) — never rename in place; see CODEBOOK.md.
    spare_str_1 = models.LongStringField(blank=True)
    spare_str_2 = models.LongStringField(blank=True)
    # One radio field per quiz item, from the same list the solutions above
    # are derived from.
    locals().update(make_quiz_item_fields())


# FUNCTIONS
def comprehension_threshold(cfg) -> int:
    """`comprehension_max_failures` as an int, via the safe accessor."""
    return int(common.cfg(cfg, 'comprehension_max_failures'))


def reread_available(player) -> bool:
    """True while the one-time lab re-read offer is open to this participant.

    Open means: the quiz_reread module is on, the participant has crossed the
    comprehension failure threshold, there is still a re-read round left, and
    the offer has not been consumed yet. Consumption happens the moment the
    participant enters the second pass (quiz.before_next_page), NOT when the
    offer modal is shown — dismissing the modal keeps the offer open.
    """
    cfg = player.session.config
    if not _flag(player, 'quiz_reread'):
        return False
    if player.round_number >= C.NUM_ROUNDS:
        return False  # no re-read round left to enter
    # Participant fields via .vars.get(), never getattr() (KeyError trap).
    if player.participant.vars.get('instructions_reread_used'):
        return False
    failed = player.participant.vars.get('failed_attempts', 0) or 0
    return failed >= comprehension_threshold(cfg)


def log_quiz_attempt(player, answers, wrong_fields):
    """Append one graded quiz submission to this round's log. NEVER raises.

    Records what was answered per item, WHICH ITEMS WERE WRONG **as judged at
    the time**, the attempt number and a timestamp. Correctness is stored, not
    recomputed later, because `intro/quiz_items.py` changes between studies (and
    can change between sessions of one study): a re-grade against a different
    item set would be silently wrong, with nothing to notice it by.

    INSTRUMENTATION MUST NEVER BREAK A PAGE (CLAUDE.md). Everything below is
    wrapped: if the log cannot be written — a value that will not serialise, a
    corrupted column — the participant still gets their answer graded and still
    proceeds, and the only loss is one row of measurement.

    Not every POST to the quiz is an attempt: the re-read shortcut and the
    DEBUG clickthrough both return before grading, so neither is logged.

    EVERY attempt is stored, however many there are — deliberately UNCAPPED
    (Julian, 2026-08-12), even though lab attempts are themselves unlimited.
    The log exists for occasional curiosity about which items people get wrong,
    not as routine analysis data, so completeness matters more than column size.
    """
    try:
        raw = player.field_maybe_none('quiz_attempt_log') or ''
        entries = json.loads(raw) if raw else []
        if not isinstance(entries, list):
            entries = []
        entries.append({
            'n': len(entries) + 1,
            't': round(time.time(), 3),
            # Truncated: these are radio choices from our own item set, but the
            # column must not be shapeable by a hand-crafted POST.
            'answers': {f: str(v)[:80] for f, v in answers.items()},
            'wrong': list(wrong_fields),
        })
        player.quiz_attempt_log = json.dumps(entries)
    except Exception:
        pass  # measurement only: never block the participant


def in_reread_pass(player) -> bool:
    """True on round-2 pages, which only the lab re-read pass reaches."""
    if player.round_number == 1:
        return False
    return bool(player.participant.vars.get('instructions_reread_used'))


def intro_page_visible(player) -> bool:
    """The ONE `is_displayed` predicate for both intro pages.

    Round 1: everyone. Round 2: only a lab participant who took the one-time
    re-read offer (Prolific never reaches it) — everyone else's round-2 pages
    return False (empty export rows, by design; see C.NUM_ROUNDS).

    Never a participant with a recorded removal — `common.removed_from_study`,
    the ONE downstream belt (whole-app review A1; this used to check
    `screened_out` alone). The tab-monitor half is LIVE, not a belt: these
    pages are monitored (monitoring.MonitoredPage), so a mid-quiz
    disqualification's reload must land on the ending, not back on the quiz.
    The screen-out half stays the belt to the soft wall's brace — the gate
    HOLDS such a participant on before.welcome, so they never reach this app.
    """
    if common.removed_from_study(player.participant):
        return False
    return player.round_number == 1 or in_reread_pass(player)


def instructions_context(player) -> dict:
    """Every variable intro/instructions_text.html renders — the ONE builder.

    TWO pages show that file: the instructions page, and the quiz's at-will
    re-read dialog. A key present for one and missing for the other renders
    SILENTLY as a blank (no error, no failing test), so both pages must build
    this dict here and nowhere else.

    MONEY IS FORMATTED ONCE, THE SAME WAY, EVERYWHERE (improvement_suggestions
    item 4, Julian 2026-08-12). The consent and results pages render currency
    through oTree's cu(), so the instructions must too — a participant who was
    promised "2.5 EUR" and is paid "€2.50" is comparing two spellings of the
    same money. The templates therefore print `{{ showup }}` with NO
    hand-written unit after it: the unit comes from the currency formatting,
    and a study that changes REAL_WORLD_CURRENCY_CODE gets it everywhere.

    Everything is read through common.cfg so a frozen session config falls
    back to the shipped default instead of 500-ing (or, for
    num_experimental_rounds, rendering the word "None" into the page).

    The Stag Hunt keys are the shipped demonstration of variable substitution
    and treatment-conditional content — replace them when you swap in your own
    instructions.
    """
    cfg = player.session.config
    return {
        # BARE READS, DELIBERATELY — no `or 0` (B4, Julian 2026-08-13). These
        # used to be guarded with `or 0`, which silently promised €0.00 for a
        # config that set the value to None while the PAYMENT side read the
        # same key bare and crashed at Results — the worst split of one value.
        # One policy now, and it is the payment path's own: failing loudly
        # beats silently promising somebody nothing.
        'showup': cu(common.cfg(cfg, 'showup')),
        'quiz_bonus': cu(common.cfg(cfg, 'quiz_bonus')),
        'num_experimental_rounds': common.cfg(cfg, 'num_experimental_rounds'),
        # Participant fields via .vars.get(), never getattr() (KeyError trap).
        'treatment': player.participant.vars.get('treatment_group', ''),
        'stag_payoff': C.STAG_PAYOFF,
        'hare_payoff': C.HARE_PAYOFF,
        'stag_alone': C.STAG_ALONE,
    }


def quiz_modal_state(player) -> dict:
    """Which quiz-failure help THIS render of the quiz shows (lab modals and
    the online at-will dialog). Server-side, in one place, because the template
    must only ever reveal what the server decided.

    The lab modals are rendered only on a re-render that follows a wrong
    submission IN THIS ROUND (num_failed_attempts is a per-round player field,
    so entering round 2 never pops a stale modal). offer_reread: the one-time
    re-read offer is open. show_experimenter: no offer is open — a dismissible
    "raise your hand" notice; nothing is recorded for it (failed_attempts is
    the experimenter's record).

    THE NOTICE IS KEYED ON THE THRESHOLD AND THE STUDY TYPE, NOT ON THE
    quiz_reread MODULE (Julian, 2026-08-12). It used to require quiz_reread
    AND instructions_reread_used, which meant a lab session that turned the
    re-read module off got NO help at all: no offer, no at-will dialog
    (suppressed for lab below) and no notice — just the inline error, forever,
    with the experimenter never called. The lab rule is "crossing
    comprehension_max_failures starts the study helping", so the notice
    appears whenever the threshold has been crossed and no re-read offer is
    currently open. Prolific never shows it: there is no experimenter to raise
    a hand to.

    ESCALATION, derived from the SAME threshold — no new setting. At twice
    comprehension_max_failures the notice also names the number of attempts.
    experimenter_attempts is 0 for "not escalated"; the template shows the
    extra line only when it is non-zero.

    THE AT-WILL RE-READ DIALOG (change_requests item 17). ONLINE ONLY. Online
    there is no experimenter to ask, so the instructions are always one click
    away, in a dialog on the quiz page, whether or not the participant has
    failed. The LAB deliberately has NO at-will re-read (Julian, 2026-08-11):
    a lab participant gets the failure-driven offer (the quiz_reread module)
    up to the allowed number of attempts and then raises their hand. Two
    re-read mechanisms on one page would also read as a contradiction. Keyed
    on the study type, not on quiz_reread, so a lab session that never enabled
    that module still gets the lab rule.
    """
    cfg = player.session.config
    failed_this_round = player.num_failed_attempts >= 1
    offer_reread = failed_this_round and reread_available(player)
    threshold = comprehension_threshold(cfg)
    # Participant fields via .vars.get(), never getattr() (KeyError trap).
    failed_total = player.participant.vars.get('failed_attempts', 0) or 0
    show_experimenter = (
        failed_this_round
        and common.is_lab(cfg)
        and failed_total >= threshold
        and not offer_reread
    )
    return {
        'offer_reread': offer_reread,
        'show_experimenter': show_experimenter,
        'experimenter_attempts':
            failed_total if failed_total >= 2 * threshold else 0,
        'show_reread_dialog': not common.is_lab(cfg),
    }


# PAGES
class instructing(monitoring.MonitoredPage):
    # MONITORED (monitoring.MonitoredPage): the agreement page the participant
    # just passed warns against consulting an AI assistant during exactly this
    # reading — the pages it protects must be the pages it watches.
    template_name = 'intro/templates/instructing.html'
    # NO form_model/form_fields: this page only advances. redoinstructions is
    # a QUIZ field (the POST that takes the re-read offer); declaring it here
    # rendered no control and stored nothing.
    is_displayed = staticmethod(intro_page_visible)

    @staticmethod
    def vars_for_template(player):
        return {
            **instructions_context(player),
            # WHICH PASS THIS IS, for intro/prequiz_text.html (Julian,
            # 2026-08-13). The re-read pass must not repeat the bonus/first-
            # attempt sentence: whoever reaches it has already failed, so the
            # bonus is gone and there is no second "first attempt". Passed as a
            # server-side fact rather than letting the template compare round
            # numbers — in_reread_pass is the one definition of "this is the
            # second pass" and every reader of it must go through it.
            'is_reread_pass': in_reread_pass(player),
            # Testing-only skip button; False whenever OTREE_PRODUCTION is set.
            'is_debug': otree_settings.DEBUG,
        }

    @staticmethod
    def before_next_page(player, timeout_happened):
        stage = (common.STAGE_INSTRUCTIONS_DONE if player.round_number == 1
                 else common.STAGE_INSTRUCTIONS_REREAD_DONE)
        common.stamp_stage(player.participant, stage)

class quiz(monitoring.MonitoredPage):
    # MONITORED (monitoring.MonitoredPage): this is the very check that gates
    # entry to the study — the page the 2026-08-12 agreement-page move existed
    # to protect. A violation here ejects exactly as on a task page.
    template_name = 'intro/templates/quiz.html'
    form_model = 'player'
    is_displayed = staticmethod(intro_page_visible)

    @staticmethod
    def get_form_fields(player):
        return QUIZ_FIELD_NAMES + ['redoinstructions']

    @staticmethod
    def error_message(player, values):
        # verify_quiz=False is a DEBUG loosening (clickthrough), honoured only
        # while DEBUG is on — in production validation always runs, whatever
        # the config says.
        if otree_settings.DEBUG and not common.cfg(player.session.config, 'verify_quiz'):
            return
        # A participant taking the re-read offer is not submitting answers, so
        # don't validate them. Honoured ONLY while the offer is actually open
        # (lab flow, threshold crossed, not yet consumed) — a hand-crafted POST
        # of redoinstructions=1 cannot bypass validation in any other state.
        if values.get('redoinstructions') and reread_available(player):
            return
        wrong = [
            key for key in QUIZ_SOLUTIONS
            if values.get(key, '') != QUIZ_SOLUTIONS[key]
        ]
        # Log EVERY graded submission, passing ones included — so the last entry
        # is the passing attempt for anyone who got through, and a failure for
        # anyone disqualified or abandoning mid-quiz (CODEBOOK.md).
        log_quiz_attempt(player, {k: values.get(k, '') for k in QUIZ_SOLUTIONS}, wrong)
        if wrong:
            player.num_failed_attempts += 1
            player.participant.failed_attempts += 1
            cfg = player.session.config
            # COMPREHENSION-FAILURE DISQUALIFICATION (module, off by default).
            # When enabled, a participant who fails too many times is not blocked
            # again — they are flagged and allowed through to the disqualified
            # ending (see app_after_this_page and the outro Disqualified page).
            if _flag(player, 'comprehension_dq'):
                if player.participant.failed_attempts >= comprehension_threshold(cfg):
                    player.participant.comprehension_disqualified = True
                    common.set_exit_code(
                        player.participant, common.EXIT_CODES['comprehension'])
                    return  # no error -> the page advances to the ending
            return "One or more quiz answers are wrong."

    @staticmethod
    def vars_for_template(player):
        # Solutions reach the browser only under settings.DEBUG (i.e. when
        # OTREE_PRODUCTION is unset), where they power the testing skip
        # button. In production nothing is sent.
        is_debug = otree_settings.DEBUG
        solution_pairs = []
        if is_debug:
            solution_pairs = [
                dict(name=field, value=solution)
                for field, solution in QUIZ_SOLUTIONS.items()
            ]
        return {
            # The at-will re-read dialog includes the REAL
            # intro/instructions_text.html, so this page needs exactly the
            # variables the instructions page passes it — both go through
            # instructions_context, the one builder, so the recap cannot
            # silently render blanks where the numbers should be.
            **instructions_context(player),
            **quiz_modal_state(player),
            'quiz_solutions_json': json.dumps(solution_pairs),
            'is_debug': is_debug,
        }

    @staticmethod
    def before_next_page(player, timeout_happened):
        common.stamp_stage(player.participant, common.STAGE_QUIZ_DONE)
        # Taking the re-read offer: consume it HERE — the moment the
        # participant leaves for the second pass — not when the modal opened.
        # (field_maybe_none: redoinstructions is blank=True and may arrive empty.)
        if player.field_maybe_none('redoinstructions') and reread_available(player):
            player.participant.instructions_reread_used = True
            common.stamp_stage(player.participant, common.STAGE_REREAD_TAKEN)

    @staticmethod
    def app_after_this_page(player, upcoming_apps):
        # Route a comprehension-disqualified participant straight to the ending
        # app, skipping the task entirely.
        if player.participant.vars.get('comprehension_disqualified'):
            return upcoming_apps[-1]


# THE TAB-MONITOR AGREEMENT PAGE IS NOT HERE ANY MORE — it moved to the
# `before` app on 2026-08-12, and it must not move back. It used to sit LAST in
# this sequence (instructing, quiz, AISafetyAgree), which armed the monitor
# only AFTER the comprehension quiz — leaving the instructions and the quiz
# itself unmonitored, so a participant could consult an AI assistant during the
# very check that gates entry to the study, which is exactly what that page's
# text warns against. It now sits after the consent/ID pages in `before`, AND
# — since 2026-08-13 — these pages really are monitored (they subclass
# monitoring.MonitoredPage), so everything a participant is asked to do alone
# is covered. Between those two dates the previous sentence was a claim the
# code did not honour: the agreement page had moved but no monitor wiring
# existed here, so the quiz stayed unwatched with nothing to say so — see the
# 2026-08-13 DECISIONS.md entry. `before.AISafetyAgree` has the arming story.
page_sequence = [instructing, quiz]

# MONITORED BY DEFAULT — every page above must be a monitoring.MonitoredPage
# subclass or explicitly opted out; a page that dodged the rule fails the BOOT
# here, never a participant (see monitoring.py).
monitoring.assert_monitored_page_sequence(__name__, page_sequence)

