"""OmniScript network and text-matching built-ins.

    http_get("https://api.example.com/users").json()
    "2026-09-15".match(r"(\\d+)-(\\d+)-(\\d+)")
"""

from __future__ import annotations

import json as _json
import re as _re
import socket as _socket
import time as _time
import urllib.error as _uerr
import urllib.parse as _uparse
import urllib.request as _ureq

from ..errors import OmniRuntimeError, OmniTypeError
from ..values import HostObject, NativeFunction, collect_signature, to_string, truthy
from .core import as_int, as_num, omni

# ------------------------------------------------------------------- http
RESPONSE_METHODS: dict[str, NativeFunction] = {}


def _resp_method(fn):
    RESPONSE_METHODS[fn.__name__] = collect_signature(fn, fn.__name__,
                                                      (fn.__doc__ or "").strip(),
                                                      takes_interp=False)
    return fn


@_resp_method
def json(self):
    """the body parsed as JSON"""
    text = self.fields["text"]
    try:
        return _json.loads(text)
    except _json.JSONDecodeError as e:
        raise OmniRuntimeError(f"the response from `{self.fields['url']}` is not JSON: {e.msg}",
                               hint=text[:200] if text else "the body is empty")


@_resp_method
def lines(self):
    """the body split into lines"""
    return self.fields["text"].splitlines()


@_resp_method
def words(self):
    """the body split on whitespace"""
    return self.fields["text"].split()


@_resp_method
def trim(self):
    """the body with surrounding whitespace removed"""
    return self.fields["text"].strip()


@_resp_method
def num(self):
    """the body parsed as a number"""
    try:
        return float(self.fields["text"].strip())
    except ValueError:
        raise OmniRuntimeError(f"the response from `{self.fields['url']}` is not a number")


@_resp_method
def save(self, path):
    """write the body to a file"""
    with open(to_string(path), "wb") as fh:
        fh.write(self.data)
    return to_string(path)


@_resp_method
def header(self, name, default=None):
    """read one response header"""
    return self.fields["headers"].get(to_string(name).lower(), default)


@_resp_method
def check(self, message=None):
    """raise unless the status is 2xx"""
    if not self.fields["ok"]:
        raise OmniRuntimeError(
            to_string(message) if message else
            f"`{self.fields['url']}` replied {int(self.fields['status'])}",
            hint=self.fields["text"][:300] or None)
    return self


def make_response(url: str, status: int, body: bytes, headers: dict,
                  seconds: float, method: str) -> HostObject:
    text = body.decode("utf-8", errors="replace")
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    return HostObject(
        "Response",
        methods=dict(RESPONSE_METHODS),
        fields={"url": url, "status": float(status), "ok": 200 <= status < 300,
                "text": text, "headers": lower, "seconds": seconds, "method": method,
                "length": float(len(body))},
        data=body,
        display=lambda o: f"<Response {int(o.fields['status'])} {o.fields['url']}>",
    )


def _request(interp, url, method="GET", data=None, json_body=None, headers=None,
             params=None, timeout=30.0, form=None):
    target = to_string(url)
    if params:
        if not isinstance(params, dict):
            raise OmniTypeError("`params:` must be a map")
        query = _uparse.urlencode({str(k): _qs(v) for k, v in params.items()})
        target += ("&" if "?" in target else "?") + query

    hdrs = {"User-Agent": "OmniScript/1.0"}
    if isinstance(headers, dict):
        hdrs.update({str(k): to_string(v) for k, v in headers.items()})

    body = None
    if json_body is not None:
        from .methods import _plain
        body = _json.dumps(_plain(json_body)).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    elif form is not None:
        if not isinstance(form, dict):
            raise OmniTypeError("`form:` must be a map")
        body = _uparse.urlencode({str(k): _qs(v) for k, v in form.items()}).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif data is not None:
        body = to_string(data).encode("utf-8")

    req = _ureq.Request(target, data=body, headers=hdrs, method=to_string(method).upper())
    limit = as_num(timeout, "timeout")
    start = _time.time()
    try:
        with _ureq.urlopen(req, timeout=limit) as resp:
            payload = resp.read()
            return make_response(resp.geturl(), resp.status, payload,
                                 dict(resp.headers), _time.time() - start,
                                 to_string(method).upper())
    except _uerr.HTTPError as e:
        payload = e.read() if e.fp else b""
        return make_response(target, e.code, payload, dict(e.headers or {}),
                             _time.time() - start, to_string(method).upper())
    except _uerr.URLError as e:
        raise OmniRuntimeError(f"could not reach `{target}`: {e.reason}",
                               hint="check the address, your connection, or a proxy")
    except _socket.timeout:
        raise OmniRuntimeError(f"`{target}` did not answer within {limit} seconds",
                               hint="pass a bigger `timeout:`")
    except OSError as e:
        raise OmniRuntimeError(f"network failure talking to `{target}`: {e}")


