@echo off
REM OmniScript wrapper - ensures omni works
REM This file is in {app} which is added to PATH, and also fallback copies in C:\Windows
"%~dp0omni.exe" %*
