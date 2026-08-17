# Getting started

## Requirements

- Windows, macOS, or Linux
- Python 3.10+

The runtime has no third-party Python dependencies.

## Install

### One-line installer (macOS/Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/scripts/install.sh | sh
```

The installer creates an isolated environment under `~/.local/share/omniscript` and links `omni` into `~/.local/bin`. Ensure that directory is on `PATH`.

### PowerShell (Windows)

```powershell
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/scripts/install.ps1 | iex
```

The installer writes an isolated environment to `%LOCALAPPDATA%\OmniScript` and a launcher to `%LOCALAPPDATA%\Microsoft\WindowsApps` by default.

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
