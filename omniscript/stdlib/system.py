"""OmniScript system built-ins: running programs, files, paths and the shell.

The headline idea is that everyday system work takes one call:

    cmd("git status").out            # run a program, keep its output
    read("notes.txt").lines()        # read a file
    read_csv("data.csv")             # straight to a list of maps
    write_json("out.json", data)     # straight back out again
"""

from __future__ import annotations

import csv as _csv
import io as _io
import json as _json
import os as _os
import shlex as _shlex
import shutil as _shutil
import subprocess as _sp
import time as _time
from glob import glob as _glob

from ..errors import OmniRuntimeError
from ..values import HostObject, NativeFunction, collect_signature, to_repr, to_string, truthy
from .core import as_int, as_num, omni

# --------------------------------------------------------------------- cmd
COMMAND_METHODS: dict[str, NativeFunction] = {}


def _cmd_method(fn):
    COMMAND_METHODS[fn.__name__] = collect_signature(fn, fn.__name__,
                                                     (fn.__doc__ or "").strip(),
                                                     takes_interp=False)
    return fn


@_cmd_method
def lines(self):
    """stdout split into lines"""
    return self.fields["stdout"].splitlines()


@_cmd_method
def out_lines(self):
    """stderr split into lines"""
    return self.fields["stderr"].splitlines()


@_cmd_method
def trim(self):
    """stdout with the surrounding whitespace removed"""
    return self.fields["stdout"].strip()


@_cmd_method
def json(self):
    """stdout parsed as JSON"""
    try:
        return _json.loads(self.fields["stdout"])
    except _json.JSONDecodeError as e:
        raise OmniRuntimeError(f"the output of `{self.fields['command']}` is not JSON: {e.msg}")


@_cmd_method
def num(self):
    """stdout parsed as a number"""
    try:
        return float(self.fields["stdout"].strip())
    except ValueError:
        raise OmniRuntimeError(f"the output of `{self.fields['command']}` is not a number")


@_cmd_method
def echo(self):
    """print stdout to the screen"""
    from ..interp import Interpreter
    Interpreter.current().out(self.fields["stdout"].rstrip("\n"))
    return self


@_cmd_method
def check(self, message=None):
    """raise if the command failed"""
    if not self.fields["ok"]:
        detail = message or f"`{self.fields['command']}` failed with exit code " \
                            f"{int(self.fields['code'])}"
        raise OmniRuntimeError(to_string(detail),
                               hint=self.fields["stderr"].strip()[:400] or None)
    return self


@_cmd_method
def save(self, path):
    """write stdout to a file"""
    with open(to_string(path), "w", encoding="utf-8") as fh:
        fh.write(self.fields["stdout"])
    return to_string(path)


def make_result(command: str, code: int, stdout: str, stderr: str,
                seconds: float) -> HostObject:
    return HostObject(
        "CommandResult",
        methods=dict(COMMAND_METHODS),
        fields={"command": command, "code": float(code), "ok": code == 0,
                "stdout": stdout, "stderr": stderr, "out": stdout, "err": stderr,
                "seconds": seconds},
        display=lambda o: f"<CommandResult `{o.fields['command']}` "
                          f"exit={int(o.fields['code'])}>",
    )


def _run(interp, command, args, cwd=None, env=None, timeout=None, shell=None,
         stdin_text=None, quiet=False):
    pieces = [to_string(command)] + [to_string(a) for a in args]
    joined = " ".join(pieces)
    use_shell = shell
    workdir = to_string(cwd) if cwd is not None else None
    environ = dict(_os.environ)
    if isinstance(env, dict):
        environ.update({str(k): to_string(v) for k, v in env.items()})
    limit = None if timeout is None else as_num(timeout, "timeout")

    argv = pieces
    if not args and command is not None:
        try:
            argv = _shlex.split(to_string(command))
        except ValueError:
            argv = [to_string(command)]

    start = _time.time()
    attempts = []
    if use_shell is True:
        attempts = [(joined, True)]
    elif use_shell is False:
        attempts = [(argv, False)]
    else:
        attempts = [(argv, False), (joined, True)]

    last_error = None
    for target, sh in attempts:
        try:
            proc = _sp.run(
                target, shell=sh, cwd=workdir, env=environ, timeout=limit,
                capture_output=True, text=True, errors="replace",
                input=None if stdin_text is None else to_string(stdin_text),
            )
            return make_result(joined, proc.returncode, proc.stdout or "",
                               proc.stderr or "", _time.time() - start)
        except FileNotFoundError as e:
            last_error = e
            continue
        except _sp.TimeoutExpired:
            raise OmniRuntimeError(f"`{joined}` did not finish within {limit} seconds",
                                   hint="pass a bigger `timeout:` or drop it entirely")
        except OSError as e:
            raise OmniRuntimeError(f"could not run `{joined}`: {e}")
    raise OmniRuntimeError(f"could not find a program to run `{joined}`",
                           hint=str(last_error) if last_error else None)


