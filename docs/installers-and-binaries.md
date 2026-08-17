# Installers and native executables

OmniScript releases provide self-contained executables. End users do **not** need Python when installing a release binary.

## Release assets

Every tagged release built by `release.yml` contains:

| Operating system | Architecture | Asset |
|---|---|---|
| Linux | x86-64 | `omni-linux-x86_64` |
| Linux | ARM64 | `omni-linux-arm64` |
| macOS | Apple Silicon ARM64 | `omni-macos-arm64` |
| Windows | x86-64 | `omni-windows-x86_64.exe` |
| Windows | ARM64 | `omni-windows-arm64.exe` |

`SHA256SUMS` contains a checksum for every released executable. All installers verify checksums before replacing an existing installation. When the installer's matching release is not published yet, it automatically falls back to the successful artifacts from workflow run `32052400359`; those artifact ZIPs are pinned to their GitHub-reported SHA-256 digests.

## Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/install.sh | sh
```

The script detects the OS and CPU, downloads the matching executable, verifies it, and installs `omni` plus an `omniscript` alias under `~/.local/bin`.

Overrides:

```bash
OMNISCRIPT_VERSION=0.2.0 ./install.sh
OMNISCRIPT_CHANNEL=nightly ./install.sh
OMNISCRIPT_CHANNEL=release ./install.sh
OMNISCRIPT_BIN_DIR="$HOME/bin" ./install.sh
OMNISCRIPT_REPOSITORY=owner/fork ./install.sh
```

## Windows Batch

Download or run `install.bat`. From a checkout:

```bat
install.bat
```

The Batch launcher invokes the checksum-verifying PowerShell installer. It installs the executable under `%LOCALAPPDATA%\Programs\OmniScript` and writes `omni.cmd` and `omniscript.cmd` launchers under `%LOCALAPPDATA%\Microsoft\WindowsApps`.

PowerShell can also be used directly:

```powershell
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/install.ps1 | iex
```

The Windows installer supports the `OMNISCRIPT_VERSION`, `OMNISCRIPT_REPOSITORY`, `OMNISCRIPT_INSTALL_DIR`, and `OMNISCRIPT_BIN_DIR` environment variables.

## Build the current operating system locally

A native executable must be built on its target operating system and architecture. Install the build extra and run the builder:

```bash
python3 -m venv .build-venv
. .build-venv/bin/activate       # Windows: .build-venv\Scripts\activate
python -m pip install -e ".[build]"
python scripts/build_executable.py --name omni --asset omni --output artifacts
```

Convenience launchers choose a release-style filename automatically:

```bash
./scripts/build_all_local.sh       # Linux or macOS
scripts\build_windows.bat          # Windows
```

The convenience launchers create an isolated `.build-venv` automatically. The builder runs PyInstaller in one-file console mode, copies the executable into `artifacts/`, and executes `--version` as a smoke test. Build environments and artifacts are intentionally ignored by Git.

## Automated builds and releases

Two complete GitHub Actions workflows are included:

- `build.yml` tests Python 3.10/3.12 on Linux, macOS, and Windows, then builds and smoke-tests all five supported executable assets.
- `release.yml` validates the release tag against both version declarations, repeats the tests, builds all native assets, generates `SHA256SUMS`, and publishes a GitHub Release.

Install them as `.github/workflows/build.yml` and `.github/workflows/release.yml`. A tag matching `v*` starts the release workflow. It can also be started manually with a tag and prerelease flag.

```bash
python scripts/verify_release.py v0.2.0
git tag v0.2.0
git push origin v0.2.0
```

The release publishing job alone receives `contents: write`; all validation and build jobs remain read-only.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/uninstall.sh | sh
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/uninstall.ps1 | iex
```

Uninstallers remove the executable, command aliases, legacy installation data, and the update cache. Override the cache location with `OMNISCRIPT_CACHE_DIR` if needed.
