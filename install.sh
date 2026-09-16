#!/usr/bin/env bash
#
# Install OmniScript.
#
#   ./install.sh                     # symlink `omni` into ~/.local/bin
#   ./install.sh --mode venv         # self-contained venv, symlinked the same way
#   ./install.sh --prefix /usr/local --force
#   ./install.sh --vscode            # also drop in the editor extension
#
#   curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
#
# Nothing is copied in the default mode: `omni` and `omniscript` become symlinks
# to the launcher in the source tree, and the interpreter stays where it is.
# Everything the script creates is written to a manifest so uninstall.sh can
# take it all back out again -- and only what it put there.
#
# Bash 3.2 compatible, because that is still what macOS ships.

set -euo pipefail

REPO_URL="https://github.com/OmniNodeCo/OmniScript.git"
MIN_PYTHON="3.10"
COMMANDS="omni omniscript"

MODE="symlink"
PREFIX="${HOME}/.local"
BIN_DIR=""
PYTHON=""
SOURCE_DIR=""
REF="main"
WITH_VSCODE=0
BREAK_SYSTEM=0
PIP_USER=0
DRY_RUN=0
FORCE=0

usage() {
    cat <<'USAGE'
Usage: install.sh [options]

  --mode MODE        symlink (default), venv, or pip
  --prefix DIR       install root; commands land in DIR/bin   [~/.local]
  --bin DIR          where to put the commands                [PREFIX/bin]
  --source DIR       source tree to install from              [this script's directory]
  --python PATH      interpreter to use                       [first python3 >= 3.10 on PATH]
  --ref REF          branch or tag to fetch when cloning      [main]
  --vscode           also install the editor extension (VS Code, Cursor, vscode-server)
  --user             pip mode: install for this user only
  --break-system-packages
                     pip mode: pass through to pip on PEP 668 systems
  --force            replace commands this script did not create
  --dry-run          print what would happen and change nothing
  -h, --help         this text

Modes:
  symlink   point DIR/bin/omni at the launcher in the source tree. Instant, no
            copies, no network. The source tree has to stay where it is.
  venv      build a virtual environment under ~/.local/share/omniscript/venv,
            install the package into it, then symlink its commands. Survives
            deleting the source tree.
  pip       install into the interpreter you already use, then make sure the
            commands are reachable from DIR/bin.

The default mode needs no network and no root. Everything installed is recorded
in ~/.local/share/omniscript/install.json for uninstall.sh.
USAGE
}

die() {
    printf 'install.sh: error: %s\n' "$*" >&2
    exit 1
}

info() { printf '==> %s\n' "$*"; }

note() { printf '    %s\n' "$*"; }

# Run a command, or in --dry-run just show it.
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# Portable absolute path: macOS readlink has no -f.
abspath() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *)  printf '%s\n' "$PWD/$1" ;;
    esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --mode) MODE="${2:-}"; shift 2 ;;
        --mode=*) MODE="${1#*=}"; shift ;;
        --prefix) PREFIX="${2:-}"; shift 2 ;;
        --prefix=*) PREFIX="${1#*=}"; shift ;;
        --bin) BIN_DIR="${2:-}"; shift 2 ;;
        --bin=*) BIN_DIR="${1#*=}"; shift ;;
        --source) SOURCE_DIR="${2:-}"; shift 2 ;;
        --source=*) SOURCE_DIR="${1#*=}"; shift ;;
        --python) PYTHON="${2:-}"; shift 2 ;;
        --python=*) PYTHON="${1#*=}"; shift ;;
        --ref) REF="${2:-}"; shift 2 ;;
        --ref=*) REF="${1#*=}"; shift ;;
        --vscode) WITH_VSCODE=1; shift ;;
        --user) PIP_USER=1; shift ;;
        --break-system-packages) BREAK_SYSTEM=1; shift ;;
        --force) FORCE=1; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

case "$MODE" in
    symlink|venv|pip) ;;
    *) usage >&2; die "--mode must be symlink, venv or pip (got '$MODE')" ;;
esac
[ -n "$PREFIX" ] || die "--prefix needs a directory"
[ -n "$BIN_DIR" ] || BIN_DIR="$PREFIX/bin"

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omniscript"
MANIFEST="$DATA_DIR/install.json"
VENV_DIR="$DATA_DIR/venv"

