"""OmniScript concurrency: run many things at once without any ceremony.

    parallel_map(urls, (u) -> http_get(u).text, workers: 8)
    let results = parallel([task_a, task_b, task_c])
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from ..errors import OmniError, OmniRuntimeError, OmniTypeError
from ..values import HostObject, NativeFunction, collect_signature, to_string, truthy
from .core import as_int, is_callable, omni


def _check_callable(v, who):
    if not (is_callable(v) or hasattr(v, "fn")):
        raise OmniTypeError(f"{who} must be a function, got {to_string(v)}",
                            hint="lambdas look like `() -> work()`")


def _call(interp, fn, args):
    return interp.call_loose(fn, list(args), {}, node=None)


def _guard(interp, fn, args):
    """Run one task, converting any failure into a value instead of a crash."""
    try:
        return {"ok": True, "value": _call(interp, fn, args), "error": None}
    except OmniError as e:
        return {"ok": False, "value": None, "error": e.message}
    except SystemExit:
        raise
    except Exception as e:                     # noqa: BLE001 - host failures are user data
        return {"ok": False, "value": None, "error": f"{type(e).__name__}: {e}"}


@omni("parallel", alias=("concurrently",))
def _parallel(interp, tasks, workers=4.0, fail_fast=False):
    """parallel([taskA, taskB]) -- run functions at the same time.

    Each task is a function taking no arguments. Results come back in the same
    order you passed them, whatever order they finished in.
    """
    items = interp.iterate(tasks)
    if not items:
        return []
    for t in items:
        _check_callable(t, "every parallel task")
    n = max(1, min(256, as_int(workers, "workers")))
    with ThreadPoolExecutor(max_workers=n) as pool:
        outcomes = list(pool.map(lambda t: _guard(interp, t, []), items))
    if truthy(fail_fast):
        for o in outcomes:
            if not o["ok"]:
                raise OmniRuntimeError(f"a parallel task failed: {o['error']}")
    return [o["value"] if o["ok"] else o for o in outcomes]


@omni("parallel_map", alias=("pmap",))
def _parallel_map(interp, items, fn, workers=4.0):
    """parallel_map(urls, (u) -> http_get(u).text) -- map across many threads."""
    _check_callable(fn, "the function")
    pool_items = interp.iterate(items)
    if not pool_items:
        return []
    n = max(1, min(256, as_int(workers, "workers")))
    with ThreadPoolExecutor(max_workers=n) as pool:
        outcomes = list(pool.map(
            lambda pair: _guard(interp, fn, [pair[1], float(pair[0])]),
            enumerate(pool_items)))
    failed = [o for o in outcomes if not o["ok"]]
    if failed:
        raise OmniRuntimeError(f"{len(failed)} of {len(outcomes)} parallel tasks failed: "
                               f"{failed[0]['error']}",
                               hint="pass a smaller `workers:` count, or use "
                                    "`parallel()` to collect failures instead of raising")
    return [o["value"] for o in outcomes]


@omni("spawn", alias=("thread",))
def _spawn(interp, fn, *args):
    """spawn(() -> work()) -- start something in the background, get a handle.

    The handle has `.done()`, `.get()` and `.result`.
    """
    _check_callable(fn, "spawn")
    box: dict = {"done": False, "value": None, "error": None}
    lock = threading.Lock()

    def runner():
        outcome = _guard(interp, fn, list(args))
        with lock:
            box["done"] = True
            box["value"] = outcome["value"]
            box["error"] = outcome["error"]

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    def done(interp_):
        with lock:
            return box["done"]

    def get(interp_, timeout=None):
        t.join(None if timeout is None else max(0.0, float(timeout)))
        with lock:
            if not box["done"]:
                raise OmniRuntimeError("the spawned task has not finished yet")
            if box["error"] is not None:
                raise OmniRuntimeError(f"the spawned task failed: {box['error']}")
            return box["value"]

    def join(interp_, timeout=None):
        return get(interp_, timeout)

    handle = HostObject(
        "Task",
        methods={"done": collect_signature(done, "done", "is the task finished?",
                                           takes_interp=False),
                 "get": collect_signature(get, "get", "wait for and return the result",
                                          takes_interp=False),
                 "join": collect_signature(join, "join", "wait for the task to finish",
                                           takes_interp=False)},
        display=lambda o: "<Task done>" if box["done"] else "<Task running>",
        data=box,
    )
    handle.fields["thread"] = None
    return handle


@omni("http_get_all", alias=("fetch_all",))
def _http_get_all(interp, urls, workers=6.0, timeout=30.0):
    """http_get_all(urls) -- download many URLs at once, in order."""
    from .net import _request
    targets = [to_string(u) for u in interp.iterate(urls)]
    if not targets:
        return []
    n = max(1, min(64, as_int(workers, "workers")))

    def one(url):
        try:
            return _request(interp, url, "GET", None, None, None, None, timeout)
        except OmniError as e:
            return {"url": url, "ok": False, "error": e.message}

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(one, targets))


@omni("repeat_for")
def _repeat_for(interp, seconds, fn):
    """repeat_for(2, () -> tick()) -- call a function until time runs out."""
    import time
    _check_callable(fn, "the function")
    deadline = time.time() + max(0.0, float(seconds))
    count = 0.0
    while time.time() < deadline:
        _call(interp, fn, [count])
        count += 1
    return count
