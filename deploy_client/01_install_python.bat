@echo off
setlocal
rem 01 - 静默安装 Python 到 C:\HwishAI\Python312（需管理员权限）
set "PKG=%~dp0"
set "TARGET=C:\HwishAI"
set "PY=%TARGET%\Python312\python.exe"
set "INSTALLER=%PKG%vendor\python\python-3.12.10-amd64.exe"

if not exist "%INSTALLER%" (
    echo [ERROR] Python installer missing: %INSTALLER%
    echo Run 00_prepare_vendor.ps1 on the vendor machine first.
    pause
    exit /b 1
)

rem 已存在时校验版本号，避免同名旧版/被替换文件被误当已安装
"%PY%" --version > "%TEMP%\hwai_pyver.txt" 2>&1
if not errorlevel 1 (
    findstr /C:"3.12" "%TEMP%\hwai_pyver.txt" >nul
    if not errorlevel 1 (
        echo [SKIP] Python 3.12 already installed: %PY%
        del "%TEMP%\hwai_pyver.txt" >nul 2>&1
        exit /b 0
    )
    echo [WARN] %PY% exists but is not 3.12, reinstalling ...
)
del "%TEMP%\hwai_pyver.txt" >nul 2>&1

echo Installing Python to %TARGET%\Python312 ...
"%INSTALLER%" /quiet InstallAllUsers=1 PrependPath=0 Include_test=0 Include_launcher=0 TargetDir="%TARGET%\Python312"
if errorlevel 1 (
    echo [ERROR] Python installer failed (exit code %errorlevel%).
    pause
    exit /b 1
)
if not exist "%PY%" (
    echo [ERROR] Python install failed. Check admin rights / installer.
    pause
    exit /b 1
)
echo [OK] Python installed.
