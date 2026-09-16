"""Two channels and the command that follows them: `omni update`.

    omni update                     newest GitHub Release
    omni update --channel beta      newest commit in the repository
    omni update --check             what is out there, changed nothing

The **release** channel asks GitHub what the newest release is, takes the file
built for this machine out of it -- the standalone executable, or the `.pyz` --
checks it against `SHA256SUMS.txt`, puts it where the old one was and runs it to
prove it works. The old file stays until the new one has run.

The **beta** channel is the repository: fetch the branch the install tracks
(`main` unless it was told otherwise) and fast-forward it. A symlink into the
tree needs nothing rebuilt, because it already points at what just moved.

Neither channel touches a file it cannot account for: a source tree with local
edits is left alone, and an executable that is not ours is left alone.
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

from . import VERSION, _bundle

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
MANIFEST_NAME = "install.txt"

# Written as one repeated line each; read back as a list under the plural name.
LIST_KEYS = {"commands": "command", "editor_extensions": "extension"}
BOOL_KEYS = ("cloned_by_installer",)


def parse_manifest(text: str) -> dict:
    """`key=value` lines: repeated keys are lists, 0 and 1 are booleans.

    Deliberately the simplest thing that can be read from a shell with sed, from
    PowerShell with -split and from here with a loop -- so a machine with no
    Python on it can still be uninstalled exactly, and nothing has to escape a
    path into JSON.
    """
    data: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        for plural, singular in LIST_KEYS.items():
            if key == singular:
                data.setdefault(plural, []).append(value.strip())
                break
        else:
            data[key] = value.strip()
    for key in BOOL_KEYS:
        if key in data:
            data[key] = data[key] == "1"
    return data


def format_manifest(data: dict) -> str:
    """The other direction; empty and None both become `key=`."""
    lines = []
    for key in sorted(data):
        value = data[key]
        if key in LIST_KEYS:
            for item in value or []:
                lines.append(f"{LIST_KEYS[key]}={item}")
        elif isinstance(value, bool):
            lines.append(f"{key}={1 if value else 0}")
        elif isinstance(value, (list, tuple)):
            for item in value:
                lines.append(f"{key}={item}")
        elif value is not None:
            lines.append(f"{key}={value}")
        else:
            lines.append(f"{key}=")
    return "\n".join(lines) + "\n"


def manifest_candidates() -> list[str]:
    """Every place an installer might have left a manifest, most specific first."""
    override = os.environ.get("OMNISCRIPT_MANIFEST")
    found = [override] if override else []
    data = os.environ.get("XDG_DATA_HOME")
    if data:
        found.append(os.path.join(data, "omniscript", MANIFEST_NAME))
    home = os.path.expanduser("~")
    found.append(os.path.join(home, ".local", "share", "omniscript", MANIFEST_NAME))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        found.append(os.path.join(local, "OmniScript", MANIFEST_NAME))
    profile = os.environ.get("USERPROFILE")
    if profile:
        found.append(os.path.join(profile, "AppData", "Local", "OmniScript",
                                  MANIFEST_NAME))
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
                    data = parse_manifest(fh.read())
                if data:
                    return data, candidate
            except (OSError, ValueError):
                continue
    return {}, ""


@dataclass
class Install:
    """What we can work out about the copy of OmniScript that is running."""

    kind: str = "unknown"        # binary | source | unknown
    mode: str = ""               # symlink | binary
    channel: str = ""            # release | beta
    version: str = VERSION
    source: str = ""
    bin_dir: str = ""
    binary: str = ""
    commands: list = field(default_factory=list)
    ref: str = ""
    python: str = ""
    cloned_by_installer: bool = False
    manifest_path: str = ""
    manifest: dict = field(default_factory=dict)
    repo: str = DEFAULT_REPO
    api: str = DEFAULT_API

    def describe(self) -> str:
        where = {"binary": self.binary, "source": self.source}.get(self.kind, "")
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
        install.python = str(manifest.get("python") or "")
        install.cloned_by_installer = bool(manifest.get("cloned_by_installer"))
        install.repo = str(manifest.get("repo") or install.repo)
        install.api = api or str(manifest.get("api_url") or "") or install.api
        install.kind = {"binary": "binary", "symlink": "source"}.get(mode, "unknown")
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


def fetch_release(api: str, repo: str, tag: str = "") -> dict:
    """The release to update to, or {} when the repository has none."""
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
    return {}


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
    kind: str = ""      # binary | pyz

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

    Preference is the standalone executable, then the single-file zipapp, which
    runs anywhere there is a Python.
    """
    assets = release.get("assets") or []
    by_name = {}
    for item in assets:
        if isinstance(item, dict) and item.get("name"):
            by_name[str(item["name"])] = item
    wanted = [(binary_asset(version, tag), "binary"), (zipapp_asset(version), "pyz")]
    for name, kind in wanted:
        item = by_name.get(name)
        if not item:
            continue
        url = str(item.get("browser_download_url") or item.get("url") or "")
        if not url:
            continue
        return Asset(name=name, url=url, size=int(item.get("size") or 0), kind=kind)
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
    force: bool = False


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
            fh.write(format_manifest(data))
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
    launcher = os.path.join(source, "omni")
    if os.path.isfile(launcher) and not os.access(launcher, os.X_OK):
        try:
            os.chmod(launcher, 0o755)
        except OSError:
            pass
    report.step("reinstalling", "nothing to rebuild: the commands point at the tree")



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
    release = fetch_release(install.api, install.repo, tag)
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
        raise UpdateError("this copy runs from a source tree; `omni update --channel "
                          "beta` follows it, or run install.sh --channel release to "
                          "switch to the published release")
    if asset is None:
        raise UpdateError(f"{published} has no file for {platform_tag()} and no .pyz "
                          "attached to it")

    if install.kind == "binary" or (install.kind == "unknown" and opts.bin_dir):
        return _install_asset_binary(install, opts, report, release, asset, available)
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


def update_beta(install: Install, opts: Options, report: Reporter) -> int:
    """Follow the repository: the newest commit on the branch being tracked."""
    ref = opts.ref or install.ref or "main"
    report.step("channel", f"beta (the repository, {ref})")
    if install.kind == "binary" or not install.source:
        raise UpdateError("this copy is a standalone executable with no repository in "
                          "it; `omni update` follows the release channel, or run "
                          "install.sh --channel beta to switch to the repository")
    if opts.check:
        _git_check(install.source, ref, report)
        report.step("would update", f"the tree at {install.source}")
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
        force=bool(getattr(args, "force", False)),
    )
    install = detect(opts.api)
    if opts.api:
        install.api = opts.api
    if opts.bin_dir:
        install.bin_dir = os.path.abspath(opts.bin_dir)
    channel = opts.channel or install.channel or "release"
    if channel not in CHANNELS:
        print(f"omni update: --channel must be one of {', '.join(CHANNELS)}",
              file=sys.stderr)
        return 1
    install.channel = channel
    report = Reporter()
    report.step("installed", install.describe())
    if not install.manifest_path:
        report.note("no manifest found; going by how this copy was started")
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
