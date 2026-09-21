# Simple uninstall
param([string]$Prefix = "")
if (-not $Prefix) {
    $local = $env:LOCALAPPDATA
    if (-not $local) { $local = Join-Path $env:USERPROFILE "AppData\Local" }
    $Prefix = Join-Path $local "Programs\OmniScript"
}
Write-Host "==> Removing OmniScript from $Prefix"
Remove-Item -Force "$Prefix\omni.exe" -ErrorAction SilentlyContinue
Remove-Item -Force "$Prefix\omni.cmd" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\OmniScript" -ErrorAction SilentlyContinue
Write-Host "Removed"
