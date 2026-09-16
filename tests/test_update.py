"""The update command, its two channels, and the artifacts they install.

Nothing here reaches the internet. A directory shaped like the GitHub API is
served over http://127.0.0.1, so the release channel runs exactly as it does in
the field -- real HTTP, real JSON, real checksums -- against a release that was
built moments ago from a copy of this tree with a different version stamped into
it. The beta channel gets a real git repository to pull from, on disk.

The artifact under test is the zipapp rather than a frozen executable, because a
zipapp builds in a fraction of a second and exercises the same code: one file,
downloaded, checksummed, swapped in, run. `tools/build_executable.py` builds both
shapes, and CI builds the frozen one on real runners.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from omniscript import update as U  # noqa: E402
from omniscript import _bundle  # noqa: E402

try:  # `unittest discover -s tests` puts tests/ on the path
    from release_fixture import (NEW, OLD, FakeGitHub, build_artifact, clone, commit,
                                 git, make_repository, stamp_version)
except ImportError:  # `python -m unittest tests.test_update` does not
    from tests.release_fixture import (NEW, OLD, FakeGitHub, build_artifact, clone,
                                       commit, git, make_repository, stamp_version)

POSIX = os.name == "posix"
HAS_GIT = bool(shutil.which("git"))


# ------------------------------------------------------------------ scaffolding
class UpdateCase(unittest.TestCase):
    """A throwaway HOME, a bin directory, and an isolated manifest."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="omni-update-"))
        self.home = self.tmp / "home"
        self.bin_dir = self.tmp / "bin"
        (self.home / "data").mkdir(parents=True)
        self.bin_dir.mkdir()
        self.env = dict(os.environ)
        self.env.update({
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / "data"),
            "LOCALAPPDATA": str(self.home / "appdata"),
            "USERPROFILE": str(self.home),
            "OMNISCRIPT_MANIFEST": str(self.manifest_path),
            "OMNISCRIPT_REPO_URL": "",
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "GITHUB_TOKEN": "",
            "GH_TOKEN": "",
        })
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for path in self.tmp.rglob("*"):
            try:
                path.chmod(stat.S_IRWXU)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    @property
    def manifest_path(self) -> Path:
        return self.home / "data" / "omniscript" / "install.txt"

    def isolate_from_the_manifest(self) -> None:
        """Make sure no manifest is found anywhere, so inference has to do the work."""
        self.env["OMNISCRIPT_MANIFEST"] = str(self.tmp / "absent.json")
        self.env["XDG_DATA_HOME"] = str(self.home / "elsewhere")
        self.env["LOCALAPPDATA"] = str(self.home / "appdata2")

    def manifest(self) -> dict:
        return U.parse_manifest(self.manifest_path.read_text())

    def stage(self, artifact: Path) -> Path:
        """Put an artifact where an installer would have put it."""
        name = "omni" if POSIX else "omni.pyz"
        target = self.bin_dir / name
        shutil.copy2(artifact, target)
        if POSIX:
            target.chmod(0o755)
        return target

    def run_omni(self, program: Path, *args: str, env: dict | None = None,
                 cwd: Path | None = None) -> subprocess.CompletedProcess:
        command = [str(program)] if POSIX and not str(program).endswith(".pyz") \
            else [sys.executable, str(program)]
        return subprocess.run(command + [str(a) for a in args], capture_output=True,
                              text=True, env=env or self.env, cwd=str(cwd or self.tmp),
                              timeout=300)

    def output(self, proc: subprocess.CompletedProcess) -> str:
        return proc.stdout + proc.stderr


class ArtifactCase(UpdateCase):
    """Builds the two artifacts once for the whole class: they are slow-ish."""

    old_artifact: Path
    new_artifact: Path

    @classmethod
    def setUpClass(cls):
        cls.artifacts = Path(tempfile.mkdtemp(prefix="omni-artifacts-"))
        cls.old_artifact = build_artifact(cls.artifacts, OLD)
        cls.new_artifact = build_artifact(cls.artifacts, NEW)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.artifacts, ignore_errors=True)


