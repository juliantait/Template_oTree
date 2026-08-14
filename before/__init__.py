# The entry app: welcome, consent, and (online) external-ID / device capture.
# - startpage: lab hold screen shown only for experimenter-run (lab) sessions.
# - welcome: welcome + consent; captures the external participant id and device
#   info when those modules are enabled. Non-consenters are routed straight to
#   the outro (they never see the task).
#
#   IT IS ALSO WHERE THE DEVICE ALLOW-LIST IS DECIDED AND WHERE A SCREENED-OUT
#   PARTICIPANT IS HELD. The entry request's User-Agent is classified
#   server-side in `welcome.get()`, before a byte of consent exists; a device
#   the study's `allowed_devices` list excludes is recorded with exit code -4
#   and served `before/screened_out.html` INSTEAD of the consent page, on this
#   same page index. Holding them here rather than walking them to the outro is
#   what makes the wall SOFT: they never advance, so every later request lands
#   on this page and is re-decided, and coming back on an acceptable device
#   before consent LIFTS the screen-out and shows them consent. See
#   `_apply_device_gate` for the rules and the asymmetry between screening and
#   clearing. With the shipped list (all four types) none of it does anything.
# - ConfirmProlificID: confirm the platform id. Its free-text field is the one
#   route in this template that can produce a DUPLICATE participant label, which
#   is a permanent lockout in oTree — see identity.py.
#
# ADDING A PAGE HERE? THE ONE RULE THIS APP KEEPS RE-LEARNING:
#
#       **FLAGS DECIDE MECHANICS, `recruitment` DECIDES COPY.**
#
# A module flag says what machinery exists — `prolific_completion_redirects` means we
# hold a completion code, `prolific_capture_participant_id` means we collect a platform
# id. Neither means "the participant is on Prolific", and neither may be used as
# a stand-in for it. Every sentence a participant READS that names the platform,
# or the room, or how to reach a human, branches on `common.is_lab` /
# `common.is_prolific`; only the machinery itself (does a link exist? is there a
# field to fill?) branches on a flag.
#
# This app broke that rule twice at once and it cost a participant DEAD END: the
# consent page guessed "Prolific" from `prolific_capture_participant_id` while the
# screen-out page guessed it from `prolific_completion_redirects`, so a
# `recruitment='prolific'` session with `prolific_completion_redirects` off told people
# to contact the researchers *through Prolific* and then served them a
# screen-out page with no way out at all.
#
# AND WHERE A STUDY TYPE OWES SOMETHING, IT IS ENFORCED, NOT DOCUMENTED. A
# Prolific participant has no experimenter to ask, so a Prolific study must
# offer a screened-out participant an exit; `settings._prelaunch_problems`
# refuses a prolific config that has no `prolific_screenout_return_url`, so the broken
# combination cannot reach a participant at all. A rule in prose is one somebody
# can configure their way past. The full argument is above `common.is_lab`;
# tests/copy_routing_test.py asserts the impossibility.

from otree.api import *
import common
import identity
import payoff_guard
from settings import STATIC_VERSION
from . import treatment_assignment

# Make oTree's entry lookup unable to raise MultipleResultsFound on a duplicate
# label (identity.py, defence 2). settings.py installs it too, as early as it
# can, because the room's entry views are reachable before any app module is
# imported; that early attempt is allowed to fail quietly (the views module may
# legitimately not be importable yet).
#
# THIS IS THE ASSERTING POINT — the last install point, and the only place a
# missing guard is treated as a failure. By now oTree has imported the app
# modules at boot, so `otree.views.participant` MUST be importable and a failure
# here is version drift, not ordering. It raises, failing the BOOT rather than a
# participant's page. See identity.assert_duplicate_label_guard for why the
# alternative placement (first participant entry) would be the wrong trade.
identity.assert_duplicate_label_guard()

