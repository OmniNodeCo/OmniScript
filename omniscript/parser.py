from .tokens import *
from .errors import OmniSyntaxError


class NumberNode:
    def __init__(self, value):
        self.value = value


class StringNode:
    def __init__(self, value):
        self.value = value


class BoolNode:
    def __init__(self, value):
        self.value = value


class ArrayNode:
    def __init__(self, elements):
        self.elements = elements


class IndexNode:
    def __init__(self, array_expr, index_expr):
        self.array_expr = array_expr
        self.index_expr = index_expr


class VarAccessNode:
    def __init__(self, name):
        self.name = name


class VarAssignNode:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class LetNode:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class BinOpNode:
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right


class UnaryOpNode:
    def __init__(self, op, node):
        self.op = op
        self.node = node


class IfNode:
    def __init__(self, cases, else_body):
        self.cases = cases
        self.else_body = else_body


class WhileNode:
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body


class LoopNode:
    def __init__(self, var_name, start, end, body):
        self.var_name = var_name
        self.start = start
        self.end = end
        self.body = body


class FuncDefNode:
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body


class FuncCallNode:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class ReturnNode:
    def __init__(self, value):
        self.value = value


class ShowNode:
    def __init__(self, args):
        self.args = args


class InputNode:
    def __init__(self, prompt):
        self.prompt = prompt


