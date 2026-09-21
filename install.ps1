# Install OmniScript on Windows (and, if you like, anywhere pwsh runs).
#
#   .\install.ps1                    # from this checkout: a shim into %LOCALAPPDATA%\Programs\OmniScript
#   .\install.ps1 -Channel release   # the published release: one file, no dependencies
#   .\install.ps1 -Prefix C:\Tools   # put it somewhere of your own
#
# Two channels, the same two `omni update` follows:
#
#   release   what the project published: a standalone executable for this
#             machine. The default when this script arrives with no source tree
#             beside it.
#   beta      the repository itself: this checkout, or a clone of main, built
#             with a C compiler (no make required), with the command pointing at
#             it so `git pull` plus a rebuild is an upgrade. The default when
#             the script is run from a source tree.
#
# If the release channel cannot deliver -- nothing published yet, no file built
# for this machine, no network -- the script says so and installs from the
# repository instead.
#
# Windows needs a shim rather than a symlink for beta installs: creating
# symlinks wants administrator rights or Developer Mode, while a two-line .cmd
# file in a directory on PATH works for everybody. Under pwsh on Linux or macOS
# this script makes real symlinks instead, exactly like install.sh does. A
# release executable needs no shim at all -- omni.exe runs itself.
#
# Beta builds directly with the C compiler (cl, gcc, clang, cc) -- no make,
# no build.ps1, no extra tools. If direct compile fails, make is tried as
# fallback for older environments.
#
# Everything created here is written to a manifest so uninstall.ps1 can remove
# it -- and only it.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('', 'release', 'beta')]
    [string]$Channel = '',
    [string]$Version = '',
    [string]$Prefix = '',
    [string]$ApiUrl = '',
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'

$Repo = 'OmniNodeCo/OmniScript'
$RepoUrl = "https://github.com/$Repo.git"
$ApiUrl = if ($ApiUrl) { $ApiUrl } elseif ($env:OMNISCRIPT_API_URL) { $env:OMNISCRIPT_API_URL } else { 'https://api.github.com' }
$Commands = @('omni')

$IsWin = [System.Environment]::OSVersion.Platform -eq 'Win32NT'

# State the two channels fill in as they go.
$Source = ''
$Mode = ''
$ReleaseResult = 1
$RelTag = ''
$RelVersion = ''
$RelAssetName = ''
$RelDownload = ''
$RelFatal = ''
$BinaryPath = ''
# App installation paths
$DesktopFile = ''
$IconFile = ''
$StartMenuDir = ''
$AppShortcuts = New-Object System.Collections.Generic.List[string]

function Write-Info { param([string]$Text) Write-Host "==> $Text" }
function Write-Note { param([string]$Text) Write-Host "    $Text" }
function Write-Warn { param([string]$Text) Write-Host "    $Text" -ForegroundColor Yellow }
function Stop-Die {
    param([string]$Text)
    Write-Host "install.ps1: error: $Text" -ForegroundColor Red
    exit 1
}
function Invoke-OrShow {
    param([scriptblock]$Block, [string]$Description)
    if ($DryRun) { Write-Note "[dry-run] $Description" } else { & $Block }
}

