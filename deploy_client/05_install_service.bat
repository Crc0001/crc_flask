@echo off
setlocal
rem 05 - Register Windows service via NSSM: auto-start on boot, restart on crash,
rem      open firewall port 8856, create desktop shortcut. (Run as Administrator)
set "PKG=%~dp0"
set "TARGET=C:\HwishAI"
set "VENV=%TARGET%\venv\Scripts\python.exe"
set "NSSM=%PKG%vendor\nssm\nssm.exe"
set "RUN=%TARGET%\run_client.py"
set "SVC=HwishAIStrain"

if not exist "%NSSM%" (
    echo [ERROR] nssm.exe missing: %NSSM%
    echo Run 00_prepare_vendor.ps1 on the vendor machine first.
    pause
    exit /b 1
)
if not exist "%VENV%" (
    echo [ERROR] venv missing. Run 02_create_venv.bat first.
    pause
    exit /b 1
)
if not exist "%RUN%" (
    echo [ERROR] run_client.py missing at %RUN%
    pause
    exit /b 1
)

rem --- create a low-privilege service account (security fix V-03: never run the web as SYSTEM) ---
set "SVCUSER=hwishai_svc"
set "SVCPWD="
for /f "delims=" %%p in ('powershell -NoProfile -Command "-join (1..24 | ForEach-Object { 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.Substring((Get-Random -Maximum 62), 1) })"') do set "SVCPWD=%%p"
if not defined SVCPWD (
    echo [ERROR] Failed to generate service account password.
    pause
    exit /b 1
)
net user %SVCUSER% >nul 2>&1
if errorlevel 1 (
    net user %SVCUSER% %SVCPWD% /add /passwordchg:no /expires:never /comment:"HwishAI service account" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to create service account %SVCUSER%. Check local password policy.
        pause
        exit /b 1
    )
) else (
    net user %SVCUSER% %SVCPWD% >nul 2>&1
)
rem remove the account from local Users group: service logon only, no interactive login
net localgroup Users %SVCUSER% /delete >nul 2>&1

"%NSSM%" status %SVC% >nul 2>&1
if not errorlevel 1 (
    echo [SKIP] Service %SVC% already exists, re-configuring ...
) else (
    "%NSSM%" install %SVC% "%VENV%" "%RUN%"
    if errorlevel 1 (
        echo [ERROR] nssm install failed.
        pause
        exit /b 1
    )
)

rem run the service as the low-privilege account instead of LocalSystem
"%NSSM%" set %SVC% ObjectName ".\%SVCUSER%" "%SVCPWD%" >nul
if errorlevel 1 (
    echo [ERROR] Failed to set service account %SVCUSER%.
    pause
    exit /b 1
)

rem grant the account access to the install dir (app writes logs/uploads/results/instance)
icacls "%TARGET%" /grant "%SVCUSER%:(OI)(CI)M" /T /Q >nul
rem instance\ holds secrets (SECRET_KEY, DB password, tokens): restrict to Admins/SYSTEM/service
icacls "%TARGET%\instance" /inheritance:r /grant:r Administrators:F SYSTEM:F "%SVCUSER%":(OI)(CI)M /Q >nul

mkdir "%TARGET%\logs" 2>nul
"%NSSM%" set %SVC% AppDirectory "%TARGET%"
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% DisplayName "HwishAI Strain Recognition System"
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% Description "HwishAI strain recognition client (local port 8856; recognition/knowledge via vendor API)"
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% Start SERVICE_AUTO_START
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppStdout "%TARGET%\logs\service.log"
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppStderr "%TARGET%\logs\service_err.log"
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppRotateFiles 1
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppRotateBytes 10485760
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppExit Default Restart
if errorlevel 1 goto setfail
"%NSSM%" set %SVC% AppRestartDelay 5000
if errorlevel 1 goto setfail

"%NSSM%" restart %SVC% >nul 2>&1
if errorlevel 1 (
    "%NSSM%" start %SVC%
    if errorlevel 1 goto startfail
)

rem firewall: allow LAN access on 8856
netsh advfirewall firewall show rule name="HwishAI 8856" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="HwishAI 8856" dir=in action=allow protocol=TCP localport=8856
    if errorlevel 1 (
        echo [WARN] Failed to add firewall rule - LAN clients may not connect.
    )
)

rem desktop shortcut: user just double-clicks to open the system
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AI_junzhong.url'); $s.TargetPath = 'http://127.0.0.1:8856/'; $s.Save()"
if errorlevel 1 (
    echo [WARN] Failed to create desktop shortcut (not critical).
)

echo.
echo [OK] Service installed and started (auto-start on boot, auto-restart on crash).
echo      Users: double-click desktop shortcut [AI_junzhong] to open the system.
echo      Local:  http://127.0.0.1:8856/     LAN:  http://<this-machine-IP>:8856/
pause
exit /b 0

:setfail
echo [ERROR] nssm set failed while configuring service.
pause
exit /b 1

:startfail
echo [ERROR] Failed to start service. Check %TARGET%\logs\service_err.log
pause
exit /b 1
