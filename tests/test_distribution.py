from __future__ import annotations

import os
import platform
import unittest
from pathlib import Path

from scripts.build_executable import validate_target
from scripts.verify_release import verify


ROOT = Path(__file__).resolve().parent.parent


class DistributionTests(unittest.TestCase):
    def test_build_and_release_workflows_cover_supported_targets(self) -> None:
        build_workflow = (ROOT / "build.yml").read_text(encoding="utf-8")
        release_workflow = (ROOT / "release.yml").read_text(encoding="utf-8")
        expected = {
            "omni-linux-x86_64",
            "omni-linux-arm64",
            "omni-macos-arm64",
            "omni-windows-x86_64.exe",
            "omni-windows-arm64.exe",
        }
        for asset in expected:
            self.assertIn(f"asset: {asset}", build_workflow)
            self.assertIn(f"asset: {asset}", release_workflow)
        self.assertNotIn("softprops/action-gh-release", build_workflow)
        self.assertIn("SHA256SUMS", release_workflow)
        self.assertIn("scripts/verify_release.py", release_workflow)

    def test_root_and_script_installers_match(self) -> None:
        self.assertEqual(
            (ROOT / "install.sh").read_bytes(),
            (ROOT / "scripts/install.sh").read_bytes(),
        )
        self.assertEqual(
            (ROOT / "install.bat").read_bytes(),
            (ROOT / "scripts/install.bat").read_bytes(),
        )
        if os.name != "nt":
            self.assertTrue(os.access(ROOT / "install.sh", os.X_OK))
        self.assertIn("OMNISCRIPT_CACHE_DIR", (ROOT / "scripts/uninstall.sh").read_text())
        self.assertIn("OMNISCRIPT_CACHE_DIR", (ROOT / "scripts/uninstall.ps1").read_text())

    def test_builder_rejects_a_mislabeled_native_asset(self) -> None:
        system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}[platform.system()]
        with self.assertRaises(SystemExit):
            validate_target(f"omni-{system}-not-this-machine")

    def test_release_tag_must_match_declared_version(self) -> None:
        self.assertEqual(verify("v0.2.1"), "0.2.1")
        with self.assertRaises(SystemExit):
            verify("v9.9.9")


if __name__ == "__main__":
    unittest.main()
