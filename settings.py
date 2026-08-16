import os

import identity

# THE EARLY INSTALL of the duplicate-label guard (identity.py, defence 2). It is
# here as well as in before/__init__.py because the ROOM's entry views can be
# reached before any app module has been imported, and a single install point
# leaves that window open.
#
# IT IS EXPECTED TO FAIL HERE, and that must stay survivable: oTree imports this
# settings module long before `otree.views.participant` is importable, so the
# usual outcome is NOT_IMPORTABLE, which is recorded and returned rather than
# raised. Hardening this line into an assert would convert a benign ordering
# fact into a guaranteed boot crash — strictly worse than the rare gap it
# guards. The single place a missing guard IS a failure is
# `identity.assert_duplicate_label_guard()`, called from before/__init__.py.
# (A symbol that imports fine but has the WRONG SHAPE is version drift and does
# raise, here or anywhere else. The two are different things — see identity.py.)
identity.install_duplicate_label_guard()

# =============================================================================
# THE THREE AXES  (read this first — between them they determine everything a
# participant experiences, and they are INDEPENDENT of each other)
# =============================================================================
# 1. STUDY TYPE (`recruitment`: 'prolific' | 'lab') — the recruitment plumbing,
#    decided once per study and rarely changed. Prolific: participant-ID
#    capture, completion-code redirects, the integrity modules. Lab: bank
#    details, demographics, the supervised quiz re-read. Resolved into explicit
#    flags at import (see RECRUITMENT_PROFILES below).
# 2. DEBUG (from the environment; never set per config) — dev-only affordances:
#    skip controls, quiz solutions in the browser, the loosened quiz validation
#    (verify_quiz=False is honoured ONLY under DEBUG), the prelaunch banner's
#    DEBUG warning. Driven by OTREE_PRODUCTION: unset -> DEBUG on; set ->
#    DEBUG off and every debug affordance is dead, so production cannot
#    accidentally ship them. Orthogonal to study type: a prolific-configured
#    study under DEBUG runs with ALL its integrity modules on.
# 3. PILOT FEEDBACK FORM (`pilot_feedback`) — whether the free-text feedback
#    page is shown at the end. On for a pilot or a friend test, off for the
#    real run, regardless of study type or debug.

# STUDY TYPE default when a session config names none.
DEFAULT_RECRUITMENT = 'lab'

# DEBUG — mirror of oTree's own derivation (OTREE_PRODUCTION unset -> True).
# Do NOT hardcode a value: oTree computes its DEBUG from the env var before
# reading this file, and a hardcoded value here would silently override it
# even in production (see the credentials section note).
DEBUG = 'OTREE_PRODUCTION' not in os.environ

# PILOT FEEDBACK FORM default; a session config may override `pilot_feedback`.
PILOT_FEEDBACK = False

# =============================================================================
# PARAMETER SCHEME  (everything else hangs off the axes above)
# =============================================================================
# Every optional module in this template is controlled by ONE feature flag in
# SESSION_CONFIG_DEFAULTS, and every flag ships OFF by default. A new project
# therefore starts with a bare, correct baseline and opts in to each module
# deliberately.
#
# On top of the flags sits the STUDY TYPE: a single `recruitment` profile
# (prolific | lab). A profile is a NAMED BUNDLE of flag/threshold values. At import time
# `resolve_recruitment_profile()` copies the bundle's values into each session
# config as EXPLICIT keys, so the admin "session configuration" view shows
# exactly what the session actually ran with. A profile therefore never changes
# behaviour silently at runtime — resolving it is a one-time, visible rewrite of
# the config; runtime code only ever reads the resolved explicit flags. (Silent
# runtime re-derivation would damage the experimental record.)
#
# Precedence, highest first:
#   1. a flag set explicitly on the session config entry   (per-study override)
#   2. the recruitment profile's value for that flag        (the bundle)
#   3. the SESSION_CONFIG_DEFAULTS baseline                 (always OFF)
#
# NUM_ROUNDS is FIXED AT IMPORT. `main` reads `num_experimental_rounds` from
# SESSION_CONFIG_DEFAULTS to set C.NUM_ROUNDS once, at import, because oTree
# builds the round tables from the constant. A session config may request FEWER
# rounds (the extra pages are skipped) but NEVER MORE — `main.creating_session`
# raises if a config asks for more than were imported.
# =============================================================================

# --- exit codes --------------------------------------------------------------
# Numeric outcome recorded on every participant so no export row is ever blank.
# Initialised to 0 ("abandoned") at session creation, set to 1 on a clean
# finish, or to a negative reason code when a participant leaves early. Keep in
# sync with the CODEBOOK.md exit-code table.
# EVERY code here must be set by some code path, and CODEBOOK.md names the line
# that sets it. A reserved code that nothing records is a lie in the export:
# delete it rather than document it (one such code has already been removed).
EXIT_CODES = dict(
    finished=1,          # completed the study normally
    abandoned=0,         # default: created but never reached the end
    no_consent=-1,       # declined consent
    comprehension=-2,    # disqualified: failed the comprehension check
    tab_monitor=-3,      # disqualified: AI-safety / tab-switch monitor
    screened_out=-4,     # device screened out at entry (allowed_devices gate)
)

# --- recruitment profiles (STUDY TYPE axis) ----------------------------------
# Each profile is a bundle of explicit values resolved into the config at import
# (see resolve_recruitment_profile). Add keys here to have a profile govern
# them; anything not listed falls through to the SESSION_CONFIG_DEFAULTS baseline
# and can still be overridden per config. Debug loosenings (e.g.
# verify_quiz=False) do NOT belong here — they live on the DEBUG axis.
RECRUITMENT_PROFILES = {
    # Physical lab (CREED): experimenter-run, paid by bank transfer. No Prolific
    # plumbing, no tab monitor.
    'lab': dict(
        prolific_capture_participant_id=False,
        prolific_completion_redirects=False,
        # Implicit consent by continuing — an ETHICS choice the lab modality
        # makes deliberately (experimenter in the room; see the flag's own
        # comment in SESSION_CONFIG_DEFAULTS). Resolving it OFF here preserves
        # the exact pre-split behaviour: the lab never showed the radio. The
        # prolific profile deliberately does NOT list this key — it falls
        # through to the baseline's ON, because explicit consent is the
        # default, not a Prolific feature.
        explicit_consent=False,
        tab_monitor=False,
        comprehension_dq=False,
        passive_capture=False,
        device_capture=False,
        collect_bank_details=True,   # lab pays by bank transfer
        collect_demographics=True,   # lab asks demographics itself (no platform export)
        quiz_reread=True,            # one supervised re-read pass instead of DQ
    ),
    # Online via Prolific: self-serve entry, paid through the platform. Turns on
    # participant-ID capture, completion-code redirects and the integrity
    # modules.
    'prolific': dict(
        prolific_capture_participant_id=True,
        prolific_completion_redirects=True,
        tab_monitor=True,
        comprehension_dq=True,
        passive_capture=True,
        device_capture=True,
        collect_bank_details=False,  # Prolific pays through the platform
        collect_demographics=False,  # Prolific supplies demographics in its own export
        quiz_reread=False,           # no re-read pass online; comprehension_dq instead
        # NB: `allowed_devices` is deliberately NOT listed here, and is not a
        # Prolific parameter at all (it has its own ENTRY section): selecting
        # the prolific study type must never start screening devices out on its
        # own. It falls
        # through to the SESSION_CONFIG_DEFAULTS baseline (all four types = no
        # gate) and is narrowed explicitly on a config.
    ),
    # There is deliberately NO 'testing' profile: clickthrough loosenings are
    # the DEBUG axis (env-driven), not a study type. For a clickthrough config,
    # pick a real study type and set the loosenings explicitly (see the 'test'
    # session config below).
}

