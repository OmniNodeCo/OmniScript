#!/usr/bin/env python3
"""Generate the release notes the way release.yml will, and complain if they break.

    python3 tools/check_release_notes.py

The notes are a heredoc full of `__PLACEHOLDERS__`, a `sed` that fills them in,
and a second file spliced into the middle with `sed /__FILES__/r`. None of that
runs until a tag is pushed, which is exactly when you do not want to find out a
placeholder was renamed. So this lifts the two steps straight out of
release.yml -- no copy of them to drift -- runs them against a directory of
pretend artifacts, and checks the result:

  * every placeholder was substituted, and no expression was left unexpanded
  * the file list landed in the middle of the notes, describing each artifact
  * the numbers, the repository and the tag all appear
  * the code fences still balance, so the page renders

Needs PyYAML (the `lint` job installs it); outside CI it says so and passes.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
STEPS = ("Describe the files for the notes", "Write the release notes")
ARTIFACTS = (
    "omni-9.9.9-linux-x86_64",
    "omni-9.9.9-windows-x86_64.exe",
    "omni-9.9.9-macos-arm64",
    "omni-9.9.9-any.pyz",
    "omniscript_lang-9.9.9-py3-none-any.whl",
    "omniscript_lang-9.9.9.tar.gz",
    "SHA256SUMS.txt",
)
VALUES = {
    "needs.verify.outputs.version": "9.9.9",
    "github.repository": "OmniNodeCo/OmniScript",
    "github.event.inputs.tag || github.ref_name": "v9.9.9",
    "needs.build.outputs.loc": "11,055",
    "needs.build.outputs.builtins": "298",
    "needs.build.outputs.examples": "10",
    "needs.build.outputs.cases": "34",
    "needs.build.outputs.pythons": "3.10 to 3.14",
}


def fail(message: str) -> None:
    print(f"check_release_notes.py: error: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        flat = " | ".join(line.strip() for line in message.splitlines() if line.strip())
        print(f"::error file=tools/check_release_notes.py,line=1::{flat[:1800]}")
    raise SystemExit(1)


def load_steps() -> dict[str, str]:
    try:
        import yaml
    except ImportError:
        print("PyYAML is not installed, so there is nothing to check against; skipping")
        raise SystemExit(0) from None
    workflow = yaml.safe_load(WORKFLOW.read_text())
    runs = {step["name"]: step["run"]
            for step in workflow["jobs"]["release"]["steps"] if "run" in step}
    for name in STEPS:
        if name not in runs:
            fail(f"release.yml has no {name!r} step any more; this check has gone stale")
    return runs


def expand(script: str, files_path: str) -> str:
    script = script.replace("${{ steps.files.outputs.path }}", files_path)
    for key, value in VALUES.items():
        script = script.replace("${{ " + key + " }}", value)
    if "${{" in script:
        line = next(ln for ln in script.splitlines() if "${{" in ln)
        fail(f"release.yml uses an expression this check does not fill in:\n    {line.strip()}")
    return script


def run_step(script: str, work: str, files_path: str = "") -> str:
    output = os.path.join(work, "step-output")
    pathlib.Path(output).write_text("")
    env = dict(os.environ, RUNNER_TEMP=work, GITHUB_OUTPUT=output)
    proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=work, env=env,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode:
        fail(f"a release-notes step exited {proc.returncode}\n"
             f"{proc.stdout[-2000:]}{proc.stderr[-1500:]}")
    produced = {}
    for line in pathlib.Path(output).read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            produced[key] = value
    return produced.get("path", "")


def main() -> int:
    runs = load_steps()
    with tempfile.TemporaryDirectory(prefix="omni-notes-") as work:
        dist = pathlib.Path(work) / "dist"
        dist.mkdir()
        for name in ARTIFACTS:
            (dist / name).write_bytes(b"x" * 4096)

        files_path = run_step(expand(runs[STEPS[0]], ""), work)
        if not files_path or not pathlib.Path(files_path).is_file():
            fail(f"the file list step did not leave a list behind (got {files_path!r})")
        listing = pathlib.Path(files_path).read_text()
        for name in ARTIFACTS:
            if name != "SHA256SUMS.txt" and name not in listing:
                fail(f"the file list does not mention {name}:\n{listing}")

        notes_path = run_step(expand(runs[STEPS[1]], files_path), work, files_path)
        if not notes_path or not pathlib.Path(notes_path).is_file():
            fail(f"the notes step did not write any notes (got {notes_path!r})")
        notes = pathlib.Path(notes_path).read_text()

    left = sorted(set(re.findall(r"__[A-Z_]+__", notes)))
    if left:
        fail(f"placeholders were never substituted: {', '.join(left)}\n{notes[:1200]}")
    for fragment in ("OmniScript 9.9.9", "OmniNodeCo/OmniScript", "v9.9.9", "11,055",
                     "298 built-ins", "omni-9.9.9-any.pyz", "omni-9.9.9-linux-x86_64",
                     "no Python needed", "sha256sum -c SHA256SUMS.txt", "omni update"):
        if fragment not in notes:
            fail(f"the notes lost {fragment!r}\n{notes[:1500]}")
    if notes.count("```") % 2:
        fail(f"the notes have an unbalanced code fence ({notes.count('```')} of them)")
    if "__FILES__" in notes or "What is attached\n\n\n" in notes:
        fail("the file list was not spliced into the notes")
    # Every artifact has to be listed in its own section -- some of these names
    # also appear earlier in the notes, so look for them after the heading.
    attached, history = notes.index("What is attached"), notes.index("Source history")
    for name in ARTIFACTS:
        if name == "SHA256SUMS.txt":
            continue
        position = notes.find(name, attached)
        if not attached < position < history:
            fail(f"{name} is not listed between 'What is attached' and the source history")

    print(f"release notes ok -- {len(notes.splitlines())} lines, {len(notes):,} bytes, "
          f"{len(ARTIFACTS) - 1} artifacts described")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
