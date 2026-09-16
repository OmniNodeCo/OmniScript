# Install OmniScript on Windows (and, if you like, anywhere pwsh runs).
#
#   .\install.ps1                          # from this checkout: shims into %LOCALAPPDATA%\Programs\OmniScript
#   .\install.ps1 -Channel release         # the published release: one file, no Python needed
#   .\install.ps1 -Mode venv               # self-contained venv, shims pointing at it
#   .\install.ps1 -Bin C:\Tools            # put the commands somewhere of your own
#   .\install.ps1 -VsCode                  # also install the editor extension
#
# Two channels, the same two `omni update` follows:
#
#   release   what the project published. A standalone executable for this
#             machine if it built one, otherwise the wheel into a venv or pip.
#             The default when this script arrives with no source tree beside
#             it, and the only channel that needs no Python at all.
#   beta      the repository itself: this checkout, or a clone of a branch, with
#             the commands pointing at it so `git pull` is an upgrade. The
#             default when the script is run from a source tree.
#
# If the release channel cannot deliver -- nothing published yet, no file built
# for this machine, no network -- the script says so and installs from the
# repository instead.
#
# Windows needs a shim rather than a symlink: creating symlinks wants
# administrator rights or Developer Mode, while a two-line .cmd file in a
# directory on PATH works for everybody. Under pwsh on Linux or macOS this
# script makes real symlinks instead, exactly like install.sh does. A release
# executable needs no shim at all -- omni.exe runs itself, and only the second
# command gets one.
#
# Everything created here is written to a manifest so uninstall.ps1 can remove
# it -- and only it.

