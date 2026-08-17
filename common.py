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

# THE ORDERED RULE LIST — THE ONE PLACE THE THREE FAMILIES ARE DEFINED.
#
# `classify_device` walks this, and `device_ua_rules()` SHIPS IT TO THE BROWSER
# (below) so the client-side twin in `_static/global/js/device_capture.js`
# applies these same patterns instead of keeping its own copy. There is
# therefore no second list to drift — which is the point, and the fix for a real
# defect: while the client kept its own patterns, they had already drifted
# (`Mobile/\d`, `BB10`, `Nexus 7|9|10` server-only; an unanchored `Linux`
# client-side), so an iOS in-app browser was recorded as "server says phone,
# client says unknown" — INDISTINGUISHABLE from the genuine client/server
# disagreement the client's classification exists to expose. See
# `device_ua_rules` for what the client does with these and how the remaining
# states are kept apart.
#
# Order matters: tablets first (an iPad's UA says "Mobile"), then phones, then
# computers. Keep it a tuple of (type, compiled regex) pairs — the JS builds its
# RegExps from `.pattern`, so every pattern must stay valid in BOTH engines
# (lookaheads and \d are fine; named groups and \Z would not be).
DEVICE_UA_RULES = (
    ('tablet', TABLET_UA_RE),
    ('phone', PHONE_UA_RE),
    ('computer', COMPUTER_UA_RE),
)


def device_ua_rules() -> dict:
    """The server's User-Agent rules, as plain data, for the client-side twin.

    Handed to the entry page through `before.welcome.js_vars` and applied by
    `device_capture.js`, so the browser classifies with THE SERVER'S list rather
    than a copy of it.

    WHY THIS EXISTS — a collapsed distinction inside the instrument built to
    detect one. The client's `device_type` is measurement: it is recorded, never
    enforced, and its whole value is that a DISAGREEMENT with the server's
    classification is visible in the export (an iPadOS tablet claiming to be a
    Mac, a stripped User-Agent). But while the client kept its own patterns, a
    disagreement had two possible causes that looked identical:

      * the device's own signals contradict its User-Agent — REAL, and the thing
        the column is for;
      * our two pattern lists simply differed — an artefact of ours, saying
        nothing about the device.

    One list removes the second cause entirely. What is left is kept APART
    rather than merged, and each state is named in the recorded JSON:

      `ua_rules`        'server'      these rules arrived and were applied
                        'unavailable' they did not (no js_vars on this page, or
                                      a malformed payload). The client then
                                      classifies NOTHING and says so — it does
                                      NOT fall back to a private copy of the
                                      list, because a silent fallback is exactly
                                      the second list this removes.
      `device_type_ua`  the client's classification of ITS OWN
                        navigator.userAgent under these rules. It should equal
                        the server's `entry_device_type`; when it does not, the
                        browser is reporting a different User-Agent than the one
                        in the request header (an extension, a proxy, UA client
                        hints) — a third state, and now a separable one.
      `device_type`     the client's FINAL answer: `device_type_ua` refined by
                        signals the server cannot see (touch points, viewport).
      `device_type_signals`  which of those signals fired, so a disagreement
                        between the last two is attributable rather than
                        mysterious.

    So: `device_type` != server  →  read `ua_rules`, then compare
    `device_type_ua` with the server's type. Equal means the client's own
    signals moved it (genuine); different means the User-Agents differ; and
    'unavailable' means we learnt nothing this time.
    """
    return dict(
        order=[name for name, _ in DEVICE_UA_RULES],
        patterns={name: rx.pattern for name, rx in DEVICE_UA_RULES},
        max_len=MAX_USABLE_UA_LEN,
        illegal=_ILLEGAL_UA_CHARS_RE.pattern,
        unknown='unknown',
        undetermined=UNDETERMINED,
    )


