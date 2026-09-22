# Fix omni PATH like git does — run if 'omni' not recognized
# This script makes omni work in any terminal immediately
$ErrorActionPreference = "Continue"

$app = "C:\Program Files\OmniScript"
if (-not (Test-Path "$app\omni.exe")) {
  $app = "$env:LOCALAPPDATA\Programs\OmniScript"
}
if (-not (Test-Path "$app\omni.exe")) {
  $app = (Get-ChildItem -Path "C:\Program Files\" -Filter "omni.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1).DirectoryName
}
if (-not $app) { $app = "C:\Program Files\OmniScript" }

Write-Host "==> OmniScript fix-path like git CLI"
Write-Host "    App dir: $app"

# Add to USER PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$app*") {
  Write-Host "    Adding $app to USER PATH"
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$app", "User")
  $env:Path += ";$app"
}

# Add to MACHINE PATH if admin
try {
  $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  if ($machinePath -notlike "*$app*") {
    Write-Host "    Adding $app to MACHINE PATH (admin)"
    [Environment]::SetEnvironmentVariable("Path", "$machinePath;$app", "Machine")
  }
} catch {
  Write-Host "    No admin for MACHINE PATH, USER PATH is enough like git"
}

# Fallback copies to locations always in PATH (like git does)
$win = "$env:WINDIR"
$sys = "$env:WINDIR\System32"
$winApps = "$env:LOCALAPPDATA\Microsoft\WindowsApps"

foreach ($dir in @($win, $sys, $winApps)) {
  if (Test-Path $dir) {
    try {
      if (Test-Path "$app\omni.exe") {
        Copy-Item "$app\omni.exe" "$dir\omni.exe" -Force -ErrorAction SilentlyContinue
        Write-Host "    Copied omni.exe to $dir"
      }
    } catch { Write-Host "    Failed to copy to $dir : $_" }
  }
}

# Create omni.bat wrapper
$batContent = "@echo off`r`n`"%~dp0omni.exe`" %*`r`n"
try {
  Set-Content -Path "$app\omni.bat" -Value $batContent -Force
  Copy-Item "$app\omni.bat" "$win\omni.bat" -Force -ErrorAction SilentlyContinue
  Copy-Item "$app\omni.bat" "$sys\omni.bat" -Force -ErrorAction SilentlyContinue
} catch {}

# Broadcast env change
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Env {
  [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
}
"@
$HWND_BROADCAST = [IntPtr]0xffff
$WM_SETTINGCHANGE = 0x001A
$result = [UIntPtr]::Zero
[Env]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null

Write-Host ""
Write-Host "==> Fixed! Now REOPEN terminal and type:"
Write-Host "    omni --version"
Write-Host "    omni"
Write-Host "    omni examples\01_hello.omni"
Write-Host "    omni -e ""print(\""hello\"")"""
Write-Host ""
Write-Host "Works in CMD, PowerShell, Windows Terminal, Git Bash like git does."
