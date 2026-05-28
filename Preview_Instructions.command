#!/bin/zsh

# Preview_Instructions.command
# Double-clickable macOS wrapper around generate_instructions_preview.py.
# Does NOT install anything — prints install hints and exits if a dep is missing.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Pick a Python: project venv first, then system. ---------------------
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
    echo ""
    echo "Press Enter to close..."
    read -r
    exit 1
fi

# --- Check Python packages. ----------------------------------------------
MISSING=$("$PY" - <<'PY' 2>/dev/null
m = []
try:
    import jinja2  # noqa: F401
except ImportError:
    m.append("jinja2")
try:
    import playwright  # noqa: F401
except ImportError:
    m.append("playwright")
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
    echo ""
    echo "Press Enter to close..."
    read -r
    exit 1
fi

# --- Check the headless Chromium binary (fast: stat only, no launch). ----
CHROMIUM_OK=$("$PY" - <<'PY' 2>/dev/null
import os
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        path = p.chromium.executable_path
    print("y" if path and os.path.exists(path) else "n")
except Exception:
    print("n")
PY
)
if [ "$CHROMIUM_OK" != "y" ]; then
    echo "✗ Headless Chromium not installed."
    echo ""
    echo "  Run, with the same Python this project uses:"
    echo "    $PY -m playwright install chromium"
    echo ""
    echo "Press Enter to close..."
    read -r
    exit 1
fi

"$PY" "$SCRIPT_DIR/previews/generate_instructions_preview.py"
STATUS=$?

if [ $STATUS -ne 0 ]; then
    echo "✗ Generator failed."
    echo ""
    echo "Press Enter to close..."
    read -r
    exit $STATUS
fi

echo "✓ Wrote previews/"
echo ""
echo "Press Enter to close..."
read -r
osascript -e 'tell application "Terminal" to close (every window whose name contains "Preview_Instructions")' &>/dev/null &
exit 0
