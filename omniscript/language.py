"""The whole language: a lexer, a parser, and an interpreter.

    import math
    from math import sqrt

    draw(window(640, 400, "Demo"),
         rect(0, 0, 640, 60, "#161b22"),
         text(20, 20, "Hello, OmniScript"),
         button(20, 300, 140, 36, "List files", cmd("ls -la")),
         save("hello.png"))

    draw_gui.window_size(640, 400, "Demo")
    draw_gui.button(pos=(20, 300), text="List files", action=cmd("ls -la"))
    draw_gui()

    cmd("tree /f")
    cmd(background, "python3 -m http.server 8000")

    file(create, "notes.txt", "first line\\nsecond line\\n")
    file(edit, "notes.txt", "first", "FIRST")
    file(delete, "notes.txt")

    python("print(sqrt(144))")

The grammar, in full:

    program     := statement*
    statement   := import_stmt | from_stmt | call
    import_stmt := "import" module ["as" NAME] ("," module ["as" NAME])*
    from_stmt   := "from" module "import" ("*" | NAME ["as" NAME] ("," ...)*)
    call        := NAME "(" [argument ("," argument)* [","]] ")"
    argument    := kwarg | value
    kwarg       := NAME "=" value
    value       := NUMBER | STRING | NAME | call | "(" [value ("," value)* [","]] ")"

There are no variables, no loops and nothing to define. A bare name is a *word*
-- `create`, `background`, `red` -- and a word is worth exactly its own name,
which is how an action or a colour reaches a command without quotes around it.
A `NAME=...` pair inside a call is a keyword argument, and `(20, 30)` in value
position is a pair of values, which is how `pos=(20, 30)` reaches a button.
"""

from __future__ import annotations

import importlib
import io
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field

from .draw import (DEFAULT_BACKGROUND, DEFAULT_HEIGHT, DEFAULT_TITLE,
                   DEFAULT_WIDTH, DrawError, Element, render)

COMMANDS = ("draw", "draw_gui", "cmd", "file", "python")
DRAW_GUI_COMMANDS = ("draw_gui.button", "draw_gui.window_size")
ALL_COMMANDS = COMMANDS + DRAW_GUI_COMMANDS
ELEMENTS = ("window", "window_size", "rect", "circle", "line", "text",
            "button", "save")
FILE_ACTIONS = ("create", "edit", "delete")

# Triple-quoted strings first, so a block of Python can be handed to python()
# with its newlines intact.
TOKEN = re.compile(r'''
    (?P<space>[ \t\r\n\f\v]+)
  | (?P<comment>\#[^\n]*)
  | (?P<number>-?\d+\.\d*|-?\.\d+|-?\d+)
  | (?P<string>"""(?:[^\\]|\\.)*?"""|"(?:[^"\\\n]|\\.)*")
  | (?P<name>[A-Za-z_][A-Za-z_0-9_.\-]*)
  | (?P<punct>[(),=*])
''', re.VERBOSE)

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}

# Every element's positional slots, plus the other spellings each slot answers
# to. `pos=(x, y)` and `size=(w, h)` are handled separately, below.
SLOTS = {
    "window": (["width", "height", "title", "background"],
               {"w": "width", "h": "height", "name": "title",
                "bg": "background", "color": "background", "colour": "background"}),
    "window_size": (["width", "height", "title", "background"],
                    {"w": "width", "h": "height", "name": "title",
                     "bg": "background", "color": "background", "colour": "background"}),
    "rect": (["x", "y", "width", "height", "color"],
             {"w": "width", "h": "height", "bg": "color", "colour": "color",
              "fill": "color"}),
    "circle": (["x", "y", "radius", "color"],
               {"r": "radius", "bg": "color", "colour": "color", "fill": "color"}),
    "line": (["x1", "y1", "x2", "y2", "color", "width"],
             {"colour": "color", "w": "width", "thickness": "width"}),
    "text": (["x", "y", "message", "color", "size"],
             {"text": "message", "msg": "message", "string": "message",
              "content": "message", "colour": "color", "font_size": "size"}),
    "button": (["x", "y", "width", "height", "label"],
               {"w": "width", "h": "height", "text": "label", "title": "label",
                "caption": "label", "name": "label"}),
    "save": (["path"],
             {"file": "path", "filename": "path", "to": "path", "name": "path"}),
}