# ------------------------------------------------------------------ pure logic
class NamingTests(unittest.TestCase):
    def test_the_platform_tag_names_this_machine(self):
        tag = U.platform_tag()
        self.assertRegex(tag, r"^(linux|macos|windows|freebsd)-[a-z0-9_]+$")
        self.assertIn(tag.split("-")[0], ("linux", "macos", "windows", "freebsd"))

    def test_artifact_names_follow_one_convention(self):
        tag = U.platform_tag()
        suffix = ".exe" if os.name == "nt" else ""
        self.assertEqual(U.binary_asset("1.2.3"), f"omni-1.2.3-{tag}{suffix}")
        self.assertEqual(U.binary_asset("1.2.3", "plan9-mips"), "omni-1.2.3-plan9-mips" + suffix)
        self.assertEqual(U.zipapp_asset("1.2.3"), "omni-1.2.3-any.pyz")

    def test_versions_compare_as_numbers_not_as_text(self):
        self.assertEqual(U.parse_version("v1.2.0"), (1, 2, 0))
        self.assertEqual(U.parse_version("1.2.0"), U.parse_version("v1.2.0"))
        self.assertGreater(U.parse_version("1.10.0"), U.parse_version("1.9.0"))
        self.assertGreater(U.parse_version("2.0.0"), U.parse_version("1.99.99"))
        self.assertEqual(U.version_of_tag("v1.2.0"), "1.2.0")

    def test_a_version_that_is_not_a_version_sorts_below_every_real_one(self):
        self.assertLess(U.parse_version("unknown"), U.parse_version("0.0.1"))
        self.assertLess(U.parse_version(""), U.parse_version("0.0.1"))
        self.assertEqual(U.parse_version("1.2.0rc1"), (1, 2, 0))


class AssetPickingTests(unittest.TestCase):
    def release(self, names: list[str], version: str = "1.2.3") -> dict:
        return {"tag_name": f"v{version}",
                "assets": [{"name": n, "size": 10,
                            "browser_download_url": f"https://example.invalid/{n}"}
                           for n in names]}

    def test_the_executable_built_for_this_machine_wins(self):
        tag = U.platform_tag()
        names = [U.zipapp_asset("1.2.3"), U.binary_asset("1.2.3")]
        asset = U.pick_asset(self.release(names), "1.2.3")
        self.assertEqual(asset.kind, "binary")
        self.assertEqual(asset.name, f"omni-1.2.3-{tag}" + (".exe" if os.name == "nt" else ""))

    def test_an_executable_for_another_machine_is_not_taken(self):
        other = "plan9-mips"
        names = [U.binary_asset("1.2.3", other), U.zipapp_asset("1.2.3")]
        asset = U.pick_asset(self.release(names), "1.2.3")
        self.assertEqual(asset.kind, "pyz")

    def test_the_zipapp_is_the_fallback(self):
        asset = U.pick_asset(self.release([U.zipapp_asset("1.2.3")]), "1.2.3")
        self.assertEqual(asset.kind, "pyz")

    def test_a_python_distribution_is_not_something_it_can_run(self):
        # The wheel and the sdist are still published, but they are for pip: an
        # updater that puts files in place has no use for them.
        release = self.release(["omniscript_lang-1.2.3-py3-none-any.whl",
                                "omniscript_lang-1.2.3.tar.gz"])
        self.assertIsNone(U.pick_asset(release, "1.2.3"))

    def test_a_release_with_no_files_picks_nothing(self):
        self.assertIsNone(U.pick_asset(self.release([]), "1.2.3"))
        self.assertIsNone(U.pick_asset({}, "1.2.3"))

    def test_an_asset_with_no_url_is_skipped(self):
        release = {"assets": [{"name": U.zipapp_asset("1.2.3"), "size": 1}]}
        self.assertIsNone(U.pick_asset(release, "1.2.3"))

    def test_checksum_lines_parse_in_both_shapes(self):
        text = (f"{'a' * 64}  omni-1.0.0-any.pyz\n"
                f"{'b' * 64} *omni-1.0.0-linux-x86_64\n"
                f"{'c' * 64} omni-1.0.0-macos-arm64\n"
                "\n# a comment\n")
        sums = U.parse_checksums(text)
        self.assertEqual(sums["omni-1.0.0-any.pyz"], "a" * 64)
        self.assertEqual(sums["omni-1.0.0-linux-x86_64"], "b" * 64)
        self.assertEqual(sums["omni-1.0.0-macos-arm64"], "c" * 64)
        self.assertEqual(len(sums), 3)


