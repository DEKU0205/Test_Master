@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 (
  echo Не удалось открыть папку cdek-assistant.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(int(sys.version_info[:2] < (3,12)))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(int(sys.version_info[:2] < (3,12)))" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.12 или новее не найден.
echo Установите Python с https://www.python.org/downloads/windows/
echo При установке отметьте Add python.exe to PATH. Перезапустите VS Code.
pause
exit /b 1
:use_py
py -3 -X utf8 -u "%~dp0start.py" %*
goto finished
:use_python
python -X utf8 -u "%~dp0start.py" %*
:finished
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" pause
exit /b %APP_EXIT%