# What a button's command answers to when it is written as a keyword.
ACTION_KEYS = ("action", "command", "on_click", "do")

# Which elements understand the pair shorthands: pos=(x, y), size=(w, h),
# from=(x1, y1), to=(x2, y2). A text's `size=` is its font size, not a pair,
# so text is deliberately missing from size's list.
PAIR_KINDS = {"pos": ("rect", "circle", "text", "button"),
              "size": ("rect", "button", "window", "window_size"),
              "from": ("line",), "to": ("line",)}

ELEMENT_LIST = ", ".join(kind + "()" for kind in ELEMENTS)


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
    kind: str                       # import | fromimport | call | number |
                                    # string | word | tuple | kwarg
    value: object = None            # import: [(module, alias), ...]
                                    # fromimport: (module, [(name, alias), ...])
                                    # call/word: the name; kwarg: the key
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

    def fail_node(self, message: str, node: Node) -> OmniScriptError:
        return OmniScriptError(message, node.line, node.column,
                               _line_text(self.source, node.line), self.name)

    def expect(self, kind: str, what: str) -> Token:
        token = self.peek()
        if token.kind != kind:
            raise self.fail(f"expected {what}" + (
                f", found '{token.value}'" if token.value else ", found the end"))
        return self.take()

    def _next_is(self, kind: str, value: str) -> bool:
        if self.index + 1 >= len(self.tokens):
            return False
        token = self.tokens[self.index + 1]
        return token.kind == kind and token.value == value

    # -- the grammar
    def parse(self) -> list:
        statements = []
        while self.peek().kind != "end":
            statements.append(self.statement())
        return statements

    def statement(self) -> Node:
        token = self.peek()
        if token.kind == "name" and token.value == "import":
            return self.import_statement()
        if token.kind == "name" and token.value == "from":
            return self.from_statement()
        return self.call()

    def import_statement(self) -> Node:
        keyword = self.take()                      # import
        modules = []
        while True:
            module = self.expect("name", "something to import")
            alias = module.value.split(".")[0]
            if self.peek().kind == "name" and self.peek().value == "as":
                self.take()
                alias = self.expect("name", "a name after 'as'").value
            modules.append((module.value, alias))
            if self.peek().value == ",":
                self.take()
                continue
            break
        return Node("import", modules, [], keyword.line, keyword.column)

    def from_statement(self) -> Node:
        keyword = self.take()                      # from
        base = self.expect("name", "a module after 'from'")
        third = self.peek()
        if third.kind != "name" or third.value != "import":
            raise self.fail("expected 'import' after 'from "
                            + base.value + "'", third)
        self.take()
        parenthesized = self.peek().value == "("
        if parenthesized:
            self.take()
        names = []
        if self.peek().kind == "punct" and self.peek().value == "*":
            self.take()
            names.append(("*", "*"))
        else:
            while True:
                found = self.expect("name", "something to import")
                alias = found.value
                if self.peek().kind == "name" and self.peek().value == "as":
                    self.take()
                    alias = self.expect("name", "a name after 'as'").value
                names.append((found.value, alias))
                if self.peek().value == ",":
                    self.take()
                    if parenthesized and self.peek().value == ")":
                        break
                    continue
                break
        if parenthesized:
            closing = self.peek()
            if closing.value != ")":
                raise self.fail("'(' after import is never closed", closing)
            self.take()
        return Node("fromimport", (base.value, names), [], keyword.line,
                    keyword.column)

    def call(self) -> Node:
        name = self.expect("name", "a command")
        opener = self.expect("punct", "'(' after " + name.value)
        if opener.value != "(":
            raise self.fail(f"expected '(' after {name.value}", opener)
        args = []
        if self.peek().value != ")":
            args.append(self.argument())
            while self.peek().value == ",":
                self.take()
                if self.peek().value == ")":
                    break                            # a trailing comma is fine
                args.append(self.argument())
        closing = self.peek()
        if closing.value != ")":
            raise self.fail(f"'(' after {name.value} is never closed", closing)
        self.take()
        return Node("call", name.value, args, name.line, name.column)

    def argument(self) -> Node:
        token = self.peek()
        if token.kind == "punct" and token.value == "(":
            return self.group()
        if token.kind == "number":
            self.take()
            value = float(token.value) if "." in token.value else int(token.value)
            return Node("number", value, [], token.line, token.column)
        if token.kind == "string":
            self.take()
            return Node("string", _unquote(token.value), [], token.line, token.column)
        if token.kind == "name":
            if self._next_is("punct", "="):
                key = self.take()
                self.take()                          # =
                value = self.argument()
                if value.kind == "kwarg":
                    raise self.fail("a keyword value cannot be another keyword",
                                    self.tokens[self.index - 1])
                return Node("kwarg", key.value, [value], key.line, key.column)
            self.take()
            if self.peek().value == "(":
                self.index -= 1
                return self.call()
            return Node("word", token.value, [], token.line, token.column)
        raise self.fail("expected a number, a string, a word or a command")

    def group(self) -> Node:
        """`(20, 30)` in value position: a pair (or trio, or more) of values."""
        opener = self.take()                       # (
        if self.peek().value == ")":
            self.take()
            return Node("tuple", None, [], opener.line, opener.column)
        elements = [self.argument()]
        commas = 0
        while self.peek().value == ",":
            self.take()
            commas += 1
            if self.peek().value == ")":
                break
            elements.append(self.argument())
        closing = self.peek()
        if closing.value != ")":
            raise self.fail("this '(' is never closed", closing)
        self.take()
        for element in elements:
            if element.kind == "kwarg":
                raise self.fail_node("a keyword cannot go inside (...)", element)
        if len(elements) == 1 and not commas:
            return elements[0]                     # (5) is just grouping
        return Node("tuple", None, elements, opener.line, opener.column)


