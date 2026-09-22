# Install — native installers EXE DMG DEB RPM

No more curl pipe. Proper native installers.

## Windows — EXE (Inno Setup)

Build:

```bat
installer\windows\build.bat
```

Or PowerShell:

```powershell
installer\windows\build.ps1
```

Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php).  
Output: `dist/OmniScript-1.0.2-Windows-x86_64-Setup.exe`

Run the EXE — installs to Program Files, adds to PATH (optional), Start Menu shortcuts, uninstaller.

## macOS — DMG

```bash
./installer/macos/build-dmg.sh
```

Output: `dist/OmniScript-1.0.2-macOS.dmg`

Open DMG, drag `OmniScript.app` to Applications. Contains `omni` binary + examples.

## Linux — DEB

```bash
./installer/linux/build-deb.sh
sudo dpkg -i dist/omniscript_1.0.2_amd64.deb
```

## Linux — RPM

```bash
./installer/linux/build-rpm.sh
sudo rpm -i dist/omniscript-1.0.2-1.x86_64.rpm
# or
sudo dnf install ./dist/omniscript-1.0.2-1.x86_64.rpm
```

Or tarball:

```bash
tar -xzf dist/omniscript-1.0.2-linux-amd64.tar.gz
sudo cp usr/bin/omni /usr/local/bin/
```

## All

```bash
./installer/build-all.sh
make dist
```

Creates `dist/` with EXE (on Windows), DMG, DEB, RPM, tarballs + `SHA256SUMS.txt`.

## Dev build

```bash
make
./omni --version
sudo make install
```
