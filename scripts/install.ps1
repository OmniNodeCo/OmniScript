$ErrorActionPreference = "Stop"

if ($env:OMNISCRIPT_WAIT_PID) {
    $ParentProcess = Get-Process -Id ([int]$env:OMNISCRIPT_WAIT_PID) -ErrorAction SilentlyContinue
    if ($ParentProcess) {
        Write-Host "Waiting for the running OmniScript process to close..."
        $ParentProcess | Wait-Process
    }
    Remove-Item Env:OMNISCRIPT_WAIT_PID -ErrorAction SilentlyContinue
}

# A PyInstaller one-file executable passes private bootloader state to child
# processes. It must not reach a newly replaced executable with another archive.
Get-ChildItem Env: | Where-Object { $_.Name -like "_PYI_*" } | ForEach-Object {
    Remove-Item "Env:$($_.Name)"
}
$env:PYINSTALLER_RESET_ENVIRONMENT = "1"

$Repository = if ($env:OMNISCRIPT_REPOSITORY) { $env:OMNISCRIPT_REPOSITORY } else { "OmniNodeCo/OmniScript" }
$BundledVersion = "0.2.1"
$Version = if ($env:OMNISCRIPT_VERSION) { $env:OMNISCRIPT_VERSION } else { $BundledVersion }
$Channel = if ($env:OMNISCRIPT_CHANNEL) { $env:OMNISCRIPT_CHANNEL.ToLowerInvariant() } else { "auto" }
if ($Channel -notin @("auto", "release", "nightly")) {
    throw "OMNISCRIPT_CHANNEL must be auto, release, or nightly"
}
$NightlyRun = if ($env:OMNISCRIPT_NIGHTLY_RUN) { $env:OMNISCRIPT_NIGHTLY_RUN } else { "32053497470" }
$InstallDir = if ($env:OMNISCRIPT_INSTALL_DIR) { $env:OMNISCRIPT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\OmniScript" }
$BinDir = if ($env:OMNISCRIPT_BIN_DIR) { $env:OMNISCRIPT_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" }
$CacheDir = if ($env:OMNISCRIPT_CACHE_DIR) { $env:OMNISCRIPT_CACHE_DIR } else { Join-Path $env:LOCALAPPDATA "OmniScript\Cache" }

$Machine = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
$Architecture = switch ($Machine.ToUpperInvariant()) {
    "AMD64" { "x86_64" }
    "X86_64" { "x86_64" }
    "ARM64" { "arm64" }
    default { throw "Unsupported Windows architecture: $Machine" }
}
$Asset = "omni-windows-$Architecture.exe"
$CleanVersion = $Version -replace '^v', ''
if ($Version -eq "latest") {
    $ReleaseBase = "https://github.com/$Repository/releases/latest/download"
} else {
    $ReleaseBase = "https://github.com/$Repository/releases/download/v$CleanVersion"
}

# GitHub's SHA-256 digest for each ZIP produced by the successful nightly build.
$NightlyDigests = @{
    "omni-windows-arm64.exe" = "d53a7b0ef3e369ffab4d00a4e03332762e6c12b007dc992b21b8f79fa317b9bc"
    "omni-windows-x86_64.exe" = "4b5d46d9b2e51fe57976f473826b8dc352c61c159d5be06777902b64179c333e"
}

$Temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("omniscript-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Temporary | Out-Null
try {
    $DownloadedExe = Join-Path $Temporary $Asset
    $ChecksumFile = Join-Path $Temporary "SHA256SUMS"
    $ReleaseAvailable = $false
    if ($Channel -ne "nightly") {
        $ReleaseAvailable = $true
        Write-Host "Looking for $Asset in $Repository releases ($Version)"
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/$Asset" -OutFile $DownloadedExe
            Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseBase/SHA256SUMS" -OutFile $ChecksumFile
        } catch {
            $ReleaseAvailable = $false
            Remove-Item -Force -ErrorAction SilentlyContinue $DownloadedExe, $ChecksumFile
        }
    } else {
        Write-Host "Installing $Asset from the nightly channel"
    }

    if ($ReleaseAvailable) {
        $EscapedAsset = [regex]::Escape($Asset)
        $ChecksumLine = Get-Content $ChecksumFile | Where-Object { $_ -match "\s+\*?$EscapedAsset$" } | Select-Object -First 1
        if (-not $ChecksumLine) { throw "$Asset is missing from SHA256SUMS" }
        $Expected = ($ChecksumLine -split "\s+")[0].ToUpperInvariant()
        $Actual = (Get-FileHash -Algorithm SHA256 $DownloadedExe).Hash.ToUpperInvariant()
        if ($Expected -ne $Actual) { throw "Checksum verification failed for $Asset" }
    } else {
        if ($Channel -eq "release") { throw "No matching OmniScript release was found" }
        if ($Channel -eq "auto" -and $Version -ne "latest" -and $CleanVersion -ne $BundledVersion) {
            throw "OmniScript release v$CleanVersion was not found"
        }
        if ($Channel -eq "nightly") {
            Write-Host "Installing verified nightly run $NightlyRun"
        } else {
            Write-Warning "Release v$BundledVersion is not published yet; installing its verified build from run $NightlyRun."
        }
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
    # Remove negative/stale GitHub release checks after replacing the executable.
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $CacheDir

    Write-Host "OmniScript installed to $OmniExe"
    & $OmniExe --version
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Temporary
}
