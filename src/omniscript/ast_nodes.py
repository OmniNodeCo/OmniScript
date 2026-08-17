"""Abstract syntax tree nodes for OmniScript.

The AST is intentionally public and made from plain dataclasses, which keeps the
interpreter embeddable and allows editors or alternative backends to reuse it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import Span
from .tokens import TokenKind


@dataclass(slots=True)
class Expr:
    span: Span


@dataclass(slots=True)
class Literal(Expr):
    value: Any


@dataclass(slots=True)
class Variable(Expr):
    name: str


@dataclass(slots=True)
class ListExpr(Expr):
    items: list[Expr]


@dataclass(slots=True)
class MapExpr(Expr):
    entries: list[tuple[Expr, Expr]]


@dataclass(slots=True)
class Unary(Expr):
    operator: TokenKind
    right: Expr


@dataclass(slots=True)
class Binary(Expr):
    left: Expr
    operator: TokenKind
    right: Expr


@dataclass(slots=True)
class Conditional(Expr):
    condition: Expr
    if_true: Expr
    if_false: Expr


@dataclass(slots=True)
class Call(Expr):
    callee: Expr
    arguments: list[Expr]


@dataclass(slots=True)
class Get(Expr):
    target: Expr
    name: str


@dataclass(slots=True)
class Index(Expr):
    target: Expr
    index: Expr


@dataclass(slots=True)
class Assign(Expr):
    name: str
    value: Expr


@dataclass(slots=True)
class SetExpr(Expr):
    target: Expr
    name: str
    value: Expr


@dataclass(slots=True)
class IndexSet(Expr):
    target: Expr
    index: Expr
    value: Expr


@dataclass(slots=True)
class Stmt:
    span: Span


@dataclass(slots=True)
class Program:
    statements: list[Stmt]


@dataclass(slots=True)
class ExpressionStmt(Stmt):
    expression: Expr


@dataclass(slots=True)
class VarDecl(Stmt):
    name: str
    initializer: Expr
    mutable: bool


@dataclass(slots=True)
class Parameter:
    name: str
    default: Expr | None
    span: Span


@dataclass(slots=True)
class FuncDecl(Stmt):
    name: str
    parameters: list[Parameter]
    body: list[Stmt]


@dataclass(slots=True)
class ShapeDecl(Stmt):
    name: str
    parameters: list[Parameter]
    methods: list[FuncDecl]


@dataclass(slots=True)
class Block(Stmt):
    statements: list[Stmt]


@dataclass(slots=True)
class IfStmt(Stmt):
    condition: Expr
    then_branch: Block
    else_branch: Block | IfStmt | None


@dataclass(slots=True)
class WhileStmt(Stmt):
    condition: Expr
    body: Block


@dataclass(slots=True)
class EachStmt(Stmt):
    item_name: str
    index_name: str | None
    iterable: Expr
    body: Block


@dataclass(slots=True)
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass(slots=True)
class BreakStmt(Stmt):
    pass


@dataclass(slots=True)
class ContinueStmt(Stmt):
    pass


@dataclass(slots=True)
class EmitStmt(Stmt):
    values: list[Expr]


@dataclass(slots=True)
class AssertStmt(Stmt):
    condition: Expr
    message: Expr | None


@dataclass(slots=True)
class UseStmt(Stmt):
    module: str
    alias: str