# Placeholder Prolific completion codes. Real codes are created in the Prolific
# study UI and pasted per config; the prelaunch banner flags any REPLACE_*
# sentinel that survives to launch.
#
# THE SCREEN-OUT HAS ITS OWN CODE, and that REVERSES what this comment said
# until 2026-08-15 ("there is no screened-out completion code, and none must be
# added here") — a prohibition that was sitting directly above the
# `DEVICE-XXXXXX_REPLACE` placeholder it forbade. Corrected rather than
# deleted, because the superseded reasoning is worth knowing: a completion code
# CLOSES a Prolific submission and a returned submission can never be retaken,
# so the 2026-08-12 rule sent a screened-out participant back by a plain,
# codeless link to keep their submission open.
#
# What changed the answer (DECISIONS.md, 2026-08-15): an open submission is not
# a kindness, it is LIMBO — it occupies a place, tells Prolific nothing, and
# expires on a timer. A REQUEST_RETURN code prompts the participant to return
# it, which frees the place. So the screen-out exit is now
# `prolific_device_code` rendered as a full completion URL by
# `common.prolific_screenout_return_url`, and the separate
# `prolific_screenout_return_url` SETTING is gone (one value in two places
# drifts). The old `error_code` / 'REPLACE_ERR' pair, removed 2026-08-12, is
# still not to be reintroduced — that was a SHARED error code across
# populations, which is a different thing and remains wrong.
PROLIFIC_CODE_PLACEHOLDERS = ('COMP-XXXXXX_REPLACE', 'NOCONS-XXXXXX_REPLACE',
                              'DQ-QUIZ-XXXXXX_REPLACE', 'DQ-TAB-XXXXXX_REPLACE',
                              'DEVICE-XXXXXX_REPLACE')

# THE FIVE ENDING POPULATIONS, AND WHY EACH HAS ITS OWN CODE (Julian,
# 2026-08-15). A shared code COLLAPSES TWO POPULATIONS IRREVERSIBLY, and the
# collapse happens on Prolific's side where we cannot undo it: once a
# comprehension failure and a tab-monitor ejection have both submitted under one
# `DQ-` code, the submission list cannot tell them apart and nothing downstream
# recovers it. This is the collapsed-distinction rule (CLAUDE.md) applied to a
# system we do not own — which is exactly the case where it has to be got right
# up front, because there is no later fix.
#
# EVERY CODE KEY IS LISTED HERE, and the prelaunch guard iterates THIS TUPLE
# rather than its own copy — see PROLIFIC_CODE_KEYS below.
PROLIFIC_CODE_KEYS = (
    'prolific_cc_code',          # completed        -> auto-approve
    'prolific_noconsent_code',   # declined consent -> request return
    'prolific_dq_quiz_code',     # comprehension DQ -> request return
    'prolific_dq_tab_code',      # tab-monitor DQ   -> request return
    'prolific_device_code',      # device screen-out-> request return
)


def is_placeholder(value) -> bool:
    """Is this config value still an unreplaced placeholder?

    MATCHED BY SHAPE, NEVER BY EXACT STRING, and that is the whole point of this
    function existing. The guard used to test `value in
    PROLIFIC_CODE_PLACEHOLDERS` — exact membership — so the day somebody
    improved the placeholders (2026-08-14: `REPLACE_CC` became
    `COMP-XXXXXX_REPLACE`, to teach the real code's shape) the guard would have
    kept passing while a study shipped codes that pay nobody. **A check that is
    silently disarmed by an unrelated edit is worse than no check**, because
    nothing goes red and everyone believes it is still watching. Placeholders
    and the guard that catches them are ONE change, and this predicate is what
    keeps them one.

    `REPLACE` anywhere in the value is the test, so it catches the old
    `REPLACE_*` shape, the new `*_REPLACE` shape, and any future one that keeps
    the word. A real completion code containing 'REPLACE' would be a false
    alarm; it would block a launch and be diagnosable in seconds from the
    printed line, which is the safe direction.
    """
    return 'REPLACE' in str(value)

# THE SCREEN-OUT RETURN URL IS A PLACEHOLDER TOO, AND IS GUARDED THE SAME WAY.
#
# THIS IS NOT THE SAME CALL AS THE SCREENED-OUT COMPLETION CODE, and the two
# must not be confused — they point in opposite directions:
#
#   * the screened-out COMPLETION CODE does not exist and must never be added
#     (see the note above). It is never sent, so guarding it would block a
#     launch over something the study does not use;
#   * this URL IS USED. It is the entire way off `before/screened_out.html` —
#     the one page a stranded participant needs — so it must be verified by a
#     human before a launch, exactly like a completion code.
#
# WHY IT IS A PLACEHOLDER RATHER THAN A WORKING DEFAULT (Julian, 2026-08-12).
# It previously shipped as `https://app.prolific.com/`, which works, and that
# is precisely the problem: A PLAUSIBLE DEFAULT NEVER GETS CHECKED. A URL that
# happens to resolve is worse than one that visibly does not, because nobody
# ever confirms it is the right destination for THIS study — and the person who
# discovers it was wrong is a participant who has already been turned away and
# now cannot get back to the platform. Shipping it broken makes the omission
# impossible to miss: the pre-launch guard fails, and the link on the page is
# visibly not a URL.
# (SCREENOUT_RETURN_URL_PLACEHOLDER retired 2026-08-15: the screened-out
#  exit is a completion code now, not a URL setting. See DECISIONS.md.)

