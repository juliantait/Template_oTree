#!/bin/zsh

# Preview_Instructions.command
# Double-clickable macOS wrapper around intro/generate_instructions_preview.py.
# Look at the instructions — as a coauthor would — WITHOUT opening a terminal,
# starting a server, or running a session.
#
# RECONSTRUCTED 2026-08-14. An earlier launcher of this name was deleted the
# same day on the reasoning that the previews flow superseded it. That was half
# right: the flow produces the same output, but only from a command line, and
# double-clicking from Finder is the whole point of this file. So it is back —
# pointed at the MAINTAINED generator this time.
#
# WHAT CHANGED, AND WHY THE OLD ONE HAD TO GO: it ran
# `previews/generate_instructions_preview.py`, a copy frozen on 2026-05-28
# inside the gitignored previews/ OUTPUT directory, eleven lines behind the real
# generator and writing to the same filenames — so clicking it silently replaced
# current previews with output from three-month-old code. `previews/` is where
# output LANDS; it is not where code lives. Never point this at anything in
# there.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GENERATOR="intro/generate_instructions_preview.py"

finish() {
    echo ""
    echo "  Press Enter to close..."
    read -r
    osascript -e 'tell application "Terminal" to close (every window whose name contains "Preview_Instructions")' &>/dev/null &
    exit "${1:-0}"
}

if [ ! -f "$GENERATOR" ]; then
    echo "✗ Cannot find $GENERATOR — is this file still in the project root?"
    finish 1
fi

# --- Pick a Python: project venv first, then system. ----------------------
PY=""
for c in venv .venv env .env; do
    if [ -x "$SCRIPT_DIR/$c/bin/python3" ]; then
        PY="$SCRIPT_DIR/$c/bin/python3"
        break
    fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
    PY=python3
fi
if [ -z "$PY" ]; then
    echo "✗ Python 3 not found. Install it from python.org."
    finish 1
fi

# --- Check the packages the generator needs. ------------------------------
# It checks these itself and prints install hints, but doing it here means the
# message arrives before any work starts.
MISSING=$("$PY" - <<'PY' 2>/dev/null
m = []
for pkg in ("jinja2", "playwright"):
    try:
        __import__(pkg)
    except ImportError:
        m.append(pkg)
print(" ".join(m))
PY
)
if [ -n "$MISSING" ]; then
    echo "✗ Missing Python packages: $MISSING"
    echo ""
    echo "  Install into a project-local venv (recommended):"
    echo "    cd \"$SCRIPT_DIR\""
    echo "    python3 -m venv venv && source venv/bin/activate"
    echo "    pip install jinja2 playwright"
    echo "    playwright install chromium"
    finish 1
fi

# --- Generate. -------------------------------------------------------------
# `--config .preview_state.json` when saved settings exist: WITHOUT it the
# generator opens a form (tkinter, or a browser tab) and waits for Generate to
# be clicked, which from a double-click looks like a window that hangs. With no
# saved state, the form is genuinely wanted — that is how the values get set the
# first time.
if [ -f ".preview_state.json" ]; then
    echo "  Using saved settings (.preview_state.json)."
    "$PY" "$GENERATOR" --config .preview_state.json
else
    echo "  No saved settings yet — a form will open; fill it in and click Generate."
    "$PY" "$GENERATOR"
fi
STATUS=$?

# EXIT CODE ALONE IS NOT THE ANSWER — measured on 2026-08-14: with the browser
# binary absent the generator writes BOTH HTML files correctly and still exits
# 1, because the PDF step failed. Treating that as a failed run would tell
# somebody their previews are broken while they are sitting there complete, and
# would skip opening them. So the outcome is decided by WHAT EXISTS, and the
# exit code is reported only when nothing was produced.
INTERACTIVE="previews/instructions_preview_interactive.html"
LONG="previews/instructions_preview_long.html"
PDF="previews/instructions_preview.pdf"

if [ ! -f "$INTERACTIVE" ] && [ ! -f "$LONG" ]; then
    echo ""
    echo "✗ Generator produced nothing (exit $STATUS). Output above says why."
    finish "$STATUS"
fi

echo ""
echo "✓ Wrote:"
for f in "$INTERACTIVE" "$LONG" "$PDF"; do
    [ -f "$f" ] && echo "    $f"
done
if [ ! -f "$PDF" ]; then
    echo ""
    echo "  (No PDF — that step alone needs the browser binary. Run once:"
    echo "     $PY -m playwright install chromium"
    echo "   The HTML files above are complete and self-contained.)"
fi

# Open the interactive one, since that is the one a coauthor clicks through.
if [ -f "previews/instructions_preview_interactive.html" ]; then
    open "previews/instructions_preview_interactive.html" &>/dev/null &
fi

finish 0