if ($Help) {
    @'
Usage: install.ps1 [options]

  -Channel release|beta    release (the default): the newest published release,
                           one file, no dependencies. beta: the repository --
                           the source tree beside this script, or a clone of
                           main. Needs a C compiler (no make required).
  -Version VERSION         a particular release, for example 1.0.0 or v1.0.0
  -Prefix DIR              install root                [see below]
  -ApiUrl URL              the GitHub API to ask       [https://api.github.com]
  -Force                   replace commands this script did not create
  -DryRun                  print what would happen and change nothing
  -Help                    this text

Defaults:
  Windows    -Prefix %LOCALAPPDATA%\Programs\OmniScript   (commands land directly in it)
  elsewhere  -Prefix ~/.local                             (commands land in PREFIX/bin)

Everything installed is recorded in install.txt under the state directory, which
is what uninstall.ps1 reads:
  Windows    %LOCALAPPDATA%\OmniScript
  elsewhere  ${XDG_DATA_HOME:-~/.local/share}/omniscript
'@ | Write-Host
    exit 0
}

# ---------------------------------------------------------------- defaults
if (-not $Prefix) {
    if ($IsWin) {
        $local = $env:LOCALAPPDATA
        if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\Local' }
        $Prefix = Join-Path $local 'Programs\OmniScript'
    } else {
        $Prefix = Join-Path $env:HOME '.local'
    }
}
if ($IsWin) { $Bin = $Prefix } else { $Bin = Join-Path $Prefix 'bin' }

if ($IsWin) {
    $local = $env:LOCALAPPDATA
    if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\Local' }
    $DataDir = Join-Path $local 'OmniScript'
} elseif ($env:XDG_DATA_HOME) {
    $DataDir = Join-Path $env:XDG_DATA_HOME 'omniscript'
} else {
    $DataDir = Join-Path $env:HOME '.local/share/omniscript'
}
$Manifest = Join-Path $DataDir 'install.txt'

# ------------------------------------------------------------- this machine
function Get-PlatformTag {
    if ($IsWin) { $os = 'windows' }
    elseif ($IsMacOS) { $os = 'macos' }
    elseif ($IsLinux) { $os = 'linux' }
    else { $os = ([System.Environment]::OSVersion.Platform.ToString()).ToLowerInvariant() }

    $arch = $env:PROCESSOR_ARCHITECTURE
    if (-not $arch) {
        $uname = Get-Command uname -ErrorAction SilentlyContinue
        if ($uname) { $arch = (& uname -m 2>$null) }
    }
    if (-not $arch) { $arch = 'unknown' }
    switch ($arch.ToLowerInvariant()) {
        'amd64' { $arch = 'x86_64'; break }
        'x64' { $arch = 'x86_64'; break }
        'x86_64' { $arch = 'x86_64'; break }
        'arm64' { $arch = 'arm64'; break }
        'aarch64' { $arch = 'arm64'; break }
        'x86' { $arch = 'x86'; break }
        default { $arch = $arch.ToLowerInvariant() }
    }
    return "$os-$arch"
}

# -------------------------------------------------------------- downloading
function ConvertFrom-FileUrl {
    param([string]$Url)
    $local = $Url -replace '^file://', ''
    $local = [System.Uri]::UnescapeDataString($local)
    if ($IsWin -and $local -match '^/([A-Za-z]:)') { $local = $local.Substring(1) }
    return $local
}

function Read-Url {
    param([string]$Url)
    if ($Url -like 'file://*') {
        $local = ConvertFrom-FileUrl $Url
        if (-not (Test-Path -LiteralPath $local)) { throw "there is no file at $local" }
        return (Get-Content -Raw -LiteralPath $local)
    }
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 60 `
        -Headers @{ 'User-Agent' = 'omniscript-install' }
    return ConvertTo-Text $response.Content
}

function ConvertTo-Text {
    param($Content)
    if ($null -eq $Content) { return '' }
    if ($Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($Content) }
    if ($Content -is [string]) { return $Content }
    return "$Content"
}

function Save-Url {
    param([string]$Url, [string]$Destination)
    if ($Url -like 'file://*') {
        Copy-Item -LiteralPath (ConvertFrom-FileUrl $Url) -Destination $Destination -Force
        return
    }
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 900 `
        -Headers @{ 'User-Agent' = 'omniscript-install' }
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-Recorded {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Manifest)) { return $false }
    foreach ($line in (Get-Content -LiteralPath $Manifest)) {
        $parts = "$line" -split '=', 2
        if ($parts.Count -lt 2) { continue }
        $key = $parts[0].Trim()
        if (($key -eq 'command' -or $key -eq 'binary') -and $parts[1].Trim() -eq $Path) {
            return $true
        }
    }
    return $false
}

function Test-SourceTree {
    param([string]$Dir)
    # A source tree is src/main.c existing; Makefile is optional now (no make required)
    return (Test-Path -LiteralPath (Join-Path $Dir 'src/main.c'))
}

function New-Shim {
    param([string]$Path, [string]$Target)
    if ($IsWin) {
        $lines = @(
            '@echo off',
            ('"{0}" %*' -f $Target)
        )
        Set-Content -Path $Path -Value $lines -Encoding ASCII
    } else {
        if (Test-Path $Path) { Remove-Item -Force $Path }
        New-Item -ItemType SymbolicLink -Path $Path -Target $Target | Out-Null
    }
}

