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

# =============================================================================
# DEVICE TYPES — what the entry gate can tell apart, and what it cannot
# =============================================================================
# FOUR TYPES, AND ONLY FOUR: phone, tablet, computer, unknown.
#
# THERE IS NO 'laptop' TYPE, AND ONE CANNOT BE ADDED. A browser does not expose
# the form factor of a computer: neither the User-Agent string nor the modern
# client hints (Sec-CH-UA-Mobile, Sec-CH-UA-Platform, navigator.userAgentData)
# distinguish a laptop from a tower. Both send the same platform ("Windows",
# "macOS", "Linux") with the mobile hint false. Battery, touch support and
# screen size do not fix it either — a desktop can have a touch screen, a
# laptop can be docked to a 27" monitor with the lid shut, and the Battery
# Status API is removed or permission-gated in current browsers. So a laptop
# and a desktop are BOTH `computer`. If a future study needs "laptop only", it
# cannot have it from the browser; it has to ask the participant.
#
# `unknown` IS ITS OWN TYPE, not a synonym for "computer". It means the
# detection could not identify the device at all: the User-Agent header was
# absent, blank, stripped by a privacy tool, or simply unrecognised. Whether an
# unknown device may take part is a study's decision, so it is listed in
# `allowed_devices` exactly like the other three and can be admitted or
# excluded without touching any code.
#
# The matching is deliberately ORDERED (tablet, then phone, then computer): an
# iPad's User-Agent contains "Mobile" and an Android tablet's differs from an
# Android phone's ONLY by the absence of the word "Mobile", so a phone-first
# test would call every tablet a phone.
DEVICE_TYPES = ('phone', 'tablet', 'computer', 'unknown')

# Tablets. iPad (including iPadOS 13+, which lies and says "Macintosh" but is
# caught by the touch check client-side — server-side such an iPad reads as a
# computer, which is recorded honestly rather than guessed at), Android without
# "Mobile", Kindle/Silk, PlayBook, and anything self-declaring "Tablet".
TABLET_UA_RE = re.compile(
    r'iPad|Android(?!.*Mobile)|Tablet|Kindle|Silk|PlayBook|Nexus (?:7|9|10)',
    re.IGNORECASE,
)

# Phones. Server-side twin of the UA test in
# _static/global/js/device_capture.js — which ALSO requires a small viewport,
# because it runs in a real browser and can. The gate runs on the FIRST
# request, before any page exists, so the User-Agent is all there is; that is
# exactly why it is the only check that can happen BEFORE the consent page.
PHONE_UA_RE = re.compile(
    r'iPhone|iPod|Android.*Mobile|webOS|BlackBerry|BB10|IEMobile|Opera Mini'
    r'|Windows Phone|Mobile Safari|Mobile/\d',
    re.IGNORECASE,
)

