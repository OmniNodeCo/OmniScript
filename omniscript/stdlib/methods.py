"""Methods you call with a dot: `"abc".upper()`, `[3,1,2].sort()`, `5.times(f)`.

Every method here also exists as a plain function, so both styles work:

    names.sort()          ==     sorted(names)
    "a,b".split(",")      ==     split("a,b", ",")

Method bodies take `self` as an ordinary parameter -- the interpreter fills it
in with the receiver, so `NativeFunction.takes_interp` is False for all of them.
"""

from __future__ import annotations

import json as _json
import math as _math
import random as _random
import re as _re
import textwrap as _textwrap

from ..errors import OmniRuntimeError, OmniTypeError
from ..values import (NativeFunction, OmniRange, collect_signature, fmt_num, omni_eq,
                      to_repr, to_string, truthy, type_name)
from .core import _sort_key, as_int, as_num, is_callable

METHODS: dict[str, dict[str, NativeFunction]] = {}

# Method names such as `sum`, `min`, `set`, `map` and `format` are perfectly
# ordinary words that also happen to be Python built-ins. Registering them here
# would shadow those built-ins inside the method bodies themselves, so every
# name we register is deleted again at the bottom of this module and the
# built-ins fall back into scope.
_REGISTERED: list[str] = []


def _register(type_: str, fn):
    table = METHODS.setdefault(type_, {})
    nf = collect_signature(fn, fn.__name__, (fn.__doc__ or "").strip(), takes_interp=False)
    table[fn.__name__] = nf
    _REGISTERED.append(fn.__name__)
    return fn


def method(type_: str):
    def deco(fn):
        return _register(type_, fn)
    return deco


# Extra spellings, applied after every method is registered.
ALIASES: dict[str, dict[str, str]] = {
    "str": {"size": "len", "has": "contains", "substr": "slice", "to_number": "to_num"},
    "list": {"size": "len", "count": "len", "append": "push", "includes": "contains",
             "has": "contains", "sorted": "sort", "transform": "map", "select": "filter",
             "keep": "filter", "fold": "reduce", "for_each": "each", "any": "some",
             "all": "every", "enumerate": "pairs", "index_by": "to_map", "mean": "avg",
             "flat": "flatten"},
    "map": {"size": "len", "count": "len", "contains": "has", "put": "set",
            "delete": "remove", "items": "entries", "pairs": "entries"},
    "bool": {"not": "not_", "negate": "not_"},
}


def apply_aliases():
    for type_, mapping in ALIASES.items():
        table = METHODS.get(type_)
        if not table:
            continue
        for new, old in mapping.items():
            src = table.get(old)
            if src is not None:
                table[new] = NativeFunction(new, src.fn, src.doc, list(src.params),
                                            takes_interp=False)


# --------------------------------------------------------------- helpers
def _call(fn, args):
    """Call an OmniScript function from inside a host method."""
    from ..interp import Interpreter
    if not (is_callable(fn) or hasattr(fn, "fn")):
        raise OmniTypeError(f"expected a function, got {to_repr(fn)}",
                            hint="lambdas look like `(x) -> x * 2")
    return Interpreter.current().call_loose(fn, list(args), {}, node=None)


def _iterate(v):
    from ..interp import Interpreter
    return Interpreter.current().iterate(v)


def _key(k):
    from ..interp import _hashable
    return _hashable(k)


def _need(v, kind, who):
    if kind is str and not isinstance(v, str):
        raise OmniTypeError(f"`{who}` needs text, got {type_name(v)}")
    if kind is list and not isinstance(v, list):
        raise OmniTypeError(f"`{who}` needs a list, got {type_name(v)}")
    if kind is dict and not isinstance(v, dict):
        raise OmniTypeError(f"`{who}` needs a map, got {type_name(v)}")
    if kind is float:
        return as_num(v, who)
    return v


def _num_of(v, by=None):
    if by is not None:
        if isinstance(by, str):
            if not isinstance(v, dict):
                raise OmniTypeError(f"cannot read `.{by}` from {type_name(v)}")
            v = v.get(by)
        else:
            v = _call(by, [v])
    return as_num(v, "list item")


def _plain(v):
    """Convert OmniScript values into something `json` can serialise."""
    from ..values import HostObject, OmniObject
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() and abs(v) < 1e16 else float(v)
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, OmniRange):
        return [_plain(x) for x in v.values()]
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (OmniObject, HostObject)):
        return {str(k): _plain(x) for k, x in v.fields.items()}
    return to_string(v)