# ============================================================ release channel
function Install-FromRelease {
    $script:ReleaseResult = 1
    $platform = Get-PlatformTag
    $api = $ApiUrl.TrimEnd('/')
    if ($Version) {
        $script:RelTag = if ($Version.StartsWith('v')) { $Version } else { "v$Version" }
        $url = "$api/repos/$Repo/releases/tags/$RelTag"
    } else {
        $url = "$api/repos/$Repo/releases/latest"
    }

    Write-Info "Asking $Repo what it has published"
    $answer = ''
    try {
        $answer = Read-Url $url
        $release = $answer | ConvertFrom-Json
    } catch {
        Write-Warn "no answer from $url ($($_.Exception.Message))"
        if ($Version) { $script:RelFatal = "$Repo has no release tagged $RelTag" }
        return
    }
    $script:RelTag = "$($release.tag_name)"
    if (-not $RelTag) {
        Write-Warn 'that release has no tag on it'
        $head = $answer.Substring(0, [Math]::Min(160, $answer.Length)) -replace "\s+", ' '
        Write-Note "$url answered: $head"
        if ($Version) { $script:RelFatal = "$Repo has no release tagged $Version" }
        return
    }
    $script:RelVersion = $RelTag.TrimStart('v')
    Write-Note "the newest release is $RelTag"

    $suffix = ''
    if ($IsWin) { $suffix = '.exe' }
    $wanted = "omni-$platform$suffix"
    $asset = @($release.assets) | Where-Object { "$($_.name)" -eq $wanted } | Select-Object -First 1
    if (-not $asset) {
        Write-Warn "nothing in $RelTag is built for $platform"
        return
    }
    $downloadUrl = "$($asset.browser_download_url)"
    if (-not $downloadUrl) { $downloadUrl = "$($asset.url)" }
    $script:RelAssetName = "$($asset.name)"
    Write-Note "this machine takes $RelAssetName"

    $tempDir = if ($env:TEMP) { $env:TEMP } else { [System.IO.Path]::GetTempPath() }
    $script:RelDownload = Join-Path $tempDir ("omniscript-download-{0}" -f [System.Diagnostics.Process]::GetCurrentProcess().Id)
    if ($DryRun) {
        Write-Note "[dry-run] download $downloadUrl"
    } else {
        Write-Info "Downloading $RelAssetName"
        try {
            Save-Url -Url $downloadUrl -Destination $RelDownload
        } catch {
            Write-Warn "the download failed: $($_.Exception.Message)"
            return
        }
        $size = (Get-Item -LiteralPath $RelDownload).Length
        Write-Note "$size bytes"
        $hashName = "$RelAssetName.sha256"
        $sumsAsset = @($release.assets) | Where-Object { "$($_.name)" -eq $hashName } | Select-Object -First 1
        if (-not $sumsAsset) {
            Remove-Item -Force -LiteralPath $RelDownload -ErrorAction SilentlyContinue
            Write-Warn "the release publishes no checksum for $RelAssetName -- refusing it"
            $script:RelFatal = "$RelTag publishes no checksum for $RelAssetName"
            return
        }
        $expected = ''
        try {
            $body = ConvertTo-Text (Read-Url "$($sumsAsset.browser_download_url)")
            $expected = (($body -split "\s+")[0]).ToLowerInvariant()
        } catch { }
        if (-not $expected) {
            Remove-Item -Force -LiteralPath $RelDownload -ErrorAction SilentlyContinue
            Write-Warn 'the checksum could not be compared -- refusing the download'
            $script:RelFatal = "could not verify $RelAssetName"
            return
        }
        $actual = Get-Sha256 $RelDownload
        if ($actual -ne $expected) {
            Remove-Item -Force -LiteralPath $RelDownload -ErrorAction SilentlyContinue
            Write-Warn "checksum mismatch for $RelAssetName"
            Write-Warn "  the release says $expected"
            Write-Warn "  the download is  $actual"
            $script:RelFatal = "$RelAssetName does not match the checksum the release published"
            return
        }
        Write-Note 'sha256 verified'
    }

    if ($IsWin) { $name = 'omni.exe' } else { $name = 'omni' }
    $target = Join-Path $Bin $name

    if ((Test-Path -LiteralPath $target) -and -not $Force -and -not (Test-Recorded $target)) {
        Stop-Die "$target already exists and was not created by this script.`n       Re-run with -Force to move it aside (a .bak copy is kept next to it)."
    }
    Invoke-OrShow { New-Item -ItemType Directory -Force -Path $Bin | Out-Null } "mkdir $Bin"

    if ($DryRun) {
        Write-Note "[dry-run] install $RelAssetName as $target"
        $script:BinaryPath = $target
        $script:Mode = 'binary'
        $script:CommandKind = 'binary'
        $script:OmniVersion = $RelVersion
        $InstalledCommands.Add($target)
        $script:ReleaseResult = 0
        return
    }

    Move-Item -Force -LiteralPath $RelDownload -Destination $target
    if (-not $IsWin) { & chmod 755 $target }
    $script:BinaryPath = $target
    $script:Mode = 'binary'
    $script:CommandKind = 'binary'
    $script:OmniVersion = $RelVersion
    $InstalledCommands.Add($target)
    Write-Note "installed $target"
    $script:ReleaseResult = 0
}

# ------------------------------------------------------- the shared tail
function Write-Manifest {
    if ($DryRun) {
        Write-Note "[dry-run] write $Manifest"
        return
    }
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $history = Join-Path $(if ($IsWin) { $env:USERPROFILE } else { $env:HOME }) '.omniscript_history'
    $lines = @(
        "api_url=$ApiUrl",
        "bin_dir=$Bin",
        "binary=$BinaryPath",
        "channel=$Channel",
        "cloned_by_installer=$(if ($Cloned) { 1 } else { 0 })",
        "command_kind=$CommandKind",
        "data_dir=$DataDir",
        "history_file=$history",
        "installed_at=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
        "mode=$Mode",
        "package=omniscript-lang",
        "release_tag=$RelTag",
        "repo=$Repo",
        "repo_url=$RepoUrl",
        "source=$Source",
        "version=$OmniVersion"
    )
    foreach ($path in $InstalledCommands) { if ($path) { $lines += "command=$path" } }
    # App entries
    if ($DesktopFile) { $lines += "desktop_file=$DesktopFile" }
    if ($IconFile) { $lines += "icon_file=$IconFile" }
    if ($StartMenuDir) { $lines += "start_menu_dir=$StartMenuDir" }
    foreach ($s in $AppShortcuts) { if ($s) { $lines += "shortcut=$s" } }
    [System.IO.File]::WriteAllLines($Manifest, [string[]]$lines)
    if (-not (Test-Path -LiteralPath $Manifest)) { Stop-Die "the manifest did not get written to $Manifest" }
    Write-Note "wrote $Manifest"
}