def pvar(participant, name, default=None):
    """Safe read of a participant field.

    ALWAYS use this (or ``participant.vars.get()``) instead of
    ``getattr(participant, name, default)``. oTree's participant-vars descriptor
    raises ``KeyError`` — NOT ``AttributeError`` — for a field that has not been
    set yet, so a ``getattr`` default does not protect you and the page 500s.
    (Learnt from a live outage; see docs/conventions.md.)
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


def flag(player, name) -> bool:
    """Is a module flag on for this player's session?

    The ONE implementation of the `_flag` helper the apps alias. Deliberately a
    raw ``config.get``, NOT ``cfg``: the two differ for a key missing from a
    frozen session config. ``cfg`` falls back to the value SHIPPED in settings —
    right for thresholds and codes, which must keep working mid-study. A module
    FLAG missing from a session's config means the module post-dates that
    session, and a module a session was created without must read as OFF for it,
    whatever a later deploy ships as the default.
    """
    return bool(player.session.config.get(name))


# =============================================================================
# STUDY TYPE — **FLAGS DECIDE MECHANICS, `recruitment` DECIDES COPY**
# =============================================================================
# THE RULE, because this is the one that gets re-tangled by the next person
# adding a page:
#
#   A MODULE FLAG answers "do we have the machinery to do this?" —
#   `prolific_completion_redirects` means "we hold a completion code to send them back
#   with", `prolific_capture_participant_id` means "we collect a platform id", and either
#   may legitimately be off in a study that still runs on Prolific.
#
#   `recruitment` answers "WHERE IS THIS PARTICIPANT?" — in a room with an
#   experimenter, or alone on a recruitment platform. **Every sentence a
#   participant reads that names the platform, or the room, or tells them how to
#   reach a human, branches on THIS** — never on a module flag standing in for
#   it.
#
# WHAT WENT WRONG WITHOUT THE RULE (found 2026-08-13, and the reason these two
# functions exist). "Is this participant on Prolific?" was answered by whichever
# flag was nearest: the consent page's contact sentence used
# `prolific_capture_participant_id`, the screen-out page's way out used
# `prolific_completion_redirects`, and everything else used `recruitment`. A
# `recruitment='prolific'` session with `prolific_completion_redirects` OFF — the natural
# config for a friend test — therefore told a participant on the consent page to
# contact the researchers *through Prolific*, and then served a screen-out page
# with no way-out section at all: a DEAD END, with nothing on screen to say so,
# no error and no failing test. Pinned now by scripts/tests/copy_routing_test.py.
#
# Read through `cfg`, never a raw `.get`: `recruitment` is a study-type axis with
# a shipped default, NOT a module flag (see `flag` for why that distinction
# decides the accessor), so a session config frozen before the key existed must
# fall back to that default rather than silently answering "not lab".

def recruitment(config) -> str:
    """This session's study type ('lab' | 'prolific'), via the safe accessor."""
    return cfg(config, 'recruitment')


def is_lab(config) -> bool:
    """Is this an experimenter-run (lab) session?

    THE ONE implementation: the answer picks participant-facing copy in three
    apps and a page in a fourth, and must not be decided by two different config
    accessors. KEEP THE CALLER LIST SHORT — every lab/online divergence is a
    thing that can be true in one variant and quietly wrong in the other,
    forever, so a branch has to earn its place: it is for things that cannot be
    true in both rooms, not for things that merely read differently.
    """
    return recruitment(config) == 'lab'


def is_prolific(config) -> bool:
    """Is this participant on the recruitment platform (i.e. not in the lab)?

    THE PREDICATE FOR COPY THAT NAMES PROLIFIC — not `prolific_capture_participant_id`
    and not `prolific_completion_redirects`, which are mechanics (see the rule above).
    A study that runs on Prolific with the id capture or the completion
    redirects switched off is still a study on Prolific, and the participant
    still has no experimenter to raise a hand to.
    """
    return recruitment(config) == 'prolific'


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
    # Post-task violations: recorded, NEVER disqualifying — a separate column
    # from focus_loss_count so an analyst can tell a completed-with-violations
    # participant from a nearly-ejected one (the phase asymmetry note above
    # _apply_focus_loss).
    participant.focus_loss_count_outro = 0
    participant.focus_event_ids = []
    # Per-event detail behind the counters, and the at-least evidence that
    # earlier events never reached the server (see _record_focus_event and
    # _note_missed_events).
    participant.focus_events = []
    participant.focus_losses_missed_at_least = 0
    # Reader-facing tab-monitor columns (see derive_tab_monitor_flag). Set here
    # rather than left to the first violation, so a participant who never trips
    # the monitor still exports a meaningful pair — and so `tab_monitor_where`
    # can record that the module was OFF for this session, which the flag's
    # empty value cannot say on its own.
    monitored = bool(participant.session.config.get('tab_monitor'))
    refresh_tab_monitor_flag(participant, monitored=monitored)
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


