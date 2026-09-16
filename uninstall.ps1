# Uninstall OmniScript on Windows (and anywhere else pwsh runs).
#
#   .\uninstall.ps1                 # commands, venv and editor extension
#   .\uninstall.ps1 -DryRun         # show what would go
#   .\uninstall.ps1 -Purge          # ...plus the REPL history, a cloned source
#                                   #    tree, and the manifest itself
#
# This works from the manifest install.ps1 wrote, so it removes exactly what was
# installed -- a shim into a source tree, a venv, a pip install, or a standalone
# executable downloaded from a release. It never deletes a source tree you cloned
# yourself, and it will not remove a command it cannot prove it created: use
# -Force for that, and read what it says first.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Prefix = '',
    [string]$Bin = '',
    [switch]$Purge,
    [switch]$KeepVsCode,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$IsWin = [System.Environment]::OSVersion.Platform -eq 'Win32NT'

function Write-Info { param([string]$Text) Write-Host "==> $Text" }
function Write-Note { param([string]$Text) Write-Host "    $Text" }
function Write-Warn { param([string]$Path, [string]$Why) Write-Host "    leaving $Path alone: $Why" }
function Stop-Die {
    param([string]$Text)
    Write-Host "uninstall.ps1: error: $Text" -ForegroundColor Red
    exit 1
}
function Invoke-OrShow {
    param([scriptblock]$Block, [string]$Description)
    if ($DryRun) { Write-Note "[dry-run] $Description" } else { & $Block }
}

if ($Help) {
    @'
Usage: uninstall.ps1 [options]

  -Prefix DIR      install root that was used     [see install.ps1]
  -Bin DIR         where the commands are         [PREFIX, or PREFIX/bin]
  -Purge           also remove the REPL history, a source tree the installer
                   cloned, and the manifest
  -KeepVsCode      leave the editor extension in place
  -Force           remove commands even when they do not look like ours
  -DryRun          print what would be removed and remove nothing
  -Help            this text
'@ | Write-Host
    exit 0
}

if (-not $Prefix) {
    if ($IsWin) {
        $local = $env:LOCALAPPDATA
        if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\Local' }
        $Prefix = Join-Path $local 'Programs\OmniScript'
        $DataDir = Join-Path $local 'OmniScript'
    } else {
        $Prefix = Join-Path $env:HOME '.local'
        $DataDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'omniscript' } else { Join-Path $env:HOME '.local/share/omniscript' }
    }
} else {
    if ($IsWin) {
        $local = $env:LOCALAPPDATA
        if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\Local' }
        $DataDir = Join-Path $local 'OmniScript'
    } else {
        $DataDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'omniscript' } else { Join-Path $env:HOME '.local/share/omniscript' }
    }
}
if (-not $Bin) {
    if ($IsWin) { $Bin = $Prefix } else { $Bin = Join-Path $Prefix 'bin' }
}
$Manifest = Join-Path $DataDir 'install.json'

$M = $null
if (Test-Path $Manifest) {
    Write-Info "Reading $Manifest"
    $M = Get-Content -Raw $Manifest | ConvertFrom-Json
    if ($M.version) {
        Write-Info "OmniScript $($M.version), installed in $($M.mode) mode"
        if ($M.channel) {
            $tracking = if ($M.ref) { ", tracking $($M.ref)" } else { '' }
            Write-Note "$($M.channel) channel$tracking"
        }
    }
} else {
    Write-Note "no manifest at $Manifest; falling back to $Bin"
}

$MSource = if ($M) { $M.source } else { '' }
$MVenv = if ($M -and $M.venv) { $M.venv } else { '' }
$MPipDir = if ($M -and $M.pip_scripts_dir) { $M.pip_scripts_dir } else { '' }
$MMode = if ($M) { $M.mode } else { '' }
$MPython = if ($M -and $M.python) { $M.python } else { '' }
$MCloned = [bool]($M -and $M.cloned_by_installer)
$MBinary = if ($M -and $M.binary) { "$($M.binary)" } else { '' }
$MChannel = if ($M -and $M.channel) { "$($M.channel)" } else { '' }
$MHistory = if ($M -and $M.history_file) { $M.history_file } else { Join-Path $(if ($IsWin) { $env:USERPROFILE } else { $env:HOME }) '.omniscript_history' }

