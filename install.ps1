# ============================================================
#  NetQuick - Quick installer (downloads the .exe)
#  Usage:  irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install.ps1 | iex
# ============================================================
$ErrorActionPreference = "Stop"

$repo    = "devmaiter/NetQuick"
$dest    = "$env:LOCALAPPDATA\NetQuick"
$exePath = "$dest\NetQuick.exe"

Write-Host ""
Write-Host "  NetQuick - Quick installer" -ForegroundColor Cyan
Write-Host "  Switch fast, stress-free." -ForegroundColor DarkGray
Write-Host ""

# 1) Installation folder
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# 2) Find the .exe of the latest Release on GitHub
Write-Host "  Looking for the latest version..." -ForegroundColor Gray
try {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ "User-Agent" = "NetQuick-Installer" }
} catch {
    throw "Could not query GitHub. Check your internet connection."
}

$asset = $release.assets | Where-Object { $_.name -like "*.exe" } | Select-Object -First 1
if (-not $asset) {
    throw "No .exe found in the latest release of $repo. Upload NetQuick.exe to Releases."
}

# 3) Download
$sizeMB = [math]::Round($asset.size / 1MB, 1)
Write-Host "  Downloading $($asset.name) ($sizeMB MB)..." -ForegroundColor Gray
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exePath -UseBasicParsing

# 4) Desktop shortcut
$desktop = [Environment]::GetFolderPath("Desktop")
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$desktop\NetQuick.lnk")
$lnk.TargetPath       = $exePath
$lnk.WorkingDirectory = $dest
$lnk.Description       = "NetQuick - Network configurator"
$lnk.Save()

# 5) Add to the user PATH so you can type "netquick"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
}

Write-Host ""
Write-Host "  Installed at: $exePath" -ForegroundColor Green
Write-Host ""
Write-Host "  How to open it:" -ForegroundColor White
Write-Host "   - Double-click the Desktop shortcut, or" -ForegroundColor Gray
Write-Host "   - Open a NEW terminal and type: netquick" -ForegroundColor Gray
Write-Host ""
Write-Host "  Remember: run it as Administrator to change the network." -ForegroundColor Yellow
Write-Host ""