#Requires -Version 5.1
[CmdletBinding()]
param(
    # 'binary' is not a choice you make: it is what a release install becomes, and
    # a validated parameter has to accept the value the script assigns to it.
    [ValidateSet('symlink', 'venv', 'pip', 'binary')]
    [string]$Mode = 'symlink',
    [ValidateSet('', 'release', 'beta')]
    [string]$Channel = '',
    [string]$Prefix = '',
    [string]$Bin = '',
    [string]$Source = '',
    [string]$Python = '',
    [string]$Ref = 'main',
    [string]$Version = '',
    [string]$Repo = '',
    [string]$ApiUrl = '',
    [switch]$NoVerify,
    [switch]$VsCode,
    [switch]$User,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Repo = if ($Repo) { $Repo } elseif ($env:OMNISCRIPT_REPO) { $env:OMNISCRIPT_REPO } else { 'OmniNodeCo/OmniScript' }
$RepoUrl = if ($env:OMNISCRIPT_REPO_URL) { $env:OMNISCRIPT_REPO_URL } else { "https://github.com/$Repo.git" }
$ApiUrl = if ($ApiUrl) { $ApiUrl } elseif ($env:OMNISCRIPT_API_URL) { $env:OMNISCRIPT_API_URL } else { 'https://api.github.com' }
$MinPython = '3.10'
$Commands = @('omni', 'omniscript')

$IsWin = [System.Environment]::OSVersion.Platform -eq 'Win32NT'

# State the two channels fill in as they go.
$InstallSpec = ''
$ReleaseResult = 1
$RelTag = ''
$RelVersion = ''
$RelAssetName = ''
$RelKind = ''
$RelDownload = ''
$RelFatal = ''
$BinaryPath = ''

function Write-Info { param([string]$Text) Write-Host "==> $Text" }
function Write-Note { param([string]$Text) Write-Host "    $Text" }
function Write-Warn { param([string]$Text) Write-Host "    $Text" }
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

  -Channel release|beta  release: the published release (default with no source
                         tree here); beta: the repository (default in a checkout)
  -Mode symlink|venv|pip   how to install                        [symlink]
  -Prefix DIR              install root                          [see below]
  -Bin DIR                 where the commands go                 [PREFIX, or PREFIX\bin]
  -Source DIR              source tree to install from           [this script's folder]
  -Python PATH             interpreter to use                    [first python >= 3.10 on PATH]
  -Ref REF                 branch or tag to fetch when cloning   [main]
  -Version VERSION         release channel: a particular release [the newest]
  -Repo OWNER/NAME         repository to ask and clone from      [OmniNodeCo/OmniScript]
  -ApiUrl URL              API root to ask for releases          [https://api.github.com]
  -NoVerify                skip the SHA256 check on what is downloaded
  -VsCode                  also install the editor extension
  -User                    pip mode: install for this user only
  -Force                   replace commands this script did not create
  -DryRun                  print what would happen and change nothing
  -Help                    this text

Defaults:
  Windows    -Prefix %LOCALAPPDATA%\Programs\OmniScript   (commands land directly in it)
  elsewhere  -Prefix ~/.local                             (commands land in PREFIX/bin)

Channels:
  release   download what the project published: a standalone executable for
            this machine when there is one, otherwise the wheel. With an
            executable there is nothing to compile and no Python to find.
  beta      install from a source tree -- this checkout, or a clone of -Ref --
            and keep tracking it. `omni update --channel beta` then moves it.

Modes:
  symlink   a .cmd shim (Windows) or a symlink (everywhere else) pointing at the
            launcher in the source tree. Instant, no network. The source tree has
            to stay where it is.
  venv      build a virtual environment under the data directory, install the
            package into it, then point the commands at that. Survives deleting
            the source tree.
  pip       install into the interpreter you already use.

A release install of a standalone executable records itself as mode binary.

State, manifest and venv live in:
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
if (-not $Bin) {
    if ($IsWin) { $Bin = $Prefix } else { $Bin = Join-Path $Prefix 'bin' }
}

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
$VenvDir = Join-Path $DataDir 'venv'

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
        'armv7l' { $arch = 'armv7'; break }
        'x86' { $arch = 'i686'; break }
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

# PowerShell 7.4 and newer answer with bytes when a server does not call its body
# text -- a mirror, a proxy or a plain file server easily manages that. Everything
# downstream of here wants a string.
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

# A command this script already put there is ours to replace: the manifest says so.
function Test-Recorded {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Manifest)) { return $false }
    # The manifest is key=value, so "did we put this here" is a line to match.
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

function New-Shim {
    param([string]$Path, [string]$Target, [string]$Interpreter)
    if ($IsWin) {
        # A .cmd shim: no privileges needed, and it survives the source moving
        # only as far as its own text says.
        $lines = @(
            '@echo off',
            ('"{0}" "{1}" %*' -f $Interpreter, $Target)
        )
        Set-Content -Path $Path -Value $lines -Encoding ASCII
    } else {
        if (Test-Path $Path) { Remove-Item -Force $Path }
        New-Item -ItemType SymbolicLink -Path $Path -Target $Target | Out-Null
    }
}

# ============================================================ release channel
# Fills in $ReleaseResult: 0 installed as a single file, 10 a wheel is waiting in
# $InstallSpec for venv or pip mode, 1 the channel cannot deliver and the
# repository should be used instead. $RelFatal says when 1 must not be a fallback.
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
    if ($Mode -eq 'venv' -or $Mode -eq 'pip') {
        $wanted = @("omniscript_lang-$RelVersion-py3-none-any.whl")
        $kinds = @('wheel')
    } else {
        $wanted = @("omni-$RelVersion-$platform$suffix", "omni-$RelVersion-$platform", "omni-$RelVersion-any.pyz")
        $kinds = @('binary', 'binary', 'pyz')
    }
    $asset = $null
    $kind = ''
    for ($i = 0; $i -lt $wanted.Count; $i++) {
        $found = @($release.assets) | Where-Object { "$($_.name)" -eq $wanted[$i] } | Select-Object -First 1
        if ($found) { $asset = $found; $kind = $kinds[$i]; break }
    }
    if (-not $asset) {
        Write-Warn "nothing in $RelTag is built for $platform"
        return
    }
    $downloadUrl = "$($asset.browser_download_url)"
    if (-not $downloadUrl) { $downloadUrl = "$($asset.url)" }
    $script:RelAssetName = "$($asset.name)"
    $script:RelKind = $kind
    Write-Note "this machine takes $RelAssetName ($kind)"

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
        if ($NoVerify) {
            Write-Note 'not checking the checksum (-NoVerify)'
        } else {
            $sumsAsset = @($release.assets) | Where-Object { "$($_.name)".ToUpperInvariant() -eq 'SHA256SUMS.TXT' } | Select-Object -First 1
            $expected = ''
            if ($sumsAsset) {
                try {
                    foreach ($line in ((Read-Url "$($sumsAsset.browser_download_url)") -split "`n")) {
                        if ($line -match [regex]::Escape($RelAssetName)) {
                            $expected = ($line.Trim() -split '\s+')[0].ToLowerInvariant()
                            break
                        }
                    }
                } catch { Write-Warn 'the checksums could not be downloaded' }
            }
            if (-not $expected) {
                Write-Warn 'the release has no checksum for this file, so it is unchecked'
            } else {
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
        }
    }

    if ($kind -eq 'wheel') {
        $script:InstallSpec = $RelDownload
        $script:OmniVersion = $RelVersion
        $script:ReleaseResult = 10
        return
    }
    if ($kind -eq 'pyz' -and -not $Python) {
        $probe = Get-Command python -ErrorAction SilentlyContinue
        $probe3 = Get-Command python3 -ErrorAction SilentlyContinue
        if (-not $probe -and -not $probe3) {
            Write-Warn "$RelAssetName needs a Python to run, and there is none on PATH"
            return
        }
    }

    if ($IsWin) { $name = if ($kind -eq 'pyz') { 'omni.pyz' } else { 'omni.exe' } } else { $name = 'omni' }
    $target = Join-Path $Bin $name
    $second = Join-Path $Bin 'omniscript.cmd'

    foreach ($path in @($target, $second)) {
        if ((Test-Path -LiteralPath $path) -and -not $Force -and -not (Test-Recorded $path)) {
            Stop-Die "$path already exists and was not created by this script.
       Re-run with -Force to move it aside (a .bak copy is kept next to it)."
        }
    }
    Invoke-OrShow { New-Item -ItemType Directory -Force -Path $Bin | Out-Null } "mkdir $Bin"

    if ($DryRun) {
        Write-Note "[dry-run] install $RelAssetName as $target"
        Write-Note "[dry-run] $second runs $name"
        $script:BinaryPath = $target
        $script:Mode = 'binary'
        $script:CommandKind = 'binary'
        $script:OmniVersion = $RelVersion
        $InstalledCommands.Add($target)
        $InstalledCommands.Add($second)
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

    if ($IsWin) {
        if ($kind -eq 'pyz') {
            $runner = if ($Python) { $Python } else { (Get-Command python).Source }
            New-Shim -Path (Join-Path $Bin 'omni.cmd') -Target $target -Interpreter $runner
            New-Shim -Path $second -Target $target -Interpreter $runner
            $InstalledCommands.Add((Join-Path $Bin 'omni.cmd'))
            $InstalledCommands.Add($second)
            Write-Note "omni.cmd and omniscript.cmd run $name"
        } else {
            # omni.exe answers to `omni` on its own; only the second name needs a shim.
            $lines = @('@echo off', ('"%~dp0{0}" %*' -f $name))
            Set-Content -Path $second -Value $lines -Encoding ASCII
            $InstalledCommands.Add($second)
            Write-Note "omniscript.cmd runs $name"
        }
    } else {
        if (Test-Path (Join-Path $Bin 'omniscript')) { Remove-Item -Force (Join-Path $Bin 'omniscript') }
        New-Item -ItemType SymbolicLink -Path (Join-Path $Bin 'omniscript') -Target $target | Out-Null
        $InstalledCommands.Add((Join-Path $Bin 'omniscript'))
        Write-Note 'omniscript -> omni'
    }
    $script:ReleaseResult = 0
}

# ------------------------------------------------------- the shared tail
# One key=value per line, and one repeated line per command or extension: the
# same file install.sh writes, so a shell can read it with sed and this can read
# it with -split. WriteAllLines because Set-Content -Encoding UTF8 leaves a BOM
# on PowerShell 5.1, and a BOM becomes part of the first key.
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
        "pip_scripts_dir=$PipTarget",
        "pip_user=$(if ($User) { 1 } else { 0 })",
        "python=$Python",
        "python_version=$PyVersion",
        "ref=$Ref",
        "release_tag=$RelTag",
        "repo=$Repo",
        "repo_url=$RepoUrl",
        "source=$Source",
        "venv=$InstalledVenv",
        "version=$OmniVersion"
    )
    foreach ($path in $InstalledCommands) { if ($path) { $lines += "command=$path" } }
    foreach ($dir in $ExtensionDirs) { if ($dir) { $lines += "extension=$dir" } }
    [System.IO.File]::WriteAllLines($Manifest, [string[]]$lines)
    if (-not (Test-Path -LiteralPath $Manifest)) { Stop-Die "the manifest did not get written to $Manifest" }
    Write-Note "wrote $Manifest"
}

