$ErrorActionPreference = "Stop"
$InstallDir = if ($env:OMNISCRIPT_INSTALL_DIR) { $env:OMNISCRIPT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\OmniScript" }
$BinDir = if ($env:OMNISCRIPT_BIN_DIR) { $env:OMNISCRIPT_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" }

if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BinDir "omni.cmd")
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BinDir "omniscript.cmd")
Write-Host "OmniScript was removed from $InstallDir"
