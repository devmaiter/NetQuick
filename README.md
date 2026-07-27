<div align="center">

<img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows"/>
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/Version-1.3.0--beta-orange?style=for-the-badge" alt="Version"/>
<img src="https://img.shields.io/badge/Estado-Beta%20%2F%20Demo%20en%20desarrollo-red?style=for-the-badge" alt="Estado"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>

<br/><br/>

# ⚡ NetQuick

### *Cambia rápido, sin estresarte.*

**NetQuick** es un widget flotante para Windows que vive en la bandeja del sistema y te deja cambiar la IP/red de tu máquina en segundos — sin abrir menús de Windows, sin memorizar comandos.

> ⚠️ **Versión beta / demo en desarrollo activo.** Funciona y se usa a diario, pero puede cambiar sin aviso y contener errores.

</div>

---

## 🚀 Cómo ejecutar NetQuick

**La app es una sola: el widget flotante con icono en la bandeja del sistema.**

| Situación | Comando |
|---|---|
| Instalar el `.exe` (recomendado) | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install.ps1 \| iex` |
| Instalar desde fuente (sin .exe) | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install-src.ps1 \| iex` |
| Repo ya clonado (desarrollo) | `.\setup.ps1` y luego doble clic en `NetQuick.vbs` |
| Directo con Python | `pythonw netquick.py` |
| **Desinstalar** | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/uninstall.ps1 \| iex` |

Tras instalar, abre una terminal nueva y escribe **`netquick`**, o usa el acceso directo del Escritorio.

> 🛡️ NetQuick necesita permisos de **Administrador** para cambiar la configuración de red; los pide solo cuando hace falta.

---

## 🗂️ Estructura del repo

| Archivo | Qué es |
|---|---|
| `netquick.py` | **La aplicación** — widget flotante + icono de bandeja |
| `netops.py` | Operaciones de red (netsh, psutil, escáner, mDNS Dante, revert de emergencia) |
| `store.py` | Persistencia de perfiles y configuración (JSON con escritura durable) |
| `winsetup.py` | Integración con Windows (inicio automático, DPI, instancia única) |
| `NetQuick.vbs` | Lanzador sin ventana de consola (doble clic) |
| `NetQuick.spec` | Empaquetado del `.exe` con PyInstaller |
| `install.ps1` / `install-src.ps1` | Instaladores por terminal (`irm ... \| iex`) |
| `uninstall.ps1` | Desinstalador (revierte archivos, PATH, accesos e inicio con Windows) |
| `setup.ps1` | Setup de desarrollo (instala dependencias) |
| `tests/` | Tests de `netops`, `store`, `winsetup` y la UI con fakes (pytest, corren en CI) |
| `docs/` | Backlog de confiabilidad y notas de ingeniería |
| `experimentos/` | Scripts para validar hipótesis en una LAN real |
| `CHANGELOG.md` | Historial de cambios |

---

## 🚀 Características

| Función | Descripción |
|---|---|
| 📌 **Widget flotante** | Barrita compacta, siempre encima, anclada abajo a la derecha |
| 🔔 **Icono en bandeja** | La ✕ oculta el widget; clic en el icono lo muestra; "Salir" en clic derecho |
| 🏷️ **Perfiles guardados** | Guarda combinaciones IP/máscara/gateway (*Casa*, *U*, *Trabajo*) y aplícalas de 1 clic |
| 🔄 **DHCP / IP fija** | Cambia de modo con un clic; el color indica el modo activo |
| 🔍 **Escáner de red** | Compatible con redes Dante (máscara real y link-local /16), descubrimiento mDNS nativo |
| 🚫 **Anti-IP duplicada** | Antes de aplicar comprueba que la IP esté libre: ping + sonda ARP dirigida (detecta equipos que callan al ping); si no puede verificar, lo dice |
| ⏪ **Auto-revert** | Si la IP aplicada te deja sin salida (el gateway no responde), cuenta regresiva de 30 s y vuelta automática a la config anterior — el revert es 100 % local |
| 🚦 **Estados honestos** | Verde = éxito limpio · ámbar = aplicado con avisos · rojo = no se aplicó; nunca verde ocultando un problema |
| 📋 **Log estructurado** | Cada intento queda en `%LOCALAPPDATA%\NetQuick\netquick.log` con operación, resultado y duración |
| ⚙️ **Iniciar con Windows** | Opción en la rueda ⚙ del widget |
| 🛡️ **Permisos de Admin** | Solicitud automática cuando hace falta |

---

## 📦 Generar el .exe

```powershell
pip install pyinstaller
pyinstaller NetQuick.spec
# resultado: dist\NetQuick.exe
```

> **Nota:** Windows (Defender / Smart App Control) puede bloquear el `.exe` por no estar firmado. Ejecutar desde fuente (`pythonw netquick.py`) no tiene ese problema.

Los `.exe` oficiales se compilan automáticamente en GitHub Actions al crear un tag `v*`, y cada release publica el **hash SHA256** del ejecutable para que puedas verificar tu descarga: `Get-FileHash NetQuick.exe -Algorithm SHA256`.

---

## 👥 Autores

<table>
  <tr>
    <td align="center"><b>Israel Moncayo</b></td>
    <td align="center"><b>Oscar Osorio</b></td>
  </tr>
</table>

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

<div align="center">

*Hecho con ❤️ en Colombia 🇨🇴*

**¿Te fue útil? ¡Dale una ⭐ al repo!**

</div>
