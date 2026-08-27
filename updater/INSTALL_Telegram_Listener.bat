@echo off
setlocal
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
echo.
pause
schtasks /Query /TN "ITH_Telegram_Listener" >nul 2>&1
if not errorlevel 1 (
  echo   Removing the previous listener task...
  schtasks /End    /TN "ITH_Telegram_Listener" >nul 2>&1
  schtasks /Delete /TN "ITH_Telegram_Listener" /F >nul 2>&1
)
for /f "delims=" %%P in ('where pythonw') do set PYW=%%P& goto :got
:got
if "%PYW%"=="" (
  echo   ERROR: pythonw was not found on PATH.
  goto end
)
echo   Using: %PYW%
schtasks /Create /TN "ITH_Telegram_Listener" /SC ONLOGON /RL LIMITED /F ^
  /TR "\"%PYW%\" \"%~dp0telegram_listener.py\"" >nul
if errorlevel 1 (
  echo   ERROR: could not create the scheduled task.
  goto end
)
echo   Task created. Starting it now...
schtasks /Run /TN "ITH_Telegram_Listener" >nul
echo.
echo   Done. Send /status to your bot in Telegram to check it.
echo   To remove it later, run UNINSTALL_Telegram_Listener.bat
:end
echo.
pause
