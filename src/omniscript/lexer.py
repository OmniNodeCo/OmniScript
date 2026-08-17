"""A dependency-free lexer for `.omni` source files."""

from __future__ import annotations

from .errors import OmniSyntaxError, Span
from .tokens import KEYWORDS, Token, TokenKind


class Lexer:
    def __init__(self, source: str, source_name: str = "<memory>"):
        self.source = source
        self.source_name = source_name
        self.lines = source.splitlines()
        self.start = 0
        self.current = 0
        self.line = 1
        self.column = 1
        self.start_line = 1
        self.start_column = 1
        self.tokens: list[Token] = []

    def scan(self) -> list[Token]:
        while not self._at_end():
            self.start = self.current
            self.start_line = self.line
            self.start_column = self.column
            self._scan_token()
        self.tokens.append(Token(TokenKind.EOF, "", None, self._span()))
        return self.tokens

    def _scan_token(self) -> None:
        c = self._advance()
        single = {
            "(": TokenKind.LEFT_PAREN,
            ")": TokenKind.RIGHT_PAREN,
            "{": TokenKind.LEFT_BRACE,
            "}": TokenKind.RIGHT_BRACE,
            "[": TokenKind.LEFT_BRACKET,
            "]": TokenKind.RIGHT_BRACKET,
            ",": TokenKind.COMMA,
            ";": TokenKind.SEMICOLON,
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "%": TokenKind.PERCENT,
        }
        if c in single:
            self._add(single[c])
        elif c == ".":
            self._add(TokenKind.RANGE if self._match(".") else TokenKind.DOT)
        elif c == "*":
            self._add(TokenKind.POWER if self._match("*") else TokenKind.STAR)
        elif c == "/":
            if self._match("/"):
                while self._peek() not in ("\n", "\0"):
                    self._advance()
            elif self._match("*"):
                self._block_comment()
            else:
                self._add(TokenKind.SLASH)
        elif c == "#":
            while self._peek() not in ("\n", "\0"):
                self._advance()
        elif c == "=":
            if not self._match("="):
                raise self._error("unexpected '='; use '==' to compare or '<-' to assign")
            self._add(TokenKind.EQUAL)
        elif c == "!":
            self._add(TokenKind.NOT_EQUAL if self._match("=") else TokenKind.NOT)
        elif c == "<":
            if self._match("-"):
                self._add(TokenKind.ASSIGN)
            else:
                self._add(TokenKind.LESS_EQUAL if self._match("=") else TokenKind.LESS)
        elif c == ">":
            self._add(TokenKind.GREATER_EQUAL if self._match("=") else TokenKind.GREATER)
        elif c == ":":
            self._add(TokenKind.DECLARE if self._match("=") else TokenKind.COLON)
        elif c == "?":
            self._add(TokenKind.COALESCE if self._match("?") else TokenKind.QUESTION)
        elif c == "|":
            if self._match(">"):
                self._add(TokenKind.PIPE)
            elif self._match("|"):
                self._add(TokenKind.OR)
            else:
                raise self._error("unexpected '|'; did you mean '|>' or '||'?")
        elif c == "&":
            if self._match("&"):
                self._add(TokenKind.AND)
            else:
                raise self._error("unexpected '&'; did you mean '&&'?")
        elif c in ("\"", "'"):
            self._string(c)
        elif c in (" ", "\r", "\t", "\n"):
            pass
        elif c.isdigit():
            self._number()
        elif c.isalpha() or c == "_":
            self._identifier()
        else:
            raise self._error(f"unexpected character {c!r}")

    def _block_comment(self) -> None:
        depth = 1
        while depth and not self._at_end():
            if self._peek() == "/" and self._peek_next() == "*":
                self._advance()
                self._advance()
                depth += 1
            elif self._peek() == "*" and self._peek_next() == "/":
                self._advance()
                self._advance()
                depth -= 1
            else:
                self._advance()
        if depth:
            raise self._error("unterminated block comment")

    def _string(self, quote: str) -> None:
        value: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "\\": "\\", "\"": "\"", "'": "'"}
        while not self._at_end() and self._peek() != quote:
            char = self._advance()
            if char == "\\":
                if self._at_end():
                    break
                escaped = self._advance()
                if escaped == "u":
                    digits = "".join(self._advance() for _ in range(4) if not self._at_end())
                    if len(digits) != 4 or any(ch not in "0123456789abcdefABCDEF" for ch in digits):
                        raise self._error("invalid Unicode escape; expected four hex digits")
                    value.append(chr(int(digits, 16)))
                elif escaped in escapes:
                    value.append(escapes[escaped])
                else:
                    raise self._error(f"unknown escape sequence '\\{escaped}'")
            elif char == "\n":
                raise self._error("unterminated string; use '\\n' for a newline")
            else:
                value.append(char)
        if self._at_end():
            raise self._error("unterminated string")
        self._advance()
        self._add(TokenKind.STRING, "".join(value))

    def _number(self) -> None:
        if self.source[self.start:self.current] == "0" and self._peek() in "xXbBoO":
            prefix = self._advance().lower()
            valid = {"x": "0123456789abcdefABCDEF_", "b": "01_", "o": "01234567_"}[prefix]
            while self._peek() in valid:
                self._advance()
            raw = self.source[self.start:self.current].replace("_", "")
            try:
                self._add(TokenKind.NUMBER, int(raw, {"x": 16, "b": 2, "o": 8}[prefix]))
            except ValueError as exc:
                raise self._error("invalid numeric literal") from exc
            return
        while self._peek().isdigit() or self._peek() == "_":
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek_next().isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit() or self._peek() == "_":
                self._advance()
        if self._peek() in "eE" and (self._peek_next().isdigit() or self._peek_next() in "+-"):
            is_float = True
            self._advance()
            if self._peek() in "+-":
                self._advance()
            if not self._peek().isdigit():
                raise self._error("invalid exponent")
            while self._peek().isdigit() or self._peek() == "_":
                self._advance()
        raw = self.source[self.start:self.current].replace("_", "")
        try:
            self._add(TokenKind.NUMBER, float(raw) if is_float else int(raw))
        except ValueError as exc:
            raise self._error("invalid numeric literal") from exc

    def _identifier(self) -> None:
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[self.start:self.current]
        self._add(KEYWORDS.get(text, TokenKind.IDENTIFIER))

    def _advance(self) -> str:
        char = self.source[self.current]
        self.current += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _match(self, expected: str) -> bool:
        if self._at_end() or self.source[self.current] != expected:
            return False
        self._advance()
        return True

    def _peek(self) -> str:
        return "\0" if self._at_end() else self.source[self.current]

    def _peek_next(self) -> str:
        return "\0" if self.current + 1 >= len(self.source) else self.source[self.current + 1]

    def _at_end(self) -> bool:
        return self.current >= len(self.source)

    def _span(self) -> Span:
        line_text = self.lines[self.start_line - 1] if self.start_line <= len(self.lines) else ""
        return Span(self.source_name, self.start_line, self.start_column, self.line, self.column, line_text)

    def _add(self, kind: TokenKind, literal: object = None) -> None:
        self.tokens.append(Token(kind, self.source[self.start:self.current], literal, self._span()))

    def _error(self, message: str) -> OmniSyntaxError:
        return OmniSyntaxError(message, self._span())
