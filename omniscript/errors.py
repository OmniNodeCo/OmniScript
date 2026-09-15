"""OmniScript error types.

Every error knows how to print itself with a source snippet and a caret,
which is the single most important usability feature a language can have.
"""

from __future__ import annotations

import difflib


class OmniError(Exception):
    """Base class for everything OmniScript raises at the user."""

    kind = "error"

    def __init__(self, message: str, line: int | None = None, col: int | None = None,
                 hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.hint = hint
        self.source: str | None = None
        self.path: str | None = None
        self.trace: list[tuple[str, int | None]] = []

    # -- rendering ---------------------------------------------------------
    def render(self) -> str:
        parts = []
        where = ""
        if self.path:
            where += f"{self.path}"
        if self.line is not None:
            where += f":{self.line}"
            if self.col is not None:
                where += f":{self.col}"
        head = f"omni: {self.kind}: {self.message}"
        if where:
            head += f"\n  --> {where}"
        parts.append(head)

        if self.source and self.line is not None:
            lines = self.source.splitlines()
            if 1 <= self.line <= len(lines):
                text = lines[self.line - 1]
                gutter = f"{self.line} | "
                parts.append(f"  {gutter}{text}")
                if self.col is not None and 1 <= self.col <= len(text) + 1:
                    parts.append("  " + " " * len(gutter) + " " * (self.col - 1) + "^")

        if self.trace:
            parts.append("  call stack:")
            for name, line in self.trace[-8:]:
                parts.append(f"    in {name}()" + (f" at line {line}" if line else ""))

        if self.hint:
            parts.append(f"  hint: {self.hint}")
        return "\n".join(parts)


class OmniSyntaxError(OmniError):
    kind = "syntax error"


class OmniLexError(OmniError):
    kind = "lex error"


class OmniRuntimeError(OmniError):
    kind = "runtime error"


class OmniTypeError(OmniError):
    kind = "type error"


class OmniNameError(OmniError):
    kind = "name error"


class OmniThrow(OmniError):
    """A value thrown by user code via `throw`."""

    kind = "uncaught throw"

    def __init__(self, value, line=None, col=None):
        super().__init__(describe(value), line, col)
        self.value = value


class OmniReturn(Exception):
    def __init__(self, value):
        super().__init__("return outside function")
        self.value = value


class OmniBreak(Exception):
    pass


class OmniContinue(Exception):
    pass


def describe(value) -> str:
    """Human readable one-line description of an OmniScript value."""
    from .values import (HostObject, NativeFunction, OmniClass, OmniFunction,
                       OmniObject)

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e16:
        return str(int(value))
    if isinstance(value, (int, float, str)):
        return repr(value) if isinstance(value, str) else str(value)
    if isinstance(value, list):
        inner = ", ".join(describe(v) for v in value[:8])
        if len(value) > 8:
            inner += ", ..."
        return f"[{inner}]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k}: {describe(v)}" for k, v in list(value.items())[:8])
        if len(value) > 8:
            inner += ", ..."
        return f"{{{inner}}}"
    if isinstance(value, OmniFunction):
        return f"<fn {value.name}>"
    if isinstance(value, NativeFunction):
        return f"<fn {value.name}>"
    if isinstance(value, OmniClass):
        return f"<class {value.name}>"
    if isinstance(value, OmniObject):
        return f"<{value.klass.name}>"
    return f"<{type(value).__name__}>"


def suggest(name: str, known) -> str | None:
    """Return a 'did you mean' hint for an unknown identifier."""
    matches = difflib.get_close_matches(name, list(known), n=1, cutoff=0.58)
    return f"did you mean `{matches[0]}`?" if matches else None
