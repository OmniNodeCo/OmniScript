"""The `omniscript` command line.

    omniscript run hello.omni
    omniscript repl
    omniscript test
    omniscript docs chart
    omniscript -e 'print(1 + 1)'
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

from . import __version__
from .errors import OmniError, OmniRuntimeError, OmniThrow, describe
from .interp import Interpreter
from .lexer import tokenize
from .parser import parse
from .stdlib import install
from .values import to_repr, to_string

BANNER = r"""
  ___                 _ ___                 _
 / _ \_ __  _ __  ___(_)/ __| __ _ _ __| |_
| (_) | '  \| '  / -_) |\__ \/ _| '_ (_-<  _|
 \___/|_|_|_|_|_|_\___|_||___/\__| .__/__/\__|
                                 |_|
"""


def make_interp(args, root=None, argv=None) -> Interpreter:
    interp = Interpreter(
        writer=sys.stdout.write,
        root=root or os.getcwd(),
        argv=argv or [],
        quiet=getattr(args, "quiet", False),
        max_steps=getattr(args, "max_steps", None),
    )
    interp.load_builtins()
    return interp


def report(interp: Interpreter, err: OmniError, path: str | None) -> int:
    interp.enrich(err, path)
    sys.stderr.write(err.render() + "\n")
    return 1


# --------------------------------------------------------------------- run
def cmd_run(args) -> int:
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        sys.stderr.write(f"omni: cannot find `{args.file}`\n")
        return 2
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    interp = make_interp(args, root=os.path.dirname(path) or os.getcwd(),
                         argv=list(args.script_args or []))
    interp.globals.define("__file__", path)
    interp.globals.immutable.add("__file__")
    started = time.perf_counter()
    try:
        interp.run_source(src, path)
        if interp.main_fn is not None:
            interp.call_value(interp.main_fn, [], {}, node=None)
    except SystemExit as se:
        _finish(interp, args, started)
        return int(se.code or 0)
    except OmniError as err:
        _finish(interp, args, started, failed=True)
        return report(interp, err, path)
    except RecursionError:
        _finish(interp, args, started, failed=True)
        sys.stderr.write("omni: stack overflow: the program recursed too deeply\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\nomni: interrupted\n")
        return 130
    code = _finish(interp, args, started)
    return interp.exit_code if interp.exit_code is not None else code


def _finish(interp: Interpreter, args, started: float, failed: bool = False) -> int:
    if not failed and not getattr(args, "no_pictures", False):
        for line in interp.save_pending_pictures():
            pass  # save() already announced itself
    if getattr(args, "timing", False):
        sys.stderr.write(f"omni: finished in {(time.perf_counter() - started) * 1000:.1f} ms\n")
    return 0


# -------------------------------------------------------------------- eval
def cmd_eval(args) -> int:
    interp = make_interp(args)
    try:
        value = interp.run_source(args.code, "<-e>")
        if value is not None:
            interp.out(to_string(value))
    except SystemExit as se:
        return int(se.code or 0)
    except OmniError as err:
        return report(interp, err, "<-e>")
    return 0


# -------------------------------------------------------------------- repl
def cmd_repl(args) -> int:
    interp = make_interp(args)
    if not args.quiet:
        sys.stdout.write(f"OmniScript {__version__} -- type `help()` for the built-ins, "
                         f"`:quit` to leave.\n")
    buffer: list[str] = []
    while True:
        try:
            prompt = "  ... " if buffer else "omni> "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\n")
            break
        if not buffer and line.strip() in (":quit", ":q", "exit", "quit"):
            break
        if not buffer and line.strip().startswith(":"):
            _repl_command(interp, line.strip())
            continue
        buffer.append(line)
        source = "\n".join(buffer)
        if _unfinished(source):
            continue
        buffer = []
        if not source.strip():
            continue
        try:
            value = interp.run_source(source, "<repl>")
            if value is not None:
                interp.out(to_repr(value))
        except SystemExit:
            break
        except OmniError as err:
            interp.enrich(err, "<repl>")
            sys.stderr.write(err.render() + "\n")
        except RecursionError:
            sys.stderr.write("omni: stack overflow\n")
    return 0


def _repl_command(interp: Interpreter, line: str) -> None:
    parts = line[1:].split(None, 1)
    verb = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if verb in ("help", "h"):
        interp.call_value(interp.builtin_index["help"], [rest or None], {}, node=None)
    elif verb in ("type", "t") and rest:
        try:
            value = interp.run_source(rest, "<repl>")
            from .values import type_name
            interp.out(type_name(value))
        except OmniError as err:
            sys.stderr.write(err.render() + "\n")
    elif verb in ("vars", "v"):
        names = [k for k in interp.globals.vars if not k.startswith("__")
                 and k not in interp.builtin_index]
        for name in sorted(names):
            interp.out(f"  {name} = {to_repr(interp.globals.vars[name])}")
        if not names:
            interp.out("  (nothing defined yet)")
    elif verb in ("tokens",):
        for tok in tokenize(rest, "<repl>"):
            interp.out(f"  {tok.kind:10} {tok.value!r}  ({tok.line}:{tok.col})")
    elif verb in ("ast",):
        for node in parse(rest, "<repl>"):
            interp.out(f"  {node!r}")
    elif verb in ("reset",):
        interp = Interpreter(writer=sys.stdout.write, root=os.getcwd(), quiet=True)
        interp.load_builtins()
        Interpreter._current = interp
        sys.stderr.write("cleared every definition\n")
    elif verb in ("quit", "q"):
        raise SystemExit(0)
    else:
        interp.out("repl commands: :help :vars :type :tokens :ast :reset :quit")


def _unfinished(source: str) -> bool:
    """True while braces/brackets/parens are still open."""
    try:
        tokens = tokenize(source, "<repl>")
    except OmniError:
        return False
    depth = 0
    for tok in tokens:
        if tok.kind in ("LBRACE", "LBRACKET", "LPAREN"):
            depth += 1
        elif tok.kind in ("RBRACE", "RBRACKET", "RPAREN"):
            depth -= 1
    if depth > 0:
        return True
    stripped = source.rstrip()
    return stripped.endswith(("|>", "||>", ",", "+", "-", "*", "/", "=>", "->",
                              "=", "==", "and", "or"))


# ------------------------------------------------------------------- check
def _source_of(args):
    """The program to inspect: either `-e code` or the contents of a file."""
    inline = getattr(args, "eval", None)
    path = getattr(args, "file", None)
    if inline:
        return inline, "<-e>"
    if not path:
        raise OmniRuntimeError("give me a file to read, or use `-e \"code\"`")
    full = os.path.abspath(path)
    if not os.path.isfile(full):
        raise OmniRuntimeError(f"cannot find `{path}`")
    with open(full, "r", encoding="utf-8") as fh:
        return fh.read(), path


def cmd_check(args) -> int:
    interp = make_interp(args)
    try:
        src, path = _source_of(args)
        parse(src, path)
    except OmniError as err:
        return report(interp, err, getattr(args, "file", None) or "<-e>")
    interp.out(f"{path}: syntax is fine")
    return 0


def cmd_tokens(args) -> int:
    interp = make_interp(args)
    try:
        src, path = _source_of(args)
        for tok in tokenize(src, path):
            print(f"{tok.line:4}:{tok.col:<4} {tok.kind:10} {tok.value!r}")
    except OmniError as err:
        return report(interp, err, getattr(args, "file", None) or "<-e>")
    return 0


def cmd_ast(args) -> int:
    interp = make_interp(args)
    try:
        src, path = _source_of(args)
        program = parse(src, path)
    except OmniError as err:
        return report(interp, err, getattr(args, "file", None) or "<-e>")
    for node in program:
        print(repr(node))
    return 0


# -------------------------------------------------------------------- docs
def cmd_docs(args) -> int:
    interp = make_interp(args)
    name = args.name
    if not name:
        names = sorted(interp.builtin_index)
        print(f"OmniScript {__version__} -- {len(names)} built-in functions\n")
        width = max(len(n) for n in names) + 2
        for i in range(0, len(names), 4):
            print("".join(n.ljust(width) for n in names[i:i + 4]))
        print("\nRun `omniscript docs NAME` for one function, or `help()` inside a script.")
        return 0
    fn = interp.builtin_index.get(name)
    if fn is None:
        from .errors import suggest
        hint = suggest(name, interp.builtin_index)
        sys.stderr.write(f"omni: no built-in called `{name}`" + (f" ({hint})" if hint else "") + "\n")
        return 1
    from .interp import sig_of
    print(f"{name}{sig_of(fn.params)}")
    if fn.doc:
        print(f"\n{fn.doc}")
    return 0


# -------------------------------------------------------------------- test
def cmd_test(args) -> int:
    paths = list(args.files or [])
    if not paths:
        paths = sorted(glob.glob("**/*_test.omni", recursive=True) +
                       glob.glob("**/test_*.omni", recursive=True) +
                       glob.glob("tests/*.omni"))
        paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p)]
    if not paths:
        sys.stderr.write("omni: no test files found (name them *_test.omni or put them in tests/)\n")
        return 1

    interp = make_interp(args)
    passed = failed = 0
    failures = []
    for path in paths:
        abspath = os.path.abspath(path)
        try:
            with open(abspath, "r", encoding="utf-8") as fh:
                src = fh.read()
            interp.sources[abspath] = src
            interp.current_file = abspath
            interp.run_program(parse(src, abspath), interp.globals, abspath)
        except OmniError as err:
            failed += 1
            failures.append((path, None, err))
            continue
        if not interp.tests:
            continue
        for name, fn in list(interp.tests):
            try:
                interp.call_value(fn, [], {}, node=None)
                passed += 1
                interp.out(f"  ok   {name}")
            except OmniThrow as t:
                failed += 1
                failures.append((path, name, t))
                interp.out(f"  FAIL {name}: {describe(t.value)}")
            except OmniError as err:
                failed += 1
                failures.append((path, name, err))
                interp.out(f"  FAIL {name}: {err.message}")
            except AssertionError as err:
                failed += 1
                failures.append((path, name, err))
                interp.out(f"  FAIL {name}: {err}")
            interp.tests = [t for t in interp.tests if t[1] is not fn]
    if failures:
        interp.out("")
        for path, name, err in failures:
            where = f"{path}" + (f" :: {name}" if name else "")
            interp.out(f"-- {where}")
            if isinstance(err, OmniError):
                interp.enrich(err, os.path.abspath(path))
                interp.out(err.render())
            else:
                interp.out(f"  {err}")
    interp.out(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


# ------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omniscript",
        description="OmniScript -- a small language for doing big things in few lines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  omniscript run examples/hello.omni\n"
               "  omniscript -e 'print(2 ** 10)'\n"
               "  omniscript repl\n"
               "  omniscript test\n",
    )
    p.add_argument("--version", action="version", version=f"OmniScript {__version__}")
    sub = p.add_subparsers(dest="command")

    def common(sp):
        sp.add_argument("--quiet", "-q", action="store_true",
                        help="suppress notices such as saved picture paths")
        sp.add_argument("--max-steps", type=int, default=None,
                        help="stop runaway programs after this many steps")
        sp.add_argument("--no-pictures", action="store_true",
                        help="do not auto-save canvases when the program ends")

    run = sub.add_parser("run", help="run a .omni file")
    run.add_argument("file")
    run.add_argument("script_args", nargs=argparse.REMAINDER,
                     help="arguments passed to the script")
    run.add_argument("--timing", action="store_true", help="report how long it took")
    common(run)
    run.set_defaults(func=cmd_run)

    ev = sub.add_parser("eval", help="run a snippet of code")
    ev.add_argument("code")
    common(ev)
    ev.set_defaults(func=cmd_eval)

    repl = sub.add_parser("repl", help="an interactive prompt")
    common(repl)
    repl.set_defaults(func=cmd_repl)

    check = sub.add_parser("check", help="check syntax without running")
    check.add_argument("file", nargs="?")
    check.add_argument("-e", "--eval", help="inspect this code instead of a file")
    common(check)
    check.set_defaults(func=cmd_check)

    toks = sub.add_parser("tokens", help="print the token stream (debugging)")
    toks.add_argument("file", nargs="?")
    toks.add_argument("-e", "--eval", help="inspect this code instead of a file")
    common(toks)
    toks.set_defaults(func=cmd_tokens)

    astp = sub.add_parser("ast", help="print the syntax tree (debugging)")
    astp.add_argument("file", nargs="?")
    astp.add_argument("-e", "--eval", help="inspect this code instead of a file")
    common(astp)
    astp.set_defaults(func=cmd_ast)

    docs = sub.add_parser("docs", help="list or explain built-in functions")
    docs.add_argument("name", nargs="?")
    common(docs)
    docs.set_defaults(func=cmd_docs)

    test = sub.add_parser("test", help="run @test functions")
    test.add_argument("files", nargs="*")
    common(test)
    test.set_defaults(func=cmd_test)

    # shorthand: `omniscript -e 'code'` and `omniscript file.omni`
    p.add_argument("-e", dest="inline", help="run this code and exit")
    p.add_argument("target", nargs="?", help="a .omni file to run")
    p.add_argument("extra", nargs=argparse.REMAINDER)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if not argv:
        return cmd_repl(argparse.Namespace(quiet=False, max_steps=None,
                                           no_pictures=False))

    # `omniscript file.omni [args...]` and `omniscript -e 'code'`
    if argv[0] == "-e" and len(argv) >= 2:
        ns = argparse.Namespace(code=argv[1], quiet=False, max_steps=None,
                                no_pictures=False)
        return cmd_eval(ns)
    if not argv[0].startswith("-") and argv[0] not in (
            "run", "eval", "repl", "check", "tokens", "ast", "docs", "test"):
        ns = argparse.Namespace(file=argv[0], script_args=argv[1:], quiet=False,
                                max_steps=None, no_pictures=False, timing=False)
        return cmd_run(ns)

    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