function Test-Install {
    if ($DryRun) { return }
    Write-Info 'Checking the install'
    if ($IsWin) { $probePath = Join-Path $Bin $(if ($Mode -eq 'binary' -and $RelKind -ne 'pyz') { 'omni.exe' } else { 'omni.cmd' }) }
    else { $probePath = Join-Path $Bin 'omni' }
    if (-not (Test-Path -LiteralPath $probePath)) {
        if ($InstalledCommands.Count -gt 0) { $probePath = $InstalledCommands[0] } else { Stop-Die "$probePath is missing after the install" }
    }
    $reported = (& $probePath --version) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$probePath --version failed: $reported" }
    Write-Note "$reported"
    $smoke = & $probePath -e 'print(6 * 7, [1, 2, 3].map((x) -> x * x).len(), 2 ** 10)'
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
        Write-Note 'run it with: omni -e "print(''hello'')"   or just: omni'
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
$InstalledVenv = ''
$PipTarget = ''
$CommandKind = if ($IsWin) { 'shim' } else { 'symlink' }
$ExtensionDirs = New-Object System.Collections.Generic.List[string]
$OmniVersion = 'unknown'
$PyVersion = ''

# ======================================================================= main
# Which channel? An explicit one wins. Otherwise a source tree beside the script
# means "install what is here", and no source tree means "get me the release".
$here = $PSScriptRoot
$besideUs = $false
if ($Source) { $besideUs = $true }
elseif ($here -and (Test-Path (Join-Path $here 'omniscript/cli.py'))) { $besideUs = $true }
elseif ($env:OMNI_HOME -and (Test-Path (Join-Path $env:OMNI_HOME 'omniscript/cli.py'))) { $besideUs = $true }

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
            Write-Note "commands into $Bin, no Python needed"
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
        10 { Write-Info "OmniScript $OmniVersion from $RelTag ($RelAssetName)" }
        default {
            if ($RelFatal) { Stop-Die $RelFatal }
            Write-Warn "the release channel did not deliver; installing from $RepoUrl instead"
            $Channel = 'beta'
        }
    }
}

