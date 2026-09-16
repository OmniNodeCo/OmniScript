"""Shared scaffolding for the tests that talk to a release.

Not a test module -- `unittest discover` only picks up `test*.py`. It holds the
three things several suites need:

* `FakeGitHub` -- a directory laid out like api.github.com, served from
  localhost, so the release channel can be exercised over real HTTP with real
  JSON and real checksums without a network.
* `build_artifact` -- a runnable single-file OmniScript that reports whatever
  version you ask for, built from a copy of this tree with that version stamped
  into it. An update that quietly did nothing is caught by what it reports after.
* `make_repository` / `commit` / `stamp_version` -- a real git repository on
  disk, which is what the beta channel pulls from.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from omniscript import update as U  # noqa: E402

OLD = "1.0.0"
NEW = "9.9.9"
FILES_COPIED = ("omniscript", "tools", "omni", "install.sh", "uninstall.sh",
                "install.ps1", "uninstall.ps1", "pyproject.toml")


class QuietHandler(SimpleHTTPRequestHandler):
    """A static file server; a directory is answered from its `.json` twin.

    That is what makes `/repos/OWNER/NAME/releases` -- the listing endpoint, which
    on the real API is not a file at all -- servable from a directory tree.
    """

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = self.translate_path(self.path).rstrip("/\\")
        twin = path + ".json"
        if os.path.isdir(path) and os.path.isfile(twin):
            body = Path(twin).read_bytes()
            query = urllib.parse.parse_qs(url.query)
            if query.get("per_page") and body[:1] == b"[":
                try:
                    limit = int(query["per_page"][0])
                except ValueError:
                    limit = 0
                if limit > 0:
                    body = json.dumps(json.loads(body)[:limit]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


class FakeGitHub:
    """`api.github.com` in a directory: /repos/OWNER/NAME/releases/latest and assets."""

    def __init__(self, root: Path, repo: str = U.DEFAULT_REPO):
        self.root = Path(root)
        self.repo = repo
        self.assets = self.root / "assets"
        self.assets.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(QuietHandler, directory=str(self.root))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.api = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def publish(self, version: str, files: list, sums: str = "good",
                prerelease: bool = False, tag: str = "") -> None:
        """Attach files to a release and make it the newest one.

        `sums` is "good", "wrong" or "none": a correct SHA256SUMS.txt, one that
        does not match, or no checksums at all.
        """
        names = []
        for path in files:
            path = Path(path)
            shutil.copy2(path, self.assets / path.name)
            names.append(path.name)
        if sums == "good":
            (self.assets / "SHA256SUMS.txt").write_text(
                "".join(f"{U.sha256_of(str(self.assets / n))}  {n}\n"
                        for n in sorted(names)))
            names.append("SHA256SUMS.txt")
        elif sums == "wrong":
            (self.assets / "SHA256SUMS.txt").write_text(
                "".join(f"{'0' * 64}  {n}\n" for n in sorted(names)))
            names.append("SHA256SUMS.txt")
        release = {
            "tag_name": tag or f"v{version}",
            "name": f"OmniScript {version}",
            "published_at": "2026-09-16T09:00:00Z",
            "prerelease": prerelease,
            "assets": [
                {"name": n, "size": (self.assets / n).stat().st_size,
                 "browser_download_url": f"{self.api}/assets/{n}"}
                for n in sorted(names)
            ],
        }
        base = self.root / "repos" / self.repo / "releases"
        for relative in ("latest", f"tags/{tag or f'v{version}'}"):
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(release, indent=2))
        # The listing endpoint keeps every release, newest first.
        index = base.parent / "releases.json"
        listed = json.loads(index.read_text()) if index.is_file() else []
        listed = [item for item in listed if item.get("tag_name") != release["tag_name"]]
        listed.insert(0, release)
        index.write_text(json.dumps(listed, indent=2))

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def build_artifact(root: Path, version: str, name: str = "") -> Path:
    """Build a single-file OmniScript that reports `version`, and return its path.

    `name` overrides the file name, which is how a test publishes an artifact
    under the name a particular platform would expect.
    """
    root = Path(root)
    src = root / f"src-{version}"
    (src / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "omniscript", src / "omniscript",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(REPO / "tools" / "build_executable.py", src / "tools")
    stamp_version(src, version)
    out = root / f"out-{version}"
    proc = subprocess.run(
        [sys.executable, str(src / "tools" / "build_executable.py"), "--out", str(out),
         "--skip-binary", "--no-smoke", "--version", version],
        capture_output=True, text=True, cwd=str(root), timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"could not build the {version} artifact:\n"
                             f"{proc.stdout}\n{proc.stderr}")
    artifact = out / U.zipapp_asset(version)
    if name and name != artifact.name:
        renamed = out / name
        shutil.copy2(artifact, renamed)
        U.write_checksums(str(out))
        return renamed
    return artifact


def stamp_version(tree: Path, version: str) -> None:
    path = Path(tree) / "omniscript" / "stdlib" / "__init__.py"
    path.write_text(re.sub(r'^VERSION = ".*"', f'VERSION = "{version}"',
                           path.read_text(), count=1, flags=re.M))


def git(directory: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True,
                          text=True, timeout=120)


def commit(directory: Path, message: str) -> None:
    git(directory, "add", "-A")
    git(directory, "-c", "user.name=OmniScript Test", "-c", "user.email=test@example.com",
        "commit", "-q", "-m", message)


def make_repository(root: Path, version: str = OLD, branch: str = "main") -> Path:
    """A git repository holding a copy of this tree, for the beta channel to pull."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in FILES_COPIED:
        source = REPO / name
        if source.is_dir():
            shutil.copytree(source, root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif source.is_file():
            shutil.copy2(source, root / name)
    stamp_version(root, version)
    git(root, "init", "-q", "-b", branch)
    commit(root, f"OmniScript {version}")
    return root


def clone(origin: Path, target: Path) -> Path:
    proc = subprocess.run(["git", "clone", "-q", str(origin), str(target)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"could not clone {origin}: {proc.stderr}")
    return Path(target)