# --- experimenter dashboard ----------------------------------------------------
# The live operator view at /experimenter_dashboard (experimenter_dashboard.py,
# notes in _ai/dashboard_notes.md, local only: _ai/ is gitignored). These are
# read AT REQUEST TIME, so tuning
# them needs only a server restart; deleting either line falls back to the same
# defaults, defined in that module. NOT session config parameters, deliberately:
# they are operator-screen behaviour, not experimental design, so they must not
# show up in the admin's session-config view or the experimental record.
#
# THE STALL THRESHOLDS ARE PER PHASE, NOT ONE NUMBER (Julian, 2026-08-13,
# change_requests_round2 item 6). There used to be a single
# DASHBOARD_STALL_SECONDS covering the whole flow, which is the
# collapsed-distinction rule in CLAUDE.md applied to a threshold: "too long" on
# the consent page and "too long" reading the instructions are different
# durations by an order of magnitude, and one number cannot be both. Set it low
# enough to catch a stuck consent page and every reader trips it; set it high
# enough for the instructions and nobody stuck at entry is ever flagged.
#
# Each phase below is its own line, tuned independently. The amber row treatment
# is unchanged — only which number decides it. A phase with no threshold here
# falls back to DASHBOARD_STALL_SECONDS_DEFAULT.
DASHBOARD_STALL_SECONDS_BEFORE = 60    # entry block (startpage, consent, ID, AI-safety)
DASHBOARD_STALL_SECONDS_INTRO = 480    # instructions + quiz, whole intro app
# TASK: 180s per ROUND, and this one is a judgement call rather than Julian's
# number — recorded here because he asked to be told what I picked. Reasoning:
# the task page is a single decision in this template's Stag Hunt, which takes
# seconds, and a session runs num_experimental_rounds of them back to back; the
# operator's question during the task is "has someone stopped?", so the
# threshold wants to be short enough that one stalled round is visible while the
# room is still working. 3 minutes is roughly an order of magnitude above a
# considered decision and well below "the participant has gone to sleep". A
# STUDY WITH A LONGER TASK PAGE MUST RAISE THIS — it is per single round, not
# per task block.
DASHBOARD_STALL_SECONDS_TASK = 180
# OUTRO: 300s before being marked complete, also my pick. The outro can contain
# a demographics questionnaire and the lab's IBAN/BIC form — typing bank details
# from a card is genuinely slow, and flagging that as a stall would cry wolf at
# the exact moment the operator wants a quiet screen. 5 minutes is long enough
# for the longest legitimate outro this template ships and short enough to catch
# somebody who has walked away without finishing.
DASHBOARD_STALL_SECONDS_OUTRO = 300
# Fallback for any phase not named above (an unmapped app, or a step added to
# the dashboard without a threshold). Deliberately the old global value, so a
# study that never touches these lines behaves as before.
DASHBOARD_STALL_SECONDS_DEFAULT = 300
DASHBOARD_POLL_SECONDS = 2      # dashboard refresh; 2s is a floor, enforced server-side
# Grace before a finisher with no recorded "Back to Prolific" click is flagged
# ("no return click" pill). A completer reading their receipt has legitimately
# not clicked yet — a pill that fired the moment Results loads would fire for
# everybody briefly and train the operator to ignore it. Prolific-redirect
# sessions only; the pill never exists in the lab (nothing to click through).
DASHBOARD_RETURN_GRACE_SECONDS = 90

# --- static asset version ----------------------------------------------------
# Appended as ?v=... to every CSS/JS href so a redeploy is never served a stale
# cached asset. BUMP THIS ON EVERY CHANGE to a file under _static/. Each app
# exposes it as C.STATIC_VERSION, which is what the templates read.
# 14 -> 15 on 2026-08-15: the logo files were renamed (see INSTITUTION_NAME
# below). Re-record the manifest with
# `python scripts/prelaunch_check.py --stamp-assets`.
STATIC_VERSION = '15'

# --- whose study this is ------------------------------------------------------
# THE ONE PLACE A COPIED STUDY NAMES ITS INSTITUTION IN PROSE (Julian,
# 2026-08-15). Rebranding a copied template is meant to be two image files plus
# this line, and nothing else — see "Rebranding a copied study" in README.md.
#
# WHAT READS IT: participant-facing COPY that names the institution, which today
# is the consent page's privacy sentence. Each app re-exports it as
# `C.INSTITUTION_NAME`, the same pattern STATIC_VERSION uses, so templates read
# it from page context.
#
# WHAT DELIBERATELY DOES NOT READ IT: the two logo partials
# (`_static/global/html/logo_section.html`, `welcome_header.html`). They are
# also included by `_templates/room_welcome.html`, which oTree renders with a
# context of ONLY `has_participant_label_file` — no session, no config, no `C`
# — so a constant referenced there would render on every participant page and
# break the lab's front door. Their alt text is generic and the institution is
# carried by the IMAGE. That asymmetry is the reason this comment exists.
#
# THE ARTICLE IS PART OF THE VALUE ("the University of Amsterdam", but "MIT"),
# because the sentence that uses it cannot know which one your name takes. Write
# whichever reads correctly after "researchers at ...".
INSTITUTION_NAME = 'the University of Amsterdam'


