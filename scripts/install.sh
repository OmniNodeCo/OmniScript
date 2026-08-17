#!/usr/bin/env sh
# Install OmniScript into an isolated virtual environment.
set -eu

PYTHON_BIN="${PYTHON:-python3}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${OMNISCRIPT_INSTALL_DIR:-$DATA_HOME/omniscript}"
BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"
DEFAULT_SOURCE="https://github.com/OmniNodeCo/OmniScript/archive/refs/heads/main.zip"
SOURCE="${OMNISCRIPT_SOURCE:-$DEFAULT_SOURCE}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "error: Python 3.10 or newer is required" >&2
    exit 1
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "error: Python 3.10 or newer is required" >&2
    exit 1
}

# When invoked from a checkout, install that checkout unless a source override was supplied.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || true)
if [ -z "${OMNISCRIPT_SOURCE:-}" ] && [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    SOURCE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
fi

echo "Installing OmniScript from $SOURCE"
rm -rf "$INSTALL_DIR"
"$PYTHON_BIN" -m venv "$INSTALL_DIR"
"$INSTALL_DIR/bin/python" -m pip install --disable-pip-version-check --upgrade pip >/dev/null
"$INSTALL_DIR/bin/python" -m pip install --disable-pip-version-check "$SOURCE"

mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/bin/omni" "$BIN_DIR/omni"
ln -sf "$INSTALL_DIR/bin/omniscript" "$BIN_DIR/omniscript"

echo
echo "OmniScript installed successfully."
echo "  executable: $BIN_DIR/omni"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "  note: add $BIN_DIR to your PATH" ;;
esac
"$BIN_DIR/omni" --version
