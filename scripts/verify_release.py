#!/usr/bin/env python3
"""Verify that a release tag matches every OmniScript version declaration."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def declared_versions() -> dict[str, str]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "src/omniscript/__init__.py").read_text(encoding="utf-8")
    project_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    package_match = re.search(r'^__version__\s*=\s*"([^"]+)"', package, re.MULTILINE)
    if not project_match or not package_match:
        raise SystemExit("could not locate OmniScript version declarations")
    return {
        "pyproject.toml": project_match.group(1),
        "src/omniscript/__init__.py": package_match.group(1),
    }


def verify(tag: str) -> str:
    version = tag.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise SystemExit(f"release tag {tag!r} must look like v1.2.3 or v1.2.3-beta.1")
    mismatches = [f"{path} declares {value}" for path, value in declared_versions().items() if value != version]
    if mismatches:
        raise SystemExit(f"release tag {tag} does not match: " + "; ".join(mismatches))
    print(f"Release version verified: {tag}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    arguments = parser.parse_args()
    verify(arguments.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