function Test-Install {
    if ($DryRun) { return }
    Write-Info 'Checking the install'
    if ($IsWin) { $probePath = Join-Path $Bin $(if ($Mode -eq 'binary') { 'omni.exe' } else { 'omni.cmd' }) }
    else { $probePath = Join-Path $Bin 'omni' }
    if (-not (Test-Path -LiteralPath $probePath)) {
        if ($InstalledCommands.Count -gt 0) { $probePath = $InstalledCommands[0] } else { Stop-Die "$probePath is missing after the install" }
    }
    $reported = (& $probePath --version) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$probePath --version failed: $reported" }
    Write-Note "$reported"
    $smoke = & $probePath -e 'cmd(whoami)'
    if ($LASTEXITCODE -ne 0) { throw "the interpreter did not run: $smoke" }
    Write-Note "$smoke"
    if ($RelTag -and $OmniVersion -and $OmniVersion -ne 'unknown') {
        if ("$reported" -notmatch [regex]::Escape($OmniVersion)) {
            throw "the release says $OmniVersion but $probePath reports: $reported"
        }
    }
}

function Undo-ReleaseInstall {
    Write-Warn 'rolling the release install back'
    foreach ($path in @($InstalledCommands)) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            Remove-Item -Force -Recurse -LiteralPath $path -ErrorAction SilentlyContinue
            Write-Note "removed $path"
        }
    }
    if (Test-Path -LiteralPath $Manifest) {
        Remove-Item -Force -LiteralPath $Manifest
        Write-Note "removed $Manifest"
    }
}

function Show-PathAdvice {
    $separator = [System.IO.Path]::PathSeparator
    $onPath = ($env:PATH -split [regex]::Escape($separator)) -contains $Bin

    if ($DryRun) {
        Write-Info 'Dry run: nothing was changed'
        return
    }

    Write-Host ''
    Write-Info "OmniScript $OmniVersion is installed ($Channel channel)"
    if ($onPath) {
        Write-Note 'run it with: omni -e "cmd(whoami)"   or just: omni'
    } else {
        Write-Note "$Bin is not on your PATH yet. In PowerShell:"
        Write-Host ''
        Write-Host "        `$env:PATH = `"${Bin}${separator}`$env:PATH`""
        Write-Host ''
        if ($IsWin) {
            Write-Note 'or make it permanent for your account:'
            Write-Host ''
            Write-Host "        [Environment]::SetEnvironmentVariable('PATH', `"$Bin;`$([Environment]::GetEnvironmentVariable('PATH','User'))`", 'User')"
            Write-Host ''
            Write-Note 'then open a new terminal.'
        } else {
            Write-Note "or add this to your shell profile:  export PATH=`"${Bin}:`$PATH`""
        }
    }
    Write-Note "update with: omni update            ($Channel channel)"
    if ($Source) {
        Write-Note "uninstall with: $(Join-Path $Source $(if ($IsWin) { 'uninstall.ps1' } else { 'uninstall.sh' }))"
    } else {
        Write-Note "uninstall with: iwr -use1 https://raw.githubusercontent.com/$Repo/main/uninstall.ps1 | iex"
    }
}

# ------------------------------------------------------- the shared state
$Cloned = $false
$InstalledCommands = New-Object System.Collections.Generic.List[string]
$CommandKind = if ($IsWin) { 'shim' } else { 'symlink' }
$OmniVersion = 'unknown'

# ======================================================================= main
$here = $PSScriptRoot
$besideUs = $false
if ($Source) { $besideUs = $true }
elseif ($here -and (Test-SourceTree $here)) { $besideUs = $true }
elseif ($env:OMNI_HOME -and (Test-SourceTree $env:OMNI_HOME)) { $besideUs = $true }

if (-not $Channel) {
    if ($besideUs) {
        $Channel = 'beta'
        if (-not $DryRun) {
            Write-Note 'installing from the source tree here (beta channel);'
            Write-Note 'pass -Channel release to take the published release instead'
        }
    } else {
        $Channel = 'release'
    }
}

if ($Channel -eq 'release') {
    Install-FromRelease
    switch ($ReleaseResult) {
        0 {
            Write-Info "OmniScript $OmniVersion from $RelTag ($RelAssetName)"
            Write-Note "command into $Bin"
            try {
                Install-App -BinPath $Bin -SrcRoot $Source -VersionStr $OmniVersion
            } catch {
                Write-Warn "app installation failed (non-fatal): $($_.Exception.Message)"
            }
            Write-Manifest
            try {
                Test-Install
            } catch {
                Write-Warn "$($_.Exception.Message)"
                Undo-ReleaseInstall
                Stop-Die "$($_.Exception.Message)"
            }
            Show-PathAdvice
            exit 0
        }
        default {
            if ($RelFatal) { Stop-Die $RelFatal }
            Write-Warn "the release channel did not deliver; installing from $RepoUrl instead"
            $Channel = 'beta'
        }
    }
}

