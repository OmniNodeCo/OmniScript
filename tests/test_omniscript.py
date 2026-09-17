"""The tests for the whole language: four commands, the CLI, and the installer.

Run them the way CI does:

    python -m unittest discover -s tests
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "omni"
BASH = shutil.which("bash")
PWSH = shutil.which("pwsh")
POSIX = os.name != "nt"


def run_omni(*args, cwd=None, expect=None):
    """Run ./omni through this Python, and check the exit code if asked to."""
    proc = subprocess.run([sys.executable, str(LAUNCHER), *args],
                          capture_output=True, text=True, timeout=300,
                          cwd=str(cwd or "."))
    if expect is not None:
        case = f"{' '.join(args)} exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        assert proc.returncode == expect, case
    return proc


class OmniCase(unittest.TestCase):
    """A temp directory to work in, and a way to run OmniScript in it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="omni-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def omni(self, code, expect=None):
        return run_omni("-e", code, cwd=self.tmp, expect=expect)

    def out(self, code):
        return self.omni(code, expect=0).stdout

    def exists(self, name):
        return (self.tmp / name).exists()


# ------------------------------------------------------------------- the language
class LanguageTests(OmniCase):
    def test_the_version_is_the_one_the_package_says(self):
        import omniscript
        self.assertEqual(f"OmniScript {omniscript.VERSION}",
                         run_omni("--version").stdout.strip())

    def test_a_bare_word_reaches_a_command_as_its_own_name(self):
        self.assertIn("created word.txt", self.out('file(create, word.txt, "x")'))
        self.assertIn("deleted word.txt", self.out('file(delete, word.txt)'))

    def test_comments_and_blank_lines_are_ignored(self):
        self.assertIn("hello", self.out('# a note\n\n   # another\ncmd("echo hello")\n'))

    def test_a_call_may_span_lines(self):
        self.assertIn("hello", self.out('cmd(\n  "echo hello"\n)'))

    def test_an_unknown_command_is_refused_with_the_list_of_commands(self):
        err = self.omni("bake(a, b)", expect=1).stderr
        self.assertIn("there is no command called bake", err)
        for command in ("draw", "draw_gui", "draw_gui.button",
                        "draw_gui.window_size", "cmd", "file", "python"):
            self.assertIn(command, err)
        self.assertIn("^", err)

    def test_an_unknown_draw_gui_subcommand_is_refused(self):
        err = self.omni("draw_gui.frobnicate(1)", expect=1).stderr
        self.assertIn("draw_gui has no '.frobnicate'", err)
        self.assertIn(".button", err)
        self.assertIn(".window_size", err)

    def test_an_element_outside_draw_is_refused(self):
        self.assertIn("only belongs inside draw()",
                      self.omni('rect(0, 0, 4, 4, red)', expect=1).stderr)

    def test_an_unclosed_call_is_reported(self):
        err = self.omni('cmd("echo hi"', expect=1).stderr
        self.assertIn("never closed", err)

    def test_an_unterminated_string_is_reported(self):
        self.assertIn("no closing quote", self.omni('cmd("echo hi)', expect=1).stderr)

    def test_a_character_that_is_not_omniscript_is_reported(self):
        err = self.omni("cmd(\"echo hi\") ;", expect=1).stderr
        self.assertIn("cannot read ';'", err)

    def test_imports_work_like_python(self):
        self.assertEqual("2\n", self.out('import math\npython("math.floor(2.9)")'))

    def test_import_as_binds_the_alias(self):
        self.assertEqual("3\n", self.out('import math as m\npython("m.ceil(2.1)")'))

    def test_from_imports_bind_names(self):
        self.assertEqual("4.0\n",
                         self.out('from math import sqrt\npython("sqrt(16)")'))

    def test_from_import_star_binds_public_names(self):
        self.assertEqual("3\n", self.out(
            'from math import *\npython("floor(3.7)")'))

    def test_an_import_that_does_not_exist_is_refused(self):
        err = self.omni("import no_such_module_xyz", expect=1).stderr
        self.assertIn("could not import 'no_such_module_xyz'", err)

    def test_a_from_import_of_nothing_is_refused(self):
        err = self.omni("from math import no_such_name_xyz", expect=1).stderr
        self.assertIn("'math' has no 'no_such_name_xyz' to import", err)

    def test_from_needs_import_after_it(self):
        err = self.omni("from math sqrt", expect=1).stderr
        self.assertIn("expected 'import' after 'from math'", err)

    def test_keyword_arguments_and_pairs(self):
        out = self.out('draw(window(20, 10, "t"), rect(pos=(1, 1), size=(4, 4)), '
                       'save("k.png"))')
        self.assertIn("wrote k.png (20x10)", out)
        self.assertTrue((self.tmp / "k.png").is_file())

    def test_a_positional_after_a_keyword_is_refused(self):
        self.assertIn("a positional argument after a keyword one",
                      self.omni("draw(rect(x=1, 2))", expect=1).stderr)

    def test_a_repeated_keyword_is_refused(self):
        self.assertIn("got 'x=' twice",
                      self.omni("draw(rect(x=1, x=2))", expect=1).stderr)

    def test_an_unknown_keyword_is_refused_with_what_there_is(self):
        err = self.omni('draw(save(foo="x"))', expect=1).stderr
        self.assertIn("save() has no 'foo='", err)
        self.assertIn("path", err)

    def test_strings_unescape(self):
        self.assertIn("a\nb", self.out('cmd("printf \'a\\\\nb\'")'))


