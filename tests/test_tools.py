from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from omniscript.cli import main
from omniscript.formatter import format_source


class ToolTests(unittest.TestCase):
    def test_formatter_preserves_comments_and_indents_blocks(self) -> None:
        source = 'when true {\nemit "{" // brace in text\nwhen true {\nemit "yes"\n}\n}\n'
        expected = 'when true {\n    emit "{" // brace in text\n    when true {\n        emit "yes"\n    }\n}\n'
        self.assertEqual(format_source(source), expected)

    def test_cli_run_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hello.omni"
            path.write_text('emit "hello"\n', encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(main(["run", str(path)]), 0)
                self.assertEqual(main(["check", str(path)]), 0)
            self.assertIn("hello", stdout.getvalue())
            self.assertIn("ok", stdout.getvalue())

    def test_cli_init_creates_runnable_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            old = Path.cwd()
            os.chdir(temporary)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["init", "demo"]), 0)
                    os.chdir("demo")
                    self.assertEqual(main(["run"]), 0)
                    self.assertEqual(main(["test"]), 0)
                self.assertTrue(Path("omni.toml").exists())
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
