"""OmniScript runtime values.

Value model
-----------
    number   -> Python float (printed without a trailing .0 when integral)
    string   -> Python str
    bool     -> Python bool
    null     -> Python None
    list     -> Python list
    map      -> Python dict
    range    -> OmniRange
    function -> OmniFunction (script) | NativeFunction (host)
    class    -> OmniClass
    instance -> OmniObject
    host obj -> HostObject (Canvas, HttpResponse, CommandResult, ...)
"""

from __future__ import annotations

import inspect
from typing import Any, Callable


# --------------------------------------------------------------------- values
class OmniFunction:
    """A function written in OmniScript."""

    __slots__ = ("name", "params", "body", "closure", "attrs", "is_method")

    def __init__(self, name, params, body, closure, attrs=None, is_method=False):
        self.name = name
        self.params = params
        self.body = body
        self.closure = closure
        self.attrs = [] if attrs is None else attrs
        self.is_method = is_method

    def __repr__(self):
        return f"<fn {self.name}>"


class NativeFunction:
    """A host function exposed to OmniScript.

    `takes_interp` is True for global built-ins (they receive the interpreter
    as their first Python argument) and False for dot-methods (the receiver
    arrives through the ordinary `self` parameter instead).
    """

    __slots__ = ("name", "fn", "doc", "params", "module", "takes_interp")

    def __init__(self, name: str, fn: Callable, doc: str = "", params=None,
                 module="", takes_interp: bool = True):
        self.name = name
        self.fn = fn
        self.doc = doc or ""
        self.params = params or []
        self.module = module
        self.takes_interp = takes_interp

    def __repr__(self):
        return f"<fn {self.name}>"


class OmniClass:
    __slots__ = ("name", "parent", "methods", "fields", "attrs")

    def __init__(self, name, parent=None, methods=None, fields=None, attrs=None):
        self.name = name
        self.parent = parent
        # NOTE: not `methods or {}` -- an empty dict is falsy, and s_class keeps
        # filling in the very container we are handed here.
        self.methods = {} if methods is None else methods
        self.fields = [] if fields is None else fields
        self.attrs = [] if attrs is None else attrs

    def lookup(self, name: str):
        klass: OmniClass | None = self
        while klass is not None:
            if name in klass.methods:
                return klass.methods[name]
            klass = klass.parent
        return None

    def __repr__(self):
        return f"<class {self.name}>"


class OmniObject:
    """An instance of an OmniScript class."""

    __slots__ = ("klass", "fields")

    def __init__(self, klass: OmniClass, fields: dict | None = None):
        self.klass = klass
        self.fields = fields if fields is not None else {}

    def __repr__(self):
        return f"<{self.klass.name}>"


class HostObject:
    """A host value with named methods, e.g. a Canvas or a CommandResult."""

    __slots__ = ("type_name", "methods", "fields", "display", "data")

    def __init__(self, type_name: str, methods: dict | None = None,
                 fields: dict | None = None, display: Callable | None = None,
                 data: Any = None):
        self.type_name = type_name
        self.methods = {} if methods is None else methods
        self.fields = {} if fields is None else fields
        self.display = display
        self.data = data

    def get(self, name: str):
        if name in self.methods:
            return self.methods[name]
        if name in self.fields:
            return self.fields[name]
        return _MISSING

    def __repr__(self):
        return f"<{self.type_name}>"


class OmniRange:
    __slots__ = ("lo", "hi", "step", "inclusive")

    def __init__(self, lo: float, hi: float | None, step: float | None, inclusive: bool):
        self.lo = lo
        self.hi = hi
        self.step = step if step is not None else 1.0
        self.inclusive = inclusive

    def values(self):
        if self.hi is None:
            raise ValueError("open range")
        out = []
        v = self.lo
        s = self.step
        if s == 0:
            raise ValueError("range step cannot be 0")
        if s > 0:
            while (v <= self.hi) if self.inclusive else (v < self.hi):
                out.append(v)
                v += s
        else:
            while (v >= self.hi) if self.inclusive else (v > self.hi):
                out.append(v)
                v += s
        return out

    def __len__(self):
        return len(self.values())

    def __iter__(self):
        return iter(self.values())

    def __repr__(self):
        dots = "..=" if self.inclusive else ".."
        hi = "" if self.hi is None else fmt_num(self.hi)
        step = f"..{fmt_num(self.step)}" if self.step != 1.0 else ""
        return f"{fmt_num(self.lo)}{dots}{hi}{step}"


class _Missing:
    def __repr__(self):
        return "<missing>"

    def __bool__(self):
        return False


_MISSING = _Missing()


# ------------------------------------------------------------------ utilities
def fmt_num(v: float) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v != v:  # NaN
        return "nan"
    if v in (float("inf"), float("-inf")):
        return "inf" if v > 0 else "-inf"
    if float(v).is_integer() and abs(v) < 1e16:
        return str(int(v))
    r = repr(float(v))
    return r


