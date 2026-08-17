"""A lightweight semantic checker for OmniScript programs."""

from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .errors import OmniCheckError, Span


BUILTIN_NAMES = {
    "len",
    "kind",
    "text",
    "number",
    "integer",
    "truthy",
    "clock",
    "input",
    "keys",
    "values",
    "has",
    "push",
    "pop",
    "sort",
    "reverse",
    "map",
    "filter",
    "reduce",
    "read",
    "write",
    "panic",
    "__file__",
}


@dataclass(slots=True)
class Symbol:
    mutable: bool
    span: Span


class Checker:
    def __init__(self, extra_names: set[str] | None = None):
        initial = BUILTIN_NAMES | (extra_names or set())
        self.scopes: list[dict[str, Symbol]] = [
            {name: Symbol(False, Span.synthetic("<builtin>")) for name in initial}
        ]
        self.errors: list[OmniCheckError] = []
        self.function_depth = 0
        self.loop_depth = 0

    def check(self, program: ast.Program) -> list[OmniCheckError]:
        self.scopes.append({})
        for statement in program.statements:
            self._statement(statement)
        self.scopes.pop()
        return self.errors

    def _declare(self, name: str, mutable: bool, span: Span) -> None:
        scope = self.scopes[-1]
        if name in scope:
            self.errors.append(OmniCheckError(f"'{name}' is already declared in this scope", span))
        else:
            scope[name] = Symbol(mutable, span)

    def _resolve(self, name: str, span: Span, assignment: bool = False) -> None:
        for scope in reversed(self.scopes):
            if name in scope:
                if assignment and not scope[name].mutable:
                    self.errors.append(OmniCheckError(f"cannot change sealed name '{name}'", span))
                return
        self.errors.append(
            OmniCheckError(
                f"unknown name '{name}'",
                span,
                "declare it before use with bind/seal or check its spelling",
            )
        )

    def _statement(self, statement: ast.Stmt) -> None:
        if isinstance(statement, ast.ExpressionStmt):
            self._expression(statement.expression)
        elif isinstance(statement, ast.VarDecl):
            self._expression(statement.initializer)
            self._declare(statement.name, statement.mutable, statement.span)
        elif isinstance(statement, ast.FuncDecl):
            self._declare(statement.name, False, statement.span)
            self._function(statement, has_self=False)
        elif isinstance(statement, ast.ShapeDecl):
            self._declare(statement.name, False, statement.span)
            self._shape(statement)
        elif isinstance(statement, ast.Block):
            self._block(statement.statements)
        elif isinstance(statement, ast.IfStmt):
            self._expression(statement.condition)
            self._statement(statement.then_branch)
            if statement.else_branch:
                self._statement(statement.else_branch)
        elif isinstance(statement, ast.WhileStmt):
            self._expression(statement.condition)
            self.loop_depth += 1
            self._statement(statement.body)
            self.loop_depth -= 1
        elif isinstance(statement, ast.EachStmt):
            self._expression(statement.iterable)
            self.loop_depth += 1
            self.scopes.append({})
            self._declare(statement.item_name, True, statement.span)
            if statement.index_name:
                self._declare(statement.index_name, False, statement.span)
            for child in statement.body.statements:
                self._statement(child)
            self.scopes.pop()
            self.loop_depth -= 1
        elif isinstance(statement, ast.ReturnStmt):
            if self.function_depth == 0:
                self.errors.append(OmniCheckError("return can only be used inside a craft", statement.span))
            if statement.value:
                self._expression(statement.value)
        elif isinstance(statement, (ast.BreakStmt, ast.ContinueStmt)):
            if self.loop_depth == 0:
                keyword = "break" if isinstance(statement, ast.BreakStmt) else "continue"
                self.errors.append(OmniCheckError(f"{keyword} can only be used inside a loop", statement.span))
        elif isinstance(statement, ast.EmitStmt):
            for value in statement.values:
                self._expression(value)
        elif isinstance(statement, ast.AssertStmt):
            self._expression(statement.condition)
            if statement.message:
                self._expression(statement.message)
        elif isinstance(statement, ast.UseStmt):
            self._declare(statement.alias, False, statement.span)

    def _block(self, statements: list[ast.Stmt]) -> None:
        self.scopes.append({})
        for statement in statements:
            self._statement(statement)
        self.scopes.pop()

    def _function(self, declaration: ast.FuncDecl, has_self: bool) -> None:
        self.function_depth += 1
        self.scopes.append({})
        if has_self:
            self._declare("self", False, declaration.span)
        for parameter in declaration.parameters:
            if parameter.default:
                self._expression(parameter.default)
            self._declare(parameter.name, True, parameter.span)
        # A loop outside a function cannot make break valid inside that function.
        outer_loop_depth = self.loop_depth
        self.loop_depth = 0
        for statement in declaration.body:
            self._statement(statement)
        self.loop_depth = outer_loop_depth
        self.scopes.pop()
        self.function_depth -= 1

    def _shape(self, declaration: ast.ShapeDecl) -> None:
        # Constructor defaults can use earlier constructor fields. Methods cannot:
        # fields are instance data and must be addressed through `self` at runtime.
        self.scopes.append({})
        for parameter in declaration.parameters:
            if parameter.default:
                self._expression(parameter.default)
            self._declare(parameter.name, True, parameter.span)
        self.scopes.pop()
        method_names: set[str] = set()
        for method in declaration.methods:
            if method.name in method_names:
                self.errors.append(OmniCheckError(f"duplicate shape method '{method.name}'", method.span))
            method_names.add(method.name)
            self._function(method, has_self=True)

    def _expression(self, expression: ast.Expr) -> None:
        if isinstance(expression, ast.Literal):
            return
        if isinstance(expression, ast.Variable):
            self._resolve(expression.name, expression.span)
        elif isinstance(expression, ast.ListExpr):
            for item in expression.items:
                self._expression(item)
        elif isinstance(expression, ast.MapExpr):
            for key, value in expression.entries:
                self._expression(key)
                self._expression(value)
        elif isinstance(expression, ast.Unary):
            self._expression(expression.right)
        elif isinstance(expression, ast.Binary):
            self._expression(expression.left)
            self._expression(expression.right)
        elif isinstance(expression, ast.Conditional):
            self._expression(expression.condition)
            self._expression(expression.if_true)
            self._expression(expression.if_false)
        elif isinstance(expression, ast.Call):
            self._expression(expression.callee)
            for argument in expression.arguments:
                self._expression(argument)
        elif isinstance(expression, ast.Get):
            self._expression(expression.target)
        elif isinstance(expression, ast.Index):
            self._expression(expression.target)
            self._expression(expression.index)
        elif isinstance(expression, ast.Assign):
            self._resolve(expression.name, expression.span, assignment=True)
            self._expression(expression.value)
        elif isinstance(expression, ast.SetExpr):
            self._expression(expression.target)
            self._expression(expression.value)
        elif isinstance(expression, ast.IndexSet):
            self._expression(expression.target)
            self._expression(expression.index)
            self._expression(expression.value)


def check_program(program: ast.Program, extra_names: set[str] | None = None) -> list[OmniCheckError]:
    return Checker(extra_names).check(program)
