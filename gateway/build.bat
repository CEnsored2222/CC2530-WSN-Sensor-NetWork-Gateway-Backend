@echo off
echo ========================================
echo   WSN-Gateway EXE Build Script
echo ========================================
echo.

cd /d "%~dp0"

echo [0/5] Checking running instances...

taskkill /f /im WSN-Gateway.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 echo   Terminated: WSN-Gateway.exe

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -like '*gui_web.py*'} | ForEach-Object { Write-Host ('  Terminated: python.exe gui_web.py (PID=' + $_.ProcessId + ')'); Stop-Process -Id $_.ProcessId -Force }" 2>nul

echo.

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo [1/5] Installing core dependencies (vision deps installed separately)...
python -m pip install paho-mqtt pyserial pywebview numpy requests python-socketio pillow
python -m pip install pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] Dependency install failed. Will try to continue with existing deps.
    echo        If build fails, run manually:
    echo        python -m pip install paho-mqtt pyserial pywebview numpy requests python-socketio pillow
    echo        python -m pip install pyinstaller
    echo.
)
echo Core dependencies check done.
echo.
echo NOTE: Vision deps (ultralytics/insightface/onnxruntime/opencv) are NOT bundled.
echo       Embedded Python runtime is bundled for auto-extraction on first use.
echo.

echo [2/5] Building frontend...
cd frontend
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] npm install failed. Please install Node.js and retry.
    pause
    exit /b 1
)
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] npm run build failed.
    pause
    exit /b 1
)
cd ..
echo Frontend build done.
echo.

echo [3/5] PyInstaller build (single file)...
set ICON=--icon "assets/icon.ico"
python -m PyInstaller -F -w ^
  --name "WSN-Gateway" ^
  %ICON% ^
  --hidden-import paho.mqtt.client ^
  --hidden-import serial.tools.list_ports_common ^
  --hidden-import cffi ^
  --hidden-import numpy ^
  --collect-all webview ^
  --add-data "gui_app.html;." ^
  --add-data "frontend\dist;frontend\dist" ^
  --add-data "..\Yolo;Yolo" ^
  --add-data "python_embed\runtime;python_embed\runtime" ^
  --exclude-module torch ^
  --exclude-module torchvision ^
  --exclude-module ultralytics ^
  --exclude-module insightface ^
  --exclude-module onnxruntime ^
  --exclude-module cv2 ^
  --exclude-module matplotlib ^
  --exclude-module scipy ^
  --exclude-module pandas ^
  --exclude-module numba ^
  --clean ^
  --noconfirm ^
  gui_web.py

if %ERRORLEVEL% NEQ 0 (
    echo Build failed.
    pause
    exit /b 1
)
echo.
echo [4/5] Build complete!
echo.
echo ========================================
echo   Output: dist\WSN-Gateway.exe
echo ========================================
echo.
echo Copy WSN-Gateway.exe to any folder and double-click to run.
echo gw_uuid.txt and gateway.ini will be auto-generated in the selected DATA_DIR.
echo Embedded Python runtime will be auto-extracted on first use.
echo.
pause
