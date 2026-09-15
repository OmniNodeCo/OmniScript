"""Tests for the command line itself: `omni run`, `-e`, `docs`, `test`, `repl`.

These drive the real binary through a subprocess, so a broken launcher or a bad
exit code shows up here rather than in a user's terminal.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OMNI = os.path.join(ROOT, "omni")


def run_cli(*args, expect_code=None, timeout=120):
    proc = subprocess.run([sys.executable, OMNI, *args],
                          capture_output=True, text=True, cwd=ROOT, timeout=timeout)
    if expect_code is not None:
        assert proc.returncode == expect_code, \
            f"`omni {' '.join(args)}` exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc


class CommandLineTests(unittest.TestCase):
    def test_version(self):
        out = run_cli("--version", expect_code=0).stdout
        self.assertIn("OmniScript", out)

    def test_inline_code(self):
        proc = run_cli("-e", "print(2 ** 10)", expect_code=0)
        self.assertEqual(proc.stdout.strip(), "1024")

    def test_run_a_file(self):
        proc = run_cli("run", "examples/01_hello.omni", expect_code=0)
        self.assertIn("Hello, OmniScript!", proc.stdout)

    def test_a_bare_filename_also_runs(self):
        proc = run_cli("examples/01_hello.omni", expect_code=0)
        self.assertIn("Hello, OmniScript!", proc.stdout)

    def test_missing_file_exits_nonzero(self):
        proc = run_cli("no_such_file.omni")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot find", (proc.stdout + proc.stderr).lower())

    def test_syntax_error_exits_nonzero_and_points_at_the_line(self):
        proc = run_cli("-e", "let = 5")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("syntax error", proc.stderr)
        self.assertIn("-->", proc.stderr)

    def test_runtime_error_shows_a_hint(self):
        proc = run_cli("-e", "print(nmae)")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("name error", proc.stderr)
        self.assertIn("did you mean", proc.stderr)

    def test_check_passes_and_fails(self):
        proc = run_cli("check", "examples/01_hello.omni", expect_code=0)
        self.assertIn("syntax is fine", proc.stdout)
        self.assertNotEqual(run_cli("check", "-e", "fn (").returncode, 0)

    def test_tokens_and_ast_accept_inline_code(self):
        toks = run_cli("tokens", "-e", "1..3", expect_code=0).stdout
        self.assertIn("NUM", toks)
        self.assertIn("DOT", toks)
        tree = run_cli("ast", "-e", "let x = 1 + 2", expect_code=0).stdout
        self.assertIn("Let(", tree)
        self.assertIn("Binary(", tree)

    def test_docs_lists_and_explains(self):
        listing = run_cli("docs", expect_code=0).stdout
        self.assertIn("built-in functions", listing)
        self.assertIn("chart", listing)
        detail = run_cli("docs", "chart", expect_code=0).stdout
        self.assertIn("chart(", detail)

    def test_test_runner_reports_counts(self):
        proc = run_cli("test", "tests/core_test.omni", expect_code=0)
        self.assertIn("passed", proc.stdout)
        self.assertIn("0 failed", proc.stdout)

    def test_test_runner_fails_on_a_failing_test(self):
        with open(os.path.join(ROOT, ".preview_fail.omni"), "w") as fh:
            fh.write("@test\nfn wrong() { assert_eq(1, 2) }\n")
        try:
            proc = run_cli("test", ".preview_fail.omni")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("FAIL wrong", proc.stdout)
        finally:
            os.remove(os.path.join(ROOT, ".preview_fail.omni"))

    def test_script_arguments_reach_the_program(self):
        proc = run_cli("-e", "print(args().len(), arg(0), arg(1))", "a", "b",
                       expect_code=0)
        self.assertEqual(proc.stdout.strip(), "2 a b")

    def test_repl_runs_a_session_from_stdin(self):
        proc = subprocess.run([sys.executable, OMNI, "repl"],
                              input="let x = 40\nx + 2\n:vars\n:quit\n",
                              capture_output=True, text=True, cwd=ROOT, timeout=60)
        self.assertIn("42", proc.stdout)
        self.assertIn("x = 40", proc.stdout)   # `x + 2` printed 42 without changing x

    def test_examples_all_run(self):
        import tempfile
        folder = os.path.join(ROOT, "examples")
        with tempfile.TemporaryDirectory() as scratch:
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".omni"):
                    continue
                with self.subTest(example=name):
                    proc = subprocess.run([sys.executable, OMNI,
                                           os.path.join(folder, name)],
                                          capture_output=True, text=True,
                                          cwd=scratch, timeout=180)
                    self.assertEqual(proc.returncode, 0, proc.stderr[-800:])


class CompleterTests(unittest.TestCase):
    def test_member_completion_uses_the_method_table(self):
        sys.path.insert(0, ROOT)
        from omniscript import cli
        from omniscript.interp import Interpreter
        interp = Interpreter(writer=lambda *_: None, root=ROOT, quiet=True)
        interp.load_builtins()
        names = cli._member_candidates(interp, '"hello"', "")
        self.assertIn("upper", names)
        self.assertIn("split", names)
        names = cli._member_candidates(interp, "{a: 1}", "")
        self.assertIn("keys", names)
        self.assertIn("a", names)
        self.assertEqual(cli._member_candidates(interp, "nope_nope", ""), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
