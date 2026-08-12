from otree.api import *
from otree import settings as otree_settings
import json
import time
import common
from settings import STATIC_VERSION
from .quiz_items import QUIZ_ITEMS

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

# Dynamically generate Player fields from QUIZ_ITEMS
def make_quiz_fields():
    fields = {
        'participant_label': models.StringField(blank=True),
        'redoinstructions': models.BooleanField(initial=0, blank=True),
        'skiptoquiz': models.BooleanField(initial=0, blank=True),
        'num_failed_attempts': models.IntegerField(initial=0),
        # EVERY GRADED QUIZ SUBMISSION, as a JSON list (see log_quiz_attempt and
        # CODEBOOK.md for the shape). It answers "which items do people get
        # wrong a lot", which the failure COUNT cannot. A real named field
        # rather than a participant var — a participant var reaches the export
        # only via PARTICIPANT_FIELDS, and participant_extra would mix this in
        # with everything else in that bucket — and rather than a spare column:
        # the spares exist to avoid a schema change on a LIVE study, and this
        # template has no data yet. Being a PER-ROUND player field, it separates
        # the first pass from the post-re-read pass (round 2) for free.
        'quiz_attempt_log': models.LongStringField(blank=True),
        # Spare columns (future-proofing) — never rename in place; see CODEBOOK.md.
        'spare_str_1': models.LongStringField(blank=True),
        'spare_str_2': models.LongStringField(blank=True),
    }
    for item in QUIZ_ITEMS:
        fields[item['field']] = models.StringField(
            label=item['prompt'],
            widget=widgets.RadioSelect,
            choices=item['choices']
        )
    return fields

class Player(BasePlayer):
    # Add all quiz fields and standard fields dynamically
    locals().update(make_quiz_fields())


# FUNCTIONS
def common_template_vars(session, group):
    return {

    }


def reread_available(player) -> bool:
    """True while the one-time lab re-read offer is open to this participant.

    Open means: the quiz_reread module is on, the participant has crossed the
    comprehension failure threshold, there is still a re-read round left, and
    the offer has not been consumed yet. Consumption happens the moment the
    participant enters the second pass (quiz.before_next_page), NOT when the
    offer modal is shown — dismissing the modal keeps the offer open.
    """
    cfg = player.session.config
    if not cfg.get('quiz_reread'):
        return False
    if player.round_number >= C.NUM_ROUNDS:
        return False  # no re-read round left to enter
    # Participant fields via .vars.get(), never getattr() (KeyError trap).
    if player.participant.vars.get('instructions_reread_used'):
        return False
    threshold = int(common.cfg(cfg, 'comprehension_max_failures'))
    failed = player.participant.vars.get('failed_attempts', 0) or 0
    return failed >= threshold


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

# PAGES    
class instructing(Page):
    template_name = 'intro/templates/instructing.html'
    form_model = 'player'
    form_fields = ['redoinstructions']

    def is_displayed(player):
        # Round 1: everyone. Round 2: only a lab participant who took the
        # one-time re-read offer (Prolific never reaches it).
        if common.is_screened_out(player.participant):
            return False  # mobile screen-out: walked straight to the ending
        return player.round_number == 1 or in_reread_pass(player)

    def vars_for_template(player):
        # Stag Hunt example: surface every variable referenced in
        # intro/instructions_text.html so the template ships as a working
        # demonstration of variable substitution and treatment-conditional
        # content. Replace this when you swap in your own instructions.
        cfg = player.session.config
        return {
            # MONEY IS FORMATTED ONCE, THE SAME WAY, EVERYWHERE
            # (improvement_suggestions item 4, Julian 2026-08-12). The consent
            # and results pages render currency through oTree's cu(), so the
            # instructions must too — a participant who was promised "2.5 EUR"
            # and is paid "€2.50" is comparing two spellings of the same money.
            # The templates therefore print `{{ showup }}` with NO hand-written
            # unit after it: the unit comes from the currency formatting, and a
            # study that changes REAL_WORLD_CURRENCY_CODE gets it everywhere.
            # Read through common.cfg so a frozen session config falls back to
            # the shipped default instead of 500-ing.
            'showup': cu(common.cfg(cfg, 'showup') or 0),
            'quiz_bonus': cu(common.cfg(cfg, 'quiz_bonus') or 0),
            'num_experimental_rounds': cfg.get('num_experimental_rounds'),
            # Read participant vars with .vars.get(), never getattr() (KeyError trap).
            'treatment': player.participant.vars.get('treatment_group', ''),
            'stag_payoff': C.STAG_PAYOFF,
            'hare_payoff': C.HARE_PAYOFF,
            'stag_alone': C.STAG_ALONE,
            # Testing-only skip button; False whenever OTREE_PRODUCTION is set.
            'is_debug': otree_settings.DEBUG,
        }

    def before_next_page(player, timeout_happened):
        stage = 'instructions_done' if player.round_number == 1 else 'instructions_reread_done'
        common.stamp_stage(player.participant, stage)