# ---------------------------------------------------------- find the source
here="$(cd "$(dirname "$0")" 2>/dev/null && pwd -P || true)"
if [ -z "$SOURCE_DIR" ] && [ -n "$here" ] && [ -f "$here/omniscript/cli.py" ]; then
    SOURCE_DIR="$here"
fi
if [ -z "$SOURCE_DIR" ] && [ -n "${OMNI_HOME:-}" ] && [ -f "$OMNI_HOME/omniscript/cli.py" ]; then
    SOURCE_DIR="$OMNI_HOME"
fi

CLONED=0
if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/omniscript/cli.py" ]; then
    if [ -n "$SOURCE_DIR" ]; then
        die "--source $SOURCE_DIR is not an OmniScript source tree (no omniscript/cli.py)"
    fi
    SOURCE_DIR="$DATA_DIR/src"
    if [ -f "$SOURCE_DIR/omniscript/cli.py" ]; then
        info "Using the source already in $SOURCE_DIR"
        if [ "$REF" != main ]; then
            run git -C "$SOURCE_DIR" fetch --quiet origin "$REF"
            run git -C "$SOURCE_DIR" checkout --quiet "$REF"
        fi
    else
        command -v git >/dev/null 2>&1 ||
            die "no source tree here and no git to fetch one; run this from a clone, or pass --source DIR"
        info "Fetching OmniScript ($REF) into $SOURCE_DIR"
        run mkdir -p "$DATA_DIR"
        run git clone --quiet --branch "$REF" --depth 1 "$REPO_URL" "$SOURCE_DIR"
        CLONED=1
    fi
fi
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
[ -f "$SOURCE_DIR/omniscript/cli.py" ] || die "$SOURCE_DIR is not an OmniScript source tree"

# ------------------------------------------------------------- find python
if [ -z "$PYTHON" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    done
fi
[ -n "$PYTHON" ] || die "no python on PATH; install Python $MIN_PYTHON or newer, or pass --python PATH"
[ -x "$PYTHON" ] || die "$PYTHON is not executable"

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    found="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo unknown)"
    die "$PYTHON is Python $found; OmniScript needs $MIN_PYTHON or newer (try --python PATH)"
fi
PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
OMNI_VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, '$SOURCE_DIR'); import omniscript; print(omniscript.__version__)" 2>/dev/null || echo unknown)"

info "OmniScript $OMNI_VERSION from $SOURCE_DIR"
note "python $PY_VERSION ($PYTHON), commands into $BIN_DIR, mode $MODE"

# ------------------------------------------------- is the bin dir writable?
if [ "$DRY_RUN" != 1 ]; then
    run mkdir -p "$BIN_DIR"
elif [ ! -d "$BIN_DIR" ]; then
    run mkdir -p "$BIN_DIR"
fi
[ -w "$BIN_DIR" ] || [ "$DRY_RUN" = 1 ] ||
    die "$BIN_DIR is not writable; try --prefix ~/.local, or run with sudo --prefix /usr/local"

INSTALLED_COMMANDS=""
INSTALLED_VENV=""
PIP_TARGET=""

# --------------------------------------------------------------- symlink mode
link_command() {
    # link_command <name> <target>
    name="$1"
    target="$2"
    path="$BIN_DIR/$name"
    if [ -L "$path" ] || [ -e "$path" ]; then
        existing=""
        [ -L "$path" ] && existing="$(readlink "$path" 2>/dev/null || true)"
        if [ "$existing" = "$target" ]; then
            note "$name already points at $target"
            INSTALLED_COMMANDS="$INSTALLED_COMMANDS $path"
            return 0
        fi
        if [ "$FORCE" != 1 ]; then
            die "$path already exists and was not created by this script
       (it is $( [ -n "$existing" ] && printf 'a symlink to %s' "$existing" || printf 'a real file' ))
       Re-run with --force to replace it; a backup is kept next to it."
        fi
        run mv "$path" "$path.bak"
        note "moved the old $name to $path.bak"
    fi
    run ln -s "$target" "$path"
    note "$name -> $target"
    INSTALLED_COMMANDS="$INSTALLED_COMMANDS $path"
}

