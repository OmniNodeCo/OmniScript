"""OmniScript core built-ins: output, types, text, lists, maps and math.

Nothing here needs importing -- every name in BUILTINS is already in scope in
every OmniScript program.
"""

from __future__ import annotations

import math
import random
import time
import unicodedata
from datetime import datetime, timezone

from ..errors import OmniRuntimeError, OmniTypeError
from ..values import (HostObject, NativeFunction, OmniClass, OmniFunction, OmniObject,
                      OmniRange, collect_signature, fmt_num, omni_eq, to_repr, to_string,
                      truthy, type_name)

BUILTINS: list[NativeFunction] = []


def omni(name: str | None = None, alias: tuple[str, ...] = ()):
    """Register a Python function as an OmniScript built-in."""
    def deco(fn):
        primary = collect_signature(fn, name or fn.__name__, fn.__doc__)
        BUILTINS.append(primary)
        for extra in alias:
            BUILTINS.append(NativeFunction(extra, fn, primary.doc, list(primary.params)))
        return fn
    return deco


# --------------------------------------------------------------------- coerce
def as_num(v, what="value"):
    if isinstance(v, bool):
        raise OmniTypeError(f"{what} must be a number, got a bool")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            raise OmniTypeError(f"{what} must be a number, got `{v}`",
                                hint="wrap it in `num()` to convert text to a number")
    raise OmniTypeError(f"{what} must be a number, got {type_name(v)}")


def as_int(v, what="value"):
    n = as_num(v, what)
    if not n.is_integer():
        raise OmniTypeError(f"{what} must be a whole number, got {fmt_num(n)}")
    return int(n)


def as_str(v, what="value"):
    if not isinstance(v, str):
        raise OmniTypeError(f"{what} must be text, got {type_name(v)}")
    return v


def as_list(v, what="value"):
    if isinstance(v, list):
        return v
    if isinstance(v, OmniRange):
        return v.values()
    if isinstance(v, str):
        return list(v)
    if isinstance(v, dict):
        return list(v.keys())
    raise OmniTypeError(f"{what} must be a list, got {type_name(v)}")


def is_callable(v):
    return isinstance(v, (OmniFunction, NativeFunction)) or hasattr(v, "fn")


# ----------------------------------------------------------------------- I/O
@omni("print")
def _print(interp, *args, sep=" ", end="\n"):
    """print(...values, sep: " ", end: "\\n") -- write values to the output."""
    interp.print(sep.join(to_string(a) for a in args) + end)
    return None


@omni("show")
def _show(interp, value, end="\n"):
    """show(value) -- print a value in its literal form (strings keep quotes)."""
    interp.print(to_repr(value) + end)
    return None


@omni("input", alias=("ask", "read_line"))
def _input(interp, prompt=""):
    """input(prompt: "") -- read one line from the keyboard."""
    if prompt:
        interp.print(to_string(prompt))
    sys_stdin = interp.stdin
    line = sys_stdin.readline()
    if line == "":
        return None
    return line.rstrip("\n")


@omni("exit")
def _exit(interp, code=0):
    """exit(code: 0) -- stop the program."""
    interp.exit_code = as_int(code, "exit code")
    raise SystemExit(interp.exit_code)


@omni("error")
def _error(interp, message, kind="error"):
    """error(message) -- raise an error you can catch with `try`/`catch`."""
    from ..errors import OmniThrow
    raise OmniThrow(HostObject("Error", fields={"message": to_string(message),
                                                "kind": to_string(kind)}))


@omni("assert")
def _assert(interp, condition, message=None):
    """assert(condition, message?) -- stop if the condition is false."""
    if not truthy(condition):
        raise OmniRuntimeError(to_string(message) if message is not None
                               else "assertion failed")
    return True


@omni("assert_eq")
def _assert_eq(interp, actual, expected, message=None):
    """assert_eq(actual, expected) -- stop the test if they differ."""
    if not omni_eq(actual, expected):
        detail = to_string(message) if message is not None else \
            f"expected {to_repr(expected)} but got {to_repr(actual)}"
        raise OmniRuntimeError(detail)
    return True


@omni("assert_true")
def _assert_true(interp, condition, message=None):
    """assert_true(value) -- stop the test if this is not truthy."""
    if not truthy(condition):
        raise OmniRuntimeError(to_string(message) if message is not None
                               else f"expected truthy, got {to_repr(condition)}")
    return True


@omni("assert_throws")
def _assert_throws(interp, fn, message=None):
    """assert_throws(() -> ...) -- the function must raise."""
    try:
        interp.call_loose(fn, [], {}, node=None)
    except Exception:
        return True
    raise OmniRuntimeError(to_string(message) if message is not None
                           else "expected this to throw, but it did not")