# ------------------------------------------------------------------------ cmd
class CmdTests(OmniCase):
    def test_a_command_runs_and_its_output_is_printed(self):
        self.assertIn("hello world", self.out('cmd("echo hello world")'))

    def test_a_command_that_fails_says_so(self):
        self.assertIn("exited 3", self.out('cmd("exit 3")'))

    def test_an_empty_command_is_refused(self):
        self.assertIn("empty command", self.omni('cmd("")', expect=1).stderr)

    def test_cmd_with_nothing_at_all_is_refused(self):
        self.assertIn("needs a command", self.omni("cmd()", expect=1).stderr)

    def test_a_background_command_does_not_wait(self):
        waiter = "sleep 5" if POSIX else "timeout /t 5"
        out = self.out(f'cmd(background, "{waiter}")')
        self.assertIn("running in the background", out)
        self.assertIn("pid", out)

    def test_a_command_runs_in_the_directory_of_the_program(self):
        (self.tmp / "here.txt").write_text("found\n")
        self.assertIn("found", self.out('cmd("cat here.txt")' if POSIX
                                        else 'cmd("type here.txt")'))


# ----------------------------------------------------------------------- file
class FileTests(OmniCase):
    def test_create_writes_and_says_how_much(self):
        out = self.out('file(create, "a.txt", "one\\ntwo\\n")')
        self.assertIn("created a.txt (8 bytes)", out)
        self.assertEqual("one\ntwo\n", (self.tmp / "a.txt").read_text())

    def test_create_refuses_to_clobber(self):
        (self.tmp / "a.txt").write_text("x")
        self.assertIn("is already there",
                      self.omni('file(create, "a.txt", "y")', expect=1).stderr)

    def test_edit_replaces_every_occurrence(self):
        (self.tmp / "a.txt").write_text("one one one")
        out = self.out('file(edit, "a.txt", "one", "two")')
        self.assertIn("3 places", out)
        self.assertEqual("two two two", (self.tmp / "a.txt").read_text())

    def test_edit_of_text_that_is_not_there_is_refused(self):
        (self.tmp / "a.txt").write_text("one")
        self.assertIn("has no 'two' in it",
                      self.omni('file(edit, "a.txt", "two", "three")', expect=1).stderr)

    def test_delete_removes_and_says_so(self):
        (self.tmp / "a.txt").write_text("gone")
        self.assertIn("deleted a.txt", self.out('file(delete, "a.txt")'))
        self.assertFalse(self.exists("a.txt"))

    def test_delete_of_nothing_is_refused(self):
        self.assertIn("is not there", self.omni('file(delete, "nope.txt")', expect=1).stderr)

    def test_an_action_file_does_not_do_is_refused(self):
        self.assertIn("file() does create, edit, delete",
                      self.omni('file(move, "a.txt")', expect=1).stderr)

    def test_a_nested_directory_is_made(self):
        self.out('file(create, "deep/in/here.txt", "x")')
        self.assertTrue((self.tmp / "deep" / "in" / "here.txt").is_file())


