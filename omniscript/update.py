"""Two channels and the command that follows them: `omni update`.

    omni update                     newest GitHub Release
    omni update --channel beta      newest commit on the branch being tracked
    omni update --check             what is out there, changed nothing

The **release** channel is the published releases. It asks GitHub what the
newest tag is, picks the file built for this machine out of that release --
the standalone executable if there is one, otherwise the `.pyz`, otherwise the
wheel -- checks it against `SHA256SUMS.txt`, puts it where the old one was and
runs it to prove it works. An install that came from a source tree takes the
same channel by checking out the release's tag, because a tag is just a commit
with a name on it.

The **beta** channel is the repository. It fetches, checks out the branch the
install is tracking (`main` unless it was told otherwise) and fast-forwards,
then refreshes whatever was built from that tree -- a venv gets reinstalled, a
pip install gets reinstalled, a symlink needs nothing because it already points
at the tree that just moved.

Nothing here touches a file it cannot account for: a source tree with local
edits is left alone, an executable that is not ours is left alone, and every
replacement keeps the previous file until the new one has run.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import _bundle
from .stdlib import VERSION

DEFAULT_REPO = "OmniNodeCo/OmniScript"
DEFAULT_API = "https://api.github.com"
CHANNELS = ("release", "beta")
USER_AGENT = f"omniscript/{VERSION} ({platform.system()}; {platform.machine()})"
TIMEOUT = 30


# --------------------------------------------------------------------- naming
def platform_tag() -> str:
    """The `<os>-<arch>` pair used in artifact names: linux-x86_64, macos-arm64."""
    system = platform.system().lower()
    os_name = {"darwin": "macos", "windows": "windows"}.get(system, system)
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64",
            "x86_64": "x86_64", "i386": "i686", "i686": "i686"}.get(machine, machine)
    return f"{os_name}-{arch}"


def binary_asset(version: str, tag: str | None = None) -> str:
    return f"omni-{version}-{tag or platform_tag()}" + (".exe" if os.name == "nt" else "")


def zipapp_asset(version: str) -> str:
    return f"omni-{version}-any.pyz"


def wheel_asset(version: str) -> str:
    return f"omniscript_lang-{version.replace('-', '_')}-py3-none-any.whl"


def sdist_asset(version: str) -> str:
    return f"omniscript_lang-{version.replace('-', '_')}.tar.gz"


def parse_version(text: str) -> tuple:
    """'v1.2.0' -> (1, 2, 0); anything unparseable sorts below every real version."""
    digits = []
    for part in str(text).lstrip("vV").split("+")[0].split("-")[0].split("."):
        number = ""
        for char in part:
            if not char.isdigit():
                break
            number += char
        if not number:
            break
        digits.append(int(number))
    return tuple(digits) if digits else (0,)


def version_of_tag(tag: str) -> str:
    return str(tag).lstrip("vV")


# ------------------------------------------------------------------- manifests
def manifest_candidates() -> list[str]:
    """Every place an installer might have left a manifest, most specific first."""
    override = os.environ.get("OMNISCRIPT_MANIFEST")
    found = [override] if override else []
    data = os.environ.get("XDG_DATA_HOME")
    if data:
        found.append(os.path.join(data, "omniscript", "install.json"))
    home = os.path.expanduser("~")
    found.append(os.path.join(home, ".local", "share", "omniscript", "install.json"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        found.append(os.path.join(local, "OmniScript", "install.json"))
    profile = os.environ.get("USERPROFILE")
    if profile:
        found.append(os.path.join(profile, "AppData", "Local", "OmniScript",
                                  "install.json"))
    seen, unique = set(), []
    for path in found:
        real = os.path.abspath(path)
        if real not in seen:
            seen.add(real)
            unique.append(real)
    return unique


def read_manifest(path: str | None = None) -> tuple[dict, str]:
    """The manifest and where it came from; ({}, "") when there is none."""
    for candidate in [path] if path else manifest_candidates():
        if candidate and os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data, candidate
            except (OSError, ValueError):
                continue
    return {}, ""


@dataclass
class Install:
    """What we can work out about the copy of OmniScript that is running."""

    kind: str = "unknown"        # binary | source | pip | unknown
    mode: str = ""               # symlink | venv | pip | binary
    channel: str = ""            # release | beta
    version: str = VERSION
    source: str = ""
    bin_dir: str = ""
    binary: str = ""
    commands: list = field(default_factory=list)
    ref: str = ""
    venv: str = ""
    python: str = ""
    pip_user: bool = False
    pip_break_system: bool = False
    cloned_by_installer: bool = False
    manifest_path: str = ""
    manifest: dict = field(default_factory=dict)
    repo: str = DEFAULT_REPO
    api: str = DEFAULT_API

    def describe(self) -> str:
        where = {"binary": self.binary, "source": self.source,
                 "pip": self.python}.get(self.kind, "")
        bits = [f"OmniScript {self.version or 'unknown'}"]
        bits.append(f"{self.mode or self.kind} install")
        if self.channel:
            bits.append(f"{self.channel} channel")
        if where:
            bits.append(f"at {where}")
        if self.kind == "source" and self.ref:
            bits.append(f"tracking {self.ref}")
        return ", ".join(bits)


def detect(api: str = "", repo: str = "") -> Install:
    """Work out how this copy was installed, from the manifest if there is one."""
    manifest, path = read_manifest()
    install = Install(manifest=manifest, manifest_path=path,
                      api=api or os.environ.get("OMNISCRIPT_API_URL") or DEFAULT_API,
                      repo=repo or os.environ.get("OMNISCRIPT_REPO") or DEFAULT_REPO)
    if manifest:
        mode = str(manifest.get("mode") or "")
        install.mode = mode
        install.channel = str(manifest.get("channel") or "")
        install.version = str(manifest.get("version") or VERSION)
        install.source = str(manifest.get("source") or "")
        install.bin_dir = str(manifest.get("bin_dir") or "")
        install.binary = str(manifest.get("binary") or "")
        install.commands = [str(c) for c in (manifest.get("commands") or [])]
        install.ref = str(manifest.get("ref") or "")
        install.venv = str(manifest.get("venv") or "")
        install.python = str(manifest.get("python") or "")
        install.pip_user = bool(manifest.get("pip_user"))
        install.pip_break_system = bool(manifest.get("pip_break_system_packages"))
        install.cloned_by_installer = bool(manifest.get("cloned_by_installer"))
        install.repo = str(manifest.get("repo") or install.repo)
        install.api = api or str(manifest.get("api_url") or "") or install.api
        install.kind = {"binary": "binary", "symlink": "source", "venv": "source",
                        "pip": "pip"}.get(mode, "unknown")
        if not install.version or install.version == "unknown":
            install.version = VERSION
        return install

    frozen = _bundle.frozen_executable()
    if frozen:
        install.kind = "binary"
        install.mode = "binary"
        install.binary = frozen
        install.bin_dir = os.path.dirname(frozen)
        install.commands = [frozen]
        install.channel = "release"
        install.version = VERSION
        return install

    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(parent, "install.sh")) or \
            os.path.isdir(os.path.join(parent, ".git")):
        install.kind = "source"
        install.mode = "symlink"
        install.source = parent
        install.version = VERSION
        install.ref = _current_ref(parent) or "main"
        return install

    here = os.path.abspath(__file__)
    if "site-packages" in here or "dist-packages" in here:
        install.kind = "pip"
        install.mode = "pip"
        install.python = sys.executable
        install.version = VERSION
        return install

    install.version = VERSION
    return install


# ------------------------------------------------------------------- reporting
class Reporter:
    """Two-column progress lines, so an update reads as a list of what happened."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self.problems: list[str] = []

    def step(self, label: str, message: str) -> None:
        if not self.quiet:
            print(f"{label:<11} {message}", flush=True)

    def note(self, message: str) -> None:
        if not self.quiet:
            print(f"{'':<11} {message}", flush=True)

    def warn(self, message: str) -> None:
        print(f"{'':<11} warning: {message}", file=sys.stderr, flush=True)

    def error(self, message: str) -> None:
        self.problems.append(message)
        print(f"omni update: {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------- network
def _request(url: str, accept: str = "") -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept": accept or "*/*"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str) -> object:
    with urllib.request.urlopen(_request(url, "application/vnd.github+json"),
                                timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response:
        return response.read()


def release_url(api: str, repo: str, tag: str = "") -> str:
    base = f"{api.rstrip('/')}/repos/{repo}"
    return f"{base}/releases/tags/{tag}" if tag else f"{base}/releases/latest"


def fetch_release(api: str, repo: str, tag: str = "", prerelease: bool = False) -> dict:
    """The release to update to, or {} when the repository has none.

    With --prerelease and no tag, the newest of the last releases wins even if
    it is marked as a prerelease, which is how the beta channel of a project
    that cuts release candidates is meant to be followed.
    """
    if tag:
        try:
            data = fetch_json(release_url(api, repo, tag))
            return data if isinstance(data, dict) else {}
        except urllib.error.HTTPError as err:
            raise UpdateError(f"no release tagged {tag} in {repo} ({err.code})") from err
        except (urllib.error.URLError, OSError, ValueError) as err:
            raise UpdateError(f"could not reach {repo}: {_reason(err)}") from err
    try:
        data = fetch_json(release_url(api, repo))
        if isinstance(data, dict) and data.get("tag_name"):
            return data
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise UpdateError(f"GitHub said {err.code} for {repo}") from err
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise UpdateError(f"could not reach {repo}: {_reason(err)}") from err
    if not prerelease:
        return {}
    try:
        listing = fetch_json(f"{api.rstrip('/')}/repos/{repo}/releases?per_page=10")
    except (urllib.error.URLError, OSError, ValueError, urllib.error.HTTPError):
        return {}
    for item in listing if isinstance(listing, list) else []:
        if isinstance(item, dict) and item.get("tag_name"):
            return item
    return {}


def fetch_releases(api: str, repo: str, limit: int = 10) -> list:
    """The recent releases, newest first -- what `omni update --list` shows."""
    per_page = max(1, min(int(limit or 10), 100))
    url = f"{api.rstrip('/')}/repos/{repo}/releases?per_page={per_page}"
    try:
        data = fetch_json(url)
    except urllib.error.HTTPError as err:
        # 404 is what an empty release list looks like from here: the repository
        # has published nothing yet, so there is nothing to list. Anything else
        # -- a rate limit, a server error -- is worth reporting.
        if err.code == 404:
            return []
        raise UpdateError(f"could not list the releases of {repo} ({err.code})") from err
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise UpdateError(f"could not reach {repo}: {_reason(err)}") from err
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _reason(err: Exception) -> str:
    text = getattr(err, "reason", None) or str(err) or err.__class__.__name__
    return str(text).strip() or err.__class__.__name__


class UpdateError(Exception):
    """Something went wrong that the caller should report and stop on."""


def download(url: str, dest: str) -> int:
    """Fetch `url` into `dest`; works for https and for file:// (used by tests)."""
    data = fetch_bytes(url)
    directory = os.path.dirname(os.path.abspath(dest))
    os.makedirs(directory, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    return len(data)


# -------------------------------------------------------------------- assets
@dataclass
class Asset:
    name: str
    url: str
    size: int = 0
    kind: str = ""      # binary | pyz | wheel | sdist

    @property
    def human_size(self) -> str:
        size = float(self.size or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
            size /= 1024
        return f"{size:,.1f} GB"


def pick_asset(release: dict, version: str, tag: str | None = None) -> Asset | None:
    """The best file in this release for this machine, or None.

    Preference is the standalone executable, then the single-file zipapp (which
    needs a Python), then the wheel, then the sdist.
    """
    assets = release.get("assets") or []
    by_name = {}
    for item in assets:
        if isinstance(item, dict) and item.get("name"):
            by_name[str(item["name"])] = item
    wanted = [(binary_asset(version, tag), "binary"),
              (zipapp_asset(version), "pyz"),
              (wheel_asset(version), "wheel"),
              (sdist_asset(version), "sdist")]
    for name, kind in wanted:
        item = by_name.get(name)
        if not item:
            continue
        url = str(item.get("browser_download_url") or item.get("url") or "")
        if not url:
            continue
        return Asset(name=name, url=url, size=int(item.get("size") or 0), kind=kind)
    # Some releases only carry the names the archive gives them.
    for name, item in sorted(by_name.items()):
        if name.endswith((".whl", ".tar.gz")):
            url = str(item.get("browser_download_url") or "")
            if url:
                return Asset(name=name, url=url, size=int(item.get("size") or 0),
                             kind="wheel" if name.endswith(".whl") else "sdist")
    return None


def checksums_for(release: dict) -> dict:
    """{file name: sha256} out of the release's SHA256SUMS.txt, or {} without one."""
    for item in release.get("assets") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").upper() != "SHA256SUMS.TXT":
            continue
        url = str(item.get("browser_download_url") or "")
        if not url:
            continue
        try:
            text = fetch_bytes(url).decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError):
            return {}
        return parse_checksums(text)
    return {}


def parse_checksums(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if not name:
            digest, _, name = line.partition(" ")
        digest, name = digest.strip(), name.strip().lstrip("*")
        if digest and name:
            out[os.path.basename(name)] = digest.lower()
    return out


def sha256_of(path: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_checksums(directory: str) -> str:
    """SHA256SUMS.txt over every file in a directory, `sha256sum -c` compatible."""
    names = sorted(name for name in os.listdir(directory)
                   if name != "SHA256SUMS.txt"
                   and os.path.isfile(os.path.join(directory, name)))
    target = os.path.join(directory, "SHA256SUMS.txt")
    with open(target, "w", encoding="utf-8") as fh:
        for name in names:
            fh.write(f"{sha256_of(os.path.join(directory, name))}  {name}\n")
    return target


def verify_checksums(directory: str) -> list[str]:
    """Complaints about a directory's SHA256SUMS.txt; empty means it all matches."""
    sums = os.path.join(directory, "SHA256SUMS.txt")
    if not os.path.isfile(sums):
        return [f"no {sums}"]
    problems = []
    with open(sums, "r", encoding="utf-8") as fh:
        wanted = parse_checksums(fh.read())
    for name, digest in sorted(wanted.items()):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            problems.append(f"{name}: missing")
        elif sha256_of(path) != digest:
            problems.append(f"{name}: checksum does not match")
    return problems


# ---------------------------------------------------------------- replacing
def cleanup_stale() -> None:
    """Delete the .old files a Windows self-update had to leave behind."""
    target = _bundle.frozen_executable()
    if not target:
        return
    for suffix in (".old", ".old.exe"):
        stale = target + suffix
        if os.path.isfile(stale):
            try:
                os.remove(stale)
            except OSError:
                pass


def replace_executable(target: str, source: str) -> str | None:
    """Put `source` at `target`, keeping the old file until the new one works.

    Returns the path of the backup, or None when there was nothing to keep. A
    running Windows executable cannot be overwritten, but it can be renamed, so
    that is what happens there; the leftover is swept up on the next start.
    """
    directory = os.path.dirname(os.path.abspath(target)) or "."
    os.makedirs(directory, exist_ok=True)
    backup = None
    if os.path.exists(target):
        backup = target + ".old"
        if os.name == "nt":
            if os.path.exists(backup):
                try:
                    os.remove(backup)
                except OSError:
                    backup = None
            if backup:
                try:
                    os.replace(target, backup)
                except OSError:
                    backup = None
        else:
            shutil.copy2(target, backup)
    staged = os.path.join(directory, f".{os.path.basename(target)}.new-{os.getpid()}")
    shutil.move(source, staged)
    if os.name != "nt":
        os.chmod(staged, 0o755)
    os.replace(staged, target)
    if os.name != "nt":
        os.chmod(target, 0o755)
    return backup


def restore(target: str, backup: str | None) -> None:
    if not backup or not os.path.isfile(backup):
        return
    try:
        if os.name == "nt" and os.path.exists(target):
            os.remove(target)
        os.replace(backup, target)
        if os.name != "nt":
            os.chmod(target, 0o755)
    except OSError:
        pass


def run_version(command: list[str], cwd: str | None = None) -> str:
    """What an executable reports for --version, or '' when it will not run."""
    try:
        proc = subprocess.run(command + ["--version"], cwd=cwd or tempfile.gettempdir(),
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return ""
    parts = out.replace("OmniScript", " ").split()
    return parts[0] if parts else ""


def command_for(path: str) -> list[str]:
    """How to invoke an installed artifact; a .pyz needs an interpreter."""
    if path.endswith((".pyz", ".zip")):
        return [sys.executable, path]
    return [path]


# ------------------------------------------------------------------- options
@dataclass
class Options:
    channel: str = ""
    check: bool = False
    version: str = ""
    ref: str = ""
    bin_dir: str = ""
    api: str = ""
    repo: str = ""
    force: bool = False
    verify: bool = True
    prerelease: bool = False
    quiet: bool = False


def _write_manifest(install: Install, changes: dict) -> None:
    """Record what changed, so the uninstaller and the next update agree."""
    path = install.manifest_path
    data = dict(install.manifest)
    data.update(changes)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not path:
        # No installer wrote one, so take the first place one would have gone:
        # $OMNISCRIPT_MANIFEST, then XDG_DATA_HOME, then the platform default.
        candidates = manifest_candidates()
        if not candidates:
            return
        path = candidates[0]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        staged = path + ".new"
        with open(staged, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(staged, path)
    except OSError:
        return
    install.manifest = data
    install.manifest_path = path


# ------------------------------------------------------------------- git work
def repo_url(install: Install) -> str:
    """Where the beta channel clones from: an override, the manifest, or GitHub.

    A fork or a mirror sets OMNISCRIPT_REPO_URL once and every later update
    follows it, which is also how the tests fetch without a network.
    """
    override = os.environ.get("OMNISCRIPT_REPO_URL") or \
        str((install.manifest or {}).get("repo_url") or "")
    if override:
        return override
    return f"https://github.com/{install.repo}.git"


def _git(directory: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", directory, *args], capture_output=True,
                          text=True, timeout=300)


def _current_ref(directory: str) -> str:
    proc = _git(directory, "rev-parse", "--abbrev-ref", "HEAD")
    name = proc.stdout.strip()
    if proc.returncode != 0 or not name or name == "HEAD":
        return ""
    return name


def _tree_is_clean(directory: str) -> bool:
    proc = _git(directory, "status", "--porcelain")
    return proc.returncode == 0 and not proc.stdout.strip()


def _is_git_checkout(directory: str) -> bool:
    return bool(directory) and os.path.isdir(os.path.join(directory, ".git"))


def _git_check(source: str, ref: str, report: Reporter) -> str:
    """How far a tree is behind its remote, asked without writing to the tree."""
    if not shutil.which("git"):
        raise UpdateError("git is not on PATH, so the beta channel cannot ask anything")
    if not _is_git_checkout(source):
        raise UpdateError(f"{source} is not a git checkout; the beta channel follows a "
                          "repository, so install from a release instead")
    local = _git(source, "rev-parse", "HEAD").stdout.strip()
    proc = _git(source, "ls-remote", "origin", f"refs/heads/{ref}")
    parts = proc.stdout.split()
    if proc.returncode != 0 or not parts:
        raise UpdateError(f"origin has no branch called {ref}"
                          + (f": {proc.stderr.strip()[-200:]}" if proc.stderr else ""))
    remote = parts[0]
    if remote == local:
        report.step("up to date", f"{ref} is at {local[:12]}")
        return remote
    known = _git(source, "cat-file", "-e", remote).returncode == 0
    if known:
        count = _git(source, "rev-list", "--count", f"{local}..{remote}").stdout.strip()
        behind = f", {count} commit(s) behind" if count.isdigit() and count != "0" else ""
    else:
        behind = ", not fetched yet"
    report.step("would update", f"{ref} has moved: {local[:12]} -> {remote[:12]}{behind}")
    return remote


def _git_pull(source: str, ref: str, report: Reporter, force: bool = False) -> str:
    """Fetch and fast-forward a source tree. Returns the new version, or raises."""
    if not shutil.which("git"):
        raise UpdateError("git is not on PATH, so the beta channel cannot fetch anything")
    if not _is_git_checkout(source):
        raise UpdateError(f"{source} is not a git checkout; the beta channel updates "
                          "a repository, so reinstall from a release instead")
    if not _tree_is_clean(source) and not force:
        raise UpdateError(f"{source} has local changes; commit or stash them first, "
                          "or pass --force to update anyway")
    before = _git(source, "rev-parse", "HEAD").stdout.strip()[:12]
    report.step("fetching", f"origin {ref or 'the tracked branch'}")
    if ref:
        proc = _git(source, "fetch", "--quiet", "--tags", "origin", ref)
    else:
        proc = _git(source, "fetch", "--quiet", "--tags", "origin")
    if proc.returncode != 0:
        raise UpdateError(f"git fetch failed: {proc.stderr.strip()[-300:]}")
    current = _current_ref(source)
    if ref and current != ref:
        report.step("checking out", ref)
        proc = _git(source, "checkout", "--quiet", ref)
        if proc.returncode != 0:
            raise UpdateError(f"git checkout {ref} failed: {proc.stderr.strip()[-300:]}")
    report.step("merging", "fast-forward only")
    if ref:
        proc = _git(source, "merge", "--quiet", "--ff-only", f"origin/{ref}")
    else:
        proc = _git(source, "merge", "--quiet", "--ff-only",
                    f"origin/{current or 'HEAD'}")
    if proc.returncode != 0 and "Already up to date" not in proc.stderr:
        detail = (proc.stderr or proc.stdout).strip()[-300:]
        raise UpdateError(f"the tree could not be fast-forwarded: {detail}")
    after = _git(source, "rev-parse", "HEAD").stdout.strip()[:12]
    if before and after and before != after:
        log = _git(source, "log", "--oneline", f"{before}..{after}")
        commits = [line for line in log.stdout.strip().splitlines() if line.strip()]
        report.step("advanced", f"{before} -> {after} ({len(commits)} commit(s))")
        for line in commits[:10]:
            report.note(line)
    else:
        report.step("advanced", f"already at {after or before or 'HEAD'}")
    return after


def _refresh_source_install(install: Install, report: Reporter) -> None:
    """Rebuild whatever was made from the source tree, after the tree moved."""
    source = install.source
    if install.mode == "venv" and install.venv:
        python = _venv_python(install.venv)
        if not python:
            raise UpdateError(f"the venv at {install.venv} has no interpreter in it")
        report.step("reinstalling", f"into {install.venv}")
        _pip(python, ["install", "--quiet", "--upgrade", source], report)
    elif install.mode == "pip" and install.python:
        report.step("reinstalling", f"into {install.python}")
        flags = []
        if install.pip_user:
            flags.append("--user")
        if install.pip_break_system:
            flags.append("--break-system-packages")
        _pip(install.python, ["install", "--quiet", "--upgrade", *flags, source], report)
    else:
        launcher = os.path.join(source, "omni")
        if os.path.isfile(launcher) and not os.access(launcher, os.X_OK):
            try:
                os.chmod(launcher, 0o755)
            except OSError:
                pass
        report.step("reinstalling", "nothing to rebuild: the commands point at the tree")


def _venv_python(venv: str) -> str:
    for name in (("Scripts", "python.exe"), ("bin", "python3"), ("bin", "python")):
        candidate = os.path.join(venv, *name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _pip(python: str, args: list[str], report: Reporter) -> None:
    proc = subprocess.run([python, "-m", "pip", *args], capture_output=True,
                          text=True, timeout=900)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[-300:]
        if "externally-managed-environment" in detail:
            report.step("retrying", "with --break-system-packages")
            proc = subprocess.run(
                [python, "-m", "pip", *args, "--break-system-packages"],
                capture_output=True, text=True, timeout=900)
            if proc.returncode != 0:
                raise UpdateError(f"pip refused: {(proc.stderr or proc.stdout).strip()[-300:]}")
            return
        raise UpdateError(f"pip failed: {detail}")


def _verify_commands(install: Install, report: Reporter, want: str = "") -> None:
    """Run the installed command and check what it says about itself."""
    targets = [c for c in (install.commands or []) if c]
    if not targets:
        if install.binary:
            targets = [install.binary]
        elif install.bin_dir:
            targets = [os.path.join(install.bin_dir, "omni")]
        elif install.source:
            targets = [os.path.join(install.source, "omni")]
    for target in targets[:1]:
        if not os.path.exists(target):
            raise UpdateError(f"{target} is not there any more")
        reported = run_version(command_for(target))
        if not reported:
            raise UpdateError(f"{target} did not run after the update")
        report.step("verified", f"{os.path.basename(target)} reports {reported}")
        if want and reported != want:
            raise UpdateError(f"{target} reports {reported} but the update was to {want}")


# --------------------------------------------------------------- the channels
def update_release(install: Install, opts: Options, report: Reporter) -> int:
    """Follow the release channel: whatever GitHub has published."""
    tag = opts.version if opts.version.startswith("v") else \
        (f"v{opts.version}" if opts.version else "")
    report.step("channel", f"release ({install.repo})")
    release = fetch_release(install.api, install.repo, tag, opts.prerelease)
    if not release:
        report.note("this repository has no releases yet")
        report.note("use `omni update --channel beta` to follow the repository itself")
        return 0

    published = str(release.get("tag_name") or "")
    available = version_of_tag(published)
    report.step("found", f"{published} "
                         f"({str(release.get('published_at') or '')[:10] or 'undated'})")
    if install.version and parse_version(available) == parse_version(install.version) \
            and not opts.force:
        report.step("up to date", f"{install.version} is the newest release")
        return 0
    if install.version and parse_version(available) < parse_version(install.version) \
            and not opts.force:
        report.warn(f"the newest release ({available}) is older than what is installed "
                    f"({install.version}); pass --force to go back")
        return 0
    if opts.check:
        report.step("would update", f"{install.version or 'unknown'} -> {available}")
        asset = pick_asset(release, available)
        if asset:
            report.note(f"from {asset.name} ({asset.human_size})")
        return 0

    asset = pick_asset(release, available)
    if install.kind == "source":
        # A source install takes a release as a tag, so it does not need a file.
        return _install_release_as_tag(install, opts, report, available, published, asset)
    if asset is None:
        raise UpdateError(f"{published} has no file for {platform_tag()}, no .pyz and "
                          "no wheel attached to it")

    if install.kind == "binary" or (install.kind == "unknown" and opts.bin_dir):
        return _install_asset_binary(install, opts, report, release, asset, available)
    if install.kind == "pip":
        return _install_release_with_pip(install, opts, report, release, asset, available)
    raise UpdateError("cannot work out how OmniScript was installed, so there is "
                      "nothing safe to replace; run install.sh (or install.ps1) again, "
                      "or pass --bin DIR to put the release executable somewhere")


def _is_zipapp(path: str) -> bool:
    return path.lower().endswith((".pyz", ".zip"))


def _artifact_name(kind: str) -> str:
    """What a downloaded file is called once it is in place.

    POSIX runs a zipapp directly through its shebang, so both kinds are simply
    `omni`. Windows has no shebang, so the file keeps an extension that says
    what it is and a .cmd shim in front of it does the running.
    """
    if os.name == "nt":
        return "omni.pyz" if kind == "pyz" else "omni.exe"
    return "omni"


def _write_windows_shim(bin_dir: str, artifact: str, name: str,
                        python: str = "") -> str:
    """A .cmd file that runs `artifact`; the only way Windows gets a command."""
    body = f'@"%~dp0{os.path.basename(artifact)}" %*\r\n'
    if _is_zipapp(artifact):
        interpreter = python or shutil.which("python") or shutil.which("python3") \
            or sys.executable
        body = f'@"{interpreter}" "%~dp0{os.path.basename(artifact)}" %*\r\n'
    path = os.path.join(bin_dir, name + ".cmd")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    return path


def _install_asset_binary(install: Install, opts: Options, report: Reporter,
                          release: dict, asset: Asset, available: str) -> int:
    """Download an executable artifact and swap it for the one that is running."""
    if asset.kind in ("wheel", "sdist"):
        raise UpdateError(f"{asset.name} is a Python distribution, not an executable; "
                          "install it with pip, or run install.sh for a source install")
    if asset.kind == "pyz" and not (shutil.which("python3") or shutil.which("python")):
        raise UpdateError(f"the only file for this machine is {asset.name}, which needs "
                          "a Python, and there is none on PATH")

    bin_dir = os.path.abspath(opts.bin_dir or install.bin_dir or
                              (os.path.dirname(install.binary) if install.binary else ""))
    if not bin_dir:
        raise UpdateError("there is nowhere to put it: pass --bin DIR")
    current = install.binary if install.binary and not opts.bin_dir else ""
    if current and _is_zipapp(current) == (asset.kind == "pyz"):
        # Same shape as what is there, so keep the name it already answers to.
        target = current
    else:
        target = os.path.join(bin_dir, _artifact_name(asset.kind))
    replaced = current if current and os.path.abspath(current) != os.path.abspath(target) \
        else ""

    report.step("downloading", f"{asset.name} ({asset.human_size})")
    tmpdir = tempfile.mkdtemp(prefix="omni-update-")
    try:
        staged = os.path.join(tmpdir, asset.name)
        size = download(asset.url, staged)
        report.note(f"{size:,} bytes")

        if opts.verify:
            sums = checksums_for(release)
            if not sums:
                report.warn("the release has no SHA256SUMS.txt to check against")
            else:
                want = sums.get(asset.name)
                got = sha256_of(staged)
                if not want:
                    report.warn(f"SHA256SUMS.txt does not mention {asset.name}")
                elif want != got:
                    raise UpdateError(f"checksum mismatch for {asset.name}: expected "
                                      f"{want}, downloaded {got}")
                else:
                    report.step("verified", f"sha256 {got[:16]}...")

        report.step("installing", target)
        backup = replace_executable(target, staged)
        try:
            reported = run_version(command_for(target))
            if reported != available:
                raise UpdateError(f"the new {os.path.basename(target)} reports "
                                  f"{reported or 'nothing'}, not {available}")
            report.step("verified", f"{os.path.basename(target)} reports {reported}")
        except UpdateError:
            restore(target, backup)
            raise
        for leftover in [b for b in (backup,) if b]:
            try:
                os.remove(leftover)
            except OSError:
                pass

        # The second command, so `omniscript` keeps working next to `omni`.
        commands = [target]
        if os.name == "nt":
            for name in ("omni", "omniscript"):
                shim = _write_windows_shim(bin_dir, target, name, install.python)
                commands.append(shim)
                report.note(f"{shim} runs {os.path.basename(target)}")
        else:
            second = os.path.join(bin_dir, "omniscript")
            if os.path.abspath(second) != os.path.abspath(target):
                try:
                    if os.path.islink(second) or os.path.exists(second):
                        os.remove(second)
                    os.symlink(target, second)
                    commands.append(second)
                    report.note(f"{second} -> {os.path.basename(target)}")
                except OSError:
                    pass
        if replaced and os.path.isfile(replaced):
            # The shape changed (an executable for a zipapp or the other way
            # round), so the file that used to be the command is not one now.
            try:
                os.remove(replaced)
                report.note(f"removed the old {os.path.basename(replaced)}")
            except OSError:
                report.warn(f"could not remove the superseded {replaced}")

        changes = {"mode": "binary", "channel": "release", "version": available,
                   "release_tag": str(release.get("tag_name") or ""),
                   "binary": target, "bin_dir": bin_dir,
                   "package": "omniscript-lang", "repo": install.repo,
                   "commands": list(dict.fromkeys(commands + list(install.commands)))}
        if replaced and replaced in changes["commands"]:
            changes["commands"].remove(replaced)
        _write_manifest(install, changes)
        report.step("updated", f"{install.version} -> {available}")
        return 0
    finally:
        shutil.rmtree(tmpdir, True)


def _install_release_as_tag(install: Install, opts: Options, report: Reporter,
                            available: str, published: str,
                            asset: Asset | None) -> int:
    """A source install takes a release by checking out its tag."""
    source = install.source
    if not _is_git_checkout(source):
        raise UpdateError(f"{source} is not a git checkout; reinstall from the release "
                          "executable with install.sh --channel release")
    if install.cloned_by_installer is False and not opts.force:
        report.warn(f"{source} is your own clone; pass --force to check out {published} "
                    "in it")
        return 0
    if not shutil.which("git"):
        raise UpdateError("git is not on PATH, so a tag cannot be checked out")
    report.step("fetching", f"tags from origin, looking for {published}")
    proc = _git(source, "fetch", "--quiet", "--tags", "origin")
    if proc.returncode != 0:
        raise UpdateError(f"git fetch failed: {proc.stderr.strip()[-300:]}")
    if not _tree_is_clean(source) and not opts.force:
        raise UpdateError(f"{source} has local changes; commit or stash them, or pass "
                          "--force")
    report.step("checking out", published)
    proc = _git(source, "checkout", "--quiet", published)
    if proc.returncode != 0:
        raise UpdateError(f"git checkout {published} failed: {proc.stderr.strip()[-300:]}")
    _refresh_source_install(install, report)
    _verify_commands(install, report, available)
    _write_manifest(install, {"version": available, "release_tag": published,
                              "channel": "release"})
    extra = f" ({asset.name} is attached to it, if you would rather have a single file)" \
        if asset else ""
    report.step("updated", f"{install.version} -> {available}{extra}")
    return 0


def _install_release_with_pip(install: Install, opts: Options, report: Reporter,
                              release: dict, asset: Asset, available: str) -> int:
    """A pip install upgrades through pip -- from the release's wheel if it has one."""
    python = install.python or sys.executable
    flags = []
    if install.pip_user:
        flags.append("--user")
    if install.pip_break_system:
        flags.append("--break-system-packages")
    tmpdir = ""
    if asset.kind == "wheel":
        report.step("downloading", f"{asset.name} ({asset.human_size})")
        tmpdir = tempfile.mkdtemp(prefix="omni-update-")
        staged = os.path.join(tmpdir, asset.name)
        try:
            download(asset.url, staged)
            if opts.verify:
                want = checksums_for(release).get(asset.name)
                if want and want != sha256_of(staged):
                    raise UpdateError(f"checksum mismatch for {asset.name}")
                if want:
                    report.step("verified", f"sha256 {want[:16]}…")
            report.step("installing", f"{asset.name} with pip")
            _pip(python, ["install", "--quiet", "--upgrade", *flags, staged], report)
        finally:
            shutil.rmtree(tmpdir, True)
    else:
        report.step("installing", f"omniscript-lang=={available} with pip")
        _pip(python, ["install", "--quiet", "--upgrade", *flags,
                      f"omniscript-lang=={available}"], report)
    _verify_commands(install, report, available)
    _write_manifest(install, {"version": available, "channel": "release"})
    report.step("updated", f"{install.version} -> {available}")
    return 0


def update_beta(install: Install, opts: Options, report: Reporter) -> int:
    """Follow the repository: the newest commit on the branch being tracked."""
    ref = opts.ref or install.ref or "main"
    report.step("channel", f"beta (the repository, {ref})")
    if install.kind == "binary":
        report.note("this copy is a standalone executable with no repository in it")
        return _beta_for_binary(install, opts, report, ref)
    if install.kind not in ("source", "pip") or not install.source:
        raise UpdateError("the beta channel needs a source tree to pull; run install.sh "
                          "--channel beta first, or use --channel release")
    if opts.check:
        _git_check(install.source, ref, report)
        report.step("would rebuild", f"{install.mode} install from {install.source}")
        return 0
    before = install.version
    _git_pull(install.source, ref, report, opts.force)
    _refresh_source_install(install, report)
    after = _source_version(install.source)
    _verify_commands(install, report)
    _write_manifest(install, {"version": after or before, "channel": "beta", "ref": ref})
    if after and after != before:
        report.step("updated", f"{before} -> {after}")
    else:
        report.step("updated", f"the tree is current (version {after or before})")
    return 0


def _beta_for_binary(install: Install, opts: Options, report: Reporter, ref: str) -> int:
    """A binary cannot pull, but it can be replaced by a build of the branch."""
    report.note("the beta channel is the repository, so this downloads a build of it")
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    source = os.path.join(data, "omniscript", "src")
    if not shutil.which("git"):
        raise UpdateError("git is not on PATH, so the repository cannot be fetched")
    url = repo_url(install)
    if opts.check and not _is_git_checkout(source):
        report.step("would clone", f"{url} ({ref}) into {source}")
        report.step("would rebuild", "an executable from that tree")
        return 0
    if _is_git_checkout(source):
        if opts.check:
            _git_check(source, ref, report)
            report.step("would rebuild", f"an executable from {source}")
            return 0
        _git_pull(source, ref, report, opts.force)
    else:
        os.makedirs(os.path.dirname(source), exist_ok=True)
        report.step("cloning", f"{url} ({ref}) into {source}")
        proc = subprocess.run(["git", "clone", "--quiet", "--branch", ref, url, source],
                              capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise UpdateError(f"git clone failed: {proc.stderr.strip()[-300:]}")
    report.step("rebuilding", "an executable from that tree (needs PyInstaller)")
    built = _build_from_source(source, ref, report)
    target = install.binary
    backup = replace_executable(target, built)
    try:
        reported = run_version(command_for(target))
        if not reported:
            raise UpdateError("the rebuilt executable did not run")
        report.step("verified", f"{os.path.basename(target)} reports {reported}")
    except UpdateError:
        restore(target, backup)
        raise
    if backup:
        try:
            os.remove(backup)
        except OSError:
            pass
    _write_manifest(install, {"version": reported, "channel": "beta", "ref": ref,
                              "source": source, "cloned_by_installer": True})
    report.step("updated", f"{install.version} -> {reported}")
    return 0


def _build_from_source(source: str, ref: str, report: Reporter) -> str:
    """Build a standalone executable out of a source tree; returns its path."""
    tool = os.path.join(source, "tools", "build_executable.py")
    if not os.path.isfile(tool):
        raise UpdateError(f"{source} has no tools/build_executable.py to build with")
    python = shutil.which("python3") or shutil.which("python") or sys.executable
    out = tempfile.mkdtemp(prefix="omni-beta-")
    version = _source_version(source) or "0.0.0"
    proc = subprocess.run(
        [python, tool, "--out", out, "--version", version, "--no-smoke"],
        cwd=out, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        shutil.rmtree(out, True)
        detail = (proc.stderr or proc.stdout).strip()[-400:]
        hint = "pip install pyinstaller" if "PyInstaller" in detail else ""
        raise UpdateError(f"the build failed: {detail}" + (f"\n           try: {hint}"
                                                           if hint else ""))
    want = os.path.join(out, binary_asset(version))
    if not os.path.isfile(want):
        names = sorted(os.listdir(out))
        shutil.rmtree(out, True)
        raise UpdateError(f"the build produced {names}, not {os.path.basename(want)}")
    report.note(f"built {os.path.basename(want)} from {ref}")
    return want


def _source_version(source: str) -> str:
    """The version a source tree reports, read without importing it."""
    path = os.path.join(source, "omniscript", "stdlib", "__init__.py")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VERSION"):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


# ------------------------------------------------------------------ the command
def list_releases(install: Install, report: Reporter, limit: int = 10) -> int:
    """`omni update --list`: what is published, and which of it fits this machine."""
    releases = fetch_releases(install.api, install.repo, limit)
    if not releases:
        report.step("releases", f"{install.repo} has not published any")
        return 0
    report.step("releases", f"the newest {len(releases)} from {install.repo}")
    mine = install.version.lstrip("vV")
    for release in releases:
        tag = str(release.get("tag_name") or "?")
        version = version_of_tag(tag)
        when = str(release.get("published_at") or "")[:10]
        asset = pick_asset(release, version)
        bits = [f"{tag:<14}", when or "no date"]
        if release.get("prerelease"):
            bits.append("prerelease")
        bits.append(asset.name if asset else "nothing for this platform")
        if version and version == mine:
            bits.append("<- installed")
        report.note("  ".join(bit for bit in bits if bit))
    return 0


def run(args) -> int:
    """`omni update` -- see the module docstring for what the channels mean."""
    cleanup_stale()
    opts = Options(
        channel=getattr(args, "channel", "") or "",
        check=bool(getattr(args, "check", False)),
        version=getattr(args, "version", "") or getattr(args, "tag", "") or "",
        ref=getattr(args, "ref", "") or "",
        bin_dir=getattr(args, "bin_dir", "") or "",
        api=getattr(args, "api_url", "") or "",
        repo=getattr(args, "repo", "") or "",
        force=bool(getattr(args, "force", False)),
        verify=not bool(getattr(args, "no_verify", False)),
        prerelease=bool(getattr(args, "prerelease", False)),
        quiet=bool(getattr(args, "quiet", False)),
    )
    install = detect(opts.api, opts.repo)
    if opts.api:
        install.api = opts.api
    if opts.repo:
        install.repo = opts.repo
    if opts.bin_dir:
        install.bin_dir = os.path.abspath(opts.bin_dir)
    channel = opts.channel or install.channel or "release"
    if channel not in CHANNELS:
        print(f"omni update: --channel must be one of {', '.join(CHANNELS)}",
              file=sys.stderr)
        return 1
    install.channel = channel
    report = Reporter(opts.quiet)
    report.step("installed", install.describe())
    if not install.manifest_path:
        report.note("no manifest found; going by how this copy was started")
    if getattr(args, "list_releases", False):
        try:
            # Asking for a list is asking to be told: --quiet must not blank it.
            return list_releases(install, Reporter(False),
                                 int(getattr(args, "limit", 0) or 10))
        except UpdateError as err:
            report.error(str(err))
            return 1
        except (urllib.error.URLError, OSError) as err:
            report.error(f"could not reach {install.repo}: {_reason(err)}")
            return 1
    try:
        if channel == "release":
            return update_release(install, opts, report)
        return update_beta(install, opts, report)
    except UpdateError as err:
        report.error(str(err))
        return 1
    except urllib.error.HTTPError as err:
        report.error(f"the server said {err.code} for {err.url or install.repo}")
        return 1
    except urllib.error.URLError as err:
        report.error(f"could not reach {install.repo}: {_reason(err)}")
        report.note("check the network, or pass --api-url for a mirror")
        return 1
    except KeyboardInterrupt:
        report.error("interrupted")
        return 130
    except subprocess.TimeoutExpired:
        report.error("a step took too long and was stopped")
        return 1