# ============================================================== string ====
@method("str")
def len(self):
    """how many characters"""
    return float(len(_need(self, str, "len")))


@method("str")
def upper(self):
    """UPPERCASE"""
    return _need(self, str, "upper").upper()


@method("str")
def lower(self):
    """lowercase"""
    return _need(self, str, "lower").lower()


@method("str")
def title(self):
    """Title Case"""
    return _need(self, str, "title").title()


@method("str")
def capitalize(self):
    """capitalise the first letter only"""
    s = _need(self, str, "capitalize")
    return s[:1].upper() + s[1:]


@method("str")
def trim(self, chars=None):
    """remove whitespace from both ends"""
    s = _need(self, str, "trim")
    return s.strip(chars) if isinstance(chars, str) else s.strip()


@method("str")
def trim_start(self, chars=None):
    """remove whitespace from the left"""
    s = _need(self, str, "trim_start")
    return s.lstrip(chars) if isinstance(chars, str) else s.lstrip()


@method("str")
def trim_end(self, chars=None):
    """remove whitespace from the right"""
    s = _need(self, str, "trim_end")
    return s.rstrip(chars) if isinstance(chars, str) else s.rstrip()


@method("str")
def split(self, sep=None, limit=-1.0):
    """cut into a list"""
    s = _need(self, str, "split")
    n = as_int(limit, "limit")
    if sep is None:
        return s.split(None, n) if n >= 0 else s.split()
    d = to_string(sep)
    return s.split(d, n) if n >= 0 else s.split(d)


@method("str")
def replace(self, old, new, count=-1.0):
    """swap text"""
    s = _need(self, str, "replace")
    n = as_int(count, "count")
    o, w = to_string(old), to_string(new)
    return s.replace(o, w) if n < 0 else s.replace(o, w, n)


@method("str")
def replace_re(self, pattern, new, count=0.0):
    """swap text matched by a regular expression"""
    s = _need(self, str, "replace_re")
    return _re.sub(to_string(pattern), to_string(new), s, count=as_int(count, "count"))


@method("str")
def contains(self, needle):
    """does this text include the needle?"""
    return to_string(needle) in _need(self, str, "contains")


@method("str")
def starts_with(self, prefix):
    """does it open with this text?"""
    return _need(self, str, "starts_with").startswith(to_string(prefix))


@method("str")
def ends_with(self, suffix):
    """does it close with this text?"""
    return _need(self, str, "ends_with").endswith(to_string(suffix))


@method("str")
def index_of(self, needle, start=0.0):
    """position of the needle, or -1"""
    return float(_need(self, str, "index_of").find(to_string(needle), as_int(start, "start")))


@method("str")
def chars(self):
    """a list of single characters"""
    return list(_need(self, str, "chars"))


@method("str")
def words(self):
    """a list split on whitespace"""
    return _need(self, str, "words").split()


@method("str")
def lines(self):
    """a list of lines"""
    return _need(self, str, "lines").splitlines()


@method("str")
def bytes(self):
    """a list of UTF-8 byte values"""
    return [float(b) for b in _need(self, str, "bytes").encode("utf-8")]


@method("list")
def from_bytes(self, encoding="utf-8"):
    """decode a list of byte values back into text"""
    data = [as_int(b, "byte") for b in _iterate(self)]
    return bytes(data).decode(to_string(encoding), errors="replace")


@method("str")
def repeat(self, times):
    """repeat the text n times"""
    return _need(self, str, "repeat") * as_int(times, "times")


@method("str")
def pad_start(self, width, fill=" "):
    """right-align to a width"""
    return _need(self, str, "pad_start").rjust(as_int(width, "width"),
                                               (to_string(fill) or " ")[:1])


@method("str")
def pad_end(self, width, fill=" "):
    """left-align to a width"""
    return _need(self, str, "pad_end").ljust(as_int(width, "width"),
                                             (to_string(fill) or " ")[:1])


@method("str")
def center(self, width, fill=" "):
    """middle-align to a width"""
    return _need(self, str, "center").center(as_int(width, "width"),
                                             (to_string(fill) or " ")[:1])


@method("str")
def reverse(self):
    """backwards"""
    return _need(self, str, "reverse")[::-1]


@method("str")
def slice(self, start=0.0, end=None, step=None):
    """a substring"""
    s = _need(self, str, "slice")
    return s[as_int(start, "start"):None if end is None else as_int(end, "end"):
             None if step is None else as_int(step, "step")]


