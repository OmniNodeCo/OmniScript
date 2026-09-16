#!/usr/bin/env python3
"""Run the test suites, and in CI turn every failure into a workflow annotation.

    python3 tools/ci_unittest.py discover -s tests
    python3 tools/ci_unittest.py tests.test_install

A red job in GitHub Actions is only as useful as the part of the log you can
see, and a log is a wall of text. This runs unittest the normal way, prints
everything it printed, and then adds one annotation per failure pointing at the
file and line the assertion died on -- so `gh api .../annotations` is enough to
know what broke, without the log.

Outside CI it is just unittest with a nicer exit message.
"""

from __future__ import annotations

import io
import os
import re
import sys
import unittest

IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))
ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
FILE_LINE = re.compile(r'^\s*File "([^"]+)", line (\d+)', re.MULTILINE)

# Run as a script, sys.path[0] is tools/ -- the suites live one level up.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def annotate(message: str, path: str = "", line: int = 0) -> None:
    if not IN_CI:
        return
    flat = " | ".join(part.strip() for part in message.splitlines() if part.strip())
    flat = flat.replace("\r", "")[:1800]
    where = f" file={path},line={line}" if path and line else ""
    print(f"::error{where}::{flat}", flush=True)


def build_suite(argv: list[str]) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    if argv and argv[0] == "discover":
        start, pattern, top = "tests", "test*.py", None
        rest = argv[1:]
        while rest:
            flag, rest = rest[0], rest[1:]
            if flag in ("-s", "--start-directory") and rest:
                start, rest = rest[0], rest[1:]
            elif flag in ("-p", "--pattern") and rest:
                pattern, rest = rest[0], rest[1:]
            elif flag in ("-t", "--top-level-directory") and rest:
                top, rest = rest[0], rest[1:]
        return loader.discover(start, pattern=pattern, top_level_dir=top)
    return loader.loadTestsFromNames(argv or ["tests"])


def where_it_hurt(traceback_text: str) -> tuple[str, int]:
    """The deepest frame in this repository: where the assertion actually died."""
    root = ROOT
    candidates = [(path, int(number)) for path, number in FILE_LINE.findall(traceback_text)]
    for path, number in reversed(candidates):
        absolute = os.path.abspath(path)
        if absolute.startswith(root) and "tools" + os.sep not in absolute:
            return os.path.relpath(absolute, root).replace(os.sep, "/"), number
    return (candidates[-1][0], int(candidates[-1][1])) if candidates else ("", 0)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(build_suite(argv))

    report = stream.getvalue()
    sys.stdout.write(report)
    sys.stdout.flush()

    failures = list(result.failures) + list(result.errors)
    for test, traceback_text in failures:
        path, line = where_it_hurt(traceback_text)
        reason = [ln for ln in traceback_text.strip().splitlines() if ln.strip()]
        last = reason[-1] if reason else "failed"
        headline = reason[-2] if len(reason) > 1 and reason[-2].strip() else ""
        detail = "\n".join(part for part in (headline, last) if part)
        annotate(f"{test}: {detail}", path, line)

    if result.skipped:
        print(f"{len(result.skipped)} test(s) skipped here:", flush=True)
        for test, why in result.skipped:
            print(f"    {test}  --  {why}", flush=True)

    if failures:
        annotate(f"{len(failures)} of {result.testsRun} tests failed")
        print(f"{len(failures)} of {result.testsRun} tests failed", file=sys.stderr)
        return 1
    print(f"all {result.testsRun} tests passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