# SAME PLACEMENT, SAME ARGUMENT, DIFFERENT DEFECT (exp_pilots review,
# 2026-08-14). `settings.AUTO_TABULATE_PAYOFFS=False` makes oTree's OWN
# `player.payoff` setter raise, and that raise lands INSIDE A PARTICIPANT'S
# REQUEST — a dead page mid-round for whoever is part-way through when a build
# carrying such a write is deployed over live sessions (oTree has no
# migrations). So the write is caught HERE instead: at boot, before anybody is
# served, where the operator sees it while the old build is still running. The
# check reads app SOURCE, so it is complete regardless of import order and of
# which paths a test happens to walk; the indirection it cannot see is covered
# from the other side by tests/payoff_ledger_test.py §7. Full argument in
# payoff_guard.py's docstring.
payoff_guard.assert_no_player_payoff_writes()

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
    # form_fields when explicit_consent is on (see get_form_fields), so an
    # implicit-consent variant (the lab profile) is unaffected and leaves it
    # null — read it with
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
    # DUPLICATE-ID TRIAGE (identity.py). Empty for everybody normally. When a
    # participant's typed id is already held by ANOTHER row in this session, the
    # claim is REFUSED — they keep their own row and finish the study, their
    # typed value is still stored verbatim in `participant_id_external`, and
    # this column carries the OWNING ROW's participant code so payment triage
    # can find both sides. Silent to the participant, by design.
    prolific_label_conflict = models.StringField(blank=True)
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


# One implementation, in common.flag (raw config.get — see its docstring for
# why it is NOT common.cfg).
_flag = common.flag


def _apply_device_gate(player, user_agent):
    """DEVICE ALLOW-LIST GATE — a SOFT WALL decided on the consent page's own
    request, before a byte of consent is rendered.

    The study STATES which device types it accepts (`allowed_devices`: any of
    'phone', 'tablet', 'computer', 'unknown'); anything else is screened out at
    entry and held on this page (see `welcome.get_template_name`).

    NO-OP BY DEFAULT. The shipped list is all four types, so every device is
    permitted and this function changes nothing a participant could see.
    (device_capture still RECORDS the device as measurement; it never blocks
    anyone.)

    THE SERVER DECIDES, from this request's User-Agent. The client's own idea of
    what it is arrives later, in the device-info JSON, and is kept beside this
    for comparison — but a client-side check is trivially bypassed, so it never
    gates. See `common.device_gate_decision`.

    WHY THE VERDICT IS NOT FINAL. oTree rematches a returning participant to the
    SAME row by participant label, so a naive "record it once, read the record
    for ever" screen-out locks somebody who reopens the study on a computer into
    the screen-out page for good — and on Prolific their submission stays open
    until they return it, while returning it means they can never retake the
    study. So:

      * THE VERDICT IS WRITTEN IMMEDIATELY, at decision time, not when the
        screen-out page renders. Somebody who reads that page and closes the tab
        still exports as a screen-out rather than as an abandoner. That property
        is the reason the write lives here — do not move it;
      * EVERY LATER PRE-CONSENT REQUEST IS RE-DECIDED. Positive evidence of a
        device the study accepts CLEARS the screen-out (`common.
        clear_screened_out` reverts the terminal marking), because somebody who
        is really doing the study must not sit in the data as screened out;
      * A CLEARED PARTICIPANT WHO COMES BACK ON A REJECTED DEVICE before consent
        is screened again, or the clear would be a permanent bypass;
      * AFTER CONSENT THE CHECK DOES NOT APPLY and never touches the
        participant, whatever device their next request comes from. The boundary
        is the durable `consent_submitted` flag, never a page index.

    THE ASYMMETRY (common.device_screens_out / device_clears_screenout, whose
    docstrings carry the full argument): an UNDETERMINED classification — no
    request, no header, garbage, an exception — ALLOWS on entry and records
    NOTHING, but can never CLEAR an existing screen-out. Absence of evidence is
    not evidence that somebody switched device; if it were, anyone screened out
    could lift their own screen-out by sending no User-Agent.

    Idempotent — a refresh re-decides identically, re-stamps nothing, and adds
    no history entry.
    """
    participant = player.participant

    # PAST THE BOUNDARY: not our business any more.
    if common.consent_submitted(participant):
        return

    detected, screens_out, clears = common.device_gate_decision(
        player.session.config, user_agent)

    # NO DECISION. There was no usable User-Agent to classify, so this request
    # is not evidence of anything: the participant proceeds (fail open) and
    # NOTHING is written — no verdict, no device type, no history. If they are
    # already screened out they simply STAY screened out, because clearing needs
    # positive evidence and this is the absence of it.
    if detected == common.UNDETERMINED:
        return

    # Measurement, recorded for EVERY participant including the ones let
    # through: it is the server's own classification of the entry request, and
    # analysis wants it whether or not the gate was narrowed.
    common.extra_set(participant, 'entry_device_type', detected)

    was_screened = common.is_screened_out(participant)
    if screens_out and not was_screened:
        # 'rescreened' when they had been cleared before — that is a device
        # switch in the other direction, and it must be visible as one.
        action = 'rescreened' if common.screenout_cleared(participant) else 'screened'
        # Records the flag, exit code -4 AND the cause in one call. THE CAUSE IS
        # THE DETECTED TYPE, not the name of the gate: -4 alone is the generic
        # "screened out at entry" bucket, and the page writes a different
        # sentence for a phone, a tablet, a computer and an unrecognised device
        # (see common.SCREENOUT_CAUSES and before/screened_out.html).
        common.set_screened_out(participant, detected)
        common.stamp_stage(participant, common.STAGE_SCREENED_OUT)
        # Keep the evidence for the decision (export only — never rendered).
        common.extra_set(participant, 'screenout_user_agent',
                         (user_agent or '')[:common.SCREENOUT_UA_TRUNC])
    elif was_screened and clears:
        action = 'cleared'
        common.clear_screened_out(participant)
        common.stamp_stage(participant, common.STAGE_SCREENOUT_CLEARED)
    elif was_screened:
        # Screened out, and this request is not positive evidence either way.
        # Unreachable while the two predicates are exact complements for a
        # determined type, and kept anyway: it is the branch that must exist if
        # a future study makes them anything else, and it writes NOTHING.
        action = 'held'
    else:
        action = 'allowed'

    common.append_screenout_history(
        participant, user_agent, detected,
        common.is_screened_out(participant), action)


