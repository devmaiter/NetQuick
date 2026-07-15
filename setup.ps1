# ============================================================
#  NetQuick - Setup para desarrollo (repo ya clonado)
#  Uso (dentro de la carpeta del repo):  .\setup.ps1
#
#  Instala las dependencias y deja NetQuick listo para ejecutar
#  desde el codigo fuente.
# ============================================================
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  NetQuick - Setup de desarrollo" -ForegroundColor Cyan
Write-Host ""

# 1) Detectar Python
$py = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $py = $cmd; break }
}
if (-not $py) {
    throw "Python no encontrado. Instala Python 3.8+ desde python.org y reintenta."
}
Write-Host "  Python detectado ($py)." -ForegroundColor Green

# 2) Instalar dependencias
if (-not (Test-Path ".\requirements.txt")) {
    throw "No se encontro requirements.txt. Ejecuta este script dentro de la carpeta del repo."
}
Write-Host "  Instalando dependencias..." -ForegroundColor Gray
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

Write-Host ""
Write-Host "  Listo. Para ejecutar NetQuick:" -ForegroundColor Green
Write-Host "     doble clic en NetQuick.vbs      (sin ventana de consola)" -ForegroundColor Gray
Write-Host "     o bien:  pythonw netquick.py" -ForegroundColor Gray
Write-Host ""
