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
import time
import winreg
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Protocol

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


def _log_op(op, resultado, motivo="", dur_ms=None, **campos):
    """Una línea estructurada por INTENTO (no solo por éxito), para poder
    computar tasa de éxito y latencia desde el log. resultado ∈
    {ok, rechazo, error}: 'rechazo' = validación/usuario (fuera del SLO),
    'error' = el SO falló (dentro del SLO)."""
    extra = " ".join(f"{k}={v}" for k, v in campos.items() if v != "")
    if dur_ms is not None:
        extra = f"dur_ms={dur_ms} {extra}".strip()
    log.info("op=%s resultado=%s motivo=%s %s", op, resultado, motivo, extra)


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


def relaunch_as_admin(script, extra=None):
    """Reinicia la app como administrador (sin ventana negra).

    Empaquetado como .exe (PyInstaller): relanzar el propio .exe.
    En desarrollo: relanzar el script con pythonw.

    extra: dict opcional {"--flag": valor} que se reenvía al proceso nuevo
    para no perder lo que el usuario ya había tecleado (issue #17).
    """
    if getattr(sys, "frozen", False):
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, None, None, 1
        )
    else:
        params = f'"{os.path.abspath(script)}"'
        for flag, valor in (extra or {}).items():
            if valor:
                params += f' {flag} "{valor}"'
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", pythonw(), params, None, 1
        )
    sys.exit(0)


# --- Consulta de interfaces ------------------------------------------------
def list_interfaces():
    """Devuelve [{'nombre', 'ip'}] de las interfaces activas (sin loopback 'lo').

    El try va POR interfaz: una interfaz rara (driver a medias, adaptador
    virtual roto) se salta sola sin tumbar la lista completa."""
    data = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception:
        return data
    for nombre, direcc in addrs.items():
        try:
            st = stats.get(nombre)
            if st and st.isup and not nombre.lower().startswith("lo"):
                ip = next((d.address for d in direcc if d.family.name == "AF_INET"), "")
                data.append({"nombre": nombre, "ip": ip})
        except Exception:
            continue
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


def _primer_dns(cadena):
    """Primer servidor de una lista DNS del registro ('8.8.8.8,1.1.1.1')."""
    return cadena.replace(",", " ").split()[0] if cadena else ""


def _config_registro(guid):
    """Modo DHCP, gateway y DNS de la interfaz, leídos del registro
    (Tcpip\\Parameters\\Interfaces\\{GUID}). Mejor esfuerzo: lo que no se
    pueda leer conserva su valor por defecto."""
    info = {"dhcp": False, "gw": "", "dns": ""}
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
            # DNS: 'NameServer' (estático, "8.8.8.8,1.1.1.1") o 'DhcpNameServer'
            clave_dns = "DhcpNameServer" if info["dhcp"] else "NameServer"
            try:
                info["dns"] = _primer_dns(
                    _reg_ip(winreg.QueryValueEx(k, clave_dns)[0]))
            except OSError:
                pass
    except OSError:
        pass
    return info


def get_config(nombre):
    """Config real de la interfaz: {'dhcp', 'ip', 'mask', 'gw', 'dns'}.

    Sin parsear texto de netsh: la IP y máscara salen de psutil y el modo
    DHCP, el gateway y el DNS del registro. Funciona igual en cualquier
    idioma/configuración de Windows.
    """
    info = {"dhcp": False, "ip": "", "mask": "", "gw": "", "dns": ""}
    try:
        for d in psutil.net_if_addrs().get(nombre, []):
            if d.family.name == "AF_INET":
                info["ip"] = d.address
                info["mask"] = d.netmask or ""
                break
    except Exception:
        pass
    guid = _iface_guid(nombre)
    if guid:
        info.update(_config_registro(guid))
    return info