# Computers — desktops AND laptops, which are the same thing here (see above).
COMPUTER_UA_RE = re.compile(
    r'Windows NT|Macintosh|Mac OS X|X11|CrOS|Linux(?!.*Android)|FreeBSD|OpenBSD',
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


def detect_device_type(user_agent) -> str:
    """Classify an entry request's User-Agent as one of DEVICE_TYPES.

    Returns 'phone', 'tablet', 'computer' or 'unknown'. NEVER raises and never
    returns anything else, so a caller can always index a copy table with it.

    'unknown' is a real answer, not a failure: an absent, blank or stripped
    User-Agent, or one this template does not recognise. A study decides
    whether unknown devices may take part by listing (or not listing) 'unknown'
    in `allowed_devices` — see the DEVICE TYPES note at the top of this file,
    which also explains why there is no 'laptop' type and cannot be one.

    ORDER MATTERS: tablets first (an iPad says "Mobile"), then phones, then
    computers.
    """
    ua = user_agent or ''
    if not ua.strip():
        return 'unknown'
    if TABLET_UA_RE.search(ua):
        return 'tablet'
    if PHONE_UA_RE.search(ua):
        return 'phone'
    if COMPUTER_UA_RE.search(ua):
        return 'computer'
    return 'unknown'


def is_mobile_user_agent(user_agent) -> bool:
    """True when an entry request's User-Agent looks like a phone or a tablet.

    Kept as a convenience for MEASUREMENT (and for any study code that only
    cares about "small screen"); the entry gate itself uses the four-way
    detect_device_type above, because "mobile or not" cannot express an
    allow-list.
    """
    return detect_device_type(user_agent) in ('phone', 'tablet')


def is_screened_out(participant) -> bool:
    """True once an entry screen-out gate has removed this participant.

    Every page between entry and the ending consults this (like the tab
    monitor's ``ai_safety_disqualified``), so a screened-out participant is
    walked straight past consent, the instructions, the quiz and the task to the
    outro ending. Reads participant vars with .vars.get() — never getattr().
    """
    return bool(participant.vars.get('screened_out'))


def allowed_devices(config) -> tuple:
    """The device types this session admits, normalised and validated.

    Accepts what a human might reasonably put in a session config: a list, a
    tuple, a set, or a comma-separated string ('phone, computer'). Case and
    spacing are ignored; unknown words are DROPPED rather than silently
    admitting or excluding everyone by accident.

    THE DEFAULT SHIPPED IN settings.py IS ALL FOUR TYPES, which means the gate
    is OFF: every device is permitted, so it can have no participant-visible
    effect at all until a study deliberately narrows the list. An EMPTY list
    would exclude every participant, so it is treated as "no gate" too, and the
    caller is expected to say so loudly rather than screening the whole sample
    out because of a typo.

    Read through common.cfg, so a session config frozen before this parameter
    existed transparently gets the permissive default instead of 500-ing.
    """
    raw = cfg(config, 'allowed_devices')
    if isinstance(raw, str):
        items = raw.split(',')
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = list(raw)
    else:
        items = []
    wanted = tuple(
        t for t in DEVICE_TYPES
        if any(str(item).strip().lower() == t for item in items)
    )
    return wanted or DEVICE_TYPES


def device_gate_verdict(config, user_agent):
    """(detected_type, is_allowed) for one entry request.

    THE SERVER DECIDES. The client also reports what it thinks it is
    (device_capture.js writes a `device_type` into the device-info JSON), but
    that is MEASUREMENT: it arrives after this gate has already run, and a
    client-side value can be edited by anyone, so it never gates anything. When
    the two disagree, the server's answer is the one recorded and the one acted
    on; the client's is kept beside it so the disagreement is visible in the
    export.
    """
    detected = detect_device_type(user_agent)
    return detected, detected in allowed_devices(config)


DEVICE_TYPE_LABELS = {
    'phone': 'a phone',
    'tablet': 'a tablet',
    # Laptop and desktop are ONE type; the browser cannot tell them apart (see
    # the DEVICE TYPES note at the top of this file).
    'computer': 'a desktop or laptop computer',
    'unknown': 'this device',
}


# Short forms, for when several types are listed in one sentence: "a phone, a
# tablet or a computer" reads; "…or a desktop or laptop computer" does not.
DEVICE_TYPE_SHORT_LABELS = dict(DEVICE_TYPE_LABELS, computer='a computer')


def device_types_phrase(types) -> str:
    """'a phone or a tablet' — the permitted devices, for participant-facing copy.

    'unknown' is never named: it is not a device a participant could go and
    find. A list that permits ONLY unknown devices therefore falls back to the
    neutral phrase rather than telling someone to use "this device".
    """
    wanted = [t for t in DEVICE_TYPES if t in tuple(types) and t != 'unknown']
    if not wanted:
        return 'a supported device'
    if len(wanted) == 1:
        return DEVICE_TYPE_LABELS[wanted[0]]
    labels = [DEVICE_TYPE_SHORT_LABELS[t] for t in wanted]
    return ', '.join(labels[:-1]) + ' or ' + labels[-1]


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
#
# THE DEVICE GATE'S CAUSE IS THE DETECTED TYPE. It records what the participant
# actually came in on — 'phone', 'tablet', 'computer' or 'unknown' — not the
# name of the gate, so the ending can say something true for each case instead
# of always claiming the study needs a computer. (Before 2026-08-11 there was a
# single cause, 'mobile', from a phones-only gate; the allow-list replaced it.)
SCREENOUT_CAUSE_KEY = 'screenout_cause'
SCREENOUT_CAUSES = {
    'phone': 'Entry device detected as a phone, which allowed_devices excludes.',
    'tablet': 'Entry device detected as a tablet, which allowed_devices excludes.',
    'computer': 'Entry device detected as a computer (desktop or laptop — the '
                'browser cannot tell them apart), which allowed_devices excludes.',
    'unknown': 'Entry device could not be identified (no or unrecognised '
               'User-Agent), and allowed_devices does not admit unknown devices.',
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