if ($M -and $M.commands) { $MCommands = @($M.commands) } else {
    $MCommands = @()
    foreach ($name in @('omni', 'omniscript')) {
        $MCommands += $(if ($IsWin) { Join-Path $Bin "$name.cmd" } else { Join-Path $Bin $name })
    }
}
if ($M -and $M.editor_extensions) { $MExtensions = @($M.editor_extensions) } else { $MExtensions = @() }

$Removed = 0
$Kept = 0

function Test-Ours {
    param([string]$Path)
    # The manifest is our own record: anything it lists, install.ps1 put there.
    # For a downloaded executable that is the only evidence there could ever be.
    foreach ($recorded in $MCommands) { if ($recorded -and "$recorded" -eq $Path) { return $true } }
    if ($MBinary -and $MBinary -eq $Path) { return $true }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return $false }
    if ($item.LinkType -and $item.Target) {
        $target = "$($item.Target)"
        foreach ($root in @($MSource, $MVenv, $MPipDir)) {
            if ($root -and $target.StartsWith($root)) { return $true }
        }
        if (-not $MSource) {
            # No manifest roots to compare with: trust a link into an OmniScript tree.
            if (Test-Path (Join-Path (Split-Path $target -Parent) 'omniscript/cli.py')) { return $true }
        }
        return $false
    }
    if ($MPipDir -and $Bin -eq $MPipDir) { return $true }
    $head = (Get-Content -LiteralPath $Path -TotalCount 8 -ErrorAction SilentlyContinue) -join "`n"
    foreach ($root in @($MSource, $MVenv, $MPipDir)) {
        if ($root -and $head -match [regex]::Escape($root)) { return $true }
    }
    # A pip-generated console script imports the entry point by name.
    if ($head -match 'from omniscript\.cli import main' -or $head -match 'omniscript\.cli:main') {
        return $true
    }
    # No manifest to compare with: a shim we wrote quotes the launcher it runs,
    # so see whether any path in it lives beside an OmniScript source tree.
    foreach ($match in [regex]::Matches($head, '"([^"]+)"')) {
        $dir = Split-Path $match.Groups[1].Value -Parent
        if ($dir -and (Test-Path (Join-Path $dir 'omniscript/cli.py'))) { return $true }
    }
    return $false
}

function Remove-Item-IfOurs {
    param([string]$Path, [string]$What = 'command')
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if (-not (Test-Ours -Path $Path) -and -not $Force) {
        Write-Warn $Path 'it does not look like something install.ps1 created (use -Force)'
        $script:Kept += 1
        return
    }
    Invoke-OrShow { Remove-Item -LiteralPath $Path -Recurse -Force } "remove $What $Path"
    Write-Note "removed $What $Path"
    $script:Removed += 1
}

# --------------------------------------------------------- commands
Write-Info 'Removing the commands'
foreach ($path in $MCommands) {
    Remove-Item-IfOurs -Path $path -What 'command'
}
foreach ($name in @('omni', 'omniscript')) {
    $bak = Join-Path $Bin $(if ($IsWin) { "$name.cmd.bak" } else { "$name.bak" })
    if (Test-Path $bak) { Write-Note "a backup of your previous $name is still at $bak" }
}

# ---------------------------------------------------- a downloaded executable
# Normally the commands list covered it already; this catches a binary that was
# moved, or a manifest an older installer wrote.
if ($MBinary -and (Test-Path -LiteralPath $MBinary)) {
    $listed = $false
    foreach ($recorded in $MCommands) { if ("$recorded" -eq $MBinary) { $listed = $true } }
    if (-not $listed) {
        Write-Info 'Removing the downloaded executable'
        Remove-Item-IfOurs -Path $MBinary -What 'executable'
    }
}

