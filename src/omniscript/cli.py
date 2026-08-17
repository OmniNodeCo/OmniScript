"""Command-line interface for the OmniScript toolchain."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

from . import __version__
from .api import OmniEngine
from .checker import check_program
from .errors import OmniError, OmniRuntimeError
from .formatter import format_source
from .lexer import Lexer
from .parser import Parser
from .runtime import stringify
from .updater import UpdateCheckError, cache_directory, check_for_updates, clear_update_cache


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni",
        description="OmniScript language toolchain",
        epilog="Run `omni <command> --help` for command-specific help.",
    )
    parser.add_argument("--version", action="version", version=f"OmniScript {__version__}")
    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser("run", help="run a .omni program")
    run.add_argument("file", nargs="?", help="program path; defaults to omni.toml's entry")
    run.add_argument("--no-check", action="store_true", help="skip semantic checks")
    run.add_argument("args", nargs=argparse.REMAINDER, help="arguments exposed to the program as args")
    run.set_defaults(handler=_command_run)

    repl = subcommands.add_parser("repl", help="start an interactive OmniScript session")
    repl.set_defaults(handler=_command_repl)

    check = subcommands.add_parser("check", help="lex, parse, and semantically check source files")
    check.add_argument("files", nargs="+", help="one or more .omni files")
    check.set_defaults(handler=_command_check)

    fmt = subcommands.add_parser("fmt", help="format source files in place")
    fmt.add_argument("files", nargs="+", help="one or more .omni files")
    fmt.add_argument("--check", action="store_true", help="report files that need formatting without writing")
    fmt.set_defaults(handler=_command_fmt)

    test = subcommands.add_parser("test", help="discover and run *_test.omni files")
    test.add_argument("path", nargs="?", default="tests", help="test file or directory (default: tests)")
    test.set_defaults(handler=_command_test)

    init = subcommands.add_parser("init", help="create a new OmniScript project")
    init.add_argument("name", help="directory name, or '.' for the current directory")
    init.add_argument("--force", action="store_true", help="write into a non-empty directory")
    init.set_defaults(handler=_command_init)

    tokens = subcommands.add_parser("tokens", help="inspect lexer output")
    tokens.add_argument("file", help="a .omni file")
    tokens.set_defaults(handler=_command_tokens)

    tree = subcommands.add_parser("ast", help="print a program's abstract syntax tree as JSON")
    tree.add_argument("file", help="a .omni file")
    tree.set_defaults(handler=_command_ast)

    doctor = subcommands.add_parser("doctor", help="verify the local OmniScript installation")
    doctor.set_defaults(handler=_command_doctor)

    update = subcommands.add_parser("update", help="check GitHub for a newer OmniScript release")
    update.add_argument("--force", action="store_true", help="ignore the 24-hour update cache")
    update.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    update.add_argument("--clear-cache", action="store_true", help="clear cached update data and exit")
    update.set_defaults(handler=_command_update)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"run", "repl", "check", "fmt", "test", "init", "tokens", "ast", "doctor", "update"}
    # Friendly shorthand: `omni hello.omni` is the same as `omni run hello.omni`.
    if argv and argv[0] not in commands and not argv[0].startswith("-"):
        argv.insert(0, "run")
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if not hasattr(arguments, "handler"):
        parser.print_help()
        return 0
    try:
        return int(arguments.handler(arguments) or 0)
    except OmniError as error:
        print(error.render(color=sys.stderr.isatty()), file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _read(path: str | Path) -> tuple[Path, str]:
    resolved = Path(path).resolve()
    return resolved, resolved.read_text(encoding="utf-8")


def _entry_from_manifest() -> Path:
    manifest = Path("omni.toml")
    if not manifest.exists():
        raise OmniRuntimeError("no program was given and omni.toml was not found")
    source = manifest.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        entry = _legacy_manifest_entry(source)
    else:
        try:
            entry = tomllib.loads(source)["project"]["entry"]
        except (KeyError, ValueError) as error:
            raise OmniRuntimeError("omni.toml needs a [project] entry value") from error
    return Path(str(entry))


def _legacy_manifest_entry(source: str) -> str:
    """Read the one required manifest key on dependency-free Python 3.10."""
    section = ""
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section == "project" and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key == "entry" and len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                return value[1:-1]
    raise OmniRuntimeError("omni.toml needs a quoted [project] entry value")


def _command_run(arguments: argparse.Namespace) -> int:
    path = Path(arguments.file) if arguments.file else _entry_from_manifest()
    resolved, source = _read(path)
    engine = OmniEngine(output=print)
    environment = engine.interpreter.new_environment()
    environment.define("args", [arg for arg in arguments.args if arg != "--"], False)
    engine.run(source, str(resolved), check=not arguments.no_check, environment=environment)
    return 0


def _command_check(arguments: argparse.Namespace) -> int:
    error_count = 0
    for raw_path in arguments.files:
        try:
            path, source = _read(raw_path)
            program = Parser(Lexer(source, str(path)).scan()).parse()
            errors = check_program(program)
            if errors:
                error_count += len(errors)
                for error in errors:
                    print(error.render(), file=sys.stderr)
            else:
                print(f"ok  {path}")
        except OmniError as error:
            error_count += 1
            print(error.render(), file=sys.stderr)
    if error_count:
        print(f"{error_count} problem(s) found", file=sys.stderr)
        return 1
    return 0


def _command_fmt(arguments: argparse.Namespace) -> int:
    changed: list[Path] = []
    for raw_path in arguments.files:
        path, source = _read(raw_path)
        # Never rewrite a file that the parser cannot understand.
        Parser(Lexer(source, str(path)).scan()).parse()
        formatted = format_source(source)
        if formatted != source:
            changed.append(path)
            if not arguments.check:
                path.write_text(formatted, encoding="utf-8")
                print(f"formatted {path}")
    if arguments.check and changed:
        for path in changed:
            print(f"needs formatting: {path}", file=sys.stderr)
        return 1
    if not changed:
        print("already formatted")
    return 0


def _command_test(arguments: argparse.Namespace) -> int:
    root = Path(arguments.path)
    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = sorted(root.rglob("*_test.omni"))
    else:
        print(f"error: test path does not exist: {root}", file=sys.stderr)
        return 1
    if not files:
        print(f"no *_test.omni files found under {root}")
        return 0
    failures = 0
    started = time.perf_counter()
    for path in files:
        output: list[str] = []
        engine = OmniEngine(output=output.append)
        try:
            engine.run_file(path)
            print(f"PASS {path}")
        except (OmniError, OSError) as error:
            failures += 1
            print(f"FAIL {path}")
            if isinstance(error, OmniError):
                print(error.render(), file=sys.stderr)
            else:
                print(f"error: {error}", file=sys.stderr)
            if output:
                print("captured output:", file=sys.stderr)
                for line in output:
                    print(f"  {line}", file=sys.stderr)
    duration = time.perf_counter() - started
    print(f"\n{len(files) - failures} passed, {failures} failed in {duration:.3f}s")
    return 1 if failures else 0


def _command_init(arguments: argparse.Namespace) -> int:
    target = Path.cwd() if arguments.name == "." else Path(arguments.name)
    if target.exists() and any(target.iterdir()) and not arguments.force:
        raise OmniRuntimeError(
            f"directory '{target}' is not empty",
            hint="choose another name or pass --force to add project files",
        )
    target.mkdir(parents=True, exist_ok=True)
    (target / "src").mkdir(exist_ok=True)
    (target / "tests").mkdir(exist_ok=True)
    project_name = target.resolve().name
    files = {
        "omni.toml": (
            f'[project]\nname = "{project_name}"\nversion = "0.1.0"\nentry = "src/main.omni"\n'
        ),
        "src/main.omni": (
            '# Welcome to OmniScript.\n'
            'craft greet(name) {\n'
            '    return "Hello, " + name + "!"\n'
            '}\n\n'
            'emit greet("Omni")\n'
        ),
        "tests/main_test.omni": (
            'craft double(value) {\n'
            '    return value * 2\n'
            '}\n\n'
            'assert double(21) == 42, "double should multiply by two"\n'
        ),
        ".gitignore": "*.pyc\n.omni-cache/\n",
    }
    for relative, content in files.items():
        path = target / relative
        if not path.exists() or arguments.force:
            path.write_text(content, encoding="utf-8")
    print(f"created OmniScript project in {target.resolve()}")
    print(f"next: cd {target} && omni run")
    return 0


def _command_tokens(arguments: argparse.Namespace) -> int:
    path, source = _read(arguments.file)
    for token in Lexer(source, str(path)).scan():
        literal = "" if token.literal is None else f" {token.literal!r}"
        print(f"{token.span.line:>4}:{token.span.column:<3} {token.kind.name:<16} {token.lexeme!r}{literal}")
    return 0


def _command_ast(arguments: argparse.Namespace) -> int:
    path, source = _read(arguments.file)
    program = Parser(Lexer(source, str(path)).scan()).parse()
    print(json.dumps(_jsonable(program), indent=2, ensure_ascii=False))
    return 0


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        result = {"node": type(value).__name__}
        for field in dataclasses.fields(value):
            result[field.name] = _jsonable(getattr(value, field.name))
        return result
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _command_update(arguments: argparse.Namespace) -> int:
    if arguments.clear_cache:
        removed = clear_update_cache()
        print("update cache cleared" if removed else "update cache is already empty")
        return 0
    try:
        info = check_for_updates(__version__, force=arguments.force)
    except UpdateCheckError as error:
        raise OmniRuntimeError(str(error)) from error
    if arguments.as_json:
        print(json.dumps(info.to_dict(), indent=2, sort_keys=True))
    elif not info.release_found:
        source = "cached result" if info.from_cache else "GitHub"
        print(f"no published OmniScript release is available yet ({source})")
        print(info.release_url)
    elif info.update_available:
        source = "cached result" if info.from_cache else "GitHub"
        print(f"update available: OmniScript {info.current_version} -> {info.latest_version} ({source})")
        print(info.release_url)
    else:
        source = "cached result" if info.from_cache else "GitHub"
        print(f"OmniScript {info.current_version} is up to date ({source})")
    return 0


def _command_doctor(_arguments: argparse.Namespace) -> int:
    checks = [
        ("OmniScript", __version__),
        ("Python", sys.version.split()[0]),
        ("Executable", sys.executable),
        ("Working directory", os.getcwd()),
        ("Update cache", str(cache_directory())),
    ]
    for label, value in checks:
        print(f"ok  {label}: {value}")
    sample = "seal answer := 6 * 7\nassert answer == 42\n"
    OmniEngine().run(sample, "<doctor>")
    print("ok  lexer, parser, checker, and runtime")
    return 0


def _command_repl(_arguments: argparse.Namespace) -> int:
    print(f"OmniScript {__version__} — type .help for help, .exit to leave")
    engine = OmniEngine(output=print)
    environment = engine.interpreter.new_environment()
    buffer: list[str] = []
    while True:
        try:
            line = input("... " if buffer else ">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not buffer and line.strip().startswith("."):
            command = line.strip()
            if command in (".exit", ".quit"):
                return 0
            if command == ".help":
                print("Enter declarations, statements, or expressions. Commands: .help .vars .exit")
            elif command == ".vars":
                names = sorted(name for name in environment.bindings if not name.startswith("_"))
                print(", ".join(names) if names else "(no user names)")
            else:
                print(f"unknown REPL command: {command}")
            continue
        buffer.append(line)
        source = "\n".join(buffer)
        try:
            # Brace balance gives multiline blocks a natural editing experience.
            if _brace_balance(source) > 0:
                continue
            result = engine.run(source, "<repl>", check=False, environment=environment)
            if result.value is not None and not source.lstrip().startswith(("emit ", "bind ", "seal ", "craft ", "shape ")):
                print(f"=> {stringify(result.value)}")
        except OmniError as error:
            print(error.render(), file=sys.stderr)
        finally:
            buffer.clear()


def _brace_balance(source: str) -> int:
    # The lexer is the authority when the input is complete; this only decides
    # whether the REPL should display a continuation prompt.
    balance = 0
    quote: str | None = None
    escaped = False
    for char in source:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "{":
            balance += 1
        elif char == "}":
            balance -= 1
    return balance
