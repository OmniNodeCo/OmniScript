$ErrorActionPreference = "Stop"

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$InstallDir = if ($env:OMNISCRIPT_INSTALL_DIR) { $env:OMNISCRIPT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "OmniScript" }
$BinDir = if ($env:OMNISCRIPT_BIN_DIR) { $env:OMNISCRIPT_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" }
$DefaultSource = "https://github.com/OmniNodeCo/OmniScript/archive/refs/heads/main.zip"
$Source = if ($env:OMNISCRIPT_SOURCE) { $env:OMNISCRIPT_SOURCE } else { $DefaultSource }

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required."
}

if (-not $env:OMNISCRIPT_SOURCE -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "..\pyproject.toml"))) {
    $Source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

Write-Host "Installing OmniScript from $Source"
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
& $Python -m venv $InstallDir
$VenvPython = Join-Path $InstallDir "Scripts\python.exe"
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
& $VenvPython -m pip install --disable-pip-version-check $Source

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$OmniExe = Join-Path $InstallDir "Scripts\omni.exe"
$Launcher = Join-Path $BinDir "omni.cmd"
$AliasLauncher = Join-Path $BinDir "omniscript.cmd"
"@echo off`r`n`"$OmniExe`" %*" | Set-Content -Encoding ASCII $Launcher
"@echo off`r`n`"$OmniExe`" %*" | Set-Content -Encoding ASCII $AliasLauncher

Write-Host ""
Write-Host "OmniScript installed successfully."
Write-Host "  executable: $Launcher"
& $OmniExe --version
