@echo off
setlocal
set "UNINSTALLER="
if exist "%~dp0uninstall.ps1" set "UNINSTALLER=%~dp0uninstall.ps1"
if not defined UNINSTALLER if exist "%~dp0scripts\uninstall.ps1" set "UNINSTALLER=%~dp0scripts\uninstall.ps1"
if not defined UNINSTALLER (
    echo error: scripts\uninstall.ps1 was not found 1>&2
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%UNINSTALLER%"
exit /b %ERRORLEVEL%
