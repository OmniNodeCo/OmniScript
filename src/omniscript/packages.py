"""Useful dependency-free packages shipped with OmniScript."""

from __future__ import annotations

import base64
import csv as csv_library
import datetime as datetime_library
import hashlib
import io
import json
import os
import platform
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .errors import OmniRuntimeError, Span
from .runtime import NativeFunction, OmniModule, stringify


def create_utility_modules() -> dict[str, OmniModule]:
    return {
        "http": OmniModule(
            "http",
            {
                "get": _native("http.get", _http_get, 1, 3),
                "post": _native("http.post", _http_post, 1, 4),
                "json": _native("http.json", _http_json, 1, 3),
            },
        ),
        "csv": OmniModule(
            "csv",
            {
                "parse": _native("csv.parse", _csv_parse, 1, 2),
                "rows": _native("csv.rows", _csv_rows, 1, 2),
                "stringify": _native("csv.stringify", _csv_stringify, 1, 2),
            },
        ),
        "crypto": OmniModule(
            "crypto",
            {
                "sha256": _native("crypto.sha256", _hash("sha256"), 1),
                "sha512": _native("crypto.sha512", _hash("sha512"), 1),
                "base64_encode": _native("crypto.base64_encode", _base64_encode, 1),
                "base64_decode": _native("crypto.base64_decode", _base64_decode, 1),
                "uuid": _native("crypto.uuid", lambda _i, _a, _s: str(uuid.uuid4()), 0),
                "token": _native("crypto.token", _token, 0, 1),
            },
        ),
        "date": OmniModule(
            "date",
            {
                "now": _native("date.now", lambda _i, _a, _s: time.time(), 0),
                "format": _native("date.format", _date_format, 1, 2),
                "parse": _native("date.parse", _date_parse, 1, 2),
                "iso": _native("date.iso", _date_iso, 0, 1),
                "sleep": _native("date.sleep", _sleep, 1),
            },
        ),
        "system": OmniModule(
            "system",
            {
                "info": _native("system.info", _system_info, 0),
                "cwd": _native("system.cwd", lambda _i, _a, _s: str(Path.cwd()), 0),
                "home": _native("system.home", lambda _i, _a, _s: str(Path.home()), 0),
                "env": _native("system.env", _system_env, 1, 2),
                "set_env": _native("system.set_env", _system_set_env, 2),
                "run": _native("system.run", _system_run, 1, 2),
            },
        ),
        "data": OmniModule(
            "data",
            {
                "unique": _native("data.unique", _unique, 1),
                "flatten": _native("data.flatten", _flatten, 1),
                "chunk": _native("data.chunk", _chunk, 2),
                "sum": _native("data.sum", _sum, 1),
                "average": _native("data.average", _average, 1),
            },
        ),
    }


def _native(
    name: str,
    implementation: Callable[[Any, list[Any], Span], Any],
    minimum: int,
    maximum: int | None = None,
) -> NativeFunction:
    return NativeFunction(name, implementation, minimum, minimum if maximum is None else maximum)


def _headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("headers must be a map")
    return {stringify(key): stringify(item) for key, item in value.items()}


def _timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise TypeError("timeout must be a positive number")
    return float(value)


def _http_request(method: str, url: Any, body: Any, headers: Any, timeout: Any, span: Span) -> dict[str, Any]:
    address = stringify(url)
    if not address.startswith(("http://", "https://")):
        raise OmniRuntimeError("HTTP URL must start with http:// or https://", span)
    request_headers = _headers(headers)
    payload: bytes | None = None
    if body is not None:
        if isinstance(body, (dict, list)):
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        else:
            payload = stringify(body).encode("utf-8")
    request = Request(address, data=payload, headers=request_headers, method=method)
    try:
        response = urlopen(request, timeout=_timeout(timeout))
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        content_type = str(response.headers.get("Content-Type", ""))
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            text = raw.decode("utf-8", errors="replace")
        return {
            "status": int(response.status),
            "ok": 200 <= int(response.status) < 300,
            "body": text,
            "headers": {str(key).lower(): str(value) for key, value in response.headers.items()},
            "content_type": content_type,
        }


