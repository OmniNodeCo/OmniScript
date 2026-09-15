"""The OmniScript parser.

Design notes
------------
* Statements are separated by newlines; `;` is accepted but never required.
* Almost everything is an expression: `if`, `match`, blocks and `try` all
  produce values, so `let x = if a { 1 } else { 2 }` just works.
* Precedence (loosest to tightest):

      assignment  =  +=  -=  *=  /=  %=  ^=  |=  &=  <<=  >>=  ++  --
      pipeline    |>   ||>
      ternary     ?:     ?.:     elvis ??
      or          or  ||
      and         and &&
      equality    ==  !=  is  isnt
      comparison  <  <=  >  >=
      bitwise-or  |
      bitwise-xor ^
      bitwise-and &
      shift       <<  >>
      additive    +  -
      multiplicative  *  /  %
      power       **            (right associative)
      range       a..b   a..=b   a..b..step
      unary       -  not  !  ~  new
      postfix     .  ?.  []  ()
      primary
"""

from __future__ import annotations

from .ast import (Assign, Binary, Block, Bool, Break, Call, ChainCompare, ClassDecl,
                  Continue, DoWhile, Elvis, ExprStmt, For, FnDecl, Ident, If, Index,
                  Lambda, Let, ListLit, MapLit, Match, MatchArm, Member, MultiAssign,
                  Null, Num, PBind, PList, PLit, PMap, PTyped, PWild,
                  Paren, Pipe, RangeLit, Return,
                  SigAttr, Slice, Str, Ternary, Throw, Try, Unary, Use, While)
from .errors import OmniError, OmniSyntaxError
from .lexer import Token, tokenize
from .values import to_repr

COMPOUND = {
    "PLUSEQ": "+", "MINUSEQ": "-", "STAREQ": "*", "SLASHEQ": "/", "PERCEQ": "%",
    "CARETEQ": "^", "PIPEEQ": "|", "AMPEQ": "&", "SHLEQ": "<<", "SHREQ": ">>",
}
ASSIGN_TOKENS = {"ASSIGN", *COMPOUND}

TYPE_WORDS = {"num", "str", "bool", "list", "map", "fn", "null", "obj", "any",
              "int", "range", "set", "bytes"}

# Each binary level: {token kind: operator} plus optional keyword operators.
LEVELS: list[tuple[dict[str, str], tuple[str, ...]]] = [
    ({"BARBAR": "or"}, ("or",)),
    ({"ANDAND": "and"}, ("and",)),
    ({"EQEQ": "==", "BANGEQ": "!="}, ("is", "isnt")),
    ({"LT": "<", "LTEQ": "<=", "GT": ">", "GTEQ": ">="}, ()),
    ({"BAR": "|"}, ()),
    ({"CARET": "^"}, ()),
    ({"AMP": "&"}, ()),
    ({"SHL": "<<", "SHR": ">>"}, ()),
    None,                                   # 8: `..` ranges (see parse_range)
    ({"PLUS": "+", "MINUS": "-"}, ()),
    ({"STAR": "*", "SLASH": "/", "PERCENT": "%", "FLOOR_DIV": "//"}, ()),
]
TOP_LEVEL = len(LEVELS)
CMP_LEVEL = 3        # the `< <= > >=` row, which may chain
RANGE_LEVEL = 8      # `..` binds looser than arithmetic: `0..n - 1`

# Tokens that may legally follow an expression we just finished parsing.
BODY_STOP = ("RBRACKET", "RPAREN", "COMMA", "NEWLINE", "SEMI", "EOF", "RBRACE",
             "FAT_ARROW", "COLON")

# Statement terminators we tolerate without consuming (the enclosing construct
# still needs to see them).
SOFT_ENDS = {"else", "catch", "finally", "when"}


def reserved_word_hint(tok) -> str | None:
    """Explain why `let when = 1` cannot work."""
    if tok.kind == "KW":
        return (f"`{tok.value}` is a reserved word, so it cannot be a name -- "
                f"try `{tok.value}_` or something more specific")
    return None


def pattern_label(pattern) -> str:
    """A readable name for a destructuring parameter, used in signatures.

    `[x1, y1]` stays `[x1, y1]`, so an error can say which one was missing.
    """
    if isinstance(pattern, PBind):
        return pattern.name
    if isinstance(pattern, PWild):
        return "_"
    if isinstance(pattern, PLit):
        return to_repr(pattern.value) if pattern.value is not None else "null"
    if isinstance(pattern, PTyped):
        return f"{pattern.name} is {pattern.type}"
    if isinstance(pattern, PList):
        inner = ", ".join(pattern_label(p) for p in pattern.items)
        if pattern.rest:
            inner = f"{inner}, *{pattern.rest}" if inner else f"*{pattern.rest}"
        return f"[{inner}]"
    if isinstance(pattern, PMap):
        parts = []
        for key, sub in pattern.entries:
            label = pattern_label(sub)
            parts.append(label if label == key else f"{key}: {label}")
        return "{" + ", ".join(parts) + "}"
    return "_"