SESSION_CONFIG_DEFAULTS = dict(
    # oTree's built-in per-config description (shown on the demo page).
    doc="",

    # =========================================================================
    # RECRUITMENT
    # =========================================================================
    # Which recruitment profile this session runs under. The profile is a named
    # bundle of the module flags below (see RECRUITMENT_PROFILES); at import it
    # is resolved into explicit per-config keys, so every flag a profile
    # governs ends up visible on the session config itself.
    recruitment=DEFAULT_RECRUITMENT,

    # =========================================================================
    # PILOT FEEDBACK  (axis 3 — independent of study type and DEBUG)
    # =========================================================================
    # Show the free-text feedback page at the end of the study. On for a pilot
    # or a friend test, off for the real run.
    pilot_feedback=PILOT_FEEDBACK,

    # =========================================================================
    # GAME AND DESIGN
    # =========================================================================
    # Structural quantities of the experiment itself: round counts and any
    # stimulus/treatment quantities a study adds.
    # NUM_ROUNDS is fixed at import from this value (the MAX). A config may set
    # it LOWER to run fewer rounds, never higher.
    num_experimental_rounds=10,

    # =========================================================================
    # PAYMENT AND INCENTIVES
    # =========================================================================
    # Everything money: base/show-up pay, bonuses, how many rounds are paid,
    # currency conversion, and whether we collect bank details to pay out.
    real_world_currency_per_point=1.00,  # oTree currency conversion rate
    # ZERO, AND HELD THERE BY A BOOT GUARD (fee_guard.py). oTree adds this ON
    # TOP of participant.payoff on the admin Payments page
    # (payoff_plus_participation_fee) — a second payment channel. It does NOT
    # reach the CSV export, so it is invisible in the data and visible only
    # where somebody reads off what to pay. This template keeps ONE ledger: the base is `showup` below, which
    # outro.compute_final_payoff folds into participant.payoff with the bonus, so
    # the admin figure equals the amount actually owed. A non-zero value here
    # splits that across two numbers and REFUSES THE BOOT.
    participation_fee=0.00,      # oTree's built-in participation fee — keep 0
    showup=2.5,                  # show-up fee quoted on consent and paid at the end
    expected_duration_minutes=30,  # session length quoted on the consent page
    quiz_bonus=5,                # bonus for passing the quiz on the first attempt
    num_rewarded=2,              # how many rounds are randomly selected for payment
    collect_bank_details=False,  # lab-style IBAN/BIC/SEPA payment collection
    # Whether the consent page states the study's LENGTH and FEE ("This study
    # takes about 30 minutes. You will receive a payment of ... plus any
    # additional earnings"). Shipped OFF (Julian, 2026-08-11): the sentence is
    # not wanted by default and is the only place `expected_duration_minutes`
    # and `showup` reach the participant. It stays behind this flag rather than
    # being deleted because the next study's ethics text may REQUIRE the fee to
    # be stated, and that must not need a template edit.
    show_duration_and_fee=False,

    # =========================================================================
    # CONSENT
    # =========================================================================
    # Whether the consent page asks an EXPLICIT question — a required, unticked
    # "I consent / I do not consent" radio, with the no-consent answer routed
    # to its own ending (exit code -1) — or states that continuing to the next
    # page IS consent (implicit consent; nothing to decline, no -1 path).
    #
    # THIS IS AN ETHICS DECISION, NOT A PLATFORM ONE. It used to be decided by
    # `prolific_completion_redirects`, which conflated "we hold a completion
    # code to send them back with" and "consent must be an affirmative act" —
    # two things that have nothing to do with each other (DECISIONS.md,
    # 2026-08-14). The default is ON: explicit consent is the safer footing,
    # and a study must OPT OUT of asking. The lab profile resolves it OFF —
    # implicit consent by continuing, because there is an experimenter in the
    # room, which preserves exactly the pre-split behaviour of both shipped
    # profiles.
    #
    # Mechanics live in `before.welcome.get_form_fields` (the radio exists only
    # under this flag) and `before._declined_consent` (the no-consent routing).
    # A frozen session created before this flag existed reads it as OFF
    # (common.flag's missing-module rule) — the predeploy frozen-config audit
    # names the missing key, and the fix is to recreate the session.
    explicit_consent=True,

    # =========================================================================
    # COMPREHENSION
    # =========================================================================
    # Quiz behaviour: how many wrong attempts count as "failed" (the threshold
    # the integrity and re-read machinery reacts to). Whether answers are
    # validated at all is verify_quiz, under TESTING AND DEV — turning it off
    # is a debug loosening, honoured only under DEBUG.
    #
    # THE SAME NUMBER MEANS TWO DIFFERENT THINGS, BY STUDY TYPE. It is one
    # counter (participant.failed_attempts, incremented in intro.quiz.
    # error_message) and one threshold, deliberately the same value in both
    # study types — what differs is the CONSEQUENCE of crossing it:
    #   * ONLINE (prolific): the point of EJECTION. comprehension_dq is on, so
    #     crossing it flags the participant, records exit code -2 and sends them
    #     to the ending and back to Prolific with prolific_dq_code.
    #   * IN THE LAB: the point at which the study STARTS HELPING. Nobody is
    #     ejected and attempts are never capped — the participant is sitting in
    #     the room, has been promised the show-up fee, and there is an
    #     experimenter to ask. Crossing it opens the one-time re-read offer
    #     (quiz_reread) and, once that is spent or if the module is off, the
    #     dismissible "raise your hand" notice; at TWICE the threshold that
    #     notice also names how many attempts they have made. Nothing is
    #     recorded beyond the counter, which is the point: at analysis time
    #     `failed_attempts >= comprehension_max_failures` is the SAME predicate
    #     the online rule ejects on, so "failed comprehension" means one thing
    #     across both study types. (Failing already costs quiz_bonus, which is
    #     paid only when failed_attempts == 0.)
    # See CODEBOOK.md (and _ai/lab_comprehension_proposal.md, local only:
    # _ai/ is gitignored, so it is not in a copied study).
    comprehension_max_failures=3,   # wrong attempts that count as failing the quiz
    # Lab re-read pass: on first crossing the failure threshold, offer ONE
    # return through the instructions (intro round 2). After it is used, further
    # failures show a dismissible "raise your hand" notice — no disqualification.
    # Mutually exclusive in practice with comprehension_dq (the online rule).
    # Turning it OFF in a lab session is allowed and no longer leaves the
    # participant without help: the experimenter notice is keyed on the
    # threshold and the study type, not on this module.
    quiz_reread=False,              # offer a one-time instructions re-read on failure
    # The ONLINE consequence of crossing the same threshold: disqualify, record
    # exit code -2 and route to the ending. Mutually exclusive in practice with
    # quiz_reread (the lab rule) — and NOT supported in a lab session at all,
    # for which see the INTEGRITY MODULES note below; scripts/prelaunch_check.py
    # fails a lab config that turns it on.
    #
    # IT LIVES HERE, WITH THE THRESHOLD IT ACTS ON AND THE OTHER HALF OF THE
    # SAME DECISION (moved 2026-08-13, Julian). It used to sit in the integrity
    # block BETWEEN `tab_monitor` and tab_monitor's own thresholds, purely by
    # accretion — which read, in the admin's session-config form, as though it
    # were one of them. It is not: it is what comprehension_max_failures does
    # online, and the choice a study makes here is quiz_reread vs this.
    comprehension_dq=False,         # disqualify past comprehension_max_failures

    # =========================================================================
    # INTEGRITY MODULES
    # =========================================================================
    # Enforcement: the tab-switch monitor and its thresholds (which only matter
    # when the module is on). The other integrity module, `comprehension_dq`,
    # is declared with the comprehension threshold it acts on, above.
    #
    # BOTH MODULES ARE NOT SUPPORTED IN A LAB SESSION (Julian, 2026-08-12), and
    # scripts/prelaunch_check.py FAILS on a lab config that turns either on.
    # The reason is conceptual, not technical: in the lab, a participant who
    # does not consent or does not pass the comprehension check simply cannot do
    # the study — and that essentially never happens, because people know what
    # they signed up for when they come to the lab. There is nothing for a
    # disqualification to accomplish that the experimenter in the room does not
    # already handle.
    # The mechanical consequence, which is why the pre-launch check exists
    # rather than a comment on its own: a disqualified participant is not a
    # completer (outro.is_completer), so they skip Demographics — the page that
    # collects the lab's IBAN/BIC — and the payment summary, and land on an
    # ending with no redirect (lab has prolific_completion_redirects off). That is a
    # participant stranded at a machine with no record of where to send their
    # fee. The lab's comprehension rule is the re-read pass plus the
    # experimenter notice; see comprehension_max_failures above.
    #
    # KNOWN ANNOYANCE (candidate future option — documented, deliberately not
    # solved): when TESTING a prolific-configured study these modules, plus
    # device capture, can get in the way — the tab monitor will disqualify YOU
    # for tabbing away to inspect the app, and comprehension disqualification
    # blocks a clickthrough after two wrong quiz submissions. If that bites
    # often, a later testing switch could relax tab_monitor, device_capture
    # and comprehension_dq as well — as a DEBUG-gated read-time override like
    # verify_quiz, NEVER by editing the resolved study values (see the
    # guarantee on resolve_recruitment_profile).
    # COVERAGE AND THE PHASE ASYMMETRY (Julian, 2026-08-13): with the module
    # on, EVERY page after the agreement screen is monitored by default
    # (monitoring.py) — but the consequence differs by phase, deliberately:
    # violations EJECT during the instructions, quiz and task (the pages the
    # agreement protects), and are RECORDED ONLY during the outro (the task is
    # over and the data collected; ejecting a completer over their bank-details
    # page would cost a real participant for no benefit). Outro violations land
    # in their own column, focus_loss_count_outro. Full why:
    # common._apply_focus_loss.
    tab_monitor=False,              # tab-switch / AI-safety monitor
    tab_monitor_max_violations=2,   # disqualify on the Nth recorded tab-away (intro/main only)
    tab_monitor_threshold_ms=4000,  # continuous away-time that counts as a violation
    tab_monitor_overlay_delay_ms=400,  # grace before the warning overlay appears

    # =========================================================================
    # MEASUREMENT
    # =========================================================================
    # Data captured about the participant/session beyond the task responses:
    # passive time-on-page and device/screen capture. (No error capture module
    # exists yet; it would belong here.)
    passive_capture=False,          # passive hidden-field measurement on the page form
    device_capture=False,           # capture device / screen info at entry
    collect_demographics=False,     # explicit demographics questionnaire (outro)

    # =========================================================================
    # ENTRY — THE DEVICE ALLOW-LIST
    # =========================================================================
    # NOT a Prolific parameter, and no longer filed as one (moved 2026-08-13):
    # the gate is decided from the entry request in every study type, it is
    # deliberately absent from both recruitment profiles, and a lab study may
    # narrow it too. What IS Prolific-specific is where a screened-out
    # participant is SENT, which is why `prolific_screenout_return_url` sits in
    # the Prolific block at the end and this does not.
    #
    # DEVICE ALLOW-LIST — which device types may take part. A study STATES the
    # devices it accepts ('phone', 'tablet', 'computer', 'unknown'); anything
    # else is screened out at entry and held on the consent page's index, where
    # it is served before/screened_out.html instead.
    #
    # READ "THE DEVICE CHECK" IN README.md BEFORE NARROWING THIS. It is the
    # reference for what the check actually inspects (the entry request's
    # User-Agent, and nothing else — no screen size, no touch, nothing
    # client-side), what the four types mean, why there is no 'laptop' type and
    # cannot be one, the fifth NO-DECISION state and its asymmetry, the soft
    # wall, worked config examples, and the honest limits. It is deliberately
    # not repeated here: two copies of a rule this subtle would drift.
    #
    # THE DEFAULT IS ALL FOUR = THE GATE IS OFF, and that safety property is
    # deliberate: with everything permitted the check has NO participant-visible
    # effect whatsoever (device_capture still RECORDS the type as measurement;
    # it never blocks anyone).
    #
    # NOT part of any recruitment profile: choosing the prolific study type must
    # never start screening devices out on its own. A comma-separated string is
    # accepted as well as a list, e.g. allowed_devices='computer'.
    allowed_devices=['phone', 'tablet', 'computer', 'unknown'],

    # =========================================================================
    # TIMING
    # =========================================================================
    # View locks and forced-wait values. None exist yet — when a study adds a
    # timed page or a minimum reading time, its parameter belongs here.

    # =========================================================================
    # TESTING AND DEV  (the DEBUG axis' config-side values)
    # =========================================================================
    # verify_quiz=False lets you click straight through the quiz without
    # answering. It is a DEBUG loosening: honoured ONLY while DEBUG is on
    # (OTREE_PRODUCTION unset) — in production validation always runs, so a
    # leftover False cannot weaken a real launch (prelaunch flags it too).
    verify_quiz=True,
    # The asset version, MIRRORED here from the module-level STATIC_VERSION so
    # the admin's config view still shows what a session ran with. Templates do
    # NOT read this copy — they read C.STATIC_VERSION, which comes from the
    # deployed CODE. A session config is frozen at creation, so a template
    # reading `session.config.static_version` 500s for every in-flight
    # participant of a study that adds the parameter later (measured; see
    # scripts/tests/frozen_config_test.py), and a cache-busting token should follow the
    # build anyway, not the session.
    static_version=STATIC_VERSION,

    # =========================================================================
    # PROLIFIC  —  LAST, AND EVERY KEY HERE IS PREFIXED `prolific_`
    # =========================================================================
    # Every exclusively-Prolific parameter, together at the end (Julian,
    # 2026-08-13). Two things make this block worth keeping contiguous:
    #
    #   * THE ORDER OF THIS DICT IS THE ORDER OF THE ADMIN'S SESSION-CONFIG
    #     FORM. oTree renders SESSION_CONFIG_DEFAULTS in INSERTION ORDER, and it
    #     gives that form no section headings at all — so a contiguous block plus
    #     the shared `prolific_` prefix is the ONLY grouping available to us.
    #     Anything filed here is out of the way of somebody configuring a lab
    #     session, and anything a lab session does need is above.
    #   * THE PREFIX IS THE OTHER HALF OF THAT. A key named `prolific_cc_code` or
    #     `prolific_completion_redirects` reads as general machinery; `prolific_cc_code`
    #     says who it belongs to at the point of use, in a template, in an
    #     export header and in this form. Renamed 2026-08-13 while the template
    #     has NO live studies — the same rename later would be a schema change
    #     across running sessions.
    #
    # WHAT IS NOT HERE, deliberately: `allowed_devices` (the entry gate applies
    # to every study type — see the ENTRY section above) and `recruitment`
    # itself (the axis, not a Prolific parameter).
    #
    # The study's ENTRY URL is configured on Prolific's side (see
    # docs/running_on_prolific.md); the completion codes below are created in
    # the Prolific study UI and pasted per config — the prelaunch banner flags
    # any REPLACE_* placeholder that survives to launch.
    prolific_capture_participant_id=False,  # capture the Prolific ID at entry
    prolific_completion_redirects=False,    # send them back with a completion code
    # WHERE A SCREENED-OUT PARTICIPANT IS SENT: a Prolific completion URL
    # carrying `prolific_device_code`, built by
    # common.prolific_screenout_return_url from that ONE key. There is no
    # separate URL setting any more — a URL that embeds a code, plus a code key,
    # is one value in two places, and they drift.
    #
    # THIS REVERSES the codeless screen-out exit (DECISIONS.md, and the old
    # rationale is preserved there rather than deleted). A Prolific
    # REQUEST_RETURN code PROMPTS the participant to return the submission and
    # frees the place; the bare researcher URL left it in limbo instead.
    # SHAPED LIKE A REAL CODE ON PURPOSE: `REASON-XXXXXX`, a semantic prefix
    # plus six random alphanumerics. The placeholder teaches the convention to
    # whoever replaces it — readable in a Prolific submission list, unguessable
    # by a participant. Replace the XXXXXX with six RANDOM characters, not a
    # short number: the completion code is the one that can AUTO-APPROVE a
    # payment on Prolific, so a guessable one is somebody else's money.
    prolific_cc_code='COMP-XXXXXX_REPLACE',            # completed
    prolific_noconsent_code='NOCONS-XXXXXX_REPLACE',   # declined consent
    prolific_dq_quiz_code='DQ-QUIZ-XXXXXX_REPLACE',    # comprehension DQ
    prolific_dq_tab_code='DQ-TAB-XXXXXX_REPLACE',      # tab-monitor DQ
    # THE DEVICE SCREEN-OUT NOW CARRIES A CODE TOO, and this REVERSES the
    # earlier codeless decision — see DECISIONS.md, 'Every ending population
    # gets its own completion code'. A Prolific REQUEST_RETURN code actively
    # PROMPTS the participant to return the submission, which frees the place;
    # the bare researcher URL it replaces left the submission sitting in limbo.
    prolific_device_code='DEVICE-XXXXXX_REPLACE',      # device screen-out
    # NB: no screened-out code. See PROLIFIC_CODE_PLACEHOLDERS above.
)


