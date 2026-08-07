import os
from os import environ

# =============================================================================
# PARAMETER SCHEME  (read this first — everything else hangs off it)
# =============================================================================
# Every optional module in this template is controlled by ONE feature flag in
# SESSION_CONFIG_DEFAULTS, and every flag ships OFF by default. A new project
# therefore starts with a bare, correct baseline and opts in to each module
# deliberately.
#
# On top of the flags sits a single `recruitment` profile (prolific | lab |
# testing). A profile is a NAMED BUNDLE of flag/threshold values. At import time
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
EXIT_CODES = dict(
    finished=1,          # completed the study normally
    abandoned=0,         # default: created but never reached the end
    no_consent=-1,       # declined consent
    comprehension=-2,    # disqualified: failed the comprehension check
    tab_monitor=-3,      # disqualified: AI-safety / tab-switch monitor
    screened_out=-4,     # screened out at entry (e.g. mobile device)
    timed_out=-5,        # inactivity / never matched in time
)

# --- recruitment profiles ----------------------------------------------------
# Each profile is a bundle of explicit values resolved into the config at import
# (see resolve_recruitment_profile). Add keys here to have a profile govern
# them; anything not listed falls through to the SESSION_CONFIG_DEFAULTS baseline
# and can still be overridden per config.
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
        verify_quiz=True,
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
        verify_quiz=True,
    ),
    # Local development / clickthrough: everything off and thresholds loosened
    # so you can walk the whole flow without being blocked.
    'testing': dict(
        capture_participant_id=False,
        completion_redirects=False,
        tab_monitor=False,
        comprehension_dq=False,
        passive_capture=False,
        device_capture=False,
        collect_bank_details=False,
        verify_quiz=False,           # loosened: click straight through the quiz
    ),
}

DEFAULT_RECRUITMENT = 'lab'

# Placeholder Prolific completion codes. Real codes are created in the Prolific
# study UI and pasted per config; the prelaunch banner flags any REPLACE_*
# sentinel that survives to launch.
PROLIFIC_CODE_PLACEHOLDERS = ('REPLACE_CC', 'REPLACE_NC', 'REPLACE_DQ', 'REPLACE_ERR')

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00,
    participation_fee=0.00,
    doc="",

    # --- recruitment profile (resolved into explicit flags at import) --------
    recruitment=DEFAULT_RECRUITMENT,

    # --- study/design quantities --------------------------------------------
    quiz_bonus=5,
    num_rewarded=2,
    showup=2.5,
    # NUM_ROUNDS is fixed at import from this value (the MAX). A config may set
    # it LOWER to run fewer rounds, never higher.
    num_experimental_rounds=10,

    # --- module feature flags (ALL OFF by default) --------------------------
    # A recruitment profile or an explicit per-config value turns these on.
    verify_quiz=True,            # validate quiz answers before proceeding
    capture_participant_id=False,   # capture an external (e.g. Prolific) ID at entry
    completion_redirects=False,     # send participants back to Prolific with a code
    tab_monitor=False,              # tab-switch / AI-safety monitor
    comprehension_dq=False,         # disqualify on repeated comprehension failure
    passive_capture=False,          # passive hidden-field measurement on the page form
    device_capture=False,           # capture device / screen info at entry
    collect_bank_details=False,     # lab-style IBAN/BIC/SEPA payment collection

    # --- integrity thresholds (used only when the module is on) -------------
    comprehension_max_failures=2,   # disqualify after this many wrong quiz attempts
    tab_monitor_max_violations=2,   # disqualify on the Nth recorded tab-away
    tab_monitor_threshold_ms=4000,  # continuous away-time that counts as a violation
    tab_monitor_overlay_delay_ms=400,  # grace before the warning overlay appears

    # --- Prolific completion codes (placeholders; flagged by prelaunch) -----
    cc_code='REPLACE_CC',        # normal completion
    noconsent_code='REPLACE_NC', # declined consent
    dq_code='REPLACE_DQ',        # disqualified (comprehension / tab monitor)
    error_code='REPLACE_ERR',    # screen-out / inactivity

    # --- static asset cache-busting -----------------------------------------
    # Appended as ?v=... to CSS/JS hrefs so a redeploy is never served a stale
    # cached asset. Bump on every static change.
    static_version='1',
)


def resolve_recruitment_profile(config):
    """Bake a config's recruitment profile into explicit flag values.

    Mutates and returns `config`. For every key the chosen profile governs, the
    profile's value is written into the config UNLESS the config already set that
    key explicitly (an explicit per-config value always wins). The result is a
    config dict that states, in full, exactly what the session will run with —
    which is what the admin session-configuration view displays.
    """
    profile_name = config.get('recruitment', DEFAULT_RECRUITMENT)
    bundle = RECRUITMENT_PROFILES.get(profile_name)
    if bundle is None:
        raise ValueError(
            f"Unknown recruitment profile {profile_name!r}. "
            f"Choose one of: {', '.join(sorted(RECRUITMENT_PROFILES))}."
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
    dict(
        name='test',
        display_name="Test (clickthrough)",
        app_sequence=['before', 'intro', 'main', 'outro'],
        num_demo_participants=10,
        recruitment='testing',
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
    'device_info',          # dict of captured device/screen info, if enabled
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
# - device_info: captured device/screen dict when device_capture is on.

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
DEBUG = 'OTREE_PRODUCTION' not in os.environ  # mirror of oTree's own derivation


def _prelaunch_problems():
    """Return a list of (label, current, must_be) tuples for anything unsafe."""
    problems = []
    if DEBUG:
        problems.append(('DEBUG (set OTREE_PRODUCTION=1)', True, False))

    for cfg in SESSION_CONFIGS:
        # Check the EFFECTIVE config (defaults + entry), since keys like cc_code
        # live in SESSION_CONFIG_DEFAULTS and are merged by oTree at runtime.
        eff = {**SESSION_CONFIG_DEFAULTS, **cfg}
        if eff.get('recruitment') == 'testing':
            # A testing config is fine locally; only warn about it under production.
            if not DEBUG:
                problems.append(
                    (f"config {cfg['name']!r} recruitment", 'testing', 'lab or prolific'))
        # Placeholder completion codes only matter when the config actually
        # redirects to Prolific.
        if eff.get('completion_redirects'):
            for code_key in ('cc_code', 'noconsent_code', 'dq_code', 'error_code'):
                value = eff.get(code_key)
                if value in PROLIFIC_CODE_PLACEHOLDERS:
                    problems.append(
                        (f"config {cfg['name']!r} {code_key}", value,
                         'a real Prolific completion code (not a REPLACE_* placeholder)'))
    return problems


def _check_prelaunch():
    profile_line = ', '.join(
        f"{c['name']}={c.get('recruitment')}" for c in SESSION_CONFIGS)
    print(f"[prelaunch] DEBUG={DEBUG}  recruitment: {profile_line}")
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