# Both linking modes create symlinks, so an existing regular file at that path
# belongs to somebody else. Say so before touching anything, rather than halfway
# through with one command linked and the next refused.
check_no_foreign_commands() {
    foreign=""
    for name in $COMMANDS; do
        path="$BIN_DIR/$name"
        if [ ! -L "$path" ] && { [ -e "$path" ] || [ -L "$path" ]; }; then
            foreign="$foreign
       $path"
        fi
    done
    if [ -n "$foreign" ] && [ "$FORCE" != 1 ]; then
        die "these already exist and were not created by this script:$foreign
       Re-run with --force to move them aside (a .bak copy is kept next to each),
       or point --bin somewhere else."
    fi
}

install_symlink_mode() {
    check_no_foreign_commands
    [ -x "$SOURCE_DIR/omni" ] || run chmod +x "$SOURCE_DIR/omni"
    for name in $COMMANDS; do
        link_command "$name" "$SOURCE_DIR/omni"
    done
}

# ------------------------------------------------------------------ venv mode
install_venv_mode() {
    check_no_foreign_commands
    info "Creating a virtual environment in $VENV_DIR"
    if [ -d "$VENV_DIR" ] && [ "$FORCE" = 1 ]; then
        run rm -rf "$VENV_DIR"
    fi
    run mkdir -p "$DATA_DIR"
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        run "$PYTHON" -m venv "$VENV_DIR"
    fi
    info "Installing the package into it"
    run "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    run "$VENV_DIR/bin/python" -m pip install --quiet "$SOURCE_DIR"
    INSTALLED_VENV="$VENV_DIR"
    for name in $COMMANDS; do
        [ -x "$VENV_DIR/bin/$name" ] || die "the venv has no $name command; the install did not take"
        link_command "$name" "$VENV_DIR/bin/$name"
    done
}

# ------------------------------------------------------------------- pip mode
install_pip_mode() {
    info "Installing into $PYTHON with pip"
    pip_args="install"
    [ "$PIP_USER" = 1 ] && pip_args="$pip_args --user"
    [ "$BREAK_SYSTEM" = 1 ] && pip_args="$pip_args --break-system-packages"
    # shellcheck disable=SC2086
    if ! pip_log="$(run "$PYTHON" -m pip $pip_args "$SOURCE_DIR" 2>&1)"; then
        printf '%s\n' "$pip_log" >&2
        case "$pip_log" in
            *externally-managed-environment*)
                die "this Python is managed by your OS. Either use --mode venv (recommended),
       or re-run with --break-system-packages if you know what that does."
                ;;
        esac
        die "pip install failed"
    fi
    printf '%s\n' "$pip_log" | tail -3 | while IFS= read -r line; do note "$line"; done

    PIP_TARGET="$("$PYTHON" - "$PIP_USER" <<'PY'
import os, sys, sysconfig
scheme = "%s_user" % os.name if sys.argv[1] == "1" else None
print(sysconfig.get_path("scripts", scheme))
PY
)"
    for name in $COMMANDS; do
        if [ -x "$PIP_TARGET/$name" ]; then
            if [ "$PIP_TARGET" != "$BIN_DIR" ]; then
                link_command "$name" "$PIP_TARGET/$name"
            else
                note "$name is already in $BIN_DIR"
                INSTALLED_COMMANDS="$INSTALLED_COMMANDS $BIN_DIR/$name"
            fi
        else
            note "pip did not create $PIP_TARGET/$name"
        fi
    done
}

case "$MODE" in
    symlink) install_symlink_mode ;;
    venv) install_venv_mode ;;
    pip) install_pip_mode ;;
esac

# ------------------------------------------------------- editor extension
VSCODE_DIRS=""
if [ "$WITH_VSCODE" = 1 ]; then
    EXT_VERSION="$("$PYTHON" - "$SOURCE_DIR" <<'PY'
