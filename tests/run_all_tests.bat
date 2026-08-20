@echo off
rem Run ALL tests: vendor mode + client mode
setlocal
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "ROOT=%~dp0.."

echo ============================================
echo [1/2] vendor mode tests
echo ============================================
set "HWISHAI_APP_ROLE=vendor"
"%PY%" -m pytest "%ROOT%\tests" -m "not client" -q
set "R1=%ERRORLEVEL%"

echo.
echo ============================================
echo [2/2] client mode tests
echo ============================================
set "HWISHAI_APP_ROLE=client"
"%PY%" -m pytest "%ROOT%\tests" -m "client" -q
set "R2=%ERRORLEVEL%"

echo.
echo ============================================
echo vendor result: %R1%    client result: %R2%
echo ============================================
if not "%R1%"=="0" exit /b 1
if not "%R2%"=="0" exit /b 1
