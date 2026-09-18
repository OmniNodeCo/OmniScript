# Uninstall

Removes exactly what install.sh/install.ps1 put there, using the manifest `~/.local/share/omniscript/install.txt`.

## Linux and macOS

```bash
./uninstall.sh
./uninstall.sh --purge   # also history, cloned source, manifest
./uninstall.sh --dry-run
```

## Windows

```powershell
.\uninstall.ps1
.\uninstall.ps1 -Purge
.\uninstall.ps1 -DryRun
```

The script never deletes a source tree you cloned yourself; only one it cloned under the data dir. A foreign `omni` (not ours) needs `--force` / `-Force`.

Backups from `--force` installs stay as `omni.bak` / `omni.exe.bak` / `omni.cmd.bak`.

After purge, to put release back:

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```