# =============================================================================
# THE STAGE-STAMP VOCABULARY — one spelling per stamp, for writers AND readers.
# =============================================================================
# LEFT_BEFORE_APP_STAGE below existed first, "so the writer and the reader
# cannot drift apart on the spelling" — and an audit (whole-app review A2,
# 2026-08-13) found every OTHER cross-file stamp was literals on both sides,
# and even that one's named reader used the literal. Either the reasoning
# holds for the whole vocabulary or the constant is decoration; it holds. The
# apps write these and experimenter_dashboard.py reads them; a typo on either
# side is now an AttributeError at import instead of a silently wrong pill.
#
# THE VALUES ARE FROZEN — they are keys inside live exports' stage_timestamps
# JSON, so the CODEBOOK never-rename rule applies to the strings, not just the
# columns. Rename the Python names freely; never the values.
STAGE_CONSENT = 'consent'
STAGE_CONFIRM_ID = 'confirm_id'
STAGE_AI_SAFETY_AGREED = 'ai_safety_agreed'
STAGE_SCREENED_OUT = 'screened_out'
STAGE_SCREENOUT_CLEARED = 'screenout_cleared'
STAGE_INSTRUCTIONS_DONE = 'instructions_done'
STAGE_INSTRUCTIONS_REREAD_DONE = 'instructions_reread_done'
STAGE_QUIZ_DONE = 'quiz_done'
STAGE_REREAD_TAKEN = 'reread_taken'
STAGE_TASK_DONE = 'task_done'
STAGE_FINISHED = 'finished'
STAGE_PROLIFIC_RETURN_CLICKED = 'prolific_return_clicked'

# THE NAME OF THE "LEFT THE ENTRY BLOCK" STAMP, defined once so the writer
# (before/__init__.py) and the reader (experimenter_dashboard._intro_seconds)
# cannot drift apart on the spelling.
LEFT_BEFORE_APP_STAGE = 'left_before_app'


def stamp_left_before_app(participant):
    """Record that the participant has just left a page of the `before` app.

    CALLED FROM EVERY `before` PAGE'S ``before_next_page``, and DELIBERATELY
    OVERWRITES — the last call to fire is the one that matters, and that is
    exactly the moment the participant left the entry block for `intro`.

    Why it is written this way rather than stamped once on "the last page":
    WHICH page is last is CONFIG-DEPENDENT. The lab ends the block at consent;
    Prolific adds the ID confirmation and the AI-safety agreement; a study that
    adds an entry page moves it again. Anything that names one page as the end
    is wrong for some configuration, silently, and the error shows up as a
    dwell time billed to the wrong phase — which has already happened once here
    (see the note on AISafetyAgree.before_next_page). Overwriting on every page
    is correct for every configuration including ones not written yet, and a new
    entry page only has to call this to stay measured.

    It is the START of the dashboard's INTRO TIME (Julian, 2026-08-13).
    """
    stamp_stage(participant, LEFT_BEFORE_APP_STAGE)


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
        # DEVICE_UA_RULES is the one ordered list, and it is the same one the
        # browser is given (device_ua_rules) — not a copy of it.
        for device_type, pattern in DEVICE_UA_RULES:
            if pattern.search(ua):
                return device_type
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
    """True while an entry screen-out gate is holding this participant.

    (Corrected 2026-08-13: this used to say a screened-out participant is
    "walked straight past consent … to the outro ending", which is the
    behaviour the SOFT WALL replaced. They are not walked anywhere.)

    The entry device gate HOLDS such a participant on `before.welcome`, which
    serves `before/screened_out.html` on that same page index, so under this
    template they never advance at all — that is what keeps the verdict
    re-decidable. The flag is read by that page to pick its template, by the
    later `before` pages to skip themselves (`before._leaving_study`), and by
    `intro` and `outro` as the belt to that brace, for any future gate that sets
    it later in the flow. Reads participant vars with .vars.get() — never
    getattr().
    """
    return bool(participant.vars.get('screened_out'))


