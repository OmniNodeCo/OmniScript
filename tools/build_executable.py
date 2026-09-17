#!/usr/bin/env python3
"""Build the files a release attaches: a standalone executable and a zipapp.

    python3 tools/build_executable.py                 # both, into dist/
    python3 tools/build_executable.py --out /tmp/out --skip-binary
    python3 tools/build_executable.py --write-checksums dist

Two artifacts come out, named so an installer on any platform can pick the
right one without asking a server what it runs:

    omni-1.1.0-linux-x86_64        a standalone executable, no Python needed
    omni-1.1.0-any.pyz             one file, runs on any Python 3.10+

The executable needs PyInstaller (`pip install pyinstaller`); the zipapp needs
nothing at all. Every artifact is smoke-tested from outside the repository --
version, a shell command, a drawing and the python import -- the parts that
breaks if the bundled data files go missing -- and SHA256SUMS.txt is written
over whatever ends up in the output directory.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import NoReturn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from omniscript import VERSION as __version__  # noqa: E402
from omniscript.update import (platform_tag, verify_checksums,  # noqa: E402
                               write_checksums)

WINDOWS = os.name == "nt"
MAIN_PY = """\
import sys

from omniscript.cli import main

if __name__ == "__main__":
    sys.exit(main())
"""

# What every artifact has to be able to do, run from a directory that is not the
# repository. The std import matters most: it is the one that fails silently when
# the .omni files are left out of the bundle.
SMOKE = [
    ("--version", "version", None),
    ("-e", "run", 'cmd("echo smoke: 42")'),
    ("-e", "python", 'import python\npython("print(6 * 7)")'),
    ("-e", "graphics", 'draw(window(16, 16, "smoke"), rect(0, 0, 16, 16, "#0d1117"),\n'
                       'circle(8, 8, 6, "#2ea043"), save("smoke.png"))'),
    ("-e", "gui", 'draw_gui.window_size(16, 16, "smoke")\n'
                  'draw_gui.button(pos=(2, 2), text="Go")\n'
                  'draw_gui(save("gsmoke.png"))'),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def annotate(msg: str) -> None:
    """In CI, say it where it can be read without the job log."""
    if os.environ.get("GITHUB_ACTIONS"):
        flat = msg.replace("\r", " ").replace("\n", " | ")[:1800]
        print(f"::error file=tools/build_executable.py,line=1::{flat}", flush=True)


def fail(msg: str) -> NoReturn:
    print(f"build_executable.py: error: {msg}", file=sys.stderr, flush=True)
    annotate(f"build_executable.py: {msg}")
    raise SystemExit(1)


# ------------------------------------------------------------------ artifacts
def zipapp_name(version: str) -> str:
    return f"omni-{version}-any.pyz"


def binary_name(version: str, tag: str | None = None) -> str:
    tag = tag or platform_tag()
    return f"omni-{version}-{tag}" + (".exe" if WINDOWS else "")


def build_zipapp(target: str) -> str:
    """One file containing the package and a two-line entry point."""
    import zipapp

    staging = tempfile.mkdtemp(prefix="omni-pyz-")
    try:
        shutil.copytree(os.path.join(ROOT, "omniscript"),
                        os.path.join(staging, "omniscript"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with open(os.path.join(staging, "__main__.py"), "w", encoding="utf-8") as fh:
            fh.write(MAIN_PY)
        zipapp.create_archive(staging, target, interpreter="/usr/bin/env python3",
                              compressed=True)
    finally:
        shutil.rmtree(staging, True)
    if not WINDOWS:
        os.chmod(target, 0o755)
    return target


def build_binary(target: str, keep: bool = False) -> str:
    """A standalone executable, via PyInstaller."""
    if shutil.which("pyinstaller") is None and not _module_available("PyInstaller"):
        fail("PyInstaller is not installed; run `pip install pyinstaller`, "
             "or pass --skip-binary to build only the zipapp")

    work = tempfile.mkdtemp(prefix="omni-bin-")
    entry = os.path.join(work, "omni_entry.py")
    with open(entry, "w", encoding="utf-8") as fh:
        fh.write(MAIN_PY)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--clean", "--noconfirm",
        "--log-level", "WARN",
        "--name", "omni",
        "--distpath", os.path.join(work, "dist"),
        "--workpath", os.path.join(work, "build"),
        "--specpath", work,
        "--paths", ROOT,
        entry,
    ]
    log("    " + " ".join(_quote(part) for part in cmd))
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-25:])
        shutil.rmtree(work, True)
        fail(f"PyInstaller failed:\n{tail}")

    built = os.path.join(work, "dist", "omni.exe" if WINDOWS else "omni")
    if not os.path.isfile(built):
        shutil.rmtree(work, True)
        fail(f"PyInstaller reported success but produced no {built}")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.move(built, target)
    if not WINDOWS:
        os.chmod(target, 0o755)
    if keep:
        log(f"    build tree kept at {work}")
    else:
        shutil.rmtree(work, True)
    return target


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _quote(part: str) -> str:
    return f'"{part}"' if " " in part or part.endswith("/std") else part


# ---------------------------------------------------------------- smoke tests
def command_for(artifact: str) -> list[str]:
    """How to run an artifact: a .pyz needs an interpreter, a binary does not."""
    if artifact.endswith(".pyz"):
        return [sys.executable, artifact]
    return [artifact]


def smoke_test(artifact: str) -> list[str]:
    """Run an artifact from a directory that is not the repository.

    Returns a list of complaints; empty means it passed.
    """
    problems = []
    runner = command_for(artifact)
    cwd = tempfile.mkdtemp(prefix="omni-smoke-")
    try:
        for flags, label, code in SMOKE:
            argv = list(runner) + ([flags, code] if code else [flags])
            proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                  timeout=180)
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                problems.append(f"{label}: exit {proc.returncode}\n{out[-500:]}")
                continue
            if label == "version":
                want = f"OmniScript {__version__}"
                if want not in out:
                    problems.append(f"version: reported {out!r}, wanted {want!r}")
            elif label == "run" and "smoke: 42" not in out:
                problems.append(f"run: unexpected output {out!r}")
            elif label == "python" and "42" not in out:
                problems.append(f"python: the import did not run: {out!r}")
            elif label == "graphics":
                png = os.path.join(cwd, "smoke.png")
                if not os.path.isfile(png):
                    problems.append(f"graphics: no PNG was written ({out!r})")
                else:
                    bad = check_png(png)
                    if bad:
                        problems.append(f"graphics: {bad}")
            elif label == "gui":
                if 'window size 16x16 "smoke"' not in out:
                    problems.append(f"gui: window_size said {out!r}")
                elif "added button 'Go' at (2, 2)" not in out:
                    problems.append(f"gui: button said {out!r}")
                png = os.path.join(cwd, "gsmoke.png")
                if not os.path.isfile(png):
                    problems.append(f"gui: no PNG was written ({out!r})")
                else:
                    bad = check_png(png)
                    if bad:
                        problems.append(f"gui: {bad}")
    except subprocess.TimeoutExpired:
        problems.append("timed out after 180s")
    finally:
        shutil.rmtree(cwd, True)
    return problems


def check_png(path: str) -> str:
    """Decode the PNG chunk by chunk; '' means it is a well-formed picture."""
    import struct
    import zlib

    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "missing PNG signature"
    pos, seen, pixels = 8, [], 0
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            return f"bad CRC in the {kind.decode('latin1')} chunk"
        seen.append(kind.decode("latin1"))
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
            pixels = width * height
        pos += 12 + length
    if seen[:1] != ["IHDR"] or "IDAT" not in seen or seen[-1:] != ["IEND"]:
        return f"chunk order is wrong: {seen}"
    if pixels <= 0:
        return "the header claims a picture with no pixels"
    return ""


# Checksums live in omniscript.update, so what a release writes and what
# `omni update` reads can never drift apart.


# ------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="build the OmniScript release artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Artifact names:\n"
               f"  {binary_name(__version__)}\n  {zipapp_name(__version__)}\n")
    p.add_argument("--out", default=os.path.join(ROOT, "dist"),
                   help="where to write the artifacts   [dist/]")
    p.add_argument("--version", default=__version__,
                   help="version to put in the file names")
    p.add_argument("--platform", default=None,
                   help="platform tag to put in the executable's name "
                        f"[{platform_tag()}]")
    p.add_argument("--skip-binary", action="store_true",
                   help="build only the zipapp (no PyInstaller needed)")
    p.add_argument("--skip-zipapp", action="store_true", help="build only the executable")
    p.add_argument("--no-smoke", action="store_true", help="do not run the artifacts")
    p.add_argument("--no-checksums", action="store_true",
                   help="leave SHA256SUMS.txt alone")
    p.add_argument("--keep-temp", action="store_true", help="keep the build tree")
    p.add_argument("--write-checksums", metavar="DIR",
                   help="write SHA256SUMS.txt over DIR and exit")
    args = p.parse_args(argv)

    if args.write_checksums:
        target = write_checksums(args.write_checksums)
        log(f"wrote {target}")
        print(open(target, encoding="utf-8").read(), end="")
        return 0

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    version = args.version
    built: list[str] = []
    failures: list[str] = []

    log(f"OmniScript {version} on {platform_tag()} "
        f"(Python {platform.python_version()})")

    if not args.skip_zipapp:
        target = os.path.join(out, zipapp_name(version))
        log(f"building the zipapp: {os.path.basename(target)}")
        build_zipapp(target)
        log(f"    {os.path.getsize(target):,} bytes")
        built.append(target)

    if not args.skip_binary:
        target = os.path.join(out, binary_name(version, args.platform))
        log(f"building the executable: {os.path.basename(target)}")
        build_binary(target, keep=args.keep_temp)
        log(f"    {os.path.getsize(target):,} bytes")
        built.append(target)

    if not built:
        fail("nothing to do: --skip-binary and --skip-zipapp were both given")

    if not args.no_smoke:
        log("smoke-testing every artifact from outside the repository")
        for artifact in built:
            problems = smoke_test(artifact)
            name = os.path.basename(artifact)
            if problems:
                failures.append(name)
                log(f"    FAIL {name}")
                for problem in problems:
                    print("      " + problem.replace("\n", "\n      "), flush=True)
            else:
                log(f"    ok   {name} ({len(SMOKE)} checks)")

    if not args.no_checksums:
        sums = write_checksums(out)
        with open(sums, encoding="utf-8") as fh:
            covered = len(fh.read().splitlines())
        log(f"wrote {os.path.basename(sums)} covering {covered} file(s)")
        problems = verify_checksums(out)
        if problems:
            fail("the checksums just written do not verify: " + "; ".join(problems))

    if failures:
        fail(f"{len(failures)} artifact(s) failed their smoke test: {', '.join(failures)}")
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