@omni("cmd", alias=("shell", "run", "exec"))
def _cmd(interp, command, *args, cwd=None, env=None, timeout=None, shell=None,
         stdin_text=None):
    """cmd("git status") -- run a program and keep its output.

    Returns a result with `.out`, `.err`, `.code`, `.ok`, `.lines()` and `.json()`.
    """
    return _run(interp, command, args, cwd, env, timeout, shell, stdin_text)


@omni("cmd_print", alias=("system",))
def _cmd_print(interp, command, *args, cwd=None, env=None, timeout=None):
    """cmd_print("ls") -- run a program and stream its output straight to you."""
    pieces = [to_string(command)] + [to_string(a) for a in args]
    joined = " ".join(pieces)
    workdir = to_string(cwd) if cwd is not None else None
    environ = dict(_os.environ)
    if isinstance(env, dict):
        environ.update({str(k): to_string(v) for k, v in env.items()})
    try:
        argv = _shlex.split(to_string(command)) if not args else pieces
    except ValueError:
        argv = [to_string(command)]
    for target, sh in ((argv, False), (joined, True)):
        try:
            code = _sp.call(target, shell=sh, cwd=workdir, env=environ,
                            timeout=None if timeout is None else as_num(timeout, "timeout"))
            return float(code)
        except FileNotFoundError:
            continue
        except _sp.TimeoutExpired:
            raise OmniRuntimeError(f"`{joined}` timed out")
    raise OmniRuntimeError(f"could not find a program to run `{joined}`")


@omni("cmd_ok")
def _cmd_ok(interp, command, *args, **opts):
    """cmd_ok("git status") -- true only when the command exits with 0."""
    return _run(interp, command, args, opts.get("cwd"), opts.get("env"),
                opts.get("timeout"), opts.get("shell"), None).fields["ok"]


@omni("which")
def _which(interp, program):
    """which("git") -- where a program lives, or null."""
    found = _shutil.which(to_string(program))
    return found


# ------------------------------------------------------------------ process
@omni("cwd")
def _cwd(interp):
    """cwd() -- the folder you are running from."""
    return _os.getcwd()


@omni("chdir")
def _chdir(interp, path):
    """chdir(path) -- switch folder."""
    _os.chdir(to_string(path))
    return _os.getcwd()


@omni("home")
def _home(interp):
    """home() -- your home folder."""
    return _os.path.expanduser("~")


@omni("hostname")
def _hostname(interp):
    """hostname() -- this machine's name."""
    import socket
    return socket.gethostname()


@omni("platform")
def _platform(interp):
    """platform() -- "linux", "darwin" or "windows"."""
    import platform as _p
    return {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(
        _p.system(), _p.system().lower())


@omni("args")
def _args(interp):
    """args() -- the command-line arguments passed to this script."""
    return list(interp.argv)


@omni("arg")
def _arg(interp, index, default=None):
    """arg(0) -- one command-line argument by position."""
    i = as_int(index, "index")
    return interp.argv[i] if 0 <= i < len(interp.argv) else default


@omni("env")
def _env(interp, name=None, default=None):
    """env() -- every variable; env("HOME") -- one of them."""
    if name is None:
        return {k: v for k, v in _os.environ.items()}
    return _os.environ.get(to_string(name), default)


@omni("set_env")
def _set_env(interp, name, value):
    """set_env("TOKEN", "abc") -- change an environment variable."""
    _os.environ[to_string(name)] = to_string(value)
    return None


@omni("exit_code")
def _exit_code(interp, code):
    """exit_code(1) -- choose the code this program ends with."""
    interp.exit_code = as_int(code, "code")
    return None


# ------------------------------------------------------------------- files
def _path(p):
    return _os.path.expanduser(to_string(p))


@omni("read")
def _read(interp, path, encoding="utf-8", default=None):
    """read("notes.txt") -- the whole file as text."""
    target = _path(path)
    try:
        with open(target, "r", encoding=to_string(encoding), errors="replace") as fh:
            return fh.read()
    except FileNotFoundError:
        if default is not None:
            return to_string(default)
        raise OmniRuntimeError(f"there is no file called `{target}`",
                               hint="check the path, or pass `default: \"\"`")
    except IsADirectoryError:
        raise OmniRuntimeError(f"`{target}` is a folder, not a file",
                               hint="use `list_dir()` to see what is inside")
    except UnicodeDecodeError as e:
        raise OmniRuntimeError(f"`{target}` is not {to_string(encoding)} text: {e}")


@omni("read_bytes")
def _read_bytes(interp, path):
    """read_bytes("logo.png") -- the raw bytes as a list of numbers."""
    with open(_path(path), "rb") as fh:
        return [float(b) for b in fh.read()]


@omni("read_lines")
def _read_lines(interp, path, keep_empty=True):
    """read_lines("log.txt") -- the file as a list of lines."""
    text = _read(interp, path)
    out = text.splitlines()
    return out if truthy(keep_empty) else [l for l in out if l.strip()]


@omni("write")
def _write(interp, path, content, encoding="utf-8"):
    """write("out.txt", "hello") -- create or replace a file."""
    target = _path(path)
    parent = _os.path.dirname(target)
    if parent and not _os.path.isdir(parent):
        _os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding=to_string(encoding)) as fh:
        fh.write(to_string(content))
    return target


