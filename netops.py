# -*- coding: utf-8 -*-
"""
Operaciones de red compartidas para NetQuick (usadas por el mini-widget).

- Todos los subprocesos corren OCULTOS (sin ventana negra parpadeante).
- La elevación a admin usa pythonw.exe para que NO aparezca ninguna consola.
"""
import ctypes
import ipaddress
import logging
import os
import subprocess
import sys
import winreg
from logging.handlers import RotatingFileHandler

import psutil

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# --- Log a archivo -----------------------------------------------------------
# Para diagnosticar en máquinas ajenas: %LOCALAPPDATA%\NetQuick\netquick.log
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA")
                       or os.path.expanduser("~"), "NetQuick")
LOG_FILE = os.path.join(LOG_DIR, "netquick.log")

log = logging.getLogger("netquick")
if not log.handlers:
    log.setLevel(logging.INFO)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _h = RotatingFileHandler(LOG_FILE, maxBytes=256 * 1024,
                                 backupCount=1, encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(_h)
    except OSError:
        log.addHandler(logging.NullHandler())


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


def run(cmd, quiet=False):
    """Ejecuta un comando (lista) sin mostrar ninguna ventana.

    quiet: no registrar el fallo en el log (para comandos cuyo error es
    normal, como el ping a una IP libre)."""
    try:
        res = subprocess.run(
            cmd, capture_output=True,
            startupinfo=_hidden_startupinfo(), creationflags=_NO_WINDOW,
        )
        res.stdout = _decodificar(res.stdout)
        res.stderr = _decodificar(res.stderr)
        if res.returncode != 0 and not quiet:
            log.warning("cmd %s -> %s: %s", cmd, res.returncode,
                        (res.stderr or res.stdout).strip())
        return res
    except Exception:
        log.exception("cmd %s no se pudo ejecutar", cmd)
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
    res = run(["ping", "-n", "1", "-w", "400", ip], quiet=True)
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


# --- Descubrimiento Dante (mDNS) --------------------------------------------
def _nombre_mdns(datos):
    """Nombre del equipo en una respuesta mDNS ('MiConsola._netaudio-arc...').

    La etiqueta del nombre precede a '_netaudio' bien de forma literal, bien
    seguida de un puntero DNS comprimido (0xC0 xx) que apunta a '_netaudio'.
    Mejor esfuerzo: si no se puede extraer, se devuelve cadena vacía.
    """
    posiciones = []
    i = datos.find(b"_netaudio")
    while i != -1:
        posiciones.append(i - 1)  # byte de longitud de '_netaudio-...'
        i = datos.find(b"_netaudio", i + 1)
    for p in range(len(datos) - 1):
        if datos[p] & 0xC0 == 0xC0:  # puntero comprimido
            destino = ((datos[p] & 0x3F) << 8) | datos[p + 1]
            if datos[destino + 1:destino + 10] == b"_netaudio":
                posiciones.append(p)
    for fin in posiciones:
        if fin < 2:
            continue
        for k in range(max(0, fin - 64), fin):
            if k + 1 + datos[k] == fin and 0 < datos[k] <= 63:
                try:
                    nombre = datos[k + 1:fin].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if nombre.isprintable() and not nombre.startswith("_"):
                    return nombre
    return ""


def descubrir_dante(nombre, timeout=2.0):
    """Descubrimiento nativo de equipos Dante, igual que Dante Controller:
    consulta mDNS/DNS-SD por '_netaudio-arc._udp.local' a 224.0.0.251:5353
    (documentación oficial de Audinate). Se envía desde un puerto efímero
    ('legacy unicast', RFC 6762) para que cada equipo responda directo.
    Devuelve {ip: nombre_dante}. No requiere admin.
    """
    import socket
    import struct
    import time

    propia = get_ip(nombre)
    if not propia:
        return {}

    def qname(dominio):
        out = b""
        for parte in dominio.split("."):
            out += bytes([len(parte)]) + parte.encode()
        return out + b"\x00"

    # Cabecera DNS estándar + 1 pregunta PTR clase IN
    consulta = (struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
                + qname("_netaudio-arc._udp.local")
                + struct.pack(">HH", 12, 1))

    encontrados = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                     socket.inet_aton(propia))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        s.bind((propia, 0))
        s.settimeout(0.3)
        for _ in range(2):  # repetir por si algún equipo no oye la primera
            s.sendto(consulta, ("224.0.0.251", 5353))
            fin = time.time() + timeout / 2
            while time.time() < fin:
                try:
                    datos, origen = s.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                ip = origen[0]
                encontrados[ip] = _nombre_mdns(datos) or encontrados.get(ip, "")
        s.close()
    except OSError:
        pass
    return encontrados


