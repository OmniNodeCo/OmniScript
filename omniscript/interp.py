"""The OmniScript interpreter.

A direct tree-walking evaluator. Every expression produces a value, every
statement optionally produces one too (blocks return their last expression,
which is what makes `fn f(x) { x * 2 }` work without the word `return`).
"""

from __future__ import annotations

import os
import sys
from typing import Any

from . import ast as A
from ._bundle import std_base
from .errors import (OmniBreak, OmniContinue, OmniError, OmniNameError, OmniReturn,
                     OmniRuntimeError, OmniThrow, OmniTypeError, describe, suggest)
from .parser import parse
from .values import (HostObject, NativeFunction, OmniClass, OmniFunction, OmniObject,
                     OmniRange, _MISSING, collect_signature, compare, fmt_num, omni_eq,
                     to_repr, to_string, truthy, type_name)

MAX_CALL_DEPTH = 800


class Environment:
    __slots__ = ("vars", "parent", "immutable", "name")

    def __init__(self, parent: "Environment | None" = None, name: str = ""):
        self.vars: dict[str, Any] = {}
        self.parent = parent
        self.immutable: set[str] = set()
        self.name = name

    def define(self, name: str, value, immutable: bool = False):
        self.vars[name] = value
        if immutable:
            self.immutable.add(name)
        else:
            self.immutable.discard(name)

    def find(self, name: str) -> "Environment | None":
        env: Environment | None = self
        while env is not None:
            if name in env.vars:
                return env
            env = env.parent
        return None

    def get(self, name: str):
        env = self.find(name)
        return _MISSING if env is None else env.vars[name]

    def assign(self, name: str, value, node=None):
        env = self.find(name)
        if env is None:
            raise OmniNameError(
                f"`{name}` is not defined",
                getattr(node, "line", None), getattr(node, "col", None),
                hint=f"declare it first with `mut {name} = ...`",
            )
        if name in env.immutable:
            raise OmniRuntimeError(
                f"cannot assign to `{name}`: it was declared with `let`",
                getattr(node, "line", None), getattr(node, "col", None),
                hint=f"change `let {name}` to `mut {name}` if you need to reassign it",
            )
        env.vars[name] = value


class BoundNative:
    """`value.method` where method is a host function: remembers its receiver."""

    __slots__ = ("obj", "fn")

    def __init__(self, obj, fn: NativeFunction):
        self.obj = obj
        self.fn = fn

    def __repr__(self):
        return f"<fn {type_name(self.obj)}.{self.fn.name}>"


class BoundMethod:
    """`instance.method`: remembers both the receiver and the defining class."""

    __slots__ = ("obj", "fn", "owner")

    def __init__(self, obj, fn: OmniFunction, owner: OmniClass | None = None):
        self.obj = obj
        self.fn = fn
        self.owner = owner

    def __repr__(self):
        return f"<fn {self.fn.name}>"


VALID_ATTRS = {"memo", "test", "main", "deprecated", "inline", "hidden"}