def removed_from_study(participant) -> bool:
    """The DOWNSTREAM belt: is there any recorded reason this participant is
    out of the study?

    ONE membership list for every removal mechanism the template has —
    the entry screen-out, both integrity disqualifications, and a declined
    consent — so a removal mechanism added tomorrow is joined in ONE place
    instead of three differently-shaped predicates (whole-app review A1,
    2026-08-13; before that, intro belted one flag, main two, outro all four).
    `intro.intro_page_visible` and `main.task_page_visible` gate on this;
    `outro.ending_reason` reads the SAME records but stays its own cascade,
    because the ending needs the reason and its priority order for copy, not
    a boolean — extend BOTH when adding a mechanism.

    Reads only durable records, so it answers the same on any request. The one
    deliberate non-caller: `before._leaving_study`, which must answer from the
    consent FORM on the page's own request, before any record exists (the
    two-currencies note at `before._declined_consent`).

    Some of what this belts is unreachable today (routing walks a non-consenter
    and a comprehension DQ straight to the outro) — kept anyway, for the same
    reason `outro.was_screened_out` is kept: the future gate that sets a flag
    later in the flow.
    """
    v = participant.vars
    return bool(
        is_screened_out(participant)
        or v.get('ai_safety_disqualified')
        or v.get('comprehension_disqualified')
        or v.get('exit_code') == EXIT_CODES['no_consent']
    )


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


def prolific_screenout_return_url(config) -> str:
    """The way OUT for a screened-out participant: a Prolific COMPLETION URL
    carrying `prolific_device_code`, the screen-out population's own code.

    STOP BEFORE YOU "FIX" THIS TO MATCH AN OLDER COMMENT. Until 2026-08-15 this
    function's docstring said the exact opposite of these four lines — that
    there is deliberately NO screened-out completion code and the link carries
    nothing — while the body already built the coded URL. Anybody reading the
    two together would reasonably have made the code match the prose, and that
    would have silently reverted a deliberate decision. The prose was the stale
    half; this is the reasoning it should have carried.

    WHY THE CODELESS EXIT WAS REVERSED (DECISIONS.md, "Every ending population
    gets its own completion code", 2026-08-15, which SUPERSEDES the 2026-08-12
    codeless-screen-out entry). The old argument was right that a completion
    code CLOSES a Prolific submission and that a returned submission can never
    be retaken. It was wrong that leaving the submission open was therefore the
    kind option: a bare researcher URL leaves it in LIMBO — occupying a place in
    the study, telling Prolific nothing, until it times out. A REQUEST_RETURN
    code is a different instrument: it prompts the participant to return the
    submission, which frees the place and ends the ambiguity. Hence a code, and
    hence this population's OWN code — one code shared with the DQ populations
    would collapse them irreversibly on a system we do not own.

    KNOWN AND DELIBERATE, NOT AN OVERSIGHT: for a participant who takes this
    exit, returning the submission does foreclose the "come back on an accepted
    device and finish" route the screen-out page invites. The page still leads
    with switching device, and this exit is deliberately the QUIET control
    (`.exit-button`, never `.next-button`, so Enter cannot trigger it). Whether
    the copy should say so is an open COPY question with Julian (raised
    2026-08-15) — it is not a defect to fix here, and the mechanics below are
    not what is in question.

    THE CODE IS THE ONLY SOURCE. There is no `prolific_screenout_return_url`
    SETTING any more: a URL that embeds a code, plus the code key itself, is one
    value in two places and they drift. The template variable of that name is
    built HERE, from the code.

    Read through `cfg` so a session created before the parameter existed falls
    back to the shipped default instead of 500-ing on the one page a stranded
    participant needs. Returns '' if a study blanks the code, and the template
    then renders no link at all rather than a broken one. Escaping happens at
    the point of use, in the template.
    """
    try:
        code = str(cfg(config, 'prolific_device_code') or '').strip()
    except Exception:
        return ''
    if not code:
        return ''
    return 'https://app.prolific.com/submissions/complete?cc=' + code


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


