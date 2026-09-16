"""The install and uninstall scripts, exercised for real.

Each test gets a throwaway HOME and prefix, so nothing here can touch the
machine running the suite. The bash scripts run wherever bash does; the
PowerShell scripts are parsed and run wherever pwsh does, and skipped
elsewhere rather than pretending to pass.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:  # `unittest discover -s tests` puts tests/ on the path
    from release_fixture import NEW, FakeGitHub, build_artifact
except ImportError:  # `python -m unittest tests.test_install` does not
    from tests.release_fixture import NEW, FakeGitHub, build_artifact

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from omniscript.update import parse_manifest  # noqa: E402

BASH = shutil.which("bash")
PWSH = shutil.which("pwsh") or shutil.which("powershell")
POSIX = os.name == "posix"


class ScriptCase(unittest.TestCase):
    """Shared scaffolding: a fake HOME, a fake prefix, and a way to run scripts."""

    interpreter = None
    scripts = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="omni-install-"))
        self.home = self.tmp / "home"
        self.prefix = self.tmp / "prefix"
        (self.home / "data").mkdir(parents=True)
        self.prefix.mkdir()
        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        self.env["XDG_DATA_HOME"] = str(self.home / "data")
        self.env["LOCALAPPDATA"] = str(self.home / "appdata")
        self.env["USERPROFILE"] = str(self.home)
        # Whatever is on PATH must not answer for the commands we are testing.
        self.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + self.env.get("PATH", "")

    def tearDown(self):
        for path in self.tmp.rglob("*"):
            try:
                path.chmod(stat.S_IRWXU)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    @property
    def bin_dir(self):
        return self.prefix / "bin" if POSIX else self.prefix

    @property
    def data_dir(self):
        return self.home / "data" / "omniscript" if POSIX else self.home / "appdata" / "OmniScript"

    @property
    def manifest_path(self):
        return self.data_dir / "install.txt"

    def manifest(self):
        return parse_manifest(self.manifest_path.read_text())

    def command_path(self, name):
        if POSIX:
            return self.bin_dir / name
        path = self.bin_dir / f"{name}.cmd"
        return path

    def run_script(self, which, *args, expect=0):
        script = REPO / self.scripts[which]
        if self.interpreter == PWSH:
            # -File, not a bare path: without it pwsh parses the call as
            # -Command and the arguments never reach the script's param block.
            command = [self.interpreter, "-NoProfile", "-File", str(script), *args]
        else:
            command = [self.interpreter, str(script), *args]
        proc = subprocess.run(command, env=self.env, cwd=str(self.tmp),
                              capture_output=True, text=True, timeout=900)
        if expect is not None:
            self.assertEqual(
                expect, proc.returncode,
                f"{' '.join(command)} exited {proc.returncode}\n"
                f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
        return proc

    def output_of(self, path):
        command = [str(path)]
        if path.suffix.lower() == ".cmd":
            command = [os.environ.get("ComSpec", "cmd.exe"), "/c", str(path)]
        return subprocess.run([*command, "--version"], env=self.env, cwd=str(self.tmp),
                              capture_output=True, text=True, timeout=120)


@unittest.skipUnless(BASH and POSIX, "install.sh needs bash on a POSIX system")
class InstallScriptTests(ScriptCase):
    interpreter = None
    scripts = {"install": "install.sh", "uninstall": "uninstall.sh"}

    def setUp(self):
        super().setUp()
        self.interpreter = BASH

    def install(self, *args, expect=0):
        return self.run_script("install", "--prefix", str(self.prefix), *args, expect=expect)

    def uninstall(self, *args, expect=0):
        return self.run_script("uninstall", "--prefix", str(self.prefix), *args, expect=expect)

    # ------------------------------------------------------------- installing
    def test_install_creates_both_commands_and_they_work(self):
        self.install()
        for name in ("omni", "omniscript"):
            path = self.command_path(name)
            self.assertTrue(path.is_symlink(), f"{name} should be a symlink")
            self.assertEqual(REPO / "omni", Path(os.readlink(path)))
        done = self.output_of(self.command_path("omni"))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("OmniScript", done.stdout)

    def test_installed_command_runs_a_program_from_anywhere(self):
        self.install()
        proc = subprocess.run(
            [str(self.command_path("omni")), "-e",
             'let c = draw(8, 8)\nc.rect(0, 0, 8, 8, "#2ea043")\nprint("ok:", 6 * 7)'],
            env=self.env, cwd=str(self.tmp), capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("ok: 42", proc.stdout)

    def test_manifest_records_what_was_done(self):
        self.install()
        manifest = self.manifest()
        self.assertEqual("symlink", manifest["mode"])
        self.assertEqual(str(REPO), manifest["source"])
        self.assertEqual(str(self.bin_dir), manifest["bin_dir"])
        self.assertFalse(manifest["cloned_by_installer"])
        self.assertEqual(sorted(str(self.command_path(n)) for n in ("omni", "omniscript")),
                         sorted(manifest["commands"]))
        self.assertEqual(str(self.home / ".omniscript_history"), manifest["history_file"])

    def test_installing_twice_changes_nothing(self):
        self.install()
        again = self.install()
        self.assertIn("already points at", again.stdout)
        self.assertTrue(self.command_path("omni").is_symlink())

    def test_dry_run_writes_nothing(self):
        result = self.install("--dry-run")
        self.assertIn("Dry run", result.stdout)
        self.assertFalse(self.command_path("omni").exists())
        self.assertFalse(self.manifest_path.exists())

    def test_uninstall_dry_run_leaves_everything(self):
        self.install()
        self.uninstall("--dry-run")
        self.assertTrue(self.command_path("omni").exists())
        self.assertTrue(self.manifest_path.exists())

    # ----------------------------------------------------------- uninstalling
    def test_uninstall_removes_the_commands_and_the_manifest(self):
        self.install()
        result = self.uninstall()
        self.assertIn("uninstalled", result.stdout)
        for name in ("omni", "omniscript"):
            self.assertFalse(self.command_path(name).exists(), f"{name} should be gone")
        self.assertFalse(self.manifest_path.exists())

    def test_uninstall_never_touches_the_source_tree(self):
        self.install()
        self.uninstall("--purge")
        self.assertTrue((REPO / "omniscript" / "cli.py").is_file())
        self.assertTrue((REPO / "omni").is_file())
        self.assertTrue((REPO / "examples").is_dir())

    def test_purge_removes_the_repl_history(self):
        self.install()
        history = self.home / ".omniscript_history"
        history.write_text("print(\"hello\")\n")
        self.uninstall("--purge")
        self.assertFalse(history.exists())

    def test_without_purge_the_repl_history_stays(self):
        self.install()
        history = self.home / ".omniscript_history"
        history.write_text("print(\"hello\")\n")
        self.uninstall()
        self.assertTrue(history.exists())

    def test_uninstall_is_happy_when_there_is_nothing_to_do(self):
        result = self.uninstall()
        self.assertEqual(0, result.returncode)
        self.assertIn("uninstalled", result.stdout)

    # ------------------------------------------------- leaving other things be
    def test_a_foreign_command_blocks_the_install_and_survives_it(self):
        stranger = self.bin_dir / "omniscript"
        stranger.parent.mkdir(parents=True, exist_ok=True)
        stranger.write_text("#!/bin/sh\necho 'not omniscript'\n")
        stranger.chmod(0o755)
        result = self.install(expect=1)
        self.assertIn("not created by this script", result.stderr)
        self.assertIn("not omniscript", stranger.read_text())
        # Nothing was half-installed on the way to that refusal.
        self.assertFalse(self.command_path("omni").exists())

    def test_force_moves_a_foreign_command_aside_instead_of_deleting_it(self):
        stranger = self.bin_dir / "omniscript"
        stranger.parent.mkdir(parents=True, exist_ok=True)
        stranger.write_text("#!/bin/sh\necho 'not omniscript'\n")
        stranger.chmod(0o755)
        result = self.install("--force")
        self.assertIn("moved the old omniscript", result.stdout)
        backup = self.bin_dir / "omniscript.bak"
        self.assertTrue(backup.exists())
        self.assertIn("not omniscript", backup.read_text())
        self.assertTrue(self.command_path("omniscript").is_symlink())

    def test_uninstall_leaves_a_strangers_command_alone(self):
        # No manifest, and a file that is not one of ours: keep it.
        stranger = self.bin_dir / "omni"
        stranger.parent.mkdir(parents=True, exist_ok=True)
        stranger.write_text("#!/bin/sh\necho 'I mention OmniScript, but I am not it'\n")
        stranger.chmod(0o755)
        result = self.uninstall()
        self.assertIn("leaving", result.stdout + result.stderr)
        self.assertTrue(stranger.exists())

    def test_uninstall_removes_a_symlink_into_the_source_tree_without_a_manifest(self):
        self.install()
        self.manifest_path.unlink()          # pretend the manifest was lost
        self.uninstall()
        self.assertFalse(self.command_path("omni").exists())

    # ------------------------------------------------------ editor extension
    def test_vscode_extension_is_installed_and_removed(self):
        extensions = self.home / ".vscode" / "extensions"
        extensions.mkdir(parents=True)
        self.install("--vscode")
        installed = list(extensions.glob("omninode.omniscript-*"))
        self.assertEqual(1, len(installed), f"expected one extension dir in {extensions}")
        self.assertTrue((installed[0] / "package.json").is_file())
        self.assertTrue((installed[0] / "syntaxes" / "omniscript.tmLanguage.json").is_file())
        self.assertEqual([str(installed[0])], self.manifest()["editor_extensions"])

        self.uninstall()
        self.assertEqual([], list(extensions.glob("omninode.omniscript-*")))

    def test_keep_vscode_leaves_the_extension(self):
        extensions = self.home / ".vscode" / "extensions"
        extensions.mkdir(parents=True)
        self.install("--vscode")
        self.uninstall("--keep-vscode")
        self.assertEqual(1, len(list(extensions.glob("omninode.omniscript-*"))))

    # ------------------------------------------------------------- refusals
    def test_help_explains_the_options(self):
        for script in ("install", "uninstall"):
            result = self.run_script(script, "--help")
            self.assertIn("Usage:", result.stdout)
        self.assertIn("--mode", self.run_script("install", "--help").stdout)
        self.assertIn("--purge", self.run_script("uninstall", "--help").stdout)

    def test_unknown_option_is_refused(self):
        self.assertIn("unknown option", self.install("--nonsense", expect=1).stderr)
        self.assertIn("unknown option", self.uninstall("--nonsense", expect=1).stderr)

    def test_unknown_mode_is_refused(self):
        self.assertIn("--mode must be", self.install("--mode", "docker", expect=1).stderr)

    def test_a_source_that_is_not_a_source_tree_is_refused(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        result = self.install("--source", str(empty), expect=1)
        self.assertIn("not an OmniScript source tree", result.stderr)

    def test_an_old_python_is_refused_with_a_useful_message(self):
        stub = self.tmp / "python3.9"
        stub.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "code = sys.argv[2] if len(sys.argv) > 2 else ''\n"
            "if 'SystemExit' in code:\n"
            "    sys.exit(1)\n"
            "if 'version_info' in code:\n"
            "    print('3.9.7')\n"
            "sys.exit(0)\n")
        stub.chmod(0o755)
        result = self.install("--python", str(stub), expect=1)
        self.assertIn("3.9.7", result.stderr)
        self.assertIn("needs 3.10 or newer", result.stderr)
        self.assertFalse(self.command_path("omni").exists())

    def test_a_missing_python_is_refused(self):
        result = self.install("--python", str(self.tmp / "no-such-python"), expect=1)
        self.assertIn("not executable", result.stderr + result.stdout)


@unittest.skipUnless(PWSH, "install.ps1 needs pwsh")
class PowerShellScriptTests(ScriptCase):
    interpreter = None
    scripts = {"install": "install.ps1", "uninstall": "uninstall.ps1"}

    def setUp(self):
        super().setUp()
        self.interpreter = PWSH

    def parse(self, script):
        """Ask PowerShell's own parser whether the file is valid."""
        program = (
            "$errors = $null; $tokens = $null;"
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{script}', [ref]$tokens, [ref]$errors) | Out-Null;"
            "if ($errors) { $errors | ForEach-Object { Write-Host $_.Message }; exit 1 };"
            "exit 0"
        )
        proc = subprocess.run([PWSH, "-NoProfile", "-Command", program],
                              capture_output=True, text=True, timeout=300,
                              env=self.env)
        self.assertEqual(0, proc.returncode,
                         f"{script} does not parse:\n{proc.stdout}\n{proc.stderr}")

    def test_both_scripts_parse(self):
        for name in ("install.ps1", "uninstall.ps1"):
            self.parse(str(REPO / name))

    def test_help_runs(self):
        for script in ("install", "uninstall"):
            proc = self.run_script(script, "-Help")
            self.assertIn("Usage:", proc.stdout)

    def test_dry_run_writes_nothing(self):
        proc = self.run_script("install", "-Prefix", str(self.prefix), "-Source", str(REPO),
                               "-Python", sys.executable, "-DryRun")
        self.assertIn("Dry run", proc.stdout)
        self.assertFalse(self.command_path("omni").exists())

    def test_install_and_uninstall_cycle(self):
        install = self.run_script("install", "-Prefix", str(self.prefix), "-Source", str(REPO),
                                  "-Python", sys.executable)
        self.assertIn("is installed", install.stdout)
        self.assertTrue(self.manifest_path.is_file(), install.stdout)

        command = self.command_path("omni")
        self.assertTrue(command.exists(), f"{command} missing after install")
        done = self.output_of(command)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("OmniScript", done.stdout)

        manifest = self.manifest()
        self.assertEqual("symlink", manifest["mode"])
        self.assertEqual(str(REPO).replace("\\", "/"), manifest["source"].replace("\\", "/"))

        removal = self.run_script("uninstall", "-Prefix", str(self.prefix), "-Purge")
        self.assertIn("uninstalled", removal.stdout)
        self.assertFalse(command.exists())
        self.assertFalse(self.manifest_path.exists())
        self.assertTrue((REPO / "omniscript" / "cli.py").is_file())

    def test_a_foreign_command_blocks_the_install(self):
        stranger = self.command_path("omniscript")
        stranger.parent.mkdir(parents=True, exist_ok=True)
        stranger.write_text("@echo off\necho not omniscript\n")
        result = self.run_script("install", "-Prefix", str(self.prefix), "-Source", str(REPO),
                                 "-Python", sys.executable, expect=1)
        self.assertIn("not created by this script", result.stdout + result.stderr)
        self.assertIn("not omniscript", stranger.read_text())


