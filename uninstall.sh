#!/usr/bin/env bash
#
# Uninstall OmniScript.
#
#   ./uninstall.sh                # take out the commands, the venv, the extension
#   ./uninstall.sh --dry-run      # show what would go
#   ./uninstall.sh --purge        # ...and the REPL history, a cloned source tree,
#                                 #    the manifest itself
#
# This works from the manifest install.sh wrote, so it removes exactly what was
# installed and nothing else -- whether that was a symlink into a source tree, a
# venv, a pip install, or a standalone executable downloaded from a release. It
# never deletes a source tree you cloned yourself, and it will not touch a
# command it cannot prove it created: use --force for that, and read what it
# says first.
#
# A release install can happen on a machine that has never had Python on it, so
# the manifest is read with awk when there is no Python to read it with.

set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omniscript"
MANIFEST="$DATA_DIR/install.json"
PREFIX="${HOME}/.local"
BIN_DIR=""
PURGE=0
DRY_RUN=0
FORCE=0
KEEP_VSCODE=0
NO_PYTHON=0
READ_MANIFEST="" 

usage() {
    cat <<'USAGE'
Usage: uninstall.sh [options]

  --prefix DIR       install root that was used              [~/.local]
  --bin DIR          where the commands are                  [PREFIX/bin]
  --purge            also remove the REPL history, a source tree the installer
                     cloned, and the manifest
  --keep-vscode      leave the editor extension in place
  --force            remove commands even when they do not look like ours
  --no-python        read the manifest with awk even if a Python is on PATH
  --read-manifest FILE
                     print the manifest as KEY=value lines and stop
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
        --bin) BIN_DIR="${2:-}"; shift 2 ;;
        --bin=*) BIN_DIR="${1#*=}"; shift ;;
        --purge) PURGE=1; shift ;;
        --keep-vscode) KEEP_VSCODE=1; shift ;;
        --force) FORCE=1; shift ;;
        --no-python) NO_PYTHON=1; shift ;;
        --read-manifest) [ $# -ge 2 ] || die "--read-manifest needs a file"
                         READ_MANIFEST="$2"; shift 2 ;;
        --read-manifest=*) READ_MANIFEST="${1#*=}"; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

[ -n "$BIN_DIR" ] || BIN_DIR="$PREFIX/bin"

# ------------------------------------------------------- an interpreter
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$(command -v "$candidate")"
        break
    fi
done

M_MODE="" M_SOURCE="" M_CLONED=0 M_VENV="" M_PIPDIR="" M_VERSION="" M_BREAK_SYSTEM=0
M_COMMANDS="" M_EXTENSIONS="" M_HISTORY="$HOME/.omniscript_history"
M_BINARY="" M_CHANNEL="" M_REF=""

# The manifest as KEY=value lines, read by Python when there is one.
read_manifest_python() {
    "$PYTHON" - "$1" <<'PY'
import json, shlex, sys

with open(sys.argv[1]) as fh:
    m = json.load(fh)

def lines(values):
    return "\n".join(v for v in (values or []) if v)

print("M_MODE=%s" % shlex.quote(str(m.get("mode") or "")))
print("M_SOURCE=%s" % shlex.quote(str(m.get("source") or "")))
print("M_CLONED=%s" % shlex.quote("1" if m.get("cloned_by_installer") else "0"))
print("M_VENV=%s" % shlex.quote(str(m.get("venv") or "")))
print("M_PIPDIR=%s" % shlex.quote(str(m.get("pip_scripts_dir") or "")))
print("M_VERSION=%s" % shlex.quote(str(m.get("version") or "")))
print("M_BREAK_SYSTEM=%s" % shlex.quote("1" if m.get("pip_break_system_packages") else "0"))
print("M_COMMANDS=%s" % shlex.quote(lines(m.get("commands"))))
print("M_EXTENSIONS=%s" % shlex.quote(lines(m.get("editor_extensions"))))
print("M_HISTORY=%s" % shlex.quote(str(m.get("history_file") or "~/.omniscript_history")))
print("M_BINARY=%s" % shlex.quote(str(m.get("binary") or "")))
print("M_CHANNEL=%s" % shlex.quote(str(m.get("channel") or "")))
print("M_REF=%s" % shlex.quote(str(m.get("ref") or "")))
PY
}

