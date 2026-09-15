"""Installing the OmniScript standard library.

There is nothing to import inside an OmniScript program: `install()` puts every
built-in into the global scope once, before the first line of user code runs.
"""

from __future__ import annotations

import math
import sys

from ..values import HostObject

VERSION = "1.0.0"

CONSTANTS = {
    "pi": math.pi,
    "PI": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "infinity": math.inf,
    "nan": math.nan,
    "phi": (1 + math.sqrt(5)) / 2,
    "sqrt2": math.sqrt(2),
    "version": VERSION,
    "os": {"linux": "linux", "darwin": "darwin", "windows": "windows"}.get(
        sys.platform, sys.platform),
    "newline": "\n",
    "tab": "\t",
}


def install(interp) -> None:
    from . import (concurrent, core, dates, graphics, methods, net,  # noqa: F401
                     system)

    for nf in core.BUILTINS:
        interp.globals.define(nf.name, nf)
        interp.builtin_index[nf.name] = nf

    interp.methods = dict(methods.METHODS)

    for name, value in CONSTANTS.items():
        interp.globals.define(name, value)
        interp.globals.immutable.add(name)

    interp.globals.define("argv", list(interp.argv))
    interp.globals.immutable.add("argv")

    interp.globals.define("std", _std_namespace(interp))
    _install_error_class(interp)


def _install_error_class(interp) -> None:
    """A script-visible base class so users can write `class MyError : Error`."""
    interp.run_source(
        """
class Error {
  message = ""
  kind = "error"
  new(message = "", kind = "error") {
    self.message = message
    self.kind = kind
  }
  fn str() { "${self.kind}: ${self.message}" }
}
""",
        "<builtin:Error>",
    )
    for name in ("Error",):
        interp.globals.immutable.add(name)


def _std_namespace(interp) -> HostObject:
    """`std.math.pi`, `std.text.slug(...)` -- a tidier way to reach some tools."""
    groups = {
        "math": ["abs", "round", "floor", "ceil", "sqrt", "pow", "exp", "log",
                 "log2", "log10", "sin", "cos", "tan", "atan2", "hypot", "clamp",
                 "lerp", "sign", "gcd", "lcm", "min", "max", "sum", "avg", "median",
                 "degrees", "radians", "rand", "rand_int", "choice", "shuffle", "seed"],
        "text": ["upper", "lower", "title", "trim", "split", "join", "replace",
                 "repeat", "pad_start", "pad_end", "center", "chars", "words",
                 "lines_of", "format", "slug", "starts_with", "ends_with", "ord", "chr"],
        "list": ["len", "sorted", "reverse", "unique", "flatten", "chunk", "zip",
                 "first", "last", "take", "drop", "push", "pop", "insert", "remove",
                 "enumerate", "map_each", "filter", "reduce", "each", "find",
                 "some", "every", "group_by", "count_by"],
        "io": ["print", "show", "input", "read", "write", "append", "read_lines",
               "write_lines", "exists", "list_dir", "glob", "walk", "mkdir", "copy",
               "move", "remove_dir", "file_info", "read_csv", "write_csv", "to_csv",
               "read_json", "write_json", "table"],
        "net": ["http", "http_get", "http_post", "http_put", "http_patch",
                "http_delete", "download", "ping", "http_get_all", "url_encode",
                "url_decode", "url_parts"],
        "sys": ["cmd", "cmd_print", "which", "cwd", "chdir", "home", "hostname",
                "platform", "env", "set_env", "exit", "args", "arg", "sleep", "now",
                "today", "timestamp", "parallel", "parallel_map", "spawn",
                "elapsed", "script_dir", "path_join", "path_dir", "path_base",
                "path_ext", "path_abs"],
        "draw": ["draw", "window", "window_size", "chart", "sparkline",
                 "progress_bar", "rgb", "hsl", "mix_colors", "palette",
                 "save_picture"],
        "re": ["regex", "regex_all", "regex_named", "regex_test", "regex_replace",
               "regex_split", "regex_escape"],
    }
    fields = {}
    for group, names in groups.items():
        fields[group] = {n: interp.builtin_index[n] for n in names
                         if n in interp.builtin_index}
    fields["version"] = VERSION
    return HostObject("std", fields=fields,
                      display=lambda o: "<std " + " ".join(sorted(o.fields)) + ">")