# --- Validación ------------------------------------------------------------
def ip_valida(valor):
    try:
        ipaddress.IPv4Address(str(valor).strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def mascara_valida(valor):
    """True solo para máscaras de subred reales: unos contiguos y luego ceros
    (255.255.255.0 sí; 1.2.3.4 o 255.7.0.255 no — netsh fallaría después
    con un error críptico)."""
    valor = str(valor).strip()
    if not ip_valida(valor):
        return False
    m = int(ipaddress.IPv4Address(valor))
    return m != 0 and (m | (m - 1)) == 0xFFFFFFFF


# --- Detección de conflictos -----------------------------------------------
def _parsear_arp(texto, red=None):
    """{ip: mac} de la salida de 'arp -a'. Descarta broadcast, multicast
    (01-00-5e) y entradas incompletas; con 'red', solo las IPs de esa
    subred (excluida su dirección de broadcast)."""
    tabla = {}
    for linea in (texto or "").splitlines():
        partes = linea.split()
        if len(partes) < 2:
            continue
        ip, mac = partes[0], partes[1].lower()
        if mac.count("-") != 5 or mac == "ff-ff-ff-ff-ff-ff" \
           or mac.startswith("01-00-5e"):
            continue
        try:
            direccion = ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            continue
        if red is not None and (direccion not in red
                                or ip == str(red.broadcast_address)):
            continue
        tabla[ip] = mac
    return tabla


def _subredes_locales():
    """Redes IPv4 directamente conectadas (según IP/máscara de cada
    interfaz activa). Solo dentro de ellas tiene sentido preguntar por ARP."""
    redes = []
    try:
        for direcc in psutil.net_if_addrs().values():
            for d in direcc:
                if d.family.name == "AF_INET" and d.netmask:
                    try:
                        redes.append(ipaddress.ip_network(
                            f"{d.address}/{d.netmask}", strict=False))
                    except ValueError:
                        continue
    except Exception:
        pass
    return redes


def _provocar_arp(ip):
    """Fuerza al SO a resolver la MAC de ip: un datagrama UDP a un puerto
    cualquiera dispara la petición ARP aunque el destino calle al ping.
    Espera breve para que la respuesta llegue a la caché. No requiere admin."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"", (ip, 9))  # puerto discard; el contenido da igual
        s.close()
    except OSError:
        pass
    time.sleep(0.4)


def _ip_en_arp(ip):
    res = run(["arp", "-a"])
    return bool(res and ip in _parsear_arp(res.stdout))


def verificar_ip(ip):
    """Veredicto sobre una IP antes de aplicarla (issue #20 / FM-2):
    'en_uso', 'libre' o 'sin_verificar'.

    Un equipo con firewall que calla al ping igual TIENE que responder ARP,
    así que dentro de la subred local se fuerza una sonda ARP dirigida y se
    relee la caché antes de darla por libre. Fuera de las subredes locales
    no hay ARP posible: si tampoco responde a ping, la evidencia es débil
    y se dice 'sin_verificar' en vez de fingir certeza.
    Las IPs de esta misma máquina no cuentan como conflicto.
    """
    ip = ip.strip()
    for i in list_interfaces():
        if i["ip"] == ip:
            return "libre"
    res = run(["ping", "-n", "1", "-w", "400", ip], quiet=True)
    # returncode 0 con "unreachable" también existe: exigir respuesta real (TTL)
    if res and res.returncode == 0 and "ttl=" in (res.stdout or "").lower():
        return "en_uso"
    if _ip_en_arp(ip):
        return "en_uso"
    try:
        direccion = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return "sin_verificar"
    if any(direccion in red for red in _subredes_locales()):
        _provocar_arp(ip)
        return "en_uso" if _ip_en_arp(ip) else "libre"
    return "sin_verificar"


def ip_en_uso(ip):
    """True si otro dispositivo de la red ya responde en esa IP."""
    return verificar_ip(ip) == "en_uso"


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


# Prefijos MAC (OUI) de fabricantes habituales en redes de audio
OUI_CONOCIDOS = {
    "00-1d-c1": "Audinate (Dante)",
    "00-a0-de": "Yamaha",
    "00-0e-dd": "Shure",
    "00-60-74": "QSC",
    "00-04-c4": "Allen & Heath",
    "b8-27-eb": "Raspberry Pi",
    "dc-a6-32": "Raspberry Pi",
}


def fabricante_mac(mac):
    """Fabricante según el prefijo OUI de la MAC ('aa-bb-cc-…'), o ''."""
    return OUI_CONOCIDOS.get((mac or "")[:8].lower(), "")


# --- Escaneo de la subred ----------------------------------------------------
def _ping_barrido(red, timeout_ms):
    """Ping corto en paralelo a todas las IPs de la subred. Las respuestas
    no se miran: el objetivo es que la caché ARP quede poblada."""
    import concurrent.futures

    def _ping(ip):
        run(["ping", "-n", "1", "-w", str(timeout_ms), str(ip)], quiet=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping, red.hosts()))


def _combinar_dispositivos(arp, dante, propia):
    """Une la tabla ARP {ip: mac} con los equipos Dante {ip: nombre} y marca
    la propia máquina. Los Dante entran aunque estén fuera de la subred (así
    aparecen los que quedaron con una IP fija equivocada). Devuelve la lista
    [{'ip','mac','propia','dante'}] ordenada numéricamente por IP."""
    encontrados = {ip: {"ip": ip, "mac": mac, "propia": False, "dante": None}
                   for ip, mac in arp.items()}
    for ip, nombre_d in dante.items():
        if ip == propia:
            continue
        e = encontrados.setdefault(ip, {"ip": ip, "mac": "", "propia": False,
                                        "dante": None})
        e["dante"] = nombre_d or "Dante"
    encontrados[propia] = {"ip": propia, "mac": "", "propia": True,
                           "dante": None}
    return sorted(encontrados.values(),
                  key=lambda d: tuple(int(x) for x in d["ip"].split(".")))


def scan_red(nombre, timeout_ms=250):
    """Escaneo de la subred REAL de la interfaz (según su máscara).

    - Subredes normales (hasta ~1000 hosts, p.ej. /24): ping a todas las IPs
      en paralelo y lectura de la caché ARP.
    - Subredes enormes (p.ej. Dante en link-local 169.254.0.0/16): el barrido
      es inviable, pero no hace falta — los equipos Dante anuncian por
      multicast constantemente y llenan solos la caché ARP; se lee entera.
    Devuelve [{'ip','mac','propia'}] ordenado por IP. No requiere admin.
    """
    propia = get_ip(nombre)
    if not propia:
        return []
    mask = get_config(nombre).get("mask") or "255.255.255.0"
    try:
        red = ipaddress.ip_network(f"{propia}/{mask}", strict=False)
    except ValueError:
        red = ipaddress.ip_network(f"{propia}/24", strict=False)

    if red.num_addresses <= 1024:
        _ping_barrido(red, timeout_ms)

    res = run(["arp", "-a"])
    arp = _parsear_arp(res.stdout if res else "", red)
    return _combinar_dispositivos(arp, descubrir_dante(nombre), propia)


# --- Aplicar configuración -------------------------------------------------
def _validar_static(ip, mask, gw, dns):
    """Mensaje de error del primer campo inválido, o None si todo cuadra."""
    if not ip_valida(ip):
        return f"IP no válida: {ip}"
    if not mascara_valida(mask):
        return f"Máscara no válida: {mask} (usa 255.255.255.0)"
    if gw and not ip_valida(gw):
        return f"Gateway no válido: {gw}"
    if dns and not ip_valida(dns):
        return f"DNS no válido: {dns}"
    return None


def set_static(nombre, ip, mask, gw=None, dns=None):
    """Aplica IP estática (y DNS si se indica). Devuelve (ok, mensaje)."""
    t0 = time.perf_counter()
    def _dur():
        return round((time.perf_counter() - t0) * 1000)

    ip, mask = ip.strip(), mask.strip()
    gw = gw.strip() if gw else ""
    dns = dns.strip() if dns else ""
    error = _validar_static(ip, mask, gw, dns)
    if error:
        _log_op("set_static", "rechazo", error, _dur(), iface=nombre, ip=ip)
        return False, error
    veredicto = verificar_ip(ip)
    if veredicto == "en_uso":
        _log_op("set_static", "rechazo", "ip_en_uso", _dur(), iface=nombre, ip=ip)
        return False, f"⚠ {ip} ya está en uso — no se aplicó nada"
    cmd = ["netsh", "interface", "ip", "set", "address", f"name={nombre}", "static", ip, mask]
    if gw:
        cmd += [gw, "1"]
    res = run(cmd)
    if not (res and res.returncode == 0):
        detalle = ((res.stderr or res.stdout) or "").strip() if res else ""
        _log_op("set_static", "error", detalle or "netsh_fallo", _dur(),
                iface=nombre, ip=ip)
        return False, (detalle or "Error (¿admin?)")
    avisos = []
    if veredicto == "sin_verificar":
        avisos.append(f"no se pudo verificar que {ip} estuviera libre")
    dns_ok = True
    if dns:
        r2 = run(["netsh", "interface", "ip", "set", "dns",
                  f"name={nombre}", "static", dns])
        if not (r2 and r2.returncode == 0):
            dns_ok = False
            avisos.append("el DNS no se pudo aplicar")
    if gw:
        red = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
        if ipaddress.IPv4Address(gw) not in red:
            avisos.append("gateway fuera de la subred")
    # Lección Rogers 2022: una operación que deja el sistema a medias no debe
    # reportar éxito limpio. Si se pidió DNS y falló, la transacción no logró su
    # objetivo -> ok=False (el gateway fuera de subred sí es solo un aviso).
    resultado = "ok" if dns_ok else "parcial"
    _log_op("set_static", resultado, " ".join(avisos), _dur(),
            iface=nombre, ip=ip, mask=mask, gw=gw, dns=dns)
    msg = "  ".join([f"IP {ip} aplicada", *(f"⚠ {a}" for a in avisos)])
    return dns_ok, msg


def set_dhcp(nombre):
    """Pone la interfaz en automático (DHCP). Devuelve (ok, mensaje)."""
    t0 = time.perf_counter()
    r1 = run(["netsh", "interface", "ip", "set", "address", f"name={nombre}", "dhcp"])
    run(["netsh", "interface", "ip", "set", "dns", f"name={nombre}", "dhcp"])
    dur_ms = round((time.perf_counter() - t0) * 1000)
    if r1 and r1.returncode == 0:
        _log_op("set_dhcp", "ok", "", dur_ms, iface=nombre)
        return True, "DHCP activado"
    detalle = ((r1.stderr or r1.stdout) or "").strip() if r1 else ""
    _log_op("set_dhcp", "error", detalle or "netsh_fallo", dur_ms, iface=nombre)
    return False, (detalle or "Error (¿admin?)")


def gateway_responde(gw):
    """True si el gateway contesta a un ping corto: conectividad básica
    verificada tras aplicar una IP fija (issue #21)."""
    if not gw:
        return False
    res = run(["ping", "-n", "1", "-w", "700", gw], quiet=True)
    return bool(res and res.returncode == 0
                and "ttl=" in (res.stdout or "").lower())


def revertir_a(nombre, previa):
    """Camino de emergencia (issue #21, lección Meta 2021): volver a la
    configuración previa por la vía más simple posible. netsh directo, sin
    validación ni verificar_ip — la herramienta de rescate no puede depender
    de la red que acaba de romperse, y la config previa ya estuvo aplicada.
    Devuelve (ok, mensaje)."""
    t0 = time.perf_counter()
    previa = previa or {}
    ip, mask = previa.get("ip", ""), previa.get("mask", "")
    if previa.get("dhcp") or not (ip and mask):
        # Sin datos fiables: DHCP es el estado conocido-bueno más simple
        ok, msg = set_dhcp(nombre)
        _log_op("revert", "ok" if ok else "error", "via_dhcp",
                round((time.perf_counter() - t0) * 1000), iface=nombre)
        return ok, msg
    cmd = ["netsh", "interface", "ip", "set", "address",
           f"name={nombre}", "static", ip, mask]
    if previa.get("gw"):
        cmd += [previa["gw"], "1"]
    res = run(cmd)
    if previa.get("dns"):
        run(["netsh", "interface", "ip", "set", "dns",
             f"name={nombre}", "static", previa["dns"]])
    dur_ms = round((time.perf_counter() - t0) * 1000)
    if res and res.returncode == 0:
        _log_op("revert", "ok", "", dur_ms, iface=nombre, ip=ip)
        return True, f"Revertido a {ip}"
    detalle = ((res.stderr or res.stdout) or "").strip() if res else ""
    _log_op("revert", "error", detalle or "netsh_fallo", dur_ms,
            iface=nombre, ip=ip)
    return False, (detalle or "No se pudo revertir")


# --- Estrategias de aplicación ----------------------------------------------
# Patrón Strategy en su forma pythónica: un Protocol (duck typing tipado) y
# dataclasses que empaquetan los parámetros y delegan en set_static/set_dhcp.
# aplicar() recibe el módulo de operaciones para que la UI pueda inyectar
# dobles en los tests, igual que hace con todo lo demás.
class EstrategiaRed(Protocol):
    def aplicar(self, ops, iface): ...


@dataclass
class IPFija:
    ip: str
    mask: str = "255.255.255.0"
    gw: str = ""
    dns: str = ""

    def aplicar(self, ops, iface):
        return ops.set_static(iface, self.ip, self.mask, self.gw, self.dns)


@dataclass
class DHCP:
    def aplicar(self, ops, iface):
        return ops.set_dhcp(iface)


def estrategia_de_perfil(p):
    """La estrategia que corresponde a un perfil guardado. Los perfiles de
    hoy son siempre de IP fija; un futuro {"modo": "dhcp"} ya tiene salida."""
    if p.get("modo") == "dhcp":
        return DHCP()
    return IPFija(p.get("ip", ""), p.get("mask", "255.255.255.0"),
                  p.get("gw", ""), p.get("dns", ""))
