"""Tree-walking reference runtime for OmniScript."""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import ast_nodes as ast
from .checker import check_program
from .errors import OmniError, OmniRuntimeError, Span
from .lexer import Lexer
from .parser import Parser
from .tokens import TokenKind as K


@dataclass(slots=True)
class Binding:
    value: Any
    mutable: bool


class Environment:
    def __init__(self, parent: Environment | None = None):
        self.parent = parent
        self.bindings: dict[str, Binding] = {}

    def define(self, name: str, value: Any, mutable: bool, span: Span | None = None) -> None:
        if name in self.bindings:
            raise OmniRuntimeError(f"'{name}' is already declared in this scope", span)
        self.bindings[name] = Binding(value, mutable)

    def get(self, name: str, span: Span) -> Any:
        if name in self.bindings:
            return self.bindings[name].value
        if self.parent:
            return self.parent.get(name, span)
        raise OmniRuntimeError(f"unknown name '{name}'", span, "declare it with bind/seal or check its spelling")

    def assign(self, name: str, value: Any, span: Span) -> Any:
        if name in self.bindings:
            binding = self.bindings[name]
            if not binding.mutable:
                raise OmniRuntimeError(f"cannot change sealed name '{name}'", span)
            binding.value = value
            return value
        if self.parent:
            return self.parent.assign(name, value, span)
        raise OmniRuntimeError(f"cannot assign unknown name '{name}'", span)

    def exported(self) -> dict[str, Any]:
        return {name: binding.value for name, binding in self.bindings.items() if not name.startswith("_")}


class OmniCallable:
    display_name = "<callable>"

    def call(self, interpreter: Interpreter, arguments: list[Any], span: Span) -> Any:
        raise NotImplementedError


class NativeFunction(OmniCallable):
    def __init__(
        self,
        name: str,
        implementation: Callable[[Interpreter, list[Any], Span], Any],
        minimum: int = 0,
        maximum: int | None = None,
    ):
        self.display_name = name
        self.implementation = implementation
        self.minimum = minimum
        self.maximum = maximum if maximum is not None else minimum

    def call(self, interpreter: Interpreter, arguments: list[Any], span: Span) -> Any:
        if len(arguments) < self.minimum or (self.maximum is not None and len(arguments) > self.maximum):
            if self.minimum == self.maximum:
                expected = str(self.minimum)
            else:
                expected = f"{self.minimum}..{self.maximum if self.maximum is not None else 'many'}"
            raise OmniRuntimeError(
                f"{self.display_name} expects {expected} argument(s), received {len(arguments)}", span
            )
        try:
            return self.implementation(interpreter, arguments, span)
        except OmniError:
            raise
        except (ValueError, TypeError, OSError, KeyError, IndexError, ArithmeticError) as exc:
            raise OmniRuntimeError(f"{self.display_name}: {exc}", span) from exc

    def __repr__(self) -> str:
        return f"<native {self.display_name}>"


class ReturnSignal(Exception):
    def __init__(self, value: Any, span: Span):
        self.value = value
        self.span = span


class BreakSignal(Exception):
    def __init__(self, span: Span):
        self.span = span


class ContinueSignal(Exception):
    def __init__(self, span: Span):
        self.span = span


class OmniFunction(OmniCallable):
    def __init__(self, declaration: ast.FuncDecl, closure: Environment):
        self.declaration = declaration
        self.closure = closure
        self.display_name = declaration.name

    def bind(self, instance: OmniInstance) -> OmniFunction:
        closure = Environment(self.closure)
        closure.define("self", instance, False, self.declaration.span)
        return OmniFunction(self.declaration, closure)

    def call(self, interpreter: Interpreter, arguments: list[Any], span: Span) -> Any:
        required = sum(parameter.default is None for parameter in self.declaration.parameters)
        maximum = len(self.declaration.parameters)
        if not required <= len(arguments) <= maximum:
            expected = str(required) if required == maximum else f"{required}..{maximum}"
            raise OmniRuntimeError(
                f"{self.display_name} expects {expected} argument(s), received {len(arguments)}", span
            )
        environment = Environment(self.closure)
        for index, parameter in enumerate(self.declaration.parameters):
            value = (
                arguments[index]
                if index < len(arguments)
                else interpreter.evaluate(parameter.default, environment)  # type: ignore[arg-type]
            )
            environment.define(parameter.name, value, True, parameter.span)
        try:
            interpreter.execute_statements(self.declaration.body, environment)
        except ReturnSignal as signal:
            return signal.value
        return None

    def __repr__(self) -> str:
        return f"<craft {self.display_name}>"


