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
# `unknown` IS ITS OWN TYPE, not a synonym for "computer". It means a real
# User-Agent was read and matches none of the three families. Whether such a
# device may take part is a study's decision, so it is listed in
# `allowed_devices` exactly like the other three and can be admitted or
# excluded without touching any code. It does NOT mean "no User-Agent" — that
# is UNDETERMINED, immediately below, and the difference is load-bearing.
#
# The matching is deliberately ORDERED (tablet, then phone, then computer): an
# iPad's User-Agent contains "Mobile" and an Android tablet's differs from an
# Android phone's ONLY by the absence of the word "Mobile", so a phone-first
# test would call every tablet a phone.
DEVICE_TYPES = ('phone', 'tablet', 'computer', 'unknown')

# =============================================================================
# 'unknown' IS A DEVICE TYPE.  UNDETERMINED IS NOT A DEVICE AT ALL.
# =============================================================================
# These two used to be the same answer, and that was a live false-positive
# waiting to happen: `unknown` was returned BOTH for "we read a real User-Agent
# and it matches none of the three families" AND for "there was nothing to read"
# (absent header, empty string, an exception in the classifier). A study that
# narrows `allowed_devices` and leaves 'unknown' off the list was therefore
# ejecting laptops whose header merely failed to arrive — the exact false
# positive that costs real participants.
#
#   'unknown'     — DETERMINED. A usable User-Agent string was read and did not
#                   match phone, tablet or computer. It is a real device type: a
#                   study may list it in `allowed_devices` or leave it out, and
#                   leaving it out screens such a participant out on purpose.
#   UNDETERMINED  — NO DECISION. There was no usable header to classify: no
#                   request object at all (oTree instantiates pages WITHOUT one
#                   while it walks the skip chain), no User-Agent, an empty or
#                   whitespace-only one, one carrying characters a header may not
#                   contain, one absurdly longer than any real browser sends, or
#                   an exception anywhere in the classifier. It is NEVER a
#                   member of `allowed_devices`, it can never screen anybody out,
#                   and — see the asymmetry below — it can never clear anybody
#                   either. The gate records NOTHING and tries again on the next
#                   real request.
UNDETERMINED = 'undetermined'

# WHERE THE BOUNDARY BETWEEN "GARBAGE" AND "MERELY UNRECOGNISED" SITS, and why
# there. Both of these tests are about whether the STRING IS USABLE AT ALL, not
# about whether we recognise the browser in it:
#
#   * LENGTH. Real User-Agents run to ~200 characters; the longest seen in the
#     wild (a Windows string carrying several .NET and toolbar tokens) is under
#     600. 1000 is well clear of any real browser and well under the 4-8KB
#     header limit a proxy would enforce, so anything longer is a probe or a
#     fuzzer, not a device — and, being UNDETERMINED, it is ALLOWED IN.
#   * CHARACTERS. RFC 9110 field values are visible ASCII plus space and HTAB.
#     A value carrying C0 controls, NUL, CR or LF is malformed (CR/LF are the
#     header-injection markers), so it is not a string to reason about. High
#     bytes (>= 0x80) are deliberately NOT rejected: a browser with a non-ASCII
#     product token is unusual but real, and rejecting it here would be a
#     judgement about the browser rather than about the header.
#
# Note which way each rule fails: BOTH of them fail towards UNDETERMINED, i.e.
# towards letting the participant in. A "garbage" string containing the word
# iPhone is therefore ALLOWED rather than screened out — deliberately.
MAX_USABLE_UA_LEN = 1000
_ILLEGAL_UA_CHARS_RE = re.compile(r'[\x00-\x08\x0a-\x1f\x7f]')

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
    # True once a screen-out has EVER been lifted for this participant. Stays
    # True even if they are later screened again, so "this person switched
    # device" is one column in the export instead of a JSON blob to parse.
    participant.screenout_cleared = False
    # THE CONSENT BOUNDARY, as a durable participant-level fact rather than a
    # page index: set in `before.welcome.before_next_page` when the consent page
    # is SUBMITTED (consenting or not), and read by the device gate, which never
    # touches a participant past it. Not an index, because adding a page moves
    # every index; not anything id-related, because the gate must be able to
    # answer the question on a request for any page.
    participant.consent_submitted = False


def stamp_stage(participant, stage):
    """Record epoch seconds for a named flow stage in ``participant.stage_timestamps``."""
    stamps = participant.vars.get('stage_timestamps') or {}
    stamps[stage] = time.time()
    participant.stage_timestamps = stamps


def set_exit_code(participant, code):
    """Record the numeric outcome for this participant (see settings.EXIT_CODES)."""
    participant.exit_code = code


