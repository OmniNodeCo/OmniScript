$ErrorActionPreference = "Stop"

$Repository = if ($env:OMNISCRIPT_REPOSITORY) { $env:OMNISCRIPT_REPOSITORY } else { "OmniNodeCo/OmniScript" }
$Version = if ($env:OMNISCRIPT_VERSION) { $env:OMNISCRIPT_VERSION } else { "latest" }
$InstallDir = if ($env:OMNISCRIPT_INSTALL_DIR) { $env:OMNISCRIPT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\OmniScript" }
$BinDir = if ($env:OMNISCRIPT_BIN_DIR) { $env:OMNISCRIPT_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" }

$Machine = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
$Architecture = switch ($Machine.ToUpperInvariant()) {
    "AMD64" { "x86_64" }
    "X86_64" { "x86_64" }
    "ARM64" { "arm64" }
    default { throw "Unsupported Windows architecture: $Machine" }
}
$Asset = "omni-windows-$Architecture.exe"
if ($Version -eq "latest") {
    $ReleaseBase = "https://github.com/$Repository/releases/latest/download"
} else {
    $CleanVersion = $Version.TrimStart("v")
    $ReleaseBase = "https://github.com/$Repository/releases/download/v$CleanVersion"
}

$Temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("omniscript-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Temporary | Out-Null
try {
    $DownloadedExe = Join-Path $Temporary $Asset
    $ChecksumFile = Join-Path $Temporary "SHA256SUMS"
    Write-Host "Downloading $Asset from $Repository ($Version)"
    Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/$Asset" -OutFile $DownloadedExe
    Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/SHA256SUMS" -OutFile $ChecksumFile

    $EscapedAsset = [regex]::Escape($Asset)
    $ChecksumLine = Get-Content $ChecksumFile | Where-Object { $_ -match "\s+\*?$EscapedAsset$" } | Select-Object -First 1
    if (-not $ChecksumLine) { throw "$Asset is missing from SHA256SUMS" }
    $Expected = ($ChecksumLine -split "\s+")[0].ToUpperInvariant()
    $Actual = (Get-FileHash -Algorithm SHA256 $DownloadedExe).Hash.ToUpperInvariant()
    if ($Expected -ne $Actual) { throw "Checksum verification failed for $Asset" }

    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $OmniExe = Join-Path $InstallDir "omni.exe"
    Move-Item -Force $DownloadedExe $OmniExe

    $Launcher = Join-Path $BinDir "omni.cmd"
    $AliasLauncher = Join-Path $BinDir "omniscript.cmd"
    "@echo off`r`n`"$OmniExe`" %*" | Set-Content -Encoding ASCII $Launcher
    "@echo off`r`n`"$OmniExe`" %*" | Set-Content -Encoding ASCII $AliasLauncher

    Write-Host "OmniScript installed to $OmniExe"
    & $OmniExe --version
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Temporary
}