def _qs(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (list, dict)):
        return _json.dumps(v)
    return to_string(v)


@omni("http", alias=("request",))
def _http(interp, url, method="GET", data=None, json=None, headers=None, params=None,
          timeout=30.0, form=None):
    """http(url, method: "POST", json: {...}) -- make any HTTP request."""
    return _request(interp, url, method, data, json, headers, params, timeout, form)


@omni("http_get", alias=("get", "fetch"))
def _http_get(interp, url, headers=None, params=None, timeout=30.0):
    """http_get(url) -- download something."""
    return _request(interp, url, "GET", None, None, headers, params, timeout)


@omni("http_post", alias=("post",))
def _http_post(interp, url, data=None, json=None, headers=None, params=None,
               timeout=30.0, form=None):
    """http_post(url, json: {...}) -- send something."""
    return _request(interp, url, "POST", data, json, headers, params, timeout, form)


@omni("http_put", alias=("put",))
def _http_put(interp, url, data=None, json=None, headers=None, timeout=30.0):
    """http_put(url, json: {...}) -- replace something."""
    return _request(interp, url, "PUT", data, json, headers, None, timeout)


@omni("http_patch", alias=("patch",))
def _http_patch(interp, url, data=None, json=None, headers=None, timeout=30.0):
    """http_patch(url, json: {...}) -- partially update something."""
    return _request(interp, url, "PATCH", data, json, headers, None, timeout)


@omni("http_delete", alias=("delete",))
def _http_delete(interp, url, headers=None, timeout=30.0):
    """http_delete(url) -- remove something."""
    return _request(interp, url, "DELETE", None, None, headers, None, timeout)


@omni("download")
def _download(interp, url, path=None, headers=None, timeout=60.0):
    """download(url, "file.png") -- fetch a URL and save the bytes."""
    resp = _request(interp, url, "GET", None, None, headers, None, timeout)
    if path is None:
        name = _uparse.urlparse(resp.fields["url"]).path.rsplit("/", 1)[-1] or "download"
        path = name
    with open(to_string(path), "wb") as fh:
        fh.write(resp.data)
    return to_string(path)


@omni("ping")
def _ping(interp, host, port=80.0, timeout=3.0):
    """ping("example.com", 443) -- can we open a socket there?"""
    try:
        with _socket.create_connection((to_string(host), as_int(port, "port")),
                                       timeout=as_num(timeout, "timeout")):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------ regex
@omni("regex")
def _regex(interp, text, pattern, default=None):
    """regex(text, r"(\\w+)@(\\w+)") -- the first match as a list of groups."""
    m = _re.search(to_string(pattern), to_string(text))
    if m is None:
        return default
    return [m.group(0)] + [g if g is not None else "" for g in m.groups()]


@omni("regex_named")
def _regex_named(interp, text, pattern):
    """regex_named(text, r"(?P<year>\\d+)") -- named groups as a map."""
    m = _re.search(to_string(pattern), to_string(text))
    if m is None:
        return None
    return {k: (v if v is not None else "") for k, v in m.groupdict().items()}


@omni("regex_all")
def _regex_all(interp, text, pattern, groups=False):
    """regex_all(text, r"\\d+") -- every match."""
    out = []
    for m in _re.finditer(to_string(pattern), to_string(text)):
        if truthy(groups):
            out.append([g if g is not None else "" for g in m.groups()])
        else:
            out.append(m.group(0))
    return out


@omni("regex_test", alias=("matches_re",))
def _regex_test(interp, text, pattern):
    """regex_test(text, r"^\\d+$") -- does it match?"""
    return _re.search(to_string(pattern), to_string(text)) is not None


@omni("regex_replace")
def _regex_replace(interp, text, pattern, replacement, count=0.0):
    """regex_replace(text, r"\\s+", " ") -- swap every match."""
    return _re.sub(to_string(pattern), to_string(replacement), to_string(text),
                   count=as_int(count, "count"))


@omni("regex_split")
def _regex_split(interp, text, pattern, limit=0.0):
    """regex_split(text, r"[,;]\\s*") -- cut on a pattern."""
    return _re.split(to_string(pattern), to_string(text),
                     maxsplit=max(0, as_int(limit, "limit")))


@omni("regex_escape")
def _regex_escape(interp, text):
    """regex_escape("a.b") -- make text safe to use inside a pattern."""
    return _re.escape(to_string(text))
