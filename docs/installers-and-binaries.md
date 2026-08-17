# Installers and native executables

OmniScript releases provide self-contained executables. End users do **not** need Python when installing a release binary.

## Release assets

Every tagged release built by `build.yml` contains:

| Operating system | Architecture | Asset |
|---|---|---|
| Linux | x86-64 | `omni-linux-x86_64` |
| Linux | ARM64 | `omni-linux-arm64` |
| macOS | Intel x86-64 | `omni-macos-x86_64` |
| macOS | Apple Silicon ARM64 | `omni-macos-arm64` |
| Windows | x86-64 | `omni-windows-x86_64.exe` |
| Windows | ARM64 | `omni-windows-arm64.exe` |

`SHA256SUMS` contains a checksum for every executable. All installers verify that checksum before replacing an existing installation.

## Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | sh
```

The script detects the OS and CPU, downloads the matching executable, verifies it, and installs `omni` plus an `omniscript` alias under `~/.local/bin`.

Overrides:

```bash
OMNISCRIPT_VERSION=0.1.0 ./install.sh
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
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/scripts/install.ps1 | iex
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

`build.yml` is a complete GitHub Actions workflow. Install it at `.github/workflows/build.yml` to activate it. It performs three stages:

1. tests Python 3.10 and 3.12 on Linux, macOS, and Windows;
2. builds and smoke-tests all six OS/architecture executables in native runners;
3. for tags matching `v*`, creates checksums and publishes every executable as a GitHub Release asset.

Create a release after updating the package version:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release job requires `contents: write`; regular test and build jobs use read-only repository permissions.

## Uninstall

```bash
./scripts/uninstall.sh
```

Windows PowerShell:

```powershell
.\scripts\uninstall.ps1
```