# ------------------------------------------------------- find the source
if (-not $Source -and $here -and (Test-SourceTree $here)) {
    $Source = $here
}
if (-not $Source -and $env:OMNI_HOME -and (Test-SourceTree $env:OMNI_HOME)) {
    $Source = $env:OMNI_HOME
}
if (-not $Source -and (Test-SourceTree (Join-Path $DataDir 'src'))) {
    $Source = Join-Path $DataDir 'src'
}

if (-not $Source -or -not (Test-SourceTree $Source)) {
    $Source = Join-Path $DataDir 'src'
    if (Test-SourceTree $Source) {
        Write-Info "Using the source already in $Source"
    } else {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Stop-Die 'no source tree here and no git to fetch one; run this from a clone, or pass -Source DIR'
        }
        Write-Info "Fetching OmniScript into $Source"
        Invoke-OrShow { New-Item -ItemType Directory -Force -Path $DataDir | Out-Null } "mkdir $DataDir"
        Invoke-OrShow { git clone --quiet --branch main --depth 1 $RepoUrl $Source } "git clone $RepoUrl"
        $Cloned = $true
    }
}
if (-not $DryRun) { $Source = (Resolve-Path $Source).Path }
if (-not (Test-SourceTree $Source)) {
    Stop-Die "$Source is not an OmniScript source tree"
}

# --------------------------------------------------------- build it (no make required)
# This is the fixed builder: direct C compile, no make, no build.ps1
# Tries cl (MSVC), then gcc, clang, cc. Falls back to make if direct fails.

function Find-Compiler {
    # Returns @{Path='...'; Name='cl'|'gcc'|'clang'|'cc'} or $null
    if ($env:CC) {
        $c = Get-Command $env:CC -ErrorAction SilentlyContinue
        if ($c) { return @{ Path=$c.Source; Name=([System.IO.Path]::GetFileNameWithoutExtension($c.Source).ToLowerInvariant()) } }
        if (Test-Path -LiteralPath $env:CC) {
            return @{ Path=$env:CC; Name=([System.IO.Path]::GetFileNameWithoutExtension($env:CC).ToLowerInvariant()) }
        }
    }
    foreach ($name in @('cl','gcc','clang','cc')) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) { return @{ Path=$c.Source; Name=$name } }
        $c = Get-Command "$name.exe" -ErrorAction SilentlyContinue
        if ($c) { return @{ Path=$c.Source; Name=$name } }
    }
    return $null
}

function Build-Direct {
    param([string]$SrcRoot, [string]$VersionStr)

    $srcDir = Join-Path $SrcRoot 'src'
    $base = @('util.c','lex.c','parse.c','eval.c','draw.c','sha256.c','update.c','main.c')
    $gui = 'gui_stub.c'

    # Detect GUI file
    if ($IsWin) {
        $gui = 'gui_win32.c'
    } else {
        # Check for X11 headers like Makefile does
        $x11 = $false
        foreach ($h in @('/usr/include/X11/Xlib.h','/usr/local/include/X11/Xlib.h','/opt/X11/include/X11/Xlib.h','/opt/homebrew/include/X11/Xlib.h')) {
            if (Test-Path -LiteralPath $h) { $x11 = $true; break }
        }
        if ($x11) { $gui = 'gui_x11.c' } else { $gui = 'gui_stub.c' }
    }

    $sources = @()
    foreach ($f in $base) { $sources += (Join-Path $srcDir $f) }
    $sources += (Join-Path $srcDir $gui)

    foreach ($s in $sources) {
        if (-not (Test-Path -LiteralPath $s)) {
            Write-Warn "missing $s"
            return $false
        }
    }

    $comp = Find-Compiler
    if (-not $comp) {
        Write-Warn "no C compiler found (tried cl, gcc, clang, cc)"
        return $false
    }

    $ccPath = $comp.Path
    $ccName = $comp.Name
    Write-Note "using compiler $ccName at $ccPath"
    if ($ccName) { $env:CC = $ccName }

    $verEsc = $VersionStr -replace '"','\"'
    $outName = if ($IsWin) { 'omni.exe' } else { 'omni' }
    $outPath = Join-Path $SrcRoot $outName

    try {
        if ($ccName -eq 'cl') {
            # MSVC: cl /nologo /O2 /W3 /std:c11 /D OMNI_VERSION="x" src\*.c /Fe:omni.exe /link gdi32.lib user32.lib
            $clArgs = @('/nologo','/O2','/W3','/std:c11',"/D", "OMNI_VERSION=`"$verEsc`"", "/Fe$outPath") + $sources + @('/link','gdi32.lib','user32.lib')
            Write-Info "Compiling with cl (no make)"
            & $ccPath @clArgs 2>&1 | ForEach-Object { Write-Host $_ }
            if ($LASTEXITCODE -ne 0) { throw "cl exited $LASTEXITCODE" }
            # Clean cl obj files
            Get-ChildItem -Path $srcDir -Filter "*.obj" -ErrorAction SilentlyContinue | ForEach-Object {
                if ($_.Name -like "omni_*" -or $_.Name -like "*.obj") { Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue }
            }
        } else {
            $cflags = @('-O2','-std=c11','-Wall','-Wextra',"-DOMNI_VERSION=`"$verEsc`"")
            if (-not $IsWin) { $cflags += '-D_POSIX_C_SOURCE=200809L' }
            if ($gui -eq 'gui_x11.c') { $cflags += '-DHAVE_X11' }
            $ld = @()
            if ($IsWin) { $ld += '-lgdi32'; $ld += '-luser32' } elseif ($gui -eq 'gui_x11.c') { $ld += '-lX11' }

            $allArgs = $cflags + @('-o',$outPath) + $sources + $ld
            Write-Info "Compiling with $ccName (no make)"
            & $ccPath @allArgs 2>&1 | ForEach-Object { Write-Host $_ }
            if ($LASTEXITCODE -ne 0) { throw "$ccName exited $LASTEXITCODE" }
        }

        if (-not (Test-Path -LiteralPath $outPath)) {
            Write-Warn "build finished but $outPath not found"
            return $false
        }
        if (-not $IsWin) {
            try { & chmod 755 $outPath } catch { }
        }
        Write-Note "built $outPath"
        return $true
    } catch {
        Write-Warn "direct build failed: $($_.Exception.Message)"
        return $false
    }
}

function Build-WithMake {
    param([string]$SrcRoot)
    $mk = ''
    foreach ($cand in @('make','gmake','mingw32-make')) {
        if (Get-Command $cand -ErrorAction SilentlyContinue) { $mk = $cand; break }
    }
    if (-not $mk) {
        Write-Warn "no make found (tried make, gmake, mingw32-make)"
        return $false
    }
    Write-Info "Building with $mk (fallback)"
    try {
        $log = & $mk -C $SrcRoot 2>&1
        $log | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "$mk exited $LASTEXITCODE" }
        return $true
    } catch {
        Write-Warn "make build failed: $($_.Exception.Message)"
        return $false
    }
}

