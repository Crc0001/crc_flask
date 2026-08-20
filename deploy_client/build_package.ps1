# Run on the VENDOR machine: assemble client deploy package at dist\hwishai_client_deploy\
# Prereq: run 00_prepare_vendor.ps1 first (vendor\ = Python installer / NSSM / offline wheels).
$ErrorActionPreference = "Stop"
$deployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $deployDir
$dist = Join-Path $repo "dist\hwishai_client_deploy"

if (-not (Test-Path (Join-Path $deployDir "vendor\nssm\nssm.exe"))) {
    Write-Error "vendor folder not ready. Run deploy_client\00_prepare_vendor.ps1 first."
}

if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
New-Item -ItemType Directory -Force -Path $dist | Out-Null

Write-Host "Copying app code (excluding caches, upload/result dirs, model weights and vendor-only/dev-only files) ..."
robocopy (Join-Path $repo "app") (Join-Path $dist "app") /E /XD __pycache__ weights uploads results maldi_uploads maldi_results downloade /XF *.pyc jpg_blob.py recognition.py yolo_service.py | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Error "robocopy app failed" }

New-Item -ItemType Directory -Force -Path (Join-Path $dist "app\static\uploads"), (Join-Path $dist "app\static\results") | Out-Null

Write-Host "Copying entrypoint and requirements ..."
Copy-Item (Join-Path $repo "run_client.py") $dist
Copy-Item (Join-Path $repo "requirements-client.txt") $dist

Write-Host "Copying deploy scripts, empty-db SQL and checklist ..."
foreach ($name in @("01_install_python.bat", "02_create_venv.bat", "03_init_mysql.py",
                    "04_configure.py", "05_install_service.bat", "06_install_backup_task.bat",
                    "backup_db.py", "service_stop.bat",
                    "service_uninstall.bat", "init_empty_db.sql")) {
    Copy-Item (Join-Path $deployDir $name) $dist
}
Copy-Item (Join-Path $deployDir "CHK_DEPLOY.md") $dist

Write-Host "Copying vendor payloads ..."
robocopy (Join-Path $deployDir "vendor") (Join-Path $dist "vendor") /E /XD py312 | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Error "robocopy vendor failed" }

$sizeMB = [math]::Round(((Get-ChildItem $dist -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host ""
Write-Host "[done] Deploy package: $dist  (about $sizeMB MB)"
Write-Host "No model / no knowledge data inside. Copy to client machine and follow CHK_DEPLOY.md."
