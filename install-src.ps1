# ============================================================
#  NetQuick - Instalador desde codigo fuente (Python + deps)
#  Uso:  irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install-src.ps1 | iex
#
#  Instala Python (via winget si falta), las dependencias, y
#  descarga los archivos de NetQuick. No requiere generar un .exe.
# ============================================================
$ErrorActionPreference = "Stop"

$repo   = "devmaiter/NetQuick"
$branch = "main"
$dest   = "$env:LOCALAPPDATA\NetQuick"
$files  = @("netquick.py", "netops.py", "requirements.txt")

Write-Host ""
Write-Host "  NetQuick - Instalacion desde fuente" -ForegroundColor Cyan
Write-Host ""

# 1) Asegurar Python
function Test-Python {
    foreach ($cmd in @("python", "py")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) { return $cmd }
    }
    return $null
}

$py = Test-Python
if (-not $py) {
    Write-Host "  Python no encontrado. Instalando con winget..." -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget no esta disponible. Instala Python 3.8+ manualmente desde python.org y reintenta."
    }
    winget install -e --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
    Write-Host "  Python instalado. IMPORTANTE: cierra y abre una terminal NUEVA, luego reejecuta este comando." -ForegroundColor Yellow
    return
}
Write-Host "  Python detectado ($py)." -ForegroundColor Green

# 2) Carpeta destino y descarga de archivos
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$base = "https://raw.githubusercontent.com/$repo/$branch"
foreach ($f in $files) {
    Write-Host "  Descargando $f..." -ForegroundColor Gray
    Invoke-WebRequest -Uri "$base/$f" -OutFile "$dest\$f" -UseBasicParsing
}

# 3) Instalar dependencias
Write-Host "  Instalando dependencias..." -ForegroundColor Gray
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r "$dest\requirements.txt"

# 4) Lanzadores con la ruta REAL de pythonw.exe (no dependen del PATH).
#    "pythonw" a secas falla silencioso si el equipo tiene "py" pero no
#    "pythonw" en el PATH (issue #12).
$realPy  = (& $py -c "import sys; print(sys.executable)").Trim()
$pythonw = Join-Path (Split-Path $realPy) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $realPy }  # ultimo recurso: con consola

$launcher = "$dest\netquick.cmd"
"@echo off`r`nstart `"`" `"$pythonw`" `"$dest\netquick.py`" %*" | Set-Content -Path $launcher -Encoding ASCII

# Lanzador .vbs de doble clic, generado con rutas absolutas
$vbsContent = @"
' Lanzador generado por install-src.ps1 (rutas absolutas, no depende del PATH)
Set sh = CreateObject("WScript.Shell")
sh.Run """$pythonw"" ""$dest\netquick.py""", 0, False
"@
Set-Content -Path "$dest\NetQuick.vbs" -Value $vbsContent -Encoding ASCII

# 5) Anadir al PATH del usuario
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
}

Write-Host ""
Write-Host "  Instalado en: $dest" -ForegroundColor Green
Write-Host "  Abre una terminal NUEVA y escribe: netquick" -ForegroundColor White
Write-Host "  (ejecutala como Administrador para cambiar la red)" -ForegroundColor Yellow
Write-Host ""