def classify_device(user_agent) -> str:
    """Classify an entry request's User-Agent.

    Returns one of DEVICE_TYPES ('phone', 'tablet', 'computer', 'unknown') when
    a usable header was read, or UNDETERMINED when there was nothing usable to
    classify. NEVER raises and never returns anything else, so a caller can
    always index a copy table with it.

    THE TWO ANSWERS THAT LOOK ALIKE AND ARE NOT (see the note at the top of this
    file, which is the full argument):

      * 'unknown'    — a real, usable User-Agent that matches none of the three
                       device families. A DEVICE TYPE: a study may admit or
                       exclude it in `allowed_devices` like any other.
      * UNDETERMINED — no usable header at all (missing, empty, malformed,
                       absurdly long, or an exception on the way). NOT a device
                       type, never in `allowed_devices`, screens nobody out and
                       clears nobody. The gate records nothing and re-decides on
                       the next real request.

    ORDER MATTERS for the three families: tablets first (an iPad says "Mobile"),
    then phones, then computers.

    (Renamed from `detect_device_type` on 2026-08-12 when the two answers above
    were split. The old name is gone rather than aliased: its contract — "always
    one of four types" — is the thing that was wrong, so a caller still holding
    it must be looked at, not silently redirected.)
    """
    try:
        if isinstance(user_agent, (bytes, bytearray)):
            ua = user_agent.decode('latin-1', 'replace')
        elif isinstance(user_agent, str):
            ua = user_agent
        else:
            return UNDETERMINED          # None, or something that is not a header
        if not ua.strip():
            return UNDETERMINED
        if len(ua) > MAX_USABLE_UA_LEN:
            return UNDETERMINED
        if _ILLEGAL_UA_CHARS_RE.search(ua):
            return UNDETERMINED
        if TABLET_UA_RE.search(ua):
            return 'tablet'
        if PHONE_UA_RE.search(ua):
            return 'phone'
        if COMPUTER_UA_RE.search(ua):
            return 'computer'
        return 'unknown'
    except Exception:
        # A classifier that raises must not decide anything, and above all must
        # not decide against the participant (the instrumentation rule).
        return UNDETERMINED


def is_mobile_user_agent(user_agent) -> bool:
    """True when an entry request's User-Agent looks like a phone or a tablet.

    Kept as a convenience for MEASUREMENT (and for any study code that only
    cares about "small screen"); the entry gate itself uses the four-way
    classify_device above, because "mobile or not" cannot express an
    allow-list. An UNDETERMINED header is not a mobile device — it is not any
    device — so this is False for it.
    """
    return classify_device(user_agent) in ('phone', 'tablet')


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


# =============================================================================
# THE ASYMMETRY.  READ THIS BEFORE TOUCHING EITHER PREDICATE BELOW.
# =============================================================================
# The screen-out is a SOFT WALL: it can be lifted again by a later pre-consent
# request from an acceptable device (see `before._apply_device_gate`). That
# makes TWO questions out of what looks like one, and they must NOT be written
# as each other's negation:
#
#   SCREENING SOMEBODY OUT needs positive evidence of a device the study does
#   not accept. Absence of evidence (UNDETERMINED) means ALLOWED — fail open,
#   record nothing, ask again on the next real request. A false positive turns a
#   real participant away; a false negative costs one noisy row.
#
#   CLEARING AN EXISTING SCREEN-OUT needs positive evidence of a device the
#   study DOES accept — the detected type must be EXPLICITLY in the allow-list.
#   Absence of evidence must NOT clear. If UNDETERMINED could clear, anyone
#   screened out could lift their own screen-out by arriving with no User-Agent,
#   which takes about ten seconds to do, and the gate would be a suggestion.
#
# So: `device_clears_screenout` is written as EXPLICIT MEMBERSHIP of the
# allow-list and must stay that way. Do NOT rewrite it as "not screened out", as
# "not in the rejected set", or as `not device_screens_out(...)` — every one of
# those formulations lets the sentinel through, because UNDETERMINED is in
# neither set.
# =============================================================================

def device_screens_out(config, detected) -> bool:
    """Is this classification positive evidence of an EXCLUDED device?

    False for UNDETERMINED (no evidence at all) and false for anything that is
    not one of DEVICE_TYPES, so only a determined type the study does not list
    can ever remove somebody.
    """
    if detected not in DEVICE_TYPES:      # UNDETERMINED, or a value from nowhere
        return False
    return detected not in allowed_devices(config)