# ------------------------------------------------------------- venv
if ($MVenv -and (Test-Path $MVenv)) {
    if ($MVenv.StartsWith($DataDir)) {
        Write-Info 'Removing the virtual environment'
        Invoke-OrShow { Remove-Item -LiteralPath $MVenv -Recurse -Force } "remove $MVenv"
        Write-Note "removed $MVenv"
        $Removed += 1
    } else {
        Write-Warn $MVenv "it is outside $DataDir, which is not where install.ps1 builds one"
        $Kept += 1
    }
}

# -------------------------------------------------------------- pip
if ($MMode -eq 'pip') {
    if (-not $MPython) {
        $found = Get-Command python -ErrorAction SilentlyContinue
        if ($found) { $MPython = $found.Source }
    }
    if ($MPython) {
        Write-Info 'Asking pip to remove the package'
        if ($DryRun) {
            Write-Note "[dry-run] $MPython -m pip uninstall -y omniscript-lang"
        } else {
            $out = (& $MPython -m pip uninstall -y omniscript-lang 2>&1) -join "`n"
            if ($LASTEXITCODE -eq 0) { Write-Note 'pip uninstalled omniscript-lang' } elseif ($out -match 'externally-managed-environment') {
                $out = (& $MPython -m pip uninstall -y --break-system-packages omniscript-lang 2>&1) -join "`n"
                if ($LASTEXITCODE -eq 0) { Write-Note 'pip uninstalled omniscript-lang' } else { Write-Note 'pip refused to remove the package:'; Write-Note $out }
            } else {
                Write-Note 'pip had nothing to remove, or said:'
                Write-Note $out
            }
        }
    }
}

# ------------------------------------------------- editor extensions
if ($KeepVsCode) {
    Write-Note 'keeping the editor extension (-KeepVsCode)'
} else {
    foreach ($ext in $MExtensions) {
        if (-not $ext) { continue }
        $leaf = Split-Path $ext -Leaf
        $pkgPath = Join-Path $ext 'package.json'
        if ($leaf -match 'omniscript' -and (Test-Path $pkgPath)) {
            $pkg = Get-Content -Raw $pkgPath | ConvertFrom-Json
            if ($pkg.name -eq 'omniscript') {
                Write-Info "Removing the editor extension $ext"
                Invoke-OrShow { Remove-Item -LiteralPath $ext -Recurse -Force } "remove $ext"
                Write-Note "removed $ext"
                $Removed += 1
                continue
            }
        }
        Write-Warn $ext 'it is not an OmniScript extension directory'
        $Kept += 1
    }
}

# ----------------------------------------------------------- purge
if ($Purge) {
    Write-Info 'Purging what is left'
    if (Test-Path $MHistory) {
        Invoke-OrShow { Remove-Item -LiteralPath $MHistory -Force } "remove $MHistory"
        Write-Note "removed the REPL history $MHistory"
        $Removed += 1
    }
    if ($MCloned -and $MSource -and (Test-Path $MSource)) {
        if ($MSource.StartsWith($DataDir)) {
            Invoke-OrShow { Remove-Item -LiteralPath $MSource -Recurse -Force } "remove $MSource"
            Write-Note "removed the source the installer cloned: $MSource"
            $Removed += 1
        } else {
            Write-Warn $MSource 'the installer did not clone it, so it stays'
            $Kept += 1
        }
    }
    if (Test-Path $DataDir) {
        Invoke-OrShow { Remove-Item -LiteralPath $DataDir -Recurse -Force } "remove $DataDir"
        Write-Note "removed $DataDir (including the manifest)"
    }
} elseif ((Test-Path $Manifest) -and -not $DryRun) {
    Remove-Item -LiteralPath $Manifest -Force
    Write-Note "removed the manifest $Manifest"
}

Write-Host ''
if ($DryRun) { Write-Info "Dry run: $Removed item(s) would be removed, $Kept left alone" } else { Write-Info "OmniScript is uninstalled ($Removed removed, $Kept left alone)" }
if ($Kept -ne 0) {
    Write-Note 'anything left alone is listed above; re-run with -Force if you want it gone'
}
Write-Note 'a source tree you cloned yourself is never deleted by this script'
if ($MChannel -eq 'release') {
    Write-Note 'to put the published release back: iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex'
}