# ============================================================== app installation
# Install OmniScript as a desktop app: Start Menu shortcuts on Windows,
# .desktop file on Linux, .app bundle on macOS when run under pwsh.
function Install-App {
    param([string]$BinPath, [string]$SrcRoot, [string]$VersionStr)

    Write-Info "Installing OmniScript as an app"

    # Determine binary for icon generation and shortcuts
    $appBin = $BinPath
    if (-not $appBin) { $appBin = $binary }
    if (-not $appBin) { $appBin = Join-Path $SrcRoot $(if ($IsWin) { 'omni.exe' } else { 'omni' }) }

    # --- icon generation ---
    try {
        if (-not $DryRun) {
            New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
            $iconBmp = Join-Path $DataDir 'icon.bmp'
            if (Test-Path -LiteralPath $appBin) {
                # Generate 64x64 icon using omni itself
                & $appBin -e "draw(window(64, 64, `"OmniScript`"), rect(0, 0, 64, 64, `"#0d1117`"), circle(32, 32, 20, `"#1f6feb`"), text(8, 20, `"Om`", white, 14), save(`"$iconBmp`"))" 2>&1 | Out-Null
                if (Test-Path -LiteralPath $iconBmp) {
                    $script:IconFile = $iconBmp
                    Write-Note "generated icon $iconBmp"
                }
            }
        } else {
            Write-Note "[dry-run] would generate icon via $appBin"
        }
    } catch {
        Write-Warn "icon generation failed: $($_.Exception.Message)"
    }

    if ($IsWin) {
        # --- Windows: Start Menu + Desktop shortcuts ---
        try {
            $startMenuRoot = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
            $script:StartMenuDir = Join-Path $startMenuRoot 'OmniScript'
            if ($DryRun) {
                Write-Note "[dry-run] mkdir $StartMenuDir"
                Write-Note "[dry-run] create shortcuts in $StartMenuDir"
            } else {
                New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
                # WScript.Shell for .lnk
                $shell = New-Object -ComObject WScript.Shell

                # Main app shortcut - points to omni.exe (or shim)
                $lnkPath = Join-Path $StartMenuDir 'OmniScript.lnk'
                $shortcut = $shell.CreateShortcut($lnkPath)
                $targetForLnk = $appBin
                # If appBin is a .cmd shim, point to the real exe behind it
                if ($targetForLnk -like '*.cmd') {
                    $shimContent = Get-Content -LiteralPath $targetForLnk -TotalCount 5 -ErrorAction SilentlyContinue | Out-String
                    $m = [regex]::Match($shimContent, '"([^"]+)"')
                    if ($m.Success) { $targetForLnk = $m.Groups[1].Value }
                }
                $shortcut.TargetPath = $targetForLnk
                $shortcut.WorkingDirectory = Split-Path $targetForLnk -Parent
                $shortcut.Description = "OmniScript $VersionStr - native tiny language"
                if ($IconFile) { $shortcut.IconLocation = $IconFile } else { $shortcut.IconLocation = $targetForLnk }
                $shortcut.Save()
                $AppShortcuts.Add($lnkPath)
                Write-Note "created Start Menu shortcut $lnkPath"

                # REPL shortcut (explicit)
                $replLnk = Join-Path $StartMenuDir 'OmniScript REPL.lnk'
                $repl = $shell.CreateShortcut($replLnk)
                $repl.TargetPath = $targetForLnk
                $repl.Arguments = ''
                $repl.WorkingDirectory = $env:USERPROFILE
                $repl.Description = "OmniScript REPL"
                $repl.IconLocation = if ($IconFile) { $IconFile } else { $targetForLnk }
                $repl.Save()
                $AppShortcuts.Add($replLnk)
                Write-Note "created $replLnk"

                # Uninstall shortcut
                $unLnk = Join-Path $StartMenuDir 'Uninstall OmniScript.lnk'
                $un = $shell.CreateShortcut($unLnk)
                $un.TargetPath = 'powershell.exe'
                $un.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($Source)\uninstall.ps1`" -Purge"
                if (-not (Test-Path -LiteralPath (Join-Path $Source 'uninstall.ps1'))) {
                    $un.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"iwr -use1 https://raw.githubusercontent.com/$Repo/main/uninstall.ps1 | iex`""
                }
                $un.WorkingDirectory = $Source
                $un.Description = "Uninstall OmniScript"
                $un.Save()
                $AppShortcuts.Add($unLnk)

                # Desktop shortcut (optional, only if user has Desktop)
                $desktop = [Environment]::GetFolderPath('Desktop')
                if ($desktop -and (Test-Path $desktop)) {
                    $deskLnk = Join-Path $desktop 'OmniScript.lnk'
                    if (-not (Test-Path $deskLnk)) {
                        $d = $shell.CreateShortcut($deskLnk)
                        $d.TargetPath = $targetForLnk
                        $d.WorkingDirectory = $env:USERPROFILE
                        $d.Description = "OmniScript $VersionStr"
                        $d.IconLocation = if ($IconFile) { $IconFile } else { $targetForLnk }
                        $d.Save()
                        $AppShortcuts.Add($deskLnk)
                        Write-Note "created Desktop shortcut $deskLnk"
                        $script:DesktopFile = $deskLnk
                    }
                }
            }
        } catch {
            Write-Warn "Windows app shortcut creation failed: $($_.Exception.Message)"
        }
    } else {
        # --- Linux/macOS when run under pwsh (install.ps1 can run there too) ---
        try {
            $appsDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'applications' } else { Join-Path $env:HOME '.local/share/applications' }
            $iconsDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'icons/hicolor/64x64/apps' } else { Join-Path $env:HOME '.local/share/icons/hicolor/64x64/apps' }
            if ($DryRun) {
                Write-Note "[dry-run] mkdir $appsDir $iconsDir"
                Write-Note "[dry-run] write $appsDir/omniscript.desktop"
            } else {
                New-Item -ItemType Directory -Force -Path $appsDir,$iconsDir | Out-Null
                # Copy icon if we have it
                if ($IconFile -and (Test-Path $IconFile)) {
                    $destPng = Join-Path $iconsDir 'omniscript.png'
                    $destBmp = Join-Path $iconsDir 'omniscript.bmp'
                    try {
                        if (Get-Command convert -ErrorAction SilentlyContinue) {
                            & convert $IconFile $destPng 2>&1 | Out-Null
                            if (Test-Path $destPng) { $script:IconFile = $destPng }
                        } elseif (Get-Command magick -ErrorAction SilentlyContinue) {
                            & magick $IconFile $destPng 2>&1 | Out-Null
                            if (Test-Path $destPng) { $script:IconFile = $destPng }
                        } else {
                            Copy-Item -Force $IconFile $destBmp
                            $script:IconFile = $destBmp
                        }
                    } catch { }
                }
                $iconForDesktop = if ($IconFile) { $IconFile } else { 'omniscript' }
                $script:DesktopFile = Join-Path $appsDir 'omniscript.desktop'
                $desktopContent = @(
                    '[Desktop Entry]',
                    'Name=OmniScript',
                    'GenericName=OmniScript Language',
                    'Comment=Native tiny language for drawing and automating — one binary, libc only',
                    \"Exec=$Bin/omni\",
                    \"Icon=$iconForDesktop\",
                    'Terminal=true',
                    'Type=Application',
                    'Categories=Development;Education;Science;',
                    'Keywords=omni;script;drawing;automation;',
                    'StartupWMClass=OmniScript',
                    'MimeType=text/x-omniscript;',
                    '',
                    '[Desktop Action REPL]',
                    'Name=Open REPL',
                    \"Exec=$Bin/omni\",
                    'Terminal=true',
                    '',
                    '[Desktop Action Examples]',
                    'Name=Run Examples',
                    \"Exec=$Bin/omni $SrcRoot/examples/03_drawing.omni\",
                    'Terminal=true'
                )
                Set-Content -Path $DesktopFile -Value $desktopContent -Encoding UTF8
                Write-Note "created app launcher $DesktopFile"
            }
        } catch {
            Write-Warn "Linux/macOS app launcher creation failed: $($_.Exception.Message)"
        }
    }
}