@method("str")
def matches(self, pattern):
    """does a regular expression match anywhere?"""
    return _re.search(to_string(pattern), _need(self, str, "matches")) is not None


@method("str")
def match(self, pattern):
    """the first match as a list of groups, else null"""
    m = _re.search(to_string(pattern), _need(self, str, "match"))
    if m is None:
        return None
    return [m.group(0)] + [g if g is not None else "" for g in m.groups()]


@method("str")
def find_all(self, pattern):
    """every regular-expression match"""
    return [m.group(0) for m in _re.finditer(to_string(pattern), _need(self, str, "find_all"))]


@method("str")
def count(self, needle):
    """how many times the needle appears"""
    return float(_need(self, str, "count").count(to_string(needle)))


@method("str")
def to_num(self, default=None):
    """parse this text as a number"""
    try:
        return float(_need(self, str, "to_num").strip())
    except ValueError:
        if default is not None:
            return as_num(default, "default")
        raise OmniTypeError(f"`{self}` is not a number")


@method("str")
def to_json(self):
    """parse this text as JSON"""
    try:
        return _json.loads(_need(self, str, "to_json"))
    except _json.JSONDecodeError as e:
        raise OmniRuntimeError(f"this text is not valid JSON: {e.msg}",
                               hint=f"problem near character {e.pos}")


@method("str")
def is_empty(self):
    """is it empty?"""
    return len(_need(self, str, "is_empty")) == 0


@method("str")
def at(self, index, default=None):
    """one character by position; negative counts from the end"""
    s = _need(self, str, "at")
    i = as_int(index, "index")
    if i < 0:
        i += len(s)
    return s[i] if 0 <= i < len(s) else default


def _to_snake(text: str) -> str:
    s = _re.sub(r"[\-\s]+", "_", text)
    s = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    s = _re.sub(r"(?=[A-Z][a-z])", "_", s)
    return _re.sub(r"_+", "_", s).strip("_").lower()


@method("str")
def snake(self):
    """to snake_case"""
    return _to_snake(_need(self, str, "snake"))


@method("str")
def camel(self):
    """to camelCase"""
    parts = [p for p in _re.split(r"[\-\_\s]+", _need(self, str, "camel")) if p]
    if not parts:
        return ""
    return parts[0].lower() + "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])


@method("str")
def kebab(self):
    """to kebab-case"""
    return _to_snake(_need(self, str, "kebab")).replace("_", "-")


@method("str")
def strip_prefix(self, prefix):
    """remove leading text if present"""
    s, p = _need(self, str, "strip_prefix"), to_string(prefix)
    return s[len(p):] if s.startswith(p) else s


@method("str")
def strip_suffix(self, suffix):
    """remove trailing text if present"""
    s, p = _need(self, str, "strip_suffix"), to_string(suffix)
    return s[:-len(p)] if p and s.endswith(p) else s


@method("str")
def wrap(self, width=79.0):
    """reflow text to a maximum line width"""
    return "\n".join(_textwrap.fill(line, as_int(width, "width"))
                     for line in _need(self, str, "wrap").splitlines())


@method("str")
def indent(self, spaces=2.0, prefix=None):
    """indent every line"""
    pad = to_string(prefix) if prefix is not None else " " * as_int(spaces, "spaces")
    return "\n".join(pad + line if line.strip() else line
                     for line in _need(self, str, "indent").splitlines())


# ============================================================== list ======
@method("list")
def len(self):
    """how many items"""
    return float(len(_need(self, list, "len")))


@method("list")
def push(self, *items):
    """append items in place and return the list"""
    _need(self, list, "push").extend(items)
    return self


@method("list")
def pop(self, index=-1.0):
    """remove and return an item (the last by default)"""
    lst = _need(self, list, "pop")
    return lst.pop(as_int(index, "index")) if lst else None


@method("list")
def shift(self):
    """remove and return the first item"""
    lst = _need(self, list, "shift")
    return lst.pop(0) if lst else None


@method("list")
def unshift(self, *items):
    """add items to the front"""
    lst = _need(self, list, "unshift")
    lst[0:0] = list(items)
    return lst


@method("list")
def insert(self, index, value):
    """put a value at a position"""
    _need(self, list, "insert").insert(as_int(index, "index"), value)
    return self


