#!/usr/bin/env sh
# Build the executable for the current machine. Native builds cannot be cross-compiled.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
BOOTSTRAP_PYTHON="${PYTHON:-python3}"
BUILD_VENV="${OMNISCRIPT_BUILD_VENV:-$ROOT/.build-venv}"

OS=$(uname -s)
ARCH=$(uname -m)
case "$OS" in
    Linux) PLATFORM=linux ;;
    Darwin) PLATFORM=macos ;;
    *) echo "error: unsupported build host $OS" >&2; exit 1 ;;
esac
case "$ARCH" in
    x86_64|amd64) ARCH=x86_64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) echo "error: unsupported architecture $ARCH" >&2; exit 1 ;;
esac

if [ ! -x "$BUILD_VENV/bin/python" ]; then
    "$BOOTSTRAP_PYTHON" -m venv "$BUILD_VENV"
fi
BUILD_PYTHON="$BUILD_VENV/bin/python"
"$BUILD_PYTHON" -m pip install --disable-pip-version-check -e ".[build]"
NAME="omni-$PLATFORM-$ARCH"
"$BUILD_PYTHON" scripts/build_executable.py --name "$NAME" --asset "$NAME" --output artifacts