# --------------------------------------------------------------------- python
class PythonTests(OmniCase):
    def test_python_needs_the_import(self):
        self.assertIn("needs `import python`",
                      self.omni('python("1 + 1")', expect=1).stderr)

    def test_an_expression_prints_its_value(self):
        self.assertEqual("42\n", self.out('import python\npython("6 * 7")'))

    def test_statements_run_and_print(self):
        out = self.out('import python\npython("for i in range(3): print(i)")')
        self.assertEqual("0\n1\n2\n", out)

    def test_a_block_of_python_keeps_its_newlines(self):
        out = self.out('import python\npython("""\nimport math\nprint(math.sqrt(144))\n""")')
        self.assertEqual("12.0\n", out)

    def test_an_error_in_python_is_reported_as_an_omniscript_error(self):
        err = self.omni('import python\npython("1 / 0")', expect=1).stderr
        self.assertIn("python() raised ZeroDivisionError", err)


# ----------------------------------------------------------------------- draw
class DrawTests(OmniCase):
    def test_a_picture_is_a_real_png(self):
        out = self.out('draw(window(64, 40, "t"), rect(0, 0, 64, 40, blue), '
                       'save("pic.png"))')
        self.assertIn("wrote pic.png (64x40)", out)
        data = (self.tmp / "pic.png").read_bytes()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((64, 40), (width, height))
        pos, pixels = 8, b""
        while pos < len(data):
            size = struct.unpack(">I", data[pos:pos + 4])[0]
            if data[pos + 4:pos + 8] == b"IDAT":
                pixels += data[pos + 8:pos + 8 + size]
            pos += 12 + size
        self.assertEqual(len(zlib.decompress(pixels)), height * (width * 3 + 1))

    def test_without_save_the_picture_still_goes_somewhere(self):
        out = self.out('draw(window(20, 10, "t"), circle(10, 5, 4, red))')
        self.assertIn("drawing.png", out)
        self.assertTrue((self.tmp / "drawing.png").is_file())

    def test_a_buttons_command_does_not_run_until_it_is_clicked(self):
        self.out('draw(window(40, 20, "t"), button(2, 2, 30, 12, "Go", '
                 'file(create, "clicked.txt", "x")), save("b.png"))')
        self.assertFalse(self.exists("clicked.txt"))

    def test_an_unknown_element_is_refused(self):
        self.assertIn("draw() has no element called triangle",
                      self.omni('draw(triangle(1, 2))', expect=1).stderr)

    def test_a_colour_that_is_not_a_colour_is_refused(self):
        self.assertIn("is not a colour",
                      self.omni('draw(rect(0, 0, 4, 4, "puce"))', expect=1).stderr)

    def test_a_command_is_not_an_element(self):
        self.assertIn("is a command, not something draw() can place",
                      self.omni('draw(cmd("ls"))', expect=1).stderr)

    def test_an_empty_draw_is_refused(self):
        self.assertIn("needs something to draw", self.omni("draw()", expect=1).stderr)

    def test_colours_take_names_and_shorthand(self):
        for colour in ("red", '"#fff"', '"#123456"'):
            self.out(f'draw(rect(0, 0, 4, 4, {colour}), save("c.png"))')


