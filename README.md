<div align="center">

<img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows"/>
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/Version-1.0.0-blue?style=for-the-badge" alt="Version"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>

<br/><br/>

# ⚡ NetQuick

### *Cambia rápido, sin estresarte.*

**NetQuick** es una herramienta de escritorio para Windows que te permite configurar tu red en segundos — sin abrir la consola, sin memorizar comandos, sin complicaciones.

[📥 Descargar .exe](#-descarga) · [🚀 Características](#-características) · [🛠️ Cómo usar](#%EF%B8%8F-cómo-usar)

---

</div>

## 🆕 Novedades v1.1

- ⚡ **Mini-widget flotante** (`mini.py`): una barrita compacta, siempre encima y
  anclada abajo a la derecha, para cambiar la IP/red al vuelo sin abrir la ventana grande.
- 🏷️ **Perfiles guardados**: guarda combinaciones IP/máscara/gateway (ej. *Casa*, *U*,
  *Trabajo*) y aplícalas de un clic.
- ⚙️ **Configuración**: opción de *Iniciar con Windows* para tenerlo siempre disponible.
- 🚫 **Sin consola negra**: se lanza con `NetQuickMini.vbs` (usa `pyw`, sin ventana).
- 🐛 **Fix**: la aplicación de IP manual ahora limpia espacios y **valida** IP/máscara/gateway
  antes de ejecutar, con mensajes de error claros.

**Cómo abrir el mini-widget:** doble clic en `NetQuickMini.vbs`.

## 🎯 ¿Qué es NetQuick?

NetQuick nació de una necesidad simple: **cambiar la IP de tu máquina rápido**, ya sea en la universidad, en el trabajo, o en casa. En lugar de navegar entre menús de Windows o recordar comandos `netsh`, NetQuick lo hace por ti en **un solo clic**.

> Perfecta para técnicos de redes, estudiantes de informática y cualquiera que cambie de entorno con frecuencia.

---

## 🚀 Características

| Función | Descripción |
|---|---|
| 🔍 **Detección automática** | Muestra todas tus interfaces de red activas al instante |
| 🔄 **Toggle DHCP / IP Estática** | Cambia de modo con un solo click |
| ✏️ **Asignación de IP manual** | Ingresa IP, Máscara y Puerta de Enlace fácilmente |
| ⚡ **Aplicación instantánea** | Cambios en segundos, sin reiniciar |
| 🛡️ **Permisos de Admin** | Solicitud automática de permisos de administrador |
| 🎨 **Interfaz moderna** | UI limpia y profesional, inspirada en apps actuales |

---

## 📥 Descarga

> **NetQuick no requiere instalación.** Descarga el `.exe` y ejecútalo directamente.

<div align="center">

### [⬇️ Descargar NetQuick v1.0 (.exe)](../../releases/latest)

</div>

1. Descarga el archivo `NetQuick.exe` de la sección **Releases**.
2. Haz clic derecho → **Ejecutar como Administrador** (necesario para modificar la red).
3. ¡Listo! Configura tu red en segundos.

> **Nota:** Windows Defender puede mostrar una advertencia la primera vez por ser un ejecutable desconocido. Haz clic en **"Más información" → "Ejecutar de todas formas"**. El programa es 100% seguro y de código abierto.

---

## 🛠️ Cómo usar

**1. Selecciona tu interfaz de red**
NetQuick detectará automáticamente tus adaptadores activos (Wi-Fi, Ethernet, etc.).

**2. Elige tu modo**
- **Automático (DHCP)** → Activa el toggle. Tu router asignará la IP.
- **Manual (IP Estática)** → Desactiva el toggle e ingresa los datos.

**3. Aplica los cambios**
Haz clic en el botón y los cambios se aplican al instante. Sin reiniciar, sin complicaciones.

---

## 🏗️ Instalación desde código fuente

Si prefieres ejecutarlo desde el código fuente:

```bash
# Clona el repositorio
git clone https://github.com/devmaiter/NetQuick.git
cd NetQuick

# Instala las dependencias
pip install psutil

# Ejecuta como administrador
python main.py
```

**Requisitos:**
- Python 3.8+
- `psutil` (`pip install psutil`)
- Windows 7/10/11

---

## ⚠️ Permisos de Administrador

NetQuick necesita permisos de administrador para modificar la configuración de red del sistema. Al ejecutar el programa, si no tienes privilegios de admin, se te pedirá que reinicies con los permisos necesarios.

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
