[CmdletBinding()]
param([string]$PythonLauncher = "py")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$EnvFile = Join-Path $RepoRoot ".env"
$DataDirectory = Join-Path $RepoRoot "data"

if (-not (Get-Command $PythonLauncher -ErrorAction SilentlyContinue)) {
    throw "Khong tim thay Python launcher '$PythonLauncher'. Cai Python va bat Python Launcher."
}

Write-Host "[1/4] Kiem tra Python..."
& $PythonLauncher --version
if ($LASTEXITCODE -ne 0) { throw "Khong the chay Python." }

Write-Host "[2/4] Tao virtual environment..."
if (-not (Test-Path $VenvPython)) {
    & $PythonLauncher -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Khong tao duoc virtual environment." }
}

Write-Host "[3/4] Cai thu vien..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Khong cap nhat duoc pip." }
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Khong cai duoc dependencies." }

Write-Host "[4/4] Chuan bi cau hinh va thu muc du lieu..."
New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null
if (-not (Test-Path $EnvFile)) {
    $Secret = (& $VenvPython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    if ($LASTEXITCODE -ne 0 -or $Secret.Length -lt 32) {
        throw "Khong tao duoc NICEGUI_STORAGE_SECRET."
    }
    $EnvContent = @"
NICEGUI_STORAGE_SECRET=$Secret
COOKIE_SECURE=false
HOST=127.0.0.1
PORT=8080
DATABASE_PATH=data/class_tracker.sqlite3
"@
    Set-Content -LiteralPath $EnvFile -Value $EnvContent -Encoding ASCII
    Write-Host "Da tao .env rieng tren may nay. Khong dua file nay len GitHub."
}
else {
    Write-Host "Da co .env; giu nguyen secrets va cau hinh hien tai."
}

Write-Host ""
Write-Host "Da chuan bi moi truong Windows du phong."
Write-Host "Chay ung dung thu cong: .\deploy\windows-standby\run_standby.ps1"