# ------------------------------------------------------------------ draw_gui
class DrawGuiTests(OmniCase):
    def test_window_size_sets_the_size(self):
        out = self.out('draw_gui.window_size(200, 120, "Gui")')
        self.assertIn('window size 200x120 "Gui"', out)

    def test_window_size_takes_keywords_a_pair_or_a_string(self):
        self.assertIn("100x60", self.out("draw_gui.window_size(size=(100, 60))"))
        self.assertIn("110x70",
                      self.out("draw_gui.window_size(width=110, height=70)"))
        self.assertIn("320x200", self.out('draw_gui.window_size("320x200")'))
        self.assertIn("130x90", self.out("draw_gui.window_size((130, 90))"))

    def test_a_window_cannot_be_nothing(self):
        self.assertIn("a window cannot be 0x10",
                      self.omni("draw_gui.window_size(0, 10)", expect=1).stderr)

    def test_a_button_reports_where_it_landed(self):
        out = self.out('draw_gui.button(pos=(20, 30), text="Go")')
        self.assertIn("added button 'Go' at (20, 30)", out)

    def test_a_button_takes_positional_arguments_too(self):
        out = self.out('draw_gui.button(20, 30, 150, 36, "Go")')
        self.assertIn("added button 'Go' at (20, 30)", out)

    def test_draw_gui_shows_the_queued_buttons(self):
        out = self.out('draw_gui.window_size(64, 40, "g")\n'
                       'draw_gui.button(pos=(4, 4), text="Go")\n'
                       'draw_gui(save("gui.png"))')
        self.assertIn("wrote gui.png (64x40)", out)
        data = (self.tmp / "gui.png").read_bytes()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
        self.assertEqual((64, 40), struct.unpack(">II", data[16:24]))

    def test_draw_gui_with_nothing_shows_an_empty_window(self):
        out = self.out('draw_gui.window_size(32, 24, "empty")\n'
                       'draw_gui(save("empty.png"))')
        self.assertIn("wrote empty.png (32x24)", out)

    def test_draw_gui_uses_its_own_window_when_given_one(self):
        out = self.out('draw_gui.window_size(200, 200, "ignored")\n'
                       'draw_gui(window(48, 36, "kept"), save("w.png"))')
        self.assertIn("wrote w.png (48x36)", out)

    def test_a_gui_buttons_command_does_not_run_until_it_is_clicked(self):
        self.out('draw_gui.button(pos=(2, 2), text="Go", '
                 'action=file(create, "clicked.txt", "x"))\n'
                 'draw_gui(save("gb.png"))')
        self.assertFalse(self.exists("clicked.txt"))

    def test_a_buttons_action_has_to_be_a_command(self):
        err = self.omni('draw_gui.button(pos=(1, 1), text="Go", action="ls")',
                        expect=1).stderr
        self.assertIn("a button's action has to be a command", err)

    def test_a_dotted_button_inside_draw_is_refused(self):
        err = self.omni("draw(draw_gui.button(pos=(1, 1)))", expect=1).stderr
        self.assertIn("is a command -- inside draw() write button(...)", err)

    def test_window_size_works_as_an_element_too(self):
        out = self.out('draw(window_size(40, 30, "e"), save("e.png"))')
        self.assertIn("wrote e.png (40x30)", out)


