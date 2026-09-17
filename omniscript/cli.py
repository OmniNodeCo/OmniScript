"""The command line.

    omni                          a REPL
    omni program.omni             run a file
    omni -e 'cmd("tree /f")'      run one line
    omni --version
    omni update [--check]         see omniscript/update.py
"""

from __future__ import annotations

import argparse
import shlex
import sys

from . import VERSION
from .language import Interpreter, OmniScriptError

BANNER = (f"OmniScript {VERSION} -- draw, draw_gui, cmd, file, python. "
          "'help' for help, Ctrl-D to finish.")

REPL_HELP = """OmniScript in this session: draw(...), draw_gui(...), draw_gui.button(...),
draw_gui.window_size(...), cmd(...), file(...), python(...). Also:
  omni FILE      run a file in this session
  omni -e CODE   run one line in this session
  omni update    update OmniScript, then restart omni
  update ...     the same update
  help           this text
  exit           leave (Ctrl-D works too)"""

SHELL_NAMES = ("omni", "omniscript")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni",
        description="OmniScript: draw(), draw_gui.button(), draw_gui.window_size() "
                    "and Python-like imports -- plus cmd(), file() and, once you "
                    "have written an import, python().",
        epilog="With no file and no -e, omni starts a REPL.")
    parser.add_argument("file", nargs="?", metavar="FILE", help="a .omni file to run")
    parser.add_argument("-e", dest="inline", metavar="CODE", help="run this code and exit")
    parser.add_argument("-V", "--version", action="store_true", help="the version, and exit")
    return parser


def build_update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni update",
        description="Update OmniScript along one of two channels.")
    parser.add_argument("--channel", "-c", choices=("release", "beta"), default="",
                        help="release (the default): the newest published release; "
                             "beta: the newest commit in the repository")
    parser.add_argument("--check", action="store_true",
                        help="say what is available and change nothing")
    parser.add_argument("--version", "--tag", dest="version", default="", metavar="VERSION",
                        help="a particular release, for example 1.2.0 or v1.2.0")
    parser.add_argument("--ref", default="", metavar="REF",
                        help="beta channel: the branch to follow [the one tracked, or main]")
    parser.add_argument("--bin", dest="bin_dir", default="", metavar="DIR",
                        help="where a downloaded file goes [where this one is]")
    parser.add_argument("--api-url", default="", metavar="URL",
                        help="the API root to ask [https://api.github.com]")
    parser.add_argument("--force", action="store_true",
                        help="update even when it looks like nothing has changed")
    return parser


def repl_shell(line: str, interp: Interpreter):
    """Shell-style lines at the REPL: `omni ...`, `update`, `help`, `exit`.

    Returns "run" when the line was handled here, "leave" to end the session,
    and None when the line is OmniScript after all.
    """
    words = line.strip().split(None, 1)
    first = words[0]
    rest = words[1] if len(words) > 1 else ""
    if first in ("exit", "quit") and not rest:
        return "leave"
    if first == "help" and not rest:
        print(REPL_HELP)
        return "run"
    if first in SHELL_NAMES:
        return repl_omni(rest, interp)
    if first == "update":
        try:
            return repl_update(shlex.split(rest))
        except ValueError as err:
            print(f"omni: {err}", file=sys.stderr)
            return "run"
    return None


def repl_omni(rest: str, interp: Interpreter) -> str:
    """`omni ...` inside the REPL: the shell command line, run in this session."""
    if not rest:
        print("you are already in omni -- type an OmniScript command, or:\n"
              "  omni FILE     run a file in this session\n"
              "  omni -e CODE  run one line in this session\n"
              "  omni update   update OmniScript (then restart omni)\n"
              "  exit          leave (Ctrl-D works too)")
        return "run"
    try:
        args = shlex.split(rest)
    except ValueError as err:
        print(f"omni: {err}", file=sys.stderr)
        return "run"
    if args and args[0] == "update":
        return repl_update(args[1:])
    try:
        parsed = build_parser().parse_args(args)
    except SystemExit:
        return "run"                               # argparse already said why
    if parsed.version:
        print(f"OmniScript {VERSION}")
        return "run"
    if parsed.inline is not None:
        source, name = parsed.inline, "-e"
    elif parsed.file:
        try:
            with open(parsed.file, encoding="utf-8-sig") as handle:
                source = handle.read()
        except OSError as err:
            print(f"omni: {err}", file=sys.stderr)
            return "run"
        name = parsed.file
    else:
        print("usage: omni FILE | omni -e CODE | omni update | omni --version")
        return "run"
    try:
        interp.run(source, name)
    except OmniScriptError as err:
        print(err, file=sys.stderr)
    return "run"


def repl_update(argv: list) -> str:
    """`update ...` inside the REPL: the same updater the shell runs."""
    from . import update
    try:
        parsed = build_update_parser().parse_args(argv)
    except SystemExit:
        return "run"                               # argparse already said why
    update.run(parsed)
    return "run"


def repl(interp: Interpreter) -> int:
    try:
        import readline                              # noqa: F401 - history and editing
    except ImportError:
        pass
    print(BANNER)
    pending = ""
    while True:
        try:
            pending_line = input("omni> " if not pending else "  ... ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            pending = ""
            continue
        pending = pending + "\n" + pending_line if pending else pending_line
        if not pending.strip():
            pending = ""
            continue
        if pending.count("(") > pending.count(")"):
            continue                                 # a call that is not finished yet
        action = repl_shell(pending, interp)
        if action == "leave":
            return 0
        if action == "run":
            pending = ""
            continue
        try:
            interp.run(pending, "<repl>")
        except OmniScriptError as err:
            print(err, file=sys.stderr)
        pending = ""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # `update` is a command, not a file to run, so it is dealt with before the
    # parser that takes a file name ever sees it.
    if argv and argv[0] == "update":
        from . import update
        return update.run(build_update_parser().parse_args(argv[1:]))

    args = build_parser().parse_args(argv)
    if args.version:
        print(f"OmniScript {VERSION}")
        return 0

    interp = Interpreter()
    if args.inline is not None:
        source, name = args.inline, "-e"
    elif args.file:
        try:
            # utf-8-sig: a file saved with a byte-order mark (Windows editors
            # still do this) reads the same as one saved without it.
            with open(args.file, encoding="utf-8-sig") as handle:
                source = handle.read()
        except OSError as err:
            print(f"omni: {err}", file=sys.stderr)
            return 1
        name = args.file
    else:
        return repl(interp)

    try:
        interp.run(source, name)
    except OmniScriptError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