# ------------------------------------------------------- find the source
if (-not $InstallSpec) {
    if (-not $Source -and $here -and (Test-Path (Join-Path $here 'omniscript/cli.py'))) {
        $Source = $here
    }
    if (-not $Source -and $env:OMNI_HOME -and (Test-Path (Join-Path $env:OMNI_HOME 'omniscript/cli.py'))) {
        $Source = $env:OMNI_HOME
    }
    if (-not $Source -and (Test-Path (Join-Path $DataDir 'src/omniscript/cli.py'))) {
        $Source = Join-Path $DataDir 'src'
    }

    if (-not $Source -or -not (Test-Path (Join-Path $Source 'omniscript/cli.py'))) {
        if ($Source) { Stop-Die "-Source $Source is not an OmniScript source tree (no omniscript/cli.py)" }
        $Source = Join-Path $DataDir 'src'
        if (Test-Path (Join-Path $Source 'omniscript/cli.py')) {
            Write-Info "Using the source already in $Source"
            if ($Ref -ne 'main') {
                Invoke-OrShow { git -C $Source fetch --quiet origin $Ref } "git fetch $Ref"
                Invoke-OrShow { git -C $Source checkout --quiet $Ref } "git checkout $Ref"
            }
        } else {
            if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
                Stop-Die 'no source tree here and no git to fetch one; run this from a clone, or pass -Source DIR'
            }
            Write-Info "Fetching OmniScript ($Ref) into $Source"
            Invoke-OrShow { New-Item -ItemType Directory -Force -Path $DataDir | Out-Null } "mkdir $DataDir"
            Invoke-OrShow { git clone --quiet --branch $Ref --depth 1 $RepoUrl $Source } "git clone $RepoUrl"
            $Cloned = $true
        }
    }
    $Source = (Resolve-Path $Source).Path
    if (-not (Test-Path (Join-Path $Source 'omniscript/cli.py'))) {
        Stop-Die "$Source is not an OmniScript source tree"
    }
}

