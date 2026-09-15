"""The OmniScript tokenizer.

OmniScript's lexical rules, all invented for this language:

  * newline is a statement separator -- no semicolons required (they are
    allowed if you like them)
  * `#` line comment, `#{ ... }#` block comment
  * strings interpolate with `${ expr }` and support `\\{ expr }` shorthand
  * numbers: 42, 3.14, 0xff, 0b1010, 1_000_000, 1e6
  * sigils: `$name` is the variable, `@name` is an attribute
"""

from __future__ import annotations

from .errors import OmniLexError

KEYWORDS = {
    "let", "mut", "fn", "return", "if", "else", "for", "in", "while", "do",
    "match", "when", "class", "new", "self", "super", "true", "false", "null",
    "and", "or", "not", "try", "catch", "finally", "throw", "break", "continue",
    "use", "as", "from", "is", "isnt", "by",
}

# (text, token kind) -- longest first so the greedy scan is correct.
SYMBOLS = [
    ("||>", "PIPEALL"),
    ("=>", "FAT_ARROW"), ("->", "ARROW"),
    ("==", "EQEQ"), ("!=", "BANGEQ"), ("<=", "LTEQ"), (">=", "GTEQ"),
    ("&&", "ANDAND"), ("||", "BARBAR"),
    ("<<=", "SHLEQ"), (">>=", "SHREQ"),
    ("+=", "PLUSEQ"), ("-=", "MINUSEQ"), ("*=", "STAREQ"), ("/=", "SLASHEQ"),
    ("%=", "PERCEQ"), ("^=", "CARETEQ"), ("|=", "PIPEEQ"), ("&=", "AMPEQ"),
    ("**", "POWER"), ("<<", "SHL"), (">>", "SHR"), ("//", "FLOOR_DIV"),
    ("?.", "QMARK_DOT"), ("??", "QMARKQMARK"), ("?:", "QMARKCOLON"),
    ("++", "PLUSPLUS"), ("--", "MINUSMINUS"),
    ("+", "PLUS"), ("-", "MINUS"), ("*", "STAR"), ("/", "SLASH"), ("%", "PERCENT"),
    ("^", "CARET"), ("&", "AMP"), ("|", "BAR"), ("~", "TILDE"), ("!", "BANG"),
    ("<", "LT"), (">", "GT"), ("=", "ASSIGN"), ("?", "QMARK"), (":", "COLON"),
    (".", "DOT"), (",", "COMMA"), (";", "SEMI"),
    ("(", "LPAREN"), (")", "RPAREN"), ("[", "LBRACKET"), ("]", "RBRACKET"),
    ("{", "LBRACE"), ("}", "RBRACE"),
]

ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"',
    "0": "\0", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "e": "\x1b",
    "$": "$",
}


class Token:
    __slots__ = ("kind", "value", "line", "col")

    def __init__(self, kind: str, value, line: int, col: int):
        self.kind = kind
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):  # pragma: no cover - debug helper
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.col})"


def _is_id_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_id_cont(c: str) -> bool:
    return c.isalnum() or c == "_"


