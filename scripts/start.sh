#!/usr/bin/env bash
#
# Bind a session to the lab room — REUSING an already-bound session if one
# exists. Run this once when the lab server boots (or from a launcher shortcut).
#
# Why reuse: if you create a NEW session on every boot, any participant who is
# mid-experiment is stranded — the room now points at a different session and
# their links break. So this script only creates a session when the room has
# none bound, and otherwise leaves the running one alone.
#
# It fails LOUDLY (non-zero exit, clear message) rather than leaving the room
# unbound, so a launcher can surface the problem instead of silently starting
# an experiment nobody can join.
#
# Configuration (env vars, with lab defaults):
#   OTREE_BASE_URL         base URL of the running server (default http://localhost:8000)
#   OTREE_ROOM             room name in settings.ROOMS (default: study)
#   OTREE_SESSION_CONFIG   session config to create (default: lab)
#   OTREE_NUM_PARTICIPANTS room size to create (default: 30)
#   OTREE_AUTH_LEVEL       if 'STUDY', REST calls are authenticated (see below)
#   OTREE_REST_KEY         REST key; REQUIRED when OTREE_AUTH_LEVEL=STUDY
#   OTREE_START_READ_TIMEOUT    seconds for a room READ      (default 20)
#   OTREE_START_CREATE_TIMEOUT  seconds for session CREATION (default 600)
#
set -euo pipefail

BASE_URL="${OTREE_BASE_URL:-http://localhost:8000}"
export ROOM_NAME="${OTREE_ROOM:-study}"
SESSION_CONFIG="${OTREE_SESSION_CONFIG:-lab}"
NUM_PARTICIPANTS="${OTREE_NUM_PARTICIPANTS:-30}"

# When AUTH_LEVEL=STUDY the REST endpoints require the rest key header. Refuse to
# run without it, rather than firing unauthenticated calls that fail and leave
# the room unbound.
AUTH_HEADER=()
if [ "${OTREE_AUTH_LEVEL:-}" = "STUDY" ]; then
    if [ -z "${OTREE_REST_KEY:-}" ]; then
        echo "FATAL: OTREE_AUTH_LEVEL=STUDY but OTREE_REST_KEY is unset." >&2
        echo "       REST calls would be rejected and the room left unbound. Refusing to continue." >&2
        exit 1
    fi
    AUTH_HEADER=(-H "otree-rest-key: ${OTREE_REST_KEY}")
fi

# TWO CLASSES OF CALL, AND NEITHER MAY INHERIT THE OTHER'S TIMEOUT.
#
# There is no default here on purpose: `api` takes the timeout as its FIRST
# ARGUMENT and every call site has to state which class it is. A shared default
# is precisely how this goes wrong — in the study this template came from, a
# boot script ran its 220-seat session creation through the same 15-second
# timeout as its millisecond health checks, treated a slow SUCCESS as a failure,
# and took the container down. A structural fix (no default to inherit) is worth
# more than a bigger number, because the next call somebody adds gets asked the
# question too.
#
# The two classes, and why the numbers are what they are:
#   READ   — /api/rooms, a small JSON read. If it has not answered in 20s the
#            server is not answering, and waiting longer tells you nothing.
#   CREATE — POST /api/sessions. oTree builds every participant x round row
#            inside this request, so a large session legitimately runs for
#            minutes. GENEROUS ON PURPOSE: a tight value here buys nothing at
#            all when creation is quick, and buys an outage when it is not.
# Both are overridable so a test can drive the slow path in seconds; neither is
# set in production.
READ_MAX_TIME="${OTREE_START_READ_TIMEOUT:-20}"
CREATE_MAX_TIME="${OTREE_START_CREATE_TIMEOUT:-600}"

# --connect-timeout is separate and short for BOTH classes: a host that will not
# accept a TCP connection is not going to accept one in ten minutes either, and
# it is the one failure that should be reported at once.
api() {
    local max_time="$1"; shift
    curl -fsS --connect-timeout 10 --max-time "$max_time" "${AUTH_HEADER[@]}" "$@"
}

# Extract the session_code bound to $ROOM_NAME from /api/rooms JSON on stdin.
room_session_code() {
    python3 -c '
import sys, json, os
room = os.environ["ROOM_NAME"]
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit("")
for r in data:
    if r.get("name") == room:
        print(r.get("session_code") or "")
        break
'
}

echo "== start.sh: ensuring room '${ROOM_NAME}' has a session at ${BASE_URL} =="