@omni("help")
def _help(interp, name=None):
    """help(name?) -- list every built-in, or explain one of them."""
    table = interp.builtin_index
    if name is None:
        names = sorted(table)
        lines = []
        for i in range(0, len(names), 5):
            lines.append("  ".join(n.ljust(14) for n in names[i:i + 5]))
        interp.out("\n".join(lines))
        interp.out(f"\n{len(names)} built-ins. Try `help(\"name\")` for details.")
        return None
    key = to_string(name)
    if key not in table:
        from ..errors import suggest
        raise OmniRuntimeError(f"there is no built-in called `{key}`",
                               hint=suggest(key, table.keys()))
    fn = table[key]
    from ..interp import sig_of
    interp.out(f"{key}{sig_of(fn.params)}")
    if fn.doc:
        interp.out(f"  {fn.doc}")
    return None


# --------------------------------------------------------------------- types
@omni("type")
def _type(interp, value):
    """type(value) -- the name of a value's type."""
    return type_name(value)


@omni("str", alias=("string", "to_str"))
def _str(interp, value):
    """str(value) -- turn anything into text."""
    return to_string(value)


@omni("repr")
def _repr(interp, value):
    """repr(value) -- the literal source form of a value."""
    return to_repr(value)


@omni("num", alias=("number", "to_num", "float"))
def _num(interp, value, default=None):
    """num(text) -- turn text into a number."""
    try:
        return as_num(value)
    except OmniTypeError:
        if default is not None:
            return as_num(default, "default")
        raise


@omni("int", alias=("to_int", "whole"))
def _int(interp, value):
    """int(value) -- round towards zero and return a whole number."""
    return float(int(as_num(value)))


@omni("bool", alias=("to_bool",))
def _bool(interp, value):
    """bool(value) -- is this value truthy?"""
    return truthy(value)


@omni("is_type")
def _is_type(interp, value, name):
    """is_type(value, "num") -- check a type by name."""
    return interp.check_type(value, to_string(name))


# ------------------------------------------------------------------ sequences
@omni("len", alias=("count", "size"))
def _len(interp, value):
    """len(value) -- how many items a list, map or piece of text holds."""
    if isinstance(value, (list, str, dict)):
        return float(len(value))
    if isinstance(value, OmniRange):
        return float(len(value.values()))
    if isinstance(value, (OmniObject, HostObject)):
        m = value.klass.lookup("len") if isinstance(value, OmniObject) \
            else value.methods.get("len")
        if m is not None:
            return interp.call_value(m, [], {}, node=None,
                                     self_obj=value if isinstance(value, OmniObject) else None)
    raise OmniTypeError(f"`{type_name(value)}` has no length")


@omni("range")
def _range(interp, start, stop=None, step=1.0):
    """range(n) or range(a, b) or range(a, b, step) -- a sequence of numbers."""
    if stop is None:
        return OmniRange(0.0, as_num(start, "range end"), as_num(step, "step"), False)
    return OmniRange(as_num(start, "range start"), as_num(stop, "range end"),
                     as_num(step, "step"), False)


@omni("list", alias=("to_list",))
def _list(interp, value=None):
    """list(value) -- turn anything iterable into a list."""
    if value is None:
        return []
    return list(interp.iterate(value))


@omni("enumerate", alias=("indexed",))
def _enumerate(interp, value, start=0.0):
    """enumerate(items) -- [[index, item], ...] so you can loop with positions."""
    s = as_int(start, "start")
    return [[float(s + i), v] for i, v in enumerate(interp.iterate(value))]


@omni("sorted", alias=("sort",))
def _sorted(interp, value, by=None, desc=False):
    """sorted(items, by: fn|key, desc: false) -- a new, ordered list."""
    items = list(interp.iterate(value))
    key = None
    from .methods import _capacity, _sort_items
    if by is not None and not isinstance(by, str) and _capacity(by) == 2:
        import functools

        def compare(a, b):
            r = interp.call_loose(by, [a, b], {}, node=None)
            if isinstance(r, bool):
                return -1 if r else 1
            return int(r)

        items.sort(key=functools.cmp_to_key(compare))
    elif by is not None:
        if isinstance(by, str):
            key = lambda x: _sort_key(x.get(by) if isinstance(x, dict) else x)  # noqa: E731
        elif is_callable(by):
            key = lambda x: _sort_key(interp.call_loose(by, [x], {}, node=None))  # noqa: E731
        else:
            raise OmniTypeError("`by` must be a function or a key name")
        items.sort(key=key)
    else:
        items.sort(key=_sort_key)
    if truthy(desc):
        items.reverse()
    return items


def _sort_key(v):
    rank = {"null": 0, "bool": 1, "num": 2, "str": 3, "list": 4, "map": 5}
    t = type_name(v)
    if t == "num":
        return (2, float(v), "")
    if t == "str":
        return (3, 0.0, v)
    if t == "bool":
        return (1, float(v), "")
    if t == "null":
        return (0, 0.0, "")
    return (rank.get(t, 9), 0.0, to_repr(v))