class Parser:
    def __init__(self, tokens: list[Token], src: str = "", path: str = "<stdin>"):
        self.toks = tokens
        self.pos = 0
        self.src = src
        self.path = path

    # ---------------------------------------------------------------- utils
    def cur(self) -> Token:
        return self.toks[self.pos]

    def peek(self, k: int = 1) -> Token:
        j = self.pos + k
        return self.toks[j] if j < len(self.toks) else self.toks[-1]

    def prev(self) -> Token:
        return self.toks[max(0, self.pos - 1)]

    def at(self, kind: str, value=None) -> bool:
        t = self.cur()
        return t.kind == kind and (value is None or t.value == value)

    def at_kw(self, *words: str) -> bool:
        t = self.cur()
        return t.kind == "KW" and t.value in words

    def eat(self, kind: str, value=None) -> Token | None:
        if self.at(kind, value):
            t = self.cur()
            self.pos += 1
            return t
        return None

    def expect(self, kind: str, what: str | None = None) -> Token:
        t = self.eat(kind)
        if t is None:
            cur = self.cur()
            got = f"`{cur.value}`" if cur.value is not None else f"end of input"
            self.fail(f"expected {what or kind} but found {got}", cur)
        return t  # type: ignore[return-value]

    def fail(self, msg: str, tok: Token | None = None, hint: str | None = None):
        t = tok or self.cur()
        raise OmniSyntaxError(msg, t.line, t.col, hint)

    def skip_seps(self) -> None:
        while self.at("NEWLINE") or self.at("SEMI"):
            self.pos += 1

    def at_stmt_end(self) -> bool:
        return self.cur().kind in ("NEWLINE", "SEMI", "EOF", "RBRACE")

    def at_range_stop(self) -> bool:
        t = self.cur()
        if t.kind in BODY_STOP:
            return True
        return t.kind == "KW" and t.value in ("by", "in", "else", "when", "and", "or")

    def end_stmt(self) -> None:
        if self.at_stmt_end():
            self.skip_seps()
            return
        t = self.cur()
        if t.kind == "KW" and t.value in SOFT_ENDS:
            return
        if t.kind == "BAR" and self.starts_pipe():
            return
        self.fail(f"unexpected `{t.value}` after this statement", t,
                  "statements are separated by newlines")

    def starts_pipe(self) -> bool:
        """`|>` arrives from the lexer as BAR + GT."""
        return self.at("BAR") and self.peek().kind == "GT"

    # -------------------------------------------------------------- program
    def parse_program(self) -> list:
        stmts = []
        self.skip_seps()
        while not self.at("EOF"):
            stmts.append(self.parse_statement())
            self.skip_seps()
        return stmts

    def parse_block(self) -> list:
        open_tok = self.expect("LBRACE", "`{`")
        stmts = []
        self.skip_seps()
        while not self.at("RBRACE"):
            if self.at("EOF"):
                self.fail("unexpected end of file", open_tok,
                          "this block is missing its closing `}`")
            stmts.append(self.parse_statement())
            self.skip_seps()
        self.expect("RBRACE", "`}`")
        return stmts

    def block_of(self, stmts, line, col=1):
        return Block(stmts, True, line=line, col=col)

    # ------------------------------------------------------------ statements
    def parse_statement(self):
        t = self.cur()
        line, col = t.line, t.col

        if t.kind == "KW":
            handler = {
                "let": self.parse_let, "mut": self.parse_let, "fn": self.parse_fn_stmt,
                "class": self.parse_class, "return": self.parse_return,
                "if": self.parse_if_stmt, "for": self.parse_for, "while": self.parse_while,
                "do": self.parse_do_while, "match": self.parse_match_stmt,
                "try": self.parse_try, "throw": self.parse_throw,
                "break": self.parse_break_continue, "continue": self.parse_break_continue,
                "use": self.parse_use,
            }.get(t.value)
            if handler:
                return handler()

        if t.kind == "SIGATTR":
            return self.parse_attributed()

        if t.kind in ("IDENT", "SIGVAR") or (t.kind == "KW" and t.value == "self"):
            swap = self.parse_multi_assign(line, col)
            if swap is not None:
                self.end_stmt()
                return swap

        expr = self.parse_expr()
        node = ExprStmt(expr, line=line, col=col)
        self.end_stmt()
        return node

    def parse_multi_assign(self, line, col):
        """`a, b = b, a` and `xs[0], ys[0] = 1, 2`.

        Returns None (and rewinds) when the statement is not one of those.
        """
        start = self.pos
        try:
            targets = [self.parse_postfix()]
            while self.at("COMMA"):
                self.pos += 1
                targets.append(self.parse_postfix())
            if len(targets) < 2 or not self.at("ASSIGN"):
                self.pos = start
                return None
            self.pos += 1
            values = [self.parse_expr()]
            while self.at("COMMA"):
                self.pos += 1
                values.append(self.parse_expr())
        except OmniError:
            self.pos = start
            return None
        return MultiAssign(targets, values, line=line, col=col)

    def parse_attributed(self):
        attrs = []
        while self.at("SIGATTR"):
            a = self.cur()
            self.pos += 1
            args = []
            if self.at("LPAREN"):
                self.pos += 1
                self.skip_seps()
                while not self.at("RPAREN"):
                    args.append(self.parse_expr())
                    if not self.eat("COMMA"):
                        break
                    self.skip_seps()
                self.expect("RPAREN", "`)`")
            attrs.append((a.value, args, a.line))
            self.skip_seps()
        if self.at_kw("fn"):
            node = self.parse_fn_stmt()
            node.attrs = attrs
            return node
        if self.at_kw("class"):
            node = self.parse_class()
            node.attrs = attrs
            return node
        self.fail("an @attribute must sit in front of `fn` or `class`")

    def parse_let(self):
        t = self.cur()
        mutable = t.value == "mut"
        self.pos += 1
        targets = self.parse_destructure_targets()
        if self.at("COLON") and self.peek().kind in ("IDENT", "KW"):
            self.pos += 1
            self.parse_type_name()
        value = None
        if self.eat("ASSIGN"):
            if len(targets) > 1:
                first = self.parse_expr()
                items = [first]
                while self.eat("COMMA"):
                    items.append(self.parse_expr())
                value = ListLit(items, [False] * len(items), line=t.line, col=t.col)
            else:
                value = self.parse_expr()
        if value is None:
            value = Null(line=t.line, col=t.col)
        node = Let(targets, value, mutable, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_type_name(self) -> str:
        t = self.cur()
        if t.kind == "IDENT" or (t.kind == "KW" and t.value in ("null",)):
            self.pos += 1
            return str(t.value)
        if t.kind == "LBRACKET":
            self.pos += 1
            inner = self.parse_type_name()
            self.expect("RBRACKET", "`]`")
            return f"[{inner}]"
        self.fail(f"expected a type name but found `{t.value}`")
        return ""  # unreachable

    def parse_destructure_targets(self) -> list:
        t = self.cur()
        if t.kind == "LBRACKET":
            return [self.parse_list_pattern()]
        if t.kind == "LBRACE":
            return [self.parse_map_pattern()]
        if t.kind in ("IDENT", "SIGVAR") or (t.kind == "KW" and t.value in ("self",)):
            names = []
            while True:
                nt = self.cur()
                if nt.kind in ("IDENT", "SIGVAR") or (nt.kind == "KW" and nt.value in TYPE_WORDS):
                    self.pos += 1
                    names.append(PBind(nt.value, line=nt.line, col=nt.col))
                else:
                    self.fail(f"expected a variable name but found `{nt.value}`",
                              nt, reserved_word_hint(nt))
                if self.at("COLON") and self.peek().kind in ("IDENT", "KW"):
                    self.pos += 1
                    self.parse_type_name()
                if not self.eat("COMMA"):
                    break
            return names
        self.fail(f"expected a variable name but found `{t.value}`", t,
                  reserved_word_hint(t))
        return []  # unreachable

    def parse_list_pattern(self):
        t = self.expect("LBRACKET", "`[`")
        items, rest = [], None
        self.skip_seps()
        while not self.at("RBRACKET"):
            if self.at("STAR") or self.at("POWER"):
                self.pos += 1
                nt = self.cur()
                if nt.kind not in ("IDENT", "SIGVAR"):
                    self.fail("expected a name after `*`")
                self.pos += 1
                rest = nt.value
            else:
                items.append(self.parse_pattern())
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RBRACKET", "`]`")
        return PList(items, rest, line=t.line, col=t.col)

    def parse_map_pattern(self):
        t = self.expect("LBRACE", "`{`")
        entries = []
        self.skip_seps()
        while not self.at("RBRACE"):
            key = self.cur()
            if key.kind in ("IDENT", "SIGVAR", "KW"):
                self.pos += 1
                kname = key.value
            elif key.kind in ("STR", "NUM"):
                self.pos += 1
                kname = key.value
            elif key.kind == "LBRACKET":
                kname = self.parse_primary()
            else:
                self.fail(f"expected a key but found `{key.value}`")
            if self.eat("COLON"):
                # `{ name: who }` binds the key `name` to the variable `who`
                entries.append((kname, self.parse_pattern()))
            else:
                # `{ name }` is shorthand for `{ name: name }`
                entries.append((kname, PBind(kname if isinstance(kname, str) else "_",
                                             line=key.line, col=key.col)))
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RBRACE", "`}`")
        return PMap(entries, line=t.line, col=t.col)

    def parse_fn_stmt(self):
        t = self.expect("KW", "`fn`")
        nt = self.cur()
        if nt.kind not in ("IDENT", "SIGVAR"):
            self.fail(f"expected a function name after `fn` but found `{nt.value}`")
        self.pos += 1
        params = self.parse_params()
        if self.at("COLON") and self.peek().kind in ("IDENT", "KW"):
            self.pos += 1
            self.parse_type_name()
        body = self.parse_block()
        node = FnDecl(nt.value, params, self.block_of(body, t.line), [],
                      line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_params(self) -> list:
        self.expect("LPAREN", "`(`")
        params = []
        seen_rest = False
        self.skip_seps()
        while not self.at("RPAREN"):
            rest = kwrest = False
            if self.at("STAR"):
                rest = True
                self.pos += 1
            elif self.at("POWER"):
                kwrest = True
                self.pos += 1
            nt = self.cur()
            pattern = None
            if nt.kind in ("LBRACKET", "LBRACE"):
                # a destructuring parameter: fn dist([x1, y1], [x2, y2])
                pattern = self.parse_pattern()
                pname = pattern_label(pattern)
            else:
                ok = nt.kind in ("IDENT", "SIGVAR") or \
                    (nt.kind == "KW" and nt.value in TYPE_WORDS)
                if not ok:
                    self.fail(f"expected a parameter name but found `{nt.value}`")
                self.pos += 1
                pname = nt.value
            type_annot = None
            if self.at("COLON") and self.peek().kind in ("IDENT", "KW"):
                self.pos += 1
                type_annot = self.parse_type_name()
            default = None
            if self.eat("ASSIGN"):
                default = self.parse_expr()
            params.append({"name": pname, "default": default, "rest": rest,
                           "kwrest": kwrest, "type": type_annot, "line": nt.line,
                           "kw_only": seen_rest, "pattern": pattern})
            seen_rest = seen_rest or rest
            self.skip_seps()
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RPAREN", "`)`")
        return params

    def parse_class(self):
        t = self.expect("KW", "`class`")
        nt = self.cur()
        if nt.kind not in ("IDENT", "SIGVAR"):
            self.fail(f"expected a class name but found `{nt.value}`")
        self.pos += 1
        parent = None
        if self.eat("COLON"):
            pt = self.cur()
            if pt.kind not in ("IDENT", "SIGVAR"):
                self.fail("expected a parent class name")
            self.pos += 1
            parent = pt.value
        self.expect("LBRACE", "`{`")
        members = []
        self.skip_seps()
        while not self.at("RBRACE"):
            if self.at("EOF"):
                self.fail("unexpected end of file", t, "this class is missing its `}`")
            attrs = []
            while self.at("SIGATTR"):
                a = self.cur()
                self.pos += 1
                attrs.append((a.value, [], a.line))
                self.skip_seps()
            mt = self.cur()
            if mt.kind == "KW" and mt.value in ("fn", "new"):
                is_ctor = mt.value == "new"
                self.pos += 1
                if is_ctor:
                    mname = "new"
                else:
                    nmt = self.cur()
                    if nmt.kind not in ("IDENT", "SIGVAR"):
                        self.fail(f"expected a method name but found `{nmt.value}`")
                    self.pos += 1
                    mname = nmt.value
                params = self.parse_params()
                body = self.parse_block()
                members.append(FnDecl(mname, params, self.block_of(body, mt.line),
                                      attrs, line=mt.line, col=mt.col))
            elif mt.kind == "IDENT":
                self.pos += 1
                value = self.parse_expr() if self.eat("ASSIGN") else Null(line=mt.line)
                members.append(("field", mt.value, value, mt.line))
            else:
                self.fail(f"expected `fn`, `new` or a field name here but found `{mt.value}`")
            self.skip_seps()
        self.expect("RBRACE", "`}`")
        node = ClassDecl(nt.value, parent, members, [], line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_return(self):
        t = self.cur()
        self.pos += 1
        value = None if self.at_stmt_end() else self.parse_expr()
        node = Return(value, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_throw(self):
        t = self.cur()
        self.pos += 1
        node = Throw(self.parse_expr(), line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_break_continue(self):
        t = self.cur()
        kind = Break if t.value == "break" else Continue
        self.pos += 1
        node = kind(line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_use(self):
        t = self.cur()
        self.pos += 1
        names = None
        if self.at("LBRACE"):
            self.pos += 1
            names = []
            self.skip_seps()
            while not self.at("RBRACE"):
                nt = self.cur()
                if nt.kind not in ("IDENT", "KW"):
                    self.fail("expected a name inside `use { ... }`")
                self.pos += 1
                alias = nt.value
                if self.at_kw("as"):
                    self.pos += 1
                    alias = self.expect("IDENT", "an alias").value
                names.append((nt.value, alias))
                if not self.eat("COMMA"):
                    break
                self.skip_seps()
            self.expect("RBRACE", "`}`")
            if not self.at_kw("from"):
                self.fail("expected `from` after `use { ... }`")
            self.pos += 1
        path_tok = self.cur()
        if path_tok.kind == "STR":
            self.pos += 1
            if not isinstance(path_tok.value, str):
                self.fail("`use` needs a plain string path")
            path = path_tok.value
        elif path_tok.kind in ("IDENT", "KW"):
            parts = [str(path_tok.value)]
            self.pos += 1
            while self.cur().kind in ("SLASH", "DOT"):
                self.pos += 1
                nt = self.cur()
                if nt.kind not in ("IDENT", "KW", "NUM"):
                    self.fail("bad module path")
                parts.append(str(nt.value))
                self.pos += 1
            path = "/".join(parts)
        else:
            self.fail(f"expected a module path after `use` but found `{path_tok.value}`")
            path = ""  # unreachable
        alias = None
        if self.at_kw("as"):
            self.pos += 1
            alias = self.expect("IDENT", "an alias").value
        node = Use(path, alias, names, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_if_stmt(self):
        node = self.parse_if()
        self.end_stmt()
        return node

    def parse_if(self):
        t = self.expect("KW", "`if`")
        branches = []
        cond = self.parse_expr()
        branches.append((cond, self.parse_body()))
        otherwise = None
        while self.at_kw("else"):
            self.pos += 1
            if self.at_kw("if"):
                self.pos += 1
                branches.append((self.parse_expr(), self.parse_body()))
            else:
                otherwise = self.parse_body()
                break
        return If(branches, otherwise, line=t.line, col=t.col)

    def parse_body(self):
        """Either a `{ block }` or one statement on the same line."""
        if self.at("LBRACE"):
            open_tok = self.cur()
            return self.block_of(self.parse_block(), open_tok.line, open_tok.col)
        t = self.cur()
        if t.kind in ("NEWLINE", "EOF", "RBRACE", "SEMI"):
            self.fail("expected a body after this condition", t,
                      "wrap it in `{ }` or put the statement on the same line")
        line = t.line
        return self.block_of([self.parse_statement()], line, t.col)

    def parse_for(self):
        t = self.expect("KW", "`for`")
        targets = self.parse_destructure_targets()
        if not self.at_kw("in"):
            self.fail(f"expected `in` in a for loop but found `{self.cur().value}`")
        self.pos += 1
        iterable = self.parse_expr()
        by = None
        if self.at_kw("by"):
            self.pos += 1
            by = self.parse_expr()
        body = self.parse_body()
        node = For(targets, iterable, body, by, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_while(self):
        t = self.expect("KW", "`while`")
        cond = self.parse_expr()
        body = self.parse_body()
        node = While(cond, body, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_do_while(self):
        t = self.expect("KW", "`do`")
        body = self.parse_body()
        if not self.at_kw("while"):
            self.fail("expected `while` after a `do` body")
        self.pos += 1
        cond = self.parse_expr()
        node = DoWhile(body, cond, line=t.line, col=t.col)
        self.end_stmt()
        return node

    def parse_match_stmt(self):
        node = self.parse_match()
        self.end_stmt()
        return node

    def parse_match(self):
        t = self.expect("KW", "`match`")
        subject = self.parse_expr()
        self.expect("LBRACE", "`{` after the match subject")
        arms = []
        self.skip_seps()
        while not self.at("RBRACE"):
            if self.at("EOF"):
                self.fail("unexpected end of file", t, "this match is missing its `}`")
            at = self.cur()
            pattern = self.parse_pattern()
            guard = None
            if self.at_kw("when", "if"):
                self.pos += 1
                guard = self.parse_expr()
            if not self.eat("FAT_ARROW"):
                self.fail(f"expected `=>` in this match arm but found `{self.cur().value}`",
                          self.cur(), "match arms look like:  pattern => value")
            if self.at("LBRACE"):
                bt = self.cur()
                value = self.block_of(self.parse_block(), bt.line, bt.col)
            else:
                value = self.parse_expr()
            arms.append(MatchArm(pattern, guard, value, line=at.line, col=at.col))
            self.eat("COMMA")
            self.skip_seps()
        self.expect("RBRACE", "`}`")
        return Match(subject, arms, line=t.line, col=t.col)

    def parse_try(self):
        t = self.expect("KW", "`try`")
        body = self.parse_block()
        catch_name = catch_body = finally_body = None
        if self.at_kw("catch"):
            self.pos += 1
            if self.at("IDENT") or self.at("SIGVAR"):
                catch_name = self.cur().value
                self.pos += 1
            elif self.at("LPAREN"):
                self.pos += 1
                catch_name = self.expect("IDENT", "a variable name").value
                self.expect("RPAREN", "`)`")
            cb = self.parse_block()
            catch_body = self.block_of(cb, t.line)
        if self.at_kw("finally"):
            self.pos += 1
            fb = self.parse_block()
            finally_body = self.block_of(fb, t.line)
        if catch_body is None and finally_body is None:
            self.fail("`try` needs a `catch` or a `finally`")
        return Try(self.block_of(body, t.line, t.col), catch_name, catch_body,
                   finally_body, line=t.line, col=t.col)

    # -------------------------------------------------------------- patterns
    def parse_pattern(self):
        t = self.cur()
        if t.kind == "LBRACKET":
            return self.parse_list_pattern()
        if t.kind == "LBRACE":
            return self.parse_map_pattern()
        if t.kind == "NUM":
            self.pos += 1
            return PLit(t.value, line=t.line, col=t.col)
        if t.kind == "STR" and isinstance(t.value, str):
            self.pos += 1
            return PLit(t.value, line=t.line, col=t.col)
        if t.kind == "MINUS" and self.peek().kind == "NUM":
            self.pos += 1
            vt = self.cur()
            self.pos += 1
            return PLit(-vt.value, line=t.line, col=t.col)
        if t.kind == "STAR":
            self.pos += 1
            return PWild(line=t.line, col=t.col)
        if t.kind == "KW":
            if t.value in ("true", "false"):
                self.pos += 1
                return PLit(t.value == "true", line=t.line, col=t.col)
            if t.value == "null":
                self.pos += 1
                return PLit(None, line=t.line, col=t.col)
        if t.kind == "IDENT":
            self.pos += 1
            if t.value == "_":
                return PWild(line=t.line, col=t.col)
            if self.at_kw("is", "isnt"):
                neg = self.cur().value == "isnt"
                self.pos += 1
                return PTyped(t.value, self.parse_type_name(), neg, line=t.line, col=t.col)
            return PBind(t.value, line=t.line, col=t.col)
        self.fail(f"cannot use `{t.value}` as a pattern", t,
                  "patterns are literals, names, `_`, `[...]` or `{...}`")
        return None  # unreachable

    # ------------------------------------------------------------ expressions
    def parse_expr(self, depth: int = 0):
        node = self.parse_ternary()
        while True:
            t = self.cur()
            if t.kind in ASSIGN_TOKENS:
                if depth > 0:
                    break
                self.pos += 1
                self.skip_newlines()
                value = self.parse_expr(0)
                op = "=" if t.kind == "ASSIGN" else COMPOUND[t.kind]
                if not _is_assignable(node):
                    self.fail("the left side of `=` must be a variable, index or member", t)
                node = Assign(op, node, value, line=t.line, col=t.col)
                continue
            if t.kind == "PIPEALL" or self.starts_pipe():
                self.pos += 2 if t.kind == "BAR" else 1
                self.skip_newlines()
                node = self.parse_pipe_rhs(node, t.kind == "PIPEALL")
                continue
            if t.kind in ("PLUSPLUS", "MINUSMINUS"):
                if depth > 0 or not _is_assignable(node):
                    break
                self.pos += 1
                op = "+" if t.kind == "PLUSPLUS" else "-"
                node = Assign("=", node,
                              Binary(op, node, Num(1.0, line=t.line), line=t.line, col=t.col),
                              line=t.line, col=t.col)
                continue
            break
        return node

    def parse_pipe_rhs(self, left, all_: bool):
        t = self.prev()
        line = t.line
        if self.at("DOT") or self.at("QMARK_DOT"):
            optional = self.cur().kind == "QMARK_DOT"
            self.pos += 1
            name = self.expect("IDENT", "a method name after `|> .`").value
            callee = Member(left, name, optional, line=line)
            args, kwargs = ([], [])
            if self.at("LPAREN"):
                args, kwargs = self.parse_call_args()
            return Pipe(callee, args, kwargs, all_, line=line)
        callee = self.parse_postfix()
        args, kwargs = [], []
        if isinstance(callee, Call):
            args, kwargs, callee = list(callee.args), list(callee.kwargs), callee.callee
        args = (args + [left]) if all_ else ([left] + args)
        return Pipe(callee, args, kwargs, all_, line=line)

    def skip_newlines(self):
        """A line may end right after an operator; the expression continues."""
        while self.at("NEWLINE"):
            self.pos += 1

    def parse_ternary(self):
        node = self.parse_binary(0)
        while True:
            if self.at("QMARK"):
                t = self.cur()
                self.pos += 1
                self.skip_newlines()
                then = self.parse_expr(0)
                self.expect("COLON", "`:` in a `? :` expression")
                self.skip_newlines()
                other = self.parse_expr(0)
                node = Ternary(node, then, other, line=t.line, col=t.col)
                continue
            if self.at("QMARKCOLON"):
                t = self.cur()
                self.pos += 1
                self.skip_newlines()
                node = Ternary(node, node, self.parse_expr(0), line=t.line, col=t.col)
                continue
            if self.at("QMARKQMARK"):
                t = self.cur()
                self.pos += 1
                self.skip_newlines()
                node = Elvis(node, self.parse_binary(0), line=t.line, col=t.col)
                continue
            break
        return node

    def parse_binary(self, level: int):
        if level >= TOP_LEVEL:
            return self.parse_power()
        if level == CMP_LEVEL:
            return self.parse_comparison(level)
        if level == RANGE_LEVEL:
            return self.parse_range()
        kinds, kws = LEVELS[level]
        node = self.parse_binary(level + 1)
        while True:
            t = self.cur()
            op = None
            if t.kind in kinds and not (t.kind == "BAR" and self.starts_pipe()):
                op = kinds[t.kind]
            elif kws and t.kind == "KW" and t.value in kws:
                op = t.value
            if op is None:
                break
            self.pos += 1
            self.skip_newlines()
            if op in ("is", "isnt") and self.cur().value in TYPE_WORDS \
                    and self.cur().kind in ("IDENT", "KW"):
                tt = self.cur()
                self.pos += 1
                right = Str(tt.value, line=tt.line, col=tt.col)
            else:
                right = self.parse_binary(level + 1)
            node = Binary(op, node, right, line=t.line, col=t.col)
        return node

    def parse_comparison(self, level: int):
        """Comparisons chain: `1 < x < 10` means both halves at once."""
        kinds = LEVELS[level][0]
        node = self.parse_binary(level + 1)
        ops, operands = [], [node]
        while self.cur().kind in kinds:
            t = self.cur()
            self.pos += 1
            self.skip_newlines()
            ops.append(kinds[t.kind])
            operands.append(self.parse_binary(level + 1))
        if not ops:
            return node
        if len(ops) == 1:
            return Binary(ops[0], operands[0], operands[1],
                          line=node.line, col=node.col)
        return ChainCompare(ops, operands, line=node.line, col=node.col)

    def parse_range(self):
        """`a..b`, `a..=b`, `a..b..step`.

        This sits between the shift and additive rows, so both bounds may be
        ordinary arithmetic: `0..xs.len() - 1` is `0..(xs.len() - 1)`.
        """
        t0 = self.cur()
        inner = RANGE_LEVEL + 1
        node = self.parse_binary(inner)
        if self.cur().kind == "DOT" and self.peek().kind == "DOT":
            self.pos += 2
            inclusive = bool(self.eat("ASSIGN"))
            self.skip_newlines()
            hi = None
            if not self.at_range_stop():
                hi = self.parse_binary(inner)
            step = None
            if self.cur().kind == "DOT" and self.peek().kind == "DOT":
                self.pos += 2
                step = self.parse_binary(inner)
            return RangeLit(node, hi, step, inclusive, line=t0.line, col=t0.col)
        return node

    def parse_power(self):
        node = self.parse_unary()
        if self.at("POWER"):
            t = self.cur()
            self.pos += 1
            return Binary("**", node, self.parse_power(), line=t.line, col=t.col)
        return node

    def parse_unary(self):
        t = self.cur()
        if t.kind == "MINUS":
            self.pos += 1
            return Unary("-", self.parse_unary(), line=t.line, col=t.col)
        if t.kind == "PLUS":
            self.pos += 1
            return self.parse_unary()
        if t.kind in ("BANG", "TILDE"):
            self.pos += 1
            return Unary("not" if t.kind == "BANG" else "~", self.parse_unary(),
                         line=t.line, col=t.col)
        if t.kind == "KW" and t.value == "not":
            self.pos += 1
            return Unary("not", self.parse_unary(), line=t.line, col=t.col)
        if t.kind == "KW" and t.value == "new":
            self.pos += 1
            target = self.parse_primary()
            while self.at("DOT") or self.at("QMARK_DOT"):
                optional = self.cur().kind == "QMARK_DOT"
                self.pos += 1
                nt = self.cur()
                if nt.kind not in ("IDENT", "SIGVAR", "KW"):
                    self.fail(f"expected a name after `.` but found `{nt.value}`")
                self.pos += 1
                target = Member(target, nt.value, optional, line=t.line, col=t.col)
            args, kwargs = ([], [])
            if self.at("LPAREN"):
                args, kwargs = self.parse_call_args()
            node = Call(target, args, kwargs, True, line=t.line, col=t.col)
            # `new B().name()` keeps chaining after the object is built
            return self.parse_postfix_tail(node)
        return self.parse_postfix()

    def parse_postfix(self):
        return self.parse_postfix_tail(self.parse_primary())

    def parse_postfix_tail(self, node):
        while True:
            t = self.cur()
            if t.kind == "NEWLINE" and self.line_starts_a_method():
                # a chain may continue on the next line, indented under it
                self.skip_newlines()
                t = self.cur()
            if t.kind == "LPAREN":
                args, kwargs = self.parse_call_args()
                node = Call(node, args, kwargs, False, line=t.line, col=t.col)
                continue
            if t.kind in ("DOT", "QMARK_DOT"):
                if t.kind == "DOT" and self.peek().kind == "DOT":
                    break        # `..` belongs to a range, not to member access
                optional = t.kind == "QMARK_DOT"
                self.pos += 1
                nt = self.cur()
                if nt.kind in ("IDENT", "SIGVAR") or nt.kind == "KW":
                    self.pos += 1
                    node = Member(node, nt.value, optional, line=t.line, col=t.col)
                    continue
                self.fail(f"expected a name after `.` but found `{nt.value}`")
            if t.kind == "LBRACKET":
                self.pos += 1
                self.skip_seps()
                if self.cur().kind == "DOT" and self.peek().kind == "DOT":
                    # `xs[..3]` -- an open-ended slice
                    self.pos += 2
                    inclusive = self.eat("ASSIGN")   # `xs[..=3]` includes index 3
                    hi = None if (self.at("RBRACKET") or self.at("COLON")) \
                        else self.parse_expr()
                    if inclusive and hi is not None:
                        hi = Binary("+", hi, Num(1.0, line=t.line), line=t.line)
                    step = None
                    if self.eat("COLON"):
                        step = None if self.at("RBRACKET") else self.parse_expr()
                    self.expect("RBRACKET", "`]`")
                    node = Slice(node, None, hi, step, line=t.line, col=t.col)
                    continue
                if self.at("COLON"):
                    self.pos += 1
                    hi = None if (self.at("RBRACKET") or self.at("COLON")) \
                        else self.parse_expr()
                    step = None
                    if self.eat("COLON"):
                        step = None if self.at("RBRACKET") else self.parse_expr()
                    self.expect("RBRACKET", "`]`")
                    node = Slice(node, None, hi, step, line=t.line, col=t.col)
                    continue
                first = self.parse_expr()
                if isinstance(first, RangeLit):
                    # `xs[1..3]` and `xs[1..=3]` are slices
                    hi = first.hi
                    if hi is not None and first.inclusive:
                        hi = Binary("+", hi, Num(1.0, line=first.line), line=first.line)
                    self.expect("RBRACKET", "`]`")
                    node = Slice(node, first.lo, hi, first.step, line=t.line, col=t.col)
                    continue
                if self.eat("COLON"):
                    hi = None if (self.at("RBRACKET") or self.at("COLON")) \
                        else self.parse_expr()
                    step = None
                    if self.eat("COLON"):
                        step = None if self.at("RBRACKET") else self.parse_expr()
                    self.expect("RBRACKET", "`]`")
                    node = Slice(node, first, hi, step, line=t.line, col=t.col)
                    continue
                self.expect("RBRACKET", "`]`")
                node = Index(node, first, line=t.line, col=t.col)
                continue
            break
        return node

    def parse_call_args(self):
        self.expect("LPAREN", "`(`")
        args, kwargs = [], []
        self.skip_seps()
        while not self.at("RPAREN"):
            if self.at("EOF"):
                self.fail("unexpected end of file", self.prev(),
                          "this call is missing its `)`")
            if self.at("STAR"):
                self.pos += 1
                args.append(("*", self.parse_expr()))
            elif self.at("POWER"):
                self.pos += 1
                args.append(("**", self.parse_expr()))
            elif (self.cur().kind in ("IDENT", "KW") and self.peek().kind == "COLON"
                  and self.peek(2).kind != "COLON"):
                name = self.cur().value
                self.pos += 2
                kwargs.append((name, self.parse_expr()))
            else:
                args.append(self.parse_expr())
            self.skip_seps()
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RPAREN", "`)`")
        return args, kwargs

    # -------------------------------------------------------------- primary
    def parse_primary(self):
        t = self.cur()

        if t.kind == "NUM":
            self.pos += 1
            return Num(t.value, line=t.line, col=t.col)

        if t.kind == "STR":
            self.pos += 1
            if isinstance(t.value, str):
                return Str(t.value, line=t.line, col=t.col)
            chunks = []
            for part in t.value:
                if isinstance(part, str):
                    chunks.append(Str(part, line=t.line, col=t.col))
                else:
                    chunks.append(Parser(part[1], self.src, self.path).parse_expr())
            return Str(chunks, line=t.line, col=t.col)

        if t.kind in ("IDENT", "SIGVAR"):
            self.pos += 1
            return Ident(t.value, line=t.line, col=t.col)

        if t.kind == "SIGATTR":
            self.pos += 1
            return SigAttr(t.value, line=t.line, col=t.col)

        if t.kind == "KW":
            if t.value == "true":
                self.pos += 1
                return Bool(True, line=t.line, col=t.col)
            if t.value == "false":
                self.pos += 1
                return Bool(False, line=t.line, col=t.col)
            if t.value == "null":
                self.pos += 1
                return Null(line=t.line, col=t.col)
            if t.value in ("self", "super"):
                self.pos += 1
                return Ident(t.value, line=t.line, col=t.col)
            if t.value == "if":
                return self.parse_if()
            if t.value == "match":
                return self.parse_match()
            if t.value == "try":
                return self.parse_try()
            if t.value == "fn":
                self.pos += 1
                params = self.parse_params()
                return self.parse_lambda_tail(params, t)
            if t.value in TYPE_WORDS:
                self.pos += 1
                return Ident(t.value, line=t.line, col=t.col)

        if t.kind == "LBRACKET":
            return self.parse_list_lit()

        if t.kind == "LBRACE":
            return self.parse_map_lit()

        if t.kind == "LPAREN":
            self.pos += 1
            self.skip_seps()
            if self.at("RPAREN"):
                self.pos += 1
                if self.at("ARROW") or self.at("FAT_ARROW"):
                    return self.parse_lambda_tail([], t)
                return ListLit([], [], line=t.line, col=t.col)
            saved = self.pos
            params = self.try_parse_lambda_params()
            if params is not None:
                return self.parse_lambda_tail(params, t)
            self.pos = saved
            first = self.parse_expr()
            self.skip_seps()
            if self.at("COMMA"):
                items = [first]
                while self.eat("COMMA"):
                    self.skip_seps()
                    if self.at("RPAREN"):
                        break
                    items.append(self.parse_expr())
                    self.skip_seps()
                self.expect("RPAREN", "`)`")
                return ListLit(items, [False] * len(items), line=t.line, col=t.col)
            self.expect("RPAREN", "`)`")
            return Paren(first, line=t.line, col=t.col)

        shown = t.value if t.value is not None else "end of input"
        self.fail(f"unexpected `{shown}`", t, "an expression was expected here")
        return None  # unreachable

    def try_parse_lambda_params(self):
        """Read `(a, b=1, *rest)` and confirm it is followed by `->` / `=>`."""
        if not (self.at("IDENT") or self.at("SIGVAR") or self.at("STAR")
                or self.at("LBRACKET") or self.at("LBRACE")):
            return None
        start = self.pos
        params = []
        try:
            while True:
                rest = False
                if self.at("STAR"):
                    self.pos += 1
                    rest = True
                nt = self.cur()
                pattern = None
                if nt.kind in ("LBRACKET", "LBRACE"):
                    pattern = self.parse_pattern()
                    pname = pattern_label(pattern)
                elif nt.kind in ("IDENT", "SIGVAR"):
                    self.pos += 1
                    pname = nt.value
                else:
                    self.pos = start
                    return None
                default = self.parse_expr() if self.eat("ASSIGN") else None
                params.append({"name": pname, "default": default, "rest": rest,
                               "kwrest": False, "type": None, "line": nt.line,
                               "pattern": pattern})
                self.skip_seps()
                if not self.eat("COMMA"):
                    break
                self.skip_seps()
                if self.at("RPAREN"):
                    break
            if not self.at("RPAREN"):
                self.pos = start
                return None
            self.pos += 1
        except OmniSyntaxError:
            self.pos = start
            return None
        if self.at("ARROW") or self.at("FAT_ARROW"):
            return params
        self.pos = start
        return None

    def parse_lambda_tail(self, params, t):
        if not (self.at("ARROW") or self.at("FAT_ARROW")):
            if self.at("LBRACE") and not self.brace_starts_a_map():
                # `fn (x) { ... }` -- a block body needs no arrow
                bt = self.cur()
                return Lambda(params, self.block_of(self.parse_block(), bt.line, bt.col),
                              True, line=t.line, col=t.col)
            self.fail(f"expected `->` after the parameter list but found `{self.cur().value}`")
        self.pos += 1
        if self.at("LBRACE"):
            bt = self.cur()
            if self.brace_starts_a_map():
                # `(r) -> {name: r.a}` builds a map, it is not a block
                return Lambda(params, self.parse_map_lit(), False,
                              line=t.line, col=t.col)
            return Lambda(params, self.block_of(self.parse_block(), bt.line, bt.col),
                          True, line=t.line, col=t.col)
        return Lambda(params, self.parse_expr(), False, line=t.line, col=t.col)

    def line_starts_a_method(self):
        """True when the next line begins with `.` or `?.` (but not `..`)."""
        nxt = self.peek()
        if nxt.kind == "QMARK_DOT":
            return True
        return nxt.kind == "DOT" and self.peek(2).kind != "DOT"

    def brace_starts_a_map(self):
        """Tell `{a: 1}` (a map) from `{ a }` (a block with one statement).

        OmniScript has no labelled statements, so `name:` straight after `{`
        can only mean a map literal.
        """
        j = self.significant_after(self.pos + 1)
        if j is None:
            return False
        nxt = self.toks[j]
        if nxt.kind in ("STAR", "POWER"):
            return True                      # `{*other}` / `{**other}` spread
        if nxt.kind == "LBRACKET":
            # `{[expr]: value}` -- a computed key, so still a map
            depth, k = 0, j
            while k < len(self.toks):
                kind = self.toks[k].kind
                if kind == "LBRACKET":
                    depth += 1
                elif kind == "RBRACKET":
                    depth -= 1
                    if depth == 0:
                        after = self.significant_after(k + 1)
                        return after is not None and self.toks[after].kind == "COLON"
                elif kind == "EOF":
                    break
                k += 1
            return False
        if nxt.kind in ("IDENT", "STR", "NUM", "SIGVAR") or \
                (nxt.kind == "KW" and nxt.value in ("true", "false", "null")):
            after = self.significant_after(j + 1)
            return after is not None and self.toks[after].kind == "COLON"
        return False

    def significant_after(self, index: int):
        """The next index at or after `index` that is not a blank line."""
        while index < len(self.toks) and self.toks[index].kind in ("NEWLINE", "SEMI"):
            index += 1
        return index if index < len(self.toks) else None

    def parse_list_lit(self):
        t = self.expect("LBRACKET", "`[`")
        items, spread = [], []
        self.skip_seps()
        while not self.at("RBRACKET"):
            if self.at("EOF"):
                self.fail("unexpected end of file", t, "this list is missing its `]`")
            if self.at("STAR") and self.peek().kind != "STAR":
                self.pos += 1
                items.append(self.parse_expr())
                spread.append(True)
            else:
                items.append(self.parse_expr())
                spread.append(False)
            self.skip_seps()
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RBRACKET", "`]`")
        return ListLit(items, spread, line=t.line, col=t.col)

    def parse_map_lit(self):
        t = self.expect("LBRACE", "`{`")
        entries = []
        self.skip_seps()
        while not self.at("RBRACE"):
            if self.at("EOF"):
                self.fail("unexpected end of file", t, "this map is missing its `}`")
            if self.at("STAR") or self.at("POWER"):
                self.pos += 1
                entries.append((None, self.parse_expr(), True))
            else:
                kt = self.cur()
                if kt.kind in ("IDENT", "SIGVAR") or (kt.kind == "KW" and kt.value in TYPE_WORDS):
                    self.pos += 1
                    key = kt.value
                elif kt.kind == "STR":
                    self.pos += 1
                    if not isinstance(kt.value, str):
                        self.fail("map keys cannot contain interpolation", kt,
                                  "use `[expr]: value` instead")
                    key = kt.value
                elif kt.kind == "NUM":
                    self.pos += 1
                    key = kt.value
                elif kt.kind == "LBRACKET":
                    self.pos += 1
                    key = self.parse_expr()
                    self.expect("RBRACKET", "`]`")
                elif kt.kind == "MINUS" and self.peek().kind == "NUM":
                    self.pos += 2
                    key = -self.toks[self.pos - 1].value
                else:
                    self.fail(f"cannot use `{kt.value}` as a map key")
                self.expect("COLON", "`:` after this map key")
                entries.append((key, self.parse_expr(), False))
            self.skip_seps()
            if not self.eat("COMMA"):
                break
            self.skip_seps()
        self.expect("RBRACE", "`}`")
        return MapLit(entries, line=t.line, col=t.col)


def _is_assignable(node) -> bool:
    return isinstance(node, (Ident, Index, Member, Slice))


def parse(src: str, path: str = "<stdin>") -> list:
    return Parser(tokenize(src, path), src, path).parse_program()