class Scanner:
    def __init__(self, src: str, path: str = "<stdin>"):
        self.src = src
        self.path = path
        self.i = 0
        self.n = len(src)
        self.line = 1
        self.col = 1

    # -- low level ---------------------------------------------------------
    def eof(self) -> bool:
        return self.i >= self.n

    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.src[j] if j < self.n else ""

    def starts(self, text: str) -> bool:
        return self.src.startswith(text, self.i)

    def advance(self, k: int = 1) -> None:
        for _ in range(k):
            if self.i >= self.n:
                return
            if self.src[self.i] == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.i += 1

    def fail(self, msg: str, hint: str | None = None, line=None, col=None):
        raise OmniLexError(msg, line or self.line, col or self.col, hint)

    # -- entry -------------------------------------------------------------
    def run(self) -> list[Token]:
        tokens: list[Token] = []
        while not self.eof():
            c = self.peek()

            if c in " \t\r":
                self.advance()
                continue

            # line continuation: trailing backslash joins the next line
            if c == "\\" and self.peek(1) == "\n":
                self.advance(2)
                continue

            if c == "\n":
                if tokens and tokens[-1].kind != "NEWLINE":
                    tokens.append(Token("NEWLINE", "\n", self.line, self.col))
                self.advance()
                continue

            if c == "#":
                if self.scan_comment():
                    continue

            if c in "\"'":
                tokens.append(self.scan_string())
                continue

            if c == "r" and self.peek(1) in ("'", '"'):
                self.advance()
                tokens.append(self.scan_string(raw=True))
                continue

            if c.isdigit():
                tokens.append(self.scan_number())
                continue

            # `.5` is a number, but `1..5` is a range: only start a number on a
            # leading dot when the previous token could not end an expression.
            if c == "." and self.peek(1).isdigit():
                prev = tokens[-1].kind if tokens else None
                if prev not in ("DOT", "NUM", "IDENT", "SIGVAR", "STR",
                                "RPAREN", "RBRACKET"):
                    tokens.append(self.scan_number())
                    continue

            if _is_id_start(c):
                tokens.append(self.scan_word())
                continue

            if c == "$" and _is_id_start(self.peek(1)):
                line, col = self.line, self.col
                self.advance()
                name = self.scan_ident_chars()
                tokens.append(Token("SIGVAR", name, line, col))
                continue

            if c == "@" and _is_id_start(self.peek(1)):
                line, col = self.line, self.col
                self.advance()
                name = self.scan_ident_chars()
                tokens.append(Token("SIGATTR", name, line, col))
                continue

            line, col = self.line, self.col
            for text, kind in SYMBOLS:
                if self.starts(text):
                    self.advance(len(text))
                    tokens.append(Token(kind, text, line, col))
                    break
            else:
                self.fail(f"unexpected character `{c}`",
                          "this character has no meaning in OmniScript")

        tokens.append(Token("EOF", None, self.line, self.col))
        return tokens

    # -- pieces ------------------------------------------------------------
    def scan_ident_chars(self) -> str:
        start = self.i
        while not self.eof() and _is_id_cont(self.peek()):
            self.advance()
        return self.src[start:self.i]

    def scan_word(self) -> Token:
        line, col = self.line, self.col
        word = self.scan_ident_chars()
        return Token("KW" if word in KEYWORDS else "IDENT", word, line, col)

    def scan_comment(self) -> bool:
        """Handle `#{ ... }#` block comments and `#` line comments."""
        if self.starts("#{"):
            open_line = self.line
            depth = 0
            while not self.eof():
                if self.starts("#{"):
                    depth += 1
                    self.advance(2)
                elif self.starts("}#"):
                    depth -= 1
                    self.advance(2)
                    if depth == 0:
                        return True
                else:
                    self.advance()
            self.fail(f"unterminated block comment opened on line {open_line}",
                      "close it with }#", line=open_line, col=1)
        while not self.eof() and self.peek() != "\n":
            self.advance()
        return True

    def scan_number(self) -> Token:
        line, col = self.line, self.col
        src = self.src

        if self.peek() == "0" and self.peek(1).lower() in ("x", "b", "o"):
            base_char = self.peek(1).lower()
            base = {"x": 16, "b": 2, "o": 8}[base_char]
            self.advance(2)
            start = self.i
            while not self.eof() and (self.peek().isdigit() or self.peek().lower() in "abcdef" or self.peek() == "_"):
                self.advance()
            raw = src[start:self.i].replace("_", "")
            if not raw:
                self.fail(f"empty `0{base_char}` literal", "put digits after the prefix")
            try:
                return Token("NUM", float(int(raw, base)), line, col)
            except ValueError:
                self.fail(f"`0{base_char}{raw}` is not a valid base-{base} number")

        start = self.i
        is_float = False
        while not self.eof() and (self.peek().isdigit() or self.peek() == "_"):
            self.advance()
        # `1..5` is a range, not `1.` followed by `.5`, so a second dot stops us.
        if self.peek() == "." and self.peek(1) != "." and not _is_id_start(self.peek(1)):
            is_float = True
            self.advance()
            while not self.eof() and (self.peek().isdigit() or self.peek() == "_"):
                self.advance()
        if self.peek().lower() == "e":
            k = self.i + 1
            if k < self.n and src[k] in "+-":
                k += 1
            if k < self.n and src[k].isdigit():
                is_float = True
                self.advance(k - self.i)
                while not self.eof() and self.peek().isdigit():
                    self.advance()

        raw = src[start:self.i].replace("_", "")
        try:
            return Token("NUM", float(raw), line, col)
        except ValueError:
            self.fail(f"invalid number literal `{raw}`")

    def scan_string(self, raw: bool = False) -> Token:
        quote = self.peek()
        line, col = self.line, self.col
        self.advance()
        # `"""..."""` and '''...''' span lines, like a here-document
        triple = False
        if self.peek() == quote and self.peek(1) == quote:
            triple = True
            self.advance(2)
        chunks: list = []
        buf: list[str] = []

        def flush():
            if buf:
                chunks.append("".join(buf))
                buf.clear()

        while True:
            if self.eof():
                self.fail("unterminated string literal",
                          f"add a closing {quote * (3 if triple else 1)}",
                          line=line, col=col)
            ch = self.peek()

            if ch == quote:
                if triple:
                    if self.peek(1) == quote and self.peek(2) == quote:
                        self.advance(3)
                        break
                    buf.append(ch)
                    self.advance()
                    continue
                self.advance()
                break

            if ch == "\n" and quote == "'" and not triple:
                self.fail("unterminated single-quoted string",
                          "single quotes must stay on one line", line=line, col=col)

            if raw and ch == "\\":
                buf.append(ch)
                self.advance()
                continue

            if ch == "\\" and not self.eof():
                nxt = self.peek(1)
                if nxt == "{":
                    flush()
                    self.advance(2)
                    chunks.append(("expr", self.lex_interp("}")))
                    continue
                if nxt == "\n":
                    self.advance(2)
                    continue
                if nxt == "u" and self.peek(2) == "{":
                    self.advance(3)
                    start = self.i
                    while not self.eof() and self.peek() != "}":
                        self.advance()
                    raw = self.src[start:self.i]
                    if self.eof():
                        self.fail("unterminated \\u{...} escape")
                    self.advance()
                    try:
                        buf.append(chr(int(raw, 16)))
                    except ValueError:
                        self.fail(f"bad unicode escape `\\u{{{raw}}}`")
                    continue
                if nxt == "x":
                    hexs = self.src[self.i + 2:self.i + 4]
                    if len(hexs) == 2:
                        try:
                            buf.append(chr(int(hexs, 16)))
                            self.advance(4)
                            continue
                        except ValueError:
                            pass
                if nxt in ESCAPES:
                    buf.append(ESCAPES[nxt])
                    self.advance(2)
                    continue
                if nxt == "":
                    self.fail("string ends with a dangling backslash")
                buf.append(nxt)
                self.advance(2)
                continue

            if not raw and ch == "$" and self.peek(1) == "{":
                flush()
                self.advance(2)
                chunks.append(("expr", self.lex_interp("}")))
                continue

            buf.append(ch)
            self.advance()

        flush()
        if not chunks:
            value: object = ""
        elif len(chunks) == 1 and isinstance(chunks[0], str):
            value = chunks[0]
        else:
            value = chunks
        return Token("STR", value, line, col)

    def lex_interp(self, closer: str) -> list[Token]:
        """We are just past `${`. Scan to the matching `}` and tokenize inside."""
        depth = 1
        start = self.i
        while not self.eof():
            ch = self.peek()
            if ch in "\"'":
                q = ch
                self.advance()
                while not self.eof():
                    if self.peek() == "\\":
                        self.advance(2)
                        continue
                    if self.peek() == q:
                        self.advance()
                        break
                    self.advance()
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            self.advance()
        if depth != 0:
            self.fail("unterminated `${` interpolation inside string",
                      "add a closing }")
        inner = self.src[start:self.i]
        self.advance()  # consume the }
        toks = [t for t in tokenize(inner, "<string>") if t.kind not in ("EOF", "NEWLINE")]
        last_line = toks[-1].line if toks else self.line
        toks.append(Token("EOF", None, last_line, 1))
        return toks


def tokenize(src: str, path: str = "<stdin>") -> list[Token]:
    return Scanner(src, path).run()
