# Uninstall

## Windows

Use Add/Remove Programs → OmniScript, or run uninstaller from Start Menu.

Or manually:

```bat
rmdir /s /q "%ProgramFiles%\OmniScript"
```

## macOS

```bash
rm -rf /Applications/OmniScript.app
rm -rf ~/Applications/OmniScript.app
```

If installed via DMG drag, just delete the app.

## Linux DEB

```bash
sudo apt remove omniscript
sudo dpkg -r omniscript
```

## Make install

```bash
sudo rm /usr/local/bin/omni
```

Or `make clean` in source dir.
