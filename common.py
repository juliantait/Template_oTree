"""Shared, oTree-free helpers used across every app.

Import as ``import common``. Keeping these here (not inside any one app) means
every app reads participant state and records outcomes the same way.

This file MUST stay at the project root. All four apps do a top-level
``import common``, and oTree puts the project root on ``sys.path``; moving it into
a subfolder (e.g. scripts/) would break that import for every app.
"""
import time

from settings import EXIT_CODES  # re-exported for convenience


def pvar(participant, name, default=None):
    """Safe read of a participant field.

    ALWAYS use this (or ``participant.vars.get()``) instead of
    ``getattr(participant, name, default)``. oTree's participant-vars descriptor
    raises ``KeyError`` — NOT ``AttributeError`` — for a field that has not been
    set yet, so a ``getattr`` default does not protect you and the page 500s.
    (Learnt from a live outage; see conventions.md.)
    """
    return participant.vars.get(name, default)


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
    participant.device_info = {}


def stamp_stage(participant, stage):
    """Record epoch seconds for a named flow stage in ``participant.stage_timestamps``."""
    stamps = participant.vars.get('stage_timestamps') or {}
    stamps[stage] = time.time()
    participant.stage_timestamps = stamps


def set_exit_code(participant, code):
    """Record the numeric outcome for this participant (see settings.EXIT_CODES)."""
    participant.exit_code = code


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
    cfg = player.session.config
    if not cfg.get('tab_monitor'):
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
    max_violations = int(cfg.get('tab_monitor_max_violations', 2))
    if count >= max_violations:
        player.participant.ai_safety_disqualified = True
        set_exit_code(player.participant, EXIT_CODES['tab_monitor'])
        return {player.id_in_group: dict(action='disqualified')}
