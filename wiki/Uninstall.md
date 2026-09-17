# Uninstall

Takes out exactly what the installer put in — commands, downloaded executable,
manifest — and nothing else. A source tree you cloned yourself is never
deleted.

## Linux and macOS

```bash
./uninstall.sh                 # take out the commands
./uninstall.sh --purge         # ...and the REPL history, a cloned source tree, the manifest
./uninstall.sh --dry-run       # show what would go, remove nothing
```

No checkout handy? The release channel one-liner works without one:

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/uninstall.sh | bash -s -- --purge
```

## Windows

```powershell
.\uninstall.ps1 -Purge
```

## Safety rules

- Only paths the manifest lists are removed. A command the installer cannot
  prove it created is left alone (use `--force` / `-Force` to take it anyway —
  read what it says first).
- A `.bak` copy of anything the installer moved aside is left next to it.
- `pip uninstall omniscript-lang` removes only the `pip install .` kind.