def type_name(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, float) or isinstance(v, int):
        return "num"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "map"
    if isinstance(v, OmniRange):
        return "range"
    if isinstance(v, (OmniFunction, NativeFunction)):
        return "fn"
    if isinstance(v, OmniClass):
        return "class"
    if isinstance(v, OmniObject):
        return v.klass.name
    if isinstance(v, HostObject):
        return v.type_name
    return type(v).__name__


def truthy(v) -> bool:
    if v is None or v is False:
        return False
    if v is True:
        return True
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    if isinstance(v, (list, dict)):
        return len(v) > 0
    if isinstance(v, OmniRange):
        return v.hi is not None
    return True


def omni_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if type(a) is not type(b):
        return False
    if isinstance(a, str):
        return a == b
    if isinstance(a, list):
        return len(a) == len(b) and all(omni_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        if len(a) != len(b):
            return False
        for k, v in a.items():
            if k not in b or not omni_eq(v, b[k]):
                return False
        return True
    if isinstance(a, OmniRange):
        return (a.lo, a.hi, a.step, a.inclusive) == (b.lo, b.hi, b.step, b.inclusive)
    if isinstance(a, OmniObject):
        eq = a.klass.lookup("eq")
        if eq is not None:
            return truthy(_call_method(a, "eq", [b]))
        return a is b
    return a is b


def _call_method(obj, name, args):
    """Tiny helper used by omni_eq; the real dispatcher lives in the interp."""
    from .interp import Interpreter
    return Interpreter.current().call_value(obj.klass.lookup(name), args, {},
                                            node=None, self_obj=obj)


def to_string(v) -> str:
    """How a value looks when printed or interpolated."""
    if isinstance(v, str):
        return v
    return to_repr(v)


def to_repr(v, depth: int = 0) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return fmt_num(float(v))
    if isinstance(v, str):
        return quote(v)
    if isinstance(v, list):
        if depth > 4:
            return "[...]"
        return "[" + ", ".join(to_repr(x, depth + 1) for x in v) + "]"
    if isinstance(v, dict):
        if depth > 4:
            return "{...}"
        return "{" + ", ".join(f"{k}: {to_repr(x, depth + 1)}" for k, x in v.items()) + "}"
    if isinstance(v, OmniRange):
        return repr(v)
    if isinstance(v, OmniFunction):
        return f"<fn {v.name}>"
    if isinstance(v, NativeFunction):
        return f"<fn {v.name}>"
    if isinstance(v, OmniClass):
        return f"<class {v.name}>"
    if isinstance(v, OmniObject):
        to_s = v.klass.lookup("str")
        if to_s is not None and depth == 0:
            return str(_call_method(v, "str", []))
        inner = ", ".join(f"{k}: {to_repr(x, depth + 1)}" for k, x in v.fields.items())
        return f"{v.klass.name}({inner})"
    if isinstance(v, HostObject):
        if v.display is not None:
            return v.display(v)
        inner = ", ".join(f"{k}: {to_repr(x, depth + 1)}" for k, x in v.fields.items())
        return f"{v.type_name}({inner})" if inner else f"<{v.type_name}>"
    return str(v)


def quote(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def compare(a, b) -> int:
    """Total ordering used by `<`, `sort` and friends."""
    if isinstance(a, bool) or isinstance(b, bool):
        a, b = float(a is True), float(b is True)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return -1 if a < b else (1 if a > b else 0)
    if isinstance(a, str) and isinstance(b, str):
        return -1 if a < b else (1 if a > b else 0)
    if isinstance(a, list) and isinstance(b, list):
        for x, y in zip(a, b):
            c = compare(x, y)
            if c:
                return c
        return -1 if len(a) < len(b) else (1 if len(a) > len(b) else 0)
    rank = {"null": 0, "bool": 1, "num": 2, "str": 3, "list": 4, "map": 5}
    ra, rb = rank.get(type_name(a), 9), rank.get(type_name(b), 9)
    if ra != rb:
        return -1 if ra < rb else 1
    return 0


# ------------------------------------------------------------------- binding
def collect_signature(fn: Callable, name: str | None = None, doc: str | None = None,
                      takes_interp: bool = True):
    """Turn a Python function into an OmniScript parameter list."""
    params = []
    sig = inspect.signature(fn)
    first = takes_interp
    seen_rest = False
    for pname, p in sig.parameters.items():
        if first:            # the interpreter handle is not an OmniScript param
            first = False
            continue
        if p.kind == inspect.Parameter.VAR_POSITIONAL:
            seen_rest = True
            params.append({"name": pname, "default": None, "rest": True,
                           "kwrest": False, "kw_only": False})
        elif p.kind == inspect.Parameter.VAR_KEYWORD:
            params.append({"name": pname, "default": None, "rest": False,
                           "kwrest": True, "kw_only": False})
        else:
            has_default = p.default is not inspect.Parameter.empty
            params.append({"name": pname,
                           "default": None if not has_default else p.default,
                           "rest": False, "kwrest": False,
                           # anything after *rest can only be passed by keyword
                           "kw_only": seen_rest or p.kind is inspect.Parameter.KEYWORD_ONLY,
                           "has_default": has_default})
    return NativeFunction(name or fn.__name__, fn, doc or (fn.__doc__ or "").strip(),
                          params, takes_interp=takes_interp)
