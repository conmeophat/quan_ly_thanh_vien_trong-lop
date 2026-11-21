[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Chua co virtual environment. Chay setup_standby.ps1 truoc."
}
if (-not (Test-Path (Join-Path $RepoRoot ".env"))) {
    throw "Chua co .env. Chay setup_standby.ps1 truoc."
}

Push-Location $RepoRoot
try {
    Write-Host "Class Merit Hub dang chay tai http://127.0.0.1:8080"
    Write-Host "Nhan Ctrl+C de dung."
    & $VenvPython main.py
    if ($LASTEXITCODE -ne 0) {
        throw "Ung dung ket thuc voi ma loi $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
