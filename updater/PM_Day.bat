@echo off
cd /d "%~dp0"
echo ==========================================
echo   ITH - Enter maintenance mode: PM Day
echo   (pauses Server/stale alerts for everyone)
echo ==========================================
echo.
if exist C:\Python314\python.exe (
  C:\Python314\python.exe "%~dp0maintenance.py" pm
) else (
  python "%~dp0maintenance.py" pm
)
echo.
echo Done. Run Back_to_Normal.bat when the job is finished.
pause