@method("list")
def remove(self, index):
    """delete the item at a position"""
    lst = _need(self, list, "remove")
    i = as_int(index, "index")
    if i < 0:
        i += len(lst)
    return lst.pop(i) if 0 <= i < len(lst) else None


@method("list")
def remove_value(self, value):
    """delete the first item equal to value"""
    lst = _need(self, list, "remove_value")
    for i, v in enumerate(lst):
        if omni_eq(v, value):
            return lst.pop(i)
    return None


@method("list")
def at(self, index, default=None):
    """an item by position; negative counts from the end"""
    lst = _need(self, list, "at")
    i = as_int(index, "index")
    if i < 0:
        i += len(lst)
    return lst[i] if 0 <= i < len(lst) else default


@method("list")
def first(self, default=None):
    """the opening item"""
    lst = _need(self, list, "first")
    return lst[0] if lst else default


@method("list")
def last(self, default=None):
    """the closing item"""
    lst = _need(self, list, "last")
    return lst[-1] if lst else default


@method("list")
def contains(self, value):
    """is this value in the list?"""
    return any(omni_eq(v, value) for v in _need(self, list, "contains"))


@method("list")
def index_of(self, value):
    """position of a value, or -1"""
    for i, v in enumerate(_need(self, list, "index_of")):
        if omni_eq(v, value):
            return float(i)
    return -1.0


@method("list")
def take(self, n):
    """the first n items"""
    return _need(self, list, "take")[:as_int(n, "n")]


@method("list")
def drop(self, n):
    """everything after the first n items"""
    return _need(self, list, "drop")[as_int(n, "n"):]


@method("list")
def take_while(self, fn):
    """items until the test first fails"""
    out = []
    for v in _need(self, list, "take_while"):
        if not truthy(_call(fn, [v])):
            break
        out.append(v)
    return out


@method("list")
def drop_while(self, fn):
    """skip items while the test passes"""
    lst = _need(self, list, "drop_while")
    i = 0
    while i < len(lst) and truthy(_call(fn, [lst[i]])):
        i += 1
    return lst[i:]


@method("list")
def slice(self, start=0.0, end=None, step=None):
    """a sub-list"""
    return _need(self, list, "slice")[
        as_int(start, "start"):None if end is None else as_int(end, "end"):
        None if step is None else as_int(step, "step")]


@method("list")
def reverse(self):
    """a new list, backwards"""
    return list(reversed(_need(self, list, "reverse")))


@method("list")
def reverse_in_place(self):
    """flip this list itself"""
    _need(self, list, "reverse_in_place").reverse()
    return self


def _capacity(fn):
    """How many positional arguments a callback declared it wants."""
    target = fn
    from ..interp import BoundMethod, BoundNative
    if isinstance(target, BoundNative):
        target = target.fn
    elif isinstance(target, BoundMethod):
        target = target.fn
    params = getattr(target, "params", None)
    if params is None or any(p.get("rest") for p in params):
        return None
    return sum(1 for p in params if not p.get("kwrest") and not p.get("kw_only"))


def _sort_items(lst, by=None, desc=False):
    import functools
    if by is None:
        items = sorted(lst, key=_sort_key)
    elif isinstance(by, str):
        items = sorted(lst, key=lambda x: _sort_key(x.get(by) if isinstance(x, dict) else x))
    elif _capacity(by) == 2:
        # two arguments means "compare these two", not "give me a sort key"
        def compare(a, b):
            r = _call(by, [a, b])
            if isinstance(r, bool):
                return -1 if r else 1
            return int(r)
        items = sorted(lst, key=functools.cmp_to_key(compare))
    else:
        items = sorted(lst, key=lambda x: _sort_key(_call(by, [x])))
    return list(reversed(items)) if truthy(desc) else items


@method("list")
def sort(self, by=None, desc=False):
    """a new, ordered list"""
    return _sort_items(_need(self, list, "sort"), by, desc)


@method("list")
def sort_in_place(self, by=None, desc=False):
    """order this list itself"""
    lst = _need(self, list, "sort_in_place")
    lst[:] = _sort_items(lst, by, desc)
    return lst


