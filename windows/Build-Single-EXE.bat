@echo off
setlocal
cd /d "%~dp0"
title Jadeit - Build ONE standalone EXE
echo.
echo  ==============================================================
echo    Jadeit : convert the system into ONE standalone EXE file
echo    Output : Jadeit-Standalone.exe   (works offline, no setup)
echo    Windows 7 / 8 / 10 / 11
echo  ==============================================================
echo.
echo  NOTE: Jadeit.exe in this folder already runs the system with one
echo        click. This tool only packs everything into a single file
echo        that you can copy alone to another computer.
echo.

if not exist "python\python.exe" goto nopython
if not exist "prereqs\wheels" goto nowheels

set "PYI=%~dp0build\pyinstaller-lib"
if exist "%PYI%\PyInstaller\__init__.py" goto build

echo  [1/3] Installing the build tool (PyInstaller) from the local folder - no internet needed...
"python\python.exe" -s -m pip install --disable-pip-version-check --no-warn-script-location --no-index --find-links "%~dp0prereqs\wheels" --target "%PYI%" pyinstaller
if errorlevel 1 goto fail

:build
echo  [2/3] Building Jadeit-Standalone.exe ... please wait (1 to 3 minutes)
set "PYTHONPATH=%PYI%"
"python\python.exe" -s -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Jadeit-Standalone ^
  --icon "%~dp0app\jadeit.ico" ^
  --distpath "%~dp0build\dist" --workpath "%~dp0build\work" --specpath "%~dp0build" ^
  --add-data "%~dp0app\web;web" ^
  --add-data "%~dp0app\server\schema.sql;server" ^
  --paths "%~dp0app" ^
  "%~dp0app\desktop.py"
if errorlevel 1 goto fail
if not exist "build\dist\Jadeit-Standalone.exe" goto fail

copy /y "build\dist\Jadeit-Standalone.exe" "%~dp0Jadeit-Standalone.exe" >nul
echo  [3/3] Done.
echo.
echo  ==============================================================
echo    SUCCESS:  Jadeit-Standalone.exe  was created in this folder.
echo    Double-click it to run. Its data is saved in the "data"
echo    folder next to it. You may delete the "build" folder.
echo  ==============================================================
echo.
pause
exit /b 0

:nopython
echo  [!] The folder "python" is missing. Extract the whole ZIP file first.
goto end
:nowheels
echo  [!] The folder "prereqs\wheels" is missing. Extract the whole ZIP file first.
goto end
:fail
echo.
echo  [!] The build failed. Please send a screenshot of this window.
:end
echo.
pause
exit /b 1
