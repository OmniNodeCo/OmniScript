#!/usr/bin/env bash
#
# Uninstall OmniScript.
#
#   ./uninstall.sh                # take out the commands
#   ./uninstall.sh --dry-run      # show what would go
#   ./uninstall.sh --purge        # ...and the REPL history, a cloned source tree,
#                                 #    the manifest itself
#
# This works from the manifest install.sh wrote, so it removes exactly what was
# installed and nothing else -- a downloaded executable as readily as a symlink
# into a source tree. It never deletes a source tree you cloned yourself, and it
# will not touch a command it cannot prove it created: use --force for that, and
# read what it says first.
#
# The manifest is one key=value per line, so this needs nothing but a shell: a
# machine that took the executable because it had no Python can still be cleaned
# up exactly.

set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omniscript"
MANIFEST="$DATA_DIR/install.txt"
PREFIX="${HOME}/.local"
PURGE=0
DRY_RUN=0
FORCE=0

usage() {
    cat <<'USAGE'
Usage: uninstall.sh [options]

  --prefix DIR       install root that was used              [~/.local]
  --purge            also remove the REPL history, a source tree the installer
                     cloned, and the manifest
  --force            remove commands even when they do not look like ours
  --dry-run, -n      print what would be removed and remove nothing
  -h, --help         this text

Without a manifest this falls back to looking in the bin directory for `omni`
and `omniscript` and removing only the ones that point at an OmniScript tree.
USAGE
}

die()  { printf 'uninstall.sh: error: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    leaving %s alone: %s\n' "$1" "$2" >&2; }

run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="${2:-}"; shift 2 ;;
        --prefix=*) PREFIX="${1#*=}"; shift ;;
        --purge) PURGE=1; shift ;;
        --force) FORCE=1; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

BIN_DIR="$PREFIX/bin"

M_MODE="" M_SOURCE="" M_CLONED=0 M_VERSION="" M_BINARY="" M_CHANNEL=""
M_COMMANDS="" M_HISTORY="$HOME/.omniscript_history"

# One key=value per line, so reading it is sed: no Python, no JSON parser, and
# nothing to escape. A repeated key is a list.
mget() { sed -n "s/^$1=//p" "$MANIFEST" | head -1; }
mall() { sed -n "s/^$1=//p" "$MANIFEST"; }

read_manifest() {
    M_VERSION="$(mget version)"
    M_MODE="$(mget mode)"
    M_CHANNEL="$(mget channel)"
    M_REF="$(mget ref)"
    M_SOURCE="$(mget source)"
    M_BINARY="$(mget binary)"
    M_CLONED="$(mget cloned_by_installer)"
    [ -n "$(mget history_file)" ] && M_HISTORY="$(mget history_file)"
    M_COMMANDS="$(mall command)"
}

if [ -f "$MANIFEST" ]; then
    info "Reading $MANIFEST"
    read_manifest
    if [ -n "$M_VERSION" ]; then
        info "OmniScript $M_VERSION, installed in $M_MODE mode"
        [ -n "$M_CHANNEL" ] && note "$M_CHANNEL channel"
    fi
else
    note "no manifest at $MANIFEST; falling back to $BIN_DIR"
fi

REMOVED=0 KEPT=0

