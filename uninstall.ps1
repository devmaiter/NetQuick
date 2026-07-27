# ============================================================
#  NetQuick - Uninstaller
#  Usage:  irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/uninstall.ps1 | iex
#
#  Reverts everything install.ps1 / install-src.ps1 and the app itself touch:
#  files, PATH, shortcut, start-with-Windows (scheduled task and Startup .vbs),
#  firewall rule and user data (profiles).
# ============================================================
$ErrorActionPreference = "SilentlyContinue"

$dest    = "$env:LOCALAPPDATA\NetQuick"
$data    = "$env:APPDATA\NetQuick"
$lnk     = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetQuick.lnk"
$vbsStart = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\NetQuick.vbs"

Write-Host ""
Write-Host "  NetQuick - Uninstaller" -ForegroundColor Cyan
Write-Host ""

# 1) Close the app if it's running
Get-Process NetQuick -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

# 2) Start with Windows: scheduled task (.exe mode) and Startup .vbs (source mode)
schtasks /Delete /TN NetQuick /F 2>$null | Out-Null
if (Test-Path $vbsStart) { Remove-Item $vbsStart -Force }

# 3) Firewall rule created by the app
netsh advfirewall firewall delete rule name=NetQuick | Out-Null

# 4) Desktop shortcut
if (Test-Path $lnk) { Remove-Item $lnk -Force }

# 5) Remove the folder from the user PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $new = ($userPath -split ";" | Where-Object { $_ -and $_ -ne $dest }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $new, "User")
}

# 6) Application files
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }

# 7) User data (saved profiles)
if (Test-Path $data) {
    $resp = Read-Host "  Also delete the saved profiles? (y/N)"
    if ($resp -match "^[yY]") { Remove-Item $data -Recurse -Force }
}

Write-Host ""
Write-Host "  NetQuick uninstalled." -ForegroundColor Green
Write-Host "  (open a NEW terminal so the PATH is refreshed)" -ForegroundColor Gray
Write-Host ""
