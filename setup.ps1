# ============================================================
#  NetQuick - Development setup (repo already cloned)
#  Usage (inside the repo folder):  .\setup.ps1
#
#  Installs the dependencies and leaves NetQuick ready to run
#  from source.
# ============================================================
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  NetQuick - Development setup" -ForegroundColor Cyan
Write-Host ""

# 1) Detect Python
$py = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $py = $cmd; break }
}
if (-not $py) {
    throw "Python not found. Install Python 3.8+ from python.org and retry."
}
Write-Host "  Python detected ($py)." -ForegroundColor Green

# 2) Install dependencies
if (-not (Test-Path ".\requirements.txt")) {
    throw "requirements.txt not found. Run this script inside the repo folder."
}
Write-Host "  Installing dependencies..." -ForegroundColor Gray
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

Write-Host ""
Write-Host "  Done. To run NetQuick:" -ForegroundColor Green
Write-Host "     double-click NetQuick.vbs      (no console window)" -ForegroundColor Gray
Write-Host "     or:  pythonw netquick.py" -ForegroundColor Gray
Write-Host ""