def screenout_vars(participant, config) -> dict:
    """The facts every screen-out screen needs, built ONCE.

    Two pages describe the same screened-out participant: the entry hold page
    (`before/screened_out.html`, where the wall is soft and reversible) and the
    outro ending (`outro/Ended.html`, the unreachable-by-design fallback for a
    future gate that screens somebody out later in the flow). The two say
    deliberately different things — "your place is still open" vs "this has
    ended" — but they must not describe the same participant's DEVICE
    differently, so what happened, what the study accepts and the codeless way
    out are derived here rather than assembled twice.

      screenout_cause        the DETECTED type ('phone'/'tablet'/'computer'/
                             'unknown'), or '' — the templates pick their
                             sentence from it, never from the exit code, which
                             is the general -4 bucket.
      detected_device_label  that type as participant-facing words ('a phone',
                             'a tablet', 'a desktop or laptop computer'), from
                             DEVICE_TYPE_LABELS — the ONE cause→noun mapping, so
                             the two pages cannot word the same device
                             differently. DELIBERATELY EMPTY for 'unknown' (we
                             must not tell a participant what they are using
                             when we do not know — their sentence says what is
                             needed instead) and for ''/any future cause (the
                             neutral fallback owns those). A template branches
                             on this being non-empty for the one physical-device
                             sentence, and keeps its own branches for the rest.
      allowed_devices_phrase what the study DOES accept, built from the same
                             list the gate enforces so copy cannot drift from
                             the rule.
      prolific_screenout_return_url   the way out, carrying NO completion code (see
                             `prolific_screenout_return_url` for why there is none).
    """
    cause = screenout_cause(participant)
    return dict(
        screenout_cause=cause,
        detected_device_label=(DEVICE_TYPE_LABELS[cause]
                               if cause in ('phone', 'tablet', 'computer') else ''),
        allowed_devices_phrase=device_types_phrase(allowed_devices(config)),
        prolific_screenout_return_url=prolific_screenout_return_url(config),
    )


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


# =============================================================================
# THE TAB MONITOR — server half. ONE counting core, TWO consequences by phase.
# =============================================================================
# SAME MONITOR, SAME COUNTING, DIFFERENT CONSEQUENCE BY PHASE (Julian,
# 2026-08-13). Violations EJECT during the instructions, the quiz and the task
# (`focus_live_method`), and are RECORDED BUT NEVER EJECT during the outro
# (`focus_live_method_outro`). This looks like an inconsistency to anyone who
# does not know why, so here is why: by the outro THE TASK IS OVER AND THE DATA
# IS ALREADY COLLECTED — disqualifying somebody who has completed the whole
# study (say, for tabbing away while typing bank details, or to fetch their
# Prolific tab) would cost a real participant for no benefit. A violation
# during the pages the agreement warns about is exactly what the module exists
# to stop; a violation after them is only worth knowing about.
#
# THE TWO PHASES ARE TWO COLUMNS, so an analyst can tell a completed-with-
# violations participant from a nearly-ejected one:
#
#   focus_loss_count        violations while ejection applied (intro + main).
#                           Crossing tab_monitor_max_violations HERE
#                           disqualifies (exit code -3).
#   focus_loss_count_outro  violations after the task (outro pages). NEVER
#                           disqualifies, whatever the count — a nonzero value
#                           on a finished participant does NOT mean they came
#                           close to ejection. See CODEBOOK.md.
#
# Event dedup (focus_event_ids) is deliberately SHARED across both phases, so
# a replayed event id cannot be counted once per phase.
#
# The page wiring that binds these — monitored BY DEFAULT for every page after
# the agreement screen — lives in participant_tab_monitor.py (MonitoredPage /
# OutroMonitoredPage); the client half is _static/global/js/ai_safety_monitor.js.