def device_clears_screenout(config, detected) -> bool:
    """Is this classification positive evidence of an ACCEPTED device?

    EXPLICIT MEMBERSHIP, deliberately — see the asymmetry note above.
    `allowed_devices` only ever contains members of DEVICE_TYPES, so
    UNDETERMINED cannot satisfy this no matter what a config says.

    THE INVARIANT, AND THE TEST TO APPLY TO ANY NEW DEVICE TYPE
    ----------------------------------------------------------
    **The clear predicate must be exactly the entry-allow predicate MINUS
    UNDETERMINED.** Nothing else is safe or coherent, in either direction:

      * if CLEAR allows MORE than entry, there is a hole — somebody lifts a
        screen-out with a device that would not have been let in;
      * if CLEAR allows LESS than entry, the screen-out page is telling somebody
        that switching devices will work when for them it cannot. That is the
        mistake the implementation this was adapted from made: their `unknown`
        never cleared, even in a study that admitted unknown devices. Their
        concrete victim: a laptop whose User-Agent is stripped by a privacy tool
        or a corporate proxy classifies as unknown and is admitted on a fresh
        visit — but if that person first opened the study on their phone they
        are screened, and switching to that very laptop does not lift it, while
        the page in front of them says to switch devices. Rare, and exactly the
        person the soft wall exists for.

    WHY OURS CANNOT BE EXPLOITED, stated as the rule to check a new type
    against rather than as a description of today's code: **anything that
    clears could equally have entered fresh on that same device**, so admitting
    it on the clear path takes nothing away from the gate. Add a fifth device
    type tomorrow and the question to ask is that one — if a participant
    arriving on it for the first time would be let in, it must also lift an
    existing screen-out; if it would not, it must not.

    UNDETERMINED is the single carve-out, and it is the one case where the two
    predicates deliberately differ: it is not a device at all, so "could they
    have entered fresh on it?" has no answer, and treating it as a clear would
    let anyone lift their own screen-out by sending no User-Agent. The cost is
    accepted and is the residual gap in OUR version too — somebody screened on a
    phone who switches to a laptop that sends no usable header stays screened.
    Their remedy is the way off the page, not a header we cannot read.
    """
    return detected in allowed_devices(config)


def device_gate_decision(config, user_agent):
    """(detected, screens_out, clears) for one entry request.

    THE SERVER DECIDES. The client also reports what it thinks it is
    (device_capture.js writes a `device_type` into the device-info JSON), but
    that is MEASUREMENT: it arrives after this gate has already run, and a
    client-side value can be edited by anyone, so it never gates anything. When
    the two disagree, the server's answer is the one recorded and the one acted
    on; the client's is kept beside it so the disagreement is visible in the
    export.

    The two booleans are NOT complements: for UNDETERMINED both are False, which
    is the whole point (allowed on entry, but not evidence that lifts a
    screen-out).
    """
    detected = classify_device(user_agent)
    return (detected,
            device_screens_out(config, detected),
            device_clears_screenout(config, detected))


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


