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
import winreg

import psutil

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _hidden_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def _decodificar(b):
    """netsh responde en UTF-8 si Windows tiene activado 'UTF-8 mundial'
    y en la página OEM clásica si no: probar en orden hasta que cuadre,
    para que los acentos (Sí, está, Dirección…) no lleguen rotos."""
    if not b:
        return ""
    for enc in ("utf-8", "oem", "cp1252"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")


def run(cmd):
    """Ejecuta un comando (lista) sin mostrar ninguna ventana."""
    try:
        res = subprocess.run(
            cmd, capture_output=True,
            startupinfo=_hidden_startupinfo(), creationflags=_NO_WINDOW,
        )
        res.stdout = _decodificar(res.stdout)
        res.stderr = _decodificar(res.stderr)
        return res
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
    """Reinicia la app como administrador (sin ventana negra).

    Empaquetado como .exe (PyInstaller): relanzar el propio .exe.
    En desarrollo: relanzar el script con pythonw.
    """
    if getattr(sys, "frozen", False):
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, None, None, 1
        )
    else:
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


def _iface_guid(nombre):
    """GUID de la interfaz a partir de su nombre visible, vía registro.
    No depende del idioma ni de la codificación de Windows."""
    base = (r"SYSTEM\CurrentControlSet\Control\Network"
            r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as red:
            for i in range(winreg.QueryInfoKey(red)[0]):
                guid = winreg.EnumKey(red, i)
                try:
                    with winreg.OpenKey(red, guid + r"\Connection") as con:
                        if winreg.QueryValueEx(con, "Name")[0] == nombre:
                            return guid
                except OSError:
                    continue
    except OSError:
        pass
    return ""


def _reg_ip(valor):
    """Primer valor útil de una entrada de red del registro (REG_MULTI_SZ)."""
    if isinstance(valor, list):
        valor = valor[0] if valor else ""
    return (valor or "").strip("\x00").strip()


def get_config(nombre):
    """Config real de la interfaz: {'dhcp', 'ip', 'mask', 'gw'}.

    Sin parsear texto de netsh: la IP y máscara salen de psutil y el modo
    DHCP y el gateway del registro (Tcpip\\Parameters\\Interfaces\\{GUID}).
    Funciona igual en cualquier idioma/configuración de Windows.
    """
    info = {"dhcp": False, "ip": "", "mask": "", "gw": ""}
    try:
        for d in psutil.net_if_addrs().get(nombre, []):
            if d.family.name == "AF_INET":
                info["ip"] = d.address
                info["mask"] = d.netmask or ""
                break
    except Exception:
        pass
    guid = _iface_guid(nombre)
    if not guid:
        return info
    ruta = (r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            "\\" + guid)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as k:
            info["dhcp"] = bool(winreg.QueryValueEx(k, "EnableDHCP")[0])
            clave_gw = "DhcpDefaultGateway" if info["dhcp"] else "DefaultGateway"
            try:
                info["gw"] = _reg_ip(winreg.QueryValueEx(k, clave_gw)[0])
            except OSError:
                pass
    except OSError:
        pass
    return info


# --- Validación ------------------------------------------------------------
def ip_valida(valor):
    try:
        ipaddress.IPv4Address(str(valor).strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


# --- Detección de conflictos -----------------------------------------------
def ip_en_uso(ip):
    """True si otro dispositivo de la red ya responde en esa IP.

    Comprueba con un ping corto y, por si el otro equipo bloquea ping
    (firewall), revisa también la caché ARP que el propio ping refresca.
    Las IPs de esta misma máquina no cuentan como conflicto.
    """
    ip = ip.strip()
    for i in list_interfaces():
        if i["ip"] == ip:
            return False
    res = run(["ping", "-n", "1", "-w", "400", ip])
    # returncode 0 con "unreachable" también existe: exigir respuesta real (TTL)
    if res and res.returncode == 0 and "ttl=" in (res.stdout or "").lower():
        return True
    res = run(["arp", "-a"])
    if res and res.stdout:
        for linea in res.stdout.splitlines():
            partes = linea.split()
            if len(partes) >= 2 and partes[0] == ip:
                mac = partes[1].lower()
                if mac.count("-") == 5 and mac != "ff-ff-ff-ff-ff-ff":
                    return True
    return False


# --- Escaneo de la subred ----------------------------------------------------
def scan_red(nombre, timeout_ms=250):
    """Barrido de la subred /24 de la interfaz: ping a las 254 IPs en paralelo
    y lectura de la caché ARP. Devuelve [{'ip','mac','propia'}] ordenado por IP.
    No requiere admin.
    """
    import concurrent.futures
    propia = get_ip(nombre)
    if not propia:
        return []
    prefijo = propia.rsplit(".", 1)[0]

    def _ping(ip):
        run(["ping", "-n", "1", "-w", str(timeout_ms), ip])

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping, [f"{prefijo}.{n}" for n in range(1, 255)]))

    encontrados = {}
    res = run(["arp", "-a"])
    if res and res.stdout:
        for linea in res.stdout.splitlines():
            partes = linea.split()
            if len(partes) < 2 or not partes[0].startswith(prefijo + "."):
                continue
            ip, mac = partes[0], partes[1].lower()
            # descartar broadcast, multicast y entradas incompletas
            if mac.count("-") != 5 or mac == "ff-ff-ff-ff-ff-ff" \
               or mac.startswith("01-00-5e") or ip.endswith(".255"):
                continue
            encontrados[ip] = {"ip": ip, "mac": mac, "propia": False}
    encontrados[propia] = {"ip": propia, "mac": "", "propia": True}
    return sorted(encontrados.values(),
                  key=lambda d: int(d["ip"].rsplit(".", 1)[1]))


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
    if ip_en_uso(ip):
        return False, f"⚠ {ip} ya está en uso — no se aplicó nada"
    cmd = ["netsh", "interface", "ip", "set", "address", f"name={nombre}", "static", ip, mask]
    if gw:
        cmd += [gw, "1"]
    res = run(cmd)
    if res and res.returncode == 0:
        return True, f"IP {ip} aplicada"
    detalle = ((res.stdout or "") + (res.stderr or "")).strip() if res else ""
    return False, (detalle or "Error (¿admin?)")


def set_dhcp(nombre):
    """Pone la interfaz en automático (DHCP). Devuelve (ok, mensaje)."""
    r1 = run(["netsh", "interface", "ip", "set", "address", f"name={nombre}", "dhcp"])
    run(["netsh", "interface", "ip", "set", "dns", f"name={nombre}", "dhcp"])
    if r1 and r1.returncode == 0:
        return True, "DHCP activado"
    detalle = ((r1.stdout or "") + (r1.stderr or "")).strip() if r1 else ""
    return False, (detalle or "Error (¿admin?)")
