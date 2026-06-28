@echo off
chcp 65001 >nul
echo ============================================
echo   Smart Home Gateway - 打包为 EXE
echo ============================================
echo.

cd /d "%~dp0"

REM 1. 安装依赖
echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
echo.

REM 2. 清理旧构建
echo [2/3] 清理旧构建...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /q "*.spec"
echo.

REM 3. 打包
echo [3/3] 开始 PyInstaller 打包...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name=SmartHomeGateway ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=paho.mqtt.client ^
    --hidden-import=serial ^
    --hidden-import=serial.tools.list_ports ^
    --hidden-import=config ^
    --hidden-import=state ^
    --hidden-import=mac_registry ^
    --hidden-import=mqtt_client ^
    --hidden-import=serial_reader ^
    --hidden-import=serial_writer ^
    --hidden-import=serial_parser ^
    gui.py

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   打包成功!
    echo   输出: dist\SmartHomeGateway.exe
    echo ============================================
) else (
    echo.
    echo ============================================
    echo   打包失败,请检查错误信息
    echo ============================================
)

pause