# --- Escaneo de la subred ----------------------------------------------------
def scan_red(nombre, timeout_ms=250):
    """Escaneo de la subred REAL de la interfaz (según su máscara).

    - Subredes normales (hasta ~1000 hosts, p.ej. /24): ping a todas las IPs
      en paralelo y lectura de la caché ARP.
    - Subredes enormes (p.ej. Dante en link-local 169.254.0.0/16): el barrido
      es inviable, pero no hace falta — los equipos Dante anuncian por
      multicast constantemente y llenan solos la caché ARP; se lee entera.
    Devuelve [{'ip','mac','propia'}] ordenado por IP. No requiere admin.
    """
    import concurrent.futures
    propia = get_ip(nombre)
    if not propia:
        return []
    mask = get_config(nombre).get("mask") or "255.255.255.0"
    try:
        red = ipaddress.ip_network(f"{propia}/{mask}", strict=False)
    except ValueError:
        red = ipaddress.ip_network(f"{propia}/24", strict=False)

    if red.num_addresses <= 1024:
        def _ping(ip):
            run(["ping", "-n", "1", "-w", str(timeout_ms), str(ip)], quiet=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            list(ex.map(_ping, red.hosts()))

    encontrados = {}
    res = run(["arp", "-a"])
    if res and res.stdout:
        for linea in res.stdout.splitlines():
            partes = linea.split()
            if len(partes) < 2:
                continue
            ip, mac = partes[0], partes[1].lower()
            try:
                if ipaddress.IPv4Address(ip) not in red:
                    continue
            except ipaddress.AddressValueError:
                continue
            # descartar broadcast, multicast y entradas incompletas
            if mac.count("-") != 5 or mac == "ff-ff-ff-ff-ff-ff" \
               or mac.startswith("01-00-5e") or ip == str(red.broadcast_address):
                continue
            encontrados[ip] = {"ip": ip, "mac": mac, "propia": False,
                               "dante": None}

    # Equipos Dante por mDNS (como Dante Controller). Sin filtrar por subred:
    # así aparecen también los que quedaron con una IP fija equivocada.
    for ip, nombre_d in descubrir_dante(nombre).items():
        if ip == propia:
            continue
        e = encontrados.setdefault(ip, {"ip": ip, "mac": "", "propia": False,
                                        "dante": None})
        e["dante"] = nombre_d or "Dante"

    encontrados[propia] = {"ip": propia, "mac": "", "propia": True,
                           "dante": None}
    return sorted(encontrados.values(),
                  key=lambda d: tuple(int(x) for x in d["ip"].split(".")))


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
        log.info("set_static %s ip=%s mask=%s gw=%s", nombre, ip, mask, gw)
        return True, f"IP {ip} aplicada"
    detalle = ((res.stderr or res.stdout) or "").strip() if res else ""
    return False, (detalle or "Error (¿admin?)")


def set_dhcp(nombre):
    """Pone la interfaz en automático (DHCP). Devuelve (ok, mensaje)."""
    r1 = run(["netsh", "interface", "ip", "set", "address", f"name={nombre}", "dhcp"])
    run(["netsh", "interface", "ip", "set", "dns", f"name={nombre}", "dhcp"])
    if r1 and r1.returncode == 0:
        log.info("set_dhcp %s", nombre)
        return True, "DHCP activado"
    detalle = ((r1.stderr or r1.stdout) or "").strip() if r1 else ""
    return False, (detalle or "Error (¿admin?)")
