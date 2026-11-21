[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RemotePath,
    [string]$BackupDirectory = (Join-Path $env:LOCALAPPDATA "ClassMeritHub\backups"),
    [string]$TaskName = "ClassMeritHub-BackupSync",
    [string]$RunAt = "04:00"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($RemotePath.Contains('"')) { throw 'RemotePath khong duoc chua dau ngoac kep.' }
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    throw "Cai rclone va chay rclone config truoc khi tao Scheduled Task."
}

$TaskScript = Join-Path $PSScriptRoot "sync_backup.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$RunTime = [datetime]::Today.Add([timespan]::Parse($RunAt))
$Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -RemotePath "{1}" -BackupDirectory "{2}"' -f $TaskScript, $RemotePath, $BackupDirectory

$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $Arguments -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Download and SHA-256 verify the latest encrypted Class Merit Hub backup." -Force | Out-Null
Write-Host "Da tao Scheduled Task: $TaskName"
Write-Host "Chay moi ngay luc $RunAt theo gio Windows."
Write-Host "May tinh can bat va tai khoan hien tai can dang nhap."
