#!/usr/bin/env bash
set -euo pipefail
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
echo "==> Removing OmniScript"
rm -f "$BIN_DIR/omni"
rm -f "$HOME/.local/share/applications/omniscript.desktop"
rm -rf "$HOME/.local/share/omniscript"
rm -rf "$HOME/Applications/OmniScript.app"
echo "Removed"