# ---------------------------------------------------------------- interpreter
class Interpreter:
    """Runs statements, and says what each one did."""

    def __init__(self, writer=None, cwd: str | None = None):
        self.out = writer or sys.stdout.write
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.imported: set = set()
        self.py_modules: dict = {}
        self.background: list = []
        self.gui = {"width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT,
                    "title": DEFAULT_TITLE, "background": DEFAULT_BACKGROUND,
                    "buttons": []}
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
            return self.do_import(node)
        if node.kind == "fromimport":
            return self.do_fromimport(node)
        return self.command(node)

    # ---------------------------------------------------------------- imports
    def do_import(self, node: Node) -> None:
        for fullname, alias in node.value:
            if fullname == "python":
                self.imported.add("python")
                continue
            try:
                self.py_modules[alias] = importlib.import_module(fullname)
            except ImportError as err:
                raise self.error(f"could not import '{fullname}': {err}", node) from err
            except ValueError as err:
                raise self.error(f"could not import '{fullname}': {err}", node) from err
            self.imported.add(fullname)
        return None

    def do_fromimport(self, node: Node) -> None:
        base, names = node.value
        if base == "python":
            raise self.error("there is no module called python to import from -- "
                             "write `import python` to enable python()", node)
        try:
            module = importlib.import_module(base)
        except ImportError as err:
            raise self.error(f"could not import from '{base}': {err}", node) from err
        except ValueError as err:
            raise self.error(f"could not import from '{base}': {err}", node) from err
        for original, alias in names:
            if original == "*":
                allowed = getattr(module, "__all__", None)
                if allowed is None:
                    allowed = [key for key in vars(module) if not key.startswith("_")]
                for key in allowed:
                    if hasattr(module, key):
                        self.py_modules[key] = getattr(module, key)
                self.imported.add(base + ".*")
                continue
            if not hasattr(module, original):
                raise self.error(f"'{base}' has no '{original}' to import", node)
            self.py_modules[alias] = getattr(module, original)
            self.imported.add(f"{base}.{original}")
        return None

    # --------------------------------------------------------------- commands
    def command(self, node: Node) -> object:
        name = str(node.value)
        if name == "draw":
            return self.do_draw(node)
        if name == "draw_gui":
            return self.do_draw_gui(node)
        if name == "draw_gui.button":
            return self.do_gui_button(node)
        if name == "draw_gui.window_size":
            return self.do_gui_window_size(node)
        if name not in COMMANDS:
            if name in ELEMENTS:
                raise self.error(f"{name}() only belongs inside draw() or draw_gui()",
                                 node)
            if name.startswith("draw_gui."):
                extra = name.split(".", 1)[1]
                raise self.error(f"draw_gui has no '.{extra}' -- it has .button and "
                                 ".window_size", node)
            raise self.error(
                f"there is no command called {name} -- OmniScript has "
                f"{', '.join(ALL_COMMANDS)}", node)
        pos, kwargs = self.call_args(node)
        if name == "cmd":
            return self.do_cmd(pos, node, kwargs)
        if name == "file":
            return self.do_file(pos, node, kwargs)
        return self.do_python(pos, node, kwargs)

    def call_args(self, node: Node) -> tuple:
        """A call's arguments, evaluated, split into positional and keyword."""
        pos: list = []
        kwargs: dict = {}
        for argument in node.args:
            if argument.kind == "kwarg":
                key = str(argument.value)
                if key in kwargs:
                    raise self.error(f"{node.value}() got '{key}=' twice", argument)
                kwargs[key] = self.value(argument.args[0])
            else:
                if kwargs:
                    raise self.error(f"{node.value}() has a positional argument "
                                     "after a keyword one", argument)
                pos.append(self.value(argument))
        return pos, kwargs

    def value(self, node: Node) -> object:
        if node.kind in ("number", "string", "word"):
            return node.value
        if node.kind == "tuple":
            return tuple(self.value(element) for element in node.args)
        if node.kind == "kwarg":
            return self.value(node.args[0])
        return self.command(node)

    # ------------------------------------------------------------------- cmd
    def do_cmd(self, args: list, node: Node, kwargs: dict | None = None) -> int:
        if kwargs:
            raise self.error("cmd() takes no 'name=' arguments -- write "
                             'cmd("...") or cmd(background, "...")', node)
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

    def do_file(self, args: list, node: Node, kwargs: dict | None = None) -> str:
        if kwargs:
            raise self.error("file() takes no 'name=' arguments -- write "
                             'file(create, "a.txt", "hi")', node)
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
    def do_python(self, args: list, node: Node, kwargs: dict | None = None) -> object:
        if kwargs:
            raise self.error('python() takes no \'name=\' arguments -- write '
                             'python("print(1)")', node)
        if not self.imported:
            raise self.error("python() needs `import python` (or any import, like "
                             "`import math`) at the top of the file", node)
        if not args:
            raise self.error('python() needs code to run, like python("print(1)")', node)
        code = str(args[0])
        namespace = {"__name__": "__omniscript__", "__file__": "<python>",
                     **self.py_modules}
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
        return self.render_elements(elements, node)

    def render_elements(self, elements: list, node: Node) -> object:
        try:
            return render(elements, cwd=self.cwd, say=self.say, on_click=self.click)
        except DrawError as err:
            line = err.line or node.line
            raise OmniScriptError(err.message, line, node.column,
                                  _line_text(self.source, line), self.name) from err

    def element(self, node: Node) -> Element:
        if node.kind != "call":
            raise self.error(
                f"draw() and draw_gui() take elements: {ELEMENT_LIST}", node)
        kind = str(node.value)
        if kind in DRAW_GUI_COMMANDS:
            short = kind.split(".", 1)[1]
            raise self.error(f"{kind}(...) is a command -- inside draw() write "
                             f"{short}(...) without the prefix", node)
        if kind not in ELEMENTS:
            if kind in COMMANDS:
                raise self.error(
                    f"{kind}() is a command, not something draw() can place", node)
            raise self.error(
                f"draw() has no element called {kind} -- it has {', '.join(ELEMENTS)}",
                node)
        args, action = self.element_args(kind, node)
        if kind == "window_size":
            kind = "window"          # a window by another name paints the same
        return Element(kind, args, action, node.line)

    def element_args(self, kind: str, node: Node) -> tuple:
        """An element's arguments, with keywords resolved onto slots.

        A button's command -- positional or `action=` -- is kept as it was
        written and run when clicked, not now.
        """
        pos: list = []
        kwargs: dict = {}
        action = None
        last = len(node.args) - 1
        for position, argument in enumerate(node.args):
            if argument.kind == "kwarg":
                key = str(argument.value)
                if key.lower() in ACTION_KEYS and kind == "button":
                    key = "action"
                if key in kwargs or (key == "action" and action is not None):
                    raise self.error(f"{kind}() got '{argument.value}=' twice",
                                     argument)
                if key == "action":
                    if argument.args[0].kind != "call":
                        raise self.error("a button's action has to be a command, "
                                         'like action=cmd("ls")', argument)
                    action = argument.args[0]
                else:
                    if key in kwargs:
                        raise self.error(f"{kind}() got '{key}=' twice", argument)
                    kwargs[key] = self.value(argument.args[0])
            else:
                if kwargs or action is not None:
                    raise self.error(f"{kind}() has a positional argument after "
                                     "a keyword one", argument)
                if kind == "button" and position == last \
                        and argument.kind == "call":
                    action = argument
                else:
                    pos.append(self.value(argument))
        return self.resolve_kwargs(kind, pos, kwargs, node), action

    def resolve_kwargs(self, kind: str, pos: list, kwargs: dict,
                       node: Node) -> list:
        slots, aliases = SLOTS[kind]
        where = {slot: index for index, slot in enumerate(slots)}
        args: list = list(pos)

        def place(slot: str, value: object, written: str) -> None:
            index = where[slot]
            if index < len(args):
                raise self.error(f"{kind}() got '{slot}' twice (positionally and "
                                 f"as {written})", node)
            while len(args) < index:
                args.append(None)
            args.append(value)

        # pos=(x, y), size=(w, h), from=(x1, y1), to=(x2, y2) -- pairs first,
        # so a duplicate with a plain keyword reads as the plain one winning.
        pairs = {}
        for key in ("pos", "size", "from", "to"):
            if kind not in PAIR_KINDS[key]:
                continue
            for written in list(kwargs):
                if written.lower() == key:
                    pairs[key] = self.pair(kwargs.pop(written), f"{kind}'s {key}",
                                           node)
        if pairs:
            self.place_pairs(kind, args, pairs, place, node)

        for written, val in kwargs.items():
            slot = aliases.get(written.lower(), written.lower())
            if slot not in where:
                known = list(slots)
                known += [key for key in ("pos", "size", "from", "to")
                          if kind in PAIR_KINDS[key]]
                if kind == "button":
                    known.append("action")
                known = ", ".join(known)
                raise self.error(f"{kind}() has no '{written}=' -- it has {known}",
                                 node)
            place(slot, val, f"'{written}='")

        if kind in ("window", "window_size"):
            self.unpack_window(args, node)
        while len(args) < len(slots):
            args.append(None)
        if kind == "button" and args[4] is None:
            args[4] = "button"
        if kind == "text" and args[2] is None:
            args[2] = ""
        return args

    def place_pairs(self, kind: str, args: list, pairs: dict, place, node: Node) -> None:
        if kind in ("rect", "circle", "text", "button"):
            if "pos" in pairs:
                (first, second) = pairs.pop("pos")
                place("x", first, "pos=")
                place("y", second, "pos=")
        if kind in ("rect", "button"):
            if "size" in pairs:
                (first, second) = pairs.pop("size")
                place("width", first, "size=")
                place("height", second, "size=")
        if kind in ("window", "window_size"):
            if "size" in pairs:
                (first, second) = pairs.pop("size")
                place("width", first, "size=")
                place("height", second, "size=")
        if kind == "line":
            if "from" in pairs:
                (first, second) = pairs.pop("from")
                place("x1", first, "from=")
                place("y1", second, "from=")
            if "to" in pairs:
                (first, second) = pairs.pop("to")
                place("x2", first, "to=")
                place("y2", second, "to=")
        if pairs:
            leftover = sorted(pairs)[0]
            hint = {"pos": "x= and y= (or from= and to= for a line)",
                    "size": "width= and height=",
                    "from": "x1= and y1=", "to": "x2= and y2="}[leftover]
            raise self.error(f"{kind}() takes no '{leftover}=' -- write {hint}",
                             node)

    def pair(self, value: object, what: str, node: Node) -> tuple:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return (value[0], value[1])
        if isinstance(value, str):
            parts = [part for part in
                     re.split(r"[,\s]+", value.strip().lower().replace("x", ",")) if part]
            if len(parts) == 2:
                return (parts[0], parts[1])
        raise self.error(f"{what} has to be two numbers, like (20, 30)", node)

    def unpack_window(self, args: list, node: Node) -> None:
        """`window_size("800x600")` and `window_size((800, 600))` both fit."""
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            pair = args[0]
            if len(pair) != 2:
                raise self.error("window_size() takes a width and a height, like "
                                 "window_size(800, 600)", node)
            args[:] = [pair[0], pair[1]]
        elif len(args) == 1 and isinstance(args[0], str):
            first, second = self.pair(args[0], "window_size()", node)
            args[:] = [first, second]

    def click(self, node: Node) -> None:
        try:
            self.command(node)
        except OmniScriptError as err:
            self.say(str(err))

    # -------------------------------------------------------------- draw_gui
    def do_gui_window_size(self, node: Node) -> tuple:
        pos: list = []
        kwargs: dict = {}
        for argument in node.args:
            if argument.kind == "kwarg":
                key = str(argument.value)
                if key in kwargs:
                    raise self.error(f"window_size() got '{key}=' twice", argument)
                kwargs[key] = self.value(argument.args[0])
            else:
                if kwargs:
                    raise self.error("window_size() has a positional argument "
                                     "after a keyword one", argument)
                pos.append(self.value(argument))
        args = self.resolve_kwargs("window_size", pos, kwargs, node)
        width = self.whole(args[0], DEFAULT_WIDTH, "the window's width", node)
        height = self.whole(args[1], DEFAULT_HEIGHT, "the window's height", node)
        if width < 1 or height < 1:
            raise self.error(f"a window cannot be {width}x{height}", node)
        title = DEFAULT_TITLE if args[2] in (None, "") else str(args[2])
        background = DEFAULT_BACKGROUND if args[3] in (None, "") else str(args[3])
        from .draw import rgb as _rgb
        try:
            background = "#%02x%02x%02x" % _rgb(background, node.line,
                                                DEFAULT_BACKGROUND)
        except DrawError as err:
            raise self.error(err.message, node) from err
        self.gui.update(width=width, height=height, title=title,
                        background=background)
        self.say(f"window size {width}x{height} \"{title}\"")
        return (width, height)

    def whole(self, value: object, default: int, what: str, node: Node) -> int:
        if value is None or value == "":
            return default
        try:
            return int(float(value))  # noqa: F841 - validated below
        except (TypeError, ValueError):
            raise self.error(f"{what} has to be a number, not '{value}'",
                             node) from None

    def do_gui_button(self, node: Node) -> Element:
        args, action = self.element_args("button", node)
        element = Element("button", args, action, node.line)
        self.gui["buttons"].append(element)
        x = 0 if args[0] in (None, "") else args[0]
        y = 0 if args[1] in (None, "") else args[1]
        try:
            at = f"({int(float(x))}, {int(float(y))})"
        except (TypeError, ValueError):
            at = f"({x}, {y})"
        self.say(f"added button '{args[4]}' at {at}")
        return element

    def do_draw_gui(self, node: Node) -> object:
        explicit = [self.element(argument) for argument in node.args]
        if not any(element.kind == "window" for element in explicit):
            explicit.insert(0, Element(
                "window",
                [self.gui["width"], self.gui["height"], self.gui["title"],
                 self.gui["background"]], None, node.line))
        queued = list(self.gui["buttons"])
        if queued:
            head = 1 if explicit and explicit[0].kind == "window" else 0
            explicit[head:head] = queued
        result = self.render_elements(explicit, node)
        self.gui["buttons"] = []
        return result