def screenout_return_url(config) -> str:
    """The way OUT for a screened-out participant: the recruitment platform's
    own site, carrying NO completion code.

    THERE IS DELIBERATELY NO SCREENED-OUT COMPLETION CODE. Submitting one would
    close the participant's Prolific submission the instant they clicked it, and
    a returned submission can never be retaken — which forecloses exactly the
    outcome the screen-out page is trying to produce, namely that they reopen
    the study on a computer and finish it. Their submission therefore stays
    OPEN, and returning it stays their decision, taken on Prolific.

    Read through `cfg` so a session created before the parameter existed falls
    back to the shipped default instead of 500-ing on the one page a stranded
    participant needs. Returns '' if a study blanks it, and the template then
    renders no link at all rather than a broken one. Escaping happens at the
    point of use, in the template.
    """
    try:
        return str(cfg(config, 'screenout_return_url') or '').strip()
    except Exception:
        return ''


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
    # NB: 'unknown' is the DETERMINED unknown — a real User-Agent that matches
    # no device family. A request with NO usable User-Agent is UNDETERMINED, is
    # never screened out and never reaches this table at all.
    'unknown': 'Entry device sent a User-Agent this template does not recognise, '
               'and allowed_devices does not admit unknown devices.',
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

    WRITTEN AT DECISION TIME, not when the screen-out page renders: a
    participant who reads that page and closes the tab must still export as a
    screen-out rather than as an abandoner.
    """
    participant.screened_out = True
    set_exit_code(participant, EXIT_CODES['screened_out'])
    extra_set(participant, SCREENOUT_CAUSE_KEY, cause)


def clear_screened_out(participant):
    """Lift a screen-out: this participant is doing the study after all.

    Called only with POSITIVE evidence of an accepted device, before consent
    (see the asymmetry note above and `before._apply_device_gate`). Somebody who
    switched to a device the study accepts must not sit in the data as screened
    out while completing the study.

    EACH VALUE IS REVERTED ONLY IF IT STILL HOLDS WHAT THE SCREEN-OUT PUT
    THERE. The exit code goes back to `abandoned` only while it is still
    `screened_out`, and the cause is dropped only while it is still one this
    gate wrote. Anything else — a tab-monitor disqualification that landed in
    the same window, a future gate's own cause — is left exactly as it is, so a
    clear can never clobber another mechanism's record.

    THE STATE IS RESET; THE HISTORY IS NOT. The appended audit trail
    (`screenout_history`) keeps the original screen-out entry, and
    `screenout_cleared` stays True for good. Without that, clearing the exit
    code would erase the evidence that anybody was ever turned away and nobody
    could count what the gate stopped.

    ACCEPTED CONSEQUENCE, stated plainly: once the exit code is clearable it is
    no longer write-once. An export taken while somebody is mid-switch shows a
    `-4` that later becomes something else. That is the price of the soft wall,
    and `screenout_cleared` plus the history is how you tell such a row apart
    from one that never moved.
    """
    participant.screened_out = False
    participant.screenout_cleared = True
    if participant.vars.get('exit_code') == EXIT_CODES['screened_out']:
        set_exit_code(participant, EXIT_CODES['abandoned'])
    if screenout_cause(participant) in SCREENOUT_CAUSES:
        extra_set(participant, SCREENOUT_CAUSE_KEY, '')


def screenout_cleared(participant) -> bool:
    """True if a screen-out has ever been lifted for this participant."""
    return bool(participant.vars.get('screenout_cleared'))


# --- the screen-out audit history --------------------------------------------
# One entry per REAL EVENT, appended and never overwritten: it is the only way
# to diagnose a false positive after the fact, or to see that somebody switched
# device. Lives in the free JSON bucket rather than in its own column because it
# is a variable-length record; the flat facts an analyst filters on
# (`screened_out`, `screenout_cleared`, `exit_code`) are all first-class fields.
SCREENOUT_HISTORY_KEY = 'screenout_history'
MAX_SCREENOUT_HISTORY = 20
SCREENOUT_UA_TRUNC = 300      # an audit note, not a payload


def screenout_history(participant) -> list:
    """The decision history, oldest first ([] if the gate never decided)."""
    entries = extra_get(participant, SCREENOUT_HISTORY_KEY)
    return list(entries) if isinstance(entries, list) else []


def append_screenout_history(participant, user_agent, device, screened, action):
    """Append one decision to the audit history. Never overwrites, never raises.

    DEDUPED: a reload re-runs the gate with the same header and the same
    outcome, and a history full of that would bury the events a reader is
    looking for, so a repeat of the previous entry is dropped.

    CAPPED, BUT THE FIRST ENTRY IS PERMANENT: the original decision is the one a
    false-positive investigation needs, so when the cap bites it is the MIDDLE
    of the history that is dropped, never the beginning.
    """
    try:
        entry = dict(
            ts=int(time.time()),
            ua=str(user_agent or '')[:SCREENOUT_UA_TRUNC],
            device=device,
            screened_out=bool(screened),
            action=action,
        )
        entries = screenout_history(participant)
        if entries:
            last = entries[-1]
            if (isinstance(last, dict)
                    and last.get('ua') == entry['ua']
                    and last.get('device') == entry['device']
                    and last.get('screened_out') == entry['screened_out']):
                return                      # a reload, not an event
        entries.append(entry)
        if len(entries) > MAX_SCREENOUT_HISTORY:
            entries = entries[:1] + entries[-(MAX_SCREENOUT_HISTORY - 1):]
        extra_set(participant, SCREENOUT_HISTORY_KEY, entries)
    except Exception:
        # Instrumentation must never break a page — least of all the page whose
        # job is to give a screened-out participant a way out.
        pass


# --- the consent boundary ----------------------------------------------------

def consent_submitted(participant) -> bool:
    """True once this participant has SUBMITTED the consent page.

    The boundary the device gate stops at. A durable participant-level fact, not
    a page index and nothing to do with an id:

      * the gate answers requests for whatever page the participant is on, and
        oTree also instantiates pages with no request at all while it walks the
        skip chain, so it needs a fact it can read, not a question about where
        somebody is;
      * page indices move the moment the page sequence changes — which this very
        feature does — so a positional boundary silently drifts.

    Set for EVERYONE who submits that page, whether they consented or not: a
    non-consenter is past the point this gate guards just as much as a
    consenter is.
    """
    return bool(participant.vars.get('consent_submitted'))


def mark_consent_submitted(participant):
    """Record that the consent page has been submitted (see above). Idempotent."""
    participant.consent_submitted = True


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
