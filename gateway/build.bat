@echo off
echo ========================================
echo   WSN-Gateway EXE Build Script
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Installing dependencies...
python -m pip install paho-mqtt pyserial pywebview pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] Dependency install failed. Will try to continue with existing deps.
    echo        If build fails, run manually:
    echo        python -m pip install paho-mqtt pyserial pywebview pyinstaller
    echo.
)
echo Dependencies check done.
echo.

echo [2/3] PyInstaller build (single file)...
set ICON=--icon "assets/icon.ico"
python -m PyInstaller -F -w ^
  --name "WSN-Gateway" ^
  %ICON% ^
  --hidden-import paho.mqtt.client ^
  --hidden-import serial.tools.list_ports_common ^
  --hidden-import cffi ^
  --collect-all webview ^
  --add-data "gui_app.html;." ^
  --clean ^
  --noconfirm ^
  gui_web.py

if %ERRORLEVEL% NEQ 0 (
    echo Build failed.
    pause
    exit /b 1
)
echo.
echo [3/3] Build complete!
echo.
echo ========================================
echo   Output: dist\WSN-Gateway.exe
echo ========================================
echo.
echo Copy WSN-Gateway.exe to any folder and double-click to run.
echo gw_uuid.txt and gateway.ini will be auto-generated next to the exe.
echo.
pause