# ------------------------------------------------------- the release channel
class ReleaseCase(ScriptCase):
    """Installs from a published release instead of from a source tree.

    The release is served from localhost by a directory shaped like the GitHub
    API, so the installer really does ask, choose an asset, download it, check
    its sha256 and put it in place -- without an internet connection.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(tempfile.mkdtemp(prefix="omni-release-"))
        cls.artifact = build_artifact(cls.fixture, NEW)
        cls.github = FakeGitHub(cls.fixture / "api")
        cls.github.publish(NEW, [cls.artifact])

    @classmethod
    def tearDownClass(cls):
        cls.github.close()
        for path in cls.fixture.rglob("*"):
            try:
                path.chmod(stat.S_IRWXU)
            except OSError:
                pass
        shutil.rmtree(cls.fixture, ignore_errors=True)


@unittest.skipUnless(BASH and POSIX, "install.sh needs bash on a POSIX system")
class BashReleaseTests(ReleaseCase):
    def setUp(self):
        super().setUp()
        self.interpreter = BASH
        self.scripts = {"install": "install.sh", "uninstall": "uninstall.sh"}

    def install(self, *args, expect=0):
        return self.run_script("install", "--prefix", str(self.prefix), *args, expect=expect)

    def uninstall(self, *args, expect=0):
        return self.run_script("uninstall", "--prefix", str(self.prefix), *args, expect=expect)

    def from_release(self, *args, expect=0):
        return self.install("--channel", "release", "--api-url", self.github.api,
                            *args, expect=expect)

    def test_a_release_installs_one_file_that_works(self):
        result = self.from_release()
        self.assertIn("sha256 verified", result.stdout)
        self.assertIn(f"OmniScript {NEW} is installed (release channel)", result.stdout)
        command = self.command_path("omni")
        self.assertTrue(command.is_file(), result.stdout)
        self.assertFalse(command.is_symlink(), "a release install is a real file")
        done = self.output_of(command)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn(f"OmniScript {NEW}", done.stdout)
        self.assertTrue(self.command_path("omniscript").exists())

    def test_the_manifest_records_the_release(self):
        self.from_release()
        record = self.manifest()
        self.assertEqual("binary", record["mode"])
        self.assertEqual("release", record["channel"])
        self.assertEqual(NEW, record["version"])
        self.assertEqual(f"v{NEW}", record["release_tag"])
        self.assertEqual(str(self.command_path("omni")), record["binary"])
        self.assertIn(str(self.command_path("omni")), record["commands"])
        self.assertIn(str(self.command_path("omniscript")), record["commands"])
        self.assertEqual("", record["source"], "a release install has no source tree")

    def test_what_it_installed_can_update_itself(self):
        self.from_release()
        command = self.command_path("omni")
        proc = subprocess.run([str(command), "update", "--check"], env=self.env,
                              cwd=str(self.tmp), capture_output=True, text=True, timeout=300)
        out = proc.stdout + proc.stderr
        self.assertEqual(0, proc.returncode, out)
        self.assertIn("binary install", out)
        self.assertIn("up to date", out)

    def test_uninstall_removes_a_release_install(self):
        self.from_release()
        removal = self.uninstall("--purge")
        self.assertIn("uninstalled", removal.stdout)
        self.assertFalse(self.command_path("omni").exists())
        self.assertFalse(self.command_path("omniscript").exists())
        self.assertFalse(self.manifest_path.exists())
        self.assertEqual([], [p for p in self.bin_dir.iterdir() if p.suffix != ".bak"])

    def test_an_unreachable_release_falls_back_to_the_repository(self):
        result = self.install("--channel", "release", "--api-url", "http://127.0.0.1:1/",
                              "--source", str(REPO))
        self.assertIn("did not deliver", result.stdout + result.stderr)
        self.assertIn("is installed (beta channel)", result.stdout)
        self.assertTrue(self.command_path("omni").is_symlink())
        self.assertEqual("symlink", self.manifest()["mode"])

    def test_a_bad_checksum_is_fatal_and_installs_nothing(self):
        broken = FakeGitHub(self.tmp / "broken-api")
        self.addCleanup(broken.close)
        broken.publish(NEW, [self.artifact], sums="wrong")
        result = self.install("--channel", "release", "--api-url", broken.api,
                              "--source", str(REPO), expect=1)
        out = result.stdout + result.stderr
        self.assertIn("checksum mismatch", out)
        self.assertIn("does not match the checksum", out)
        self.assertFalse(self.command_path("omni").exists())
        self.assertFalse(self.manifest_path.exists())

    def test_a_pinned_release_that_does_not_exist_is_fatal(self):
        result = self.install("--channel", "release", "--api-url", self.github.api,
                              "--version", "7.7.7", "--source", str(REPO), expect=1)
        out = result.stdout + result.stderr
        self.assertIn("no release tagged v7.7.7", out)
        self.assertFalse(self.command_path("omni").exists())

    def test_a_pinned_release_that_does_exist_is_installed(self):
        result = self.install("--channel", "release", "--api-url", self.github.api,
                              "--version", NEW)
        self.assertIn(f"OmniScript {NEW} is installed", result.stdout)
        self.assertEqual(f"v{NEW}", self.manifest()["release_tag"])

    def test_no_verify_skips_the_checksum(self):
        broken = FakeGitHub(self.tmp / "broken-api2")
        self.addCleanup(broken.close)
        broken.publish(NEW, [self.artifact], sums="wrong")
        result = self.install("--channel", "release", "--api-url", broken.api, "--no-verify")
        self.assertIn("not checking the checksum", result.stdout)
        self.assertTrue(self.command_path("omni").is_file())

    def test_dry_run_downloads_nothing(self):
        result = self.from_release("--dry-run")
        self.assertIn("Dry run", result.stdout)
        self.assertIn("[dry-run]", result.stdout)
        self.assertFalse(self.bin_dir.exists() and any(self.bin_dir.iterdir()))
        self.assertFalse(self.manifest_path.exists())

    def test_an_unknown_channel_is_refused(self):
        result = self.install("--channel", "gamma", expect=1)
        self.assertIn("--channel must be release or beta", result.stderr)


@unittest.skipUnless(PWSH, "PowerShell is not installed")
class PowerShellReleaseTests(ReleaseCase):
    def setUp(self):
        super().setUp()
        self.interpreter = PWSH
        self.scripts = {"install": "install.ps1", "uninstall": "uninstall.ps1"}

    def install(self, *args, expect=0):
        return self.run_script("install", "-Prefix", str(self.prefix), *args, expect=expect)

    def uninstall(self, *args, expect=0):
        return self.run_script("uninstall", "-Prefix", str(self.prefix), *args, expect=expect)

    def from_release(self, *args, expect=0):
        return self.install("-Channel", "release", "-ApiUrl", self.github.api, *args,
                            expect=expect)

    def test_both_scripts_still_parse(self):
        for script in self.scripts.values():
            check = (
                "$errors = $null\n"
                "[System.Management.Automation.Language.Parser]::ParseFile("
                f"'{REPO / script}', [ref]$null, [ref]$errors) | Out-Null\n"
                "if ($errors) { $errors | ForEach-Object { Write-Host $_.Message }; exit 1 }\n"
            )
            proc = subprocess.run([PWSH, "-NoProfile", "-Command", check],
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(0, proc.returncode, f"{script}: {proc.stdout}{proc.stderr}")

    def test_a_release_installs_and_uninstalls(self):
        result = self.from_release()
        out = result.stdout + result.stderr
        self.assertIn("sha256 verified", out)
        self.assertIn(f"OmniScript {NEW} is installed (release channel)", out)

        record = self.manifest()
        self.assertEqual("binary", record["mode"])
        self.assertEqual("release", record["channel"])
        self.assertEqual(f"v{NEW}", record["release_tag"])
        self.assertTrue(record["binary"], "the manifest does not say what was downloaded")

        command = self.command_path("omni")
        self.assertTrue(command.exists(), out)
        done = self.output_of(command)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn(f"OmniScript {NEW}", done.stdout)

        removal = self.uninstall("-Purge")
        self.assertIn("uninstalled", removal.stdout + removal.stderr)
        self.assertFalse(command.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_an_unreachable_release_falls_back_to_the_repository(self):
        result = self.install("-Channel", "release", "-ApiUrl", "http://127.0.0.1:1/",
                              "-Source", str(REPO), "-Python", sys.executable)
        out = result.stdout + result.stderr
        self.assertIn("did not deliver", out)
        self.assertIn("is installed (beta channel)", out)
        self.assertEqual("symlink", self.manifest()["mode"])

    def test_a_bad_checksum_is_fatal(self):
        broken = FakeGitHub(self.tmp / "broken-api")
        self.addCleanup(broken.close)
        broken.publish(NEW, [self.artifact], sums="wrong")
        result = self.install("-Channel", "release", "-ApiUrl", broken.api,
                              "-Source", str(REPO), expect=1)
        out = result.stdout + result.stderr
        self.assertIn("checksum mismatch", out)
        self.assertFalse(self.command_path("omni").exists())



if __name__ == "__main__":
    unittest.main()
