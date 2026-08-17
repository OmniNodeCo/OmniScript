"""Token definitions for the OmniScript lexical grammar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from .errors import Span


class TokenKind(Enum):
    EOF = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()

    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    COMMA = auto()
    DOT = auto()
    COLON = auto()
    SEMICOLON = auto()
    QUESTION = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    POWER = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    ASSIGN = auto()       # <-
    DECLARE = auto()      # :=
    RANGE = auto()        # ..
    PIPE = auto()         # |>
    COALESCE = auto()     # ??
    AND = auto()
    OR = auto()
    NOT = auto()

    BIND = auto()
    SEAL = auto()
    CRAFT = auto()
    SHAPE = auto()
    RETURN = auto()
    WHEN = auto()
    OTHERWISE = auto()
    WHILST = auto()
    EACH = auto()
    IN = auto()
    BREAK = auto()
    CONTINUE = auto()
    TRUE = auto()
    FALSE = auto()
    VOID = auto()
    EMIT = auto()
    ASSERT = auto()
    USE = auto()
    AS = auto()


KEYWORDS = {
    "bind": TokenKind.BIND,
    "seal": TokenKind.SEAL,
    "craft": TokenKind.CRAFT,
    "shape": TokenKind.SHAPE,
    "return": TokenKind.RETURN,
    "when": TokenKind.WHEN,
    "otherwise": TokenKind.OTHERWISE,
    "whilst": TokenKind.WHILST,
    "each": TokenKind.EACH,
    "in": TokenKind.IN,
    "break": TokenKind.BREAK,
    "continue": TokenKind.CONTINUE,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
    "void": TokenKind.VOID,
    "emit": TokenKind.EMIT,
    "assert": TokenKind.ASSERT,
    "use": TokenKind.USE,
    "as": TokenKind.AS,
    "and": TokenKind.AND,
    "or": TokenKind.OR,
    "not": TokenKind.NOT,
}


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    lexeme: str
    literal: Any
    span: Span
