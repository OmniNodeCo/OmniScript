#!/usr/bin/env sh
set -eu

BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"
LEGACY_DIR="${OMNISCRIPT_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omniscript}"
rm -f "$BIN_DIR/omni" "$BIN_DIR/omniscript"
# Clean installations made by OmniScript 0.1's original Python installer.
rm -rf "$LEGACY_DIR"
echo "OmniScript was removed from $BIN_DIR"
