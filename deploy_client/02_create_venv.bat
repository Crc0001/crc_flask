@echo off
setlocal
rem 02 - 创建虚拟环境并离线安装依赖（不联网）
set "PKG=%~dp0"
set "TARGET=C:\HwishAI"
set "PY=%TARGET%\Python312\python.exe"
set "VENV=%TARGET%\venv\Scripts\python.exe"
set "WHEELS=%PKG%vendor\wheels"

if not exist "%PY%" (
    echo [ERROR] Python not found. Run 01_install_python.bat first.
    pause
    exit /b 1
)
if not exist "%WHEELS%" (
    echo [ERROR] Offline wheels missing: %WHEELS%
    echo Run 00_prepare_vendor.ps1 on the vendor machine first.
    pause
    exit /b 1
)

if not exist "%VENV%" (
    echo Creating venv at %TARGET%\venv ...
    "%PY%" -m venv "%TARGET%\venv"
)

echo Installing dependencies (offline) ...
"%VENV%" -m pip install --no-index --find-links "%WHEELS%" -r "%PKG%requirements-client.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
echo [OK] venv ready.
