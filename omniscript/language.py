"""The whole language: a lexer, a parser, and an interpreter for four commands.

    import python

    draw(window(640, 400, "Demo"),
         rect(0, 0, 640, 60, "#161b22"),
         text(20, 20, "Hello, OmniScript"),
         button(20, 300, 140, 36, "List files", cmd("ls -la")),
         save("hello.png"))

    cmd("tree /f")
    cmd(background, "python3 -m http.server 8000")

    file(create, "notes.txt", "first line\\nsecond line\\n")
    file(edit, "notes.txt", "first", "FIRST")
    file(delete, "notes.txt")

    python("print(6 * 7)")

The grammar, in full:

    program   := statement*
    statement := "import" NAME | NAME "(" [argument ("," argument)*] ")"
    argument  := NUMBER | STRING | NAME | call

There are no variables, no loops and nothing to define. A bare name is a *word*
-- `create`, `background`, `red` -- and a word is worth exactly its own name,
which is how an action or a colour reaches a command without quotes around it.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field

from .draw import Element, render

COMMANDS = ("draw", "cmd", "file", "python")
ELEMENTS = ("window", "rect", "circle", "line", "text", "button", "save")
FILE_ACTIONS = ("create", "edit", "delete")
IMPORTABLE = ("python",)

# Triple-quoted strings first, so a block of Python can be handed to python()
# with its newlines intact.
TOKEN = re.compile(r'''
    (?P<space>[ \t\r\n\f\v]+)
  | (?P<comment>\#[^\n]*)
  | (?P<number>\d+\.\d*|\.\d+|\d+)
  | (?P<string>"""(?:[^\\]|\\.)*?"""|"(?:[^"\\\n]|\\.)*")
  | (?P<name>[A-Za-z_][A-Za-z_0-9_.\-]*)
  | (?P<punct>[(),])
''', re.VERBOSE)

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}


# --------------------------------------------------------------------- errors
class OmniScriptError(Exception):
    """One message, the line it happened on, and a caret under that line."""

    def __init__(self, message: str, line: int = 0, column: int = 0,
                 text: str = "", name: str = ""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.text = text
        self.name = name

    def __str__(self) -> str:
        if not self.line:
            return self.message
        where = f"{self.name}:{self.line}" if self.name else f"line {self.line}"
        parts = [f"{where}: {self.message}"]
        if self.text:
            parts.append("    " + self.text)
            parts.append("    " + " " * max(0, self.column - 1) + "^")
        return "\n".join(parts)


# --------------------------------------------------------------------- tokens
@dataclass
class Token:
    kind: str          # number | string | name | punct
    value: str
    line: int
    column: int


def tokenize(source: str, name: str = "<input>") -> list:
    tokens: list = []
    position = 0
    line = 1
    column = 1
    while position < len(source):
        match = TOKEN.match(source, position)
        if not match:
            if source[position] == '"':
                raise OmniScriptError("this string has no closing quote", line, column,
                                      _line_text(source, line), name)
            raise OmniScriptError(
                f"cannot read '{source[position]}' here", line, column,
                _line_text(source, line), name)
        kind = match.lastgroup
        text = match.group()
        if kind == "space":
            line += text.count("\n")
            column = len(text) - text.rfind("\n") if "\n" in text else column + len(text)
        elif kind == "comment":
            column += len(text)
        else:
            tokens.append(Token(kind, text, line, column))
            column += len(text)
        position = match.end()
    tokens.append(Token("end", "", line, column))
    return tokens


def _line_text(source: str, line: int) -> str:
    lines = source.split("\n")
    return lines[line - 1] if 0 < line <= len(lines) else ""


def _unquote(text: str) -> str:
    if text.startswith('"""'):
        body = text[3:-3]
    else:
        body = text[1:-1]
    out = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            out.append(ESCAPES.get(body[index + 1], body[index + 1]))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


# ---------------------------------------------------------------------- trees
@dataclass
class Node:
    kind: str                       # import | call | number | string | word
    value: object = None            # the name of a call, or the literal itself
    args: list = field(default_factory=list)
    line: int = 0
    column: int = 0


