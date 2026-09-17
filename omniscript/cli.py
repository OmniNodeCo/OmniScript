"""The command line.

    omni                          a REPL
    omni program.omni             run a file
    omni -e 'cmd("tree /f")'      run one line
    omni --version
    omni update [--check]         see omniscript/update.py
"""

from __future__ import annotations

import argparse
import sys

from . import VERSION
from .language import Interpreter, OmniScriptError

BANNER = f"OmniScript {VERSION} -- draw, draw_gui, cmd, file, python. Ctrl-D to finish."


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
            with open(args.file, encoding="utf-8") as handle:
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