@method("list")
def unique(self):
    """drop repeats, keeping the first of each"""
    seen, out = set(), []
    for v in _need(self, list, "unique"):
        k = to_repr(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


@method("list")
def flatten(self, depth=1.0):
    """unwrap nested lists; depth: -1 unwraps all of them"""
    items = list(_need(self, list, "flatten"))
    limit = as_int(depth, "depth")
    passes = 0
    while limit < 0 or passes < limit:
        out, changed = [], False
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


@method("list")
def join(self, sep=""):
    """glue items into text"""
    return to_string(sep).join(to_string(v) for v in _need(self, list, "join"))


@method("list")
def concat(self, *others):
    """a new list with everything appended"""
    out = list(_need(self, list, "concat"))
    for o in others:
        out.extend(o if isinstance(o, list) else _iterate(o) if isinstance(o, OmniRange) else [o])
    return out


@method("list")
def map(self, fn):
    """apply a function to every item"""
    return [_call(fn, [v, float(i)]) for i, v in enumerate(_need(self, list, "map"))]


@method("list")
def filter(self, fn=None):
    """keep only what passes"""
    out = []
    for i, v in enumerate(_need(self, list, "filter")):
        keep = truthy(v) if fn is None else truthy(_call(fn, [v, float(i)]))
        if keep:
            out.append(v)
    return out


@method("list")
def flat_map(self, fn):
    """map then flatten one level"""
    out = []
    for i, v in enumerate(_need(self, list, "flat_map")):
        r = _call(fn, [v, float(i)])
        if isinstance(r, list):
            out.extend(r)
        elif isinstance(r, OmniRange):
            out.extend(r.values())
        else:
            out.append(r)
    return out


@method("list")
def reject(self, fn):
    """throw away what passes"""
    return [v for i, v in enumerate(_need(self, list, "reject"))
            if not truthy(_call(fn, [v, float(i)]))]


@method("list")
def reduce(self, fn, initial=None):
    """fold into one value"""
    it = iter(_need(self, list, "reduce"))
    acc = initial
    if acc is None:
        try:
            acc = next(it)
        except StopIteration:
            raise OmniRuntimeError("reduce of an empty list needs an initial value")
    for i, v in enumerate(it):
        acc = _call(fn, [acc, v, float(i)])
    return acc


@method("list")
def each(self, fn):
    """run something for every item"""
    for i, v in enumerate(_need(self, list, "each")):
        _call(fn, [v, float(i)])
    return None


@method("list")
def find(self, fn):
    """the first item that passes"""
    for i, v in enumerate(_need(self, list, "find")):
        if truthy(_call(fn, [v, float(i)])):
            return v
    return None


@method("list")
def find_index(self, fn):
    """position of the first item that passes, else -1"""
    for i, v in enumerate(_need(self, list, "find_index")):
        if truthy(_call(fn, [v, float(i)])):
            return float(i)
    return -1.0


@method("list")
def some(self, fn=None):
    """does at least one pass?"""
    for i, v in enumerate(_need(self, list, "some")):
        if truthy(v) if fn is None else truthy(_call(fn, [v, float(i)])):
            return True
    return False


@method("list")
def every(self, fn=None):
    """do all of them pass?"""
    for i, v in enumerate(_need(self, list, "every")):
        if not (truthy(v) if fn is None else truthy(_call(fn, [v, float(i)]))):
            return False
    return True


@method("list")
def sum(self, by=None):
    """add everything up"""
    return sum(_num_of(v, by) for v in _need(self, list, "sum"))


@method("list")
def avg(self, by=None):
    """the arithmetic mean"""
    vals = [_num_of(v, by) for v in _need(self, list, "avg")]
    if not vals:
        raise OmniRuntimeError("cannot average an empty list")
    return sum(vals) / len(vals)


@method("list")
def min(self, by=None):
    """the smallest"""
    vals = [_num_of(v, by) for v in _need(self, list, "min")]
    if not vals:
        raise OmniRuntimeError("min of an empty list")
    return min(vals)


@method("list")
def max(self, by=None):
    """the largest"""
    vals = [_num_of(v, by) for v in _need(self, list, "max")]
    if not vals:
        raise OmniRuntimeError("max of an empty list")
    return max(vals)


@method("list")
def chunk(self, size):
    """split into groups of n"""
    n = as_int(size, "size")
    if n <= 0:
        raise OmniRuntimeError("chunk size must be at least 1")
    lst = _need(self, list, "chunk")
    return [lst[i:i + n] for i in range(0, len(lst), n)]


@method("list")
def zip(self, other):
    """pair items up"""
    return [list(t) for t in zip(_need(self, list, "zip"), _iterate(other))]


@method("list")
def pairs(self, start=0.0):
    """[[index, item], ...]"""
    s = as_int(start, "start")
    return [[float(s + i), v] for i, v in enumerate(_need(self, list, "pairs"))]


@method("list")
def group_by(self, key):
    """bucket items into a map"""
    out: dict[str, list] = {}
    for v in _need(self, list, "group_by"):
        if isinstance(key, str):
            if not isinstance(v, dict):
                raise OmniTypeError("grouping by a key name needs a list of maps")
            k = to_string(v.get(key))
        else:
            k = to_string(_call(key, [v]))
        out.setdefault(k, []).append(v)
    return out


@method("list")
def to_map(self, key, value=None):
    """index a list of maps by one of their fields"""
    out = {}
    for v in _need(self, list, "to_map"):
        k = v.get(key) if isinstance(key, str) and isinstance(v, dict) else _call(key, [v])
        if value is None:
            val = v
        elif isinstance(value, str):
            val = v.get(value) if isinstance(v, dict) else None
        else:
            val = _call(value, [v])
        out[_key(k)] = val
    return out


@method("list")
def sample(self, n=1.0):
    """n items at random"""
    lst = _need(self, list, "sample")
    if not lst:
        raise OmniRuntimeError("cannot sample an empty list")
    k = as_int(n, "n")
    return _random.sample(lst, k) if 0 <= k <= len(lst) \
        else [_random.choice(lst) for _ in range(max(0, k))]


@method("list")
def shuffle(self):
    """a new list in random order"""
    lst = list(_need(self, list, "shuffle"))
    _random.shuffle(lst)
    return lst


@method("list")
def clear(self):
    """empty this list in place"""
    _need(self, list, "clear").clear()
    return self


@method("list")
def is_empty(self):
    """does it hold nothing?"""
    return len(_need(self, list, "is_empty")) == 0


@method("list")
def to_json(self, indent=None):
    """serialise to JSON text"""
    pad = None if indent is None else as_int(indent, "indent")
    return _json.dumps(_plain(_need(self, list, "to_json")), indent=pad)


@method("list")
def counts(self):
    """how many times each value appears"""
    out: dict[str, float] = {}
    for v in _need(self, list, "counts"):
        k = to_string(v)
        out[k] = out.get(k, 0.0) + 1.0
    return out


@method("list")
def interleave(self, sep):
    """put a separator between every item"""
    out = []
    lst = _need(self, list, "interleave")
    for i, v in enumerate(lst):
        if i:
            out.append(sep)
        out.append(v)
    return out


# ============================================================== map =======
@method("map")
def len(self):
    """how many keys"""
    return float(len(_need(self, dict, "len")))


@method("map")
def keys(self):
    """every key"""
    return list(_need(self, dict, "keys").keys())


@method("map")
def values(self):
    """every value"""
    return list(_need(self, dict, "values").values())


@method("map")
def entries(self):
    """[[key, value], ...]"""
    return [[k, v] for k, v in _need(self, dict, "entries").items()]


@method("map")
def has(self, key):
    """is this key present?"""
    return _key(key) in _need(self, dict, "has")


@method("map")
def get(self, key, default=None):
    """read a key safely"""
    return _need(self, dict, "get").get(_key(key), default)


@method("map")
def set(self, key, value):
    """write a key in place"""
    _need(self, dict, "set")[_key(key)] = value
    return self


@method("map")
def remove(self, key):
    """delete a key in place"""
    return _need(self, dict, "remove").pop(_key(key), None)


@method("map")
def merge(self, *others):
    """a new map with everything combined"""
    out = dict(_need(self, dict, "merge"))
    for o in others:
        if not isinstance(o, dict):
            raise OmniTypeError(f"merge needs maps, got {type_name(o)}")
        out.update(o)
    return out


@method("map")
def update(self, other):
    """combine another map into this one"""
    _need(self, dict, "update").update(_need(other, dict, "update"))
    return self


@method("map")
def pick(self, *names):
    """a smaller map with only those keys"""
    src = _need(self, dict, "pick")
    return {_key(n): src[_key(n)] for n in names if _key(n) in src}


@method("map")
def omit(self, *names):
    """a copy without those keys"""
    src = _need(self, dict, "omit")
    skip = {_key(n) for n in names}
    return {k: v for k, v in src.items() if k not in skip}


@method("map")
def map(self, fn):
    """apply a function to every value"""
    return {k: _call(fn, [v, k]) for k, v in _need(self, dict, "map").items()}


@method("map")
def filter(self, fn=None):
    """keep the entries that pass"""
    out = {}
    for k, v in _need(self, dict, "filter").items():
        keep = truthy(v) if fn is None else truthy(_call(fn, [v, k]))
        if keep:
            out[k] = v
    return out


@method("map")
def each(self, fn):
    """run something for every entry"""
    for k, v in _need(self, dict, "each").items():
        _call(fn, [v, k])
    return None


@method("map")
def invert(self):
    """swap keys and values"""
    return {_key(v): k for k, v in _need(self, dict, "invert").items()}


@method("map")
def sort_by(self, key="value", desc=False):
    """a list of entries, ordered by key or value"""
    items = list(_need(self, dict, "sort_by").items())
    if isinstance(key, str) and key in ("key", "value"):
        items.sort(key=lambda kv: _sort_key(kv[0] if key == "key" else kv[1]))
    else:
        items.sort(key=lambda kv: _sort_key(_call(key, [kv[1], kv[0]])))
    if truthy(desc):
        items.reverse()
    return [[k, v] for k, v in items]


@method("map")
def to_list(self):
    """[[key, value], ...]"""
    return [[k, v] for k, v in _need(self, dict, "to_list").items()]


@method("map")
def to_json(self, indent=None):
    """serialise to JSON text"""
    pad = None if indent is None else as_int(indent, "indent")
    return _json.dumps(_plain(_need(self, dict, "to_json")), indent=pad)


@method("map")
def sum(self, by=None):
    """add the values up"""
    return sum(_num_of(v, by) for v in _need(self, dict, "sum").values())


@method("map")
def clear(self):
    """empty this map in place"""
    _need(self, dict, "clear").clear()
    return self


@method("map")
def is_empty(self):
    """does it hold nothing?"""
    return len(_need(self, dict, "is_empty")) == 0


# ============================================================== num =======
@method("num")
def abs(self):
    """drop the sign"""
    return abs(as_num(self, "value"))


@method("num")
def round(self, places=0.0):
    """round to n decimal places"""
    return round(as_num(self, "value"), as_int(places, "places"))


@method("num")
def floor(self):
    """round down"""
    return float(_math.floor(as_num(self, "value")))


@method("num")
def ceil(self):
    """round up"""
    return float(_math.ceil(as_num(self, "value")))


@method("num")
def sqrt(self):
    """the square root"""
    v = as_num(self, "value")
    if v < 0:
        raise OmniRuntimeError("cannot take the square root of a negative number")
    return _math.sqrt(v)


@method("num")
def pow(self, exponent):
    """raise to a power"""
    return as_num(self, "value") ** as_num(exponent, "exponent")


@method("num")
def clamp(self, lo, hi):
    """force between two bounds"""
    return min(max(as_num(self, "value"), as_num(lo, "low")), as_num(hi, "high"))


@method("num")
def to_int(self):
    """drop the fraction"""
    return float(int(as_num(self, "value")))


@method("num")
def to_str(self):
    """render as text"""
    return fmt_num(as_num(self, "value"))


@method("num")
def to_fixed(self, places=2.0):
    """fixed-point text, e.g. 3.10"""
    return f"{as_num(self, 'value'):.{as_int(places, 'places')}f}"


@method("num")
def times(self, fn=None):
    """run a function this many times, or produce 0..n"""
    n = as_int(self, "value")
    if n < 0:
        raise OmniRuntimeError("cannot repeat a negative number of times")
    if fn is None:
        return OmniRange(0.0, float(n), 1.0, False)
    return [_call(fn, [float(i)]) for i in range(n)]


@method("num")
def up_to(self, stop, fn=None):
    """count from here up to stop"""
    lo, hi = as_num(self, "value"), as_num(stop, "stop")
    if fn is None:
        return OmniRange(lo, hi, 1.0, True)
    out, v = [], lo
    while v <= hi:
        out.append(_call(fn, [v]))
        v += 1
    return out


@method("num")
def down_to(self, stop, fn=None):
    """count down from here to stop"""
    lo, hi = as_num(self, "value"), as_num(stop, "stop")
    if fn is None:
        return OmniRange(lo, hi, -1.0, True)
    out, v = [], lo
    while v >= hi:
        out.append(_call(fn, [v]))
        v -= 1
    return out


@method("num")
def is_even(self):
    """divisible by two?"""
    return as_int(self, "value") % 2 == 0


@method("num")
def is_odd(self):
    """not divisible by two?"""
    return as_int(self, "value") % 2 != 0


@method("num")
def is_whole(self):
    """no fractional part?"""
    return float(as_num(self, "value")).is_integer()


@method("num")
def sign(self):
    """-1, 0 or 1"""
    v = as_num(self, "value")
    return float((v > 0) - (v < 0))


@method("num")
def between(self, lo, hi, inclusive=True):
    """is this number inside a range?"""
    v, a, b = as_num(self, "value"), as_num(lo, "low"), as_num(hi, "high")
    return (a <= v <= b) if truthy(inclusive) else (a < v < b)


@method("num")
def percent_of(self, total):
    """what percentage is this of total?"""
    t = as_num(total, "total")
    if t == 0:
        raise OmniRuntimeError("cannot take a percentage of zero")
    return as_num(self, "value") / t * 100.0


@method("num")
def gcd(self, other):
    """greatest common divisor"""
    return float(_math.gcd(as_int(self, "value"), as_int(other, "other")))


@method("num")
def format(self, spec=","):
    """format with a layout spec, e.g. (1234.5).format(",.2f")"""
    return format(as_num(self, "value"), to_string(spec))


@method("num")
def ordinal(self):
    """1 -> "1st", 2 -> "2nd", ..."""
    n = as_int(self, "value")
    if 10 <= abs(n) % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(n) % 10, "th")
    return f"{n}{suffix}"


