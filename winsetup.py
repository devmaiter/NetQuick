# -*- coding: utf-8 -*-
"""
Integración de NetQuick con Windows (Facade).

Una interfaz simple sobre schtasks, netsh advfirewall, winreg y ctypes:
la UI no sabe CÓMO se hace (tareas programadas, claves del registro,
mutex de instancia), solo QUÉ puede pedir — iniciar con Windows,
primer arranque del exe, instancia única y conciencia de DPI.
"""
import ctypes
import os
import sys
import winreg

import netops

# Empaquetado con PyInstaller: __file__ apunta a una carpeta temporal, así que
# los datos del usuario (perfiles) van a %APPDATA%\NetQuick.
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
if FROZEN:
    APP_DIR = os.path.join(os.environ.get("APPDATA", HERE), "NetQuick")
    os.makedirs(APP_DIR, exist_ok=True)
else:
    APP_DIR = HERE
VBS_SRC = os.path.join(HERE, "NetQuick.vbs")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS_DST = os.path.join(STARTUP_DIR, "NetQuick.vbs")

# Como .exe la app corre siempre elevada (manifest requireAdministrator):
# así aplicar IP/DHCP nunca cierra ni relanza la ventana. El inicio con
# Windows usa una tarea programada con privilegios (RunLevel Highest), que
# arranca elevada al iniciar sesión SIN mostrar UAC.
TASK_NAME = "NetQuick"
# Clave Run de versiones anteriores (solo para migrar/limpiar)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "NetQuick"


def _task_xml(exe):
    """XML de la tarea programada: al iniciar sesión, elevada, sin límites
    de batería ni de tiempo (las opciones por defecto de schtasks los ponen)."""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{exe}</Command></Exec>
  </Actions>
</Task>"""


# --- Inicio con Windows ----------------------------------------------------
def in_startup():
    if FROZEN:
        res = netops.run(["schtasks", "/Query", "/TN", TASK_NAME], quiet=True)
        return bool(res and res.returncode == 0)
    return os.path.exists(VBS_DST)


def _dir_solo_admin():
    """Carpeta escribible SOLO por administradores/SYSTEM, no por usuarios
    estándar: %SystemRoot%\\Temp. El task.xml se genera aquí (no en %APPDATA%,
    que es escribible por el usuario) para cerrar la ventana TOCTOU de FM-5:
    un proceso sin privilegios no puede reescribir el XML entre que la app
    elevada lo crea y schtasks lo lee. La app corre elevada, así que sí puede
    escribir aquí."""
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")


def _crear_tarea_inicio(exe):
    """Crea la tarea programada de inicio desde un XML en carpeta solo-admin,
    con nombre aleatorio, y lo borra al terminar. Devuelve True si schtasks
    creó la tarea."""
    import tempfile
    try:
        fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="netquick_",
                                        dir=_dir_solo_admin())
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(_task_xml(exe))
    except OSError:
        # Sin carpeta protegida donde escribir no se crea la tarea en un sitio
        # inseguro: mejor no activar el inicio que hacerlo de forma vulnerable.
        return False
    try:
        res = netops.run(["schtasks", "/Create", "/TN", TASK_NAME,
                          "/XML", xml_path, "/F"])
        return bool(res and res.returncode == 0)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass


def set_startup(on):
    try:
        if FROZEN:
            if on:
                return _crear_tarea_inicio(sys.executable)
            netops.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
            return True
        if on:
            # El .vbs de inicio lleva rutas absolutas (script Y pythonw): si
            # pythonw no está en el PATH, un "pythonw" a secas falla silencioso.
            script = os.path.join(HERE, "netquick.py")
            pyw = netops.pythonw()
            with open(VBS_DST, "w", encoding="utf-8") as f:
                f.write('CreateObject("WScript.Shell").Run '
                        f'"""{pyw}"" ""{script}""", 0, False\r\n')
        elif not on and os.path.exists(VBS_DST):
            os.remove(VBS_DST)
        return True
    except Exception:
        return False


def regla_firewall():
    """Regla de firewall para el exe (como hace Dante Controller al
    instalarse): sin ella Windows bloquea las respuestas mDNS unicast de los
    equipos Dante hacia el puerto efímero del escáner. Idempotente: borra la
    regla anterior por si el exe cambió de ruta."""
    netops.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                "name=NetQuick"], quiet=True)
    netops.run(["netsh", "advfirewall", "firewall", "add", "rule",
                "name=NetQuick", "dir=in", "action=allow",
                f"program={sys.executable}", "profile=any", "enable=yes"])


def primer_arranque_exe():
    """La primera vez que corre el .exe: regla de firewall y limpieza de
    instalaciones previas. NetQuick ya NO se auto-registra para iniciar con
    Windows — se abre, se queda en la bandeja, y punto. Iniciar con Windows es
    una opción del usuario en ⚙ (apagada por defecto): la app no debe colarse
    en el arranque elevado sin que el usuario lo pida."""
    if not FROZEN:
        return
    regla_firewall()
    # Migrar instalaciones previas: quitar la clave Run insegura (arrancaba sin
    # permisos). NO se recrea la tarea: si el usuario quiere inicio automático,
    # lo marca él mismo en ⚙.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_ALL_ACCESS) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            winreg.DeleteValue(k, RUN_NAME)
    except OSError:
        pass


# --- Proceso ----------------------------------------------------------------
# El handle del mutex debe vivir todo el proceso (si se cerrara, otra
# instancia podría arrancar): se guarda a nivel de módulo a propósito.
_MUTEX = None


def ya_corriendo():
    """Evita instancias (e iconos de bandeja) duplicados."""
    global _MUTEX
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                 "NetQuick_Instancia")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def dpi_awareness():
    """Con escalado de Windows (125/150 %) Tkinter se ve borroso si el proceso
    no declara conciencia de DPI. Declararla ANTES de crear la ventana."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
