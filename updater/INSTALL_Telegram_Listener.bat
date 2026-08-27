@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title ITH Bearing Temp - Telegram acknowledge listener
echo ============================================================
echo   Telegram acknowledge listener
echo ============================================================
echo.
echo   This keeps a small background process running so that
echo   pressing the ACKNOWLEDGE button in Telegram stops the
echo   repeat alerts instantly instead of up to 5 minutes later.
echo   It also answers /status in the chat at any time.
echo.
echo   It starts automatically every time you log in to Windows.
echo   No administrator rights are needed.
echo.
pause

for /f "delims=" %%P in ('where pythonw 2^>nul') do set "PYW=%%P"
if not defined PYW (
  echo   ERROR: pythonw was not found on PATH.
  goto end
)
echo   Using: !PYW!

set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ITH_Telegram_Listener.vbs"

REM stop any copy that is already running, then rebuild the startup entry
taskkill /F /IM pythonw.exe >nul 2>&1
if exist "!VBS!" del /f /q "!VBS!" >nul 2>&1

python "%~dp0install_listener.py" "!PYW!"
if errorlevel 1 (
  echo   ERROR: could not write the startup entry.
  goto end
)

echo   Starting it now...
wscript.exe "!VBS!"
echo.
echo ============================================================
echo   Done. Send /status to your bot in Telegram to check it.
echo   To remove it later, run UNINSTALL_Telegram_Listener.bat
echo ============================================================
:end
echo.
pause
