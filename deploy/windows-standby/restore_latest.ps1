[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RemotePath,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$AgeIdentity,

    [string]$DatabasePath = "",

    [string]$BackupDirectory = (Join-Path $env:LOCALAPPDATA "ClassMeritHub\backups")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$SqliteTools = Join-Path $PSScriptRoot "sqlite_tools.py"
$SyncScript = Join-Path $PSScriptRoot "sync_backup.ps1"

if ([string]::IsNullOrWhiteSpace($DatabasePath)) {
    $DatabasePath = Join-Path $RepoRoot "data\class_tracker.sqlite3"
}
$DatabasePath = [System.IO.Path]::GetFullPath($DatabasePath)
$AgeIdentity = [System.IO.Path]::GetFullPath($AgeIdentity)

if (-not (Test-Path $VenvPython)) { throw "Chay setup_standby.ps1 truoc." }
if (-not (Test-Path $AgeIdentity -PathType Leaf)) { throw "Khong tim thay age identity file. Kiem tra duong dan khoa giai ma." }
if (-not (Get-Command age -ErrorAction SilentlyContinue)) { throw "Khong tim thay age.exe trong PATH." }

$Listeners = @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)
if ($Listeners.Count -gt 0) {
    throw "Cong 8080 dang co tien trinh lang nghe. Dung website Windows truoc khi thay database."
}

Write-Host "[1/5] Dong bo va xac minh ban backup ma hoa..."
& $SyncScript -RemotePath $RemotePath -BackupDirectory $BackupDirectory
if ($LASTEXITCODE -ne 0) { throw "Dong bo backup that bai." }

$LatestArchive = Get-ChildItem -LiteralPath $BackupDirectory -Filter "class-merit-*.sqlite3.gz.age" -File |
    Sort-Object Name -Descending |
    Select-Object -First 1
if (-not $LatestArchive) { throw "Khong co file backup local." }

$ChecksumPath = "$($LatestArchive.FullName).sha256"
$ExpectedHash = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$ActualHash = (Get-FileHash -LiteralPath $LatestArchive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedHash -ne $ActualHash) { throw "Checksum thay doi sau khi tai; dung phuc hoi." }

$WorkDirectory = Join-Path $env:TEMP ("ClassMeritRestore-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null
$GzipPath = Join-Path $WorkDirectory "database.sqlite3.gz"
$RestoredDatabase = Join-Path $WorkDirectory "restored.sqlite3"

try {
    Write-Host "[2/5] Giai ma age..."
    & age -d -i $AgeIdentity -o $GzipPath $LatestArchive.FullName
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $GzipPath -PathType Leaf)) {
        throw "Giai ma that bai. Khoa age co the khong khop voi backup."
    }

    Write-Host "[3/5] Giai nen va kiem tra SQLite..."
    $InputStream = [System.IO.File]::OpenRead($GzipPath)
    try {
        $GzipStream = New-Object System.IO.Compression.GzipStream(
            $InputStream,
            [System.IO.Compression.CompressionMode]::Decompress
        )
        try {
            $OutputStream = [System.IO.File]::Create($RestoredDatabase)
            try { $GzipStream.CopyTo($OutputStream) }
            finally { $OutputStream.Dispose() }
        }
        finally { $GzipStream.Dispose() }
    }
    finally { $InputStream.Dispose() }

    & $VenvPython $SqliteTools validate $RestoredDatabase
    if ($LASTEXITCODE -ne 0) { throw "Backup khong qua SQLite integrity/schema validation." }

    Write-Host "[4/5] Tao snapshot database cu (neu co)..."
    $DatabaseDirectory = Split-Path -Parent $DatabasePath
    New-Item -ItemType Directory -Force -Path $DatabaseDirectory | Out-Null
    $PreviousSnapshot = ""
    if (Test-Path $DatabasePath -PathType Leaf) {
        $PreviousSnapshot = "$DatabasePath.pre-restore.$(Get-Date -Format yyyyMMddTHHmmss)"
        & $VenvPython $SqliteTools snapshot $DatabasePath $PreviousSnapshot
        if ($LASTEXITCODE -ne 0) { throw "Khong tao duoc snapshot database cu; tu choi thay the." }
    }

    Write-Host "[5/5] Thay database du phong..."
    $NewDatabasePath = "$DatabasePath.restore-new"
    Copy-Item -LiteralPath $RestoredDatabase -Destination $NewDatabasePath -Force
    try {
        Move-Item -LiteralPath $NewDatabasePath -Destination $DatabasePath -Force
    }
    catch {
        Remove-Item -LiteralPath $NewDatabasePath -Force -ErrorAction SilentlyContinue
        throw
    }
    Remove-Item -LiteralPath "$DatabasePath-wal", "$DatabasePath-shm" -Force -ErrorAction SilentlyContinue

    & $VenvPython $SqliteTools validate $DatabasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Database sau khi thay the khong qua kiem tra. Snapshot cu duoc giu neu co: $PreviousSnapshot"
    }

    Write-Host "PHUC HOI THANH CONG."
    Write-Host "Backup: $($LatestArchive.Name)"
    Write-Host "Database: $DatabasePath"
    if ($PreviousSnapshot) { Write-Host "Snapshot truoc phuc hoi: $PreviousSnapshot" }
    Write-Host "Khoi dong website bang run_standby.ps1 va kiem tra /healthz."
}
finally {
    Remove-Item -LiteralPath $WorkDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
