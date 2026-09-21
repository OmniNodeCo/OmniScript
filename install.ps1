# Simple installer for OmniScript 2.0.0
param([string]$Prefix = "")

$ErrorActionPreference = "Stop"
$Src = $PSScriptRoot
if (-not $Prefix) {
    $local = $env:LOCALAPPDATA
    if (-not $local) { $local = Join-Path $env:USERPROFILE "AppData\Local" }
    $Prefix = Join-Path $local "Programs\OmniScript"
}
$Bin = $Prefix
$Version = (Get-Content "$Src\VERSION" -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
if (-not $Version) { $Version = "2.0.0" }

Write-Host "==> OmniScript $Version — super simple"
Write-Host "    Building from $Src"

# Find compiler
$cc = $null
foreach ($name in @("cl","gcc","clang","cc")) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { $cc = $c.Source; break }
    $c = Get-Command "$name.exe" -ErrorAction SilentlyContinue
    if ($c) { $cc = $c.Source; break }
}
if (-not $cc) { Write-Host "no C compiler found"; exit 1 }

New-Item -ItemType Directory -Force -Path $Bin | Out-Null

$srcFiles = @("src\util.c","src\lex.c","src\parse.c","src\eval.c","src\draw.c","src\main.c","src\gui_win32.c")
$fullSrc = $srcFiles | ForEach-Object { Join-Path $Src $_ }

if ($cc -like "*cl.exe") {
    & $cc /nologo /O2 /W3 /std:c11 /D "OMNI_VERSION=`"$Version`"" /Fe"$Src\omni.exe" $fullSrc /link gdi32.lib user32.lib
} else {
    & $cc -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION="$Version" -D_POSIX_C_SOURCE=200809L -o "$Src\omni.exe" $fullSrc -lgdi32 -luser32
}

Copy-Item -Force "$Src\omni.exe" "$Bin\omni.exe"
Write-Host "==> Installed to $Bin\omni.exe"
& "$Bin\omni.exe" --version
& "$Bin\omni.exe" -e 'import draw; draw.window(100,100); draw.rect(0,0,50,50,"red"); draw.save("test.bmp"); print("ok")'
Remove-Item -Force test.bmp -ErrorAction SilentlyContinue
Write-Host "Done. Add $Bin to PATH if needed."
