@echo off
rem WorkBuddy credit whale widget - one-time setup.
rem Installs Pillow and drops a shortcut into the Startup folder so the whale
rem comes back after a reboot. ASCII-only + CRLF on purpose (see start-whale.vbs).
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 goto nopython

echo [1/2] Installing Pillow ...
python -m pip install --upgrade pillow
if errorlevel 1 goto pipfail
echo.

echo [2/2] Creating the startup shortcut ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=$PWD.Path; $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'WorkBuddy Whale.lnk')); $s.TargetPath=(Join-Path $d 'start-whale.vbs'); $s.WorkingDirectory=$d; $s.IconLocation=((Join-Path $d 'assets\whale.ico') + ',0'); $s.Description='WorkBuddy credit whale widget'; $s.Save()"
if errorlevel 1 goto lnkfail
echo.

echo Done. The whale will now start on every logon.
echo Double-click start-whale.vbs to see it right away.
echo.
pause
exit /b 0

:nopython
echo.
echo Python was not found in PATH.
echo Install Python 3 from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run me again.
echo.
pause
exit /b 1

:pipfail
echo.
echo pip could not install pillow. Run this by hand to see the full error:
echo     python -m pip install pillow
echo.
pause
exit /b 1

:lnkfail
echo.
echo Pillow is installed, but the startup shortcut could not be created.
echo Make it by hand: press Win+R, type  shell:startup  and drop a shortcut
echo to start-whale.vbs into that folder.
echo.
pause
exit /b 1
