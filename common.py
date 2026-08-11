"""Shared, oTree-free helpers used across every app.

Import as ``import common``. Keeping these here (not inside any one app) means
every app reads participant state and records outcomes the same way.

This file MUST stay at the project root. All four apps do a top-level
``import common``, and oTree puts the project root on ``sys.path``; moving it into
a subfolder (e.g. scripts/) would break that import for every app.
"""
import re
import time

from settings import EXIT_CODES  # re-exported for convenience

# Phone/tablet markers in a User-Agent string. Server-side twin of the UA test in
# _static/global/js/device_capture.js — which also requires a small viewport,
# because it runs in a real browser. The gate below runs on the FIRST request,
# before any page is rendered, so the User-Agent is all there is; that is also
# exactly why it is the only check that can happen BEFORE the consent page.
MOBILE_UA_RE = re.compile(
    r'Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini'
    r'|Windows Phone|Mobile Safari|Mobile/\d',
    re.IGNORECASE,
)


def pvar(participant, name, default=None):
    """Safe read of a participant field.

    ALWAYS use this (or ``participant.vars.get()``) instead of
    ``getattr(participant, name, default)``. oTree's participant-vars descriptor
    raises ``KeyError`` — NOT ``AttributeError`` — for a field that has not been
    set yet, so a ``getattr`` default does not protect you and the page 500s.
    (Learnt from a live outage; see conventions.md.)
    """
    return participant.vars.get(name, default)


def cfg(config, name):
    """Safe read of a SESSION CONFIG value. Use this, never ``config[name]``.

    oTree copies the session config onto the Session row when the session is
    CREATED and never refreshes it, so a parameter added to
    ``settings.SESSION_CONFIG_DEFAULTS`` in a later deploy is simply ABSENT from
    the config of every session already running. ``config['new_param']`` then
    raises ``KeyError`` — an HTTP 500 for a participant mid-study, visible only
    in the container log. (That is a live outage from the pilot this template
    came from, not a hypothetical; see CLAUDE.md.)

    This reads through to the value SHIPPED in settings for that parameter, so a
    frozen session transparently gets the default instead of 500-ing, while a
    key that was never shipped at all raises a KeyError that NAMES the
    parameter — a typo stays loud rather than degrading to a silent None.

    ``config`` may be a session config mapping or anything dict-like
    (``player.session.config``).
    """
    from settings import SESSION_CONFIG_DEFAULTS
    try:
        return config[name]
    except (KeyError, TypeError):
        pass
    if name in SESSION_CONFIG_DEFAULTS:
        return SESSION_CONFIG_DEFAULTS[name]
    raise KeyError(
        f"unknown session config parameter {name!r}: it is not on this "
        f"session's (frozen) config and has no default in "
        f"settings.SESSION_CONFIG_DEFAULTS")


def init_participant(participant):
    """Initialise every participant field at session creation.

    Called once from ``before.creating_session`` so no export row is ever blank —
    in particular ``exit_code`` starts at 0 (abandoned) and is raised to 1 only
    when the participant actually finishes.
    """
    participant.exit_code = EXIT_CODES['abandoned']   # 0 until they finish
    participant.failed_attempts = 0
    participant.payoff_vector = []
    participant.stage_timestamps = {}
    participant.participant_extra = {}
    participant.participant_id_external = participant.vars.get('participant_id_external', '')
    participant.ai_safety_disqualified = False
    participant.focus_loss_count = 0
    participant.focus_event_ids = []
    participant.comprehension_disqualified = False
    participant.instructions_reread_used = False
    participant.device_info = {}
    participant.screened_out = False


def stamp_stage(participant, stage):
    """Record epoch seconds for a named flow stage in ``participant.stage_timestamps``."""
    stamps = participant.vars.get('stage_timestamps') or {}
    stamps[stage] = time.time()
    participant.stage_timestamps = stamps


def set_exit_code(participant, code):
    """Record the numeric outcome for this participant (see settings.EXIT_CODES)."""
    participant.exit_code = code


def is_mobile_user_agent(user_agent) -> bool:
    """True when an entry request's User-Agent looks like a phone/tablet."""
    return bool(MOBILE_UA_RE.search(user_agent or ''))


