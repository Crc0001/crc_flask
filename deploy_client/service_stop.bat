@echo off
rem 停止服务（维护用）
set "NSSM=%~dp0vendor\nssm\nssm.exe"
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe missing: %NSSM%
    pause
    exit /b 1
)
"%NSSM%" status HwishAIStrain >nul 2>&1
if errorlevel 1 (
    echo [SKIP] Service HwishAIStrain does not exist.
    pause
    exit /b 0
)
"%NSSM%" stop HwishAIStrain
if errorlevel 1 (
    echo [ERROR] Failed to stop service.
    pause
    exit /b 1
)
echo Service stopped.
pause
