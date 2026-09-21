# Build OmniScript Windows installer
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Version = (Get-Content "$Root\VERSION" -First 1).Trim()
if (-not $Version) { $Version = "2.0.0" }

Write-Host "==> OmniScript $Version Windows installer"
Write-Host "    Building omni.exe"

$src = @("src\util.c","src\lex.c","src\parse.c","src\eval.c","src\draw.c","src\main.c","src\gui_win32.c")
$fullSrc = $src | ForEach-Object { Join-Path $Root $_ }

# Find compiler
$cc = $null
foreach ($name in @("gcc","clang","cc","cl")) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { $cc = $c.Source; break }
}
if (-not $cc) { throw "No C compiler found" }

Write-Host "    Using $cc"

if ($cc -like "*cl.exe") {
    & $cc /nologo /O2 /W3 /std:c11 /D "OMNI_VERSION=`"$Version`"" /Fe"$Root\omni.exe" $fullSrc /link gdi32.lib user32.lib
} else {
    & $cc -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION="$Version" -o "$Root\omni.exe" $fullSrc -lgdi32 -luser32
}

if (-not (Test-Path "$Root\omni.exe")) { throw "Build failed" }
& "$Root\omni.exe" --version

# Inno Setup
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) { $iscc = Get-Command ISCC -ErrorAction SilentlyContinue }
if ($iscc) {
    Write-Host "==> Building installer with ISCC"
    Push-Location $PSScriptRoot
    & $iscc.Source "/DMyAppVersion=$Version" OmniScript.iss
    Pop-Location
    Get-ChildItem "$Root\dist" | Format-Table
} else {
    Write-Host "ISCC not found. Install Inno Setup 6: https://jrsoftware.org/isinfo.php"
    Write-Host "Then: iscc /DMyAppVersion=$Version OmniScript.iss"
}
