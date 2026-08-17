# Getting started

## Requirements

- Linux or Windows on x86-64/ARM64, or Apple Silicon macOS
- No separate runtime for a release executable
- Python 3.10+ only when developing or installing from source

## Install

### One-line installer (macOS/Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/install.sh | sh
```

The installer detects the OS and architecture, downloads the matching executable, verifies its SHA-256 checksum, and installs `omni` under `~/.local/bin`.

### Command Prompt (Windows)

From a downloaded copy or repository checkout:

```bat
install.bat
```

### PowerShell (Windows)

```powershell
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/install.ps1 | iex
```

The Windows installers verify and write `omni.exe` to `%LOCALAPPDATA%\Programs\OmniScript`, with command launchers under `%LOCALAPPDATA%\Microsoft\WindowsApps`.

See [Installers and native executables](installers-and-binaries.md) for version overrides, release asset names, and local builds.

### From source

```bash
git clone https://github.com/OmniNodeCo/OmniScript.git
cd OmniScript
python3 -m pip install -e .
omni doctor
```

`pipx install .` also works.

## First program

Save this as `hello.omni`:

```omni
seal subject := "universe"
emit "Hello, " + subject + "!"
```

Run it:

```bash
omni run hello.omni
# shorthand:
omni hello.omni
```

## Create a project

```bash
omni init solar
cd solar
omni run
omni test
```

The generated `omni.toml` points to `src/main.omni`:

```toml
[project]
name = "solar"
version = "0.1.0"
entry = "src/main.omni"
```

## Interactive mode

Run `omni repl`. The REPL preserves bindings between entries and waits for closing braces on multiline blocks.

```text
>>> bind radius := 4
>>> radius ** 2
=> 16
>>> .vars
radius
```

Use `.help`, `.vars`, and `.exit` for REPL commands.

## Next steps

Read the [language guide](language-guide.md), then run `omni examples/tour.omni` from the repository.
