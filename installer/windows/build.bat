@echo off
setlocal

REM Build OmniScript Windows installer with Inno Setup
REM Requires: gcc/clang/cc and ISCC (Inno Setup)

set VERSION=
for /f "delims=" %%v in (..\..\VERSION) do set VERSION=%%v
if "%VERSION%"=="" set VERSION=1.0.1

echo ==> OmniScript %VERSION% Windows installer
echo     Building omni.exe

REM Build omni.exe with properly quoted version
where gcc >nul 2>&1
if %ERRORLEVEL%==0 (
    gcc -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\"%VERSION%\" -o ..\..\omni.exe ..\..\src\util.c ..\..\src\lex.c ..\..\src\parse.c ..\..\src\eval.c ..\..\src\draw.c ..\..\src\main.c ..\..\src\gui_win32.c -lgdi32 -luser32
) else (
    where clang >nul 2>&1
    if %ERRORLEVEL%==0 (
        clang -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\"%VERSION%\" -o ..\..\omni.exe ..\..\src\util.c ..\..\src\lex.c ..\..\src\parse.c ..\..\src\eval.c ..\..\src\draw.c ..\..\src\main.c ..\..\src\gui_win32.c -lgdi32 -luser32
    ) else (
        where cc >nul 2>&1
        if %ERRORLEVEL%==0 (
            cc -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\"%VERSION%\" -o ..\..\omni.exe ..\..\src\util.c ..\..\src\lex.c ..\..\src\parse.c ..\..\src\eval.c ..\..\src\draw.c ..\..\src\main.c ..\..\src\gui_win32.c -lgdi32 -luser32
        ) else (
            echo No C compiler found
            exit /b 1
        )
    )
)

if not exist ..\..\omni.exe (
    echo Build failed
    exit /b 1
)

echo     Built omni.exe
..\..\omni.exe --version

REM Build installer with Inno Setup
where iscc >nul 2>&1
if %ERRORLEVEL%==0 (
    echo ==> Building installer with ISCC
    iscc /DMyAppVersion=%VERSION% OmniScript.iss
    echo Installer built in ..\..\dist\
    dir ..\..\dist\
) else (
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        echo ==> Building installer with ISCC from Program Files
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=%VERSION% OmniScript.iss
        dir ..\..\dist\
    ) else (
        echo ISCC not found. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
        echo Then run: iscc /DMyAppVersion=%VERSION% OmniScript.iss
        echo Or use the binary directly: omni.exe
    )
)

endlocal
