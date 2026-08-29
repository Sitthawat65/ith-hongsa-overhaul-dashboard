@echo off
setlocal
title ITH Bearing Temp - FIX Sleep / Wake
color 0B

echo ==================================================
echo    FIX: let the updater WAKE the PC from sleep
echo ==================================================
echo.
echo   Problem this fixes:
echo   while Windows is asleep NOTHING runs - not the
echo   5-min updater, not git push, not Telegram.
echo   Leaving Primus open in the browser does not help.
echo.

echo [1/3] Letting the scheduled tasks wake the PC...
powershell -NoProfile -Command "foreach ($n in 'ITH_Bearing_Temp_Update','ITH_Flight_Price_Update') { try { $t = Get-ScheduledTask -TaskName $n -ErrorAction Stop; $t.Settings.WakeToRun = $true; $t.Settings.StartWhenAvailable = $true; Set-ScheduledTask -TaskName $n -Settings $t.Settings | Out-Null; Write-Host ('   ' + $n + ' -> WakeToRun ON') } catch { Write-Host ('   ' + $n + ' -> not installed, skipped') } }"

echo.
echo [2/3] Enabling wake timers on battery and mains...
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0 1>nul 2>nul
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0 1>nul 2>nul
powercfg /setactive SCHEME_CURRENT 1>nul 2>nul
echo    Wake timers = Enable ^(AC + DC^)

echo.
echo [3/3] Verifying...
powershell -NoProfile -Command "$t = Get-ScheduledTask -TaskName 'ITH_Bearing_Temp_Update' -ErrorAction SilentlyContinue; if ($t) { $i = $t | Get-ScheduledTaskInfo; Write-Host ('   WakeToRun          : ' + $t.Settings.WakeToRun); Write-Host ('   StartWhenAvailable : ' + $t.Settings.StartWhenAvailable); Write-Host ('   LastRunTime        : ' + $i.LastRunTime); Write-Host ('   LastTaskResult     : ' + $i.LastTaskResult + '   (0 = OK)'); Write-Host ('   NextRunTime        : ' + $i.NextRunTime) } else { Write-Host '   Task not installed - run RESET_Dashboard.bat first.' }"

echo.
echo ==================================================
echo    DONE.  The PC will now wake every 5 minutes
echo    to refresh the dashboard and Telegram.
echo.
echo    Tip: to stop sleeping by accident, set the power
echo    button to "Do nothing" in Control Panel ^>
echo    Power Options ^> Choose what the power button does.
echo ==================================================
echo.
pause