class ReplacementTests(UpdateCase):
    def test_replacing_keeps_the_previous_file_and_the_new_one_runs(self):
        target = self.bin_dir / "omni"
        target.write_text("old\n")
        staged = self.tmp / "downloaded"
        staged.write_text("new\n")
        backup = U.replace_executable(str(target), str(staged))
        self.assertEqual(target.read_text(), "new\n")
        self.assertTrue(backup and Path(backup).is_file())
        self.assertEqual(Path(backup).read_text(), "old\n")
        if POSIX:
            self.assertTrue(os.access(target, os.X_OK))

    def test_restore_puts_the_previous_file_back(self):
        target = self.bin_dir / "omni"
        target.write_text("old\n")
        staged = self.tmp / "downloaded"
        staged.write_text("new\n")
        backup = U.replace_executable(str(target), str(staged))
        U.restore(str(target), backup)
        self.assertEqual(target.read_text(), "old\n")

    def test_a_zipapp_renamed_to_omni_is_still_recognised(self):
        # What an installer does on POSIX: the .pyz becomes plain `omni`, and
        # `omni update` still has to see it as one replaceable file.
        artifact = build_artifact(self.tmp, OLD)
        target = self.stage(artifact)
        proc = self.run_omni(target, "update", "--check", "--api-url",
                             "http://127.0.0.1:1/")
        out = self.output(proc)
        self.assertIn("binary install", out)
        self.assertIn(str(target), out)

    def test_a_source_checkout_is_not_mistaken_for_a_binary(self):
        self.assertIsNone(_bundle.frozen_executable(),
                          "running from a checkout is not a single replaceable file")
        proc = self.run_omni(REPO / "omni", "update", "--check", "--api-url",
                             "http://127.0.0.1:1/")
        out = self.output(proc)
        self.assertIn("symlink install", out)
        self.assertIn(str(REPO), out)


