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

api() { curl -fsS "${AUTH_HEADER[@]}" "$@"; }

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
if ! rooms_json="$(api "${BASE_URL}/api/rooms")"; then
    echo "FATAL: cannot reach ${BASE_URL}/api/rooms (is the server up? is the rest key correct?)." >&2
    exit 1
fi
existing_code="$(printf '%s' "$rooms_json" | room_session_code)"
if [ -n "$existing_code" ]; then
    echo "Room '${ROOM_NAME}' already has session '${existing_code}' — reusing it (no new session created)."
    exit 0
fi

# 2) Nothing bound — create a session bound to the room.
echo "Room '${ROOM_NAME}' has no session; creating '${SESSION_CONFIG}' with ${NUM_PARTICIPANTS} participants..."
if ! create_json="$(api -X POST "${BASE_URL}/api/sessions" \
        -H 'Content-Type: application/json' \
        -d "{\"session_config_name\":\"${SESSION_CONFIG}\",\"num_participants\":${NUM_PARTICIPANTS},\"room_name\":\"${ROOM_NAME}\"}")"; then
    echo "FATAL: session creation request failed. Room left unbound." >&2
    exit 1
fi
new_code="$(printf '%s' "$create_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("code",""))' 2>/dev/null || true)"
if [ -z "$new_code" ]; then
    echo "FATAL: session creation returned no code. Response was:" >&2
    echo "$create_json" >&2
    exit 1
fi

# 3) Verify the room is now bound; fail loudly otherwise.
rooms_json2="$(api "${BASE_URL}/api/rooms")"
bound_code="$(printf '%s' "$rooms_json2" | room_session_code)"
if [ "$bound_code" != "$new_code" ]; then
    echo "FATAL: created session '${new_code}' but room '${ROOM_NAME}' is not bound to it (bound='${bound_code}')." >&2
    exit 1
fi

echo "Created session '${new_code}' and bound it to room '${ROOM_NAME}'."
echo "Room-wide URL: ${BASE_URL}/room/${ROOM_NAME}"
