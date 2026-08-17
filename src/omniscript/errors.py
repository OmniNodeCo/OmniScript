"""Source locations and user-facing diagnostics for OmniScript."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    source: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None
    line_text: str = ""

    @classmethod
    def synthetic(cls, source: str = "<runtime>") -> "Span":
        return cls(source, 1, 1, 1, 1, "")


class OmniError(Exception):
    """Base class for errors that should be shown without a Python traceback."""

    label = "error"

    def __init__(self, message: str, span: Span | None = None, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.span = span
        self.hint = hint
        self.frames: list[tuple[str, Span]] = []

    def add_frame(self, name: str, span: Span) -> None:
        self.frames.append((name, span))

    def render(self, color: bool = False) -> str:
        # Deliberately color-free by default so diagnostics remain useful in logs and tests.
        head = f"{self.label}: {self.message}"
        if self.span is None:
            lines = [head]
        else:
            span = self.span
            lines = [head, f" --> {span.source}:{span.line}:{span.column}"]
            if span.line_text:
                gutter = str(span.line)
                width = len(gutter)
                marker_width = max(1, (span.end_column or span.column + 1) - span.column)
                lines.extend(
                    [
                        f"{' ' * width} |",
                        f"{gutter} | {span.line_text}",
                        f"{' ' * width} | {' ' * (span.column - 1)}{'^' * marker_width}",
                    ]
                )
        for name, location in reversed(self.frames):
            lines.append(f"  at {name} ({location.source}:{location.line}:{location.column})")
        if self.hint:
            lines.append(f"hint: {self.hint}")
        return "\n".join(lines)


class OmniSyntaxError(OmniError):
    label = "syntax error"


class OmniCheckError(OmniError):
    label = "check error"


class OmniRuntimeError(OmniError):
    label = "runtime error"
