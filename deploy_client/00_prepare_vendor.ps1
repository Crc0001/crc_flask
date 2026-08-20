# Run once on the VENDOR machine: download Python installer, NSSM and offline wheels into vendor\.
# After this, the whole deploy_client folder can be copied to the client machine for offline install.
# Security: every downloaded binary is verified against a pinned SHA256 before use.
$ErrorActionPreference = "Stop"
# PowerShell 7.3+: make native command failures trigger Stop; older PS ignores this variable,
# so explicit $LASTEXITCODE checks below are the real guard.
$PSNativeCommandUseErrorActionPreference = $true

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendor = Join-Path $root "vendor"
$pyDir = Join-Path $vendor "python"
$nssmDir = Join-Path $vendor "nssm"
$wheelDir = Join-Path $vendor "wheels"
$tempPy = Join-Path $vendor "py312"

New-Item -ItemType Directory -Force -Path $pyDir, $nssmDir, $wheelDir | Out-Null

$pythonVersion = "3.12.10"
$pyInstaller = Join-Path $pyDir "python-$pythonVersion-amd64.exe"
$pySha256 = "67B5635E80EA51072B87941312D00EC8927C4DB9BA18938F7AD2D27B328B95FB"
$nssmSha256 = "727D1E42275C605E0F04ABA98095C38A8E1E46DEF453CDFFCE42869428AA6743"

function Assert-Hash($Path, $Expected, $Name) {
    if (-not (Test-Path $Path)) { throw "$Name missing: $Path" }
    $actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) {
        throw "$Name SHA256 mismatch. Expected $Expected, got $actual. Delete the file and re-run."
    }
}

# 1) Python installer (silent install on client)
if (-not (Test-Path $pyInstaller)) {
    Write-Host "Downloading Python $pythonVersion installer ..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe" -OutFile $pyInstaller
} else {
    Write-Host "[skip] Python installer exists"
}
Assert-Hash $pyInstaller $pySha256 "Python installer"

# 2) NSSM (Windows service helper)
if (-not (Test-Path (Join-Path $nssmDir "nssm.exe"))) {
    Write-Host "Downloading NSSM 2.24 ..."
    $zip = Join-Path $env:TEMP "nssm-2.24.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    Assert-Hash $zip $nssmSha256 "NSSM zip"
    $extract = Join-Path $env:TEMP "nssm_extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract
    Copy-Item (Join-Path $extract "nssm-2.24\win64\nssm.exe") (Join-Path $nssmDir "nssm.exe")
    if (-not (Test-Path (Join-Path $nssmDir "nssm.exe"))) { throw "NSSM extraction failed" }
} else {
    Write-Host "[skip] NSSM exists"
}

# 3) Download offline wheels using the exact Python version the client will run
if (-not (Test-Path (Join-Path $tempPy "python.exe"))) {
    Write-Host "Unpacking Python to vendor\py312 (to fetch matching wheels) ..."
    Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0", "Include_launcher=0", "TargetDir=$tempPy" -Wait
    if (-not (Test-Path (Join-Path $tempPy "python.exe"))) { throw "Python unpack failed" }
}
Write-Host "Downloading offline wheels (requirements-client.txt) ..."
& (Join-Path $tempPy "python.exe") -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed (exit $LASTEXITCODE)" }
& (Join-Path $tempPy "python.exe") -m pip download `
    -r (Join-Path (Split-Path -Parent $root) "requirements-client.txt") `
    -d $wheelDir --only-binary=:all:
if ($LASTEXITCODE -ne 0) { throw "pip download failed (exit $LASTEXITCODE)" }

$wheelCount = (Get-ChildItem $wheelDir -Filter *.whl -ErrorAction SilentlyContinue).Count
if ($wheelCount -eq 0) { throw "No wheels downloaded - requirements-client.txt may be broken" }

Write-Host ""
Write-Host "[done] vendor ready:"
Write-Host "  python\  Python installer (SHA256 verified)"
Write-Host "  nssm\    nssm.exe (SHA256 verified)"
Write-Host ("  wheels\  offline wheels: " + $wheelCount)