# --------------------------------------------------------------------------
# THE READER-FACING TAB-MONITOR FLAG
#
# The raw columns answer "what did the software count?". They do not answer the
# question a person actually has — **does this participant's ATTENTION need a
# human decision, and what should I do about it?** — because answering that from
# the raw columns requires knowing which phase ejects, which does not, and what
# `tab_monitor_max_violations` was set to for THAT session. A reader who has
# never opened CODEBOOK.md cannot get there, and a reader who half-remembers it
# gets there wrongly: a nonzero `focus_loss_count_outro` on a finished
# participant looks alarming and means "keep and pay them".
#
# So one column says what to DO, in an ordered vocabulary, most severe winning:
#
#   ''             clean — nothing observed (see the `where` companion for
#                  whether the monitor was even on).
#   'observed'     a record-only focus loss AFTER the task. KEEP AND PAY —
#                  the data is valid; treat those questionnaire answers with
#                  suspicion.
#   'warned'       violations on an enforcing page, under the threshold. The
#                  TASK DATA IS VALID; attention is a covariate, not a reason
#                  to exclude.
#   'disqualified' the threshold was crossed. EXCLUDE from analysis — the row
#                  is flagged, not deleted.
#
# It REPLACES NOTHING. `focus_loss_count`, `focus_loss_count_outro` and
# `ai_safety_disqualified` remain exactly as they were and are what this is
# derived from; the flag is a reading of them, not a substitute.
#
# DERIVED IN ONE PLACE (`derive_tab_monitor_flag`) and written from the ONE
# counting core below, which is the only code in this template that changes any
# of the three inputs. A flag computed at each write site would drift the first
# time somebody added a fourth site.
# --------------------------------------------------------------------------

# Ordered least-to-most severe. The order IS the semantics — `max()` over this
# tuple is what "most severe wins" means, so do not reorder it for tidiness.
TAB_MONITOR_FLAG_ORDER = ('', 'observed', 'warned', 'disqualified')


def derive_tab_monitor_flag(pvars) -> str:
    """The single derivation. `pvars` is a participant.vars-like mapping.

    Pure and read-only so it can be applied to a live participant, an exported
    row, or a test fixture without special-casing any of them.
    """
    if pvars.get('ai_safety_disqualified'):
        return 'disqualified'
    if int(pvars.get('focus_loss_count') or 0) > 0:
        # Under the threshold: crossing it sets ai_safety_disqualified above, so
        # reaching here means enforcing-phase violations that did NOT eject.
        return 'warned'
    if int(pvars.get('focus_loss_count_outro') or 0) > 0:
        return 'observed'
    return ''