class OmniShape(OmniCallable):
    def __init__(self, declaration: ast.ShapeDecl, closure: Environment):
        self.declaration = declaration
        self.closure = closure
        self.display_name = declaration.name
        self.methods = {method.name: OmniFunction(method, closure) for method in declaration.methods}

    def call(self, interpreter: Interpreter, arguments: list[Any], span: Span) -> Any:
        parameters = self.declaration.parameters
        required = sum(parameter.default is None for parameter in parameters)
        if not required <= len(arguments) <= len(parameters):
            expected = str(required) if required == len(parameters) else f"{required}..{len(parameters)}"
            raise OmniRuntimeError(
                f"{self.display_name} expects {expected} argument(s), received {len(arguments)}", span
            )
        fields: dict[str, Any] = {}
        defaults = Environment(self.closure)
        for index, parameter in enumerate(parameters):
            value = (
                arguments[index]
                if index < len(arguments)
                else interpreter.evaluate(parameter.default, defaults)  # type: ignore[arg-type]
            )
            fields[parameter.name] = value
            defaults.define(parameter.name, value, True, parameter.span)
        return OmniInstance(self, fields)

    def __repr__(self) -> str:
        return f"<shape {self.display_name}>"


class OmniInstance:
    def __init__(self, shape: OmniShape, fields: dict[str, Any]):
        self.shape = shape
        self.fields = fields

    def get(self, name: str, span: Span) -> Any:
        if name in self.fields:
            return self.fields[name]
        if name in self.shape.methods:
            return self.shape.methods[name].bind(self)
        raise OmniRuntimeError(f"{self.shape.display_name} has no property '{name}'", span)

    def set(self, name: str, value: Any) -> Any:
        self.fields[name] = value
        return value

    def __repr__(self) -> str:
        fields = ", ".join(f"{key}: {stringify(value)}" for key, value in self.fields.items())
        return f"{self.shape.display_name}({fields})"


class OmniModule:
    def __init__(self, name: str, members: dict[str, Any]):
        self.name = name
        self.members = members

    def get(self, name: str, span: Span) -> Any:
        if name not in self.members:
            raise OmniRuntimeError(f"module '{self.name}' does not expose '{name}'", span)
        return self.members[name]

    def __repr__(self) -> str:
        return f"<module {self.name}>"