# --- version ---
$versionFile = Join-Path $Source 'VERSION'
if (Test-Path -LiteralPath $versionFile) {
    $OmniVersion = ((Get-Content -LiteralPath $versionFile -TotalCount 1) -join '').Trim()
}
if (-not $OmniVersion) { $OmniVersion = 'unknown' }
Write-Info "OmniScript $OmniVersion from $Source"

if ($IsWin) { $binaryName = 'omni.exe' } else { $binaryName = 'omni' }
$expectedBinary = Join-Path $Source $binaryName

# --- try direct, then make ---
$built = $false
if (-not $DryRun) {
    $built = Build-Direct -SrcRoot $Source -VersionStr $OmniVersion
    if (-not $built) {
        Write-Note "direct compile failed, trying make"
        $built = Build-WithMake -SrcRoot $Source
    }
} else {
    Write-Note "[dry-run] would build $expectedBinary from $Source"
    $built = $true
}

if (-not $built) {
    Stop-Die "the beta channel builds OmniScript from source and needs a C compiler (cl, gcc, clang, cc). Install one and re-run, or use -Channel release"
}

Write-Note "command into $Bin"

$binary = ''
foreach ($candidate in @($expectedBinary, (Join-Path $Source 'omni'), (Join-Path $Source 'omni.exe'))) {
    if (Test-Path -LiteralPath $candidate) { $binary = $candidate; break }
}
if (-not $binary -and -not $DryRun) { Stop-Die "the build finished but left no binary in $Source" }
if ($DryRun) { $binary = $expectedBinary }
$script:BinaryPath = $binary

