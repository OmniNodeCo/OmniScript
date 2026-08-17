from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from omniscript.cli import main
from omniscript.updater import (
    UpdateCheckError,
    UpdateInfo,
    _installer_environment,
    cache_directory,
    check_for_updates,
    clear_update_cache,
    is_newer_version,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class UpdaterTests(unittest.TestCase):
    def test_semantic_version_comparison(self) -> None:
        self.assertTrue(is_newer_version("0.3.0", "0.1.9"))
        self.assertTrue(is_newer_version("1.0.0", "1.0.0-rc.1"))
        self.assertFalse(is_newer_version("v0.1.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0-beta.2", "0.1.0"))
        with self.assertRaises(UpdateCheckError):
            is_newer_version("nightly", "0.1.0")

    def test_missing_release_is_a_valid_result(self) -> None:
        def missing(request, timeout):
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"OMNISCRIPT_CACHE_DIR": temporary}):
                info = check_for_updates("0.1.0", force=True, opener=missing)
                self.assertFalse((Path(temporary) / "update.json").exists())
        self.assertFalse(info.release_found)
        self.assertFalse(info.update_available)

    def test_stale_negative_cache_never_hides_a_new_github_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_file = Path(temporary) / "update.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "repository": "OmniNodeCo/OmniScript",
                        "latest_version": "0.1.0",
                        "release_url": "https://example.test/releases",
                        "checked_at": 100.0,
                        "release_found": False,
                    }
                ),
                encoding="utf-8",
            )
            calls = 0

            def opener(_request, timeout):
                nonlocal calls
                calls += 1
                return FakeResponse(
                    [
                        {
                            "tag_name": "v0.3.0",
                            "html_url": "https://example.test/v0.3.0",
                            "draft": False,
                            "prerelease": False,
                        }
                    ]
                )

            with patch.dict(os.environ, {"OMNISCRIPT_CACHE_DIR": temporary}):
                info = check_for_updates("0.2.0", opener=opener, now=lambda: 101.0)
            self.assertEqual(calls, 1)
            self.assertTrue(info.release_found)
            self.assertEqual(info.latest_version, "0.3.0")

    def test_update_response_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"OMNISCRIPT_CACHE_DIR": temporary}):
                calls = 0

                def opener(request, timeout):
                    nonlocal calls
                    self.assertEqual(timeout, 10)
                    self.assertIn("api.github.com/repos/OmniNodeCo/OmniScript/releases?per_page=20", request.full_url)
                    calls += 1
                    return FakeResponse(
                        [
                            {
                                "tag_name": "v0.3.0-beta.1",
                                "html_url": "https://example.test/v0.3.0-beta.1",
                                "draft": False,
                                "prerelease": True,
                            },
                            {
                                "tag_name": "v0.3.0",
                                "html_url": "https://github.com/OmniNodeCo/OmniScript/releases/tag/v0.3.0",
                                "draft": False,
                                "prerelease": False,
                            },
                        ]
                    )

                fresh = check_for_updates("0.1.0", opener=opener, now=lambda: 100.0)
                cached = check_for_updates("0.1.0", opener=opener, now=lambda: 101.0)
                self.assertTrue(fresh.update_available)
                self.assertFalse(fresh.from_cache)
                self.assertTrue(cached.from_cache)
                self.assertEqual(calls, 1)
                self.assertTrue((Path(temporary) / "update.json").exists())
                self.assertTrue(clear_update_cache())
                self.assertFalse(clear_update_cache())

    def test_cli_update_json_and_cache_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_file = Path(temporary) / "update.json"
            cache_file.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"OMNISCRIPT_CACHE_DIR": temporary}):
                with patch("omniscript.cli.check_for_updates") as check:
                    check.return_value = check_for_updates(
                        "0.1.0",
                        force=True,
                        opener=lambda *_args, **_kwargs: FakeResponse(
                            {
                                "tag_name": "v0.1.0",
                                "html_url": "https://example.test/release",
                            }
                        ),
                        now=lambda: 20.0,
                    )
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(main(["update", "--json"]), 0)
                    payload = json.loads(output.getvalue())
                    self.assertFalse(payload["update_available"])

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["update", "--clear-cache"]), 0)
                self.assertIn("cleared", output.getvalue())

    def test_interactive_update_can_choose_nightly(self) -> None:
        output = io.StringIO()
        info = UpdateInfo(
            current_version="0.3.0",
            latest_version="0.1.0",
            update_available=False,
            release_url="https://github.com/OmniNodeCo/OmniScript/releases/tag/v0.1.0",
            checked_at=1.0,
        )
        with patch("builtins.input", return_value="2"):
            with patch("omniscript.cli.check_for_updates", return_value=info) as check:
                with patch("omniscript.cli.install_update", return_value="nightly installed") as install:
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(main(["update"]), 0)
        check.assert_called_once_with("0.3.0", force=False)
        install.assert_called_once_with("nightly", "0.3.0")
        self.assertIn("Checking GitHub Releases", output.getvalue())
        self.assertIn("Latest GitHub release: 0.1.0", output.getvalue())
        self.assertIn("nightly installed", output.getvalue())

    def test_nightly_remains_available_when_github_release_check_fails(self) -> None:
        output = io.StringIO()
        with patch("builtins.input", return_value="2"):
            with patch("omniscript.cli.check_for_updates", side_effect=UpdateCheckError("offline")):
                with patch("omniscript.cli.install_update", return_value="nightly installed") as install:
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(main(["update"]), 0)
        install.assert_called_once_with("nightly", "0.3.0")
        self.assertIn("GitHub release check failed: offline", output.getvalue())

    def test_explicit_release_channel_installs_latest_release(self) -> None:
        info = UpdateInfo(
            current_version="0.3.0",
            latest_version="0.3.0",
            update_available=False,
            release_url="https://example.test/v0.3.0",
            checked_at=1.0,
        )
        with patch("omniscript.cli.check_for_updates", return_value=info):
            with patch("omniscript.cli.install_update", return_value="release installed") as install:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["update", "--channel", "release"]), 0)
        install.assert_called_once_with("release", "0.3.0")

    def test_release_downgrade_requires_confirmation(self) -> None:
        info = UpdateInfo(
            current_version="0.3.0",
            latest_version="0.1.0",
            update_available=False,
            release_url="https://example.test/v0.1.0",
            checked_at=1.0,
        )
        with patch("omniscript.cli.check_for_updates", return_value=info):
            with patch("builtins.input", return_value="n"):
                with patch("omniscript.cli.install_update") as install:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main(["update", "--channel", "release"]), 0)
        install.assert_not_called()

    def test_installer_environment_resets_pyinstaller_bootloader_state(self) -> None:
        inherited = {
            "_PYI_ARCHIVE_FILE": "old-omni.exe",
            "_PYI_APPLICATION_HOME_DIR": "old-temp",
            "UNCHANGED_VALUE": "yes",
        }
        with patch.dict(os.environ, inherited, clear=True):
            environment = _installer_environment("nightly", "0.3.0")
        self.assertNotIn("_PYI_ARCHIVE_FILE", environment)
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", environment)
        self.assertEqual(environment["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertEqual(environment["OMNISCRIPT_CHANNEL"], "nightly")
        self.assertEqual(environment["UNCHANGED_VALUE"], "yes")

    def test_cache_directory_override(self) -> None:
        with patch.dict(os.environ, {"OMNISCRIPT_CACHE_DIR": "/tmp/custom-omni-cache"}):
            self.assertEqual(cache_directory(), Path("/tmp/custom-omni-cache"))


if __name__ == "__main__":
    unittest.main()