class Interpreter:
    def __init__(
        self,
        output: Callable[[str], None] | None = None,
        input_provider: Callable[[str], str] | None = None,
    ):
        self.output = output or print
        self.input_provider = input_provider or input
        self.globals = Environment()
        self._module_cache: dict[str, OmniModule] = {}
        self._module_loading: list[str] = []
        self._install_builtins()

    def new_environment(self) -> Environment:
        return Environment(self.globals)

    def interpret(self, program: ast.Program, environment: Environment | None = None) -> Any:
        environment = environment or self.new_environment()
        try:
            return self.execute_statements(program.statements, environment)
        except ReturnSignal as signal:
            raise OmniRuntimeError("return can only be used inside a craft", signal.span) from None
        except BreakSignal as signal:
            raise OmniRuntimeError("break can only be used inside a loop", signal.span) from None
        except ContinueSignal as signal:
            raise OmniRuntimeError("continue can only be used inside a loop", signal.span) from None

    def execute_statements(self, statements: list[ast.Stmt], environment: Environment) -> Any:
        result = None
        for statement in statements:
            result = self.execute(statement, environment)
        return result

    def execute(self, statement: ast.Stmt, environment: Environment) -> Any:
        if isinstance(statement, ast.ExpressionStmt):
            return self.evaluate(statement.expression, environment)
        if isinstance(statement, ast.VarDecl):
            value = self.evaluate(statement.initializer, environment)
            environment.define(statement.name, value, statement.mutable, statement.span)
            return value
        if isinstance(statement, ast.FuncDecl):
            function = OmniFunction(statement, environment)
            environment.define(statement.name, function, False, statement.span)
            return function
        if isinstance(statement, ast.ShapeDecl):
            shape = OmniShape(statement, environment)
            environment.define(statement.name, shape, False, statement.span)
            return shape
        if isinstance(statement, ast.Block):
            return self.execute_statements(statement.statements, Environment(environment))
        if isinstance(statement, ast.IfStmt):
            if truthy(self.evaluate(statement.condition, environment)):
                return self.execute(statement.then_branch, environment)
            if statement.else_branch is not None:
                return self.execute(statement.else_branch, environment)
            return None
        if isinstance(statement, ast.WhileStmt):
            result = None
            while truthy(self.evaluate(statement.condition, environment)):
                try:
                    result = self.execute(statement.body, environment)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return result
        if isinstance(statement, ast.EachStmt):
            iterable = self.evaluate(statement.iterable, environment)
            try:
                iterator = iter(iterable)
            except TypeError as exc:
                raise OmniRuntimeError(f"cannot iterate over {kind_name(iterable)}", statement.iterable.span) from exc
            result = None
            for index, item in enumerate(iterator):
                loop_environment = Environment(environment)
                loop_environment.define(statement.item_name, item, True, statement.span)
                if statement.index_name:
                    loop_environment.define(statement.index_name, index, False, statement.span)
                try:
                    result = self.execute_statements(statement.body.statements, loop_environment)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return result
        if isinstance(statement, ast.ReturnStmt):
            value = None if statement.value is None else self.evaluate(statement.value, environment)
            raise ReturnSignal(value, statement.span)
        if isinstance(statement, ast.BreakStmt):
            raise BreakSignal(statement.span)
        if isinstance(statement, ast.ContinueStmt):
            raise ContinueSignal(statement.span)
        if isinstance(statement, ast.EmitStmt):
            values = [self.evaluate(value, environment) for value in statement.values]
            self.output(" ".join(stringify(value) for value in values))
            return None
        if isinstance(statement, ast.AssertStmt):
            condition = self.evaluate(statement.condition, environment)
            if not truthy(condition):
                message = (
                    stringify(self.evaluate(statement.message, environment))
                    if statement.message is not None
                    else "assertion failed"
                )
                raise OmniRuntimeError(message, statement.span)
            return None
        if isinstance(statement, ast.UseStmt):
            module = self.load_module(statement.module, statement.span)
            environment.define(statement.alias, module, False, statement.span)
            return module
        raise OmniRuntimeError(f"unsupported statement {type(statement).__name__}", statement.span)

    def evaluate(self, expression: ast.Expr, environment: Environment) -> Any:
        if isinstance(expression, ast.Literal):
            return expression.value
        if isinstance(expression, ast.Variable):
            return environment.get(expression.name, expression.span)
        if isinstance(expression, ast.ListExpr):
            return [self.evaluate(item, environment) for item in expression.items]
        if isinstance(expression, ast.MapExpr):
            result: dict[Any, Any] = {}
            for key_expr, value_expr in expression.entries:
                key = self.evaluate(key_expr, environment)
                try:
                    result[key] = self.evaluate(value_expr, environment)
                except TypeError as exc:
                    raise OmniRuntimeError("map keys must be hashable", key_expr.span) from exc
            return result
        if isinstance(expression, ast.Unary):
            right = self.evaluate(expression.right, environment)
            if expression.operator == K.NOT:
                return not truthy(right)
            if expression.operator == K.MINUS:
                return -self._number(right, expression.span)
            if expression.operator == K.PLUS:
                return +self._number(right, expression.span)
        if isinstance(expression, ast.Binary):
            return self._binary(expression, environment)
        if isinstance(expression, ast.Conditional):
            branch = expression.if_true if truthy(self.evaluate(expression.condition, environment)) else expression.if_false
            return self.evaluate(branch, environment)
        if isinstance(expression, ast.Assign):
            return environment.assign(expression.name, self.evaluate(expression.value, environment), expression.span)
        if isinstance(expression, ast.Get):
            return self._get(self.evaluate(expression.target, environment), expression.name, expression.span)
        if isinstance(expression, ast.SetExpr):
            target = self.evaluate(expression.target, environment)
            value = self.evaluate(expression.value, environment)
            return self._set(target, expression.name, value, expression.span)
        if isinstance(expression, ast.Index):
            target = self.evaluate(expression.target, environment)
            index = self.evaluate(expression.index, environment)
            return self._index(target, index, expression.span)
        if isinstance(expression, ast.IndexSet):
            target = self.evaluate(expression.target, environment)
            index = self.evaluate(expression.index, environment)
            value = self.evaluate(expression.value, environment)
            return self._index_set(target, index, value, expression.span)
        if isinstance(expression, ast.Call):
            callee = self.evaluate(expression.callee, environment)
            arguments = [self.evaluate(argument, environment) for argument in expression.arguments]
            return self.call_value(callee, arguments, expression.span)
        raise OmniRuntimeError(f"unsupported expression {type(expression).__name__}", expression.span)

    def call_value(self, callee: Any, arguments: list[Any], span: Span) -> Any:
        if not isinstance(callee, OmniCallable):
            raise OmniRuntimeError(f"{kind_name(callee)} is not callable", span)
        try:
            return callee.call(self, arguments, span)
        except OmniRuntimeError as error:
            error.add_frame(callee.display_name, span)
            raise

    def _binary(self, expression: ast.Binary, environment: Environment) -> Any:
        operator = expression.operator
        left = self.evaluate(expression.left, environment)
        if operator == K.AND:
            return self.evaluate(expression.right, environment) if truthy(left) else left
        if operator == K.OR:
            return left if truthy(left) else self.evaluate(expression.right, environment)
        if operator == K.COALESCE:
            return left if left is not None else self.evaluate(expression.right, environment)
        if operator == K.PIPE:
            right = self.evaluate(expression.right, environment)
            return self.call_value(right, [left], expression.span)
        right = self.evaluate(expression.right, environment)
        if operator == K.PLUS:
            if _both_numbers(left, right):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            raise OmniRuntimeError("'+' needs two numbers, two texts, or two lists", expression.span)
        if operator == K.MINUS:
            return self._number(left, expression.span) - self._number(right, expression.span)
        if operator == K.STAR:
            if _both_numbers(left, right):
                return left * right
            if isinstance(left, (str, list)) and _is_integer(right):
                return left * int(right)
            raise OmniRuntimeError("'*' needs numbers, or text/list and an integer", expression.span)
        if operator == K.SLASH:
            divisor = self._number(right, expression.span)
            if divisor == 0:
                raise OmniRuntimeError("division by zero", expression.span)
            return self._number(left, expression.span) / divisor
        if operator == K.PERCENT:
            divisor = self._number(right, expression.span)
            if divisor == 0:
                raise OmniRuntimeError("remainder by zero", expression.span)
            return self._number(left, expression.span) % divisor
        if operator == K.POWER:
            try:
                result = self._number(left, expression.span) ** self._number(right, expression.span)
            except (OverflowError, ZeroDivisionError) as exc:
                raise OmniRuntimeError(f"invalid exponentiation: {exc}", expression.span) from exc
            if isinstance(result, complex):
                raise OmniRuntimeError("exponentiation would produce a complex number", expression.span)
            return result
        if operator == K.EQUAL:
            return left == right
        if operator == K.NOT_EQUAL:
            return left != right
        if operator in (K.LESS, K.LESS_EQUAL, K.GREATER, K.GREATER_EQUAL):
            try:
                return {
                    K.LESS: lambda: left < right,
                    K.LESS_EQUAL: lambda: left <= right,
                    K.GREATER: lambda: left > right,
                    K.GREATER_EQUAL: lambda: left >= right,
                }[operator]()
            except TypeError as exc:
                raise OmniRuntimeError(
                    f"cannot compare {kind_name(left)} with {kind_name(right)}", expression.span
                ) from exc
        if operator == K.IN:
            try:
                return left in right
            except TypeError as exc:
                raise OmniRuntimeError(f"cannot search inside {kind_name(right)}", expression.span) from exc
        if operator == K.RANGE:
            if not _is_integer(left) or not _is_integer(right):
                raise OmniRuntimeError("range bounds must be integers", expression.span)
            start, end = int(left), int(right)
            step = 1 if end >= start else -1
            return list(range(start, end + step, step))
        raise OmniRuntimeError("unknown binary operator", expression.span)

    @staticmethod
    def _number(value: Any, span: Span) -> int | float:
        if not _is_number(value):
            raise OmniRuntimeError(f"expected number, found {kind_name(value)}", span)
        return value

    @staticmethod
    def _get(target: Any, name: str, span: Span) -> Any:
        if isinstance(target, OmniInstance):
            return target.get(name, span)
        if isinstance(target, OmniModule):
            return target.get(name, span)
        if isinstance(target, dict):
            if name not in target:
                raise OmniRuntimeError(f"map has no key '{name}'", span)
            return target[name]
        raise OmniRuntimeError(f"cannot read property '{name}' from {kind_name(target)}", span)

    @staticmethod
    def _set(target: Any, name: str, value: Any, span: Span) -> Any:
        if isinstance(target, OmniInstance):
            return target.set(name, value)
        if isinstance(target, dict):
            target[name] = value
            return value
        raise OmniRuntimeError(f"cannot set property '{name}' on {kind_name(target)}", span)

    @staticmethod
    def _index(target: Any, index: Any, span: Span) -> Any:
        if isinstance(target, (list, str)):
            if not _is_integer(index):
                raise OmniRuntimeError("list/text index must be an integer", span)
            index = int(index)
        try:
            return target[index]
        except (IndexError, KeyError):
            raise OmniRuntimeError(f"index/key {stringify(index)} does not exist", span) from None
        except (TypeError, AttributeError):
            raise OmniRuntimeError(f"cannot index {kind_name(target)}", span) from None

    @staticmethod
    def _index_set(target: Any, index: Any, value: Any, span: Span) -> Any:
        if isinstance(target, list):
            if not _is_integer(index):
                raise OmniRuntimeError("list index must be an integer", span)
            index = int(index)
        if not isinstance(target, (list, dict)):
            raise OmniRuntimeError(f"cannot assign an index on {kind_name(target)}", span)
        try:
            target[index] = value
        except (IndexError, TypeError) as exc:
            raise OmniRuntimeError(f"cannot assign index/key {stringify(index)}", span) from exc
        return value

    def load_module(self, specifier: str, span: Span) -> OmniModule:
        if specifier in self._builtin_modules:
            return self._builtin_modules[specifier]
        source_path = Path(span.source)
        base = source_path.parent if span.source not in ("<memory>", "<repl>", "<stdin>") else Path.cwd()
        path = Path(specifier)
        if not path.is_absolute():
            path = base / path
        if not path.suffix:
            path = path.with_suffix(".omni")
        try:
            canonical = str(path.resolve())
        except OSError:
            canonical = str(path.absolute())
        if canonical in self._module_cache:
            return self._module_cache[canonical]
        if canonical in self._module_loading:
            chain = " -> ".join([*self._module_loading, canonical])
            raise OmniRuntimeError(f"cyclic module import: {chain}", span)
        try:
            source = Path(canonical).read_text(encoding="utf-8")
        except OSError as exc:
            raise OmniRuntimeError(f"cannot load module '{specifier}': {exc}", span) from exc
        self._module_loading.append(canonical)
        environment = self.new_environment()
        environment.define("__file__", canonical, False, span)
        try:
            program = Parser(Lexer(source, canonical).scan()).parse()
            problems = check_program(program)
            if problems:
                raise problems[0]
            self.interpret(program, environment)
        finally:
            self._module_loading.pop()
        module = OmniModule(Path(canonical).stem, environment.exported())
        self._module_cache[canonical] = module
        return module

    def _install_builtins(self) -> None:
        def native(name: str, function: Callable[[Interpreter, list[Any], Span], Any], minimum: int, maximum: int | None = None) -> NativeFunction:
            return NativeFunction(name, function, minimum, minimum if maximum is None else maximum)

        builtins: dict[str, NativeFunction] = {
            "len": native("len", lambda _i, a, _s: len(a[0]), 1),
            "kind": native("kind", lambda _i, a, _s: kind_name(a[0]), 1),
            "text": native("text", lambda _i, a, _s: stringify(a[0]), 1),
            "number": native("number", _to_number, 1),
            "integer": native("integer", lambda _i, a, _s: int(a[0]), 1),
            "truthy": native("truthy", lambda _i, a, _s: truthy(a[0]), 1),
            "clock": native("clock", lambda _i, _a, _s: time.time(), 0),
            "input": native("input", lambda i, a, _s: i.input_provider(stringify(a[0]) if a else ""), 0, 1),
            "keys": native("keys", lambda _i, a, _s: list(_require_map(a[0]).keys()), 1),
            "values": native("values", lambda _i, a, _s: list(_require_map(a[0]).values()), 1),
            "has": native("has", lambda _i, a, _s: a[1] in a[0], 2),
            "push": native("push", _push, 2),
            "pop": native("pop", _pop, 1),
            "sort": native("sort", _sort, 1),
            "reverse": native("reverse", lambda _i, a, _s: list(reversed(a[0])), 1),
            "map": native("map", _map_values, 2),
            "filter": native("filter", _filter_values, 2),
            "reduce": native("reduce", _reduce_values, 3),
            "read": native("read", lambda _i, a, _s: Path(str(a[0])).read_text(encoding="utf-8"), 1),
            "write": native("write", _write, 2),
            "panic": native("panic", lambda _i, a, s: _panic(a[0], s), 1),
        }
        for name, function in builtins.items():
            self.globals.define(name, function, False)

        math_members: dict[str, Any] = {"pi": math.pi, "e": math.e, "tau": math.tau}
        for name, function in {
            "abs": abs,
            "ceil": math.ceil,
            "floor": math.floor,
            "round": round,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "min": min,
            "max": max,
        }.items():
            minimum = 2 if name in {"min", "max"} else 1
            maximum = 2 if name in {"log", "min", "max"} else 1
            math_members[name] = native(
                f"math.{name}",
                lambda _i, a, _s, fn=function: fn(*a),
                minimum,
                maximum,
            )

        text_members = {
            "upper": native("text.upper", lambda _i, a, _s: str(a[0]).upper(), 1),
            "lower": native("text.lower", lambda _i, a, _s: str(a[0]).lower(), 1),
            "trim": native("text.trim", lambda _i, a, _s: str(a[0]).strip(), 1),
            "split": native("text.split", lambda _i, a, _s: str(a[0]).split(str(a[1])), 2),
            "join": native("text.join", lambda _i, a, _s: str(a[0]).join(map(str, a[1])), 2),
            "contains": native("text.contains", lambda _i, a, _s: str(a[1]) in str(a[0]), 2),
            "replace": native("text.replace", lambda _i, a, _s: str(a[0]).replace(str(a[1]), str(a[2])), 3),
        }
        json_members = {
            "parse": native("json.parse", lambda _i, a, _s: json.loads(str(a[0])), 1),
            "stringify": native("json.stringify", lambda _i, a, _s: json.dumps(_json_value(a[0]), ensure_ascii=False), 1),
        }
        path_members = {
            "join": native("path.join", lambda _i, a, _s: str(Path(str(a[0])).joinpath(str(a[1]))), 2),
            "name": native("path.name", lambda _i, a, _s: Path(str(a[0])).name, 1),
            "stem": native("path.stem", lambda _i, a, _s: Path(str(a[0])).stem, 1),
            "exists": native("path.exists", lambda _i, a, _s: Path(str(a[0])).exists(), 1),
        }
        random_members = {
            "number": native("random.number", lambda _i, _a, _s: random.random(), 0),
            "integer": native("random.integer", lambda _i, a, _s: random.randint(int(a[0]), int(a[1])), 2),
            "pick": native("random.pick", lambda _i, a, _s: random.choice(a[0]), 1),
        }
        self._builtin_modules = {
            "math": OmniModule("math", math_members),
            "text": OmniModule("text", text_members),
            "json": OmniModule("json", json_members),
            "path": OmniModule("path", path_members),
            "random": OmniModule("random", random_members),
        }
        # Imported lazily to avoid making Tk a requirement for the core runtime.
        from .gui import create_gui_module
        from .packages import create_utility_modules

        self._builtin_modules["gui"] = create_gui_module()
        self._builtin_modules.update(create_utility_modules())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) or isinstance(value, float) and value.is_integer()


