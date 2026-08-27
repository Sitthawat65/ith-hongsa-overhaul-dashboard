@echo off
setlocal
title ITH Bearing Temp - remove acknowledge listener
echo Removing the Telegram acknowledge listener...
schtasks /End    /TN "ITH_Telegram_Listener" >nul 2>&1
schtasks /Delete /TN "ITH_Telegram_Listener" /F >nul 2>&1
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *telegram_listener*" >nul 2>&1
echo.
echo Done. Alerts still work - pressing ACKNOWLEDGE just takes
echo up to 5 minutes to register instead of being instant.
echo.
pause