# 1) Already bound? Reuse.
if ! rooms_json="$(api "$READ_MAX_TIME" "${BASE_URL}/api/rooms")"; then
    echo "FATAL: cannot reach ${BASE_URL}/api/rooms (is the server up? is the rest key correct?)." >&2
    exit 1
fi
existing_code="$(printf '%s' "$rooms_json" | room_session_code)"
if [ -n "$existing_code" ]; then
    echo "Room '${ROOM_NAME}' already has session '${existing_code}' — reusing it (no new session created)."
    exit 0
fi

# 2) Nothing bound — create a session bound to the room.
echo "Room '${ROOM_NAME}' has no session; creating '${SESSION_CONFIG}' with ${NUM_PARTICIPANTS} participants (up to ${CREATE_MAX_TIME}s)..."
create_rc=0
create_json="$(api "$CREATE_MAX_TIME" -X POST "${BASE_URL}/api/sessions" \
        -H 'Content-Type: application/json' \
        -d "{\"session_config_name\":\"${SESSION_CONFIG}\",\"num_participants\":${NUM_PARTICIPANTS},\"room_name\":\"${ROOM_NAME}\"}")" || create_rc=$?

new_code=""
if [ "$create_rc" -eq 0 ]; then
    new_code="$(printf '%s' "$create_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("code",""))' 2>/dev/null || true)"
fi

# A CLIENT-SIDE FAILURE IS NOT PROOF THE SERVER DID NOTHING, and the difference
# is the whole reason this branch exists. curl exiting 28 means WE stopped
# listening, not that the POST was refused: the same crash in exp_pilots left an
# ORPHAN SESSION behind, created by a request that completed after its client
# had gone. So re-read the room before calling anything fatal. A retry that does
# not re-check binds a SECOND session over a good one — and the participants
# already holding links to the first are stranded, which is the exact outcome
# this script's reuse rule exists to prevent.
#
# The same re-read covers a reply that arrived and did not parse: "no code came
# back" is a fact about the response, never about the room.
#
# THIS IS ONE RE-READ, NOT A WAIT, and the difference was measured rather than
# assumed: oTree binds the room only as the POST returns (creation is a single
# transaction), so a creation still genuinely in flight reads as unbound and is
# reported as the failure it currently is. Re-running this script is the
# recovery, and step 1 makes that safe.
if [ -z "$new_code" ]; then
    if [ "$create_rc" -ne 0 ]; then
        echo "WARNING: the session-creation request did not return cleanly (curl exit ${create_rc}$([ "$create_rc" -eq 28 ] && echo ' — CLIENT TIMEOUT after '"${CREATE_MAX_TIME}"'s, which says nothing about what the server did'))." >&2
    else
        echo "WARNING: session creation returned no session code. Response was:" >&2
        echo "$create_json" >&2
    fi
    echo "         Re-reading the room before deciding — the POST may have completed anyway." >&2
    late_rooms_json="$(api "$READ_MAX_TIME" "${BASE_URL}/api/rooms" || true)"
    late_code="$(printf '%s' "$late_rooms_json" | room_session_code || true)"
    if [ -n "$late_code" ]; then
        echo "Room '${ROOM_NAME}' IS bound to session '${late_code}' — the creation completed server-side after the client stopped listening. Keeping it; NO second session was created."
        echo "Room-wide URL: ${BASE_URL}/room/${ROOM_NAME}"
        exit 0
    fi
    echo "FATAL: session creation failed and room '${ROOM_NAME}' is still unbound." >&2
    echo "       This is ONE re-read, not a wait: a creation still in flight is reported" >&2
    echo "       here as unbound. RE-RUNNING THIS SCRIPT IS SAFE and is the recovery —" >&2
    echo "       step 1 reuses whatever is bound by then, so a re-run cannot double-bind." >&2
    exit 1
fi

# 3) Verify the room is now bound; fail loudly otherwise.
rooms_json2="$(api "$READ_MAX_TIME" "${BASE_URL}/api/rooms")"
bound_code="$(printf '%s' "$rooms_json2" | room_session_code)"
if [ "$bound_code" != "$new_code" ]; then
    echo "FATAL: created session '${new_code}' but room '${ROOM_NAME}' is not bound to it (bound='${bound_code}')." >&2
    exit 1
fi

echo "Created session '${new_code}' and bound it to room '${ROOM_NAME}'."
echo "Room-wide URL: ${BASE_URL}/room/${ROOM_NAME}"
