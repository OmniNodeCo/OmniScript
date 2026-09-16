"""The install and uninstall scripts, exercised for real.

Each test gets a throwaway HOME and prefix, so nothing here can touch the
machine running the suite. The bash scripts run wherever bash does; the
PowerShell scripts are parsed and run wherever pwsh does, and skipped
elsewhere rather than pretending to pass.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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
        return self.data_dir / "install.json"

    def manifest(self):
        return json.loads(self.manifest_path.read_text())

    def command_path(self, name):
        if POSIX:
            return self.bin_dir / name
        path = self.bin_dir / f"{name}.cmd"
        return path

    def run_script(self, which, *args, expect=0):
        script = REPO / self.scripts[which]
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
                              capture_output=True, text=True, timeout=300)
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


if __name__ == "__main__":
    unittest.main()
