# Install

One line, no dependencies. The installer takes the binary built for your machine from the newest release, checks its `.sha256`, puts `omni` on PATH **and installs it as an app**.

## Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

This creates:
- `~/.local/bin/omni` (binary)
- `~/.local/share/applications/omniscript.desktop` (app launcher, shows in GNOME/KDE)
- `~/.local/share/icons/hicolor/64x64/apps/omniscript.png` (icon, generated via omni)
- macOS: `~/Applications/OmniScript.app` bundle (Launchpad/Spotlight)

## Windows

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```

This creates:
- `%LOCALAPPDATA%\Programs\OmniScript\omni.exe` (binary, on PATH if configured)
- Start Menu `OmniScript` folder with `OmniScript.lnk`, `REPL.lnk`, `Uninstall.lnk`
- Desktop `OmniScript.lnk` (if Desktop exists)
- Icon `%LOCALAPPDATA%\OmniScript\icon.bmp` (generated via omni)

## Channels and options

- **release** (default) — newest published release, one binary, libc only, plus app entries
- **beta** (`-s beta` / `-Channel beta`) — repository itself, built with `cc` (no make required); `git pull` then rebuild is the upgrade, `make` still works as fallback

```bash
./install.sh --version 1.0.1   # a particular release
./install.sh --dry-run         # show plan, touch nothing
./install.sh --prefix ~/.local # where command goes (default)
```

Every install is recorded in `~/.local/share/omniscript/install.txt`, which [[Uninstall]] reads. Re-installing over same place is no-op unless foreign file sits there (`--force` moves to `.bak`).

## Other ways in

```bash
git clone https://github.com/OmniNodeCo/OmniScript && cd OmniScript
cc -O2 -std=c11 -o omni src/*.c -lX11   # no make needed
# or
make && ./omni --version                # classic make still works
./omni --version
```

## Check it worked

```bash
omni --version
omni -e 'cmd("echo hello")'
omni -e 'draw(window(200, 120, "hi"), circle(100, 60, 40, blue), save("hi.bmp"))'
```

## Keep it current

```bash
omni update --check
omni update
```

Update needs `curl` and refuses install without checksum.