# ------------------------------------------------------------------------ cli
class CliTests(OmniCase):
    def test_a_file_runs(self):
        program = self.tmp / "p.omni"
        program.write_text('cmd("echo from a file")\n')
        self.assertIn("from a file", run_omni(str(program), cwd=self.tmp).stdout)

    def test_a_missing_file_is_reported_plainly(self):
        err = run_omni(str(self.tmp / "nope.omni"), cwd=self.tmp, expect=1).stderr
        self.assertIn("nope.omni", err)

    def test_a_file_saved_with_a_bom_runs(self):
        program = self.tmp / "bom.omni"
        program.write_bytes(b'\xef\xbb\xbfcmd("echo bom ok")\n')
        proc = run_omni(str(program), cwd=self.tmp, expect=0)
        self.assertIn("bom ok", proc.stdout)

    def test_a_bom_pasted_inline_runs(self):
        self.assertIn("bom ok", self.out('\ufeffcmd("echo bom ok")'))

    def test_a_file_with_crlf_endings_runs(self):
        program = self.tmp / "crlf.omni"
        program.write_bytes(b'cmd("echo one")\r\ncmd("echo two")\r\n')
        proc = run_omni(str(program), cwd=self.tmp, expect=0)
        self.assertIn("one", proc.stdout)
        self.assertIn("two", proc.stdout)

    def test_an_empty_file_exits_quietly(self):
        program = self.tmp / "empty.omni"
        program.write_text("")
        proc = run_omni(str(program), cwd=self.tmp, expect=0)
        self.assertEqual("", proc.stdout)

    def test_a_shebang_line_is_just_a_comment(self):
        program = self.tmp / "bang.omni"
        program.write_text('#!/usr/bin/env omni\ncmd("echo bang ok")\n')
        proc = run_omni(str(program), cwd=self.tmp, expect=0)
        self.assertIn("bang ok", proc.stdout)

    def test_update_is_a_command_and_not_a_file_to_run(self):
        proc = run_omni("update", "--check", "--api-url", "http://127.0.0.1:1/",
                        cwd=self.tmp)
        self.assertEqual(1, proc.returncode)
        self.assertNotIn("no such file", (proc.stdout + proc.stderr).lower())

    def test_the_repl_runs_what_it_is_given(self):
        proc = subprocess.run([sys.executable, str(LAUNCHER)], input='cmd("echo repl")\n',
                              capture_output=True, text=True, timeout=120, cwd=str(self.tmp))
        self.assertIn("repl", proc.stdout)


# ------------------------------------------------------- a published release
class FakeGitHub(http.server.BaseHTTPRequestHandler):
    """Just enough of the GitHub API for the installers to fetch a release."""

    root = None          # the directory of files to serve
    sums = "good"        # "good" or "wrong"

    def log_message(self, *args):
        pass

    def _send(self, body: bytes, kind: str):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        if self.path.endswith("/releases/latest"):
            names = sorted(p.name for p in FakeGitHub.root.iterdir() if p.is_file())
            release = {"tag_name": "v" + __import__("omniscript").VERSION,
                       "published_at": "2026-01-01T00:00:00Z",
                       "assets": [{"name": n, "size": (FakeGitHub.root / n).stat().st_size,
                                   "browser_download_url": f"{base}/{n}"} for n in names]}
            self._send(json.dumps(release).encode(), "application/json")
        elif self.path.endswith("/SHA256SUMS.txt"):
            text = (FakeGitHub.root / "SHA256SUMS.txt").read_text()
            if FakeGitHub.sums == "wrong":
                text = "\n".join("0" * 64 + line[64:] for line in text.splitlines())
            self._send(text.encode(), "text/plain")
        else:
            path = FakeGitHub.root / self.path.lstrip("/")
            if path.is_file():
                self._send(path.read_bytes(), "application/octet-stream")
            else:
                self.send_error(404)