class BlockNode:
    def __init__(self, statements):
        self.statements = statements


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def current(self):
        return self.tokens[self.pos]

    def eat(self, type_):
        tok = self.current()
        if tok.type != type_:
            raise OmniSyntaxError(
                f"Expected {type_}, got {tok.type} ({tok.value!r})", tok.line
            )
        self.pos += 1
        return tok

    def skip_newlines(self):
        while self.current().type == TT_NEWLINE:
            self.pos += 1

    def parse(self):
        stmts = self.statement_list()
        self.eat(TT_EOF)
        return BlockNode(stmts)

    def statement_list(self):
        stmts = []
        self.skip_newlines()
        while self.current().type not in (TT_EOF, TT_RBRACE):
            stmts.append(self.statement())
            self.skip_newlines()
        return stmts

    def statement(self):
        tok = self.current()

        if tok.type == TT_LET:
            return self.let_statement()
        elif tok.type == TT_FUNC:
            return self.func_def()
        elif tok.type == TT_IF:
            return self.if_statement()
        elif tok.type == TT_WHILE:
            return self.while_statement()
        elif tok.type == TT_LOOP:
            return self.loop_statement()
        elif tok.type == TT_RETURN:
            return self.return_statement()
        elif tok.type == TT_SHOW:
            return self.show_statement()
        elif tok.type == TT_IDENTIFIER:
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TT_ASSIGN:
                return self.assignment()
            return self.expr()
        else:
            return self.expr()

    def let_statement(self):
        self.eat(TT_LET)
        name = self.eat(TT_IDENTIFIER).value
        self.eat(TT_ASSIGN)
        value = self.expr()
        return LetNode(name, value)

    def assignment(self):
        name = self.eat(TT_IDENTIFIER).value
        self.eat(TT_ASSIGN)
        value = self.expr()
        return VarAssignNode(name, value)

    def func_def(self):
        self.eat(TT_FUNC)
        name = self.eat(TT_IDENTIFIER).value
        self.eat(TT_LPAREN)
        params = []
        if self.current().type != TT_RPAREN:
            params.append(self.eat(TT_IDENTIFIER).value)
            while self.current().type == TT_COMMA:
                self.eat(TT_COMMA)
                params.append(self.eat(TT_IDENTIFIER).value)
        self.eat(TT_RPAREN)
        body = self.block()
        return FuncDefNode(name, params, body)

    def if_statement(self):
        cases = []
        self.eat(TT_IF)
        cond = self.expr()
        body = self.block()
        cases.append((cond, body))

        self.skip_newlines()
        while self.current().type == TT_ELIF:
            self.eat(TT_ELIF)
            cond = self.expr()
            body = self.block()
            cases.append((cond, body))
            self.skip_newlines()

        else_body = None
        if self.current().type == TT_ELSE:
            self.eat(TT_ELSE)
            else_body = self.block()

        return IfNode(cases, else_body)

    def while_statement(self):
        self.eat(TT_WHILE)
        cond = self.expr()
        body = self.block()
        return WhileNode(cond, body)

    def loop_statement(self):
        self.eat(TT_LOOP)
        var_name = self.eat(TT_IDENTIFIER).value
        self.eat(TT_IN)
        start = self.expr()
        self.eat(TT_DOTDOT)
        end = self.expr()
        body = self.block()
        return LoopNode(var_name, start, end, body)

    def return_statement(self):
        self.eat(TT_RETURN)
        value = None
        if self.current().type not in (TT_NEWLINE, TT_RBRACE, TT_EOF):
            value = self.expr()
        return ReturnNode(value)

    def show_statement(self):
        self.eat(TT_SHOW)
        self.eat(TT_LPAREN)
        args = []
        if self.current().type != TT_RPAREN:
            args.append(self.expr())
            while self.current().type == TT_COMMA:
                self.eat(TT_COMMA)
                args.append(self.expr())
        self.eat(TT_RPAREN)
        return ShowNode(args)

    def block(self):
        self.skip_newlines()
        self.eat(TT_LBRACE)
        stmts = self.statement_list()
        self.eat(TT_RBRACE)
        return BlockNode(stmts)

    def expr(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.current().type == TT_OR:
            op = self.eat(TT_OR).value
            right = self.and_expr()
            left = BinOpNode(left, op, right)
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.current().type == TT_AND:
            op = self.eat(TT_AND).value
            right = self.not_expr()
            left = BinOpNode(left, op, right)
        return left

    def not_expr(self):
        if self.current().type == TT_NOT:
            op = self.eat(TT_NOT).value
            node = self.not_expr()
            return UnaryOpNode(op, node)
        return self.comparison()

    def comparison(self):
        left = self.arith()
        while self.current().type in (TT_EQ, TT_NEQ, TT_LT, TT_GT, TT_LTE, TT_GTE):
            op = self.current().value
            self.pos += 1
            right = self.arith()
            left = BinOpNode(left, op, right)
        return left

    def arith(self):
        left = self.term()
        while self.current().type in (TT_PLUS, TT_MINUS):
            op = self.current().value
            self.pos += 1
            right = self.term()
            left = BinOpNode(left, op, right)
        return left

    def term(self):
        left = self.unary()
        while self.current().type in (TT_MUL, TT_DIV, TT_MOD):
            op = self.current().value
            self.pos += 1
            right = self.unary()
            left = BinOpNode(left, op, right)
        return left

    def unary(self):
        if self.current().type == TT_MINUS:
            self.pos += 1
            node = self.unary()
            return UnaryOpNode('-', node)
        return self.postfix()

    def postfix(self):
        node = self.atom()
        while self.current().type == TT_LBRACKET:
            self.eat(TT_LBRACKET)
            idx = self.expr()
            self.eat(TT_RBRACKET)
            node = IndexNode(node, idx)
        return node

    def atom(self):
        tok = self.current()

        if tok.type == TT_INT:
            self.pos += 1
            return NumberNode(tok.value)

        if tok.type == TT_FLOAT:
            self.pos += 1
            return NumberNode(tok.value)

        if tok.type == TT_STRING:
            self.pos += 1
            return StringNode(tok.value)

        if tok.type == TT_BOOL:
            self.pos += 1
            return BoolNode(tok.value)

        if tok.type == TT_INPUT:
            self.pos += 1
            self.eat(TT_LPAREN)
            prompt = None
            if self.current().type != TT_RPAREN:
                prompt = self.expr()
            self.eat(TT_RPAREN)
            return InputNode(prompt)

        if tok.type == TT_IDENTIFIER:
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TT_LPAREN:
                name = self.eat(TT_IDENTIFIER).value
                self.eat(TT_LPAREN)
                args = []
                if self.current().type != TT_RPAREN:
                    args.append(self.expr())
                    while self.current().type == TT_COMMA:
                        self.eat(TT_COMMA)
                        args.append(self.expr())
                self.eat(TT_RPAREN)
                return FuncCallNode(name, args)
            self.pos += 1
            return VarAccessNode(tok.value)

        if tok.type == TT_LPAREN:
            self.eat(TT_LPAREN)
            node = self.expr()
            self.eat(TT_RPAREN)
            return node

        if tok.type == TT_LBRACKET:
            self.eat(TT_LBRACKET)
            elements = []
            if self.current().type != TT_RBRACKET:
                elements.append(self.expr())
                while self.current().type == TT_COMMA:
                    self.eat(TT_COMMA)
                    elements.append(self.expr())
            self.eat(TT_RBRACKET)
            return ArrayNode(elements)

        raise OmniSyntaxError(f"Unexpected token: {tok.type} ({tok.value!r})", tok.line)