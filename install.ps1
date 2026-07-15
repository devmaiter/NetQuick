# ============================================================
#  NetQuick - Instalador rapido (descarga el .exe)
#  Uso:  irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install.ps1 | iex
# ============================================================
$ErrorActionPreference = "Stop"

$repo    = "devmaiter/NetQuick"
$dest    = "$env:LOCALAPPDATA\NetQuick"
$exePath = "$dest\NetQuick.exe"

Write-Host ""
Write-Host "  NetQuick - Instalador rapido" -ForegroundColor Cyan
Write-Host "  Cambia rapido, sin estresarte." -ForegroundColor DarkGray
Write-Host ""

# 1) Carpeta de instalacion
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# 2) Buscar el .exe del ultimo Release en GitHub
Write-Host "  Buscando la ultima version..." -ForegroundColor Gray
try {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ "User-Agent" = "NetQuick-Installer" }
} catch {
    throw "No se pudo consultar GitHub. Revisa tu conexion a internet."
}

$asset = $release.assets | Where-Object { $_.name -like "*.exe" } | Select-Object -First 1
if (-not $asset) {
    throw "No se encontro un .exe en el ultimo release de $repo. Sube NetQuick.exe a Releases."
}

# 3) Descargar
$sizeMB = [math]::Round($asset.size / 1MB, 1)
Write-Host "  Descargando $($asset.name) ($sizeMB MB)..." -ForegroundColor Gray
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exePath -UseBasicParsing

# 4) Acceso directo en el Escritorio
$desktop = [Environment]::GetFolderPath("Desktop")
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$desktop\NetQuick.lnk")
$lnk.TargetPath       = $exePath
$lnk.WorkingDirectory = $dest
$lnk.Description       = "NetQuick - Configurador de red"
$lnk.Save()

# 5) Anadir al PATH del usuario para poder escribir "netquick"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
}

Write-Host ""
Write-Host "  Instalado en: $exePath" -ForegroundColor Green
Write-Host ""
Write-Host "  Como abrirlo:" -ForegroundColor White
Write-Host "   - Doble clic en el acceso directo del Escritorio, o" -ForegroundColor Gray
Write-Host "   - Abre una terminal NUEVA y escribe: netquick" -ForegroundColor Gray
Write-Host ""
Write-Host "  Recuerda: ejecutalo como Administrador para cambiar la red." -ForegroundColor Yellow
Write-Host ""