class Parser:
    def __init__(self, tokens: list, source: str, name: str):
        self.tokens = tokens
        self.source = source
        self.name = name
        self.index = 0

    # -- the small machinery every parser needs
    def peek(self) -> Token:
        return self.tokens[self.index]

    def take(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def fail(self, message: str, token: Token | None = None) -> OmniScriptError:
        token = token or self.peek()
        return OmniScriptError(message, token.line, token.column,
                               _line_text(self.source, token.line), self.name)

    def expect(self, kind: str, what: str) -> Token:
        token = self.peek()
        if token.kind != kind:
            raise self.fail(f"expected {what}" + (
                f", found '{token.value}'" if token.value else ", found the end"))
        return self.take()

    # -- the grammar
    def parse(self) -> list:
        statements = []
        while self.peek().kind != "end":
            statements.append(self.statement())
        return statements

    def statement(self) -> Node:
        token = self.peek()
        if token.kind == "name" and token.value == "import":
            self.take()
            name = self.expect("name", "something to import")
            return Node("import", name.value, [], name.line, name.column)
        return self.call()

    def call(self) -> Node:
        name = self.expect("name", "a command")
        self.expect("punct", "'(' after " + name.value)
        if name.value != "(":
            pass
        args = []
        if self.peek().value != ")":
            args.append(self.argument())
            while self.peek().value == ",":
                self.take()
                args.append(self.argument())
        closing = self.peek()
        if closing.value != ")":
            raise self.fail(f"'(' after {name.value} is never closed", closing)
        self.take()
        return Node("call", name.value, args, name.line, name.column)

    def argument(self) -> Node:
        token = self.peek()
        if token.kind == "number":
            self.take()
            value = float(token.value) if "." in token.value else int(token.value)
            return Node("number", value, [], token.line, token.column)
        if token.kind == "string":
            self.take()
            return Node("string", _unquote(token.value), [], token.line, token.column)
        if token.kind == "name":
            self.take()
            if self.peek().value == "(":
                self.index -= 1
                return self.call()
            return Node("word", token.value, [], token.line, token.column)
        raise self.fail("expected a number, a string, a word or a command")


# ---------------------------------------------------------------- interpreter
class Interpreter:
    """Runs statements, and says what each one did."""

    def __init__(self, writer=None, cwd: str | None = None):
        self.out = writer or sys.stdout.write
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.imported: set = set()
        self.background: list = []
        self.name = "<input>"
        self.source = ""

    # -- output
    def say(self, message: str) -> None:
        self.out(message.rstrip("\n") + "\n")

    def say_text(self, text: str) -> None:
        self.out(text if text.endswith("\n") or not text else text + "\n")

    def error(self, message: str, node: Node) -> OmniScriptError:
        return OmniScriptError(message, node.line, node.column,
                               _line_text(self.source, node.line), self.name)

    # -- running
    def run(self, source: str, name: str = "<input>") -> None:
        self.name = name
        self.source = source
        for statement in Parser(tokenize(source, name), source, name).parse():
            self.statement(statement)

    def statement(self, node: Node) -> object:
        if node.kind == "import":
            if node.value not in IMPORTABLE:
                raise self.error(
                    f"the only import is python, not '{node.value}'", node)
            self.imported.add(str(node.value))
            return None
        return self.command(node)

    def command(self, node: Node) -> object:
        name = str(node.value)
        if name == "draw":
            return self.do_draw(node)
        if name not in COMMANDS:
            if name in ELEMENTS:
                raise self.error(f"{name}() only belongs inside draw()", node)
            raise self.error(
                f"there is no command called {name} -- OmniScript has "
                f"{', '.join(COMMANDS)}", node)
        args = [self.value(argument) for argument in node.args]
        if name == "cmd":
            return self.do_cmd(args, node)
        if name == "file":
            return self.do_file(args, node)
        return self.do_python(args, node)

    def value(self, node: Node) -> object:
        if node.kind in ("number", "string", "word"):
            return node.value
        return self.command(node)

    # ------------------------------------------------------------------- cmd
    def do_cmd(self, args: list, node: Node) -> int:
        if not args:
            raise self.error('cmd() needs a command to run, like cmd("tree /f")', node)
        background = len(args) > 1 and str(args[0]).lower() == "background"
        command = str(args[-1])
        if not command.strip():
            raise self.error("cmd() was given an empty command", node)

        if background:
            detached = {} if os.name == "nt" else {"start_new_session": True}
            try:
                process = subprocess.Popen(          # noqa: S602 - that is the command
                    command, shell=True, cwd=self.cwd, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detached)
            except OSError as err:
                raise self.error(f"could not start '{command}': {err}", node) from err
            self.background.append(process)
            self.say(f"running in the background: {command} (pid {process.pid})")
            return process.pid

        try:
            process = subprocess.run(                # noqa: S602 - that is the command
                command, shell=True, cwd=self.cwd, capture_output=True, text=True)
        except OSError as err:
            raise self.error(f"could not run '{command}': {err}", node) from err
        if process.stdout:
            self.say_text(process.stdout)
        if process.stderr:
            self.say_text(process.stderr)
        if process.returncode:
            self.say(f"the command exited {process.returncode}")
        return process.returncode

    # ------------------------------------------------------------------ file
    def path_of(self, given: str) -> str:
        return given if os.path.isabs(given) else os.path.join(self.cwd, given)

    def do_file(self, args: list, node: Node) -> str:
        if len(args) < 2:
            raise self.error(
                'file() takes an action and a path, like file(create, "a.txt", "hi")',
                node)
        action = str(args[0]).lower()
        path = self.path_of(str(args[1]))
        if action not in FILE_ACTIONS:
            raise self.error("file() does " + ", ".join(FILE_ACTIONS)
                             + f", not '{action}'", node)

        if action == "create":
            text = "" if len(args) < 3 else str(args[2])
            if os.path.exists(path):
                raise self.error(
                    f"{args[1]} is already there -- file(edit, ...) changes it, "
                    "file(delete, ...) removes it", node)
            self._write(path, text, node)
            self.say(f"created {args[1]} ({len(text.encode('utf-8'))} bytes)")
            return path

        if action == "edit":
            if len(args) < 4:
                raise self.error(
                    "file(edit, path, old, new) needs the text to find and the text "
                    "to put there", node)
            old, new = str(args[2]), str(args[3])
            text = self._read(path, node)
            found = text.count(old)
            if not found:
                raise self.error(f"{args[1]} has no '{old}' in it to change", node)
            self._write(path, text.replace(old, new), node)
            self.say(f"edited {args[1]} ({found} place{'s' if found > 1 else ''})")
            return path

        text = self._read(path, node)
        try:
            os.remove(path)
        except OSError as err:
            raise self.error(f"could not delete {args[1]}: {err}", node) from err
        self.say(f"deleted {args[1]} ({len(text.encode('utf-8'))} bytes)")
        return path

    def _read(self, path: str, node: Node) -> str:
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            raise self.error(f"{os.path.basename(path)} is not there", node) from None
        except IsADirectoryError:
            raise self.error(f"{os.path.basename(path)} is a directory", node) from None
        except OSError as err:
            raise self.error(f"could not read {os.path.basename(path)}: {err}",
                             node) from err

    def _write(self, path: str, text: str, node: Node) -> None:
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as err:
            raise self.error(f"could not write {os.path.basename(path)}: {err}",
                             node) from err

    # ---------------------------------------------------------------- python
    def do_python(self, args: list, node: Node) -> object:
        if "python" not in self.imported:
            raise self.error("python() needs `import python` at the top of the file",
                             node)
        if not args:
            raise self.error('python() needs code to run, like python("print(1)")', node)
        code = str(args[0])
        namespace = {"__name__": "__omniscript__", "__file__": "<python>"}
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                try:
                    value = eval(code, namespace)    # noqa: S307 - that is the command
                except SyntaxError:
                    exec(code, namespace)            # noqa: S102 - that is the command
                    value = None
        except OmniScriptError:
            raise
        except BaseException as err:                 # noqa: BLE001 - report and carry on
            raise self.error(
                f"python() raised {err.__class__.__name__}: {err}", node) from err
        if buffer.tell():
            self.say_text(buffer.getvalue())
        if value is not None:
            self.say(repr(value))
        return value

    # ------------------------------------------------------------------ draw
    def do_draw(self, node: Node) -> object:
        if not node.args:
            raise self.error(
                'draw() needs something to draw, like draw(window(200, 100, "Hi"))',
                node)
        elements = [self.element(argument) for argument in node.args]
        return render(elements, cwd=self.cwd, say=self.say, on_click=self.click)

    def element(self, node: Node) -> Element:
        if node.kind != "call":
            raise self.error(
                "draw() takes elements: window(), rect(), circle(), line(), text(), "
                "button(), save()", node)
        kind = str(node.value)
        if kind not in ELEMENTS:
            if kind in COMMANDS:
                raise self.error(
                    f"{kind}() is a command, not something draw() can place", node)
            raise self.error(
                f"draw() has no element called {kind} -- it has {', '.join(ELEMENTS)}",
                node)
        args = []
        last = len(node.args) - 1
        action = None
        for position, argument in enumerate(node.args):
            # A button's last argument is what it does when it is clicked, so it
            # is kept as it was written and run later, not now.
            if kind == "button" and position == last and argument.kind == "call":
                action = argument
            else:
                args.append(self.value(argument))
        return Element(kind, args, action, node.line)

    def click(self, node: Node) -> None:
        try:
            self.command(node)
        except OmniScriptError as err:
            self.say(str(err))