def _screenout_vars(player):
    """Template vars for `before/screened_out.html` — the page a screened-out
    participant is held on in place of consent.

    The COPY IS DRIVEN BY THE DETECTED TYPE (`screenout_cause`), so a tablet
    participant is not told the study cannot be taken on a phone, and by what
    the study DOES accept (`allowed_devices_phrase`, built from the same list
    the gate enforces, so the sentence cannot drift from the rule).

    The way out is a PLAIN LINK to the recruitment platform carrying NO
    completion code (common.prolific_screenout_return_url explains why there is no such
    code). It is offered only where it means something — a study with
    `prolific_completion_redirects` off has no platform to return to — and never as a
    broken link when the URL is blank.
    """
    cfg = player.session.config
    # The three device facts come from common.screenout_vars, which the outro
    # ending uses too — the two pages say deliberately different things, but not
    # about the participant's device.
    vars_ = common.screenout_vars(player.participant, cfg)
    return dict(
        vars_,
        # THE WAY OUT IS OWED TO A PROLIFIC PARTICIPANT, and it is the STUDY
        # TYPE that owes it — not `prolific_completion_redirects` (Julian, 2026-08-13).
        #
        # It used to be `return_url and prolific_completion_redirects`, and that was the
        # dead end: the return URL carries NO completion code (that is the whole
        # design — their submission must stay open), so gating it on the
        # completion-CODE flag conflated two unrelated things and left a
        # `recruitment='prolific'` session with redirects off serving a
        # screened-out participant a page with no exit at all.
        #
        # A Prolific participant has no experimenter to raise a hand to, so
        # being a Prolific study IS the obligation to offer an exit. The
        # combination that had no exit is now unconstructable rather than
        # documented: `settings._prelaunch_problems` FAILS a prolific config
        # whose `prolific_screenout_return_url` is blank or still the placeholder, so it
        # cannot reach a participant. The `is_prolific` branch in the template
        # is the runtime belt to that braces — a frozen session predating the
        # guard still reads correctly rather than dead-ending.
        show_return_link=bool(common.is_prolific(cfg)
                              and vars_['prolific_screenout_return_url']),
        is_lab=common.is_lab(cfg),
        is_prolific=common.is_prolific(cfg),
    )