@omni("reverse")
def _reverse(interp, value):
    """reverse(items) -- the same list, backwards."""
    if isinstance(value, str):
        return value[::-1]
    return list(reversed(interp.iterate(value)))


@omni("unique", alias=("distinct",))
def _unique(interp, value):
    """unique(items) -- drop repeats, keeping the first of each."""
    seen, out = set(), []
    for v in interp.iterate(value):
        k = to_repr(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


@omni("flatten", alias=("flat",))
def _flatten(interp, value, depth=1.0):
    """flatten(items, depth: 1) -- unwrap nested lists; depth: -1 unwraps all of them."""
    d = as_int(depth, "depth")
    items = list(interp.iterate(value))
    passes = 0
    while d < 0 or passes < d:
        out = []
        changed = False
        for v in items:
            if isinstance(v, list):
                out.extend(v)
                changed = True
            else:
                out.append(v)
        items = out
        passes += 1
        if not changed:
            break
    return items


@omni("chunk")
def _chunk(interp, value, size):
    """chunk(items, n) -- split a list into groups of n."""
    n = as_int(size, "size")
    if n <= 0:
        raise OmniRuntimeError("chunk size must be at least 1")
    items = list(interp.iterate(value))
    return [items[i:i + n] for i in range(0, len(items), n)]


@omni("zip")
def _zip(interp, a, b=None, *rest):
    """zip(listA, listB) -- pair items up: [[a1,b1], [a2,b2], ...]."""
    lists = [list(interp.iterate(a))]
    if b is not None:
        lists.append(list(interp.iterate(b)))
    lists += [list(interp.iterate(r)) for r in rest]
    return [list(t) for t in zip(*lists)]


@omni("first")
def _first(interp, value, default=None):
    """first(items, default?) -- the opening item."""
    items = interp.iterate(value)
    return items[0] if items else default


@omni("last")
def _last(interp, value, default=None):
    """last(items, default?) -- the closing item."""
    items = interp.iterate(value)
    return items[-1] if items else default


@omni("take")
def _take(interp, value, n):
    """take(items, n) -- the first n items."""
    return list(interp.iterate(value))[:as_int(n, "n")]


@omni("drop")
def _drop(interp, value, n):
    """drop(items, n) -- everything after the first n items."""
    return list(interp.iterate(value))[as_int(n, "n"):]


@omni("push")
def _push(interp, target, *items):
    """push(list, value) -- append to a list in place and return it."""
    if isinstance(target, list):
        target.extend(items)
        return target
    if isinstance(target, dict):
        for it in items:
            if not isinstance(it, dict):
                raise OmniTypeError("merging into a map needs map arguments")
            target.update(it)
        return target
    raise OmniTypeError(f"cannot push into {type_name(target)}")


@omni("pop")
def _pop(interp, target, index=-1.0):
    """pop(list) -- remove and return the last item."""
    if not isinstance(target, list):
        raise OmniTypeError(f"cannot pop from {type_name(target)}")
    if not target:
        return None
    return target.pop(as_int(index, "index"))


@omni("insert")
def _insert(interp, target, index, value):
    """insert(list, index, value) -- put a value at a position."""
    if not isinstance(target, list):
        raise OmniTypeError(f"cannot insert into {type_name(target)}")
    target.insert(as_int(index, "index"), value)
    return target


@omni("remove")
def _remove(interp, target, key):
    """remove(list, index) or remove(map, key) -- delete in place."""
    if isinstance(target, list):
        i = as_int(key, "index")
        if i < 0:
            i += len(target)
        if 0 <= i < len(target):
            return target.pop(i)
        return None
    if isinstance(target, dict):
        from ..interp import _hashable
        return target.pop(_hashable(key), None)
    raise OmniTypeError(f"cannot remove from {type_name(target)}")


# --------------------------------------------------------------------- maps
@omni("map_new", alias=("dict",))
def _map_new(interp, *pairs):
    """map_new([k, v], ...) -- build a map from key/value pairs."""
    out = {}
    for p in pairs:
        items = interp.iterate(p)
        if len(items) != 2:
            raise OmniRuntimeError("each pair needs exactly two items")
        from ..interp import _hashable
        out[_hashable(items[0])] = items[1]
    return out


@omni("keys")
def _keys(interp, value):
    """keys(map) -- every key."""
    _need_map(value, "keys")
    return list(value.keys())


@omni("values")
def _values(interp, value):
    """values(map) -- every value."""
    _need_map(value, "values")
    return list(value.values())


@omni("entries", alias=("items", "pairs"))
def _entries(interp, value):
    """entries(map) -- [[key, value], ...]."""
    if isinstance(value, dict):
        return [[k, v] for k, v in value.items()]
    return [[float(i), v] for i, v in enumerate(interp.iterate(value))]


@omni("has", alias=("contains",))
def _has(interp, container, key):
    """has(map, key) or has(list, value) or has(text, needle)."""
    if isinstance(container, dict):
        from ..interp import _hashable
        return _hashable(key) in container
    if isinstance(container, str):
        return to_string(key) in container
    if isinstance(container, list):
        return any(omni_eq(v, key) for v in container)
    raise OmniTypeError(f"cannot search inside {type_name(container)}")


@omni("get")
def _get(interp, container, key, default=None):
    """get(map, key, default?) -- read a key without risking an error."""
    if isinstance(container, dict):
        from ..interp import _hashable
        return container.get(_hashable(key), default)
    if isinstance(container, list):
        i = as_int(key, "index")
        return container[i] if -len(container) <= i < len(container) else default
    return default


@omni("merge")
def _merge(interp, *maps):
    """merge(a, b, ...) -- combine maps into a brand new one."""
    out = {}
    for m in maps:
        if not isinstance(m, dict):
            raise OmniTypeError(f"merge needs maps, got {type_name(m)}")
        out.update(m)
    return out


@omni("pick")
def _pick(interp, source, *names):
    """pick(map, "a", "b") -- a smaller map with only those keys."""
    if not isinstance(source, dict):
        raise OmniTypeError(f"pick needs a map, got {type_name(source)}")
    return {to_string(n): source[to_string(n)] for n in names if to_string(n) in source}


@omni("omit")
def _omit(interp, source, *names):
    """omit(map, "a") -- a copy without those keys."""
    if not isinstance(source, dict):
        raise OmniTypeError(f"omit needs a map, got {type_name(source)}")
    skip = {to_string(n) for n in names}
    return {k: v for k, v in source.items() if k not in skip}


@omni("deep_copy", alias=("clone",))
def _deep_copy(interp, value):
    """deep_copy(value) -- an independent copy, nested lists and maps included."""
    if isinstance(value, list):
        return [_deep_copy(interp, v) for v in value]
    if isinstance(value, dict):
        return {k: _deep_copy(interp, v) for k, v in value.items()}
    if isinstance(value, OmniObject):
        return OmniObject(value.klass, {k: _deep_copy(interp, v)
                                        for k, v in value.fields.items()})
    return value


def _need_map(value, who):
    if not isinstance(value, dict):
        raise OmniTypeError(f"`{who}` needs a map, got {type_name(value)}")


# ----------------------------------------------------------- higher order fns
def _apply(interp, fn, args):
    if not is_callable(fn) and not isinstance(fn, (OmniObject, HostObject)):
        raise OmniTypeError(f"expected a function, got {to_repr(fn)}",
                            hint="lambdas look like `(x) -> x * 2`")
    return interp.call_loose(fn, args, {}, node=None)


@omni("map_each", alias=("map_all", "transform", "map"))
def _map_each(interp, items, fn):
    """map_each(items, (x) -> ...) -- apply a function to every item."""
    return [_apply(interp, fn, [v, float(i)]) for i, v in enumerate(interp.iterate(items))]


@omni("filter", alias=("select", "keep"))
def _filter(interp, items, fn=None):
    """filter(items, (x) -> ...) -- keep only what passes."""
    out = []
    for i, v in enumerate(interp.iterate(items)):
        keep = truthy(v) if fn is None else truthy(_apply(interp, fn, [v, float(i)]))
        if keep:
            out.append(v)
    return out


@omni("reject")
def _reject(interp, items, fn):
    """reject(items, (x) -> ...) -- the opposite of filter."""
    return [v for i, v in enumerate(interp.iterate(items))
            if not truthy(_apply(interp, fn, [v, float(i)]))]


@omni("reduce", alias=("fold",))
def _reduce(interp, items, fn, initial=None):
    """reduce(items, (acc, x) -> ..., initial) -- fold a list into one value."""
    it = iter(interp.iterate(items))
    acc = initial
    if acc is None:
        try:
            acc = next(it)
        except StopIteration:
            raise OmniRuntimeError("reduce of an empty list needs an `initial` value")
    for i, v in enumerate(it):
        acc = _apply(interp, fn, [acc, v, float(i)])
    return acc


@omni("each", alias=("for_each", "walk"))
def _each(interp, items, fn):
    """each(items, (x) -> ...) -- run something for every item, return nothing."""
    for i, v in enumerate(interp.iterate(items)):
        _apply(interp, fn, [v, float(i)])
    return None


@omni("find", alias=("first_where",))
def _find(interp, items, fn):
    """find(items, (x) -> ...) -- the first item that passes, else null."""
    for i, v in enumerate(interp.iterate(items)):
        if truthy(_apply(interp, fn, [v, float(i)])):
            return v
    return None


@omni("find_index")
def _find_index(interp, items, fn):
    """find_index(items, (x) -> ...) -- position of the first match, else -1."""
    for i, v in enumerate(interp.iterate(items)):
        if truthy(_apply(interp, fn, [v, float(i)])):
            return float(i)
    return -1.0


@omni("index_of")
def _index_of(interp, items, value):
    """index_of(list, value) -- where a value sits, or -1."""
    for i, v in enumerate(interp.iterate(items)):
        if omni_eq(v, value):
            return float(i)
    return -1.0


@omni("some", alias=("any",))
def _some(interp, items, fn=None):
    """some(items, (x) -> ...) -- does at least one pass?"""
    for i, v in enumerate(interp.iterate(items)):
        if truthy(v) if fn is None else truthy(_apply(interp, fn, [v, float(i)])):
            return True
    return False


@omni("every", alias=("all",))
def _every(interp, items, fn=None):
    """every(items, (x) -> ...) -- do all of them pass?"""
    for i, v in enumerate(interp.iterate(items)):
        if not (truthy(v) if fn is None else truthy(_apply(interp, fn, [v, float(i)]))):
            return False
    return True


@omni("flat_map")
def _flat_map(interp, items, fn):
    """flat_map(items, (x) -> [...]) -- map then flatten one level."""
    out = []
    for i, v in enumerate(interp.iterate(items)):
        r = _apply(interp, fn, [v, float(i)])
        out.extend(interp.iterate(r) if isinstance(r, (list, OmniRange)) else [r])
    return out


@omni("group_by")
def _group_by(interp, items, key):
    """group_by(rows, "field") or group_by(rows, fn) -- bucket items into a map."""
    out: dict[str, list] = {}
    for i, v in enumerate(interp.iterate(items)):
        if isinstance(key, str):
            if not isinstance(v, dict):
                raise OmniTypeError("grouping by a key name needs a list of maps")
            k = to_string(v.get(key))
        else:
            k = to_string(_apply(interp, key, [v, float(i)]))
        out.setdefault(k, []).append(v)
    return out


@omni("count_by")
def _count_by(interp, items, key):
    """count_by(rows, "field") -- how many items fall in each bucket."""
    groups = _group_by(interp, items, key)
    return {k: float(len(v)) for k, v in groups.items()}


@omni("sum")
def _sum(interp, items, by=None, start=0.0):
    """sum(numbers) or sum(rows, "field") -- add everything up."""
    total = as_num(start, "start")
    for v in interp.iterate(items):
        total += _pick_number(v, by, interp)
    return total


@omni("product")
def _product(interp, items, by=None):
    """product(numbers) -- multiply everything together."""
    total = 1.0
    for v in interp.iterate(items):
        total *= _pick_number(v, by, interp)
    return total


@omni("avg", alias=("mean",))
def _avg(interp, items, by=None):
    """avg(numbers) -- the arithmetic mean."""
    vals = [_pick_number(v, by, interp) for v in interp.iterate(items)]
    if not vals:
        raise OmniRuntimeError("cannot average an empty list")
    return sum(vals) / len(vals)


@omni("median")
def _median(interp, items, by=None):
    """median(numbers) -- the middle value."""
    vals = sorted(_pick_number(v, by, interp) for v in interp.iterate(items))
    if not vals:
        raise OmniRuntimeError("cannot take the median of an empty list")
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


@omni("min")
def _min(interp, *values, by=None):
    """min(numbers) or min(a, b, c...) -- the smallest."""
    vals = _collect_numbers(interp, values, by)
    if not vals:
        raise OmniRuntimeError("min of an empty list")
    return min(vals)


@omni("max")
def _max(interp, *values, by=None):
    """max(numbers) or max(a, b, c...) -- the largest."""
    vals = _collect_numbers(interp, values, by)
    if not vals:
        raise OmniRuntimeError("max of an empty list")
    return max(vals)


def _collect_numbers(interp, items, by):
    # `max(1, 7, 3)` passes several numbers; `max([1, 7, 3])` passes one list
    if isinstance(items, tuple) and len(items) > 1:
        items = list(items)
    elif isinstance(items, tuple) and len(items) == 1:
        items = items[0]
    if isinstance(items, (list, dict, str, OmniRange)) and by is None:
        try:
            return [_pick_number(v, by, interp) for v in interp.iterate(items)]
        except OmniTypeError:
            return [as_num(items, "value")]
    if isinstance(items, (int, float)) and not isinstance(items, bool):
        return [float(items)]
    return [_pick_number(v, by, interp) for v in interp.iterate(items)]


def _pick_number(v, by, interp):
    if by is not None:
        if isinstance(by, str):
            if not isinstance(v, dict):
                raise OmniTypeError(f"cannot read `.{by}` from {type_name(v)}")
            v = v.get(by)
        else:
            v = _apply(interp, by, [v])
    return as_num(v, "list item")


# ------------------------------------------------------------------- strings
@omni("join")
def _join(interp, items, sep=""):
    """join(list, ", ") -- glue text together."""
    return to_string(sep).join(to_string(v) for v in interp.iterate(items))


@omni("split")
def _split(interp, text, sep=None, limit=-1.0):
    """split(text, ",") -- cut text into a list."""
    s = to_string(text)
    n = as_int(limit, "limit")
    if sep is None:
        return s.split() if n < 0 else s.split(None, n)
    d = to_string(sep)
    return s.split(d) if n < 0 else s.split(d, n)


@omni("trim", alias=("strip",))
def _trim(interp, text, chars=None):
    """trim(text) -- cut whitespace off both ends."""
    s = to_string(text)
    return s.strip(to_string(chars)) if chars is not None else s.strip()


@omni("upper", alias=("to_upper", "upcase"))
def _upper(interp, text):
    """upper(text) -- SHOUTING."""
    return to_string(text).upper()


@omni("lower", alias=("to_lower", "downcase"))
def _lower(interp, text):
    """lower(text) -- whispering."""
    return to_string(text).lower()


@omni("title")
def _title(interp, text):
    """title(text) -- Every Word Capitalised."""
    return to_string(text).title()


@omni("replace")
def _replace(interp, text, old, new, count=-1.0):
    """replace(text, "old", "new") -- swap every occurrence."""
    n = as_int(count, "count")
    return to_string(text).replace(to_string(old), to_string(new)) if n < 0 \
        else to_string(text).replace(to_string(old), to_string(new), n)


@omni("repeat")
def _repeat(interp, text, times):
    """repeat("ab", 3) -- "ababab"."""
    return to_string(text) * as_int(times, "times")


@omni("starts_with")
def _starts_with(interp, text, prefix):
    """starts_with(text, "pre") -- does it open with this?"""
    return to_string(text).startswith(to_string(prefix))


@omni("ends_with")
def _ends_with(interp, text, suffix):
    """ends_with(text, "ing") -- does it close with this?"""
    return to_string(text).endswith(to_string(suffix))


@omni("pad_start", alias=("lpad",))
def _pad_start(interp, text, width, fill=" "):
    """pad_start(text, 10, "0") -- right-align inside a fixed width."""
    return to_string(text).rjust(as_int(width, "width"), to_string(fill)[:1] or " ")


@omni("pad_end", alias=("rpad",))
def _pad_end(interp, text, width, fill=" "):
    """pad_end(text, 10) -- left-align inside a fixed width."""
    return to_string(text).ljust(as_int(width, "width"), to_string(fill)[:1] or " ")


@omni("center")
def _center(interp, text, width, fill=" "):
    """center(text, 20) -- middle-align inside a fixed width."""
    return to_string(text).center(as_int(width, "width"), to_string(fill)[:1] or " ")


@omni("chars")
def _chars(interp, text):
    """chars(text) -- a list of single characters."""
    return list(to_string(text))


@omni("words")
def _words(interp, text):
    """words(text) -- split on any whitespace."""
    return to_string(text).split()


@omni("lines_of", alias=("lines",))
def _lines_of(interp, text):
    """lines_of(text) -- split into lines."""
    return to_string(text).splitlines()


@omni("format")
def _format(interp, template, *args, **named):
    """format("Hi {}!", name) -- fill {} slots in order, or {name} by key."""
    out = to_string(template)
    for a in args:
        out = out.replace("{}", to_string(a), 1)
    for k, v in named.items():
        out = out.replace("{" + k + "}", to_string(v))
    return out


@omni("round_to")
def _round_to(interp, value, places=0.0):
    """round_to(3.14159, 2) -- 3.14."""
    p = as_int(places, "places")
    return round(as_num(value, "value"), p)


@omni("ord")
def _ord(interp, ch):
    """ord("A") -- 65, the code point of a character."""
    s = to_string(ch)
    if len(s) != 1:
        raise OmniRuntimeError("ord() needs exactly one character")
    return float(ord(s))


@omni("chr")
def _chr(interp, code):
    """chr(65) -- "A", the character for a code point."""
    return chr(as_int(code, "code"))


@omni("slug")
def _slug(interp, text, sep="-"):
    """slug("Hello World!") -- "hello-world", safe for filenames and URLs."""
    import re
    s = unicodedata.normalize("NFKD", to_string(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", to_string(sep), s.lower()).strip(to_string(sep))
    return s


# ---------------------------------------------------------------------- math
@omni("abs")
def _abs(interp, value):
    """abs(-5) -- 5."""
    return abs(as_num(value, "value"))


@omni("round")
def _round(interp, value):
    """round(2.5) -- the nearest whole number."""
    return float(round(as_num(value, "value")))


@omni("floor")
def _floor(interp, value):
    """floor(2.9) -- 2."""
    return float(math.floor(as_num(value, "value")))


@omni("ceil", alias=("ceiling",))
def _ceil(interp, value):
    """ceil(2.1) -- 3."""
    return float(math.ceil(as_num(value, "value")))


@omni("sqrt")
def _sqrt(interp, value):
    """sqrt(9) -- 3."""
    v = as_num(value, "value")
    if v < 0:
        raise OmniRuntimeError("cannot take the square root of a negative number")
    return math.sqrt(v)


@omni("pow")
def _pow(interp, base, exponent):
    """pow(2, 10) -- 1024 (same as `2 ** 10`)."""
    return math.pow(as_num(base, "base"), as_num(exponent, "exponent"))


@omni("exp")
def _exp(interp, value):
    """exp(x) -- e raised to x."""
    return math.exp(as_num(value, "value"))


@omni("log")
def _log(interp, value, base=None):
    """log(x) or log(x, base) -- natural logarithm by default."""
    v = as_num(value, "value")
    if v <= 0:
        raise OmniRuntimeError("log() needs a positive number")
    return math.log(v) if base is None else math.log(v, as_num(base, "base"))


@omni("log10")
def _log10(interp, value):
    """log10(1000) -- 3."""
    return math.log10(as_num(value, "value"))


@omni("log2")
def _log2(interp, value):
    """log2(8) -- 3."""
    return math.log2(as_num(value, "value"))


def _register_trig():
    table = [("sin", math.sin), ("cos", math.cos), ("tan", math.tan),
             ("asin", math.asin), ("acos", math.acos), ("atan", math.atan),
             ("sinh", math.sinh), ("cosh", math.cosh), ("tanh", math.tanh)]
    for nm, f in table:
        BUILTINS.append(collect_signature(
            lambda interp, value, _f=f: _f(as_num(value, "value")),
            nm, f"{nm}(x) -- the {nm} trig function, in radians."))


_register_trig()


@omni("atan2")
def _atan2(interp, y, x):
    """atan2(y, x) -- the angle to a point, in radians."""
    return math.atan2(as_num(y, "y"), as_num(x, "x"))


@omni("hypot")
def _hypot(interp, a, b):
    """hypot(3, 4) -- 5, the straight-line distance."""
    return math.hypot(as_num(a, "a"), as_num(b, "b"))


@omni("degrees")
def _degrees(interp, radians):
    """degrees(x) -- radians to degrees."""
    return math.degrees(as_num(radians, "radians"))


@omni("radians")
def _radians(interp, degrees):
    """radians(x) -- degrees to radians."""
    return math.radians(as_num(degrees, "degrees"))


@omni("clamp")
def _clamp(interp, value, lo, hi):
    """clamp(15, 0, 10) -- 10, forced between two bounds."""
    return min(max(as_num(value, "value"), as_num(lo, "low")), as_num(hi, "high"))


@omni("lerp")
def _lerp(interp, a, b, t):
    """lerp(0, 100, 0.25) -- 25, a point between two numbers."""
    t = as_num(t, "t")
    return as_num(a, "a") + (as_num(b, "b") - as_num(a, "a")) * t


@omni("sign")
def _sign(interp, value):
    """sign(-9) -- -1 (0 or 1 otherwise)."""
    v = as_num(value, "value")
    return float((v > 0) - (v < 0))


@omni("gcd")
def _gcd(interp, a, b):
    """gcd(12, 18) -- 6."""
    return float(math.gcd(as_int(a, "a"), as_int(b, "b")))


@omni("lcm")
def _lcm(interp, a, b):
    """lcm(4, 6) -- 12."""
    return float(math.lcm(as_int(a, "a"), as_int(b, "b")))


@omni("is_even")
def _is_even(interp, value):
    """is_even(4) -- true."""
    return as_int(value, "value") % 2 == 0


@omni("is_odd")
def _is_odd(interp, value):
    """is_odd(4) -- false."""
    return as_int(value, "value") % 2 != 0


# -------------------------------------------------------------------- random
@omni("rand", alias=("random",))
def _rand(interp, lo=0.0, hi=1.0):
    """rand() or rand(lo, hi) -- a decimal between the bounds."""
    return random.uniform(as_num(lo, "low"), as_num(hi, "high"))


@omni("rand_int", alias=("randint",))
def _rand_int(interp, lo, hi=None):
    """rand_int(6) -- a die roll; rand_int(lo, hi) -- inclusive bounds."""
    if hi is None:
        return float(random.randint(0, as_int(lo, "high")))
    return float(random.randint(as_int(lo, "low"), as_int(hi, "high")))


@omni("choice")
def _choice(interp, items):
    """choice(list) -- pick one at random."""
    pool = interp.iterate(items)
    if not pool:
        raise OmniRuntimeError("cannot choose from an empty list")
    return random.choice(pool)


@omni("sample")
def _sample(interp, items, n):
    """sample(list, 3) -- three distinct items at random."""
    pool = interp.iterate(items)
    return random.sample(pool, as_int(n, "n"))


@omni("shuffle")
def _shuffle(interp, items):
    """shuffle(list) -- a new list in random order."""
    pool = list(interp.iterate(items))
    random.shuffle(pool)
    return pool


@omni("seed")
def _seed(interp, value):
    """seed(42) -- make random numbers repeatable."""
    random.seed(as_int(value, "seed"))
    return None


# ---------------------------------------------------------------------- time
@omni("now")
def _now(interp):
    """now() -- seconds since 1 Jan 1970, with fractions."""
    return time.time()


@omni("today")
def _today(interp, fmt="%Y-%m-%d"):
    """today() -- the current date as text."""
    return datetime.now().strftime(to_string(fmt))


@omni("timestamp")
def _timestamp(interp, fmt="%Y-%m-%d %H:%M:%S", when=None):
    """timestamp() -- the current date and time as text."""
    if when is None:
        return datetime.now().strftime(to_string(fmt))
    return datetime.fromtimestamp(as_num(when, "when")).strftime(to_string(fmt))


@omni("sleep", alias=("wait",))
def _sleep(interp, seconds):
    """sleep(0.5) -- pause."""
    time.sleep(max(0.0, as_num(seconds, "seconds")))
    return None


@omni("stopwatch")
def _stopwatch(interp):
    """stopwatch() -- a timer with .lap() and .stop()."""
    start = time.perf_counter()
    laps = []

    def lap(interp_):
        t = time.perf_counter() - start
        laps.append(t)
        return t

    def stop(interp_):
        return time.perf_counter() - start

    return HostObject("Stopwatch",
                      methods={"lap": collect_signature(lap, "lap",
                                                         "seconds since the stopwatch started",
                                                         takes_interp=False),
                               "stop": collect_signature(stop, "stop",
                                                         "stop and return total seconds",
                                                         takes_interp=False)},
                      fields={"laps": laps},
                      display=lambda o: f"<Stopwatch running for "
                                        f"{time.perf_counter() - o.data:.4f}s>",
                      data=start)


@omni("elapsed", alias=("benchmark",))
def _elapsed(interp, fn, times=1.0):
    """elapsed((_) -> work(), times: 1) -- how long something takes, in seconds."""
    n = max(1, as_int(times, "times"))
    start = time.perf_counter()
    result = None
    for _ in range(n):
        result = _apply(interp, fn, [])
    total = time.perf_counter() - start
    return {"seconds": total, "runs": float(n), "per_run": total / n, "result": result}


# ------------------------------------------------------------ pretty printing
@omni("table")
def _table(interp, rows, columns=None, title=None):
    """table(rows) -- draw a list of maps as an aligned text table."""
    if not isinstance(rows, list):
        rows = interp.iterate(rows)
    if not rows:
        return "(empty table)"
    if isinstance(rows[0], dict):
        cols = [to_string(c) for c in columns] if columns else \
            [k for k in rows[0].keys()]
        body = [[to_string(r.get(c, "")) for c in cols] for r in rows]
    else:
        cols = [f"[{i}]" for i in range(len(rows[0]))] if isinstance(rows[0], list) else ["value"]
        body = [[to_string(x) for x in r] if isinstance(r, list) else [to_string(r)]
                for r in rows]
    widths = [len(c) for c in cols]
    for row in body:
        for i, cell in enumerate(row[:len(widths)]):
            widths[i] = max(widths[i], len(cell))
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = []
    if title:
        out.append(to_string(title).center(len(sep)))
    out.append(sep)
    out.append("| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |")
    out.append(sep)
    for row in body:
        cells = list(row) + [""] * (len(widths) - len(row))
        out.append("| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |")
    out.append(sep)
    text = "\n".join(out)
    interp.out(text)
    return text


@omni("hash")
def _hash(interp, value):
    """hash(value) -- a stable number for any value."""
    import hashlib
    return float(int(hashlib.sha256(to_repr(value).encode()).hexdigest()[:12], 16))


@omni("wait_for")
def _wait_for(interp, fn, timeout=10.0, interval=0.1):
    """wait_for(() -> ready(), timeout: 10) -- poll until something is true."""
    deadline = time.time() + as_num(timeout, "timeout")
    gap = as_num(interval, "interval")
    while time.time() < deadline:
        if truthy(_apply(interp, fn, [])):
            return True
        time.sleep(gap)
    return False
