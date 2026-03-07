from .tokens import *
from .errors import OmniSyntaxError


class Lexer:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []

    def peek(self, offset=0):
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return '\0'

    def advance(self):
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_whitespace(self):
        while self.pos < len(self.source) and self.peek() in (' ', '\t', '\r'):
            self.advance()

    def skip_comment(self):
        if self.peek() == '-' and self.peek(1) == '-':
            while self.pos < len(self.source) and self.peek() != '\n':
                self.advance()

    def read_string(self):
        quote = self.advance()
        result = ""
        while self.pos < len(self.source) and self.peek() != quote:
            ch = self.advance()
            if ch == '\\':
                esc = self.advance()
                escape_map = {'n': '\n', 't': '\t', '\\': '\\', '"': '"', "'": "'"}
                result += escape_map.get(esc, esc)
            else:
                result += ch
        if self.pos >= len(self.source):
            raise OmniSyntaxError("Unterminated string", self.line)
        self.advance()
        return result

    def read_number(self):
        start = self.pos
        has_dot = False
        while self.pos < len(self.source) and (self.peek().isdigit() or self.peek() == '.'):
            if self.peek() == '.':
                if self.peek(1) == '.':
                    break
                if has_dot:
                    break
                has_dot = True
            self.advance()
        text = self.source[start:self.pos]
        if has_dot:
            return Token(TT_FLOAT, float(text), self.line, self.col)
        return Token(TT_INT, int(text), self.line, self.col)

    def read_identifier(self):
        start = self.pos
        while self.pos < len(self.source) and (self.peek().isalnum() or self.peek() == '_'):
            self.advance()
        text = self.source[start:self.pos]
        if text in KEYWORDS:
            tt = KEYWORDS[text]
            val = text
            if tt == TT_BOOL:
                val = True if text == "true" else False
            return Token(tt, val, self.line, self.col)
        return Token(TT_IDENTIFIER, text, self.line, self.col)

    def tokenize(self):
        while self.pos < len(self.source):
            self.skip_whitespace()
            if self.pos >= len(self.source):
                break

            ch = self.peek()

            if ch == '-' and self.peek(1) == '-':
                self.skip_comment()
                continue

            if ch == '\n':
                self.tokens.append(Token(TT_NEWLINE, '\\n', self.line, self.col))
                self.advance()
                continue

            if ch in ('"', "'"):
                s = self.read_string()
                self.tokens.append(Token(TT_STRING, s, self.line, self.col))
                continue

            if ch.isdigit():
                self.tokens.append(self.read_number())
                continue

            if ch.isalpha() or ch == '_':
                self.tokens.append(self.read_identifier())
                continue

            two = ch + self.peek(1) if self.pos + 1 < len(self.source) else ""
            if two == '==':
                self.tokens.append(Token(TT_EQ, '==', self.line, self.col))
                self.advance()
                self.advance()
                continue
            if two == '!=':
                self.tokens.append(Token(TT_NEQ, '!=', self.line, self.col))
                self.advance()
                self.advance()
                continue
            if two == '<=':
                self.tokens.append(Token(TT_LTE, '<=', self.line, self.col))
                self.advance()
                self.advance()
                continue
            if two == '>=':
                self.tokens.append(Token(TT_GTE, '>=', self.line, self.col))
                self.advance()
                self.advance()
                continue
            if two == '..':
                self.tokens.append(Token(TT_DOTDOT, '..', self.line, self.col))
                self.advance()
                self.advance()
                continue

            single_map = {
                '+': TT_PLUS, '-': TT_MINUS, '*': TT_MUL, '/': TT_DIV,
                '%': TT_MOD, '=': TT_ASSIGN, '<': TT_LT, '>': TT_GT,
                '(': TT_LPAREN, ')': TT_RPAREN,
                '{': TT_LBRACE, '}': TT_RBRACE,
                '[': TT_LBRACKET, ']': TT_RBRACKET,
                ',': TT_COMMA,
            }

            if ch in single_map:
                self.tokens.append(Token(single_map[ch], ch, self.line, self.col))
                self.advance()
                continue

            raise OmniSyntaxError(f"Unexpected character: '{ch}'", self.line)

        self.tokens.append(Token(TT_EOF, None, self.line, self.col))
        return self.tokens