# ------------------------------------------------------------- release channel
class ReleaseChannelTests(ArtifactCase):
    def setUp(self):
        super().setUp()
        self.github = FakeGitHub(self.tmp / "api")
        self.addCleanup(self.github.close)
        self.installed = self.stage(self.old_artifact)

    def update(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_omni(self.installed, "update", "--api-url", self.github.api, *args)

    def test_check_says_what_is_available_and_changes_nothing(self):
        self.github.publish(NEW, [self.new_artifact])
        proc = self.update("--check")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn(f"would update {OLD} -> {NEW}", out)
        self.assertIn("binary install", out)
        self.assertIn(U.zipapp_asset(NEW), out)
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {OLD}")
        self.assertFalse(self.manifest_path.exists(), "--check must not write anything")

    def test_the_release_channel_replaces_the_executable(self):
        self.github.publish(NEW, [self.new_artifact])
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("verified", out)
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {NEW}")
        record = self.manifest()
        self.assertEqual(record["mode"], "binary")
        self.assertEqual(record["channel"], "release")
        self.assertEqual(record["version"], NEW)
        self.assertEqual(record["release_tag"], f"v{NEW}")
        self.assertEqual(record["binary"], str(self.installed))
        self.assertIn(str(self.installed), record["commands"])

    def test_the_new_install_still_runs_a_program(self):
        self.github.publish(NEW, [self.new_artifact])
        self.assertEqual(self.update().returncode, 0)
        proc = self.run_omni(self.installed, "-e",
                             "use std/math\nprint('after:', sqrt(144), 6 * 7)",
                             cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, self.output(proc))
        self.assertIn("after: 12 42", proc.stdout)

    def test_a_second_update_has_nothing_to_do(self):
        self.github.publish(NEW, [self.new_artifact])
        self.assertEqual(self.update().returncode, 0)
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("up to date", out)

    def test_a_bad_checksum_stops_the_update_and_leaves_the_install_alone(self):
        self.github.publish(NEW, [self.new_artifact], sums="wrong")
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("checksum mismatch", out)
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {OLD}")
        self.assertEqual(sorted(p.name for p in self.bin_dir.iterdir()),
                         [self.installed.name], "a failed update leaves nothing behind")

    def test_a_release_without_checksums_warns_but_continues(self):
        self.github.publish(NEW, [self.new_artifact], sums="none")
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("no SHA256SUMS.txt", out)

    def test_a_repository_with_no_releases_is_not_an_error(self):
        proc = self.update("--check")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("no releases yet", out)
        self.assertIn("--channel beta", out)

    def test_a_pinned_version_is_fetched_by_its_tag(self):
        self.github.publish(NEW, [self.new_artifact])
        proc = self.update(f"--version={NEW}")
        self.assertEqual(proc.returncode, 0, self.output(proc))
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {NEW}")

    def test_a_version_that_was_never_released_is_refused(self):
        self.github.publish(NEW, [self.new_artifact])
        proc = self.update("--version=7.7.7")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("no release tagged v7.7.7", out)

    def test_an_older_release_is_not_installed_without_force(self):
        self.installed = self.stage(self.new_artifact)
        self.github.publish(OLD, [self.old_artifact])
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("older than what is installed", out)
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {NEW}")

    def test_force_goes_back_to_an_older_release(self):
        self.installed = self.stage(self.new_artifact)
        self.github.publish(OLD, [self.old_artifact])
        proc = self.update("--force")
        self.assertEqual(proc.returncode, 0, self.output(proc))
        self.assertEqual(self.run_omni(self.installed, "--version").stdout.strip(),
                         f"OmniScript {OLD}")

    def test_a_release_with_nothing_for_this_machine_says_so(self):
        other = self.tmp / "elsewhere" / "notes.txt"
        other.parent.mkdir(parents=True)
        other.write_text("not an artifact\n")
        self.github.publish(NEW, [other])
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("has no file for", out)

    def test_an_install_it_cannot_account_for_is_refused(self):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(U.format_manifest(
{"package": "omniscript-lang", "version": OLD, "mode": "mystery"}))
        self.github.publish(NEW, [self.new_artifact])
        proc = self.run_omni(REPO / "omni", "update", "--api-url", self.github.api)
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("cannot work out how OmniScript was installed", out)


# ---------------------------------------------------------------- beta channel
@unittest.skipUnless(HAS_GIT, "git is not installed")
class BetaChannelTests(ArtifactCase):
    def setUp(self):
        super().setUp()
        self.origin = make_repository(self.tmp / "origin", OLD)
        self.work = clone(self.origin, self.tmp / "work")
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(U.format_manifest(
{
            "package": "omniscript-lang", "version": OLD, "mode": "symlink",
            "channel": "beta", "source": str(self.work), "cloned_by_installer": True,
            "bin_dir": str(self.bin_dir), "commands": [str(self.work / "omni")],
            "ref": "main", "python": sys.executable,
        }))

    def publish_commit(self, version: str) -> str:
        stamp_version(self.origin, version)
        commit(self.origin, f"OmniScript {version}")
        return git(self.origin, "rev-parse", "HEAD").stdout.strip()

    def update(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_omni(REPO / "omni", "update", "--channel", "beta", *args)

    def test_the_beta_channel_fast_forwards_the_tree(self):
        head = self.publish_commit(NEW)
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("advanced", out)
        self.assertEqual(git(self.work, "rev-parse", "HEAD").stdout.strip(), head)
        reported = subprocess.run([sys.executable, str(self.work / "omni"), "--version"],
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(reported.stdout.strip(), f"OmniScript {NEW}")
        self.assertEqual(self.manifest()["version"], NEW)
        self.assertEqual(self.manifest()["channel"], "beta")

    def test_a_tree_that_is_already_current_says_so(self):
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("already at", out)

    def test_check_does_not_touch_the_tree(self):
        head = self.publish_commit(NEW)
        proc = self.update("--check")
        self.assertEqual(proc.returncode, 0, self.output(proc))
        self.assertNotEqual(git(self.work, "rev-parse", "HEAD").stdout.strip(), head)

    def test_local_changes_stop_the_update(self):
        self.publish_commit(NEW)
        (self.work / "README.local").write_text("work in progress\n")
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("local changes", out)
        self.assertTrue((self.work / "README.local").is_file())

    def test_force_updates_a_tree_with_local_changes(self):
        self.publish_commit(NEW)
        (self.work / "tracked.omni").write_text("print('mine')\n")
        git(self.work, "add", "tracked.omni")
        git(self.work, "-c", "user.name=T", "-c", "user.email=t@example.com",
            "commit", "-q", "-m", "local work")
        proc = self.update("--force")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("fast-forward", out)

    def test_a_branch_can_be_chosen(self):
        git(self.origin, "checkout", "-q", "-b", "next")
        stamp_version(self.origin, NEW)
        commit(self.origin, f"OmniScript {NEW} on next")
        git(self.origin, "checkout", "-q", "main")
        proc = self.update("--ref", "next")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(git(self.work, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
                         "next")

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        self.manifest_path.write_text(U.format_manifest(
{
            "package": "omniscript-lang", "version": OLD, "mode": "symlink",
            "channel": "beta", "source": str(self.tmp), "cloned_by_installer": True,
            "bin_dir": str(self.bin_dir), "commands": [str(self.work / "omni")],
            "ref": "main", "python": sys.executable}))
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("not a git checkout", out)

    def test_a_binary_install_is_told_the_beta_channel_needs_a_tree(self):
        installed = self.stage(self.old_artifact)
        self.isolate_from_the_manifest()
        proc = self.run_omni(installed, "update", "--channel", "beta")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("standalone executable", out)
        self.assertIn("install.sh --channel beta", out)
        self.assertFalse((Path(self.env["XDG_DATA_HOME"]) / "omniscript" / "src").exists(),
                         "it fetched a repository nobody asked for")

# ------------------------------------------------- a source tree and its release
@unittest.skipUnless(HAS_GIT, "git is not installed")
class SourceInstallTests(ArtifactCase):
    """A symlink install follows the repository it points at, and nothing else."""

    def setUp(self):
        super().setUp()
        self.origin = make_repository(self.tmp / "origin", OLD)
        self.work = clone(self.origin, self.tmp / "work")
        self.github = FakeGitHub(self.tmp / "api")
        self.addCleanup(self.github.close)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def write_manifest(self, cloned: bool) -> None:
        self.manifest_path.write_text(U.format_manifest({
            "package": "omniscript-lang", "version": OLD, "mode": "symlink",
            "channel": "release", "source": str(self.work),
            "cloned_by_installer": cloned, "bin_dir": str(self.bin_dir),
            "commands": [str(self.work / "omni")], "ref": "main",
            "python": sys.executable,
        }))

    def tag_release(self, version: str) -> None:
        stamp_version(self.origin, version)
        commit(self.origin, f"OmniScript {version}")
        git(self.origin, "tag", f"v{version}")
        self.github.publish(version, [])

    def update(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_omni(REPO / "omni", "update", "--api-url", self.github.api,
                             "--channel", "release", *args)

    def test_a_source_install_is_told_how_to_follow_a_release(self):
        self.write_manifest(cloned=False)
        self.tag_release(NEW)
        proc = self.update()
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("runs from a source tree", out)
        self.assertIn("install.sh --channel release", out)
        self.assertEqual(git(self.work, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
                         "main", "the tree was moved")
        self.assertEqual(self.manifest()["version"], OLD)

    def test_the_beta_channel_moves_the_same_tree(self):
        self.write_manifest(cloned=False)
        stamp_version(self.origin, NEW)
        commit(self.origin, f"OmniScript {NEW}")
        proc = self.run_omni(REPO / "omni", "update", "--channel", "beta")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(self.manifest()["version"], NEW)

# ------------------------------------------------------------ the build tool
class BuildToolTests(UpdateCase):
    def tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPO / "tools" / "build_executable.py"),
                               *args], capture_output=True, text=True, cwd=str(self.tmp),
                              timeout=900)

    def test_the_zipapp_it_builds_runs_and_carries_the_std_modules(self):
        out = self.tmp / "dist"
        proc = self.tool("--out", str(out), "--skip-binary")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ok   omni-", proc.stdout)
        artifact = out / U.zipapp_asset(U.VERSION)
        self.assertTrue(artifact.is_file())
        self.assertTrue(os.access(artifact, os.X_OK) or not POSIX)
        run = subprocess.run([sys.executable, str(artifact), "-e",
                              "use std/stats\nprint('std:', stdev([2, 4, 6]))"],
                             capture_output=True, text=True, cwd=str(self.tmp), timeout=180)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("std: 2", run.stdout)

    def test_the_checksums_it_writes_verify(self):
        out = self.tmp / "dist"
        self.assertEqual(self.tool("--out", str(out), "--skip-binary").returncode, 0)
        self.assertEqual(U.verify_checksums(str(out)), [])
        (out / U.zipapp_asset(U.VERSION)).write_bytes(b"corrupted\n")
        problems = U.verify_checksums(str(out))
        self.assertEqual(len(problems), 1)
        self.assertIn("does not match", problems[0])

    def test_write_checksums_covers_a_directory_of_files(self):
        out = self.tmp / "dist"
        out.mkdir()
        (out / "a.txt").write_text("a\n")
        (out / "b.bin").write_bytes(b"\x00\x01")
        proc = self.tool("--write-checksums", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = (out / "SHA256SUMS.txt").read_text().splitlines()
        self.assertEqual([line.split("  ")[1] for line in lines], ["a.txt", "b.bin"])
        self.assertEqual(U.verify_checksums(str(out)), [])

    def test_building_only_an_executable_without_pyinstaller_explains_itself(self):
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("PyInstaller is installed here, so there is nothing to report")
        proc = self.tool("--out", str(self.tmp / "dist"), "--skip-zipapp")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("PyInstaller is not installed", proc.stdout + proc.stderr)

    def test_skipping_both_artifacts_is_refused(self):
        proc = self.tool("--out", str(self.tmp / "dist"), "--skip-binary", "--skip-zipapp")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nothing to do", proc.stdout + proc.stderr)


# ----------------------------------------------------------------- the command
class CommandLineTests(UpdateCase):
    def test_help_explains_both_channels(self):
        proc = self.run_omni(REPO / "omni", "update", "--help")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 0, out)
        for word in ("release", "beta", "--check", "--api-url", "--force"):
            self.assertIn(word, out)

    def test_update_is_a_command_and_not_a_file_to_run(self):
        # `omni update` must not be read as `omni run update`.
        proc = self.run_omni(REPO / "omni", "update", "--check", "--api-url",
                             "http://127.0.0.1:1/")
        out = self.output(proc)
        self.assertIn("channel     release", out)
        self.assertNotIn("cannot open", out)

    def test_an_unknown_channel_is_refused(self):
        proc = self.run_omni(REPO / "omni", "update", "--channel", "gamma")
        self.assertEqual(proc.returncode, 2, self.output(proc))

    def test_a_server_that_cannot_be_reached_is_reported_plainly(self):
        proc = self.run_omni(REPO / "omni", "update", "--api-url",
                             "http://127.0.0.1:1/")
        out = self.output(proc)
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("could not reach", out)


if __name__ == "__main__":
    unittest.main()
