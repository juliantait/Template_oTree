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
        capture_participant_id=False,
        completion_redirects=False,
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
        capture_participant_id=True,
        completion_redirects=True,
        tab_monitor=True,
        comprehension_dq=True,
        passive_capture=True,
        device_capture=True,
        collect_bank_details=False,  # Prolific pays through the platform
        collect_demographics=False,  # Prolific supplies demographics in its own export
        quiz_reread=False,           # no re-read pass online; comprehension_dq instead
        # NB: `allowed_devices` is deliberately NOT listed here. It sits in the
        # Prolific block but is its own decision: selecting the prolific study
        # type must never start screening devices out on its own. It falls
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
# THERE IS NO SCREENED-OUT COMPLETION CODE, and none must be added here. A
# device screened out at entry is sent back to Prolific by a PLAIN LINK with no
# code at all (`screenout_return_url`), because submitting a code closes the
# participant's submission, and a returned submission can never be retaken —
# which forecloses the very thing the screen-out page asks them to do, namely
# come back on a computer and finish. The old `error_code` / 'REPLACE_ERR' pair
# was removed on 2026-08-12 for exactly that reason; do not reintroduce it.
PROLIFIC_CODE_PLACEHOLDERS = ('REPLACE_CC', 'REPLACE_NC', 'REPLACE_DQ')

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
SCREENOUT_RETURN_URL_PLACEHOLDER = 'REPLACE_SCREENOUT_RETURN_URL'

# --- experimenter dashboard ----------------------------------------------------
# The live operator view at /experimenter_dashboard (experimenter_dashboard.py,
# notes in _ai/dashboard_notes.md). These are read AT REQUEST TIME, so tuning
# them needs only a server restart; deleting either line falls back to the same
# defaults, defined in that module. NOT session config parameters, deliberately:
# they are operator-screen behaviour, not experimental design, so they must not
# show up in the admin's session-config view or the experimental record.
DASHBOARD_STALL_SECONDS = 300   # a row turns AMBER after this long on one page
DASHBOARD_POLL_SECONDS = 2      # dashboard refresh; 2s is a floor, enforced server-side