def resolve_recruitment_profile(config):
    """Bake a config's recruitment profile into explicit flag values.

    Mutates and returns `config`. For every key the chosen profile governs, the
    profile's value is written into the config UNLESS the config already set that
    key explicitly (an explicit per-config value always wins). The result is a
    config dict that states, in full, exactly what the session will run with —
    which is what the admin session-configuration view displays.

    GUARANTEE — testing never mutates the real study parameters. This
    resolution writes STUDY-TYPE values only. Debug/testing loosenings are a
    SEPARATE OVERRIDE LAYER that sits on top: they are consulted at the point
    of use (settings.DEBUG from the environment, plus DEBUG-gated keys like
    verify_quiz) and never rewrite the resolved lab/prolific values here or
    anywhere else. Turning the testing switch off — setting OTREE_PRODUCTION=1,
    or verify_quiz back to True — therefore returns every gate to exactly the
    real study behaviour, with nothing left changed behind it. Keep it that
    way: a future testing switch must also override at read time, never edit
    the resolved config.
    """
    profile_name = config.get('recruitment', DEFAULT_RECRUITMENT)
    bundle = RECRUITMENT_PROFILES.get(profile_name)
    if bundle is None:
        hint = (
            " The 'testing' profile was removed: clickthrough loosenings are "
            "the DEBUG axis (OTREE_PRODUCTION unset + verify_quiz=False), not "
            "a study type." if profile_name == 'testing' else ""
        )
        raise ValueError(
            f"Unknown recruitment profile {profile_name!r}. "
            f"Choose one of: {', '.join(sorted(RECRUITMENT_PROFILES))}.{hint}"
        )
    config.setdefault('recruitment', profile_name)
    for key, value in bundle.items():
        # Only fill keys the config did not set explicitly (precedence rule 1).
        if key not in config:
            config[key] = value
    return config


