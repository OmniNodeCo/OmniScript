@echo off
setlocal
cd /d "%~dp0.."
if not defined PYTHON set "PYTHON=python"
if not defined OMNISCRIPT_BUILD_VENV set "OMNISCRIPT_BUILD_VENV=%CD%\.build-venv"
if not exist "%OMNISCRIPT_BUILD_VENV%\Scripts\python.exe" (
    %PYTHON% -m venv "%OMNISCRIPT_BUILD_VENV%" || exit /b 1
)
set "BUILD_PYTHON=%OMNISCRIPT_BUILD_VENV%\Scripts\python.exe"
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check -e ".[build]" || exit /b 1
set "MACHINE=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "MACHINE=%PROCESSOR_ARCHITEW6432%"
if /I "%MACHINE%"=="ARM64" (
    set "ARCH=arm64"
) else (
    set "ARCH=x86_64"
)
"%BUILD_PYTHON%" scripts\build_executable.py --name "omni-windows-%ARCH%" --asset "omni-windows-%ARCH%.exe" --output artifacts
exit /b %ERRORLEVEL%