# A path is ours when the manifest lists it -- that record was written by
# install.sh, so it is the strongest evidence there is, and the only evidence a
# downloaded executable can ever offer. Failing that: a symlink into the source
# tree we installed from, or a console script pip generated for us.
belongs_to_us() {
    path="$1"
    if [ -n "$M_COMMANDS" ]; then
        while IFS= read -r recorded; do
            [ -n "$recorded" ] || continue
            [ "$recorded" = "$path" ] && return 0
        done <<EOF
$M_COMMANDS
EOF
    fi
    if [ -n "$M_BINARY" ] && [ "$M_BINARY" = "$path" ]; then
        return 0
    fi
    if [ -L "$path" ]; then
        target="$(readlink "$path" 2>/dev/null || true)"
        case "$target" in
            /*) ;;
            *) target="$BIN_DIR/$target" ;;
        esac
        if [ -n "$M_SOURCE" ]; then
            case "$target" in
                "$M_SOURCE"/*) return 0 ;;
            esac
        fi
        # No manifest roots to compare against: trust a link whose target sits in
        # an OmniScript tree.
        if [ -z "$M_SOURCE" ] && [ -f "$(dirname "$target")/omniscript/cli.py" ]; then
            return 0
        fi
        return 1
    fi
    if [ -f "$path" ]; then
        # Only a generated console script counts: it imports the CLI entry point
        # by name. A file that merely mentions OmniScript -- a note, a wrapper
        # someone wrote, a different tool -- is left strictly alone.
        head -c 4096 "$path" 2>/dev/null |
            grep -qE "from omniscript\.cli import main|omniscript\.cli:main" && return 0
    fi
    return 1
}

remove_path() {
    path="$1"
    what="${2:-command}"
    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        return 0
    fi
    if ! belongs_to_us "$path" && [ "$FORCE" != 1 ]; then
        warn "$path" "it does not look like something install.sh created (use --force)"
        KEPT=$((KEPT + 1))
        return 0
    fi
    run rm -rf "$path"
    note "removed $what $path"
    REMOVED=$((REMOVED + 1))
}

# ------------------------------------------------------------- commands
info "Removing the commands"
if [ -n "$M_COMMANDS" ]; then
    while IFS= read -r path; do
        [ -n "$path" ] && remove_path "$path" "command"
    done <<EOF
$M_COMMANDS
EOF
else
    for name in omni omniscript; do
        remove_path "$BIN_DIR/$name" "command"
    done
fi
for name in omni omniscript; do
    if [ -e "$BIN_DIR/$name.bak" ]; then
        note "a backup of your previous $name is still at $BIN_DIR/$name.bak"
    fi
done

# ---------------------------------------------------- a downloaded executable
# Normally the commands list already covered it; this catches a binary that was
# moved or a manifest written by an older installer.
if [ -n "$M_BINARY" ] && [ -f "$M_BINARY" ]; then
    listed=0
    if [ -n "$M_COMMANDS" ]; then
        while IFS= read -r recorded; do
            [ "$recorded" = "$M_BINARY" ] && listed=1
        done <<EOF
$M_COMMANDS
EOF
    fi
    if [ "$listed" != 1 ]; then
        info "Removing the downloaded executable"
        remove_path "$M_BINARY" "executable"
    fi
fi

# --------------------------------------------------------------- purge
if [ "$PURGE" = 1 ]; then
    info "Purging what is left"
    if [ -f "$M_HISTORY" ]; then
        run rm -f "$M_HISTORY"
        note "removed the REPL history $M_HISTORY"
        REMOVED=$((REMOVED + 1))
    fi
    if [ "$M_CLONED" = 1 ] && [ -n "$M_SOURCE" ] && [ -d "$M_SOURCE" ]; then
        case "$M_SOURCE" in
            "$DATA_DIR"/*)
                run rm -rf "$M_SOURCE"
                note "removed the source the installer cloned: $M_SOURCE"
                REMOVED=$((REMOVED + 1))
                ;;
            *)
                warn "$M_SOURCE" "the installer did not clone it, so it stays"
                KEPT=$((KEPT + 1))
                ;;
        esac
    fi
    if [ "$DRY_RUN" != 1 ] && [ -d "$DATA_DIR" ]; then
        rm -rf "$DATA_DIR"
        note "removed $DATA_DIR (including the manifest)"
    elif [ -d "$DATA_DIR" ]; then
        note "[dry-run] would remove $DATA_DIR"
    fi
elif [ -f "$MANIFEST" ] && [ "$DRY_RUN" != 1 ]; then
    rm -f "$MANIFEST"
    note "removed the manifest $MANIFEST"
fi

printf '\n'
if [ "$DRY_RUN" = 1 ]; then
    info "Dry run: $REMOVED item(s) would be removed, $KEPT left alone"
else
    info "OmniScript is uninstalled ($REMOVED removed, $KEPT left alone)"
fi
if [ "$KEPT" != 0 ]; then
    note "anything left alone is listed above; re-run with --force if you want it gone"
fi
note "a source tree you cloned yourself is never deleted by this script"
if [ "$M_CHANNEL" = release ]; then
    note "to put the published release back: curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash"
fi