# Example session configs. Each names its recruitment profile explicitly; the
# resolution pass below turns that into a full, visible set of flags.
SESSION_CONFIGS = [
    # Clickthrough config: a real study type (lab) with the loosenings set
    # EXPLICITLY per config — there is no 'testing' study type. verify_quiz
    # is honoured only under DEBUG, so this config cannot weaken production.
    dict(
        name='test',
        display_name="Test (clickthrough; loosenings live under DEBUG)",
        app_sequence=['before', 'intro', 'main', 'outro'],
        num_demo_participants=10,
        recruitment='lab',
        verify_quiz=False,           # DEBUG-only loosening: click through the quiz
        collect_bank_details=False,  # skip payment/demographics forms when clicking through
        collect_demographics=False,
        pilot_feedback=True,         # exercise the pilot feedback page too
        num_experimental_rounds=3,   # short for quick testing
    ),
    dict(
        name='lab',
        display_name="Lab session (CREED)",
        app_sequence=['before', 'intro', 'main', 'outro'],
        num_demo_participants=10,
        recruitment='lab',
    ),
    dict(
        name='prolific',
        display_name="Prolific (online)",
        app_sequence=['before', 'intro', 'main', 'outro'],
        num_demo_participants=100,
        recruitment='prolific',
        # prolific_cc_code / prolific_noconsent_code / prolific_dq_code default to REPLACE_* placeholders;
        # paste the real codes from your Prolific study before launch.
    ),
]

# Resolve every config's profile into explicit flags AT IMPORT (see the module
# header). After this, each entry in SESSION_CONFIGS carries the full set of
# module flags it will run with.
for _config in SESSION_CONFIGS:
    resolve_recruitment_profile(_config)


