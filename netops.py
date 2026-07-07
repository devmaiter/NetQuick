# -*- coding: utf-8 -*-
"""
Operaciones de red compartidas para NetQuick (usadas por el mini-widget).

- Todos los subprocesos corren OCULTOS (sin ventana negra parpadeante).
- La elevación a admin usa pythonw.exe para que NO aparezca ninguna consola.
"""
import ctypes
import ipaddress
import os
import subprocess
import sys

import psutil

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _hidden_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def run(cmd):
    """Ejecuta un comando (lista) sin mostrar ninguna ventana."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True,
            startupinfo=_hidden_startupinfo(), creationflags=_NO_WINDOW,
        )
    except Exception:
        return None


# --- Admin / elevación -----------------------------------------------------
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pythonw():
    """Ruta a pythonw.exe (sin consola). Si no existe, cae a sys.executable."""
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.exists(cand) else sys.executable


def relaunch_as_admin(script):
    """Reinicia el script como administrador usando pythonw (sin ventana negra)."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", pythonw(), f'"{os.path.abspath(script)}"', None, 1
    )
    sys.exit(0)


# --- Consulta de interfaces ------------------------------------------------
def list_interfaces():
    """Devuelve [{'nombre', 'ip'}] de las interfaces activas (sin loopback 'lo')."""
    data = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for nombre, direcc in addrs.items():
            st = stats.get(nombre)
            if st and st.isup and not nombre.lower().startswith("lo"):
                ip = next((d.address for d in direcc if d.family.name == "AF_INET"), "")
                data.append({"nombre": nombre, "ip": ip})
    except Exception:
        pass
    return data


def get_ip(nombre):
    for i in list_interfaces():
        if i["nombre"] == nombre:
            return i["ip"]
    return ""


# --- Validación ------------------------------------------------------------
def ip_valida(valor):
    try:
        ipaddress.IPv4Address(str(valor).strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


# --- Aplicar configuración -------------------------------------------------
def set_static(nombre, ip, mask, gw=None):
    """Aplica IP estática. Devuelve (ok, mensaje)."""
    ip, mask = ip.strip(), mask.strip()
    gw = gw.strip() if gw else ""
    if not ip_valida(ip):
        return False, f"IP no válida: {ip}"
    if not ip_valida(mask):
        return False, "Máscara no válida (usa 255.255.255.0)"
    if gw and not ip_valida(gw):
        return False, f"Gateway no válido: {gw}"
    cmd = ["netsh", "interface", "ip", "set", "address", f"name={nombre}", "static", ip, mask]
    if gw:
        cmd += [gw, "1"]
    res = run(cmd)
    if res and res.returncode == 0:
        return True, f"IP {ip} aplicada"
    return False, (res.stdout.strip() if res and res.stdout else "Error (¿admin?)")


def set_dhcp(nombre):
    """Pone la interfaz en automático (DHCP). Devuelve (ok, mensaje)."""
    r1 = run(["netsh", "interface", "ip", "set", "address", f"name={nombre}", "dhcp"])
    run(["netsh", "interface", "ip", "set", "dns", f"name={nombre}", "dhcp"])
    if r1 and r1.returncode == 0:
        return True, "DHCP activado"
    return False, (r1.stdout.strip() if r1 and r1.stdout else "Error (¿admin?)")