def _declined_consent(player) -> bool:
    """Did this participant answer the consent question with "no"?

    ONE implementation. The routing decision (`welcome.app_after_this_page`),
    the exit code (`welcome.before_next_page`) and every later page's gate
    (`_leaving_study`) are the same question, and three copies of a two-clause
    predicate get edited one at a time.

    THE FLAG TEST IS THE SHORT-CIRCUIT, NOT A STYLE CHOICE: `consent` is only
    ever a form field — and therefore only ever set — when
    `explicit_consent` is on (see `welcome.get_form_fields`), so it must not
    be read when that flag is off. Under implicit consent (the lab profile)
    the first operand is False and `player.consent` is never touched.

    AND THE READ IS DELIBERATELY BARE, not `field_maybe_none`. Unset consent is
    NOT "declined": it is "never asked", and the two must not collapse into one
    answer. `field_maybe_none` would quietly route somebody who never saw the
    question to the ending; a bare read makes that state a loud TypeError
    instead. The one place consent is legitimately unset — a screened-out
    participant, whose form has no fields at all — is short-circuited by the
    screen-out test in `_leaving_study` before this is ever reached.
    """
    return bool(_flag(player, 'explicit_consent')) and not player.consent


def _leaving_study(player) -> bool:
    """True for a participant who is on their way OUT of the study.

    ONE implementation, because more than one page in this app needs it and two
    copies would drift. A participant is leaving when the entry device gate has
    screened them out, or when they declined consent — in both cases the
    remaining pages of THIS app must not be shown to them. (`app_after_this_page`
    routes them past `intro` and `main`, but it only takes effect once this app
    finishes, so every later page in `before` has to gate itself.)

    ORDER IS LOAD-BEARING: the screen-out test comes first because it is what
    keeps `_declined_consent` from reading a consent field that was never on the
    screened-out participant's form (see its docstring).
    """
    return common.is_screened_out(player.participant) or _declined_consent(player)


# DEVICE CAPTURE IS DECIDED BY `device_capture` ALONE (Julian, 2026-08-13).
#
# It used to be `prolific_capture_participant_id or device_capture`, so turning
# on Prolific ID capture SILENTLY also turned on device capture — one flag
# quietly doing a second flag's job, and changing what an export column records.
# Nobody reading either flag name would expect that. One flag, one job.
#
# THE THREE SITES THAT MUST AGREE, all now reading `device_capture`:
# `welcome.get_form_fields` (which fields exist), `welcome.js_vars` (the
# server's UA rules for the script) and welcome+consent.html (the hidden inputs
# and the <script> tag). oTree renders any form field the template does not
# place as a VISIBLE LABELLED BOX, so a field switched on in one place and not
# the other puts a raw "Is mobile" control on the consent page — with no error
# and no failing bot test to say so.
#
# WHAT THIS CHANGES IN THE DATA: a config with `prolific_capture_participant_id`
# ON and `device_capture` OFF used to record device info and no longer does.
# Neither shipped profile is affected (both set the two together), but an export
# compared across this change must be read with it in mind — see CODEBOOK.md.


def _claim_participant_label(player, raw_id):
    """Write a participant label the safe way, and record a refused claim.

    Never raises, never blocks, never tells the participant anything (see
    identity.py). A conflict lands in `prolific_label_conflict` — the OWNING
    ROW's participant code — which is what payment triage needs to see both
    sides of a mistyped or borrowed id.

    THE OUTCOME IS RECORDED, and that is what makes the `except` below
    verifiable: 'error' was previously a value NOTHING anywhere could observe —
    returned to two call sites that both ignored it — so the defensive path
    could not be told apart from a successful claim in any export. The key holds
    the LAST claim's outcome (this page's URL capture, then the confirmation
    page's typed id, if both run); the conflict detail is in
    `prolific_label_conflict` and `participant_extra` either way.
    """
    try:
        outcome, owner_code = identity.claim_label(player.participant, raw_id)
        if outcome == 'conflict':
            player.prolific_label_conflict = owner_code or ''
    except Exception:
        # A label that cannot be stamped is a data problem; a page that 500s on
        # the way to consent is a lost participant.
        outcome = 'error'
    try:
        common.extra_set(player.participant, 'label_claim', outcome)
    except Exception:
        pass          # instrumentation must never break a page
    return outcome


