# OmniScript Installers — EXE DMG DEB RPM

No more `install.sh` curl-pipe. Now proper native installers.

## Windows — Inno Setup EXE

**File:** `installer/windows/OmniScript.iss`

Build on Windows:

```bat
installer\windows\build.bat
```

Or PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File installer\windows\build.ps1
```

Requires:
- C compiler (gcc/clang/cc/cl) to build `omni.exe`
- Inno Setup 6 — https://jrsoftware.org/isinfo.php — provides `iscc`

Output: `dist/OmniScript-1.0.1-Windows-x86_64-Setup.exe`

What it does:
- Installs to `{pf}\OmniScript`
- Adds to PATH (optional task)
- Start Menu shortcuts, Desktop shortcut
- Uninstaller

## macOS — DMG

**Script:** `installer/macos/build-dmg.sh`

```bash
./installer/macos/build-dmg.sh
```

Creates `OmniScript.app` bundle + DMG:

- `dist/OmniScript-1.0.1-macOS.dmg` (on macOS with hdiutil)
- `dist/OmniScript-1.0.1-macOS.tar.gz` fallback on Linux

App bundle contains `omni` binary, README, examples.

On macOS, open DMG and drag to Applications.

## Linux — DEB + RPM + tarball

**DEB Script:** `installer/linux/build-deb.sh`

```bash
./installer/linux/build-deb.sh
```

Output:
- `dist/omniscript_1.0.1_amd64.deb`
- `dist/omniscript-1.0.1-linux-amd64.tar.gz`

DEB installs:
- `/usr/bin/omni`
- `/usr/share/doc/omniscript/`
- `/usr/share/applications/omniscript.desktop`

**RPM Script:** `installer/linux/build-rpm.sh`

```bash
./installer/linux/build-rpm.sh
```

Output:
- `dist/omniscript-1.0.1-1.x86_64.rpm`

RPM installs same files. Requires `rpmbuild`:
```bash
sudo apt-get install rpm   # Debian/Ubuntu
sudo dnf install rpm-build # Fedora
```

Install:

```bash
sudo dpkg -i dist/omniscript_1.0.1_amd64.deb
# or
sudo apt install ./dist/omniscript_1.0.1_amd64.deb

sudo rpm -i dist/omniscript-1.0.1-1.x86_64.rpm
# or
sudo dnf install ./dist/omniscript-1.0.1-1.x86_64.rpm
```

Uninstall:

```bash
sudo apt remove omniscript
sudo rpm -e omniscript
```

Tarball install:

```bash
tar -xzf dist/omniscript-1.0.1-linux-amd64.tar.gz -C /tmp
sudo cp /tmp/usr/bin/omni /usr/local/bin/
```

## All

```bash
./installer/build-all.sh
```

Builds generic tarball + DEB + RPM + DMG fallback + SHA256SUMS.txt in `dist/`.

## Makefile targets

```bash
make              # build omni
make install      # install to /usr/local/bin (or PREFIX)
make clean
make dmg          # macOS DMG (calls installer/macos/build-dmg.sh)
make deb          # Linux DEB
make rpm          # Linux RPM
make exe          # info about Windows EXE
make dist         # all installers EXE DMG DEB RPM
```
