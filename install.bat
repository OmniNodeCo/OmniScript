@echo off
setlocal

set "INSTALLER="
if exist "%~dp0install.ps1" set "INSTALLER=%~dp0install.ps1"
if not defined INSTALLER if exist "%~dp0scripts\install.ps1" set "INSTALLER=%~dp0scripts\install.ps1"

if defined INSTALLER (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%"
    if errorlevel 1 exit /b 1
    exit /b 0
)

set "INSTALLER=%TEMP%\omniscript-install-%RANDOM%%RANDOM%.ps1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/install.ps1' -OutFile '%INSTALLER%'"
if errorlevel 1 exit /b %ERRORLEVEL%
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%"
set "RESULT=%ERRORLEVEL%"
del /q "%INSTALLER%" >nul 2>nul
exit /b %RESULT%