def _both_numbers(left: Any, right: Any) -> bool:
    return _is_number(left) and _is_number(right)


def truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value == 0 or value == "" or value == [] or value == {}:
        return False
    return True


def kind_name(value: Any) -> str:
    if value is None:
        return "void"
    if isinstance(value, bool):
        return "truth"
    if _is_number(value):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, OmniFunction):
        return "craft"
    if isinstance(value, NativeFunction):
        return "native-craft"
    if isinstance(value, OmniShape):
        return "shape"
    if isinstance(value, OmniInstance):
        return value.shape.display_name
    if isinstance(value, OmniModule):
        return "module"
    return type(value).__name__


def stringify(value: Any) -> str:
    if value is None:
        return "void"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return "[" + ", ".join(stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{stringify(k)}: {stringify(v)}" for k, v in value.items()) + "}"
    return str(value)


def _to_number(_interpreter: Interpreter, arguments: list[Any], span: Span) -> int | float:
    value = arguments[0]
    if _is_number(value):
        return value
    try:
        converted = float(str(value))
    except ValueError as exc:
        raise OmniRuntimeError(f"cannot convert {stringify(value)} to number", span) from exc
    return int(converted) if converted.is_integer() else converted


def _require_map(value: Any) -> dict[Any, Any]:
    if not isinstance(value, dict):
        raise TypeError("expected map")
    return value