def is_screened_out(participant) -> bool:
    """True once an entry screen-out gate has removed this participant.

    Every page between entry and the ending consults this (like the tab
    monitor's ``ai_safety_disqualified``), so a screened-out participant is
    walked straight past consent, the instructions, the quiz and the task to the
    outro ending. Reads participant vars with .vars.get() — never getattr().
    """
    return bool(participant.vars.get('screened_out'))


# --- entry screen-out causes -------------------------------------------------
# Exit code -4 (``screened_out``) is the GENERAL "removed at entry" bucket, not a
# phone-specific code. Which gate fired is recorded separately, as a cause string
# in participant_extra, and that cause is what selects the sentence the
# participant reads on the ending (see outro/Ended.html).
#
# WHY THE CODE STAYS GENERIC: the exit-code table in CODEBOOK.md is a contract —
# every code in it must be set by a real code path, so codes are not minted
# speculatively. A new screen-out reason therefore adds a CAUSE and a sentence
# here, NOT a new exit code. Analysis still gets one clean "screened out at
# entry" bucket, and splitting by reason is a filter on the cause column.
#
# To add one: append it here, set it at the gate via ``set_screened_out``, and
# add a branch in outro/Ended.html. Ship nothing without its own sentence.
SCREENOUT_CAUSE_KEY = 'screenout_cause'
SCREENOUT_CAUSES = {
    'mobile': 'Entry User-Agent looked like a phone/tablet (mobile_screenout).',
}


def extra_get(participant, key, default=None):
    """Read one key out of the participant's free JSON bucket (participant_extra).

    Safe on a participant whose bucket predates the key (or the bucket itself).
    """
    bucket = participant.vars.get('participant_extra') or {}
    return bucket.get(key, default)


def screenout_cause(participant) -> str:
    """Why this participant was screened out at entry ('' if not / unrecorded).

    An empty string is a legitimate answer, not an error: a study that sets exit
    code -4 from a new gate without recording a cause still gets the neutral
    fallback sentence on the ending rather than another gate's wording.
    """
    return extra_get(participant, SCREENOUT_CAUSE_KEY, '') or ''


def set_screened_out(participant, cause):
    """Remove this participant at entry, recording WHY.

    One call so a gate cannot record the flag and the exit code but forget the
    cause. Idempotent at the caller's discretion (check ``is_screened_out``
    first, so a page reload never re-stamps).
    """
    participant.screened_out = True
    set_exit_code(participant, EXIT_CODES['screened_out'])
    extra_set(participant, SCREENOUT_CAUSE_KEY, cause)


def extra_set(participant, key, value):
    """Write one key into the participant's free JSON bucket (participant_extra)."""
    bucket = participant.vars.get('participant_extra') or {}
    bucket[key] = value
    participant.participant_extra = bucket


def focus_live_method(player, data):
    """Server-authoritative tab-switch handler (bind as live_method on monitored pages).

    Counts each real focus-loss once (deduped by client-supplied event_id) and
    disqualifies at the configured threshold, broadcasting {action:'disqualified'}
    to that player so the client reloads onto the ending. No-op unless the
    tab_monitor flag is on. See settings + _static/global/js/ai_safety_monitor.js.
    """
    # NB the local name is `config`, not `cfg`: `cfg` is this module's safe
    # session-config accessor and shadowing it here would hide it.
    config = player.session.config
    if not config.get('tab_monitor'):
        return
    if not isinstance(data, dict) or data.get('type') != 'focus_loss':
        return
    event_id = data.get('event_id')
    seen = player.participant.vars.get('focus_event_ids') or []
    if event_id in seen:
        return  # dedup: count each real loss once
    seen.append(event_id)
    player.participant.focus_event_ids = seen
    count = (player.participant.vars.get('focus_loss_count') or 0) + 1
    player.participant.focus_loss_count = count
    max_violations = int(cfg(config, 'tab_monitor_max_violations'))
    if count >= max_violations:
        player.participant.ai_safety_disqualified = True
        set_exit_code(player.participant, EXIT_CODES['tab_monitor'])
        return {player.id_in_group: dict(action='disqualified')}
