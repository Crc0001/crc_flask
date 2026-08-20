@echo off
rem 卸载服务（彻底移除开机自启；程序文件不删除）
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
"%NSSM%" stop HwishAIStrain >nul 2>&1
"%NSSM%" remove HwishAIStrain confirm
if errorlevel 1 (
    echo [ERROR] Failed to remove service.
    pause
    exit /b 1
)
echo Service removed.
pause
