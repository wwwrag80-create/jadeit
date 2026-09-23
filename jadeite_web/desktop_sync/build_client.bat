@echo off
REM ============================================================================
REM  Jadeite - build the CLIENT version by double-click
REM  Output: dist\Jadeite-Client-<version>.exe
REM  First run creates a separate build environment (.venv-build) and installs
REM  the libraries there. Extra options are passed through, e.g. --console
REM  Full explanation (Arabic): BUILD_AR.md
REM ============================================================================
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo.
    echo X  Python not found. Install Python 3.11+ from https://www.python.org/downloads/
    echo    and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    echo Creating build environment .venv-build ...
    %PY% -m venv .venv-build
    if errorlevel 1 (
        echo X  Could not create the build environment.
        pause
        exit /b 1
    )
)

".venv-build\Scripts\python.exe" build_exe.py client %*
if errorlevel 1 (
    echo.
    echo X  BUILD FAILED - read the message above.
    pause
    exit /b 1
)

echo.
echo OK  Done. Your file is in the dist folder:
dir /b dist\Jadeite-Client-*.exe
start "" "%~dp0dist"
pause
