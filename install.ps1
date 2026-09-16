# Install OmniScript on Windows (and, if you like, anywhere pwsh runs).
#
#   .\install.ps1                          # shims into %LOCALAPPDATA%\Programs\OmniScript
#   .\install.ps1 -Mode venv               # self-contained venv, shims pointing at it
#   .\install.ps1 -Bin C:\Tools            # put the commands somewhere of your own
#   .\install.ps1 -VsCode                  # also install the editor extension
#
# Windows needs a shim rather than a symlink: creating symlinks wants
# administrator rights or Developer Mode, while a two-line .cmd file in a
# directory on PATH works for everybody. Under pwsh on Linux or macOS this
# script makes real symlinks instead, exactly like install.sh does.
#
# Everything created here is written to a manifest so uninstall.ps1 can remove
# it -- and only it.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('symlink', 'venv', 'pip')]
    [string]$Mode = 'symlink',
    [string]$Prefix = '',
    [string]$Bin = '',
    [string]$Source = '',
    [string]$Python = '',
    [string]$Ref = 'main',
    [switch]$VsCode,
    [switch]$User,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/OmniNodeCo/OmniScript.git'
$MinPython = '3.10'
$Commands = @('omni', 'omniscript')

$IsWin = [System.Environment]::OSVersion.Platform -eq 'Win32NT'

function Write-Info { param([string]$Text) Write-Host "==> $Text" }
function Write-Note { param([string]$Text) Write-Host "    $Text" }
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

  -Mode symlink|venv|pip   how to install                        [symlink]
  -Prefix DIR              install root                          [see below]
  -Bin DIR                 where the commands go                 [PREFIX, or PREFIX\bin]
  -Source DIR              source tree to install from           [this script's folder]
  -Python PATH             interpreter to use                    [first python >= 3.10 on PATH]
  -Ref REF                 branch or tag to fetch when cloning   [main]
  -VsCode                  also install the editor extension
  -User                    pip mode: install for this user only
  -Force                   replace commands this script did not create
  -DryRun                  print what would happen and change nothing
  -Help                    this text

Defaults:
  Windows    -Prefix %LOCALAPPDATA%\Programs\OmniScript   (commands land directly in it)
  elsewhere  -Prefix ~/.local                             (commands land in PREFIX/bin)

Modes:
  symlink   a .cmd shim (Windows) or a symlink (everywhere else) pointing at the
            launcher in the source tree. Instant, no network. The source tree has
            to stay where it is.
  venv      build a virtual environment under the data directory, install the
            package into it, then point the commands at that. Survives deleting
            the source tree.
  pip       install into the interpreter you already use.

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
$Manifest = Join-Path $DataDir 'install.json'
$VenvDir = Join-Path $DataDir 'venv'

# ------------------------------------------------------- find the source
if (-not $Source -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'omniscript/cli.py'))) {
    $Source = $PSScriptRoot
}
if (-not $Source -and $env:OMNI_HOME -and (Test-Path (Join-Path $env:OMNI_HOME 'omniscript/cli.py'))) {
    $Source = $env:OMNI_HOME
}

$Cloned = $false
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
$OmniVersion = (& $Python -c "import sys; sys.path.insert(0, r'$Source'); import omniscript; print(omniscript.__version__)").Trim()

Write-Info "OmniScript $OmniVersion from $Source"
Write-Note "python $PyVersion ($Python), commands into $Bin, mode $Mode"

Invoke-OrShow { New-Item -ItemType Directory -Force -Path $Bin | Out-Null } "mkdir $Bin"

$InstalledCommands = New-Object System.Collections.Generic.List[string]
$InstalledVenv = ''
$PipTarget = ''
$CommandKind = if ($IsWin) { 'shim' } else { 'symlink' }

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

