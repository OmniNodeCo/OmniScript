from .parser import (
    BlockNode, NumberNode, StringNode, BoolNode, ArrayNode, IndexNode,
    VarAccessNode, VarAssignNode, LetNode, BinOpNode, UnaryOpNode,
    IfNode, WhileNode, LoopNode, FuncDefNode, FuncCallNode,
    ReturnNode, ShowNode, InputNode
)
from .errors import OmniRuntimeError, OmniReturnSignal


class Environment:
    def __init__(self, parent=None):
        self.store = {}
        self.parent = parent

    def get(self, name):
        if name in self.store:
            return self.store[name]
        if self.parent:
            return self.parent.get(name)
        raise OmniRuntimeError(f"Undefined variable: '{name}'")

    def set(self, name, value):
        self.store[name] = value

    def update(self, name, value):
        if name in self.store:
            self.store[name] = value
            return
        if self.parent:
            self.parent.update(name, value)
            return
        raise OmniRuntimeError(f"Undefined variable: '{name}'")


class OmniFunction:
    def __init__(self, name, params, body, closure):
        self.name = name
        self.params = params
        self.body = body
        self.closure = closure

    def __repr__(self):
        return f"<func {self.name}>"


class Interpreter:
    def __init__(self):
        self.global_env = Environment()
        self.builtins = {
            "len":   lambda args: self._builtin_len(args),
            "str":   lambda args: str(args[0]),
            "int":   lambda args: int(args[0]),
            "float": lambda args: float(args[0]),
            "type":  lambda args: type(args[0]).__name__,
            "push":  lambda args: self._builtin_push(args),
            "pop":   lambda args: self._builtin_pop(args),
        }

    def _builtin_len(self, args):
        if len(args) != 1:
            raise OmniRuntimeError("len() takes exactly 1 argument")
        val = args[0]
        if isinstance(val, (str, list)):
            return len(val)
        raise OmniRuntimeError(f"len() not supported for {type(val).__name__}")

    def _builtin_push(self, args):
        if len(args) != 2:
            raise OmniRuntimeError("push() takes exactly 2 arguments")
        arr, val = args
        if not isinstance(arr, list):
            raise OmniRuntimeError("push() first argument must be an array")
        arr.append(val)
        return arr

    def _builtin_pop(self, args):
        if len(args) != 1:
            raise OmniRuntimeError("pop() takes exactly 1 argument")
        arr = args[0]
        if not isinstance(arr, list):
            raise OmniRuntimeError("pop() argument must be an array")
        return arr.pop()

    def run(self, ast):
        return self.visit(ast, self.global_env)

    def visit(self, node, env):
        method_name = f"visit_{type(node).__name__}"
        method = getattr(self, method_name, None)
        if method is None:
            raise OmniRuntimeError(f"No visit method for {type(node).__name__}")
        return method(node, env)

    def visit_BlockNode(self, node, env):
        result = None
        for stmt in node.statements:
            result = self.visit(stmt, env)
        return result

    def visit_NumberNode(self, node, env):
        return node.value

    def visit_StringNode(self, node, env):
        return node.value

    def visit_BoolNode(self, node, env):
        return node.value

    def visit_ArrayNode(self, node, env):
        return [self.visit(el, env) for el in node.elements]

    def visit_IndexNode(self, node, env):
        arr = self.visit(node.array_expr, env)
        idx = self.visit(node.index_expr, env)
        if not isinstance(idx, int):
            raise OmniRuntimeError("Index must be an integer")
        try:
            return arr[idx]
        except IndexError:
            raise OmniRuntimeError(f"Index {idx} out of range")

    def visit_VarAccessNode(self, node, env):
        return env.get(node.name)

    def visit_VarAssignNode(self, node, env):
        value = self.visit(node.value, env)
        env.update(node.name, value)
        return value

    def visit_LetNode(self, node, env):
        value = self.visit(node.value, env)
        env.set(node.name, value)
        return value

    def visit_BinOpNode(self, node, env):
        left = self.visit(node.left, env)
        right = self.visit(node.right, env)
        op = node.op

        try:
            if op == '+':
                if isinstance(left, str) or isinstance(right, str):
                    return str(left) + str(right)
                return left + right
            elif op == '-':
                return left - right
            elif op == '*':
                return left * right
            elif op == '/':
                if right == 0:
                    raise OmniRuntimeError("Division by zero")
                return left / right
            elif op == '%':
                return left % right
            elif op == '==':
                return left == right
            elif op == '!=':
                return left != right
            elif op == '<':
                return left < right
            elif op == '>':
                return left > right
            elif op == '<=':
                return left <= right
            elif op == '>=':
                return left >= right
            elif op == 'and':
                return left and right
            elif op == 'or':
                return left or right
        except TypeError:
            raise OmniRuntimeError(f"Invalid operation: {type(left).__name__} {op} {type(right).__name__}")

        raise OmniRuntimeError(f"Unknown operator: {op}")

    def visit_UnaryOpNode(self, node, env):
        value = self.visit(node.node, env)
        if node.op == '-':
            return -value
        if node.op == 'not':
            return not value
        raise OmniRuntimeError(f"Unknown unary operator: {node.op}")

    def visit_IfNode(self, node, env):
        for condition, body in node.cases:
            result = self.visit(condition, env)
            if result:
                return self.visit(body, Environment(env))
        if node.else_body:
            return self.visit(node.else_body, Environment(env))
        return None

    def visit_WhileNode(self, node, env):
        result = None
        while self.visit(node.condition, env):
            result = self.visit(node.body, Environment(env))
        return result

    def visit_LoopNode(self, node, env):
        start = self.visit(node.start, env)
        end = self.visit(node.end, env)
        result = None
        for i in range(int(start), int(end)):
            loop_env = Environment(env)
            loop_env.set(node.var_name, i)
            result = self.visit(node.body, loop_env)
        return result

    def visit_FuncDefNode(self, node, env):
        func = OmniFunction(node.name, node.params, node.body, env)
        env.set(node.name, func)
        return func

    def visit_FuncCallNode(self, node, env):
        if node.name in self.builtins:
            args = [self.visit(a, env) for a in node.args]
            return self.builtins[node.name](args)

        func = env.get(node.name)
        if not isinstance(func, OmniFunction):
            raise OmniRuntimeError(f"'{node.name}' is not a function")

        if len(node.args) != len(func.params):
            raise OmniRuntimeError(
                f"{func.name}() expects {len(func.params)} args, got {len(node.args)}"
            )

        call_env = Environment(func.closure)
        for param, arg_node in zip(func.params, node.args):
            call_env.set(param, self.visit(arg_node, env))

        try:
            self.visit(func.body, call_env)
        except OmniReturnSignal as ret:
            return ret.value
        return None

    def visit_ReturnNode(self, node, env):
        value = None
        if node.value:
            value = self.visit(node.value, env)
        raise OmniReturnSignal(value)

    def visit_ShowNode(self, node, env):
        values = [self.visit(arg, env) for arg in node.args]
        output = " ".join(self._format(v) for v in values)
        print(output)
        return None

    def visit_InputNode(self, node, env):
        prompt = ""
        if node.prompt:
            prompt = str(self.visit(node.prompt, env))
        return input(prompt)

    def _format(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, list):
            inner = ", ".join(self._format(v) for v in value)
            return f"[{inner}]"
        if isinstance(value, float):
            if value == int(value):
                return str(int(value))
        return str(value)