# PAGES
# NB: _static/global/html/template.html is a DESIGN REFERENCE (open it directly
# in a browser to preview the shell). It is intentionally NOT a flow page — it
# has no working Next control — so it is not in page_sequence.

class startpage(Page):
    # Lab hold screen: only meaningful when an experimenter starts the session.
    @staticmethod
    def is_displayed(player):
        # common.is_lab, like every other reader of the study type (B2, Julian
        # 2026-08-13 — the LAST raw read of `recruitment` in the flow). The raw
        # `.get` it replaces evaluated None == 'lab' -> False on a session
        # frozen before the key existed, silently dropping the lab hold screen
        # while the consent page one index later still rendered lab copy
        # through is_lab's own default fallback: one participant, one
        # question, two answers, one page apart.
        return common.is_lab(player.session.config)


class welcome(Page):
    """Consent — AND the screen-out page, which is this page under another
    template.

    WHY ONE PAGE AND NOT TWO. The screen-out has to be re-decidable: the
    participant must be able to come back on a computer and carry on. oTree only
    ever moves a participant FORWARD, and it advances the page index the moment
    a page's `is_displayed` is False — so a screened-out participant who was
    walked past this page could never be brought back to consent, and a separate
    screen-out page placed after it could only ever send them further away. By
    holding them HERE, on the page index they must pass through anyway, every
    later request lands on the gate, is re-decided, and either renders the
    screen-out page again or renders consent.

    THE DECISION IS MADE ONCE PER REAL REQUEST, IN `get()`, AND RECORDED.
    Everything else — `get_template_name`, `get_form_fields`,
    `vars_for_template`, every page downstream — READS the record. oTree
    instantiates pages with NO request while it walks the skip chain
    (`views/abstract.py`: `instantiate_without_request`), and a header read
    there would be a phantom answer.
    """
    template_name = 'before/welcome+consent.html'
    form_model = 'player'

    def get(self):
        """Run the entry device gate before this page renders.

        This override is the ONE place the entry request is reachable
        server-side (oTree's page hooks receive the player, not the request), and
        it runs before a single byte of the consent page exists.

        Instrumentation must never break a page (conventions.md): if anything in
        the gate raises, the participant simply proceeds to consent.
        """
        try:
            # FIRST REAL USE: is the duplicate-label guard actually in place?
            # Loud in the log and on the row if not, never fatal — at this point
            # we are inside a participant's request, and a missing guard is a
            # CONDITIONAL risk (it only matters if a duplicate exists) that must
            # not be turned into their certain 500. See identity.py.
            identity.note_guard_state(self.participant)
        except Exception:
            pass
        try:
            _apply_device_gate(
                self.player, self.request.headers.get('user-agent', ''))
        except Exception:
            pass
        return super().get()

    def post(self):
        """A screened-out participant may not advance past this page.

        Nothing on `before/screened_out.html` can submit — it has no form
        fields and no submit control — so this is for the stale tab and the
        crafted POST: someone who had the consent page open and was screened out
        by a later request, whose browser then posts the old form. Re-rendering
        is the answer, never processing the submit.

        The gate is deliberately NOT re-run here. The decision belongs to the
        page's own GET; this reads the RECORD, exactly like everything else
        downstream.
        """
        try:
            if common.is_screened_out(self.participant):
                return self.get()
        except Exception:
            pass
        return super().post()

    def get_template_name(self):
        """Consent, or the screen-out page, for this same page index."""
        if common.is_screened_out(self.participant):
            return 'before/screened_out.html'
        return self.template_name

    @staticmethod
    def get_form_fields(player):
        # A screened-out participant is shown a page with no form at all: no
        # consent radio, and none of the hidden telemetry either. oTree renders
        # any form field the template does not place as a visible labelled box,
        # so this is not optional tidiness.
        if common.is_screened_out(player.participant):
            return []
        fields = []
        # The explicit consent question (with its no-consent routing) exists
        # exactly when the `explicit_consent` flag says so — an ETHICS
        # decision with its own flag, split from `prolific_completion_redirects`
        # on 2026-08-14 (DECISIONS.md): whether consent must be an affirmative
        # act has nothing to do with whether we hold a completion code. The
        # lab profile resolves it OFF (implicit consent by continuing).
        if _flag(player, 'explicit_consent'):
            fields.append('consent')
        # NB: the participant id is NOT collected here. It has its own page
        # (ConfirmProlificID) so this page stays platform-neutral and renders
        # identically in the lab. Only the invisible URL capture rides along.
        if _flag(player, 'prolific_capture_participant_id'):
            fields.append('participant_id_url')
        # BOTH device fields under the ONE flag that owns them (see the note
        # above `_claim_participant_label`'s section): they are filled by the
        # same script, so they appear and disappear together.
        if _flag(player, 'device_capture'):
            fields += ['is_mobile', 'device_info_json']
        return fields

    @staticmethod
    def js_vars(player):
        """The server's User-Agent rules, for the client-side twin.

        The browser classifies with THE SERVER'S list rather than a copy of it,
        so the two cannot drift — see `common.device_ua_rules`, which explains
        what the client does with them and how a genuine client/server
        disagreement is kept separable from an artefact of ours. Sent only when
        the capture script is actually on the page; when it is not sent, the
        client records `ua_rules: 'unavailable'` and classifies nothing rather
        than falling back to a private list.
        """
        if not _flag(player, 'device_capture'):
            return {}
        return dict(DEVICE_UA_RULES=common.device_ua_rules())

    @staticmethod
    def vars_for_template(player):
        cfg = player.session.config
        if common.is_screened_out(player.participant):
            return _screenout_vars(player)
        return dict(
            prolific_capture_participant_id=_flag(player, 'prolific_capture_participant_id'),
            device_capture=_flag(player, 'device_capture'),
            # Drives the template's radio-vs-implicit branch; see
            # get_form_fields, which adds the field under the same flag.
            explicit_consent=_flag(player, 'explicit_consent'),
            # Payment-mechanics wording only. Branching on collect_bank_details
            # (not on prolific_capture_participant_id) because the sentence is about HOW
            # the participant is paid — and it keeps this page from having any
            # notion of a recruitment platform.
            collect_bank_details=_flag(player, 'collect_bank_details'),
            # Consent quotes duration and payment from config, so a lab session
            # can state its own show-up fee (safe reads: defaults if unset).
            # Rendered only when show_duration_and_fee is on (off by default).
            show_duration_and_fee=bool(common.cfg(cfg, 'show_duration_and_fee')),
            expected_duration_minutes=common.cfg(cfg, 'expected_duration_minutes'),
            # BARE READ, no `or 0` (B4, Julian 2026-08-13): one guard policy for one
            # money value — the payment side reads this key bare and fails loudly,
            # so the promise side must not silently advertise €0.00 for the same
            # broken config. See intro.instructions_context for the full note.
            showup_fee=cu(common.cfg(cfg, 'showup')),
            # WHICH CONTACT ROUTE the closing sentence offers. BOTH branches
            # come from the STUDY TYPE, never from a module flag: this is copy,
            # and copy is `recruitment`'s to decide (the rule is written out in
            # full above `common.is_lab`).
            #
            # It used to read `names_prolific=_flag(player,
            # 'prolific_capture_participant_id')`, on the argument that the id-capture
            # flag "means this study runs on Prolific". It does not: a Prolific
            # study may capture no id and still be a study where the platform's
            # messaging is the participant's only channel. Worse, the screen-out
            # page next door was making the same guess from a DIFFERENT flag
            # (`prolific_completion_redirects`), so one config could name Prolific here
            # and offer no way out there — see tests/copy_routing_test.py.
            is_lab=common.is_lab(cfg),
            names_prolific=common.is_prolific(cfg),
        )

    # NB: there is deliberately no error_message here blocking `is_mobile`.
    # The client-side `is_mobile` field is MEASUREMENT (device_capture) and
    # never blocks anyone; screening devices out is the `allowed_devices`
    # gate's job alone, and it happens before this page (see
    # _apply_device_gate). Blocking here as well would give the device check a
    # participant-visible effect even when the allow-list permits everything.

    @staticmethod
    def before_next_page(player, timeout_happened):
        # THE CONSENT BOUNDARY, recorded first and unconditionally: from here on
        # the device gate never touches this participant again, whether they
        # consented or not (common.consent_submitted).
        common.mark_consent_submitted(player.participant)
        player.participant_label = player.participant.label or ''
        # Copy the pre-assigned treatment onto the player for display/testing.
        # Read participant vars with .vars.get(), never getattr() (KeyError trap;
        # the oTree vars descriptor raises KeyError, so a getattr default does not
        # protect you — see conventions.md).
        player.treatment_group = player.participant.vars.get('treatment_group', '')

        # The id arrived in the URL (if at all). Keep it on the player for the
        # audit trail and seed participant.label from it when oTree has not
        # already resolved one, so the confirmation page can pre-fill.
        if _flag(player, 'prolific_capture_participant_id'):
            url_id = (player.field_maybe_none('participant_id_url') or '').strip()
            if url_id:
                player.participant_id_url = url_id
                if not player.participant.label:
                    # Through claim_label, never a bare assignment: two rows
                    # sharing a label is a permanent 500 on the front door for
                    # the id's real owner (identity.py).
                    _claim_participant_label(player, url_id)
        if _flag(player, 'device_capture') and player.device_info_json:
            common.extra_set(player.participant, 'device_info_json', player.device_info_json)

        common.stamp_stage(player.participant, common.STAGE_CONSENT)
        # And the entry-block exit stamp, written by EVERY page of this app and
        # deliberately overwritten each time — see common.stamp_left_before_app.
        common.stamp_left_before_app(player.participant)

        # No-consent short-circuit: record the outcome; routing happens in
        # app_after_this_page so the participant never enters the task apps.
        if _declined_consent(player):
            common.set_exit_code(player.participant, common.EXIT_CODES['no_consent'])

    @staticmethod
    def app_after_this_page(player, upcoming_apps):
        # Send non-consenters straight to the final app (outro), skipping intro
        # and main entirely.
        if _declined_consent(player):
            return upcoming_apps[-1]


