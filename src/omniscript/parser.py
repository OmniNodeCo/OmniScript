"""Recursive-descent and Pratt-style parser for OmniScript."""

from __future__ import annotations

from . import ast_nodes as ast
from .errors import OmniSyntaxError
from .tokens import Token, TokenKind as K


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.current = 0

    def parse(self) -> ast.Program:
        statements: list[ast.Stmt] = []
        while not self._at_end():
            statements.append(self._declaration())
        return ast.Program(statements)

    def _declaration(self) -> ast.Stmt:
        if self._match(K.BIND):
            return self._var_declaration(True, self._previous())
        if self._match(K.SEAL):
            return self._var_declaration(False, self._previous())
        if self._match(K.CRAFT):
            return self._function_declaration(self._previous())
        if self._match(K.SHAPE):
            return self._shape_declaration(self._previous())
        return self._statement()

    def _var_declaration(self, mutable: bool, start: Token) -> ast.VarDecl:
        name = self._consume(K.IDENTIFIER, "expected a name after declaration keyword")
        self._consume(K.DECLARE, "expected ':=' between a name and its initial value")
        initializer = self._expression()
        self._finish_statement()
        return ast.VarDecl(start.span, name.lexeme, initializer, mutable)

    def _parameters(self) -> list[ast.Parameter]:
        parameters: list[ast.Parameter] = []
        saw_default = False
        if not self._check(K.RIGHT_PAREN):
            while True:
                if len(parameters) >= 255:
                    raise self._error(self._peek(), "a craft or shape cannot have more than 255 parameters")
                name = self._consume(K.IDENTIFIER, "expected parameter name")
                default = None
                if self._match(K.DECLARE):
                    saw_default = True
                    default = self._expression()
                elif saw_default:
                    raise self._error(name, "required parameters cannot follow optional parameters")
                parameters.append(ast.Parameter(name.lexeme, default, name.span))
                if not self._match(K.COMMA):
                    break
        self._consume(K.RIGHT_PAREN, "expected ')' after parameters")
        return parameters

    def _function_declaration(self, start: Token) -> ast.FuncDecl:
        name = self._consume(K.IDENTIFIER, "expected a craft name")
        self._consume(K.LEFT_PAREN, "expected '(' after craft name")
        parameters = self._parameters()
        body = self._block("expected '{' before craft body")
        return ast.FuncDecl(start.span, name.lexeme, parameters, body.statements)

    def _shape_declaration(self, start: Token) -> ast.ShapeDecl:
        name = self._consume(K.IDENTIFIER, "expected a shape name")
        self._consume(K.LEFT_PAREN, "expected '(' after shape name")
        parameters = self._parameters()
        self._consume(K.LEFT_BRACE, "expected '{' before shape methods")
        methods: list[ast.FuncDecl] = []
        while not self._check(K.RIGHT_BRACE) and not self._at_end():
            craft = self._consume(K.CRAFT, "only craft declarations are allowed inside a shape")
            methods.append(self._function_declaration(craft))
        self._consume(K.RIGHT_BRACE, "expected '}' after shape")
        return ast.ShapeDecl(start.span, name.lexeme, parameters, methods)

    def _statement(self) -> ast.Stmt:
        if self._match(K.WHEN):
            return self._if_statement(self._previous())
        if self._match(K.WHILST):
            return self._while_statement(self._previous())
        if self._match(K.EACH):
            return self._each_statement(self._previous())
        if self._match(K.RETURN):
            return self._return_statement(self._previous())
        if self._match(K.BREAK):
            token = self._previous()
            self._finish_statement()
            return ast.BreakStmt(token.span)
        if self._match(K.CONTINUE):
            token = self._previous()
            self._finish_statement()
            return ast.ContinueStmt(token.span)
        if self._match(K.EMIT):
            return self._emit_statement(self._previous())
        if self._match(K.ASSERT):
            return self._assert_statement(self._previous())
        if self._match(K.USE):
            return self._use_statement(self._previous())
        if self._match(K.LEFT_BRACE):
            start = self._previous()
            return self._block_after_open(start)
        expression = self._expression()
        self._finish_statement()
        return ast.ExpressionStmt(expression.span, expression)

    def _if_statement(self, start: Token) -> ast.IfStmt:
        condition = self._expression()
        then_branch = self._block("expected '{' after when condition")
        else_branch: ast.Block | ast.IfStmt | None = None
        if self._match(K.OTHERWISE):
            if self._match(K.WHEN):
                else_branch = self._if_statement(self._previous())
            else:
                else_branch = self._block("expected 'when' or '{' after otherwise")
        return ast.IfStmt(start.span, condition, then_branch, else_branch)

    def _while_statement(self, start: Token) -> ast.WhileStmt:
        condition = self._expression()
        return ast.WhileStmt(start.span, condition, self._block("expected '{' after whilst condition"))

    def _each_statement(self, start: Token) -> ast.EachStmt:
        item = self._consume(K.IDENTIFIER, "expected item name after each")
        index_name = None
        if self._match(K.COMMA):
            index_name = self._consume(K.IDENTIFIER, "expected index name after ','").lexeme
        self._consume(K.IN, "expected 'in' in each loop")
        iterable = self._expression()
        body = self._block("expected '{' after each iterable")
        return ast.EachStmt(start.span, item.lexeme, index_name, iterable, body)

    def _return_statement(self, start: Token) -> ast.ReturnStmt:
        value = None if self._statement_ended() else self._expression()
        self._finish_statement()
        return ast.ReturnStmt(start.span, value)

    def _emit_statement(self, start: Token) -> ast.EmitStmt:
        if self._statement_ended():
            raise self._error(self._peek(), "emit expects at least one value")
        values = [self._expression()]
        while self._match(K.COMMA):
            values.append(self._expression())
        self._finish_statement()
        return ast.EmitStmt(start.span, values)

    def _assert_statement(self, start: Token) -> ast.AssertStmt:
        condition = self._expression()
        message = self._expression() if self._match(K.COMMA) else None
        self._finish_statement()
        return ast.AssertStmt(start.span, condition, message)

    def _use_statement(self, start: Token) -> ast.UseStmt:
        module = self._consume(K.STRING, "expected a quoted module name after use")
        if self._match(K.AS):
            alias = self._consume(K.IDENTIFIER, "expected an alias after as").lexeme
        else:
            raw = str(module.literal).replace("\\", "/").rsplit("/", 1)[-1]
            alias = raw.rsplit(".", 1)[0]
            if not alias.isidentifier():
                raise self._error(module, "module needs an explicit identifier alias")
        self._finish_statement()
        return ast.UseStmt(start.span, str(module.literal), alias)

    def _block(self, message: str) -> ast.Block:
        opening = self._consume(K.LEFT_BRACE, message)
        return self._block_after_open(opening)

    def _block_after_open(self, opening: Token) -> ast.Block:
        statements: list[ast.Stmt] = []
        while not self._check(K.RIGHT_BRACE) and not self._at_end():
            statements.append(self._declaration())
        self._consume(K.RIGHT_BRACE, "expected '}' after block")
        return ast.Block(opening.span, statements)

    def _expression(self) -> ast.Expr:
        return self._assignment()

    def _assignment(self) -> ast.Expr:
        expression = self._conditional()
        if self._match(K.ASSIGN):
            arrow = self._previous()
            value = self._assignment()
            if isinstance(expression, ast.Variable):
                return ast.Assign(expression.span, expression.name, value)
            if isinstance(expression, ast.Get):
                return ast.SetExpr(expression.span, expression.target, expression.name, value)
            if isinstance(expression, ast.Index):
                return ast.IndexSet(expression.span, expression.target, expression.index, value)
            raise self._error(arrow, "invalid assignment target")
        return expression

    def _conditional(self) -> ast.Expr:
        expression = self._pipeline()
        if self._match(K.QUESTION):
            if_true = self._expression()
            self._consume(K.COLON, "expected ':' in conditional expression")
            if_false = self._conditional()
            return ast.Conditional(expression.span, expression, if_true, if_false)
        return expression

    def _pipeline(self) -> ast.Expr:
        expression = self._or()
        while self._match(K.PIPE):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._or())
        return expression

    def _or(self) -> ast.Expr:
        expression = self._and()
        while self._match(K.OR):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._and())
        return expression

    def _and(self) -> ast.Expr:
        expression = self._coalesce()
        while self._match(K.AND):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._coalesce())
        return expression

    def _coalesce(self) -> ast.Expr:
        expression = self._equality()
        while self._match(K.COALESCE):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._equality())
        return expression

    def _equality(self) -> ast.Expr:
        expression = self._comparison()
        while self._match(K.EQUAL, K.NOT_EQUAL):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._comparison())
        return expression

    def _comparison(self) -> ast.Expr:
        expression = self._range()
        while self._match(K.LESS, K.LESS_EQUAL, K.GREATER, K.GREATER_EQUAL, K.IN):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._range())
        return expression

    def _range(self) -> ast.Expr:
        expression = self._term()
        while self._match(K.RANGE):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._term())
        return expression

    def _term(self) -> ast.Expr:
        expression = self._factor()
        while self._match(K.PLUS, K.MINUS):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._factor())
        return expression

    def _factor(self) -> ast.Expr:
        expression = self._power()
        while self._match(K.STAR, K.SLASH, K.PERCENT):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._power())
        return expression

    def _power(self) -> ast.Expr:
        expression = self._unary()
        if self._match(K.POWER):
            operator = self._previous()
            expression = ast.Binary(operator.span, expression, operator.kind, self._power())
        return expression

    def _unary(self) -> ast.Expr:
        if self._match(K.NOT, K.MINUS, K.PLUS):
            operator = self._previous()
            return ast.Unary(operator.span, operator.kind, self._unary())
        return self._call()

    def _call(self) -> ast.Expr:
        expression = self._primary()
        while True:
            if self._match(K.LEFT_PAREN):
                arguments: list[ast.Expr] = []
                if not self._check(K.RIGHT_PAREN):
                    while True:
                        if len(arguments) >= 255:
                            raise self._error(self._peek(), "a call cannot have more than 255 arguments")
                        arguments.append(self._expression())
                        if not self._match(K.COMMA):
                            break
                closing = self._consume(K.RIGHT_PAREN, "expected ')' after arguments")
                expression = ast.Call(closing.span, expression, arguments)
            elif self._match(K.DOT):
                name = self._consume(K.IDENTIFIER, "expected property name after '.'")
                expression = ast.Get(name.span, expression, name.lexeme)
            elif self._match(K.LEFT_BRACKET):
                index = self._expression()
                closing = self._consume(K.RIGHT_BRACKET, "expected ']' after index")
                expression = ast.Index(closing.span, expression, index)
            else:
                break
        return expression

    def _primary(self) -> ast.Expr:
        if self._match(K.FALSE):
            return ast.Literal(self._previous().span, False)
        if self._match(K.TRUE):
            return ast.Literal(self._previous().span, True)
        if self._match(K.VOID):
            return ast.Literal(self._previous().span, None)
        if self._match(K.NUMBER, K.STRING):
            token = self._previous()
            return ast.Literal(token.span, token.literal)
        if self._match(K.IDENTIFIER):
            token = self._previous()
            return ast.Variable(token.span, token.lexeme)
        if self._match(K.LEFT_PAREN):
            expression = self._expression()
            self._consume(K.RIGHT_PAREN, "expected ')' after expression")
            return expression
        if self._match(K.LEFT_BRACKET):
            opening = self._previous()
            items: list[ast.Expr] = []
            if not self._check(K.RIGHT_BRACKET):
                while True:
                    items.append(self._expression())
                    if not self._match(K.COMMA):
                        break
            self._consume(K.RIGHT_BRACKET, "expected ']' after list")
            return ast.ListExpr(opening.span, items)
        if self._match(K.LEFT_BRACE):
            opening = self._previous()
            entries: list[tuple[ast.Expr, ast.Expr]] = []
            if not self._check(K.RIGHT_BRACE):
                while True:
                    if self._check(K.IDENTIFIER) and self._peek_next().kind == K.COLON:
                        key_token = self._advance()
                        key: ast.Expr = ast.Literal(key_token.span, key_token.lexeme)
                    else:
                        key = self._expression()
                    self._consume(K.COLON, "expected ':' between map key and value")
                    entries.append((key, self._expression()))
                    if not self._match(K.COMMA):
                        break
            self._consume(K.RIGHT_BRACE, "expected '}' after map")
            return ast.MapExpr(opening.span, entries)
        raise self._error(self._peek(), "expected an expression")

    def _finish_statement(self) -> None:
        if self._match(K.SEMICOLON):
            return
        if self._check(K.RIGHT_BRACE) or self._at_end():
            return
        if self._previous().span.end_line is not None and self._previous().span.end_line < self._peek().span.line:
            return
        raise self._error(self._peek(), "expected ';' or a newline after statement")

    def _statement_ended(self) -> bool:
        return (
            self._check(K.SEMICOLON)
            or self._check(K.RIGHT_BRACE)
            or self._at_end()
            or (self.current > 0 and (self._previous().span.end_line or 0) < self._peek().span.line)
        )

    def _match(self, *kinds: K) -> bool:
        for kind in kinds:
            if self._check(kind):
                self._advance()
                return True
        return False

    def _consume(self, kind: K, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._error(self._peek(), message)

    def _check(self, kind: K) -> bool:
        return self._peek().kind == kind

    def _advance(self) -> Token:
        if not self._at_end():
            self.current += 1
        return self._previous()

    def _at_end(self) -> bool:
        return self._peek().kind == K.EOF

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _peek_next(self) -> Token:
        return self.tokens[min(self.current + 1, len(self.tokens) - 1)]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    @staticmethod
    def _error(token: Token, message: str) -> OmniSyntaxError:
        return OmniSyntaxError(message, token.span)