# The same thing in awk, for a machine where a release install was the only
# thing that ever happened. It reads both shapes install.sh writes: the indented
# arrays Python produces and the flat ones the shell writer produces. Values come
# out double-quoted, with the four characters that matter to a shell escaped.
read_manifest_awk() {
    awk '
    function dq(value) {
        gsub(/\\/, "\\\\", value)
        gsub(/"/, "\\\"", value)
        gsub(/\$/, "\\$", value)
        gsub(/`/, "\\`", value)
        return "\"" value "\""
    }
    function trim(value) {
        gsub(/^[ \t]+|[ \t]+$/, "", value)
        return value
    }
    function unquote(value) {
        value = trim(value)
        sub(/,$/, "", value)
        if (value == "null") return ""
        if (value ~ /^".*"$/) return substr(value, 2, length(value) - 2)
        return value
    }
    function emit(key, value) {
        if (key == "mode") print "M_MODE=" dq(value)
        else if (key == "source") print "M_SOURCE=" dq(value)
        else if (key == "cloned_by_installer") print "M_CLONED=" dq(value == "true" ? "1" : "0")
        else if (key == "venv") print "M_VENV=" dq(value)
        else if (key == "pip_scripts_dir") print "M_PIPDIR=" dq(value)
        else if (key == "version") print "M_VERSION=" dq(value)
        else if (key == "pip_break_system_packages") print "M_BREAK_SYSTEM=" dq(value == "true" ? "1" : "0")
        else if (key == "commands") print "M_COMMANDS=" dq(value)
        else if (key == "editor_extensions") print "M_EXTENSIONS=" dq(value)
        else if (key == "history_file") print "M_HISTORY=" dq(value)
        else if (key == "binary") print "M_BINARY=" dq(value)
        else if (key == "channel") print "M_CHANNEL=" dq(value)
        else if (key == "ref") print "M_REF=" dq(value)
    }
    function flat_array(text,   inner, parts, count, i, item, out) {
        inner = trim(text)
        sub(/,$/, "", inner)
        sub(/^\[/, "", inner)
        sub(/\]$/, "", inner)
        count = split(inner, parts, ",")
        out = ""
        for (i = 1; i <= count; i++) {
            item = unquote(parts[i])
            if (item != "") out = (out == "" ? item : out "\n" item)
        }
        return out
    }
    BEGIN { in_array = 0; key = ""; acc = "" }
    {
        line = $0
        sub(/\r$/, "", line)
        if (in_array) {
            if (line ~ /^[ \t]*\]/) { emit(key, acc); in_array = 0; key = ""; acc = ""; next }
            item = unquote(line)
            if (item != "") acc = (acc == "" ? item : acc "\n" item)
            next
        }
        if (line !~ /^[ \t]*"[^"]+"[ \t]*:/) next
        key = line
        sub(/^[ \t]*"/, "", key)
        sub(/".*$/, "", key)
        value = line
        sub(/^[^:]*:[ \t]*/, "", value)
        if (value ~ /^[ \t]*\[/) {
            if (value ~ /\][ \t]*,?[ \t]*$/) { emit(key, flat_array(value)); key = ""; next }
            in_array = 1
            acc = ""
            next
        }
        emit(key, unquote(value))
        key = ""
    }
    ' "$1"
}

read_manifest() {
    if [ -n "$PYTHON" ] && [ "$NO_PYTHON" != 1 ]; then
        read_manifest_python "$1" 2>/dev/null || read_manifest_awk "$1"
    else
        read_manifest_awk "$1"
    fi
}

if [ -n "$READ_MANIFEST" ]; then
    [ -f "$READ_MANIFEST" ] || die "--read-manifest: there is no file at $READ_MANIFEST"
    read_manifest "$READ_MANIFEST"
    exit 0
fi

if [ -f "$MANIFEST" ]; then
    if [ -n "$PYTHON" ] && [ "$NO_PYTHON" != 1 ]; then
        info "Reading $MANIFEST"
    elif [ -n "$PYTHON" ]; then
        info "Reading $MANIFEST with awk (--no-python)"
    else
        info "Reading $MANIFEST with awk (no python on PATH)"
    fi
    eval "$(read_manifest "$MANIFEST")"
    if [ -n "$M_VERSION" ]; then
        info "OmniScript $M_VERSION, installed in $M_MODE mode"
        [ -n "$M_CHANNEL" ] && note "$M_CHANNEL channel$( [ -n "$M_REF" ] && printf ', tracking %s' "$M_REF")"
    fi
else
    note "no manifest at $MANIFEST; falling back to $BIN_DIR"
fi

REMOVED=0 KEPT=0

# A path is ours when the manifest lists it -- that record was written by
# install.sh, so it is the strongest evidence there is, and the only evidence a
# downloaded executable can ever offer. Failing that: a symlink into something we
# installed, or a real file that pip wrote for us.
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
        for root in "$M_SOURCE" "$M_VENV" "$M_PIPDIR"; do
            [ -n "$root" ] || continue
            case "$target" in
                "$root"/*) return 0 ;;
            esac
        done
        # No manifest roots to compare against: trust a link whose target sits in
        # an OmniScript tree.
        if [ -z "$M_SOURCE" ] && [ -f "$(dirname "$target")/omniscript/cli.py" ]; then
            return 0
        fi
        return 1
    fi
    if [ -f "$path" ]; then
        # The manifest says pip put its console scripts here, so they are ours.
        [ -n "$M_PIPDIR" ] && [ "$BIN_DIR" = "$M_PIPDIR" ] && return 0
        # Otherwise only a generated console script counts: it imports the CLI
        # entry point by name. A file that merely mentions OmniScript -- a note,
        # a wrapper someone wrote, a different tool -- is left strictly alone.
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

# ----------------------------------------------------------------- venv
if [ -n "$M_VENV" ] && [ -d "$M_VENV" ]; then
    case "$M_VENV" in
        "$DATA_DIR"/*|"$DATA_DIR")
            info "Removing the virtual environment"
            run rm -rf "$M_VENV"
            note "removed $M_VENV"
            REMOVED=$((REMOVED + 1))
            ;;
        *)
            warn "$M_VENV" "it is outside $DATA_DIR, which is not where install.sh builds one"
            KEPT=$((KEPT + 1))
            ;;
    esac
fi

# ------------------------------------------------------------------ pip
if [ "$M_MODE" = pip ] && [ -n "$PYTHON" ]; then
    info "Asking pip to remove the package"
    pip_extra=""
    [ "$M_BREAK_SYSTEM" = 1 ] && pip_extra="--break-system-packages"
    if [ "$DRY_RUN" = 1 ]; then
        note "[dry-run] $PYTHON -m pip uninstall -y $pip_extra omniscript-lang"
    else
        # shellcheck disable=SC2086
        if pip_out="$("$PYTHON" -m pip uninstall -y $pip_extra omniscript-lang 2>&1)"; then
            note "pip uninstalled omniscript-lang"
        elif printf '%s' "$pip_out" | grep -q "externally-managed-environment"; then
            # The manifest did not know, but this interpreter does: try once more.
            if pip_out="$("$PYTHON" -m pip uninstall -y --break-system-packages \
                    omniscript-lang 2>&1)"; then
                note "pip uninstalled omniscript-lang"
            else
                note "pip refused to remove the package:"
                printf '%s\n' "$pip_out" | tail -3 | sed 's/^/       /' >&2
            fi
        else
            note "pip had nothing to remove, or said:"
            printf '%s\n' "$pip_out" | tail -3 | sed 's/^/       /'
        fi
    fi
fi

# --------------------------------------------------- editor extensions
if [ "$KEEP_VSCODE" = 1 ]; then
    note "keeping the editor extension (--keep-vscode)"
elif [ -n "$M_EXTENSIONS" ]; then
    info "Removing the editor extension"
    while IFS= read -r ext; do
        [ -n "$ext" ] || continue
        case "$(basename "$ext")" in
            *omniscript*)
                if [ -f "$ext/package.json" ] && grep -q '"name": *"omniscript"' "$ext/package.json" 2>/dev/null; then
                    run rm -rf "$ext"
                    note "removed $ext"
                    REMOVED=$((REMOVED + 1))
                else
                    warn "$ext" "it is not an OmniScript extension directory"
                    KEPT=$((KEPT + 1))
                fi
                ;;
            *)
                warn "$ext" "the directory name does not mention omniscript"
                KEPT=$((KEPT + 1))
                ;;
        esac
    done <<EOF
$M_EXTENSIONS
EOF
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
