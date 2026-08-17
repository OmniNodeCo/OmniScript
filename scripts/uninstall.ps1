$ErrorActionPreference = "Stop"
$InstallDir = if ($env:OMNISCRIPT_INSTALL_DIR) { $env:OMNISCRIPT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\OmniScript" }
$BinDir = if ($env:OMNISCRIPT_BIN_DIR) { $env:OMNISCRIPT_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" }
$CacheDir = if ($env:OMNISCRIPT_CACHE_DIR) { $env:OMNISCRIPT_CACHE_DIR } else { Join-Path $env:LOCALAPPDATA "OmniScript\Cache" }

if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
if (Test-Path $CacheDir) { Remove-Item -Recurse -Force $CacheDir }
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BinDir "omni.cmd")
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BinDir "omniscript.cmd")
Write-Host "OmniScript was removed from $InstallDir"
Write-Host "OmniScript cache was removed from $CacheDir"
