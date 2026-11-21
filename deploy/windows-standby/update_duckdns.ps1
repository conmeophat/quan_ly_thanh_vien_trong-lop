[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]$')]
    [string]$Subdomain
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Write-Warning "Chi chay khi da quyet dinh chuyen website tu Oracle sang may Windows."
Write-Warning "Neu VM Oracle con hoat dong, hay dung DuckDNS timer tren Oracle truoc."

$SecureToken = Read-Host "Nhap DuckDNS token (ky tu se duoc an)" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
try {
    $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
    $EncodedDomain = [Uri]::EscapeDataString($Subdomain)
    $EncodedToken = [Uri]::EscapeDataString($Token)
    $RequestUri = "https://www.duckdns.org/update?domains=$EncodedDomain&token=$EncodedToken&verbose=true"
    $Response = (Invoke-RestMethod -Uri $RequestUri -Method Get -TimeoutSec 20).ToString().Trim()
    if (-not $Response.StartsWith("OK")) {
        throw "DuckDNS khong xac nhan cap nhat: $Response"
    }
    Write-Host "DuckDNS da chap nhan cap nhat IP cong khai cua mang hien tai."
    Write-Host "Script khong luu token vao file."
}
finally {
    if ($Bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    $Token = $null
}
