#!/usr/bin/env python3
"""Rehearse a release: install what is in dist/ the way a user would, then remove it.

    python3 tools/build_executable.py --out dist
    python3 tools/rehearse_release.py --dist dist --prefix /tmp/omni-rehearsal

This is the last check before a tag goes up. It lays the built files out as a
GitHub release (see make_release_fixture.py), points the installer for this
platform at that fixture, and then walks the whole life of an installation:

    1. install.sh --channel release   /   install.ps1 -Channel release
    2. the command it installed reports the version that was built
    3. it runs a program, including a `use std/...` import
    4. `omni update --check` reads the same release and says it is up to date
    5. the uninstaller takes everything back out and leaves nothing behind

Every step says what it found. Under GitHub Actions a failure is also written as
a workflow annotation, so it is readable without the job log.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from make_release_fixture import build as build_fixture  # noqa: E402

from omniscript import __version__  # noqa: E402

WINDOWS = os.name == "nt"
PROGRAM = "use std/stats\nprint(\"rehearsal:\", 6 * 7, stdev([2, 4, 6]))"
EXPECTED = "rehearsal: 42 2"


def annotate(message: str) -> None:
    """Say it loudly, and in CI say it where the annotations will carry it."""
    print(message, flush=True)
    if os.environ.get("GITHUB_ACTIONS"):
        flat = message.replace("\r", " ").replace("\n", " | ")[:1800]
        print(f"::error file=tools/rehearse_release.py,line=1::{flat}", flush=True)


def show(label: str, proc: subprocess.CompletedProcess) -> str:
    out = (proc.stdout or "") + (proc.stderr or "")
    print(f"--- {label} (exit {proc.returncode}) ---", flush=True)
    for line in out.strip().splitlines()[-40:]:
        print(f"    {line}", flush=True)
    return out


def run(command: list[str], env: dict, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd,
                          timeout=900)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dist", required=True, help="the directory of built release files")
    p.add_argument("--prefix", default="", help="where to install [a temporary directory]")
    p.add_argument("--version", default=__version__, help="the version being rehearsed")
    p.add_argument("--keep", action="store_true", help="leave the rehearsal directory behind")
    p.add_argument("--skip-uninstall", action="store_true", help="stop after installing")
    args = p.parse_args(argv)

    dist = os.path.abspath(args.dist)
    if not os.path.isdir(dist):
        annotate(f"there is no directory at {dist}")
        return 1
    files = sorted(n for n in os.listdir(dist) if os.path.isfile(os.path.join(dist, n)))
    print(f"rehearsing a release of OmniScript {args.version}")
    print(f"    files: {', '.join(files)}")
    if not files:
        annotate(f"{dist} is empty; build the artifacts first")
        return 1

    work = os.path.abspath(args.prefix) if args.prefix else tempfile.mkdtemp(prefix="omni-rehearsal-")
    prefix = os.path.join(work, "prefix")
    home = os.path.join(work, "home")
    fixture = os.path.join(work, "release")
    os.makedirs(prefix, exist_ok=True)
    os.makedirs(os.path.join(home, "data"), exist_ok=True)

    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    env["XDG_DATA_HOME"] = os.path.join(home, "data")
    env["LOCALAPPDATA"] = os.path.join(home, "appdata")
    env.pop("OMNISCRIPT_MANIFEST", None)
    env.pop("OMNISCRIPT_API_URL", None)

    api = build_fixture(dist, fixture, "OmniNodeCo/OmniScript", args.version, "")
    print(f"    release laid out at {fixture}")
    print(f"    installing into {prefix} from {api}")

    problems: list[str] = []
    bin_dir = prefix if WINDOWS else os.path.join(prefix, "bin")
    command = os.path.join(bin_dir, "omni.exe" if WINDOWS else "omni")
    if WINDOWS:
        installer = ["pwsh", "-NoProfile", "-File", os.path.join(ROOT, "install.ps1"),
                     "-Channel", "release", "-ApiUrl", api, "-Prefix", prefix]
        remover = ["pwsh", "-NoProfile", "-File", os.path.join(ROOT, "uninstall.ps1"),
                   "-Prefix", prefix, "-Purge"]
    else:
        bash = shutil.which("bash") or "/bin/bash"
        installer = [bash, os.path.join(ROOT, "install.sh"), "--channel", "release",
                     "--api-url", api, "--prefix", prefix]
        remover = [bash, os.path.join(ROOT, "uninstall.sh"), "--prefix", prefix, "--purge"]

    # 1. install
    proc = run(installer, env, work)
    out = show("install", proc)
    if proc.returncode != 0:
        problems.append("the installer failed")
    else:
        if "sha256 verified" not in out and "unchecked" not in out:
            problems.append("the installer never mentioned the checksum")
        if not os.path.exists(command):
            # A .pyz release on Windows lands as omni.pyz behind an omni.cmd shim.
            alternate = os.path.join(bin_dir, "omni.cmd" if WINDOWS else "omni.pyz")
            if os.path.exists(alternate):
                command = alternate
            else:
                problems.append(f"no command was left at {command}")

    if not problems:
        runner = [command]
        if command.endswith((".pyz", ".cmd")):
            runner = ([sys.executable, command] if command.endswith(".pyz")
                      else [os.environ.get("ComSpec", "cmd.exe"), "/c", command])

        # 2. the version it reports
        proc = run([*runner, "--version"], env, work)
        out = show("version", proc)
        if proc.returncode != 0 or f"OmniScript {args.version}" not in out:
            problems.append(f"the installed command does not report OmniScript {args.version}")

        # 3. a program, with a std module that lives inside the artifact
        proc = run([*runner, "-e", PROGRAM], env, work)
        out = show("program", proc)
        if proc.returncode != 0 or EXPECTED not in out:
            problems.append(f"the installed command did not run a program (wanted {EXPECTED!r})")

        # 4. it can see the release it came from
        proc = run([*runner, "update", "--check"], env, work)
        out = show("update --check", proc)
        if proc.returncode != 0:
            problems.append("omni update --check failed")
        elif "up to date" not in out:
            problems.append("omni update --check did not recognise the release it came from")

    # 5. and it can all be taken back out
    if not args.skip_uninstall and not problems:
        proc = run(remover, env, work)
        show("uninstall", proc)
        if proc.returncode != 0:
            problems.append("the uninstaller failed")
        elif os.path.exists(command):
            problems.append(f"{command} survived the uninstall")
        else:
            left = [n for n in os.listdir(bin_dir)] if os.path.isdir(bin_dir) else []
            left = [n for n in left if not n.endswith(".bak")]
            if left:
                problems.append(f"the uninstall left {left} in {bin_dir}")

    if not args.keep and not args.prefix:
        shutil.rmtree(work, ignore_errors=True)

    if problems:
        for problem in problems:
            annotate(f"release rehearsal: {problem}")
        return 1
    print("release rehearsal ok: installed, ran, saw its own release, and uninstalled clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