# ============================================================== bool ======
@method("bool")
def to_str(self):
    """"true" or "false" """
    return "true" if self else "false"


@method("bool")
def to_num(self):
    """1 or 0"""
    return 1.0 if self else 0.0


@method("bool")
def not_(self):
    """flip it"""
    return not truthy(self)


apply_aliases()


# Every collection function is also reachable as a method, so `map_each(xs, f)`
# and `xs.map_each(f)` mean the same thing. Names that already have a real
# method keep it.
GLOBAL_ALIASES: dict[str, tuple[str, ...]] = {
    "list": ("map_each", "count_by", "sort_by", "group_by", "sum", "avg", "median",
             "min", "max", "first", "last", "compact", "flatten", "unique",
             "take_while", "drop_while", "enumerate", "sample", "shuffle", "zip",
             "chunk", "pairs", "to_map", "counts", "sorted", "reverse", "each",
             "find", "some", "every", "reduce", "filter", "reject", "map", "join",
             "push", "pop", "insert", "remove", "clear", "take", "drop", "slice",
             "at", "index_of", "contains", "flat_map", "range", "len", "sorted_by"),
    "map": ("entries", "keys", "values", "has", "get", "set", "remove", "merge",
            "update", "pick", "omit", "invert", "sort_by", "to_list", "map",
            "filter", "each", "counts", "len", "first", "last"),
    "str": ("split", "join", "words", "lines", "chars", "replace", "contains",
            "starts_with", "ends_with", "index_of", "repeat", "pad_start",
            "pad_end", "trim", "upper", "lower", "title", "capitalize", "center",
            "reverse", "slice", "at", "matches", "match", "find_all", "count",
            "to_num", "to_json", "snake", "camel", "kebab", "wrap", "indent",
            "bytes", "slug", "len"),
    "num": ("clamp", "times", "up_to", "down_to", "between", "percent_of", "gcd",
            "format", "ordinal", "to_fixed", "round", "floor", "ceil", "abs",
            "sqrt", "pow", "to_int", "is_even", "is_odd"),
}


def apply_global_aliases():
    from .core import BUILTINS
    by_name: dict[str, NativeFunction] = {}
    for nf in BUILTINS:
        by_name.setdefault(nf.name, nf)
    for type_, names in GLOBAL_ALIASES.items():
        table = METHODS.setdefault(type_, {})
        for name in names:
            if name in table:
                continue
            target = by_name.get(name)
            if target is None:
                continue
            table[name] = _forwarding_method(name, target)


def _forwarding_method(name, target):
    """Build a method that runs the global function with `self` in front."""
    def alias(interp, self, *args, **kwargs):
        return interp.call_loose(target, [self, *args], kwargs, node=None)

    alias.__name__ = name
    nf = collect_signature(alias, name,
                           f"the {name}() function, written as a method",
                           takes_interp=True)
    _REGISTERED.append(name)
    return nf


apply_global_aliases()


def _release_builtin_names():
    """Put Python's built-ins back in scope for the method bodies above."""
    for name in dict.fromkeys(_REGISTERED):
        globals().pop(name, None)


_release_builtin_names()
