@echo off
echo ========================================
echo   WSN-Gateway Vision Dependencies Installer
echo ========================================
echo.
echo This script installs Yolo vision dependencies.
echo These are NOT bundled in WSN-Gateway.exe to keep it lightweight.
echo.
echo Installing:
echo   - ultralytics (YOLO26 detection)
echo   - insightface (face recognition)
echo   - onnxruntime (CPU inference engine)
echo   - opencv-python-headless (image processing)
echo.
echo NOTE: For GPU support, replace onnxruntime with onnxruntime-gpu
echo       and install CUDA toolkit separately.
echo.

python -m pip install ultralytics>=8.3.0 insightface>=0.7.3 onnxruntime>=1.18.0 opencv-python-headless>=4.9.0
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Vision dependency install failed.
    echo        Please check your Python/pip environment and retry.
    pause
    exit /b 1
)
echo.
echo Vision dependencies installed successfully.
echo Yolo detection and face recognition are now available.
echo.
pause