# --- participant fields ------------------------------------------------------
PARTICIPANT_FIELDS = [
    'temp_data',            # scratch storage for any participant-specific data
    'payoff_vector',        # all payoff-relevant values across rounds/apps
    'failed_attempts',      # number of wrong quiz submissions (comprehension)
    'treatment_group',      # treatment cell, assigned at session creation
    'exit_code',            # numeric outcome (see EXIT_CODES); init 0 = abandoned
    'participant_id_external',  # external recruitment ID (e.g. Prolific), if captured
    'stage_timestamps',     # dict {stage_name: epoch_seconds} filled as the flow advances
    'participant_extra',    # free JSON bucket for future/ad-hoc fields (see codebook)
    'ai_safety_disqualified',   # tab-monitor authoritative disqualification flag
    'focus_loss_count',     # tab-monitor violations while ejection applied (intro+main)
    'focus_loss_count_outro',  # tab-monitor violations in the outro: recorded, NEVER eject
    'focus_event_ids',      # tab-monitor seen event ids (server-side dedup)
    'focus_events',         # per-event detail: {page, region, ts} for each counted loss
    'focus_losses_missed_at_least',  # AT-LEAST evidence of events that never reached us
    'tab_monitor_flag',     # READER-FACING verdict: ''|observed|warned|disqualified
    'tab_monitor_where',    # where those observations were: task|questionnaire|both|not-monitored
    'comprehension_disqualified',  # comprehension-DQ authoritative flag
    'instructions_reread_used',    # lab: the one-time re-read pass was taken
    'device_info',          # dict of captured device/screen info, if enabled
    'screened_out',         # entry device gate removed them before consent
    'screenout_cleared',    # a screen-out was LIFTED (they switched device)
    'consent_submitted',    # the consent page was submitted (the gate's boundary)
]
# Description of PARTICIPANT_FIELDS:
# - temp_data: Temporary storage for any participant-specific data during the session.
# - payoff_vector: A list storing all payoff-relevant values across all rounds and apps.
# - failed_attempts: Counts the number of times a participant answers the quiz incorrectly.
# - treatment_group: The treatment cell assigned in before/creating_session.
# - exit_code: Numeric outcome; see EXIT_CODES. Initialised to 0 (abandoned) so
#   no export row is ever blank; set to 1 on a clean finish or a negative reason.
# - participant_id_external: External platform participant id (Prolific etc.).
# - stage_timestamps: {stage: epoch_seconds}; when the participant cleared a stage.
# - participant_extra: A JSON-able dict reserved for future use (repurpose
#   convention in CODEBOOK.md — never rename in place).
# - ai_safety_disqualified / focus_loss_count / focus_event_ids: tab monitor
#   state. focus_loss_count counts ONLY the ejecting phases (intro + main) —
#   crossing tab_monitor_max_violations there disqualifies.
# - focus_loss_count_outro: violations AFTER the task (outro pages), recorded
#   only — never a disqualification, whatever the count. Its own column so an
#   analyst can tell a completed-with-violations participant from a
#   nearly-ejected one (see common._apply_focus_loss and CODEBOOK.md).
# - focus_events: one {page, region, ts} record per COUNTED focus loss. `page`
#   is the SERVER's own participant._current_page_name, never the client's
#   reported pathname — the client half of the monitor is the half a participant
#   can edit, and a field an analyst trusts must not be attacker-controlled.
#   This is what lets tab_monitor_where name the pages instead of the region.
# - focus_losses_missed_at_least: evidence that events were LOST before reaching
#   the server, from comparing the client's own running total against ours. It is
#   an AT-LEAST, not a count — 4 against 2 means at least two were lost, possibly
#   more — so it is a maximum, never a sum, and must never be totalled across
#   participants as if it were a number of events. 0 means no evidence of loss,
#   NOT proof that nothing was lost (see CODEBOOK.md).
# - tab_monitor_flag / tab_monitor_where: the READER-FACING pair, derived from
#   the three raw columns above by common.derive_tab_monitor_flag — what to DO
#   ('' | observed | warned | disqualified, most severe wins) and WHERE to look
#   (task | questionnaire | task+questionnaire | not-monitored). They replace
#   nothing: the counts remain the datum, and these are a reading of them for
#   somebody who has not read the codebook. `where` carries 'not-monitored'
#   because the flag's empty value would otherwise mean both "watched and
#   clean" and "never watched" — every lab session being the latter.
# - comprehension_disqualified: set when a participant fails the quiz too often.
# - instructions_reread_used: True once a lab participant enters the second
#   instructions pass (quiz_reread module). Consumed on entry, not on offer.
# - device_info: captured device/screen dict when device_capture is on.
# - screened_out: True while the entry device gate (allowed_devices) is holding
#   the participant on the consent page's index with exit_code -4, shown
#   before/screened_out.html instead of consent. Authoritative flag, and NOT
#   write-once: the wall is soft, so a pre-consent request from an accepted
#   device clears it again (see before._apply_device_gate).
# - screenout_cleared: True once a screen-out has EVER been lifted for this
#   participant, and it stays True even if they are later screened again. This
#   is the column that makes device switching findable in the export without
#   parsing the audit history in participant_extra['screenout_history'].
# - consent_submitted: True once the consent page has been SUBMITTED (consenting
#   or not). The device gate's boundary: past it the check never applies again.
#   A durable fact rather than a page index, because indices move when the page
#   sequence does and the gate must answer on requests for any page.

SESSION_FIELDS = []

# ISO-639 code, e.g. de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'
# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False

# ONE PAYMENT LEDGER (J1, Julian 2026-08-13). oTree's per-round player.payoff
# is NOT used: the game records each round in its own field
# (main.Player.round_payoff), the template pays from participant.payoff_vector,
# and oTree's participant.payoff is written ONCE — from `earned`, when the
# results page computes payment (outro.compute_final_payoff) — so the admin
# Payments page shows exactly the figure the participant was shown. With this
# False, the per-round payoff column is omitted from the export entirely
# (deliberately ABSENT, not silently empty — see the payment-record note in
# CODEBOOK.md; no data is lost, every round is in payoff_vector).
#
# WHAT THIS FLAG DOES NOT DO (exp_pilots review, 2026-08-14). It ALSO makes
# oTree's own player.payoff setter raise (otree/models/player.py:41-46) — but
# that is not enforcement, it is a participant-facing crash. The raise happens
# inside a request, so a build carrying such a write, deployed over live
# sessions (oTree has no migrations), is a DEAD PAGE for whoever is mid-round.
# The actual guard is `payoff_guard.assert_no_player_payoff_writes()`, called
# at boot from `before/__init__.py`: the build refuses to start instead.
#
# Flip this back to True only together with a decision about which ledger is
# the record, or the two-numbers disagreement this removed comes straight back
# — and note that flipping it does NOT retire the boot guard, whose job is the
# ledger, not the raise.
AUTO_TABULATE_PAYOFFS = False

