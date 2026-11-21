$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Da tao file .env." -ForegroundColor Yellow
    Write-Host "Hay mo .env, thay NICEGUI_STORAGE_SECRET va BOOTSTRAP_TOKEN bang hai chuoi ngau nhien khac nhau, sau do chay lai run.ps1." -ForegroundColor Yellow
    exit 1
}

py main.py