def _push(_interpreter: Interpreter, arguments: list[Any], _span: Span) -> list[Any]:
    if not isinstance(arguments[0], list):
        raise TypeError("push expects a list")
    arguments[0].append(arguments[1])
    return arguments[0]


def _pop(_interpreter: Interpreter, arguments: list[Any], _span: Span) -> Any:
    if not isinstance(arguments[0], list):
        raise TypeError("pop expects a list")
    return arguments[0].pop()


def _sort(_interpreter: Interpreter, arguments: list[Any], _span: Span) -> list[Any]:
    if not isinstance(arguments[0], list):
        raise TypeError("sort expects a list")
    return sorted(arguments[0])


def _map_values(interpreter: Interpreter, arguments: list[Any], span: Span) -> list[Any]:
    return [interpreter.call_value(arguments[1], [value], span) for value in arguments[0]]


def _filter_values(interpreter: Interpreter, arguments: list[Any], span: Span) -> list[Any]:
    return [value for value in arguments[0] if truthy(interpreter.call_value(arguments[1], [value], span))]


def _reduce_values(interpreter: Interpreter, arguments: list[Any], span: Span) -> Any:
    accumulator = arguments[2]
    for value in arguments[0]:
        accumulator = interpreter.call_value(arguments[1], [accumulator, value], span)
    return accumulator


def _write(_interpreter: Interpreter, arguments: list[Any], _span: Span) -> None:
    Path(str(arguments[0])).write_text(str(arguments[1]), encoding="utf-8")
    return None


def _panic(value: Any, span: Span) -> None:
    raise OmniRuntimeError(stringify(value), span)


def _json_value(value: Any) -> Any:
    if isinstance(value, OmniInstance):
        return {key: _json_value(item) for key, item in value.fields.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"cannot encode {kind_name(value)} as JSON")
