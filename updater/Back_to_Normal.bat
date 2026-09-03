@echo off
cd /d "%~dp0"
echo ==========================================
echo   ITH - Back to NORMAL (resume alerts)
echo ==========================================
echo.
if exist C:\Python314\python.exe (
  C:\Python314\python.exe "%~dp0maintenance.py" normal
) else (
  python "%~dp0maintenance.py" normal
)
echo.
pause
