#!/usr/bin/env bash
#
# PRE-DEPLOY UPGRADE CHECK.
#
#   scripts/predeploy_check.sh [<path-to-COPY-of-live-db.sqlite3>] [app-dir]
#
# WHICH CHECK IS THIS? There are two, and they do different jobs:
#   scripts/prelaunch_check.py  — STATIC config guard, no server, instant. Asks
#       "is this CONFIGURATION safe to launch?": REPLACE_* completion codes,
#       DEBUG still on, testing loosenings (verify_quiz=False) left in. Run it
#       in the target environment before opening a study to participants.
#   scripts/predeploy_check.sh  — THIS. DYNAMIC upgrade gate. Boots the
#       candidate build against a COPY of the live database and drives real
#       participants over real HTTP. Asks "will the RUNNING study survive being
#       upgraded to this code?". Run it before every deploy that lands on a
#       database with participants in it.
# Neither replaces the other: prelaunch cannot detect a broken upgrade path,
# and predeploy cannot tell you the completion codes are still placeholders.
#
# WHY: two live outages in the pilot study this template was distilled from
# shared one root cause — the new code was only ever tested against a FRESH
# database, but both failures could only occur for a participant whose state
# PREDATED the change (an unset participant-vars key; a session config frozen
# before a parameter existed). A fresh session cannot reproduce either. This
# script tests the UPGRADE, not the install: it boots the candidate build
# against a copy of the live database, audits every EXISTING session's frozen
# config against the current settings (failing on missing keys and REPLACE_*
# placeholders, reporting all other differences as information — a stale
# session cannot be repaired by editing settings, it has to be recreated), and
# drives, over real HTTP, (a) an EXISTING mid-flow participant several pages
# forward, (b) a FRESH participant entry -> end, (c) a no-JS participant whose
# JS-produced hidden fields all post EMPTY — then greps the server log for
# 5xx / tracebacks / KeyError / TypeError.
# Any failure exits non-zero, so this can gate a deploy.
#
# DEGRADED MODE (a template, or a study before its first session, has no live
# database): run with NO database argument and the fresh-install checks run
# alone, every upgrade-path check is reported NOT TESTED (never PASS), and the
# summary says THE UPGRADE PATH WAS NOT TESTED in a banner you cannot miss. Pass
# --require-db (or PREDEPLOY_REQUIRE_DB=1) to make a degraded run FAIL — that is
# what a deploy pipeline for a study with live sessions should do.
#
# GETTING THE DB COPY (never stops the container):
#   docker cp <container>:/app/data/db.sqlite3 /tmp/db_live_copy.sqlite3
# then run this script against /tmp/db_live_copy.sqlite3. The LIVE database is
# NEVER touched: the script refuses live-looking paths outright AND works on its
# own private temp copy of whatever file it is given, so even the given copy is
# never modified. A study built from this template should name its own live
# volume/host path in PREDEPLOY_LIVE_MARKERS (comma-separated substrings) so
# that refusal keeps working for it.
#
# HOW ISOLATION WORKS (an oTree 6 trap, verified against otree 6.0.15):
# for sqlite, oTree IGNORES the path in DATABASE_URL — otree/database.py opens
# the literal file ./db.sqlite3 of the process's CWD at import. So this script
# stages a pristine copy of the candidate build in a private temp dir, drops the
# DB copy in as its db.sqlite3, and runs the checks from there; the Python
# helper then verifies via PRAGMA database_list that the engine really is on
# that staged file and aborts otherwise. Neither the live volume, the given
# snapshot, nor the checkout's own db.sqlite3 is ever opened.
#
# [app-dir] defaults to the checkout containing this script; pass a different
# directory to test another build (e.g. an unpacked release candidate). That is
# also how you test a proposed change without touching your working tree.
#
# OPTIONS
#   --require-db      a degraded run (no DB copy) FAILS instead of passing
#   --debug           drive the app with DEBUG on; the default is the PRODUCTION
#                     shape, since production is what is being deployed and
#                     debug loosenings (verify_quiz=False) would mask a broken
#                     gate
#   --configs a,b     session configs to drive fresh participants through
#                     (default: one per recruitment profile, so the lab flow and
#                     the prolific flow are both exercised)
#   --keep            keep the temp workdir even on success
#
# INTERPRETER: runs with the first python that can import otree — the
# candidate/repo .venv if one exists (local dev), else python3/python on PATH
# (a deployment image installs oTree system-wide, no venv). Set
# PREDEPLOY_PYTHON=/path/to/python to force a specific interpreter.
#
set -euo pipefail

