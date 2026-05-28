@echo off
setlocal EnableExtensions

rem Keep this launcher ASCII-only: older cmd.exe builds can misread
rem UTF-8/Cyrillic text in .bat files and then execute fragments as commands.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "APP_DIR=%~dp0"
pushd "%APP_DIR%"
if errorlevel 1 (
  echo [ERROR] Could not enter application folder: "%APP_DIR%"
  pause
  exit /b 1
)
set "SCRIPT=%APP_DIR%wallet_recovery_gui_final.py"

if exist "%SCRIPT%" goto :find_python
echo [ERROR] Script not found: "%SCRIPT%"
echo [ERROR] Start this file from the project folder that contains wallet_recovery_gui_final.py.
pause
exit /b 1

:find_python
where py >nul 2>nul
if errorlevel 1 goto :try_python
py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto :try_python
echo [INFO] Starting with py -3.12
py -3.12 "%SCRIPT%"
exit /b %ERRORLEVEL%

:try_python
where python >nul 2>nul
if errorlevel 1 goto :install_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 goto :install_python
echo [INFO] Starting with python
python "%SCRIPT%"
exit /b %ERRORLEVEL%

:install_python
echo [WARN] Python 3.8+ was not found. Trying to install Python 3.12 with winget...
where winget >nul 2>nul
if errorlevel 1 goto :no_winget
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :winget_failed
echo [INFO] Python install finished. Restarting GUI...
py -3.12 "%SCRIPT%"
if not errorlevel 1 exit /b 0
python "%SCRIPT%"
exit /b %ERRORLEVEL%

:no_winget
echo [ERROR] winget was not found. Install Python 3.12 manually:
echo https://www.python.org/downloads/
pause
exit /b 1

:winget_failed
echo [ERROR] Could not install Python with winget.
echo [ERROR] Install Python 3.12 manually: https://www.python.org/downloads/
pause
exit /b 1
