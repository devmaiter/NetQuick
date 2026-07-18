# ============================================================
#  NetQuick - Desinstalador
#  Uso:  irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/uninstall.ps1 | iex
#
#  Revierte todo lo que tocan install.ps1 / install-src.ps1 y la propia app:
#  archivos, PATH, acceso directo, inicio con Windows (tarea programada y
#  .vbs de Startup), regla de firewall y datos del usuario (perfiles).
# ============================================================
$ErrorActionPreference = "SilentlyContinue"

$dest    = "$env:LOCALAPPDATA\NetQuick"
$datos   = "$env:APPDATA\NetQuick"
$lnk     = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetQuick.lnk"
$vbsStart = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\NetQuick.vbs"

Write-Host ""
Write-Host "  NetQuick - Desinstalador" -ForegroundColor Cyan
Write-Host ""

# 1) Cerrar la app si esta corriendo
Get-Process NetQuick -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

# 2) Inicio con Windows: tarea programada (modo .exe) y .vbs de Startup (modo fuente)
schtasks /Delete /TN NetQuick /F 2>$null | Out-Null
if (Test-Path $vbsStart) { Remove-Item $vbsStart -Force }

# 3) Regla de firewall creada por la app
netsh advfirewall firewall delete rule name=NetQuick | Out-Null

# 4) Acceso directo del Escritorio
if (Test-Path $lnk) { Remove-Item $lnk -Force }

# 5) Quitar la carpeta del PATH del usuario
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $nuevo = ($userPath -split ";" | Where-Object { $_ -and $_ -ne $dest }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $nuevo, "User")
}

# 6) Archivos de la aplicacion
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }

# 7) Datos del usuario (perfiles guardados)
if (Test-Path $datos) {
    $resp = Read-Host "  Borrar tambien los perfiles guardados? (s/N)"
    if ($resp -match "^[sS]") { Remove-Item $datos -Recurse -Force }
}

Write-Host ""
Write-Host "  NetQuick desinstalado." -ForegroundColor Green
Write-Host "  (abre una terminal NUEVA para que el PATH quede actualizado)" -ForegroundColor Gray
Write-Host ""