# --- static asset version ----------------------------------------------------
# Appended as ?v=... to every CSS/JS href so a redeploy is never served a stale
# cached asset. BUMP THIS ON EVERY CHANGE to a file under _static/. Each app
# exposes it as C.STATIC_VERSION, which is what the templates read.
STATIC_VERSION = '6'


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
    # PAYMENT AND INCENTIVES
    # =========================================================================
    # Everything money: base/show-up pay, bonuses, how many rounds are paid,
    # currency conversion, and whether we collect bank details to pay out.
    real_world_currency_per_point=1.00,  # oTree currency conversion rate
    participation_fee=0.00,      # oTree's built-in participation fee (admin report)
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
    # GAME AND DESIGN
    # =========================================================================
    # Structural quantities of the experiment itself: round counts and any
    # stimulus/treatment quantities a study adds.
    # NUM_ROUNDS is fixed at import from this value (the MAX). A config may set
    # it LOWER to run fewer rounds, never higher.
    num_experimental_rounds=10,

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
    #     to the ending and back to Prolific with dq_code.
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
    # See _ai/lab_comprehension_proposal.md and CODEBOOK.md.
    comprehension_max_failures=3,   # wrong attempts that count as failing the quiz
    # Lab re-read pass: on first crossing the failure threshold, offer ONE
    # return through the instructions (intro round 2). After it is used, further
    # failures show a dismissible "raise your hand" notice — no disqualification.
    # Mutually exclusive in practice with comprehension_dq (the online rule).
    # Turning it OFF in a lab session is allowed and no longer leaves the
    # participant without help: the experimenter notice is keyed on the
    # threshold and the study type, not on this module.
    quiz_reread=False,              # offer a one-time instructions re-read on failure

    # =========================================================================
    # INTEGRITY MODULES
    # =========================================================================
    # Enforcement: the tab-switch monitor and comprehension disqualification,
    # plus their thresholds (thresholds only matter when the module is on).
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
    # ending with no redirect (lab has completion_redirects off). That is a
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
    tab_monitor=False,              # tab-switch / AI-safety monitor
    comprehension_dq=False,         # disqualify past comprehension_max_failures
    tab_monitor_max_violations=2,   # disqualify on the Nth recorded tab-away
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
    # TIMING
    # =========================================================================
    # View locks and forced-wait values. None exist yet — when a study adds a
    # timed page or a minimum reading time, its parameter belongs here.

    # =========================================================================
    # PROLIFIC
    # =========================================================================
    # Every Prolific-specific parameter lives here. The study's ENTRY URL is
    # configured on Prolific's side (see prolific/Prolific_running.md); the
    # completion codes below are created in the Prolific study UI and pasted
    # per config — the prelaunch banner flags any REPLACE_* placeholder that
    # survives to launch.
    capture_participant_id=False,   # capture an external (Prolific) ID at entry
    completion_redirects=False,     # send participants back to Prolific with a code
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
    # WHERE A SCREENED-OUT PARTICIPANT IS SENT, as a plain link carrying NO
    # completion code: the Prolific participant site itself. Their submission
    # therefore stays OPEN, so they can still reopen the study on an accepted
    # device and finish it — which is the outcome the screen-out page asks for,
    # and which a completion code would foreclose for good. See "The device
    # check" in README.md, and common.screenout_return_url.
    # Blank it to render no link at all (a study with no platform to return to).
    #
    # SHIPPED AS A REPLACE_* PLACEHOLDER, deliberately — see
    # SCREENOUT_RETURN_URL_PLACEHOLDER above for why a working default is worse
    # than a broken one here. Replace it with the platform URL your participants
    # should be sent back to (for Prolific that is https://app.prolific.com/),
    # or blank it if the study has no platform to return to. The pre-launch
    # guard fails while this is still the placeholder AND the study redirects.
    screenout_return_url=SCREENOUT_RETURN_URL_PLACEHOLDER,
    cc_code='REPLACE_CC',        # normal completion
    noconsent_code='REPLACE_NC', # declined consent
    dq_code='REPLACE_DQ',        # disqualified (comprehension / tab monitor)
    # NB: no screened-out code. See PROLIFIC_CODE_PLACEHOLDERS above.

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
    # tests/frozen_config_test.py), and a cache-busting token should follow the
    # build anyway, not the session.
    static_version=STATIC_VERSION,
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
        # cc_code / noconsent_code / dq_code default to REPLACE_* placeholders;
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
    'focus_loss_count',     # tab-monitor authoritative violation count
    'focus_event_ids',      # tab-monitor seen event ids (server-side dedup)
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
# - ai_safety_disqualified / focus_loss_count / focus_event_ids: tab monitor state.
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
        # Check the EFFECTIVE config (defaults + entry), since keys like cc_code
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
        if eff.get('completion_redirects'):
            for code_key in ('cc_code', 'noconsent_code', 'dq_code'):
                value = eff.get(code_key)
                if value in PROLIFIC_CODE_PLACEHOLDERS:
                    problems.append(
                        (f"config {cfg['name']!r} {code_key}", value,
                         'a real Prolific completion code (not a REPLACE_* placeholder)'))
            # THE SCREEN-OUT RETURN URL, guarded in the same family as the codes
            # but for the opposite reason to the code we deliberately do NOT
            # have: this one is really used (it is the whole way off the
            # screen-out page), so an unreplaced placeholder is a participant
            # stranded with no route back to the platform. Gated on
            # `completion_redirects` for the same reason the codes are — that
            # flag is what means "this study sends people back to a platform";
            # a lab session has nowhere to return to and is never asked.
            # A DELIBERATELY BLANK value is a legitimate choice (render no link
            # at all) and is not flagged — only the untouched placeholder is.
            if eff.get('screenout_return_url') == SCREENOUT_RETURN_URL_PLACEHOLDER:
                problems.append(
                    (f"config {cfg['name']!r} screenout_return_url",
                     SCREENOUT_RETURN_URL_PLACEHOLDER,
                     'the real URL a screened-out participant is sent back to '
                     '(e.g. https://app.prolific.com/), or blank for no link — '
                     'NOT the REPLACE_* placeholder'))
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