DEMO_PAGE_INTRO_HTML = """ """

INSTALLED_APPS = ['otree']

# Do NOT set DEBUG here: oTree derives it from the OTREE_PRODUCTION env var
# (unset -> DEBUG on), and a hardcoded value here would override that even in
# production. Debug-only features (testing skip buttons, quiz solutions in the
# browser) are gated on settings.DEBUG.

# This room exists on the computers in the CREED large lab as a desktop shortcut
# 'Chrome to experiment Room' or 'Chrome to Large Lab experiment Server (Giorgia)'.
# start.sh reuses this room's already-bound session rather than creating a new
# one per boot (which would strand in-progress participants).
ROOMS = [
    dict(
        name='experiment',
        display_name='Experimental Session',
        # THE ROOM WELCOME GATE, STYLED. oTree 6 serves an interstitial on every
        # room entry (a GET without `welcome_page_ok=1`), and its stock template
        # is bare framework markup — the FIRST thing a participant sees looking
        # like different software from the study behind it. `welcome_page` takes
        # a template path (otree/room.py; rendered at
        # otree/views/participant.py:291), so we serve our own styled copy.
        # STYLING ONLY: the page's behaviour is oTree's, verbatim. The template's
        # own header explains what may and may not be changed there, including
        # why it links base.css directly and therefore carries no `?v=`
        # cache-buster — this render has no page context to read
        # C.STATIC_VERSION from, so bump-and-refresh does not reach this one file.
        welcome_page='_templates/room_welcome.html',
    ),
]

# --- credentials / database (runs out of the box) ----------------------------
# Admin credentials from environment, with dev fallbacks so the template runs
# locally with no setup. Set real values via env in production.
ADMIN_USERNAME = os.environ.get('OTREE_ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('OTREE_ADMIN_PASSWORD', 'admin')

# Postgres only when DB_NAME is set; otherwise fall back to a local SQLite file
# so a fresh clone runs with `otree devserver` immediately.
if os.environ.get('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.sqlite3'),
        }
    }

# Dev SECRET_KEY fallback; override via env in production.
SECRET_KEY = os.environ.get('OTREE_SECRET_KEY', 'dev-secret-key-change-me')


# =============================================================================
# PRE-LAUNCH GUARD
# =============================================================================
# Printed on every start. Compares the live config against what a real launch
# requires and prints a loud banner if anything is still a testing/placeholder
# value. It is advisory (it never blocks a dev session) but impossible to miss.
# (DEBUG itself is defined at the top of this file — it is one of the three
# axes; the env derivation must never be overridden with a hardcoded value.)


def _prelaunch_problems():
    """Return a list of (label, current, must_be) tuples for anything unsafe."""
    problems = []
    if DEBUG:
        problems.append(('DEBUG (set OTREE_PRODUCTION=1)', True, False))

    for cfg in SESSION_CONFIGS:
        # Check the EFFECTIVE config (defaults + entry), since keys like prolific_cc_code
        # live in SESSION_CONFIG_DEFAULTS and are merged by oTree at runtime.
        eff = {**SESSION_CONFIG_DEFAULTS, **cfg}
        # verify_quiz=False is a DEBUG loosening; it is IGNORED in production,
        # but a config still carrying it at launch is a testing config that
        # should not ship — flag it.
        if not DEBUG and not eff.get('verify_quiz', True):
            problems.append(
                (f"config {cfg['name']!r} verify_quiz", False,
                 'True (False is a DEBUG-only loosening and is ignored in production)'))
        # Placeholder completion codes only matter when the config actually
        # redirects to Prolific.
        # NB three codes, not four: there is deliberately NO screened-out code
        # (see PROLIFIC_CODE_PLACEHOLDERS). Do not add one back here.
        # WHICH CODES ARE OWED, AND BY WHAT. The four ENDING codes are owed by
        # the redirect flag: a study that does not send participants back to
        # Prolific needs none of them. The DEVICE code is owed by the STUDY TYPE
        # itself — a Prolific participant screened out at entry has no
        # experimenter to ask, so the way out is owed whether or not the study
        # uses completion redirects. That asymmetry predates this key (it was
        # the old `prolific_screenout_return_url` rule, and its reasoning is in
        # DECISIONS.md); it is preserved here rather than quietly lost when the
        # URL setting became a code.
        if eff.get('prolific_completion_redirects'):
            code_keys = PROLIFIC_CODE_KEYS
        elif eff.get('recruitment') == 'prolific':
            code_keys = ('prolific_device_code',)
        else:
            code_keys = ()
        if code_keys:
            # ITERATES THE ONE LIST. An enumeration copied here would be the
            # trap this template keeps hitting: add a sixth ending, forget this
            # line, and its code ships unguarded while the check reports clean.
            for code_key in code_keys:
                value = eff.get(code_key)
                if is_placeholder(value):
                    problems.append(
                        (f"config {cfg['name']!r} {code_key}", value,
                         'a real Prolific completion code, shaped '
                         'REASON-XXXXXX with six RANDOM characters (this is '
                         'still an unreplaced placeholder)'))
        # NB THE SCREEN-OUT IS NOT A SEPARATE CHECK ANY MORE. It used to have
        # its own branch here, guarding a `prolific_screenout_return_url` that
        # had to be a real URL. That key is gone: the screened-out exit is now
        # `prolific_device_code`, which the loop above already covers along with
        # the other four. One enumeration, five populations — see
        # PROLIFIC_CODE_KEYS.

    return problems


def _check_prelaunch():
    def _axes(c):
        eff = {**SESSION_CONFIG_DEFAULTS, **c}
        return f"{c['name']}={c.get('recruitment')}{'+feedback' if eff.get('pilot_feedback') else ''}"
    profile_line = ', '.join(_axes(c) for c in SESSION_CONFIGS)
    print(f"[prelaunch] DEBUG={DEBUG}  study type/feedback: {profile_line}")
    problems = _prelaunch_problems()
    if not problems:
        print("[prelaunch] CLEAN — no testing/placeholder values detected.")
        return
    bar = "#" * 72
    print(bar)
    print("##  PRE-LAUNCH: the following MUST be fixed before a real launch:")
    for label, current, must_be in problems:
        print(f"##    {label}: currently {current!r}, MUST BE {must_be}")
    print(bar)


_check_prelaunch()