class quiz(Page):
    template_name = 'intro/templates/quiz.html'
    form_model = 'player'
    # Dynamically include only the quiz items that have corresponding Player fields
    quiz_items = [item for item in QUIZ_ITEMS if hasattr(Player, item['field'])]
    quiz_field_names = [item['field'] for item in quiz_items]
    quiz_solutions = [item['answer'] for item in quiz_items]

    def get_form_fields(player):
        # Use class attribute to avoid attribute errors when oTree passes the Player instance
        return quiz.quiz_field_names + ['redoinstructions']

    def is_displayed(player):
        # Round 1: everyone. Round 2: only the lab re-read pass.
        if common.is_screened_out(player.participant):
            return False  # mobile screen-out: walked straight to the ending
        return player.round_number == 1 or in_reread_pass(player)

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
        # Define mapping of quiz fields to their correct answers
        solutions = dict(zip(quiz.quiz_field_names, quiz.quiz_solutions))
        # Check answers
        wrong = [
            key for key in solutions
            if values.get(key, '') != solutions[key]
        ]
        # Log EVERY graded submission, passing ones included — so the last entry
        # is the passing attempt for anyone who got through, and a failure for
        # anyone disqualified or abandoning mid-quiz (CODEBOOK.md).
        log_quiz_attempt(player, {k: values.get(k, '') for k in solutions}, wrong)
        if wrong:
            player.num_failed_attempts += 1
            player.participant.failed_attempts += 1
            cfg = player.session.config
            # COMPREHENSION-FAILURE DISQUALIFICATION (module, off by default).
            # When enabled, a participant who fails too many times is not blocked
            # again — they are flagged and allowed through to the disqualified
            # ending (see app_after_this_page and the outro Disqualified page).
            if cfg.get('comprehension_dq'):
                max_fail = int(common.cfg(cfg, 'comprehension_max_failures'))
                if player.participant.failed_attempts >= max_fail:
                    player.participant.comprehension_disqualified = True
                    common.set_exit_code(
                        player.participant, common.EXIT_CODES['comprehension'])
                    return  # no error -> the page advances to the ending
            return "One or more quiz answers are wrong."

    def vars_for_template(self):
        # Solutions reach the browser only under settings.DEBUG (i.e. when
        # OTREE_PRODUCTION is unset), where they power the testing skip
        # button. In production nothing is sent.
        is_debug = otree_settings.DEBUG
        solution_pairs = []
        if is_debug:
            solution_pairs = [
                dict(name=field, value=solution)
                for field, solution in zip(quiz.quiz_field_names, quiz.quiz_solutions)
            ]
        cfg = self.session.config
        # Lab quiz-failure modals. Both are computed server-side and rendered
        # only on a re-render that follows a wrong submission IN THIS ROUND
        # (num_failed_attempts is a per-round player field, so entering round 2
        # never pops a stale modal). offer_reread: the one-time re-read offer
        # is open. show_experimenter: no offer is open — a dismissible
        # "raise your hand" notice; nothing is recorded for it (failed_attempts
        # is the experimenter's record).
        #
        # THE NOTICE IS KEYED ON THE THRESHOLD AND THE STUDY TYPE, NOT ON THE
        # quiz_reread MODULE (Julian, 2026-08-12). It used to require
        # quiz_reread AND instructions_reread_used, which meant a lab session
        # that turned the re-read module off got NO help at all: no offer, no
        # at-will dialog (suppressed for lab below) and no notice — just the
        # inline error, forever, with the experimenter never called. The lab
        # rule is "crossing comprehension_max_failures starts the study
        # helping", so the notice appears whenever the threshold has been
        # crossed and no re-read offer is currently open. Prolific never shows
        # it: there is no experimenter to raise a hand to.
        failed_this_round = self.num_failed_attempts >= 1
        offer_reread = failed_this_round and reread_available(self)
        threshold = int(common.cfg(cfg, 'comprehension_max_failures'))
        # Participant fields via .vars.get(), never getattr() (KeyError trap).
        failed_total = self.participant.vars.get('failed_attempts', 0) or 0
        show_experimenter = (
            failed_this_round
            and common.cfg(cfg, 'recruitment') == 'lab'
            and failed_total >= threshold
            and not offer_reread
        )
        # ESCALATION, derived from the SAME threshold — no new setting. At twice
        # comprehension_max_failures the notice also names the number of
        # attempts. 0 means "not escalated"; the template shows the extra line
        # only when this is non-zero.
        experimenter_attempts = failed_total if failed_total >= 2 * threshold else 0
        # THE AT-WILL RE-READ DIALOG (change_requests item 17). ONLINE ONLY.
        # Online there is no experimenter to ask, so the instructions are always
        # one click away, in a dialog on this page, whether or not the
        # participant has failed. The LAB deliberately has NO at-will re-read
        # (Julian, 2026-08-11): a lab participant gets the failure-driven offer
        # (the quiz_reread module) up to the allowed number of attempts and then
        # raises their hand. Two re-read mechanisms on one page would also read
        # as a contradiction. Keyed on the study type, not on quiz_reread, so a
        # lab session that never enabled that module still gets the lab rule.
        show_reread_dialog = common.cfg(cfg, 'recruitment') != 'lab'
        return {
            'quiz_solutions_json': json.dumps(solution_pairs),
            'is_debug': is_debug,
            'offer_reread': offer_reread,
            'show_experimenter': show_experimenter,
            'experimenter_attempts': experimenter_attempts,
            'show_reread_dialog': show_reread_dialog,
            # Context for the instructions included INSIDE that dialog. It is
            # the real intro/instructions_text.html, so it needs exactly the
            # variables the instructions page passes it — keep these in step
            # with instructing.vars_for_template above or the recap silently
            # renders blanks where the numbers should be. The money goes through
            # cu() here for the same reason it does there: one format for one
            # amount, everywhere in the study.
            'showup': cu(common.cfg(cfg, 'showup') or 0),
            'quiz_bonus': cu(common.cfg(cfg, 'quiz_bonus') or 0),
            'num_experimental_rounds': cfg.get('num_experimental_rounds'),
            'treatment': self.participant.vars.get('treatment_group', ''),
            'stag_payoff': C.STAG_PAYOFF,
            'hare_payoff': C.HARE_PAYOFF,
            'stag_alone': C.STAG_ALONE,
        }

    def before_next_page(player, timeout_happened):
        common.stamp_stage(player.participant, 'quiz_done')
        # Taking the re-read offer: consume it HERE — the moment the
        # participant leaves for the second pass — not when the modal opened.
        # (field_maybe_none: redoinstructions is blank=True and may arrive empty.)
        if player.field_maybe_none('redoinstructions') and reread_available(player):
            player.participant.instructions_reread_used = True
            common.stamp_stage(player.participant, 'reread_taken')

    def app_after_this_page(player, upcoming_apps):
        # Route a comprehension-disqualified participant straight to the ending
        # app, skipping the task entirely.
        if player.participant.vars.get('comprehension_disqualified'):
            return upcoming_apps[-1]


class AISafetyAgree(Page):
    """Arms the tab-switch monitor. Shown only when tab_monitor is on.

    On submit the template sets sessionStorage.aiSafetyAgreed = '1'; the monitor
    JS stays dormant until then, so this page marks exactly where monitoring
    begins.
    """
    template_name = 'intro/templates/ai_safety.html'

    @staticmethod
    def is_displayed(player):
        # Arm once, after the round-1 quiz; never in the re-read round, and
        # never for a participant the mobile screen-out already removed.
        if common.is_screened_out(player.participant):
            return False
        return player.round_number == 1 and bool(player.session.config.get('tab_monitor'))


page_sequence = [instructing, quiz, AISafetyAgree]

