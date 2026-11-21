[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RemotePath,
    [string]$BackupDirectory = (Join-Path $env:LOCALAPPDATA "ClassMeritHub\backups"),
    [ValidateRange(1, 365)]
    [int]$KeepLocalCopies = 30
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($RemotePath.Contains('"')) { throw 'RemotePath khong duoc chua dau ngoac kep.' }
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    throw "Khong tim thay rclone. Cai rclone va chay rclone config truoc."
}

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$LogFile = Join-Path $BackupDirectory "sync.log"

try {
    $RemoteFiles = @(& rclone lsf --files-only --max-depth 1 $RemotePath)
    if ($LASTEXITCODE -ne 0) {
        throw "Rclone khong liet ke duoc remote. Kiem tra remote/path va quyen truy cap."
    }

    $Candidates = @(
        $RemoteFiles |
            Where-Object { $_ -match '^class-merit-\d{8}T\d{6}Z\.sqlite3\.gz\.age$' } |
            Sort-Object -Descending
    )
    if ($Candidates.Count -eq 0) {
        throw "Khong tim thay backup Class Merit Hub tren remote."
    }

    $Latest = $Candidates[0]
    $ArchivePath = Join-Path $BackupDirectory $Latest
    $ChecksumPath = "$ArchivePath.sha256"
    $RemoteBase = $RemotePath.TrimEnd('/')

    & rclone copyto "$RemoteBase/$Latest" $ArchivePath --quiet
    if ($LASTEXITCODE -ne 0) { throw "Khong tai duoc file backup." }
    & rclone copyto "$RemoteBase/$Latest.sha256" $ChecksumPath --quiet
    if ($LASTEXITCODE -ne 0) { throw "Khong tai duoc file checksum." }

    $ExpectedHash = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $ActualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExpectedHash -notmatch '^[0-9a-f]{64}$' -or $ExpectedHash -ne $ActualHash) {
        Remove-Item -LiteralPath $ArchivePath, $ChecksumPath -Force -ErrorAction SilentlyContinue
        throw "Checksum khong khop. Tu choi su dung ban backup nay."
    }

    $OldArchives = @(
        Get-ChildItem -LiteralPath $BackupDirectory -Filter "class-merit-*.sqlite3.gz.age" -File |
            Sort-Object Name -Descending |
            Select-Object -Skip $KeepLocalCopies
    )
    foreach ($OldArchive in $OldArchives) {
        Remove-Item -LiteralPath $OldArchive.FullName -Force
        Remove-Item -LiteralPath "$($OldArchive.FullName).sha256" -Force -ErrorAction SilentlyContinue
    }

    Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) OK $Latest" -Encoding UTF8
    Write-Host "Da tai va xac minh SHA-256: $Latest"
    Write-Host "Thu muc backup: $BackupDirectory"
}
catch {
    Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) ERROR $($_.Exception.Message)" -Encoding UTF8
    throw
}