def derive_tab_monitor_where(pvars, monitored=True) -> str:
    """WHERE the observations happened — the companion the flag is useless
    without.

    'observed' means "treat those answers with suspicion", which is not
    actionable until the reader knows WHICH answers. This says which region of
    the study the observations came from.

    IT NAMES THE PAGES when they are known: `questionnaire: Demographics,
    Feedback`. That is the point of recording `focus_events` — 'questionnaire'
    alone spans Results, Demographics, Feedback and Ended, so it could not tell
    a reader whether to distrust the demographics answers or the feedback typed
    on the page after them.

    THE REGION WORD STAYS THE PREFIX, deliberately. Values were region-only
    before `focus_events` existed, and a participant recorded then still has no
    page list — so `startswith('questionnaire')` keeps working across the
    change, and an old row degrades to the old value instead of becoming
    unreadable.

    `monitored=False` (the session's tab_monitor flag is off) is reported here
    rather than in the flag itself: the flag's empty value would otherwise mean
    both "watched and clean" and "never watched", which are different facts
    about a participant — every lab session is the latter.
    """
    if not monitored:
        return 'not-monitored'
    task = int(pvars.get('focus_loss_count') or 0) > 0
    outro = int(pvars.get('focus_loss_count_outro') or 0) > 0
    if task and outro:
        region = 'task+questionnaire'
    elif task:
        region = 'task'
    elif outro:
        region = 'questionnaire'
    else:
        return ''

    # Distinct page names, in the order they were first seen — reading order is
    # what a reader wants ("distracted on Demographics, then again on
    # Feedback"), not alphabetical. Silently absent for a participant recorded
    # before focus_events existed, which is why the region word stands alone.
    seen, pages = set(), []
    for event in (pvars.get('focus_events') or []):
        page = (event or {}).get('page')
        if page and page not in seen:
            seen.add(page)
            pages.append(page)
    if not pages:
        return region
    return f"{region}: {', '.join(pages)}"


def refresh_tab_monitor_flag(participant, monitored=True) -> None:
    """Recompute both reader-facing columns from the raw counters."""
    participant.tab_monitor_flag = derive_tab_monitor_flag(participant.vars)
    participant.tab_monitor_where = derive_tab_monitor_where(
        participant.vars, monitored=monitored)


def _record_focus_event(player, region):
    """Append the per-event detail behind the counters. Never raises.

    THE PAGE COMES FROM THE SERVER, NOT THE CLIENT. `ai_safety_monitor.js` sends
    `page: window.location.pathname` with every event and this deliberately
    ignores it: the client half of the monitor is the half a participant can
    edit, and a field an analyst trusts must not be attacker-controlled.
    `participant._current_page_name` is oTree's own record of where the
    participant is (otree/models/participant.py:77) and is authoritative.

    Wrapped defensively because instrumentation must never break a page — a
    focus event that cannot be described in detail must still be COUNTED, and
    the counters are written by the caller before this runs.
    """
    try:
        page = getattr(player.participant, '_current_page_name', None) or ''
        events = list(player.participant.vars.get('focus_events') or [])
        events.append(dict(page=page, region=region, ts=int(time.time())))
        player.participant.focus_events = events
    except Exception:
        pass


def _note_missed_events(player, data):
    """Retrospective drop detection: did events fail to reach us EARLIER?

    The client sends its own running total (`count`) with every event and the
    counting core has always ignored it. Comparing it to ours turns a silent
    client-side drop into something visible — the participant whose websocket
    was down for two events, then came back.

    TWO DISTINCTIONS THIS MUST NOT COLLAPSE (the rule this codebase keeps
    breaking; both were named before this was written):

    1. A client count LOWER than ours IS NOT A DROP. It is a cleared
       sessionStorage, a reused browser, a second tab, or a replay — the client
       counter restarts at 0 while ours does not. Recording that as a loss would
       invent missing data out of an ordinary browser event, so only a STRICTLY
       GREATER client count is evidence of anything.

    2. The gap is EVIDENCE OF A DROP, NOT A COUNT OF DROPPED EVENTS. Client 4
       against our 2 means AT LEAST two were lost — there may have been more
       that the client itself never counted. Hence the field name
       `focus_losses_missed_at_least`, and hence `max()` rather than `+=`:
       summing successive observations of the same gap would multiply one drop
       into many.
    """
    try:
        client_count = data.get('count')
        if not isinstance(client_count, int) or isinstance(client_count, bool):
            return                                   # unusable -> say nothing
        server_total = (int(player.participant.vars.get('focus_loss_count') or 0)
                        + int(player.participant.vars.get('focus_loss_count_outro') or 0))
        gap = client_count - server_total
        if gap <= 0:
            return                                   # distinction 1
        previous = int(player.participant.vars.get(
            'focus_losses_missed_at_least') or 0)
        player.participant.focus_losses_missed_at_least = max(previous, gap)
    except Exception:
        pass


