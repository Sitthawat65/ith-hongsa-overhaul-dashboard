@echo off
setlocal enabledelayedexpansion
title ITH Bearing Temp - RESET / Fix Dashboard
color 0B

REM run from an ASCII path (Chromium cannot use the Thai project folder as cwd)
cd /d "%LOCALAPPDATA%"
set "SCRIPT=%~dp0update_temps.py"

echo ==================================================
echo    ITH BEARING PULLEY TEMP  -  RESET DASHBOARD
echo ==================================================
echo.

REM --- 0a) fast path needs websocket-client (tiny, no browser involved) ---
python -c "import websocket" 1>nul 2>nul
if errorlevel 1 (
  echo [setup] Installing websocket-client...
  python -m pip install --upgrade websocket-client
)

REM --- 0b) Playwright + Chromium: only needed to refresh the login session ---
python -c "import playwright" 1>nul 2>nul
if errorlevel 1 (
  echo [setup] Installing Playwright + Chromium ^(first time, ~130 MB^)...
  python -m pip install --upgrade playwright
  python -m playwright install chromium
  echo.
)

REM --- 1) normal update: pull live values via socket.io, push to GitHub ---
echo [1/4] Pulling latest temperatures from Primus...
python "%SCRIPT%"
if not errorlevel 1 goto ensuretask

REM --- 2) failed = session dead -> open browser to log in, then retry ---
echo.
echo [2/4] Session looks expired. Opening Primus so you can LOG IN...
echo       ^(a browser window will appear - log in, it closes by itself^)
python "%SCRIPT%" --login
echo       Pulling again after login...
python "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo   !! Still could not read values.
  echo      Check your internet connection or Primus login, then run this again.
  echo.
  pause
  exit /b 1
)

:ensuretask
REM --- 3) make sure the every-5-min auto-updater is installed and enabled ---
echo.
echo [3/4] Checking auto-update schedule ^(every 5 min^)...
schtasks /query /tn "ITH_Bearing_Temp_Update" 1>nul 2>nul
if errorlevel 1 (
  set "PYW="
  for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
  if not defined PYW for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYW set "PYW=%%i"
  schtasks /create /tn "ITH_Bearing_Temp_Update" /tr "\"!PYW!\" \"%SCRIPT%\"" /sc minute /mo 5 /f
  echo   Created auto-update task.
) else (
  schtasks /change /tn "ITH_Bearing_Temp_Update" /enable 1>nul 2>nul
  echo   Auto-update task present and enabled.
)


REM --- 4) let the task WAKE the PC, so sleeping no longer freezes the dashboard ---
echo.
echo [4/4] Allowing the updater to wake the PC from sleep...
powershell -NoProfile -Command "foreach ($n in 'ITH_Bearing_Temp_Update','ITH_Flight_Price_Update') { try { $t = Get-ScheduledTask -TaskName $n -ErrorAction Stop; $t.Settings.WakeToRun = $true; $t.Settings.StartWhenAvailable = $true; Set-ScheduledTask -TaskName $n -Settings $t.Settings | Out-Null } catch {} }"
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0 1>nul 2>nul
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0 1>nul 2>nul
powercfg /setactive SCHEME_CURRENT 1>nul 2>nul
echo   Wake timers enabled - the PC will wake itself every 5 min to update.

echo.
echo ==================================================
echo    DONE!  Dashboard updated, auto-update is ON.
echo    The PC will now wake from sleep to keep updating.
echo.
echo    Live: https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/motor_temp.html
echo    ^(the site refreshes ~1 min after each update^)
echo ==================================================
echo.
pause