die() { echo "predeploy_check: FATAL: $*" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_APP_DIR="$(dirname "$SCRIPT_DIR")"

REQUIRE_DB=""
DEBUG_FLAG=""
CONFIGS=""
KEEP=""
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --require-db) REQUIRE_DB="--require-db"; shift ;;
        --debug)      DEBUG_FLAG="--debug"; shift ;;
        --keep)       KEEP=1; shift ;;
        --configs)    CONFIGS="${2:-}"; [[ -n "$CONFIGS" ]] || die "--configs needs a value"; shift 2 ;;
        --configs=*)  CONFIGS="${1#*=}"; shift ;;
        -h|--help)    sed -n '2,80p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*)           die "unknown option: $1" ;;
        *)            POSITIONAL+=("$1"); shift ;;
    esac
done

# Positional arguments. With one argument, a DIRECTORY is the app dir (degraded
# run of that build) and a FILE is the database copy — so neither form of the
# one-argument call can be misread.
DB_ARG=""
APP_ARG=""
case "${#POSITIONAL[@]}" in
    0) ;;
    1) if [[ -d "${POSITIONAL[0]}" ]]; then APP_ARG="${POSITIONAL[0]}"; else DB_ARG="${POSITIONAL[0]}"; fi ;;
    2) DB_ARG="${POSITIONAL[0]}"; APP_ARG="${POSITIONAL[1]}" ;;
    *) die "usage: $0 [<path-to-COPY-of-live-db.sqlite3>] [app-dir]" ;;
esac

APP_DIR="$(cd "${APP_ARG:-$REPO_APP_DIR}" && pwd)" || die "app dir not found: ${APP_ARG:-}"
[[ -f "$APP_DIR/settings.py" ]] || die "$APP_DIR does not look like an oTree app (no settings.py)"

DEGRADED=""
DB_REAL=""
if [[ -z "$DB_ARG" ]]; then
    DEGRADED="--degraded"
else
    [[ -f "$DB_ARG" ]] || die "database file not found: $DB_ARG"
    DB_REAL="$(realpath "$DB_ARG")"
fi

# ---------------------------------------------------------------------------
# REFUSE anything that looks like the LIVE database. This check must only ever
# run against a copy. (PREDEPLOY_LIVE_MARKERS adds a study's own markers, e.g.
# the name of its docker volume.)
# ---------------------------------------------------------------------------
if [[ -n "$DB_REAL" ]]; then
    case "$DB_REAL" in
        /var/lib/docker/*) die "path is inside /var/lib/docker (a live container volume) — copy it out first: $DB_REAL" ;;
        *docker/volumes*)  die "path is inside a docker volumes tree — copy it out first: $DB_REAL" ;;
        /app/*)            die "path is under /app (the live container tree) — copy it out first: $DB_REAL" ;;
    esac
    IFS=',' read -r -a _markers <<< "${PREDEPLOY_LIVE_MARKERS:-}"
    for marker in "${_markers[@]:-}"; do
        [[ -n "$marker" ]] || continue
        case "$DB_REAL" in
            *"$marker"*) die "path mentions the live marker '$marker' (PREDEPLOY_LIVE_MARKERS) — point at a COPY: $DB_REAL" ;;
        esac
    done
    for live in "$APP_DIR/db.sqlite3" "$APP_DIR/data/db.sqlite3" \
                "$REPO_APP_DIR/db.sqlite3" "$REPO_APP_DIR/data/db.sqlite3"; do
        if [[ -e "$live" && "$(realpath "$live")" == "$DB_REAL" ]]; then
            die "path IS the app tree's own database ($live) — run against a copy"
        fi
    done
    head -c 16 "$DB_ARG" | grep -aq 'SQLite format 3' \
        || die "not a sqlite database (bad magic header): $DB_ARG"
    if [[ -e "$DB_ARG-wal" || -e "$DB_ARG-shm" ]]; then
        echo "predeploy_check: WARNING: $DB_ARG has -wal/-shm sidecars — it may have" >&2
        echo "predeploy_check: been copied while the server was writing; results can be stale." >&2
    fi
fi

# ---------------------------------------------------------------------------
# python: any interpreter that can import otree. $PREDEPLOY_PYTHON wins if set;
# otherwise prefer the candidate/repo venvs (local dev), then fall back to
# python3/python on PATH (a Docker image installs oTree system-wide, with no
# venv anywhere).
# ---------------------------------------------------------------------------
has_otree() { "$1" -c 'import otree' >/dev/null 2>&1; }

PY=""
if [[ -n "${PREDEPLOY_PYTHON:-}" ]]; then
    [[ -x "$PREDEPLOY_PYTHON" ]] || die "PREDEPLOY_PYTHON is set but not executable: $PREDEPLOY_PYTHON"
    has_otree "$PREDEPLOY_PYTHON" || die "PREDEPLOY_PYTHON cannot import otree: $PREDEPLOY_PYTHON"
    PY="$PREDEPLOY_PYTHON"
else
    tried=()
    for cand in "$APP_DIR/.venv/bin/python" "$REPO_APP_DIR/.venv/bin/python" python3 python; do
        if [[ "$cand" == */* ]]; then
            resolved="$cand"
            [[ -x "$resolved" ]] || { tried+=("$resolved (not found)"); continue; }
        else
            resolved="$(command -v "$cand" 2>/dev/null)" || { tried+=("$cand (not on PATH)"); continue; }
        fi
        if has_otree "$resolved"; then PY="$resolved"; break; fi
        tried+=("$resolved (cannot import otree)")
    done
    [[ -n "$PY" ]] || die "no python with otree importable; tried: ${tried[*]} — set PREDEPLOY_PYTHON to an interpreter that has otree installed"