@unittest.skipUnless(BASH and POSIX, "install.sh needs bash on a POSIX system")
class InstallerTests(unittest.TestCase):
    """The installers, against a source tree and against a published release."""

    @classmethod
    def setUpClass(cls):
        cls.dist = Path(tempfile.mkdtemp(prefix="omni-dist-"))
        build = subprocess.run([sys.executable, str(REPO / "tools" / "build_executable.py"),
                                "--skip-binary", "--out", str(cls.dist)],
                               capture_output=True, text=True, cwd=str(REPO), timeout=900)
        if build.returncode != 0:
            raise unittest.SkipTest(f"could not build the zipapp: {build.stderr[-300:]}")
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        FakeGitHub.root = cls.dist
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.dist, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="omni-install-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.prefix = self.tmp / "prefix"
        (self.home / "data").mkdir(parents=True)
        self.prefix.mkdir()
        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        self.env["XDG_DATA_HOME"] = str(self.home / "data")

    def install(self, *args, expect=0):
        proc = subprocess.run([BASH, str(REPO / "install.sh"), "--prefix", str(self.prefix),
                               *args], env=self.env, capture_output=True, text=True,
                              timeout=900, cwd=str(self.tmp))
        if expect is not None:
            self.assertEqual(expect, proc.returncode,
                             f"{args}\n{proc.stdout}\n{proc.stderr}")
        return proc

    def uninstall(self, *args, expect=0):
        return subprocess.run([BASH, str(REPO / "uninstall.sh"), "--prefix", str(self.prefix),
                               *args], env=self.env, capture_output=True, text=True,
                              timeout=900, cwd=str(self.tmp))

    def manifest(self):
        text = (self.home / "data" / "omniscript" / "install.txt").read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    def test_a_source_tree_installs_and_uninstalls(self):
        out = self.install().stdout
        self.assertIn("is installed (beta channel)", out)
        self.assertTrue((self.prefix / "bin" / "omni").is_symlink())
        self.assertEqual("symlink", self.manifest()["mode"])
        version = subprocess.run([str(self.prefix / "bin" / "omni"), "--version"],
                                 capture_output=True, text=True, timeout=120)
        self.assertIn("OmniScript", version.stdout)
        removal = self.uninstall("--purge")
        self.assertIn("uninstalled", removal.stdout)
        self.assertFalse((self.prefix / "bin" / "omni").exists())

    def test_a_release_installs_one_verified_file(self):
        out = self.install("--channel", "release", "--api-url", self.api).stdout
        self.assertIn("sha256 verified", out)
        self.assertIn("is installed (release channel)", out)
        record = self.manifest()
        import omniscript
        self.assertEqual("binary", record["mode"])
        self.assertEqual(f"v{omniscript.VERSION}", record["release_tag"])
        self.assertFalse((self.prefix / "bin" / "omni").is_symlink())
        self.uninstall("--purge", expect=0)

    def test_a_download_that_does_not_match_its_checksum_installs_nothing(self):
        FakeGitHub.sums = "wrong"
        try:
            out = self.install("--channel", "release", "--api-url", self.api, expect=1)
        finally:
            FakeGitHub.sums = "good"
        self.assertIn("checksum mismatch", out.stdout + out.stderr)
        self.assertFalse((self.prefix / "bin" / "omni").exists())

    def test_a_release_that_cannot_be_reached_falls_back_to_the_source(self):
        proc = self.install("--channel", "release", "--api-url", "http://127.0.0.1:1/")
        out = proc.stdout + proc.stderr
        self.assertIn("did not deliver", out)
        self.assertIn("is installed (beta channel)", out)

    def test_a_foreign_command_survives_the_install_and_the_uninstall(self):
        stranger = self.prefix / "bin" / "omni"
        stranger.parent.mkdir(parents=True, exist_ok=True)
        stranger.write_text("#!/bin/sh\necho not omni\n")
        stranger.chmod(0o755)
        out = self.install(expect=1)
        self.assertIn("not created by this script", out.stdout + out.stderr)
        self.assertIn("not omni", stranger.read_text())


@unittest.skipUnless(PWSH, "install.ps1 needs pwsh")
class PowerShellParseTests(unittest.TestCase):
    def test_both_scripts_parse(self):
        for name in ("install.ps1", "uninstall.ps1"):
            program = ("$errors = $null; [System.Management.Automation.Language.Parser]"
                       f"::ParseFile('{REPO / name}', [ref]$null, [ref]$errors) | Out-Null;"
                       "if ($errors) { $errors | ForEach-Object { Write-Host $_.Message };"
                       "exit 1 }; exit 0")
            proc = subprocess.run([PWSH, "-NoProfile", "-Command", program],
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(0, proc.returncode, f"{name}: {proc.stdout}{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