def _http_get(_interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
    headers = arguments[1] if len(arguments) >= 2 else {}
    timeout = arguments[2] if len(arguments) >= 3 else 15
    return _http_request("GET", arguments[0], None, headers, timeout, span)


def _http_post(_interpreter: Any, arguments: list[Any], span: Span) -> dict[str, Any]:
    body = arguments[1] if len(arguments) >= 2 else ""
    headers = arguments[2] if len(arguments) >= 3 else {}
    timeout = arguments[3] if len(arguments) >= 4 else 15
    return _http_request("POST", arguments[0], body, headers, timeout, span)


def _http_json(_interpreter: Any, arguments: list[Any], span: Span) -> Any:
    response = _http_get(_interpreter, arguments, span)
    try:
        return json.loads(response["body"])
    except json.JSONDecodeError as error:
        raise OmniRuntimeError(f"HTTP response was not valid JSON: {error}", span) from error


def _delimiter(arguments: list[Any]) -> str:
    delimiter = stringify(arguments[1]) if len(arguments) == 2 else ","
    if len(delimiter) != 1:
        raise ValueError("CSV delimiter must be one character")
    return delimiter


def _csv_rows(_interpreter: Any, arguments: list[Any], _span: Span) -> list[list[str]]:
    return [list(row) for row in csv_library.reader(io.StringIO(stringify(arguments[0])), delimiter=_delimiter(arguments))]


def _csv_parse(_interpreter: Any, arguments: list[Any], _span: Span) -> list[dict[str, str]]:
    reader = csv_library.DictReader(io.StringIO(stringify(arguments[0])), delimiter=_delimiter(arguments))
    return [{str(key): value for key, value in row.items()} for row in reader]


def _csv_stringify(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    rows = arguments[0]
    if not isinstance(rows, list):
        raise TypeError("csv.stringify expects a list of rows")
    output = io.StringIO(newline="")
    delimiter = _delimiter(arguments)
    if rows and isinstance(rows[0], dict):
        fields: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("CSV rows must all be maps or all be lists")
            for key in row:
                name = stringify(key)
                if name not in fields:
                    fields.append(name)
        writer = csv_library.DictWriter(output, fieldnames=fields, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({stringify(key): stringify(value) for key, value in row.items()})
    else:
        writer = csv_library.writer(output, delimiter=delimiter, lineterminator="\n")
        for row in rows:
            if not isinstance(row, list):
                raise TypeError("CSV rows must all be maps or all be lists")
            writer.writerow([stringify(value) for value in row])
    return output.getvalue()


def _hash(algorithm: str) -> Callable[[Any, list[Any], Span], str]:
    return lambda _i, arguments, _s: hashlib.new(algorithm, stringify(arguments[0]).encode("utf-8")).hexdigest()


def _base64_encode(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    return base64.b64encode(stringify(arguments[0]).encode("utf-8")).decode("ascii")


def _base64_decode(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    return base64.b64decode(stringify(arguments[0]), validate=True).decode("utf-8")


def _token(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    value = arguments[0] if arguments else 32
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise TypeError("token length must be a whole number")
    length = int(value)
    if not 1 <= length <= 1024:
        raise ValueError("token length must be between 1 and 1024")
    return secrets.token_urlsafe(length)[:length]


def _date_format(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    pattern = stringify(arguments[1]) if len(arguments) == 2 else "%Y-%m-%d %H:%M:%S"
    return datetime_library.datetime.fromtimestamp(float(arguments[0])).strftime(pattern)


def _date_parse(_interpreter: Any, arguments: list[Any], _span: Span) -> float:
    pattern = stringify(arguments[1]) if len(arguments) == 2 else "%Y-%m-%d %H:%M:%S"
    return datetime_library.datetime.strptime(stringify(arguments[0]), pattern).timestamp()


def _date_iso(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    timestamp = float(arguments[0]) if arguments else time.time()
    return datetime_library.datetime.fromtimestamp(timestamp, datetime_library.timezone.utc).isoformat()


def _sleep(_interpreter: Any, arguments: list[Any], _span: Span) -> None:
    seconds = float(arguments[0])
    if seconds < 0 or seconds > 86_400:
        raise ValueError("sleep duration must be between 0 and 86400 seconds")
    time.sleep(seconds)
    return None


def _system_info(_interpreter: Any, _arguments: list[Any], _span: Span) -> dict[str, str]:
    return {
        "os": platform.system().lower(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "executable": sys.executable,
    }


def _system_env(_interpreter: Any, arguments: list[Any], _span: Span) -> Any:
    default = arguments[1] if len(arguments) == 2 else None
    return os.environ.get(stringify(arguments[0]), default)


def _system_set_env(_interpreter: Any, arguments: list[Any], _span: Span) -> str:
    name, value = stringify(arguments[0]), stringify(arguments[1])
    os.environ[name] = value
    return value


def _system_run(_interpreter: Any, arguments: list[Any], _span: Span) -> dict[str, Any]:
    command = arguments[0]
    if not isinstance(command, list) or not command:
        raise TypeError("system.run expects a non-empty list such as ['git', '--version']")
    timeout = _timeout(arguments[1]) if len(arguments) == 2 else 30.0
    try:
        result = subprocess.run(
            [stringify(item) for item in command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"command timed out after {timeout:g} seconds") from error
    return {
        "code": result.returncode,
        "ok": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr,
    }


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"data.{name} expects a list")
    return value


def _unique(_interpreter: Any, arguments: list[Any], _span: Span) -> list[Any]:
    result: list[Any] = []
    for value in _require_list(arguments[0], "unique"):
        if value not in result:
            result.append(value)
    return result


def _flatten_values(values: list[Any], result: list[Any]) -> None:
    for value in values:
        if isinstance(value, list):
            _flatten_values(value, result)
        else:
            result.append(value)


def _flatten(_interpreter: Any, arguments: list[Any], _span: Span) -> list[Any]:
    result: list[Any] = []
    _flatten_values(_require_list(arguments[0], "flatten"), result)
    return result


def _chunk(_interpreter: Any, arguments: list[Any], _span: Span) -> list[list[Any]]:
    values = _require_list(arguments[0], "chunk")
    size = int(arguments[1])
    if isinstance(arguments[1], bool) or size != arguments[1] or size < 1:
        raise ValueError("chunk size must be a positive whole number")
    return [values[index : index + size] for index in range(0, len(values), size)]


def _sum(_interpreter: Any, arguments: list[Any], _span: Span) -> int | float:
    values = _require_list(arguments[0], "sum")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise TypeError("data.sum accepts only numbers")
    return sum(values)


def _average(_interpreter: Any, arguments: list[Any], _span: Span) -> float | None:
    values = _require_list(arguments[0], "average")
    if not values:
        return None
    return float(_sum(_interpreter, arguments, _span)) / len(values)