function Add-Command {
    param([string]$Name, [string]$Target, [string]$Interpreter)
    $path = Join-Path $Bin $Name
    if ($IsWin) { $path = "$path.cmd" }
    if (Test-Path $path) {
        $ours = $false
        $item = Get-Item $path -Force
        if ($item.LinkType -and $item.Target) {
            foreach ($root in @($Source, $InstalledVenv, $PipTarget)) {
                if ($root -and "$($item.Target)".StartsWith($root)) { $ours = $true }
            }
        } else {
            $head = (Get-Content -Path $path -TotalCount 5 -ErrorAction SilentlyContinue) -join "`n"
            if ($head -match [regex]::Escape($Source) -or ($InstalledVenv -and $head -match [regex]::Escape($InstalledVenv))) {
                $ours = $true
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
        if ((Test-Path $path) -and -not $Force) {
            $item = Get-Item $path -Force
            if (-not $item.LinkType) {
                Stop-Die "$path already exists and was not created by this script.
       Re-run with -Force to move it aside, or point -Bin somewhere else."
            }
        }
    }
}

switch ($Mode) {
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
        Write-Info 'Installing the package into it'
        Invoke-OrShow { & $venvPython -m pip install --quiet --upgrade pip } 'pip install --upgrade pip'
        Invoke-OrShow { & $venvPython -m pip install --quiet $Source } "pip install $Source"
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
        Write-Info "Installing into $Python with pip"
        $pipArgs = @('-m', 'pip', 'install')
        if ($User) { $pipArgs += '--user' }
        $pipArgs += $Source
        Invoke-OrShow { & $Python @pipArgs } "python -m pip install $Source"
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

# -------------------------------------------------- editor extension
$ExtensionDirs = New-Object System.Collections.Generic.List[string]
if ($VsCode) {
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

# ------------------------------------------------------- manifest
if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $history = Join-Path $(if ($IsWin) { $env:USERPROFILE } else { $env:HOME }) '.omniscript_history'
    $manifest = [ordered]@{
        package                 = 'omniscript-lang'
        version                 = $OmniVersion
        installed_at            = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        mode                    = $Mode
        command_kind            = $CommandKind
        source                  = $Source
        cloned_by_installer     = $Cloned
        bin_dir                 = $Bin
        commands                = @($InstalledCommands)
        python                  = $Python
        python_version          = $PyVersion
        venv                    = $(if ($InstalledVenv) { $InstalledVenv } else { $null })
        pip_scripts_dir         = $(if ($PipTarget) { $PipTarget } else { $null })
        pip_user                = [bool]$User
        editor_extensions       = @($ExtensionDirs)
        history_file            = $history
        data_dir                = $DataDir
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $Manifest -Encoding UTF8
    Write-Note "wrote $Manifest"

    Write-Info 'Checking the install'
    $omniCommand = Join-Path $Bin $(if ($IsWin) { 'omni.cmd' } else { 'omni' })
    if (-not (Test-Path $omniCommand)) { Stop-Die "$omniCommand is missing after the install" }
    $reported = (& $omniCommand --version) 2>&1
    if ($LASTEXITCODE -ne 0) { Stop-Die "$omniCommand --version failed: $reported" }
    Write-Note "$reported"
    $smoke = & $omniCommand -e 'print(6 * 7, [1, 2, 3].map((x) -> x * x).len(), 2 ** 10)'
    if ($LASTEXITCODE -ne 0) { Stop-Die "the interpreter did not run: $smoke" }
    Write-Note "$smoke"
}

# ------------------------------------------------------- PATH advice
$separator = [System.IO.Path]::PathSeparator
$onPath = ($env:PATH -split [regex]::Escape($separator)) -contains $Bin

if ($DryRun) {
    Write-Info 'Dry run: nothing was changed'
    exit 0
}

Write-Host ''
Write-Info "OmniScript $OmniVersion is installed"
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
Write-Note "uninstall with: $(Join-Path $Source $(if ($IsWin) { 'uninstall.ps1' } else { 'uninstall.sh' }))"