# --------------------------------------------------------- find python
if (-not $Python) {
    foreach ($candidate in @('python3', 'python', 'py')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { $Python = $found.Source; break }
    }
}
if (-not $Python) { Stop-Die "no python on PATH; install Python $MinPython or newer, or pass -Python PATH" }
if (-not (Test-Path $Python)) { Stop-Die "$Python does not exist" }

& $Python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    $found = & $Python -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'
    Stop-Die "$Python is Python $found; OmniScript needs $MinPython or newer (try -Python PATH)"
}
$PyVersion = (& $Python -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])').Trim()
if ($InstallSpec) {
    Write-Note "python $PyVersion ($Python), commands into $Bin, mode $Mode"
} else {
    $OmniVersion = (& $Python -c "import sys; sys.path.insert(0, r'$Source'); import omniscript; print(omniscript.__version__)").Trim()
    Write-Info "OmniScript $OmniVersion from $Source"
    Write-Note "python $PyVersion ($Python), commands into $Bin, mode $Mode"
}

Invoke-OrShow { New-Item -ItemType Directory -Force -Path $Bin | Out-Null } "mkdir $Bin"

function Add-Command {
    param([string]$Name, [string]$Target, [string]$Interpreter)
    $path = Join-Path $Bin $Name
    if ($IsWin) { $path = "$path.cmd" }
    if (Test-Path $path) {
        $ours = Test-Recorded $path
        if (-not $ours) {
            $item = Get-Item $path -Force
            if ($item.LinkType -and $item.Target) {
                foreach ($root in @($Source, $InstalledVenv, $PipTarget)) {
                    if ($root -and "$($item.Target)".StartsWith($root)) { $ours = $true }
                }
            } else {
                $head = (Get-Content -Path $path -TotalCount 5 -ErrorAction SilentlyContinue) -join "`n"
                if ($Source -and $head -match [regex]::Escape($Source)) { $ours = $true }
                if ($InstalledVenv -and $head -match [regex]::Escape($InstalledVenv)) { $ours = $true }
            }
        }
        if ($ours) {
            Write-Note "$Name is already installed"
            $InstalledCommands.Add($path)
            return
        }
        if (-not $Force) {
            Stop-Die "$path already exists and was not created by this script.
       Re-run with -Force to move it aside (a .bak copy is kept next to it)."
        }
        Invoke-OrShow { Move-Item -Force -Path $path -Destination "$path.bak" } "move $path to $path.bak"
        Write-Note "moved the old $Name to $path.bak"
    }
    Invoke-OrShow { New-Shim -Path $path -Target $Target -Interpreter $Interpreter } "$Name -> $Target"
    Write-Note "$Name -> $Target"
    $InstalledCommands.Add($path)
}

function Test-NoForeignCommands {
    foreach ($name in $Commands) {
        $path = Join-Path $Bin $name
        if ($IsWin) { $path = "$path.cmd" }
        if ((Test-Path $path) -and -not $Force -and -not (Test-Recorded $path)) {
            $item = Get-Item $path -Force
            if (-not $item.LinkType) {
                Stop-Die "$path already exists and was not created by this script.
       Re-run with -Force to move it aside, or point -Bin somewhere else."
            }
        }
    }
}