class Interpreter:
    _current: "Interpreter | None" = None

    def __init__(self, writer=None, root: str = ".", argv: list[str] | None = None,
                 quiet: bool = False, max_steps: int | None = None):
        self.write = writer or (lambda s: sys.stdout.write(s))
        self.root = os.path.abspath(root)
        self.argv = argv or []
        self.quiet = quiet
        self.max_steps = max_steps
        self.steps = 0
        self.globals = Environment(name="globals")
        self.stack: list[tuple[str, int | None]] = []
        self.sources: dict[str, str] = {}
        self.modules: dict[str, Environment] = {}
        self.current_file: str | None = None
        self.tests: list[tuple[str, OmniFunction]] = []
        self.main_fn: OmniFunction | None = None
        self.methods: dict[str, dict[str, NativeFunction]] = {}
        self.exit_code: int | None = None
        self.canvases: list = []
        self.picture_count = 0
        self.stdin = sys.stdin
        self.builtin_index: dict[str, Any] = {}
        Interpreter._current = self

    @classmethod
    def current(cls) -> "Interpreter":
        if cls._current is None:
            cls._current = Interpreter()
        return cls._current

    def next_picture_path(self) -> str:
        """An automatic filename for a picture nobody asked to save explicitly."""
        self.picture_count += 1
        base = "omni-picture.png" if self.picture_count == 1 \
            else f"omni-picture-{self.picture_count}.png"
        return os.path.join(self.root or ".", base)

    def save_pending_pictures(self) -> list[str]:
        """Write out any canvas that was never saved by the program itself."""
        written = []
        for canvas in getattr(self, "canvases", []):
            if canvas.fields.get("saved"):
                continue
            try:
                written.append(canvas.methods["save"].fn(canvas, None))
            except Exception:
                continue
        return written

    # ---------------------------------------------------------------- output
    def print(self, text: str = ""):
        self.write(text)

    def out(self, text: str = ""):
        self.write(text + "\n")

    # --------------------------------------------------------------- running
    def load_builtins(self):
        from .stdlib import install
        install(self)
        self.prelude = set(self.globals.vars)

    def run_source(self, src: str, path: str = "<stdin>", env: Environment | None = None):
        self.sources[path] = src
        self.current_file = path
        program = parse(src, path)
        return self.run_program(program, env or self.globals, path)

    def run_program(self, program, env: Environment, path: str = "<program>"):
        value = None
        for stmt in program:
            value = self.exec_stmt(stmt, env)
        return value

    def tick(self):
        if self.max_steps is not None:
            self.steps += 1
            if self.steps > self.max_steps:
                raise OmniRuntimeError(
                    f"stopped after {self.max_steps:,} steps",
                    hint="this looks like an infinite loop; raise --max-steps if it is intentional",
                )

    # ------------------------------------------------------------ statements
    def exec_stmt(self, node, env: Environment):
        self.tick()
        handler = self._dispatch.get(type(node))
        if handler is None:
            raise OmniRuntimeError(f"cannot execute `{type(node).__name__}`",
                                   getattr(node, "line", None))
        return handler(self, node, env)

    def run_block(self, block, env: Environment):
        value = None
        for stmt in block.stmts:
            value = self.exec_stmt(stmt, env)
        return value

    # -- individual statements ----------------------------------------------
    def s_let(self, node: A.Let, env: Environment):
        value = self.eval(node.value, env)
        self.bind_targets(node.targets, value, env, immutable=not node.mutable, node=node)
        return None

    def bind_targets(self, targets, value, env: Environment, immutable=False, node=None):
        if len(targets) == 1 and isinstance(targets[0], A.PBind):
            env.define(targets[0].name, value, immutable)
            return
        if len(targets) > 1:
            items = self.iterate(value, node)
            if len(items) < len(targets):
                raise OmniRuntimeError(
                    f"cannot unpack {len(items)} values into {len(targets)} names",
                    getattr(node, "line", None),
                    hint=f"expected at least {len(targets)} items",
                )
            for tgt, item in zip(targets, items):
                self.bind_pattern(tgt, item, env, immutable, node)
            return
        self.bind_pattern(targets[0], value, env, immutable, node)

    def bind_pattern(self, pattern, value, env: Environment, immutable=False, node=None):
        if isinstance(pattern, A.PBind):
            env.define(pattern.name, value, immutable)
        elif isinstance(pattern, A.PWild):
            return
        elif isinstance(pattern, A.PList):
            items = self.iterate(value, node)
            for sub, item in zip(pattern.items, items):
                self.bind_pattern(sub, item, env, immutable, node)
            if pattern.rest:
                env.define(pattern.rest, list(items[len(pattern.items):]), False)
        elif isinstance(pattern, A.PMap):
            if not isinstance(value, dict):
                raise OmniTypeError(f"cannot destructure {type_name(value)} as a map",
                                    getattr(node, "line", None))
            for key, sub in pattern.entries:
                kname = key if isinstance(key, str) else self.eval(key, env)
                self.bind_pattern(sub, value.get(kname), env, immutable, node)
        elif isinstance(pattern, A.PTyped):
            env.define(pattern.name, value, immutable)

    def s_fndecl(self, node: A.FnDecl, env: Environment):
        fn = self.make_function(node.name, node.params, node.body, env, node.attrs, node)
        env.define(node.name, fn)
        self.apply_attrs(node.attrs, fn, node, env)
        return None

    def make_function(self, name, params, body, env, attrs, node):
        fn = OmniFunction(name, params, body, env, attrs)
        return fn

    def apply_attrs(self, attrs, fn, node, env):
        for aname, aargs, aline in attrs:
            if aname not in VALID_ATTRS:
                raise OmniRuntimeError(
                    f"unknown attribute `@{aname}`", aline,
                    hint=suggest(aname, VALID_ATTRS) or
                    f"known attributes: {', '.join('@' + a for a in sorted(VALID_ATTRS))}")
            if aname == "memo":
                cache: dict = {}
                original = fn

                def memoized(interp, *args, **kwargs):
                    key = to_repr([args, sorted(kwargs.items())])
                    if key in cache:
                        return cache[key]
                    result = interp.call_value(original, list(args), dict(kwargs), node=None)
                    cache[key] = result
                    return result

                wrapped = collect_signature(memoized, name=fn.name)
                wrapped.params = original.params
                wrapped.doc = original.__doc__ if hasattr(original, "__doc__") else ""
                env.define(fn.name, wrapped)
            elif aname == "test":
                self.tests.append((fn.name, fn))
            elif aname == "main":
                self.main_fn = fn
            elif aname == "deprecated":
                msg = aargs[0].value if aargs and isinstance(aargs[0], A.Str) else fn.name
                original = fn

                def dep(interp, *args, **kwargs):
                    if not interp.quiet:
                        interp.out(f"warning: `{original.name}` is deprecated: {msg}")
                    return interp.call_value(original, list(args), dict(kwargs), node=None)

                wrapped = collect_signature(dep, name=fn.name)
                wrapped.params = original.params
                env.define(fn.name, wrapped)

    def s_class(self, node: A.ClassDecl, env: Environment):
        parent = None
        if node.parent:
            p = env.get(node.parent)
            if p is _MISSING or not isinstance(p, OmniClass):
                raise OmniRuntimeError(f"parent class `{node.parent}` does not exist",
                                       node.line, node.col)
            parent = p
        methods: dict[str, OmniFunction] = {}
        fields: list[tuple[str, Any]] = []
        klass = OmniClass(node.name, parent, methods, fields, node.attrs)
        for member in node.members:
            if isinstance(member, tuple):
                fields.append((member[1], member[2], env))
            else:
                methods[member.name] = OmniFunction(
                    member.name, member.params, member.body, env, member.attrs,
                    is_method=True)
        env.define(node.name, klass)
        return None

    def s_for(self, node: A.For, env: Environment):
        source = node.iterable
        iterable = self.eval(source, env)
        step = self.eval(node.by, env) if node.by is not None else None

        pairs: list[Any]
        if isinstance(iterable, OmniRange):
            if step is not None:
                iterable = OmniRange(iterable.lo, iterable.hi, step, iterable.inclusive)
            pairs = iterable.values()
        elif isinstance(iterable, dict) and len(node.targets) == 1 and \
                isinstance(node.targets[0], A.PList) and len(node.targets[0].items) == 2:
            pairs = [[k, v] for k, v in iterable.items()]
        elif isinstance(iterable, dict) and len(node.targets) >= 2:
            pairs = [[k, v] for k, v in iterable.items()]
        elif isinstance(iterable, dict):
            pairs = list(iterable.keys())
        elif isinstance(iterable, str) and len(node.targets) >= 2:
            pairs = [[float(i), ch] for i, ch in enumerate(iterable)]
        elif isinstance(iterable, str):
            pairs = list(iterable)
        elif isinstance(iterable, (list, tuple)) and len(node.targets) >= 2:
            # `for i, item in items` hands you the position and the item
            pairs = [[float(i), v] for i, v in enumerate(iterable)]
        elif isinstance(iterable, (list, tuple)):
            pairs = list(iterable)
        elif isinstance(iterable, HostObject) and "__iter__" in iterable.methods:
            pairs = list(self.call_value(iterable.methods["__iter__"], [], {},
                                         node=None) or [])
        elif isinstance(iterable, OmniObject):
            it = iterable.klass.lookup("iter")
            if it is None:
                raise OmniTypeError(f"cannot loop over <{iterable.klass.name}>",
                                    node.line, node.col,
                                    hint="give the class an `iter()` method")
            pairs = list(self.call_value(it, [], {}, node=None, self_obj=iterable))
        else:
            hint = None
            if isinstance(iterable, (int, float)) and not isinstance(iterable, bool):
                n = fmt_num(float(iterable))
                hint = (f"a number is not a sequence -- try `for i in 1..{n}` "
                        f"or `{n}.times((i) -> ...)`")
            elif iterable is None:
                hint = "this value is null; guard it with `?.` or `?? []`"
            raise OmniTypeError(f"cannot loop over {type_name(iterable)}",
                                node.line, node.col, hint=hint)

        if step is not None and not isinstance(iterable, OmniRange):
            pairs = pairs[::int(step)]

        loop_env_parent = env
        for item in pairs:
            self.tick()
            body_env = Environment(loop_env_parent, "for")
            if len(node.targets) == 1:
                self.bind_pattern(node.targets[0], item, body_env, False, node)
            else:
                parts = list(item) if isinstance(item, (list, str)) else [item]
                if isinstance(item, list) and len(item) == len(node.targets):
                    parts = item
                for tgt, val in zip(node.targets, parts):
                    self.bind_pattern(tgt, val, body_env, False, node)
            try:
                self.run_block(node.body, body_env)
            except OmniBreak:
                break
            except OmniContinue:
                continue
        return None

    def s_while(self, node: A.While, env: Environment):
        while truthy(self.eval(node.cond, env)):
            self.tick()
            try:
                self.run_block(node.body, Environment(env, "while"))
            except OmniBreak:
                break
            except OmniContinue:
                continue
        return None

    def s_dowhile(self, node: A.DoWhile, env: Environment):
        while True:
            self.tick()
            try:
                self.run_block(node.body, Environment(env, "do"))
            except OmniBreak:
                break
            except OmniContinue:
                pass
            if not truthy(self.eval(node.cond, env)):
                break
        return None

    def s_try(self, node: A.Try, env: Environment):
        produced = None
        try:
            produced = self.run_block(node.body, Environment(env, "try"))
        except OmniThrow as thrown:
            if node.catch_body is None:
                raise
            cenv = Environment(env, "catch")
            if node.catch_name:
                cenv.define(node.catch_name, thrown.value)
            produced = self.run_block(node.catch_body, cenv)
        except OmniError as err:
            if node.catch_body is None:
                raise
            cenv = Environment(env, "catch")
            if node.catch_name:
                cenv.define(node.catch_name, HostObject(
                    "Error",
                    fields={"message": err.message, "kind": err.kind,
                            "line": err.line, "hint": err.hint or ""},
                    display=lambda o: f"{o.fields['kind']}: {o.fields['message']}"))
            produced = self.run_block(node.catch_body, cenv)
        except RecursionError:
            if node.catch_body is None:
                raise
            cenv = Environment(env, "catch")
            if node.catch_name:
                cenv.define(node.catch_name, HostObject(
                    "Error", fields={"message": "too much recursion", "kind": "stack overflow"}))
            produced = self.run_block(node.catch_body, cenv)
        finally:
            if node.finally_body is not None:
                self.run_block(node.finally_body, Environment(env, "finally"))
        return produced

    def s_return(self, node: A.Return, env: Environment):
        raise OmniReturn(self.eval(node.value, env) if node.value is not None else None)

    def s_throw(self, node: A.Throw, env: Environment):
        raise OmniThrow(self.eval(node.value, env), node.line, node.col)

    def s_break(self, node, env: Environment):
        raise OmniBreak()

    def s_continue(self, node, env: Environment):
        raise OmniContinue()

    def s_use(self, node: A.Use, env: Environment):
        path = self.resolve_module(node.path, env)
        mod_env = self.load_module(path)
        if node.alias:
            view = {k: v for k, v in mod_env.vars.items() if not k.startswith("__")}
            env.define(node.alias, view)
        elif node.names:
            for orig, alias in node.names:
                val = mod_env.get(orig)
                if val is _MISSING:
                    raise OmniRuntimeError(f"module `{node.path}` has no `{orig}`", node.line)
                env.define(alias, val)
        else:
            for k, v in mod_env.vars.items():
                if not k.startswith("__"):
                    env.define(k, v)
        return None

    def resolve_module(self, path: str, env: Environment) -> str:
        candidates = [path]
        if not path.endswith(".omni"):
            candidates.append(path + ".omni")
        bases = []
        if self.current_file:
            bases.append(os.path.dirname(self.current_file))
        bases.append(self.root)
        # the std/ modules that ship with the language -- on disk, or copied out
        # of the archive when we are running as a zipapp
        bases.append(std_base())
        for base in bases:
            for cand in candidates:
                full = os.path.normpath(os.path.join(base, cand))
                if os.path.isfile(full):
                    return full
        for cand in candidates:
            if os.path.isfile(cand):
                return os.path.abspath(cand)
        raise OmniRuntimeError(f"cannot find module `{path}`",
                               hint=f"looked in {', '.join(bases)}")

    def load_module(self, abspath: str) -> Environment:
        key = os.path.abspath(abspath)
        if key in self.modules:
            return self.modules[key]
        with open(key, "r", encoding="utf-8") as fh:
            src = fh.read()
        env = Environment(self.globals, f"module:{os.path.basename(key)}")
        self.modules[key] = env          # registered first so cycles terminate
        prev = self.current_file
        self.current_file = key
        try:
            self.sources[key] = src
            self.run_program(parse(src, key), env, key)
        finally:
            self.current_file = prev
        return env

    def s_expr(self, node: A.ExprStmt, env: Environment):
        return self.eval(node.expr, env)

    def s_block(self, node: A.Block, env: Environment):
        return self.run_block(node, Environment(env, "block"))

    def s_if_stmt(self, node: A.If, env: Environment):
        return self.eval_if(node, env)

    def s_match_stmt(self, node: A.Match, env: Environment):
        return self.eval_match(node, env)

    _dispatch = {}

    # ------------------------------------------------------------ expressions
    def eval(self, node, env: Environment):
        handler = self._dispatch.get(type(node))
        if handler is None:
            raise OmniRuntimeError(f"cannot evaluate `{type(node).__name__}`",
                                   getattr(node, "line", None))
        return handler(self, node, env)

    def e_num(self, node: A.Num, env):
        return node.value

    def e_const(self, node: A.Const, env):
        return node.value

    def dunder(self, obj, name: str):
        """Find an operator hook such as `__add__` on an object, if it has one."""
        if isinstance(obj, OmniObject):
            m = obj.klass.lookup(name)
            if m is None:
                return None
            return BoundMethod(obj, m, obj.klass)
        if isinstance(obj, HostObject):
            got = obj.methods.get(name)
            if got is None:
                return None
            return BoundNative(obj, got)
        return None

    def e_chain_compare(self, node: A.ChainCompare, env):
        """`1 < x < 10` -- every pair must hold, each operand evaluated once."""
        left = self.eval(node.operands[0], env)
        for op, operand in zip(node.ops, node.operands[1:]):
            right = self.eval(operand, env)
            pair = A.Binary(op, A.Const(left), A.Const(right),
                            line=node.line, col=node.col)
            if not truthy(self.e_binary(pair, env)):
                return False
            left = right
        return True

    def e_multi_assign(self, node: A.MultiAssign, env):
        """`a, b = b, a` -- the right side is read before anything is written."""
        values = [self.eval(v, env) for v in node.values]
        targets = node.targets
        if len(values) == 1 and isinstance(values[0], list) \
                and len(values[0]) == len(targets):
            values = values[0]
        if len(values) != len(targets):
            raise OmniRuntimeError(
                f"cannot put {len(values)} values into {len(targets)} targets",
                node.line, node.col,
                hint="the two sides of `a, b = ...` must have the same length")
        for target, value in zip(targets, values):
            self.assign_to(target, value, env, node)
        return None

    def e_str(self, node: A.Str, env):
        if isinstance(node.chunks, str):
            return node.chunks
        parts = []
        for chunk in node.chunks:
            v = self.eval(chunk, env)
            parts.append(to_string(v))
        return "".join(parts)

    def e_bool(self, node: A.Bool, env):
        return node.value

    def e_null(self, node: A.Null, env):
        return None

    def e_ident(self, node: A.Ident, env):
        val = env.get(node.name)
        if val is _MISSING:
            known = set(env.vars)
            e = env
            while e is not None:
                known |= set(e.vars)
                e = e.parent
            builtins = set(self.builtin_index) | set(getattr(self, "prelude", ()))
            hint = suggest(node.name, known - builtins) or suggest(node.name, known)
            raise OmniNameError(f"`{node.name}` is not defined", node.line, node.col, hint)
        return val

    def e_sigattr(self, node: A.SigAttr, env):
        val = env.get("@" + node.name)
        if val is _MISSING:
            val = env.get(node.name)
        if val is _MISSING:
            raise OmniNameError(f"`@{node.name}` is not defined", node.line, node.col)
        return val

    def e_paren(self, node: A.Paren, env):
        return self.eval(node.inner, env)

    def e_block(self, node: A.Block, env):
        return self.run_block(node, Environment(env, "block"))

    def e_list(self, node: A.ListLit, env):
        out = []
        for item, is_spread in zip(node.items, node.spread):
            v = self.eval(item, env)
            # `[1..5]` expands; a bare `1..5` stays a range you can loop over
            if is_spread or isinstance(v, OmniRange):
                out.extend(self.iterate(v, node))
            else:
                out.append(v)
        return out

    def e_map(self, node: A.MapLit, env):
        out: dict = {}
        for key, value, is_spread in node.entries:
            if is_spread:
                v = self.eval(value, env)
                if not isinstance(v, dict):
                    raise OmniTypeError(f"cannot spread {type_name(v)} into a map",
                                        node.line, node.col)
                out.update(v)
                continue
            k = key if isinstance(key, (str, float)) else self.eval(key, env)
            if isinstance(k, bool):
                k = "true" if k else "false"
            elif isinstance(k, float) and k.is_integer():
                k = fmt_num(k)
            elif k is None:
                k = "null"
            elif not isinstance(k, (str, float)):
                k = to_string(k)
            out[k] = self.eval(value, env)
        return out

    def e_range(self, node: A.RangeLit, env):
        lo = self.eval(node.lo, env)
        hi = self.eval(node.hi, env) if node.hi is not None else None
        step = self.eval(node.step, env) if node.step is not None else None
        for v, what in ((lo, "range start"), (hi, "range end"), (step, "range step")):
            if v is not None and not isinstance(v, (int, float)):
                raise OmniTypeError(f"{what} must be a number, got {type_name(v)}",
                                    node.line, node.col)
        return OmniRange(float(lo), None if hi is None else float(hi),
                         None if step is None else float(step), bool(node.inclusive))

    def e_unary(self, node: A.Unary, env):
        v = self.eval(node.operand, env)
        if node.op == "-":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise OmniTypeError(f"cannot negate {type_name(v)}", node.line, node.col)
            return -float(v)
        if node.op == "not":
            return not truthy(v)
        if node.op == "~":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise OmniTypeError(f"`~` needs a number, got {type_name(v)}",
                                    node.line, node.col)
            return float(~int(v))
        raise OmniRuntimeError(f"unknown unary operator `{node.op}`", node.line)

    def e_binary(self, node: A.Binary, env):
        op = node.op
        if op == "and":
            left = self.eval(node.left, env)
            return self.eval(node.right, env) if truthy(left) else left
        if op == "or":
            left = self.eval(node.left, env)
            return left if truthy(left) else self.eval(node.right, env)

        left = self.eval(node.left, env)
        right = self.eval(node.right, env)

        hook = OPERATOR_HOOKS.get(op)
        if hook is not None:
            mine = self.dunder(left, hook)
            if mine is not None:
                return self.call_value(mine, [right], {}, node)
            theirs = self.dunder(right, "__r" + hook[2:])
            if theirs is not None:
                return self.call_value(theirs, [left], {}, node)

        if op == "==":
            if isinstance(left, OmniObject) and isinstance(right, OmniObject):
                m = left.klass.lookup("eq")
                if m is not None and left.klass is right.klass:
                    return truthy(self.call_value(m, [right], {}, node, self_obj=left))
            return omni_eq(left, right)
        if op == "!=":
            if isinstance(left, OmniObject) and isinstance(right, OmniObject):
                m = left.klass.lookup("eq")
                if m is not None and left.klass is right.klass:
                    return not truthy(self.call_value(m, [right], {}, node, self_obj=left))
            return not omni_eq(left, right)
        if op in ("is", "isnt"):
            result = self.type_matches(left, right)
            return result if op == "is" else not result
        if op in ("<", "<=", ">", ">="):
            c = compare(left, right)
            return {"<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0}[op]
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return to_string(left) + to_string(right)
            if isinstance(left, list):
                if isinstance(right, list):
                    return left + right
                return left + [right]
            if isinstance(right, list) and isinstance(left, (int, float, str, bool)):
                return [left] + right
            if isinstance(left, dict) and isinstance(right, dict):
                return {**left, **right}
            self.arith_check(left, right, op, node)
            return float(left) + float(right)
        if op == "-":
            self.arith_check(left, right, op, node)
            return float(left) - float(right)
        if op == "*":
            if isinstance(left, str) and isinstance(right, (int, float)):
                return left * int(right)
            if isinstance(left, (int, float)) and isinstance(right, str):
                return right * int(left)
            if isinstance(left, list) and isinstance(right, (int, float)):
                return left * int(right)
            self.arith_check(left, right, op, node)
            return float(left) * float(right)
        if op == "/":
            self.arith_check(left, right, op, node)
            if float(right) == 0.0:
                raise OmniRuntimeError("division by zero", node.line, node.col,
                                       hint="use `a / b` only when b is non-zero, "
                                            "or guard it with `if b != 0`")
            return float(left) / float(right)
        if op == "%":
            self.arith_check(left, right, op, node)
            if float(right) == 0.0:
                raise OmniRuntimeError("modulo by zero", node.line, node.col)
            return float(left) % float(right)
        if op == "//":
            self.arith_check(left, right, op, node)
            if float(right) == 0.0:
                raise OmniRuntimeError("division by zero", node.line, node.col,
                                       hint="`//` is whole-number division")
            return float(float(left) // float(right))
        if op == "**":
            self.arith_check(left, right, op, node)
            r = float(left) ** float(right)
            if isinstance(r, complex):
                raise OmniRuntimeError("a negative number raised to a fractional power "
                                       "is not a real number", node.line, node.col)
            return float(r)
        if op in ("&", "|", "^", "<<", ">>"):
            self.arith_check(left, right, op, node, ints=True)
            a, b = int(left), int(right)
            return float({"&": a & b, "|": a | b, "^": a ^ b,
                          "<<": a << b, ">>": a >> b}[op])
        raise OmniRuntimeError(f"unknown operator `{op}`", node.line)

    def arith_check(self, left, right, op, node, ints=False):
        for v in (left, right):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise OmniTypeError(
                    f"`{op}` needs numbers, got {type_name(left)} and {type_name(right)}",
                    node.line, node.col,
                    hint="use `+` with strings to join text, or `to_num()` to convert")

    def type_matches(self, value, right) -> bool:
        """`x is num` passes a type name; `x is Point` passes a class."""
        if isinstance(right, str):
            return self.check_type(value, right)
        if isinstance(right, OmniClass):
            return self.instance_of(value, right)
        raise OmniTypeError("`is` compares against a type name or a class")

    def instance_of(self, value, klass: OmniClass) -> bool:
        if isinstance(value, OmniObject):
            c: OmniClass | None = value.klass
            while c is not None:
                if c is klass:
                    return True
                c = c.parent
        return False

    def check_type(self, value, name: str) -> bool:
        if isinstance(value, OmniObject):
            c: OmniClass | None = value.klass
            while c is not None:
                if c.name == name:
                    return True
                c = c.parent
        t = type_name(value)
        if name == "any":
            return True
        if name in ("num", "int"):
            if name == "int":
                return isinstance(value, (int, float)) and not isinstance(value, bool) \
                    and float(value).is_integer()
            return t == "num"
        if name == "obj":
            return isinstance(value, (OmniObject, HostObject))
        if name == "fn":
            return isinstance(value, (OmniFunction, NativeFunction, BoundNative, BoundMethod))
        return t == name

    def e_ternary(self, node: A.Ternary, env):
        return self.eval(node.then, env) if truthy(self.eval(node.cond, env)) \
            else self.eval(node.otherwise, env)

    def e_elvis(self, node: A.Elvis, env):
        left = self.eval(node.left, env)
        return left if left is not None else self.eval(node.right, env)

    def e_if(self, node: A.If, env):
        return self.eval_if(node, env)

    def eval_if(self, node: A.If, env):
        for cond, body in node.branches:
            if truthy(self.eval(cond, env)):
                return self.run_block(body, Environment(env, "if"))
        if node.otherwise is not None:
            return self.run_block(node.otherwise, Environment(env, "else"))
        return None

    def e_match(self, node: A.Match, env):
        return self.eval_match(node, env)

    def eval_match(self, node: A.Match, env):
        subject = self.eval(node.subject, env)
        for arm in node.arms:
            bindings: dict[str, Any] = {}
            if self.match_pattern(arm.pattern, subject, bindings, env):
                if arm.guard is not None:
                    genv = Environment(env, "guard")
                    for k, v in bindings.items():
                        genv.define(k, v)
                    if not truthy(self.eval(arm.guard, genv)):
                        continue
                aenv = Environment(env, "match")
                for k, v in bindings.items():
                    aenv.define(k, v)
                return self.eval(arm.value, aenv)
        raise OmniRuntimeError(
            f"no match arm fits {describe(subject)}", node.line, node.col,
            hint="add a `_ => ...` arm to catch everything else")

    def match_pattern(self, pattern, value, bindings: dict, env) -> bool:
        if isinstance(pattern, A.PWild):
            return True
        if isinstance(pattern, A.PBind):
            bindings[pattern.name] = value
            return True
        if isinstance(pattern, A.PLit):
            return omni_eq(pattern.value, value)
        if isinstance(pattern, A.PTyped):
            ok = self.check_type(value, pattern.type)
            if ok and not pattern.neg:
                bindings[pattern.name] = value
            if pattern.neg and ok:
                return False
            if pattern.neg:
                bindings[pattern.name] = value
                return True
            return ok
        if isinstance(pattern, A.PList):
            if not isinstance(value, list):
                return False
            items = value
            if pattern.rest is None and len(items) != len(pattern.items):
                return False
            if len(items) < len(pattern.items):
                return False
            for sub, item in zip(pattern.items, items):
                if not self.match_pattern(sub, item, bindings, env):
                    return False
            if pattern.rest is not None:
                bindings[pattern.rest] = list(items[len(pattern.items):])
            return True
        if isinstance(pattern, A.PMap):
            if not isinstance(value, dict):
                return False
            for key, sub in pattern.entries:
                kname = key if isinstance(key, str) else self.eval(key, env)
                if kname not in value:
                    return False
                if not self.match_pattern(sub, value[kname], bindings, env):
                    return False
            return True
        raise OmniRuntimeError(f"bad pattern `{type(pattern).__name__}`")

    # ----------------------------------------------------------- assignment
    def e_assign(self, node: A.Assign, env):
        value = self.eval(node.value, env)
        target = node.target
        if node.op != "=":
            current = self.eval(target, env)
            value = self.apply_compound(node.op, current, value, node)
        self.assign_to(target, value, env, node)
        return value

    def apply_compound(self, op, current, value, node):
        if op == "+":
            if isinstance(current, str) or isinstance(value, str):
                return to_string(current) + to_string(value)
            if isinstance(current, list):
                return current + (value if isinstance(value, list) else [value])
            if isinstance(current, dict) and isinstance(value, dict):
                return {**current, **value}
        self.arith_check(current, value, op, node)
        a, bb = float(current), float(value)
        result = self.eval_binary_op(op, a, bb, node)
        return result

    def eval_binary_op(self, op, a, b, node):
        tmp = A.Binary(op, A.Num(a), A.Num(b), line=node.line, col=node.col)
        env = self.globals
        return self.e_binary(tmp, env)

    def assign_to(self, target, value, env, node):
        if isinstance(target, A.Ident):
            existing = env.find(target.name)
            if existing is None:
                known = set()
                e = env
                while e is not None:
                    known |= set(e.vars)
                    e = e.parent
                hint = suggest(target.name, known) or (
                    f"declare it first with `let {target.name} = ...` or "
                    f"`mut {target.name} = ...`")
                raise OmniNameError(f"`{target.name}` is not defined",
                                    node.line, node.col, hint=hint)
            existing.assign(target.name, value, node)
        elif isinstance(target, A.Index):
            obj = self.eval(target.obj, env)
            key = self.eval(target.index, env)
            self.set_index(obj, key, value, node)
        elif isinstance(target, A.Member):
            obj = self.eval(target.obj, env)
            self.set_member(obj, target.name, value, node)
        elif isinstance(target, A.Slice):
            obj = self.eval(target.obj, env)
            lo = self.eval(target.lo, env) if target.lo is not None else None
            hi = self.eval(target.hi, env) if target.hi is not None else None
            step = self.eval(target.step, env) if target.step is not None else None
            if isinstance(obj, list):
                obj[slice(_int(lo), _int(hi), _int(step))] = value
            else:
                raise OmniTypeError(f"cannot assign into {type_name(obj)}",
                                    node.line, node.col)
        else:
            raise OmniRuntimeError("cannot assign to this expression", node.line, node.col)

    def set_index(self, obj, key, value, node):
        if isinstance(obj, list):
            idx = _int(key, node)
            if idx < 0:
                idx += len(obj)
            if 0 <= idx < len(obj):
                obj[idx] = value
            elif idx == len(obj):
                obj.append(value)
            else:
                raise OmniRuntimeError(f"index {idx} is out of range for a list of "
                                       f"length {len(obj)}", node.line, node.col)
        elif isinstance(obj, dict):
            obj[_hashable(key)] = value
        elif isinstance(obj, HostObject):
            obj.fields[_hashable(key)] = value
        elif isinstance(obj, OmniObject):
            obj.fields[_hashable(key)] = value
        else:
            raise OmniTypeError(f"cannot index into {type_name(obj)}", node.line, node.col)

    def set_member(self, obj, name, value, node):
        if isinstance(obj, dict):
            obj[name] = value
        elif isinstance(obj, OmniObject):
            obj.fields[name] = value
        elif isinstance(obj, HostObject):
            obj.fields[name] = value
        elif isinstance(obj, OmniClass):
            obj.methods[name] = value
        else:
            raise OmniTypeError(
                f"cannot set `.{name}` on {type_name(obj)}", node.line, node.col,
                hint="only maps and objects have writable fields")

    # ------------------------------------------------------- member & index
    def e_member(self, node: A.Member, env):
        obj = self.eval(node.obj, env)
        if obj is None:
            if node.optional:
                return None
            raise OmniTypeError(f"cannot read `.{node.name}` of null", node.line, node.col,
                                hint="use `?.` to read it safely, or `?? default`")
        val = self.get_member(obj, node.name, node, env)
        if val is _MISSING:
            if node.optional:
                return None
            self.member_error(obj, node.name, node)
        return val

    def member_error(self, obj, name, node):
        candidates: list[str] = []
        t = type_name(obj)
        candidates += list(self.methods.get(t, {}).keys())
        if isinstance(obj, dict):
            candidates += [str(k) for k in obj.keys()]
        elif isinstance(obj, OmniObject):
            candidates += list(obj.fields.keys())
            candidates += list(obj.klass.methods.keys())
        elif isinstance(obj, HostObject):
            candidates += list(obj.methods.keys()) + list(obj.fields.keys())
        elif isinstance(obj, OmniClass):
            candidates += list(obj.methods.keys())
        hint = suggest(name, candidates)
        if isinstance(obj, dict):
            hint = hint or f"the map has keys: {', '.join(str(k) for k in list(obj)[:10])}"
        raise OmniTypeError(f"{t} has no member `{name}`", node.line, node.col, hint)

    def get_member(self, obj, name: str, node, env):
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            table = self.methods.get("map")
            if table and name in table:
                return BoundNative(obj, table[name])
            return _MISSING
        if isinstance(obj, OmniObject):
            if name in obj.fields:
                return obj.fields[name]
            m = obj.klass.lookup(name)
            if m is not None:
                return BoundMethod(obj, m, obj.klass)
            return _MISSING
        if isinstance(obj, OmniClass):
            if name in obj.methods:
                return obj.methods[name]
            return _MISSING
        if isinstance(obj, HostObject):
            got = obj.get(name)
            # a host method has to carry its receiver along with it
            if isinstance(got, NativeFunction):
                return BoundNative(obj, got)
            return got
        table = self.methods.get(type_name(obj))
        if table and name in table:
            return BoundNative(obj, table[name])
        if name == "len" and isinstance(obj, (list, str, dict)):
            return float(len(obj))
        if name == "size" and isinstance(obj, (list, str, dict)):
            return float(len(obj))
        return _MISSING

    def e_index(self, node: A.Index, env):
        obj = self.eval(node.obj, env)
        key = self.eval(node.index, env)
        return self.get_index(obj, key, node)

    def get_index(self, obj, key, node):
        if isinstance(obj, list):
            idx = _int(key, node)
            if idx < 0:
                idx += len(obj)
            if not (0 <= idx < len(obj)):
                raise OmniRuntimeError(f"index {fmt_num(float(key))} is out of range "
                                       f"for a list of length {len(obj)}",
                                       node.line, node.col,
                                       hint="negative indexes count from the end")
            return obj[idx]
        if isinstance(obj, str):
            idx = _int(key, node)
            if idx < 0:
                idx += len(obj)
            if not (0 <= idx < len(obj)):
                raise OmniRuntimeError(f"index out of range for a string of length {len(obj)}",
                                       node.line, node.col)
            return obj[idx]
        if isinstance(obj, dict):
            k = _hashable(key)
            if k in obj:
                return obj[k]
            return None
        if isinstance(obj, OmniRange):
            return obj.values()[_int(key, node)]
        if isinstance(obj, (OmniObject, HostObject)):
            got = obj.get(_hashable(key)) if isinstance(obj, HostObject) \
                else obj.fields.get(_hashable(key), _MISSING)
            if got is _MISSING:
                raise OmniRuntimeError(f"<{type_name(obj)}> has no field `{describe(key)}`",
                                       node.line, node.col)
            return got
        raise OmniTypeError(f"cannot index into {type_name(obj)}", node.line, node.col)

    def e_slice(self, node: A.Slice, env):
        obj = self.eval(node.obj, env)
        lo = self.eval(node.lo, env) if node.lo is not None else None
        hi = self.eval(node.hi, env) if node.hi is not None else None
        step = self.eval(node.step, env) if node.step is not None else None
        s = slice(_int(lo), _int(hi), _int(step))
        if isinstance(obj, (list, str)):
            return obj[s]
        if isinstance(obj, OmniRange):
            return obj.values()[s]
        raise OmniTypeError(f"cannot slice {type_name(obj)}", node.line, node.col)

    # -------------------------------------------------------------- calling
    def e_call(self, node: A.Call, env):
        args, kwargs = self.eval_args(node.args, node.kwargs, env)
        callee = node.callee
        if node.is_new:
            klass = self.eval(callee, env)
            if not isinstance(klass, OmniClass):
                raise OmniTypeError(f"`{to_string(klass)}` is not a class, so `new` "
                                    f"cannot build one", node.line, node.col)
            return self.construct(klass, args, kwargs, node)
        if isinstance(callee, A.Member):
            obj = self.eval(callee.obj, env)
            if obj is None and callee.optional:
                return None
            self_obj = obj
            if isinstance(callee.obj, A.Ident) and callee.obj.name == "super":
                # super lives in the method scope; the receiver is `self`
                self_obj = env.get("self")
                if self_obj is _MISSING:
                    raise OmniRuntimeError("`super` only works inside a method",
                                           node.line, node.col)
            fn = self.get_member(obj, callee.name, callee, env)
            if fn is _MISSING:
                if callee.optional:
                    return None      # `cfg?.missing()` stays null instead of raising
                self.member_error(obj, callee.name, callee)
            if fn is _MISSING:
                self.member_error(obj, callee.name, node)
            if isinstance(fn, (OmniFunction,)):
                return self.call_function(fn, args, kwargs, node, self_obj=self_obj)
            return self.call_value(fn, args, kwargs, node, self_obj=self_obj)
        fn = self.eval(callee, env)
        return self.call_value(fn, args, kwargs, node)

    def eval_args(self, arg_nodes, kwarg_nodes, env):
        args = []
        for a in arg_nodes:
            if isinstance(a, tuple):
                kind, expr = a
                v = self.eval(expr, env)
                if kind == "*":
                    args.extend(self.iterate(v, expr))
                else:
                    if not isinstance(v, dict):
                        raise OmniTypeError("`**` needs a map", expr.line, expr.col)
                    for k, val in v.items():
                        args.append((str(k), val))
            else:
                args.append(self.eval(a, env))
        kwargs = {}
        for name, expr in kwarg_nodes:
            kwargs[name] = self.eval(expr, env)
        # `**` spreads arrive as (name, value) tuples inside the positional list
        positional, spread_kw = [], {}
        for a in args:
            if isinstance(a, tuple) and len(a) == 2 and isinstance(a[0], str):
                spread_kw[a[0]] = a[1]
            else:
                positional.append(a)
        if spread_kw:
            kwargs = {**spread_kw, **kwargs}
        return positional, kwargs

    def construct(self, klass: OmniClass, args, kwargs, node):
        obj = OmniObject(klass)
        # inherited field defaults first, then our own
        chain = []
        k: OmniClass | None = klass
        while k is not None:
            chain.append(k)
            k = k.parent
        for c in reversed(chain):
            for fname, fexpr, fenv in c.fields:
                fscope = Environment(fenv, "field")
                fscope.define("self", obj)
                obj.fields[fname] = self.eval(fexpr, fscope)
        ctor = klass.lookup("new")
        if ctor is not None:
            self.call_function(ctor, args, kwargs, node, self_obj=obj)
        elif args or kwargs:
            names = [f[0] for f in klass.fields]
            if len(args) > len(names):
                extra = len(args) - len(names)
                fields = ", ".join(names) or "no fields at all"
                raise OmniRuntimeError(
                    f"`new {klass.name}()` got {extra} argument{'s' if extra > 1 else ''} "
                    f"too many",
                    getattr(node, "line", None), getattr(node, "col", None),
                    hint=f"{klass.name} has {fields}, and no `new` to take the rest -- "
                         f"give it one, or pass keywords")
            for name, value in list(kwargs.items()):
                obj.fields[name] = value
            for name, value in zip(names, args):
                if name not in kwargs:
                    obj.fields[name] = value
        return obj

    def call_value(self, fn, args, kwargs, node, self_obj=None):
        if isinstance(fn, BoundNative):
            return self.call_native(fn.fn, [fn.obj] + list(args), kwargs, node)
        if isinstance(fn, BoundMethod):
            return self.call_function(fn.fn, args, kwargs, node, self_obj=fn.obj,
                                      owner=fn.owner)
        if isinstance(fn, NativeFunction):
            return self.call_native(fn, args, kwargs, node)
        if isinstance(fn, OmniFunction):
            return self.call_function(fn, args, kwargs, node, self_obj=self_obj)
        if isinstance(fn, OmniClass):
            return self.construct(fn, args, kwargs, node)
        if isinstance(fn, HostObject) and "__call__" in fn.methods:
            return self.call_value(fn.methods["__call__"], args, kwargs, node)
        if callable(fn):
            return fn(*args)
        hint = "only functions and classes can be called with ()"
        name = getattr(getattr(node, "callee", None), "name", None)
        if name and name in self.builtin_names():
            hint = (f"`{name}` is a {type_name(fn)} here, which hides the built-in "
                    f"function `{name}()` -- rename the variable to call it")
        raise OmniTypeError(f"`{to_repr(fn)}` is not callable",
                            getattr(node, "line", None), getattr(node, "col", None),
                            hint=hint)

    _builtin_names = None

    @classmethod
    def builtin_names(cls):
        if cls._builtin_names is None:
            from .stdlib.core import BUILTINS
            cls._builtin_names = {nf.name for nf in BUILTINS}
        return cls._builtin_names

    def call_loose(self, fn, args, kwargs=None, node=None):
        """Call a callback, dropping extra arguments it did not ask for.

        That is what makes `[1,2,3].map((x) -> x * 2)` work even though `map`
        offers each callback both the item and its index.
        """
        target = fn
        extra: list = []
        if isinstance(target, BoundNative):
            extra = [target.obj]
            target = target.fn
        elif isinstance(target, BoundMethod):
            extra = []
            target = target.fn
        params = getattr(target, "params", None)
        if params is not None and not any(p.get("rest") for p in params):
            capacity = sum(1 for p in params
                           if not p.get("kwrest") and not p.get("kw_only"))
            if len(extra) + len(args) > capacity:
                keep = max(0, capacity - len(extra))
                args = list(args)[:keep]
        return self.call_value(fn, list(args), dict(kwargs or {}), node)

    def call_native(self, fn: NativeFunction, args, kwargs, node):
        bound = bind_native(fn.params, args, kwargs, fn.name, node)
        if len(self.stack) > MAX_CALL_DEPTH:
            raise OmniRuntimeError("stack overflow: too many nested calls",
                                   getattr(node, "line", None))
        # Rebuild the Python call so positional parameters keep their order and
        # only keyword-only / `**kwrest` parameters travel by name.
        call_args: list = []
        call_kwargs: dict = {}
        for p in fn.params:
            name = p["name"]
            if p.get("rest"):
                call_args.extend(bound.get(name, []))
            elif p.get("kwrest"):
                call_kwargs.update(bound.get(name, {}))
            elif p.get("kw_only"):
                if name in bound:
                    call_kwargs[name] = bound[name]
            elif name in bound:
                call_args.append(bound[name])
        self.stack.append((fn.name, getattr(node, "line", None)))
        try:
            if fn.takes_interp:
                return fn.fn(self, *call_args, **call_kwargs)
            return fn.fn(*call_args, **call_kwargs)
        except OmniError as e:
            if e.line is None and node is not None:
                e.line, e.col = node.line, node.col
            raise
        except TypeError as e:
            raise OmniTypeError(f"bad arguments to `{fn.name}`: {e}",
                                getattr(node, "line", None))
        finally:
            self.stack.pop()

    def call_function(self, fn: OmniFunction, args, kwargs, node, self_obj=None,
                      owner: OmniClass | None = None):
        if len(self.stack) > MAX_CALL_DEPTH:
            raise OmniRuntimeError("stack overflow: too much recursion",
                                   getattr(node, "line", None),
                                   hint=f"check that `{fn.name}` eventually stops calling itself")
        env = Environment(fn.closure, fn.name)
        if self_obj is not None:
            env.define("self", self_obj)
            if owner is not None and owner.parent is not None:
                env.define("super", owner.parent)
        bind_params(self, fn.params, args, kwargs, env, fn.name, node)
        self.stack.append((fn.name, getattr(node, "line", None)))
        try:
            return self.run_block(fn.body, env)
        except OmniReturn as r:
            return r.value
        finally:
            self.stack.pop()

    # -------------------------------------------------------------- pipes
    def e_pipe(self, node: A.Pipe, env):
        callee_node = node.callee
        args, kwargs = self.eval_args(node.args, node.kwargs, env)
        if isinstance(callee_node, A.Member):
            obj = self.eval(callee_node.obj, env)
            fn = self.get_member(obj, callee_node.name, callee_node, env)
            if fn is _MISSING:
                self.member_error(obj, callee_node.name, node)
            if isinstance(fn, OmniFunction):
                return self.call_function(fn, args, kwargs, node, self_obj=obj)
            return self.call_value(fn, args, kwargs, node, self_obj=obj)
        fn = self.eval(callee_node, env)
        return self.call_value(fn, args, kwargs, node)

    # -------------------------------------------------------------- lambda
    def e_lambda(self, node: A.Lambda, env):
        params = []
        for p in node.params:
            q = dict(p)
            q.setdefault("kw_only", False)
            q.setdefault("type", None)
            q.setdefault("pattern", None)
            params.append(q)
        if node.is_block:
            body = node.body
        else:
            body = A.Block([A.Return(node.body, line=node.body.line)], True,
                           line=node.line)
        return OmniFunction("anonymous", params, body, env, [])

    # ------------------------------------------------------------ iterating
    def iterate(self, value, node=None) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return list(value)
        if isinstance(value, dict):
            return list(value.keys())
        if isinstance(value, OmniRange):
            return value.values()
        if isinstance(value, OmniObject):
            m = value.klass.lookup("iter")
            if m is not None:
                return list(self.call_value(m, [], {}, node, self_obj=value))
        if isinstance(value, HostObject) and "__iter__" in value.methods:
            return list(self.call_value(value.methods["__iter__"], [], {}, node) or [])
        raise OmniTypeError(f"cannot iterate over {type_name(value)}",
                            getattr(node, "line", None), getattr(node, "col", None))

    # ---------------------------------------------------------------- errors
    def enrich(self, err: OmniError, path: str | None):
        if err.source is None:
            which = path or self.current_file
            err.source = self.sources.get(which) if which else None
            err.path = which
        if not err.trace:
            err.trace = list(self.stack)
        return err


def _int(v, node=None) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise OmniTypeError(f"expected a whole number, got {describe(v)}",
                            getattr(node, "line", None), getattr(node, "col", None))
    return int(v)


def _hashable(key):
    if isinstance(key, bool):
        return "true" if key else "false"
    if isinstance(key, float):
        return fmt_num(key) if key.is_integer() else key
    if key is None:
        return "null"
    if isinstance(key, str):
        return key
    if isinstance(key, (list, dict)):
        return to_repr(key)
    return key


def bind_native(params, args, kwargs, fname, node):
    return _bind(params, args, kwargs, fname, node, evaluate=None)


def bind_params(interp: "Interpreter", params, args, kwargs, env: Environment,
                fname: str, node):
    bound = _bind(params, args, kwargs, fname, node,
                  evaluate=lambda p: interp.eval(p["default"], env))
    patterns = {p["name"]: p.get("pattern") for p in params if p.get("pattern")}
    for name, value in bound.items():
        pattern = patterns.get(name)
        if pattern is not None:
            # `fn dist([x1, y1], ...)` -- unpack the argument into its parts
            interp.bind_pattern(pattern, value, env, False, node)
        else:
            env.define(name, value)


def _bind(params, args, kwargs, fname, node, evaluate):
    """Match arguments to parameters.

    Order of filling: plain positional parameters, then `*rest` mops up what is
    left, then keyword-only parameters, then `**kwrest` collects the rest.
    """
    line = getattr(node, "line", None)
    col = getattr(node, "col", None)
    positional = [p for p in params
                  if not p.get("rest") and not p.get("kwrest") and not p.get("kw_only")]
    kw_only = [p for p in params if p.get("kw_only")]
    rest = next((p for p in params if p.get("rest")), None)
    kwrest = next((p for p in params if p.get("kwrest")), None)

    def default_for(p):
        if evaluate is not None:
            return evaluate(p)
        return p.get("default")

    def has_default(p):
        if evaluate is not None:
            return p.get("default") is not None
        return p.get("has_default", p.get("default") is not None)

    bound: dict = {}
    idx = 0
    for p in positional:
        name = p["name"]
        if name in kwargs:
            bound[name] = kwargs.pop(name)
        elif idx < len(args):
            bound[name] = args[idx]
            idx += 1
        elif has_default(p):
            bound[name] = default_for(p)
        else:
            raise OmniRuntimeError(f"`{fname}()` is missing its `{name}` argument",
                                   line, col, hint=f"`{fname}()` expects: {sig_of(params)}")
    if rest:
        bound[rest["name"]] = list(args[idx:])
    elif idx < len(args):
        extra = len(args) - idx
        raise OmniRuntimeError(
            f"`{fname}()` got {extra} argument{'s' if extra > 1 else ''} too many",
            line, col, hint=f"`{fname}()` expects: {sig_of(params)}")
    for p in kw_only:
        name = p["name"]
        if name in kwargs:
            bound[name] = kwargs.pop(name)
        elif has_default(p):
            bound[name] = default_for(p)
        else:
            raise OmniRuntimeError(f"`{fname}()` needs `{name}:` to be passed by name",
                                   line, col, hint=f"`{fname}()` expects: {sig_of(params)}")
    if kwrest:
        bound[kwrest["name"]] = dict(kwargs)
    elif kwargs:
        unknown = next(iter(kwargs))
        raise OmniRuntimeError(f"`{fname}()` has no argument called `{unknown}`",
                               line, col,
                               hint=suggest(unknown, [p["name"] for p in params]) or
                               f"`{fname}()` expects: {sig_of(params)}")
    return bound


def sig_of(params) -> str:
    parts = []
    for p in params:
        if p.get("rest"):
            parts.append("*" + p["name"])
        elif p.get("kwrest"):
            parts.append("**" + p["name"])
        elif p.get("default") is not None:
            d = p["default"]
            shown = "..." if not isinstance(d, (str, float, int, bool)) else to_repr(d)
            parts.append(f"{p['name']}={shown}")
        else:
            parts.append(p["name"])
    return "(" + ", ".join(parts) + ")"


# `a + b` on an object calls its `__add__`; `1 + obj` calls the object's
# `__radd__`. Classes get operator overloading for free.
OPERATOR_HOOKS = {
    "+": "__add__", "-": "__sub__", "*": "__mul__", "/": "__div__",
    "//": "__idiv__", "%": "__mod__", "**": "__pow__",
    "<": "__lt__", "<=": "__le__", ">": "__gt__", ">=": "__ge__",
    "==": "__eq__", "!=": "__ne__",
}


Interpreter._dispatch = {
    A.Let: Interpreter.s_let,
    A.FnDecl: Interpreter.s_fndecl,
    A.ClassDecl: Interpreter.s_class,
    A.For: Interpreter.s_for,
    A.While: Interpreter.s_while,
    A.DoWhile: Interpreter.s_dowhile,
    A.Try: Interpreter.s_try,
    A.Return: Interpreter.s_return,
    A.Throw: Interpreter.s_throw,
    A.Break: Interpreter.s_break,
    A.Continue: Interpreter.s_continue,
    A.Use: Interpreter.s_use,
    A.ExprStmt: Interpreter.s_expr,
    A.Block: Interpreter.s_block,
    A.Num: Interpreter.e_num,
    A.Const: Interpreter.e_const,
    A.ChainCompare: Interpreter.e_chain_compare,
    A.MultiAssign: Interpreter.e_multi_assign,
    A.Str: Interpreter.e_str,
    A.Bool: Interpreter.e_bool,
    A.Null: Interpreter.e_null,
    A.Ident: Interpreter.e_ident,
    A.SigAttr: Interpreter.e_sigattr,
    A.Paren: Interpreter.e_paren,
    A.ListLit: Interpreter.e_list,
    A.MapLit: Interpreter.e_map,
    A.RangeLit: Interpreter.e_range,
    A.Unary: Interpreter.e_unary,
    A.Binary: Interpreter.e_binary,
    A.Ternary: Interpreter.e_ternary,
    A.Elvis: Interpreter.e_elvis,
    A.If: Interpreter.e_if,
    A.Match: Interpreter.e_match,
    A.Assign: Interpreter.e_assign,
    A.Member: Interpreter.e_member,
    A.Index: Interpreter.e_index,
    A.Slice: Interpreter.e_slice,
    A.Call: Interpreter.e_call,
    A.Pipe: Interpreter.e_pipe,
    A.Lambda: Interpreter.e_lambda,
}
