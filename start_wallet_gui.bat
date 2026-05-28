@echo off
setlocal enableextensions
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "SCRIPT=wallet_recovery_gui_final.py"
if not exist "%SCRIPT%" (
  echo [ERROR] Не найден %SCRIPT% в %CD%
  pause
  exit /b 1
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3.12 -V >nul 2>nul
  if %ERRORLEVEL%==0 (
    echo [INFO] Запуск через py -3.12
    py -3.12 "%SCRIPT%"
    exit /b %ERRORLEVEL%
  )
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python -V >nul 2>nul
  if %ERRORLEVEL%==0 (
    echo [INFO] Запуск через python
    python "%SCRIPT%"
    exit /b %ERRORLEVEL%
  )
)

echo [WARN] Python не найден. Пытаюсь установить Python 3.12 через winget...
where winget >nul 2>nul
if not %ERRORLEVEL%==0 (
  echo [ERROR] winget не найден. Установите Python 3.12 вручную: https://www.python.org/downloads/
  pause
  exit /b 1
)

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if not %ERRORLEVEL%==0 (
  echo [ERROR] Не удалось установить Python через winget.
  pause
  exit /b 1
)

echo [INFO] Повторный запуск...
py -3.12 "%SCRIPT%"
if %ERRORLEVEL%==0 exit /b 0
python "%SCRIPT%"
exit /b %ERRORLEVEL%
