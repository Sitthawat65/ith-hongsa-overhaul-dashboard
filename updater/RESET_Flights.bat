@echo off
setlocal enabledelayedexpansion
title ITH Flight Price Watch - RESET / Update now
color 0B

cd /d "%LOCALAPPDATA%"
set "SCRIPT=%~dp0update_flights.py"

echo ==================================================
echo    ITH FLIGHT PRICE WATCH  -  Nan / Chiang Mai / Nakhon Phanom ^<-^> Bangkok
echo ==================================================
echo.

python -c "import playwright" 1>nul 2>nul
if errorlevel 1 (
  echo [setup] Installing Playwright + Chromium ^(first time, ~130 MB^)...
  python -m pip install --upgrade playwright
  python -m playwright install chromium
  echo.
)

echo [1/2] Fetching cheapest fares for the next 90 days (3 months)...
echo       ^(6 routes x 90 days = 540 pages - about 2 to 2.5 hours^)
python "%SCRIPT%" --days 90
if errorlevel 1 (
  echo.
  echo   !! Could not read fares. Check your internet connection and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo [2/2] Checking auto-update schedule ^(every 12 hours^)...
schtasks /query /tn "ITH_Flight_Price_Update" 1>nul 2>nul
if errorlevel 1 (
  set "PYW="
  for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
  if not defined PYW for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYW set "PYW=%%i"
  schtasks /create /tn "ITH_Flight_Price_Update" /tr "\"!PYW!\" \"%SCRIPT%\"" /sc hourly /mo 12 /f
  echo   Created auto-update task ^(every 12 hours^).
) else (
  schtasks /change /tn "ITH_Flight_Price_Update" /enable 1>nul 2>nul
  echo   Auto-update task present and enabled.
)

echo.
echo ==================================================
echo    DONE!  Prices updated, auto-update is ON.
echo.
echo    Live: https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/flights.html
echo ==================================================
echo.
pause