@omni("write_lines")
def _write_lines(interp, path, rows):
    """write_lines("out.txt", ["a", "b"]) -- one item per line."""
    from ..interp import Interpreter
    return _write(interp, path, "\n".join(to_string(r) for r in Interpreter.current().iterate(rows)))


@omni("write_bytes")
def _write_bytes(interp, path, data):
    """write_bytes("out.bin", [72, 105]) -- write raw bytes."""
    from ..interp import Interpreter
    values = [as_int(b, "byte") for b in Interpreter.current().iterate(data)]
    with open(_path(path), "wb") as fh:
        fh.write(bytes(values))
    return to_string(path)


@omni("append")
def _append(interp, path, content):
    """append("log.txt", "another line\\n") -- add to the end of a file."""
    target = _path(path)
    parent = _os.path.dirname(target)
    if parent and not _os.path.isdir(parent):
        _os.makedirs(parent, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(to_string(content))
    return target


@omni("exists")
def _exists(interp, path):
    """exists("notes.txt") -- is there anything at this path?"""
    return _os.path.exists(_path(path))


@omni("is_file")
def _is_file(interp, path):
    """is_file(path) -- is it a regular file?"""
    return _os.path.isfile(_path(path))


@omni("is_dir", alias=("is_folder",))
def _is_dir(interp, path):
    """is_dir(path) -- is it a folder?"""
    return _os.path.isdir(_path(path))


@omni("remove", alias=("delete_file",))
def _remove(interp, path):
    """remove(path) -- delete a file."""
    target = _path(path)
    try:
        _os.remove(target)
        return True
    except FileNotFoundError:
        return False
    except IsADirectoryError:
        raise OmniRuntimeError(f"`{target}` is a folder", hint="use `remove_dir()` instead")


@omni("remove_dir")
def _remove_dir(interp, path, recursive=True):
    """remove_dir(path) -- delete a folder."""
    target = _path(path)
    if not _os.path.isdir(target):
        return False
    if truthy(recursive):
        _shutil.rmtree(target)
    else:
        _os.rmdir(target)
    return True


@omni("mkdir")
def _mkdir(interp, path, parents=True):
    """mkdir("build/out") -- create a folder."""
    _os.makedirs(_path(path), exist_ok=True if truthy(parents) else False)
    return to_string(path)


@omni("copy")
def _copy(interp, src, dst):
    """copy("a.txt", "b.txt") -- duplicate a file or folder."""
    s, d = _path(src), _path(dst)
    if _os.path.isdir(s):
        _shutil.copytree(s, d, dirs_exist_ok=True)
    else:
        parent = _os.path.dirname(d)
        if parent:
            _os.makedirs(parent, exist_ok=True)
        _shutil.copy2(s, d)
    return d


@omni("move", alias=("rename",))
def _move(interp, src, dst):
    """move("a.txt", "b.txt") -- move or rename."""
    s, d = _path(src), _path(dst)
    parent = _os.path.dirname(d)
    if parent:
        _os.makedirs(parent, exist_ok=True)
    _shutil.move(s, d)
    return d


@omni("list_dir", alias=("dir", "ls"))
def _list_dir(interp, path=".", pattern=None, recursive=False):
    """list_dir(".") -- the names inside a folder."""
    target = _path(path)
    if not _os.path.isdir(target):
        raise OmniRuntimeError(f"`{target}` is not a folder")
    if truthy(recursive):
        names = [f for f in _glob(_os.path.join(target, "**", pattern or "*"),
                                  recursive=True)]
    else:
        names = _glob(_os.path.join(target, pattern or "*"))
    return sorted(names)


@omni("glob", alias=("find_files",))
def _glob_fn(interp, pattern, path="."):
    """glob("**/*.omni") -- every path matching a pattern."""
    return sorted(_glob(_os.path.join(_path(path), to_string(pattern)), recursive=True))


@omni("walk")
def _walk(interp, path=".", files_only=True):
    """walk(".") -- every path under a folder."""
    out = []
    for root, dirs, files in _os.walk(_path(path)):
        if not truthy(files_only):
            out.extend(_os.path.join(root, d) for d in dirs)
        out.extend(_os.path.join(root, f) for f in files)
    return sorted(out)


@omni("file_info", alias=("stat",))
def _file_info(interp, path):
    """file_info("a.txt") -- name, size, modified time and more."""
    target = _path(path)
    if not _os.path.exists(target):
        raise OmniRuntimeError(f"there is nothing at `{target}`")
    st = _os.stat(target)
    base = _os.path.basename(target.rstrip("/\\")) or target
    stem, ext = _os.path.splitext(base)
    return {"path": target, "name": base, "stem": stem, "ext": ext.lstrip("."),
            "size": float(st.st_size), "is_dir": _os.path.isdir(target),
            "modified": st.st_mtime, "modified_text": _time.strftime(
                "%Y-%m-%d %H:%M:%S", _time.localtime(st.st_mtime))}


@omni("file_size")
def _file_size(interp, path):
    """file_size("a.txt") -- size in bytes."""
    return float(_os.path.getsize(_path(path)))


@omni("temp_path")
def _temp_path(interp, prefix="omni-", suffix=""):
    """temp_path(suffix: ".png") -- a fresh path in the temporary folder."""
    import tempfile
    fd, name = tempfile.mkstemp(prefix=to_string(prefix), suffix=to_string(suffix))
    _os.close(fd)
    return name


# ------------------------------------------------------------------- paths
@omni("path_join", alias=("join_path",))
def _path_join(interp, *parts):
    """path_join("a", "b.txt") -- build a path for this operating system."""
    if not parts:
        return ""
    return _os.path.join(*[_path(p) for p in parts])


@omni("path_dir")
def _path_dir(interp, path):
    """path_dir("a/b.txt") -- "a"."""
    return _os.path.dirname(_path(path))


@omni("path_base")
def _path_base(interp, path):
    """path_base("a/b.txt") -- "b.txt"."""
    return _os.path.basename(_path(path))


@omni("path_stem")
def _path_stem(interp, path):
    """path_stem("a/b.txt") -- "b"."""
    return _os.path.splitext(_os.path.basename(_path(path)))[0]


@omni("path_ext")
def _path_ext(interp, path):
    """path_ext("a/b.txt") -- "txt"."""
    return _os.path.splitext(_path(path))[1].lstrip(".")


@omni("path_abs")
def _path_abs(interp, path):
    """path_abs("b.txt") -- the full path."""
    return _os.path.abspath(_path(path))


@omni("path_rel")
def _path_rel(interp, path, start="."):
    """path_rel(full, start) -- the path relative to a folder."""
    return _os.path.relpath(_path(path), _path(start))


@omni("script_dir")
def _script_dir(interp):
    """script_dir() -- the folder holding the running script."""
    return _os.path.dirname(interp.current_file or _os.getcwd())


# --------------------------------------------------------------------- csv
@omni("read_csv")
def _read_csv(interp, path=None, text=None, sep=",", header=True, encoding="utf-8"):
    """read_csv("data.csv") -- a list of maps, one per row.

    Pass `text:` instead of a path to parse CSV you already have in memory.
    """
    if text is None:
        if path is None:
            raise OmniRuntimeError("read_csv() needs a path or `text:`")
        text = _read(interp, path, encoding)
    return parse_csv(to_string(text), to_string(sep), truthy(header))


def parse_csv(text: str, sep: str = ",", header: bool = True) -> list:
    reader = _csv.reader(_io.StringIO(text), delimiter=sep or ",")
    rows = [r for r in reader if r != [] and not (len(r) == 1 and r[0].strip() == "")]
    if not rows:
        return []
    if not header:
        return [[_maybe_num(c) for c in r] for r in rows]
    cols = [c.strip() for c in rows[0]]
    out = []
    for r in rows[1:]:
        item = {}
        for i, c in enumerate(cols):
            item[c] = _maybe_num(r[i]) if i < len(r) else None
        out.append(item)
    return out


def _maybe_num(s: str):
    t = s.strip()
    if not t:
        return ""
    try:
        f = float(t)
    except ValueError:
        return s
    return f


@omni("to_csv")
def _to_csv(interp, rows, columns=None, sep=",", header=True):
    """to_csv(rows) -- turn a list of maps (or lists) into CSV text."""
    return render_csv(rows, columns, to_string(sep), truthy(header))


def render_csv(rows, columns=None, sep=",", header=True) -> str:
    buf = _io.StringIO()
    rows = rows if isinstance(rows, list) else list(rows)
    if not rows:
        return ""
    if isinstance(rows[0], dict):
        cols = [to_string(c) for c in columns] if columns else list(rows[0].keys())
        writer = _csv.writer(buf, delimiter=sep, lineterminator="\n")
        if header:
            writer.writerow(cols)
        for r in rows:
            writer.writerow(["" if r.get(c) is None else _csv_cell(r.get(c)) for c in cols])
    else:
        writer = _csv.writer(buf, delimiter=sep, lineterminator="\n")
        for r in rows:
            writer.writerow([_csv_cell(x) for x in (r if isinstance(r, list) else [r])])
    return buf.getvalue()


def _csv_cell(v) -> str:
    from ..values import to_string as _ts
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return _json.dumps(v)
    return _ts(v)


@omni("write_csv")
def _write_csv(interp, path, rows, columns=None, sep=","):
    """write_csv("out.csv", rows) -- save a list of maps as CSV."""
    return _write(interp, path, render_csv(rows, columns, to_string(sep), True))


# -------------------------------------------------------------------- json
@omni("json")
def _json_parse(interp, text, default=None):
    """json(text) -- parse JSON text into maps and lists."""
    try:
        return _json.loads(to_string(text))
    except _json.JSONDecodeError as e:
        if default is not None:
            return default
        raise OmniRuntimeError(f"this is not valid JSON: {e.msg}",
                               hint=f"the problem starts at character {e.pos}")


@omni("to_json")
def _to_json(interp, value, indent=None, sort_keys=False):
    """to_json(value, indent: 2) -- turn anything into JSON text."""
    from .methods import _plain
    pad = None if indent is None else as_int(indent, "indent")
    return _json.dumps(_plain(value), indent=pad, sort_keys=truthy(sort_keys),
                       ensure_ascii=False, default=to_repr)


@omni("read_json")
def _read_json(interp, path):
    """read_json("config.json") -- parse a JSON file."""
    return _json_parse(interp, _read(interp, path))


@omni("write_json")
def _write_json(interp, path, value, indent=2.0):
    """write_json("out.json", value) -- save anything as JSON."""
    return _write(interp, path, _to_json(interp, value, indent))


# --------------------------------------------------------------- encoding
@omni("base64_encode", alias=("b64",))
def _b64_encode(interp, text):
    """base64_encode("hi") -- encode text."""
    import base64
    return base64.b64encode(to_string(text).encode("utf-8")).decode("ascii")


@omni("base64_decode")
def _b64_decode(interp, text):
    """base64_decode("aGk=") -- decode text."""
    import base64
    return base64.b64decode(to_string(text).strip()).decode("utf-8", errors="replace")


@omni("url_encode")
def _url_encode(interp, text):
    """url_encode("a b&c") -- make text safe for a URL."""
    from urllib.parse import quote
    return quote(to_string(text), safe="")


@omni("url_decode")
def _url_decode(interp, text):
    """url_decode("a%20b") -- undo URL encoding."""
    from urllib.parse import unquote
    return unquote(to_string(text))


@omni("url_parts")
def _url_parts(interp, url):
    """url_parts("https://x.com/a?b=1") -- the pieces of a URL."""
    from urllib.parse import parse_qs, urlparse
    p = urlparse(to_string(url))
    return {"scheme": p.scheme, "host": p.hostname or "", "port": p.port,
            "path": p.path, "query": p.query, "fragment": p.fragment,
            "params": {k: v[0] if len(v) == 1 else v for k, v in parse_qs(p.query).items()}}