fi

# ---------------------------------------------------------------------------
# stage a pristine copy of the build with the DB copy as its db.sqlite3
# (mirrors the container layout; nothing outside the temp dir is written)
# ---------------------------------------------------------------------------
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/predeploy_check.XXXXXX")"
mkdir -p "$WORKDIR/app"
tar -C "$APP_DIR" \
    --exclude='.venv' --exclude='db.sqlite3' --exclude='db.sqlite3-wal' \
    --exclude='db.sqlite3-shm' --exclude='data' --exclude='_ai' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' \
    --exclude='.DS_Store' \
    -cf - . | tar -C "$WORKDIR/app" -xf -

if [[ -n "$DEGRADED" ]]; then
    # No live data to upgrade: build a fresh database inside the staged copy so
    # the fresh-install checks have something to run against. The helper then
    # reports every upgrade-path check NOT TESTED.
    echo "predeploy_check: no database copy given — DEGRADED run (fresh database)."
    ( cd "$WORKDIR/app" && PATH="$(dirname "$PY"):$PATH" OTREE_PRODUCTION=1 \
        "$PY" -c "import sys; sys.argv=['otree','resetdb','--noinput']; from otree.main import execute_from_command_line; execute_from_command_line()" ) \
        >"$WORKDIR/resetdb.log" 2>&1 \
        || { echo "predeploy_check: FATAL: could not create a fresh database; see $WORKDIR/resetdb.log" >&2; exit 2; }
else
    cp "$DB_ARG" "$WORKDIR/app/db.sqlite3"
fi
chmod u+w "$WORKDIR/app/db.sqlite3"

# Informational only for sqlite (oTree ignores the path — see header); the
# helper independently verifies the engine's actual file.
export DATABASE_URL="sqlite:///$WORKDIR/app/db.sqlite3"
unset OTREE_AUTH_LEVEL OTREE_REST_KEY OTREE_IN_MEMORY 2>/dev/null || true

echo "predeploy_check: python          : $PY"
echo "predeploy_check: candidate build : $APP_DIR"
echo "predeploy_check: database source : ${DB_REAL:-(none — DEGRADED, fresh database)}"
echo "predeploy_check: staged app+DB   : $WORKDIR/app"
echo "predeploy_check: server log      : $WORKDIR/server.log"
echo

rc=0
"$PY" "$SCRIPT_DIR/predeploy_check.py" \
    --app-dir "$WORKDIR/app" --src-app-dir "$APP_DIR" \
    --log "$WORKDIR/server.log" \
    ${DEGRADED} ${REQUIRE_DB} ${DEBUG_FLAG} \
    ${CONFIGS:+--configs "$CONFIGS"} || rc=$?

if [[ $rc -eq 0 && -z "$KEEP" ]]; then
    rm -rf "$WORKDIR"
else
    echo
    if [[ $rc -eq 0 ]]; then
        echo "predeploy_check: PASSED — workdir kept (--keep): $WORKDIR"
    else
        echo "predeploy_check: FAILED (exit $rc) — workdir kept for inspection: $WORKDIR"
    fi
fi
exit $rc
