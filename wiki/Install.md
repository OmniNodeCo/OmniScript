# Install

One line, no Python needed. The installer takes the file built for your machine
out of the newest release, checks its sha256, and puts `omni` and `omniscript`
on your PATH.

## Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

## Windows

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```

## Channels and options

Two channels:

- **release** (the default) — the newest published release. One file, no
  Python needed.
- **beta** (`-s beta` / `-Channel beta`) — the repository itself. Needs
  Python 3.10+; `git pull` is then the upgrade.

```bash
./install.sh --version 1.1.0   # a particular release
./install.sh --dry-run         # show the plan, touch nothing
./install.sh --prefix ~/.local # where the commands go (default)
```

Every install is recorded in `~/.local/share/omniscript/install.txt`, which is
what [[Uninstall]] reads. Re-installing over the same place is a no-op, not an
error — unless something that is not ours sits where a command would go, in
which case the installer says so and stops (`--force` moves it to `.bak`).

## Other ways in

```bash
pip install omniscript-lang==1.1.0   # a venv or system-wide
python3 omni-1.1.0-any.pyz           # the zipapp from the release
git clone https://github.com/OmniNodeCo/OmniScript && cd OmniScript && ./omni
```

## Check it worked

```bash
omni --version
omni -e 'cmd("echo hello")'
omni -e 'draw(window(200, 120, "hi"), circle(100, 60, 40, blue))'
```

## Keep it current

```bash
omni update --check     # what is published, what you have
omni update             # fetch it, check the sha256, swap it in, prove it runs
omni update -c beta     # follow the repository instead
```