def _apply_focus_loss(player, data, ejects):
    """The one counting core. `ejects` picks the phase's consequence."""
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
    if not ejects:
        # OUTRO: record in the outro's OWN column and stop. Deliberately not
        # the same counter — see the phase note above: the ejecting count must
        # stay readable as "how close to disqualification", and this must not
        # push it over a threshold that no longer applies.
        count = (player.participant.vars.get('focus_loss_count_outro') or 0) + 1
        player.participant.focus_loss_count_outro = count
        # Detail and drop-detection AFTER the counter, so a participant is
        # counted even if either of them cannot describe the event. Both use the
        # same region vocabulary as tab_monitor_where.
        _record_focus_event(player, 'questionnaire')
        _note_missed_events(player, data)
        # Reader-facing columns follow the counters they are derived from, from
        # inside the ONE place that changes them.
        refresh_tab_monitor_flag(player.participant)
        return
    count = (player.participant.vars.get('focus_loss_count') or 0) + 1
    player.participant.focus_loss_count = count
    _record_focus_event(player, 'task')
    _note_missed_events(player, data)
    max_violations = int(cfg(config, 'tab_monitor_max_violations'))
    if count >= max_violations:
        player.participant.ai_safety_disqualified = True
        set_exit_code(player.participant, EXIT_CODES['tab_monitor'])
        refresh_tab_monitor_flag(player.participant)
        return {player.id_in_group: dict(action='disqualified')}
    refresh_tab_monitor_flag(player.participant)


def focus_live_method(player, data):
    """Server-authoritative tab-switch handler for the EJECTING phases
    (intro + main — bound by participant_tab_monitor.MonitoredPage).

    Counts each real focus-loss once (deduped by client-supplied event_id) and
    disqualifies at the configured threshold, broadcasting {action:'disqualified'}
    to that player so the client reloads onto the ending. No-op unless the
    tab_monitor flag is on. See settings + _static/global/js/ai_safety_monitor.js.
    """
    return _apply_focus_loss(player, data, ejects=True)


def focus_live_method_outro(player, data):
    """The OUTRO's handler (bound by participant_tab_monitor.OutroMonitoredPage):
    the same counting, RECORDED ONLY — it never disqualifies, never touches the
    exit code, and never broadcasts (Julian, 2026-08-13; the full why is the phase
    note above). Violations land in `focus_loss_count_outro`, a separate
    column, so the export can tell post-task violations from the ones that
    counted toward ejection.
    """
    return _apply_focus_loss(player, data, ejects=False)


def _monitor_js_vars(player, ejects):
    """Client thresholds for ai_safety_monitor.js, or {} when the module is off.

    Empty-when-off matches the device-capture pattern (`welcome.js_vars`):
    config is sent only when the script that reads it is meant to run. The
    client REQUIRES this config and refuses to start without it — there is
    deliberately no defaults fallback in the JS any more, because a fallback
    is a second copy of settings.SESSION_CONFIG_DEFAULTS that drifts.

    `ejects` tells the client which phase it is in: in the record-only outro
    phase it counts and reports but shows NO overlay and NO warning modal —
    the modal's copy ("will end your participation") would be a lie there.
    """
    config = player.session.config
    if not config.get('tab_monitor'):
        return {}
    return dict(AI_SAFETY_CONFIG=dict(
        max_violations=int(cfg(config, 'tab_monitor_max_violations')),
        threshold_ms=int(cfg(config, 'tab_monitor_threshold_ms')),
        overlay_delay_ms=int(cfg(config, 'tab_monitor_overlay_delay_ms')),
        ejects=bool(ejects),
    ))


def monitor_js_vars(player):
    """js_vars for the EJECTING phases
    (bound by participant_tab_monitor.MonitoredPage)."""
    return _monitor_js_vars(player, ejects=True)


def monitor_js_vars_outro(player):
    """js_vars for the record-only OUTRO phase
    (bound by participant_tab_monitor.OutroMonitoredPage)."""
    return _monitor_js_vars(player, ejects=False)