class ConfirmProlificID(Page):
    """Confirm the recruitment-platform id — the ONLY page that mentions Prolific.

    Everything platform-specific was moved off the shared consent page onto this
    one, so consent can render identically in the lab and online. Gated on
    `prolific_capture_participant_id`, so a lab session never sees it.

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
        # Never in the lab; never for a participant on their way to an ending.
        if not _flag(player, 'prolific_capture_participant_id'):
            return False
        return not _leaving_study(player)

    @staticmethod
    def vars_for_template(player):
        url_id = ConfirmProlificID._url_id(player)
        # prefill_id is participant-controlled; the template escapes it. See the
        # SECURITY note in before/confirm_prolific_id.html.
        return dict(prefill_id=url_id, has_prefill=bool(url_id))

    @staticmethod
    def before_next_page(player, timeout_happened):
        confirmed = (player.field_maybe_none('participant_id_external') or '').strip()
        # STORED VERBATIM WHATEVER HAPPENS NEXT. This column is what the
        # participant actually typed; the label claim below may be refused, and
        # a refused claim must still leave the typed value in the export.
        player.participant_id_external = confirmed
        # The confirmed id is the one payment should use, so it becomes the
        # participant label the platform matches on — UNLESS another row in this
        # session already holds it, in which case the claim is refused, silently
        # (identity.py). A typo or a pasted friend's id would otherwise create
        # two rows with one label, which is a permanent 500 at entry for
        # whoever really owns it. The URL-arrived value stays in
        # participant_id_url for the audit trail either way.
        if confirmed:
            _claim_participant_label(player, confirmed)
            player.participant.participant_id_external = confirmed
        common.stamp_stage(player.participant, common.STAGE_CONFIRM_ID)
        common.stamp_left_before_app(player.participant)


class AISafetyAgree(Page):
    """Arms the tab-switch monitor. Shown only when `tab_monitor` is on.

    On submit the template sets `sessionStorage.aiSafetyAgreed = '1'`; the
    monitor JS (`_static/global/js/ai_safety_monitor.js`) stays dormant until
    that flag is set, so this page marks exactly where monitoring begins — and
    since 2026-08-13 everything after it really IS monitored by default
    (monitoring.MonitoredPage: intro and main eject at the threshold, outro
    records only — see monitoring.py). Between 2026-08-12 and then, "begins
    here" was a claim the code did not honour: the page had moved but the
    intro pages carried no monitor wiring, so the instructions and the quiz
    stayed unwatched with nothing anywhere to say so (the whole-app review's
    headline finding; recorded in DECISIONS.md).

    WHY IT IS IN `before`, AND NOT AT THE END OF `intro` (moved 2026-08-12 —
    a deliberate correction, do not move it back).
    ------------------------------------------------------------------------
    It used to be the LAST page of `intro`, after the comprehension quiz. That
    armed the monitor only once the quiz was already passed, which left the two
    things a participant does entirely alone — reading the instructions, and
    sitting the quiz that gates entry to the study — completely unmonitored. A
    participant could consult an AI assistant during the very check that decides
    whether they may take part, which is precisely the behaviour the text on
    this page asks them not to engage in. No rationale for the old position was
    recorded anywhere (docstring, README, conventions or history); the reference
    implementation this template is compared against arms it right after consent.

    WHY HERE SPECIFICALLY, i.e. after the ID confirmation rather than before it:
    this page reads as the "now we begin" gate, and putting it after the ID page
    keeps the Prolific-specific admin (id capture, id confirmation) together as
    one block. Arming one page earlier would buy nothing — there is nothing to
    game on an id confirmation page.

    NO `round_number` TEST. The old one (`round_number == 1`) was meaningless
    even in `intro` for a page that is only ever shown once, and here it would
    be actively misleading: `before` has `NUM_ROUNDS = 1`, so it could only ever
    be True. It is removed rather than carried over, so nothing looks
    load-bearing that is not.

    The `tab_monitor` gate IS kept, and is what makes this page invisible in the
    lab: the lab profile ships the monitor off, so a lab participant never sees
    it. A lab session that deliberately turns the monitor on gets the agreement
    page too, which is correct — the two belong together.
    """
    template_name = 'before/ai_safety.html'

    @staticmethod
    def is_displayed(player):
        # No monitor, no agreement to take: the page exists only to arm it.
        if not _flag(player, 'tab_monitor'):
            return False
        # And never for somebody on their way to an ending — a participant who
        # declined consent, or whom the device gate screened out, must not be
        # asked to agree to being monitored during a study they are not doing.
        return not _leaving_study(player)

    @staticmethod
    def before_next_page(player, timeout_happened):
        # STAMPED (added 2026-08-12; this page deliberately had no stamp
        # before). The stamp is not for the export's sake — it is because this
        # page sits INSIDE the interval anything measuring "time on the
        # instructions" has to use.
        #
        # The entry block's stamps used to end at `consent` / `confirm_id`, both
        # of which are BEFORE this page, while the next stamp is
        # `instructions_done` AFTER the instructions. So the dwell time on this
        # page fell inside that gap and was billed to the instructions — and
        # only for Prolific, because the lab ships `tab_monitor` off and never
        # shows this page at all. One column, two meanings depending on the
        # study type, with nothing on screen to say which: the experimenter
        # dashboard reported 5s of "instructions time" for a participant who
        # spent 5s here and none there (found by the conformance audit,
        # `_ai/dashboard_conformance_audit.md`).
        #
        # Consumers do NOT need to special-case this page, and must not start:
        # every page of this app calls `common.stamp_left_before_app`, which
        # OVERWRITES, so the end of the entry block is that one stamp whichever
        # pages a config happens to show. The max of `consent` / `confirm_id` /
        # `ai_safety_agreed` survives only as the fallback in
        # `experimenter_dashboard._intro_seconds`, for participants who were
        # already mid-flow when `left_before_app` was deployed.
        common.stamp_stage(player.participant, common.STAGE_AI_SAFETY_AGREED)
        common.stamp_left_before_app(player.participant)


# LAB      : startpage (the CREED gate) -> welcome/consent
#            (no ID page and no agreement page: the lab captures no platform id
#             and ships the tab monitor off)
# PROLIFIC : [device screen-out, no page of its own] -> welcome/consent ->
#            ConfirmProlificID -> AISafetyAgree (arms the monitor BEFORE the
#            instructions and the quiz — see AISafetyAgree's docstring)
page_sequence = [startpage, welcome, ConfirmProlificID, AISafetyAgree]