Invoke-OrShow { New-Item -ItemType Directory -Force -Path $Bin | Out-Null } "mkdir $Bin"

function Add-Command {
    param([string]$Name, [string]$Target)
    $path = Join-Path $Bin $Name
    if ($IsWin) { $path = "$path.cmd" }
    if (Test-Path $path) {
        $ours = Test-Recorded $path
        if (-not $ours) {
            $item = Get-Item $path -Force -ErrorAction SilentlyContinue
            if ($item -and $item.LinkType -and $item.Target) {
                if ($Source -and "$($item.Target)".StartsWith($Source)) { $ours = $true }
            } else {
                $head = (Get-Content -Path $path -TotalCount 5 -ErrorAction SilentlyContinue) -join "`n"
                if ($Source -and $head -match [regex]::Escape($Source)) { $ours = $true }
            }
        }
        if ($ours) {
            Write-Note "$Name is already installed"
            $InstalledCommands.Add($path)
            return
        }
        if (-not $Force) {
            Stop-Die "$path already exists and was not created by this script.`n       Re-run with -Force to move it aside (a .bak copy is kept next to it)."
        }
        Invoke-OrShow { Move-Item -Force -Path $path -Destination "$path.bak" } "move $path to $path.bak"
        Write-Note "moved the old $Name to $path.bak"
    }
    Invoke-OrShow { New-CommandLink -Path $path -Target $Target } "$Name -> $Target"
    Write-Note "$Name -> $Target"
    $InstalledCommands.Add($path)
}

function Test-NoForeignCommands {
    foreach ($name in $Commands) {
        $path = Join-Path $Bin $name
        if ($IsWin) { $path = "$path.cmd" }
        if ((Test-Path $path) -and -not $Force -and -not (Test-Recorded $path)) {
            $item = Get-Item $path -Force -ErrorAction SilentlyContinue
            if (-not $item -or -not $item.LinkType) {
                Stop-Die "$path already exists and was not created by this script.`n       Re-run with -Force to move it aside (a .bak copy is kept next to it)."
            }
        }
    }
}

function New-CommandLink {
    param([string]$Path, [string]$Target)
    if ($IsWin) {
        New-Shim -Path $Path -Target $Target
    } else {
        if (Test-Path -LiteralPath $Path) { Remove-Item -Force -LiteralPath $Path }
        New-Item -ItemType SymbolicLink -Path $Path -Target $Target | Out-Null
    }
}

Test-NoForeignCommands
$Mode = 'symlink'
foreach ($name in $Commands) { Add-Command -Name $name -Target $binary }

# ------------------------------------------------------- app (Start Menu, Desktop, .desktop)
try {
    Install-App -BinPath $Bin -SrcRoot $Source -VersionStr $OmniVersion
} catch {
    Write-Warn "app installation failed (non-fatal): $($_.Exception.Message)"
}

# ------------------------------------------------------- manifest and checks
Write-Manifest
try {
    Test-Install
} catch {
    if ($Mode -eq 'binary') { Undo-ReleaseInstall }
    Stop-Die "$($_.Exception.Message)"
}
Show-PathAdvice
