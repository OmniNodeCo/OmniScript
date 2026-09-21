# OmniScript native builder — no make, no Python, just a C compiler.
# Works on Windows (MSVC cl, gcc, clang) and on Linux/macOS (cc/gcc/clang).
# This is what install.ps1 now uses for the beta channel.
#
#   pwsh ./build.ps1                 # builds ./omni or ./omni.exe
#   pwsh ./build.ps1 -Output out.exe # custom output
#   pwsh ./build.ps1 -NoGui          # no X11 / no Win32 window, file fallback only
#   pwsh ./build.ps1 -Compiler gcc   # force a compiler
#   pwsh ./build.ps1 -Clean          # remove built files
#   pwsh ./build.ps1 -VerboseBuild   # show the compile command
#
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Output = "",
    [string]$Compiler = "",
    [string]$Version = "",
    [switch]$NoGui,
    [switch]$Clean,
    [switch]$VerboseBuild,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Write-Info { param([string]$Text) Write-Host "==> $Text" }
function Write-Note { param([string]$Text) Write-Host "    $Text" }
function Stop-Die {
    param([string]$Text)
    Write-Host "build.ps1: error: $Text" -ForegroundColor Red
    exit 1
}

if ($Help) {
    @'
Usage: build.ps1 [options]

  -Output PATH       where to write the binary [./omni(.exe)]
  -Compiler NAME     cl, gcc, clang, cc -- auto-detected by default
  -Version VER       override VERSION file
  -NoGui             build without windows (drawings become BMP files)
  -Clean             remove built binaries and object files
  -VerboseBuild      show the full compiler command
  -Help              this text

No make, no Python. Just a C compiler (MSVC, MinGW gcc, clang, or cc).
'@
    exit 0
}

# ------------------------------------------------------------------ root
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
$Root = (Resolve-Path $Root -ErrorAction SilentlyContinue).Path
if (-not $Root) { $Root = $PSScriptRoot }

# Version from file or param
if (-not $Version) {
    $verFile = Join-Path $Root "VERSION"
    if (Test-Path -LiteralPath $verFile) {
        $Version = ((Get-Content -LiteralPath $verFile -TotalCount 1) -join "").Trim()
    }
}
if (-not $Version) { $Version = "0.0.0" }

# Platform
$IsWinOS = $false
try {
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        $IsWinOS = $IsWindows
    } else {
        $IsWinOS = ([System.Environment]::OSVersion.Platform -eq "Win32NT")
    }
} catch {
    $IsWinOS = ($env:OS -like "*Windows*")
}
if (-not $IsWinOS) {
    # fallback: uname -s contains MINGW/MSYS/CYGWIN => Windows
    try {
        $u = (& uname -s 2>$null)
        if ($u -match "MINGW|MSYS|CYGWIN|Windows") { $IsWinOS = $true }
    } catch { }
}

$ExeSuffix = if ($IsWinOS) { ".exe" } else { "" }
if (-not $Output) {
    $Output = Join-Path $Root "omni$ExeSuffix"
}
# Resolve output to absolute if relative
if (-not [System.IO.Path]::IsPathRooted($Output)) {
    $Output = Join-Path (Get-Location).Path $Output
}

# ------------------------------------------------------------------ clean
if ($Clean) {
    Write-Info "Cleaning"
    $toRemove = @(
        (Join-Path $Root "omni"),
        (Join-Path $Root "omni.exe"),
        (Join-Path $Root "omni$ExeSuffix"),
        $Output
    )
    foreach ($p in $toRemove) {
        if (Test-Path -LiteralPath $p) {
            Write-Note "remove $p"
            Remove-Item -Force -LiteralPath $p -ErrorAction SilentlyContinue
        }
    }
    foreach ($obj in @("*.o", "*.obj")) {
        Get-ChildItem -Path (Join-Path $Root "src") -Filter $obj -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Note "remove $($_.FullName)"
                Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue
            }
    }
    Write-Info "clean done"
    exit 0
}

# ------------------------------------------------------------------ sources
$SrcDir = Join-Path $Root "src"
if (-not (Test-Path -LiteralPath (Join-Path $SrcDir "main.c"))) {
    Stop-Die "no source tree at $SrcDir (expected src/main.c)"
}

$BaseSources = @(
    "util.c", "lex.c", "parse.c", "eval.c", "draw.c", "sha256.c", "update.c", "main.c"
)

$GuiFile = ""
if ($NoGui) {
    $GuiFile = "gui_stub.c"
    Write-Note "NoGui forced -- using gui_stub.c"
} elseif ($IsWinOS) {
    $GuiFile = "gui_win32.c"
} else {
    # check for X11 headers
    $x11Candidates = @(
        "/usr/include/X11/Xlib.h",
        "/usr/local/include/X11/Xlib.h",
        "/opt/X11/include/X11/Xlib.h",
        "/opt/homebrew/include/X11/Xlib.h"
    )
    $foundX11 = $false
    foreach ($h in $x11Candidates) {
        if (Test-Path -LiteralPath $h) { $foundX11 = $true; break }
    }
    if ($foundX11) {
        $GuiFile = "gui_x11.c"
        Write-Note "X11 headers found -- using gui_x11.c"
    } else {
        $GuiFile = "gui_stub.c"
        Write-Note "no X11 headers -- using gui_stub.c (drawings become BMP files)"
    }
}

