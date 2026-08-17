#!/usr/bin/env python3
"""Build one self-contained OmniScript executable with PyInstaller."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def validate_target(asset: str) -> None:
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(platform.system())
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        architecture = "arm64"
    elif machine in {"amd64", "x86_64"}:
        architecture = "x86_64"
    else:
        architecture = machine
    if system and f"-{system}-" in asset and f"-{system}-{architecture}" not in asset:
        raise SystemExit(
            f"asset name {asset!r} does not match build host {platform.system()} {platform.machine()}"
        )


def build(name: str, asset: str, output: Path) -> Path:
    validate_target(asset)
    root = Path(__file__).resolve().parent.parent
    entry = root / "scripts" / "omni_entry.py"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="omniscript-build-") as temporary:
        work = Path(temporary)
        dist = work / "dist"
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--hidden-import",
            "tkinter",
            "--hidden-import",
            "tkinter.ttk",
            "--hidden-import",
            "tkinter.messagebox",
            "--hidden-import",
            "tkinter.filedialog",
            "--hidden-import",
            "tkinter.colorchooser",
            "--name",
            name,
            "--distpath",
            str(dist),
            "--workpath",
            str(work / "work"),
            "--specpath",
            str(work / "spec"),
            "--paths",
            str(root / "src"),
            str(entry),
        ]
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=root, check=True)

        generated_name = f"{name}.exe" if os.name == "nt" else name
        generated = dist / generated_name
        if not generated.is_file():
            raise SystemExit(f"PyInstaller did not produce {generated}")
        destination = output / asset
        shutil.copy2(generated, destination)

    if os.name != "nt":
        destination.chmod(destination.stat().st_mode | 0o755)
    print(f"Built {destination} ({destination.stat().st_size:,} bytes)")
    print(f"Smoke testing {destination} --version", flush=True)
    completed = subprocess.run(
        [str(destination), "--version"],
        check=True,
        text=True,
        capture_output=True,
    )
    print(completed.stdout.strip())
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="omni", help="internal executable name")
    parser.add_argument("--asset", help="final release asset filename")
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    arguments = parser.parse_args()
    asset = arguments.asset or (f"{arguments.name}.exe" if os.name == "nt" else arguments.name)
    build(arguments.name, asset, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
