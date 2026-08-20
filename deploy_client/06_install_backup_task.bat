@echo off
setlocal
rem 06 - Register daily DB backup task (02:30, silent via pythonw) and run one now.
set "TARGET=C:\HwishAI"

rem /RU SYSTEM：任务以 SYSTEM 运行（即使无人登录也执行）；备份目录随后收紧 ACL
schtasks /Create /F /TN "HwishAIDbBackup" /TR "\"%TARGET%\venv\Scripts\pythonw.exe\" \"%TARGET%\backup_db.py\"" /SC DAILY /ST 02:30 /RU SYSTEM /RL HIGHEST
if errorlevel 1 (
    echo [ERROR] Failed to create scheduled task. Run as Administrator.
    pause
    exit /b 1
)

echo Running one backup now to verify ...
"%TARGET%\venv\Scripts\python.exe" "%TARGET%\backup_db.py"
if errorlevel 1 (
    echo [ERROR] Backup failed. Check %TARGET%\backups\backup.log
    pause
    exit /b 1
)

rem 备份含全部业务数据与口令哈希：目录仅 Administrators / SYSTEM 可访问
icacls "%TARGET%\backups" /inheritance:r /grant:r Administrators:F SYSTEM:F /Q >nul
if errorlevel 1 (
    echo [WARN] Failed to tighten ACL on %TARGET%\backups - please set manually.
)

echo.
echo [OK] Daily backup registered (Task: HwishAIDbBackup, 02:30 every day, runs as SYSTEM).
echo      Backups: %TARGET%\backups\  (keep 30 days, log: backup.log, restricted ACL)
pause