import json, sys, pathlib
pkg = json.loads((pathlib.Path(sys.argv[1]) / "extras/vscode/package.json").read_text())
print("%s.%s-%s" % (pkg.get("publisher", "omninode"), pkg["name"], pkg["version"]))
PY
)" || die "could not read extras/vscode/package.json"
    found_editor=0
    for base in "$HOME/.vscode/extensions" "$HOME/.cursor/extensions" "$HOME/.vscode-server/extensions"; do
        editor_root="$(dirname "$base")"
        if [ -d "$editor_root" ] || [ "$base" = "$HOME/.vscode/extensions" ]; then
            ext_dir="$base/$EXT_VERSION"
            info "Installing the editor extension into $ext_dir"
            run mkdir -p "$ext_dir"
            run cp -R "$SOURCE_DIR/extras/vscode/." "$ext_dir/"
            VSCODE_DIRS="$VSCODE_DIRS $ext_dir"
            found_editor=1
        fi
    done
    [ "$found_editor" = 1 ] || note "no editor found; installed into ~/.vscode/extensions anyway"
    note "restart the editor to pick up OmniScript syntax highlighting"
fi

# ------------------------------------------------------------- manifest
if [ "$DRY_RUN" != 1 ]; then
    mkdir -p "$DATA_DIR"
    MODE="$MODE" SOURCE_DIR="$SOURCE_DIR" BIN_DIR="$BIN_DIR" PYTHON="$PYTHON" \
    VENV_DIR="$INSTALLED_VENV" PIP_TARGET="$PIP_TARGET" COMMANDS="$INSTALLED_COMMANDS" \
    VSCODE_DIRS="$VSCODE_DIRS" CLONED="$CLONED" DATA_DIR="$DATA_DIR" \
    BREAK_SYSTEM="$BREAK_SYSTEM" PIP_USER_FLAG="$PIP_USER" \
    OMNI_VERSION="$OMNI_VERSION" PY_VERSION="$PY_VERSION" \
    "$PYTHON" - "$MANIFEST" <<'PY'
import json, os, sys, datetime

def split(value):
    return [p for p in (value or "").split() if p]

manifest = {
    "package": "omniscript-lang",
    "version": os.environ["OMNI_VERSION"],
    "installed_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "mode": os.environ["MODE"],
    "source": os.environ["SOURCE_DIR"],
    "cloned_by_installer": os.environ["CLONED"] == "1",
    "bin_dir": os.environ["BIN_DIR"],
    "commands": split(os.environ["COMMANDS"]),
    "python": os.environ["PYTHON"],
    "python_version": os.environ["PY_VERSION"],
    "venv": os.environ["VENV_DIR"] or None,
    "pip_scripts_dir": os.environ["PIP_TARGET"] or None,
    # uninstall.sh needs these to talk to the same pip the same way
    "pip_user": os.environ["PIP_USER_FLAG"] == "1",
    "pip_break_system_packages": os.environ["BREAK_SYSTEM"] == "1",
    "editor_extensions": split(os.environ["VSCODE_DIRS"]),
    "history_file": os.path.join(os.path.expanduser("~"), ".omniscript_history"),
    "data_dir": os.environ["DATA_DIR"],
}
with open(sys.argv[1], "w") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("wrote", sys.argv[1])
PY
fi

# ------------------------------------------------------------- verify
if [ "$DRY_RUN" != 1 ]; then
    info "Checking the install"
    for path in $INSTALLED_COMMANDS; do
        [ -x "$path" ] || [ -L "$path" ] || die "$path is not usable"
    done
    reported="$("$BIN_DIR/omni" --version 2>&1)" || die "$BIN_DIR/omni --version failed: $reported"
    note "$reported"
    smoke="$("$BIN_DIR/omni" -e 'let c = draw(8, 8)
c.rect(0, 0, 8, 8, "#2ea043")
print("smoke ok:", 6 * 7, [1, 2, 3].map((x) -> x * x).join(","))' 2>&1)" ||
        die "the interpreter did not run: $smoke"
    note "$smoke"
fi

# ------------------------------------------------------------- PATH advice
case ":$PATH:" in
    *":$BIN_DIR:"*) on_path=1 ;;
    *) on_path=0 ;;
esac

if [ "$DRY_RUN" = 1 ]; then
    info "Dry run: nothing was changed"
    exit 0
fi

printf '\n'
info "OmniScript $OMNI_VERSION is installed"
if [ "$on_path" = 1 ]; then
    note "run it with: omni -e 'print(\"hello\")'   or just: omni"
else
    note "$BIN_DIR is not on your PATH yet. Add this to your shell profile:"
    printf '\n        export PATH="%s:$PATH"\n\n' "$BIN_DIR"
    note "then open a new terminal, or run that line now."
fi
note "uninstall with: $SOURCE_DIR/uninstall.sh"
