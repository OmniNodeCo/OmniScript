$ErrorActionPreference = "Stop"

$Repository = if ($env:OMNISCRIPT_REPOSITORY) { $env:OMNISCRIPT_REPOSITORY } else { "OmniNodeCo/OmniScript" }
$Version = if ($env:OMNISCRIPT_VERSION) { $env:OMNISCRIPT_VERSION } else { "latest" }
$NightlyRun = if ($env:OMNISCRIPT_NIGHTLY_RUN) { $env:OMNISCRIPT_NIGHTLY_RUN } else { "32032755910" }
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
    $CleanVersion = $Version -replace '^v', ''
    $ReleaseBase = "https://github.com/$Repository/releases/download/v$CleanVersion"
}

# GitHub's SHA-256 digest for each ZIP produced by the successful nightly build.
$NightlyDigests = @{
    "omni-windows-arm64.exe" = "551c75b39cbbb735092cba24331561ce6284cd4101d026036bf38a83cc651d15"
    "omni-windows-x86_64.exe" = "5594030fcd6364121abcf936361df85046c9f1d12e92598afd1003b8a35feadc"
}

$Temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("omniscript-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Temporary | Out-Null
try {
    $DownloadedExe = Join-Path $Temporary $Asset
    $ChecksumFile = Join-Path $Temporary "SHA256SUMS"
    $ReleaseAvailable = $true
    Write-Host "Looking for $Asset in $Repository releases ($Version)"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/$Asset" -OutFile $DownloadedExe
        Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/SHA256SUMS" -OutFile $ChecksumFile
    } catch {
        $ReleaseAvailable = $false
        Remove-Item -Force -ErrorAction SilentlyContinue $DownloadedExe, $ChecksumFile
    }

    if ($ReleaseAvailable) {
        $EscapedAsset = [regex]::Escape($Asset)
        $ChecksumLine = Get-Content $ChecksumFile | Where-Object { $_ -match "\s+\*?$EscapedAsset$" } | Select-Object -First 1
        if (-not $ChecksumLine) { throw "$Asset is missing from SHA256SUMS" }
        $Expected = ($ChecksumLine -split "\s+")[0].ToUpperInvariant()
        $Actual = (Get-FileHash -Algorithm SHA256 $DownloadedExe).Hash.ToUpperInvariant()
        if ($Expected -ne $Actual) { throw "Checksum verification failed for $Asset" }
    } else {
        if ($Version -ne "latest") { throw "OmniScript release v$CleanVersion was not found" }
        Write-Warning "No GitHub release exists yet; installing the verified nightly build from run $NightlyRun."
        $Archive = Join-Path $Temporary "$Asset.zip"
        $NightlyUrl = "https://nightly.link/$Repository/actions/runs/$NightlyRun/$Asset.zip"
        Invoke-WebRequest -UseBasicParsing -Uri $NightlyUrl -OutFile $Archive
        $Expected = $NightlyDigests[$Asset]
        if (-not $Expected) { throw "No trusted nightly digest is registered for $Asset" }
        $Actual = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
        if ($Expected -ne $Actual) { throw "Nightly archive checksum verification failed for $Asset" }
        $Extracted = Join-Path $Temporary "extracted"
        Expand-Archive -Force -Path $Archive -DestinationPath $Extracted
        $BuiltFile = Get-ChildItem -Path $Extracted -Recurse -File | Where-Object { $_.Name -eq $Asset } | Select-Object -First 1
        if (-not $BuiltFile) { throw "$Asset was not found inside the nightly archive" }
        Copy-Item -Force $BuiltFile.FullName $DownloadedExe
    }

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
