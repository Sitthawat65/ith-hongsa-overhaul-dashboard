@echo off
cd /d "%~dp0"
set TELEGRAM_INSECURE_SSL=1
echo ==========================================
echo   ITH - Enter maintenance mode: Relocate Day
echo   (pauses Server/stale alerts for everyone)
echo ==========================================
echo.
if exist C:\Python314\python.exe (
  C:\Python314\python.exe "%~dp0maintenance.py" relocate
) else (
  python "%~dp0maintenance.py" relocate
)
echo.
echo Done. Run Back_to_Normal.bat when the job is finished.
pause
