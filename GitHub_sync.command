#!/bin/zsh

# GitHub_sync.command — Double-clickable macOS script to git sync this project.
# Sources gsync from .zshrc for the nice emoji output.

# Resolve project root (same folder as this script)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

# Source zshrc to get gsync function
source ~/.zshrc 2>/dev/null

# Ask for commit message in terminal
echo ""
printf "  💬 Commit message (default: updates): "
read -r COMMIT_MSG
COMMIT_MSG="${COMMIT_MSG:-updates}"
echo ""

# Run gsync
gsync "$COMMIT_MSG"

# Keep window open so user can read output, then close
echo ""
echo "  Press Enter to close..."
read -r
osascript -e 'tell application "Terminal" to close (every window whose name contains "GitHub_sync")' &>/dev/null &
exit 0