$AllSources = @()
foreach ($name in $BaseSources) {
    $AllSources += (Join-Path $SrcDir $name)
}
$AllSources += (Join-Path $SrcDir $GuiFile)

foreach ($s in $AllSources) {
    if (-not (Test-Path -LiteralPath $s)) {
        Stop-Die "missing source $s"
    }
}

# ------------------------------------------------------------------ compiler detection
function Find-Compiler {
    param([string]$Hint, [bool]$IsWin)
    if ($Hint) {
        $cmd = Get-Command $Hint -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        # also try Hint.exe on Windows
        if ($IsWin) {
            $cmd = Get-Command "$Hint.exe" -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        }
        Stop-Die "compiler '$Hint' not found on PATH"
    }

    # env var CC wins
    if ($env:CC) {
        $cmd = Get-Command $env:CC -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        # CC might be a full path
        if (Test-Path -LiteralPath $env:CC) { return $env:CC }
    }

    $orderWin = @("cl", "gcc", "clang", "cc", "clang-cl")
    $orderUnix = @("cc", "gcc", "clang", "cl")
    $order = if ($IsWin) { $orderWin } else { $orderUnix }

    foreach ($name in $order) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        if ($IsWin) {
            $cmd = Get-Command "$name.exe" -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        }
    }
    return $null
}

$CompilerPath = Find-Compiler -Hint $Compiler -IsWin $IsWinOS
if (-not $CompilerPath) {
    Stop-Die "no C compiler found. Install one: Visual Studio Build Tools (cl), MinGW gcc, or clang, and ensure it is on PATH."
}

$CompilerName = [System.IO.Path]::GetFileNameWithoutExtension($CompilerPath).ToLowerInvariant()
$IsMsvc = ($CompilerName -eq "cl" -or $CompilerName -eq "clang-cl")

Write-Info "OmniScript $Version"
Write-Note "root: $Root"
Write-Note "compiler: $CompilerPath ($CompilerName)"
Write-Note "gui: $GuiFile"
Write-Note "output: $Output"

# ------------------------------------------------------------------ build
$OutputDir = Split-Path $Output -Parent
if ($OutputDir -and -not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

if ($IsMsvc) {
    # MSVC cl path
    # Escape version for /D
    $verEscaped = $Version -replace '"', '\"'
    $cflags = @(
        "/nologo",
        "/O2",
        "/W3",
        "/std:c11",
        "/D", "OMNI_VERSION=`"$verEscaped`"",
        "/Fo$(Join-Path $SrcDir 'omni_')",
        "/Fe$Output"
    )
    # Add define for Windows (cl already defines _WIN32)
    # No extra includes needed

    $linkLibs = @("gdi32.lib", "user32.lib")

    $args = @()
    $args += $cflags
    $args += $AllSources
    $args += "/link"
    $args += $linkLibs
    $args += "/SUBSYSTEM:CONSOLE"

    if ($VerboseBuild) {
        Write-Host "cl $($args -join ' ')"
    }

    Write-Info "Compiling with cl"
    # cl returns non-zero on failure
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $CompilerPath @args
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $oldPref

    if ($rc -ne 0) {
        Stop-Die "cl failed with exit code $rc"
    }

    # cl leaves .obj files with prefix we gave; clean them
    Get-ChildItem -Path $SrcDir -Filter "omni_*.obj" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue }

} else {
    # gcc / clang / cc compatible
    $verEscaped = $Version -replace '"', '\"'
    $cflags = @(
        "-O2",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-DOMNI_VERSION=`"$verEscaped`""
    )
    if (-not $IsWinOS) {
        $cflags += "-D_POSIX_C_SOURCE=200809L"
    }
    if ($GuiFile -eq "gui_x11.c") {
        $cflags += "-DHAVE_X11"
    }

    $ldlibs = @()
    if ($IsWinOS) {
        $ldlibs += "-lgdi32"
        $ldlibs += "-luser32"
    } elseif ($GuiFile -eq "gui_x11.c") {
        $ldlibs += "-lX11"
    }

    $args = @()
    $args += $cflags
    $args += "-o"
    $args += $Output
    $args += $AllSources
    $args += $ldlibs

    if ($VerboseBuild) {
        Write-Host "$CompilerPath $($args -join ' ')"
    }

    Write-Info "Compiling with $CompilerName"
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $CompilerPath @args
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $oldPref

    if ($rc -ne 0) {
        Stop-Die "$CompilerName failed with exit code $rc"
    }
}

if (-not (Test-Path -LiteralPath $Output)) {
    Stop-Die "build finished but $Output not found"
}

# Make executable on Unix
if (-not $IsWinOS) {
    try { & chmod 755 $Output } catch { }
}

$size = (Get-Item -LiteralPath $Output).Length
Write-Info "built $Output ($size bytes)"

# Smoke test
try {
    $verOut = & $Output --version 2>&1
    Write-Note "$verOut"
} catch {
    Write-Note "built but --version failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Info "Done. Run it: $Output --version  or  $Output -e 'cmd(\"echo hi\")'"
