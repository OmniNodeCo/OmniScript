from __future__ import annotations

import os
import platform
import unittest
from pathlib import Path

from scripts.build_executable import validate_target


ROOT = Path(__file__).resolve().parent.parent


class DistributionTests(unittest.TestCase):
    def test_release_workflow_covers_supported_targets(self) -> None:
        workflow = (ROOT / "build.yml").read_text(encoding="utf-8")
        expected = {
            "omni-linux-x86_64",
            "omni-linux-arm64",
            "omni-macos-x86_64",
            "omni-macos-arm64",
            "omni-windows-x86_64.exe",
            "omni-windows-arm64.exe",
        }
        for asset in expected:
            self.assertIn(f"asset: {asset}", workflow)
        self.assertIn("SHA256SUMS", workflow)

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

    def test_builder_rejects_a_mislabeled_native_asset(self) -> None:
        system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}[platform.system()]
        with self.assertRaises(SystemExit):
            validate_target(f"omni-{system}-not-this-machine")


if __name__ == "__main__":
    unittest.main()