switch ($Mode) {
    default { Stop-Die "-Mode must be symlink, venv, pip or binary, not '$Mode'" }
    'symlink' {
        Test-NoForeignCommands
        $launcher = Join-Path $Source 'omni'
        foreach ($name in $Commands) { Add-Command -Name $name -Target $launcher -Interpreter $Python }
    }
    'venv' {
        Test-NoForeignCommands
        Write-Info "Creating a virtual environment in $VenvDir"
        if ((Test-Path $VenvDir) -and $Force) {
            Invoke-OrShow { Remove-Item -Recurse -Force $VenvDir } "remove $VenvDir"
        }
        Invoke-OrShow { New-Item -ItemType Directory -Force -Path $DataDir | Out-Null } "mkdir $DataDir"
        $venvPython = Join-Path $VenvDir $(if ($IsWin) { 'Scripts\python.exe' } else { 'bin/python' })
        if (-not (Test-Path $venvPython)) {
            Invoke-OrShow { & $Python -m venv $VenvDir } "python -m venv $VenvDir"
        }
        $spec = if ($InstallSpec) { $InstallSpec } else { $Source }
        Write-Info "Installing $spec into it"
        Invoke-OrShow { & $venvPython -m pip install --quiet --upgrade pip } 'pip install --upgrade pip'
        Invoke-OrShow { & $venvPython -m pip install --quiet $spec } "pip install $spec"
        if (-not $DryRun -and $LASTEXITCODE -ne 0) { Stop-Die 'pip could not install the package into the venv' }
        $InstalledVenv = $VenvDir
        foreach ($name in $Commands) {
            if ($IsWin) { $built = Join-Path $VenvDir "Scripts\$name.exe" } else { $built = Join-Path $VenvDir "bin/$name" }
            if (-not $DryRun -and -not (Test-Path $built)) {
                Stop-Die "the venv has no $name command; the install did not take"
            }
            Add-Command -Name $name -Target $built -Interpreter $venvPython
        }
    }
    'pip' {
        $spec = if ($InstallSpec) { $InstallSpec } else { $Source }
        Write-Info "Installing $spec into $Python with pip"
        $pipArgs = @('-m', 'pip', 'install')
        if ($User) { $pipArgs += '--user' }
        $pipArgs += $spec
        Invoke-OrShow { & $Python @pipArgs } "python -m pip install $spec"
        if (-not $DryRun -and $LASTEXITCODE -ne 0) { Stop-Die 'pip install failed' }
        $probe = 'import os, sys, sysconfig; ' +
                 'scheme = "%s_user" % os.name if sys.argv[1] == "1" else None; ' +
                 'print(sysconfig.get_path("scripts", scheme))'
        $userFlag = if ($User) { '1' } else { '0' }
        $PipTarget = (& $Python -c $probe $userFlag).Trim()
        foreach ($name in $Commands) {
            if ($IsWin) { $built = Join-Path $PipTarget "$name.exe" } else { $built = Join-Path $PipTarget $name }
            if (Test-Path $built) {
                if ($PipTarget -ne $Bin) { Add-Command -Name $name -Target $built -Interpreter $Python } else {
                    Write-Note "$name is already in $Bin"
                    $InstalledCommands.Add($built)
                }
            } else { Write-Note "pip did not create $built" }
        }
    }
}
if ($InstallSpec -and (Test-Path -LiteralPath $InstallSpec)) {
    Remove-Item -Force -LiteralPath $InstallSpec -ErrorAction SilentlyContinue
}

# -------------------------------------------------- editor extension
if ($VsCode) {
    if (-not $Source) { Stop-Die '-VsCode needs a source tree with extras/vscode in it' }
    $pkg = Get-Content -Raw (Join-Path $Source 'extras/vscode/package.json') | ConvertFrom-Json
    $extName = '{0}.{1}-{2}' -f $pkg.publisher, $pkg.name, $pkg.version
    $roots = @()
    if ($IsWin) {
        $roots += (Join-Path $env:USERPROFILE '.vscode\extensions')
        $roots += (Join-Path $env:USERPROFILE '.cursor\extensions')
    } else {
        $roots += (Join-Path $env:HOME '.vscode/extensions')
        $roots += (Join-Path $env:HOME '.cursor/extensions')
        $roots += (Join-Path $env:HOME '.vscode-server/extensions')
    }
    foreach ($root in $roots) {
        $editorRoot = Split-Path $root -Parent
        if ((Test-Path $editorRoot) -or $root -match '\.vscode') {
            $extDir = Join-Path $root $extName
            Write-Info "Installing the editor extension into $extDir"
            Invoke-OrShow { New-Item -ItemType Directory -Force -Path $extDir | Out-Null } "mkdir $extDir"
            Invoke-OrShow {
                Copy-Item -Recurse -Force -Path (Join-Path $Source 'extras/vscode/*') -Destination $extDir
            } "copy extras/vscode to $extDir"
            $ExtensionDirs.Add($extDir)
        }
    }
    Write-Note 'restart the editor to pick up OmniScript syntax highlighting'
}

# ------------------------------------------------------- manifest and checks
Write-Manifest
try {
    Test-Install
} catch {
    if ($ReleaseResult -eq 10) { Undo-ReleaseInstall }
    Stop-Die "$($_.Exception.Message)"
}
Show-PathAdvice
