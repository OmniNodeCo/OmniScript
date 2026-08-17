"""Release update checks with a small, disposable on-disk cache."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_REPOSITORY = "OmniNodeCo/OmniScript"
DEFAULT_INSTALLER_REF = "arena/01a00f9c-omniscript"
DEFAULT_CACHE_SECONDS = 24 * 60 * 60


class UpdateCheckError(Exception):
    """Raised when release information cannot be obtained or decoded."""


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    checked_at: float
    from_cache: bool = False
    release_found: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cache_directory() -> Path:
    override = os.environ.get("OMNISCRIPT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "OmniScript" / "Cache"
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "omniscript"


def clear_update_cache() -> bool:
    path = cache_directory() / "update.json"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _installer_environment(channel: str, current_version: str) -> dict[str, str]:
    environment = os.environ.copy()
    # Private PyInstaller variables identify the currently running one-file
    # archive. Passing them through PowerShell/sh to a different executable
    # triggers: "Security validation failure: parent process has different executable".
    for name in list(environment):
        if name.startswith("_PYI_"):
            environment.pop(name, None)
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    environment["OMNISCRIPT_CHANNEL"] = channel
    environment["OMNISCRIPT_VERSION"] = "latest" if channel == "release" else current_version
    return environment


def install_update(
    channel: str,
    current_version: str,
    *,
    repository: str | None = None,
    installer_ref: str | None = None,
    opener: Callable[..., Any] = urlopen,
) -> str:
    """Run the verified platform installer for a release or nightly build."""

    if channel not in {"release", "nightly"}:
        raise UpdateCheckError("update channel must be 'release' or 'nightly'")
    repository = repository or os.environ.get("OMNISCRIPT_REPOSITORY", DEFAULT_REPOSITORY)
    installer_ref = installer_ref or os.environ.get("OMNISCRIPT_INSTALLER_REF", DEFAULT_INSTALLER_REF)
    environment = _installer_environment(channel, current_version)

    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if powershell is None:
            raise UpdateCheckError("PowerShell is required to update OmniScript on Windows")
        environment["OMNISCRIPT_WAIT_PID"] = str(os.getpid())
        url = f"https://raw.githubusercontent.com/{repository}/{installer_ref}/scripts/install.ps1"
        command = [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"(Invoke-RestMethod -UseBasicParsing -Uri '{url}') | Invoke-Expression",
        ]
        try:
            subprocess.Popen(command, env=environment)
        except OSError as error:
            raise UpdateCheckError(f"could not start the Windows updater: {error}") from error
        return "updater started; this OmniScript process will now exit so the executable can be replaced"

    url = f"https://raw.githubusercontent.com/{repository}/{installer_ref}/install.sh"
    try:
        request = Request(url, headers={"User-Agent": f"OmniScript/{current_version}"})
        with opener(request, timeout=15) as response:
            installer = response.read()
    except (HTTPError, URLError, OSError) as error:
        raise UpdateCheckError(f"could not download the OmniScript installer: {error}") from error

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="omniscript-update-", suffix=".sh", delete=False) as handle:
            handle.write(installer)
            path = Path(handle.name)
        completed = subprocess.run(["/bin/sh", str(path)], env=environment, check=False)
        if completed.returncode != 0:
            raise UpdateCheckError(f"the OmniScript installer exited with status {completed.returncode}")
    except OSError as error:
        raise UpdateCheckError(f"could not run the OmniScript installer: {error}") from error
    finally:
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    clear_update_cache()
    return f"installed the {channel} channel successfully"


def check_for_updates(
    current_version: str,
    *,
    repository: str | None = None,
    force: bool = False,
    cache_seconds: int = DEFAULT_CACHE_SECONDS,
    opener: Callable[..., Any] = urlopen,
    now: Callable[[], float] = time.time,
) -> UpdateInfo:
    repository = repository or os.environ.get("OMNISCRIPT_REPOSITORY", DEFAULT_REPOSITORY)
    cache_file = cache_directory() / "update.json"
    timestamp = now()
    if not force:
        cached = _read_cache(cache_file, repository, current_version, timestamp, cache_seconds)
        if cached is not None:
            return cached

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"OmniScript/{current_version}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=20",
        headers=headers,
    )
    release_found = True
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            payload = []
            release_found = False
        else:
            raise UpdateCheckError(f"GitHub returned HTTP {error.code} while checking for updates") from error
    except URLError as error:
        raise UpdateCheckError(f"could not reach GitHub: {error.reason}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise UpdateCheckError(f"could not read update information: {error}") from error

    if isinstance(payload, list):
        # GitHub orders this endpoint newest-first. Drafts and prereleases do not
        # belong to the user-selected Release channel.
        release = next(
            (
                item
                for item in payload
                if isinstance(item, dict)
                and not bool(item.get("draft"))
                and not bool(item.get("prerelease"))
            ),
            None,
        )
    elif isinstance(payload, dict):
        # Kept for compatibility with GitHub API proxies that return one release.
        release = payload
    else:
        raise UpdateCheckError("GitHub's releases response was not a list or object")

    if release is None:
        latest = current_version
        release_url = f"https://github.com/{repository}/releases"
        release_found = False
    else:
        latest = str(release.get("tag_name", "")).lstrip("v")
        release_url = str(release.get("html_url", ""))
        if not latest or not release_url:
            raise UpdateCheckError("a GitHub release is missing tag_name or html_url")

    info = UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        update_available=is_newer_version(latest, current_version),
        release_url=release_url,
        checked_at=timestamp,
        from_cache=False,
        release_found=release_found,
    )
    if release_found:
        _write_cache(cache_file, repository, info)
    else:
        # Never cache a negative lookup: a release can be published seconds later.
        clear_update_cache()
    return info


def is_newer_version(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _version_key(version: str) -> tuple[int, int, int, int, tuple[tuple[int, str], ...]]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", version)
    if not match:
        raise UpdateCheckError(f"unsupported release version {version!r}")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return major, minor, patch, 1, ()
    parts: list[tuple[int, str]] = []
    for part in prerelease.split("."):
        parts.append((0, f"{int(part):020d}") if part.isdigit() else (1, part.lower()))
    return major, minor, patch, 0, tuple(parts)


def _read_cache(
    path: Path,
    repository: str,
    current_version: str,
    timestamp: float,
    cache_seconds: int,
) -> UpdateInfo | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("repository") != repository:
            return None
        checked_at = float(payload["checked_at"])
        if timestamp - checked_at > cache_seconds:
            return None
        # Older versions cached a 404 for 24 hours. Negative release lookups are
        # intentionally ignored so a newly published release appears immediately.
        if not bool(payload.get("release_found", True)):
            return None
        latest = str(payload["latest_version"])
        release_url = str(payload["release_url"])
        return UpdateInfo(
            current_version=current_version,
            latest_version=latest,
            update_available=is_newer_version(latest, current_version),
            release_url=release_url,
            checked_at=checked_at,
            from_cache=True,
            release_found=bool(payload.get("release_found", True)),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, UpdateCheckError):
        return None


def _write_cache(path: Path, repository: str, info: UpdateInfo) -> None:
    payload = {
        "repository": repository,
        "latest_version": info.latest_version,
        "release_url": info.release_url,
        "checked_at": info.checked_at,
        "release_found": info.release_found,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError:
        # A read-only home directory must not make an update check fail.
        pass
