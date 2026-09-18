# Uninstall OmniScript on Windows (and anywhere else pwsh runs).
#
#   .\uninstall.ps1                 # take out the command
#   .\uninstall.ps1 -DryRun         # show what would go
#   .\uninstall.ps1 -Purge          # ...plus the REPL history, a cloned source
#                                   #    tree, and the manifest itself
#
# This works from the manifest install.ps1 wrote, so it removes exactly what was
# installed -- a downloaded executable as readily as a link into a source tree.
# It never deletes a source tree you cloned
# yourself, and it will not remove a command it cannot prove it created: use
# -Force for that, and read what it says first.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Prefix = '',
    [switch]$Purge,
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
function Test-SourceTree {
    param([string]$Dir)
    return ($Dir -and (Test-Path -LiteralPath (Join-Path $Dir 'Makefile')) -and
        (Test-Path -LiteralPath (Join-Path $Dir 'src/main.c')))
}

if ($Help) {
    @'
Usage: uninstall.ps1 [options]

  -Prefix DIR      install root that was used     [see install.ps1]
  -Purge           also remove the REPL history, a source tree the installer
                   cloned, and the manifest
  -Force           remove the command even when it does not look like ours
  -DryRun          print what would be removed and remove nothing
  -Help            this text
'@ | Write-Host
    exit 0
}

if (-not $Prefix) {
    if ($IsWin) {
        $local = $env:LOCALAPPDATA
        if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\\Local' }
        $Prefix = Join-Path $local 'Programs\\OmniScript'
        $DataDir = Join-Path $local 'OmniScript'
    } else {
        $Prefix = Join-Path $env:HOME '.local'
        $DataDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'omniscript' } else { Join-Path $env:HOME '.local/share/omniscript' }
    }
} else {
    if ($IsWin) {
        $local = $env:LOCALAPPDATA
        if (-not $local) { $local = Join-Path $env:USERPROFILE 'AppData\\Local' }
        $DataDir = Join-Path $local 'OmniScript'
    } else {
        $DataDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'omniscript' } else { Join-Path $env:HOME '.local/share/omniscript' }
    }
}
if ($IsWin) { $Bin = $Prefix } else { $Bin = Join-Path $Prefix 'bin' }
$Manifest = Join-Path $DataDir 'install.txt'

# The manifest is one key=value per line, with a repeated line per installed
# command -- the same file install.sh writes and reads with sed.
$MVersion = ''; $MMode = ''; $MChannel = ''; $MSource = ''
$MBinary = ''; $MCloned = $false
$MHistory = Join-Path $(if ($IsWin) { $env:USERPROFILE } else { $env:HOME }) '.omniscript_history'
$MCommands = @()

if (Test-Path -LiteralPath $Manifest) {
    Write-Info "Reading $Manifest"
    foreach ($line in (Get-Content -LiteralPath $Manifest)) {
        $parts = "$line" -split '=', 2
        if ($parts.Count -lt 2) { continue }
        $value = $parts[1].Trim()
        switch ($parts[0].Trim()) {
            'version'             { $MVersion = $value }
            'mode'                { $MMode = $value }
            'channel'             { $MChannel = $value }
            'source'              { $MSource = $value }
            'binary'              { $MBinary = $value }
            'cloned_by_installer' { $MCloned = ($value -eq '1') }
            'history_file'        { if ($value) { $MHistory = $value } }
            'command'             { if ($value) { $MCommands += $value } }
        }
    }
    if ($MVersion) {
        Write-Info "OmniScript $MVersion, installed in $MMode mode"
        if ($MChannel) { Write-Note "$MChannel channel" }
    }
} else {
    Write-Note "no manifest at $Manifest; falling back to $Bin"
}

if ($MCommands.Count -eq 0) {
    # No manifest, so guess: on Windows the command is either a .cmd shim from
    # the beta channel or an omni.exe from the release channel.
    $MCommands += $(if ($IsWin) { Join-Path $Bin 'omni.cmd' } else { Join-Path $Bin 'omni' })
    if ($IsWin) { $MCommands += Join-Path $Bin 'omni.exe' }
}

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
        if ($MSource -and $target.StartsWith($MSource)) { return $true }
        if (-not $MSource) {
            # No manifest roots to compare with: trust a link into an OmniScript tree.
            if (Test-SourceTree (Split-Path $target -Parent)) { return $true }
        }
        return $false
    }
    $head = (Get-Content -LiteralPath $Path -TotalCount 8 -ErrorAction SilentlyContinue) -join "`n"
    if ($MSource -and $head -match [regex]::Escape($MSource)) { return $true }
    # No manifest to compare with: a shim we wrote quotes the binary it runs,
    # so see whether any path in it lives beside an OmniScript source tree.
    foreach ($match in [regex]::Matches($head, '"([^"]+)"')) {
        $dir = Split-Path $match.Groups[1].Value -Parent
        if ($dir -and (Test-SourceTree $dir)) { return $true }
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

# --------------------------------------------------------- command
Write-Info 'Removing the command'
foreach ($path in $MCommands) {
    Remove-Item-IfOurs -Path $path -What 'command'
}
foreach ($name in @('omni.cmd.bak', 'omni.exe.bak', 'omni.bak')) {
    $bak = Join-Path $Bin $name
    if (Test-Path $bak) { Write-Note "a backup of your previous command is still at $bak" }
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
