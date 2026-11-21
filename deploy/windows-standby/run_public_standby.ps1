[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.duckdns\.org$')]
    [string]$Domain,
    [string]$CaddyExe = "caddy"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not (Get-Command $CaddyExe -ErrorAction SilentlyContinue)) {
    throw "Khong tim thay caddy.exe. Cai Caddy va them vao PATH, hoac truyen -CaddyExe voi duong dan day du."
}

$ProgramDataDirectory = Join-Path $env:ProgramData "ClassMeritHub"
New-Item -ItemType Directory -Force -Path $ProgramDataDirectory | Out-Null
$Caddyfile = Join-Path $ProgramDataDirectory "Caddyfile"
$CaddyContent = @"
$Domain {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        X-Frame-Options DENY
        -Server
    }
}
"@
Set-Content -LiteralPath $Caddyfile -Value $CaddyContent -Encoding ASCII

Write-Host "Caddyfile: $Caddyfile"
Write-Host "Proxy HTTPS $Domain -> 127.0.0.1:8080"
Write-Host "DNS A record phai tro ve IP cong khai mang nha."
Write-Host "Router phai forward TCP 80 va 443 den may Windows; Windows Firewall cung phai cho phep."
Write-Host "Neu nha mang dung CGNAT hoac chan inbound, port forwarding se khong hoat dong."
Write-Host "Nhan Ctrl+C de dung Caddy."
& $CaddyExe run --config $Caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    throw "Caddy ket thuc voi ma loi $LASTEXITCODE."
}
