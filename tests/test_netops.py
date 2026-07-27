# -*- coding: utf-8 -*-
"""Tests de las funciones puras de netops (sin red ni admin)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netops


# --- ip_valida ---------------------------------------------------------------
@pytest.mark.parametrize("valor", [
    "192.168.1.1",
    "10.0.0.1",
    " 10.0.0.1 ",          # con espacios: se limpian
    "255.255.255.0",       # una máscara también es una IPv4 válida
    "0.0.0.0",
])
def test_ip_valida_acepta(valor):
    assert netops.ip_valida(valor)


@pytest.mark.parametrize("valor", [
    "",
    "abc",
    "999.1.1.1",
    "192.168.1",           # incompleta
    "192.168.1.1.5",       # sobra un octeto
    "192.168.1.-1",
    None,
])
def test_ip_valida_rechaza(valor):
    assert not netops.ip_valida(valor)


# --- _decodificar ------------------------------------------------------------
def test_decodificar_vacio():
    assert netops._decodificar(b"") == ""
    assert netops._decodificar(None) == ""


def test_decodificar_utf8():
    assert netops._decodificar("Sí, está bien".encode()) == "Sí, está bien"


def test_decodificar_oem():
    # netsh clásico responde en la página OEM (cp850/cp437): los acentos de
    # es-ES caen en el rango compartido por ambas, así el test no depende
    # del locale de la máquina que corre los tests.
    texto = "Dirección física"
    assert netops._decodificar(texto.encode("cp850")) == texto


# --- _reg_ip -----------------------------------------------------------------
@pytest.mark.parametrize("valor,esperado", [
    (["10.0.0.1\x00", "otra"], "10.0.0.1"),
    ([], ""),
    ("10.0.0.1\x00", "10.0.0.1"),
    ("  10.0.0.1  ", "10.0.0.1"),
    (None, ""),
])
def test_reg_ip(valor, esperado):
    assert netops._reg_ip(valor) == esperado


# --- _nombre_mdns ------------------------------------------------------------
def test_nombre_mdns_literal():
    # Etiqueta DNS: [len]MiConsola[len]_netaudio-arc[len]_udp[len]local[0]
    datos = (b"\x00" * 12
             + bytes([9]) + b"MiConsola"
             + bytes([13]) + b"_netaudio-arc"
             + bytes([4]) + b"_udp"
             + bytes([5]) + b"local" + b"\x00")
    assert netops._nombre_mdns(datos) == "MiConsola"


def test_nombre_mdns_sin_nombre():
    assert netops._nombre_mdns(b"respuesta sin la etiqueta esperada") == ""
    assert netops._nombre_mdns(b"") == ""


# --- _parsear_arp ------------------------------------------------------------
# Salida real de 'arp -a' en Windows en español: cabeceras, entradas
# dinámicas/estáticas, broadcast, multicast y basura que hay que descartar.
ARP_EJEMPLO = """
Interfaz: 10.0.0.5 --- 0x10
  Dirección de Internet          Dirección física      Tipo
  10.0.0.1              aa-bb-cc-00-11-22     dinámico
  10.0.0.7              00-1d-c1-33-44-55     dinámico
  10.0.0.255            ff-ff-ff-ff-ff-ff     estático
  224.0.0.251           01-00-5e-00-00-fb     estático
  192.168.50.9          11-22-33-44-55-66     dinámico
  no-es-ip              aa-aa-aa-aa-aa-aa     dinámico
"""


def test_parsear_arp_sin_red():
    tabla = netops._parsear_arp(ARP_EJEMPLO)
    assert tabla == {"10.0.0.1": "aa-bb-cc-00-11-22",
                     "10.0.0.7": "00-1d-c1-33-44-55",
                     "192.168.50.9": "11-22-33-44-55-66"}


def test_parsear_arp_filtra_por_subred():
    import ipaddress
    red = ipaddress.ip_network("10.0.0.0/24")
    tabla = netops._parsear_arp(ARP_EJEMPLO, red)
    assert "192.168.50.9" not in tabla       # fuera de la subred
    assert "10.0.0.255" not in tabla         # broadcast de la subred
    assert set(tabla) == {"10.0.0.1", "10.0.0.7"}


def test_parsear_arp_vacio():
    assert netops._parsear_arp("") == {}
    assert netops._parsear_arp(None) == {}


# --- _combinar_dispositivos --------------------------------------------------
def test_combinar_ordena_y_marca_propia():
    arp = {"10.0.0.20": "aa-aa-aa-aa-aa-01", "10.0.0.3": "aa-aa-aa-aa-aa-02"}
    lista = netops._combinar_dispositivos(arp, {}, "10.0.0.5")
    assert [d["ip"] for d in lista] == ["10.0.0.3", "10.0.0.5", "10.0.0.20"]
    assert [d["propia"] for d in lista] == [False, True, False]


def test_combinar_dante_fuera_de_subred_aparece():
    # Un equipo Dante con IP fija equivocada no está en ARP: entra igual
    lista = netops._combinar_dispositivos({}, {"169.254.3.3": "MiConsola"},
                                          "10.0.0.5")
    dante = next(d for d in lista if d["ip"] == "169.254.3.3")
    assert dante["dante"] == "MiConsola"


def test_combinar_dante_sin_nombre_dice_dante():
    lista = netops._combinar_dispositivos({}, {"10.0.0.9": ""}, "10.0.0.5")
    assert next(d for d in lista if d["ip"] == "10.0.0.9")["dante"] == "Dante"


# --- _primer_dns -------------------------------------------------------------
@pytest.mark.parametrize("cadena,esperado", [
    ("8.8.8.8,1.1.1.1", "8.8.8.8"),
    ("8.8.8.8 1.1.1.1", "8.8.8.8"),
    ("8.8.8.8", "8.8.8.8"),
    ("", ""),
])
def test_primer_dns(cadena, esperado):
    assert netops._primer_dns(cadena) == esperado


# --- _validar_static ---------------------------------------------------------
@pytest.mark.parametrize("ip,mask,gw,dns,fragmento", [
    ("no-es-ip", "255.255.255.0", "", "", "IP no válida"),
    ("10.0.0.5", "1.2.3.4", "", "", "Máscara no válida"),
    ("10.0.0.5", "255.255.255.0", "no-es-gw", "", "Gateway no válido"),
    ("10.0.0.5", "255.255.255.0", "10.0.0.1", "no-es-dns", "DNS no válido"),
])
def test_validar_static_detecta_cada_campo(ip, mask, gw, dns, fragmento):
    assert fragmento in netops._validar_static(ip, mask, gw, dns)


def test_validar_static_acepta_todo_valido():
    assert netops._validar_static("10.0.0.5", "255.255.255.0",
                                  "10.0.0.1", "8.8.8.8") is None
    assert netops._validar_static("10.0.0.5", "255.255.255.0", "", "") is None


# --- fabricante_mac ----------------------------------------------------------
@pytest.mark.parametrize("mac,esperado", [
    ("00-1d-c1-11-22-33", "Audinate (Dante)"),
    ("00-1D-C1-11-22-33", "Audinate (Dante)"),   # mayúsculas: se normaliza
    ("b8-27-eb-aa-bb-cc", "Raspberry Pi"),
    ("aa-bb-cc-dd-ee-ff", ""),                    # OUI desconocido
    ("", ""),
    (None, ""),
])
def test_fabricante_mac(mac, esperado):
    assert netops.fabricante_mac(mac) == esperado


# --- Observabilidad: cada intento se loggea (cierra el sesgo de la Fase 5) ---
class _RunFalso:
    def __init__(self, rc, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_set_static_loggea_rechazo_de_validacion(monkeypatch, caplog):
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "no-es-ip", "255.255.255.0")
    linea = "".join(r.message for r in caplog.records)
    assert "op=set_static" in linea and "resultado=rechazo" in linea


def test_set_static_loggea_error_de_netsh(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_en_uso", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _RunFalso(1, "denegado"))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0")
    linea = "".join(r.message for r in caplog.records)
    assert "resultado=error" in linea


def test_set_static_loggea_ok_con_duracion(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_en_uso", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _RunFalso(0))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0")
    linea = "".join(r.message for r in caplog.records)
    assert "resultado=ok" in linea and "dur_ms=" in linea


# --- #22: no reportar éxito con la config a medias (lección Rogers 2022) ------
def test_set_static_dns_a_medias_no_reporta_exito(monkeypatch):
    """Si la IP se aplica pero el DNS falla, la transacción NO es un éxito
    limpio: ok=False, y el mensaje deja claro que la IP sí y el DNS no."""
    monkeypatch.setattr(netops, "ip_en_uso", lambda ip: False)
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False:
                        _RunFalso(1) if "dns" in cmd else _RunFalso(0))
    ok, msg = netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0",
                                "", "8.8.8.8")
    assert ok is False
    assert "IP 10.0.0.5 aplicada" in msg and "DNS" in msg


def test_set_static_dns_a_medias_loggea_parcial(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_en_uso", lambda ip: False)
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False:
                        _RunFalso(1) if "dns" in cmd else _RunFalso(0))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0", "", "8.8.8.8")
    assert "resultado=parcial" in "".join(r.message for r in caplog.records)


def test_set_static_gateway_fuera_de_subred_es_aviso_no_fallo(monkeypatch):
    """Gateway fuera de la subred SÍ es un éxito (puede ser intencional): la
    IP se aplicó; queda como aviso, no como fallo."""
    monkeypatch.setattr(netops, "ip_en_uso", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _RunFalso(0))
    ok, msg = netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0",
                                "192.168.99.1", "")
    assert ok is True
    assert "gateway fuera de la subred" in msg


# --- #20 / FM-2: verificar_ip con sonda ARP dirigida --------------------------
ARP_CON_OBJETIVO = """
Interfaz: 10.0.0.5 --- 0x10
  10.0.0.9              aa-bb-cc-00-11-22     dinámico
"""


def _sin_ttl(cmd, quiet=False):
    """run() falso: ping sin respuesta y caché ARP vacía."""
    return _RunFalso(1 if cmd[0] == "ping" else 0, "")


def test_verificar_ip_equipo_silencioso_aparece_tras_sonda_arp(monkeypatch):
    """El escenario FM-2: encendido, calla al ping y NO está aún en ARP.
    La sonda ARP dirigida lo hace aparecer -> en_uso (antes: falso negativo)."""
    import ipaddress
    llamadas = {"arp": 0}

    def run_falso(cmd, quiet=False):
        if cmd[0] == "ping":
            return _RunFalso(1, "")
        llamadas["arp"] += 1
        # La 1ª lectura de ARP viene vacía; tras _provocar_arp ya aparece
        return _RunFalso(0, ARP_CON_OBJETIVO if llamadas["arp"] > 1 else "")

    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", run_falso)
    monkeypatch.setattr(netops, "_provocar_arp", lambda ip: None)
    monkeypatch.setattr(netops, "_subredes_locales",
                        lambda: [ipaddress.ip_network("10.0.0.0/24")])
    assert netops.verificar_ip("10.0.0.9") == "en_uso"


def test_verificar_ip_libre_en_subred_local(monkeypatch):
    import ipaddress
    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", _sin_ttl)
    monkeypatch.setattr(netops, "_provocar_arp", lambda ip: None)
    monkeypatch.setattr(netops, "_subredes_locales",
                        lambda: [ipaddress.ip_network("10.0.0.0/24")])
    assert netops.verificar_ip("10.0.0.9") == "libre"


def test_verificar_ip_fuera_de_subred_no_finge_certeza(monkeypatch):
    """Fuera de las subredes locales no hay ARP posible: si el ping calla,
    la respuesta honesta es 'sin_verificar', no 'libre'."""
    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", _sin_ttl)
    monkeypatch.setattr(netops, "_subredes_locales", lambda: [])
    assert netops.verificar_ip("192.168.77.9") == "sin_verificar"


def test_verificar_ip_propia_es_libre(monkeypatch):
    monkeypatch.setattr(netops, "list_interfaces",
                        lambda: [{"nombre": "Ethernet", "ip": "10.0.0.5"}])
    assert netops.verificar_ip("10.0.0.5") == "libre"


def test_set_static_sin_verificar_aplica_con_aviso(monkeypatch):
    monkeypatch.setattr(netops, "verificar_ip", lambda ip: "sin_verificar")
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _RunFalso(0))
    ok, msg = netops.set_static("Ethernet", "192.168.77.9", "255.255.255.0")
    assert ok is True
    assert "no se pudo verificar" in msg


# --- #21: revert de emergencia y verificación de gateway ----------------------
def test_gateway_responde_exige_ttl(monkeypatch):
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: _RunFalso(0, "Respuesta TTL=64"))
    assert netops.gateway_responde("10.0.0.1")
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: _RunFalso(0, "inaccesible"))
    assert not netops.gateway_responde("10.0.0.1")
    assert not netops.gateway_responde("")


def test_revertir_a_estatica_usa_netsh_directo_sin_verificar_ip(monkeypatch):
    """El rescate va por el camino más tonto posible: netsh directo, sin
    pasar por verificar_ip ni validación (la config previa ya estuvo puesta)."""
    comandos = []

    def run_falso(cmd, quiet=False):
        comandos.append(cmd)
        return _RunFalso(0)

    def _boom(ip):
        raise AssertionError("el revert no debe consultar la red")

    monkeypatch.setattr(netops, "run", run_falso)
    monkeypatch.setattr(netops, "verificar_ip", _boom)
    ok, _ = netops.revertir_a("Ethernet", {
        "dhcp": False, "ip": "10.0.0.5", "mask": "255.255.255.0",
        "gw": "10.0.0.1", "dns": "8.8.8.8"})
    assert ok
    assert comandos[0] == ["netsh", "interface", "ip", "set", "address",
                           "name=Ethernet", "static", "10.0.0.5",
                           "255.255.255.0", "10.0.0.1", "1"]
    assert comandos[1][:6] == ["netsh", "interface", "ip", "set", "dns",
                               "name=Ethernet"]


def test_revertir_a_dhcp_o_sin_datos_cae_a_dhcp(monkeypatch):
    comandos = []
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: comandos.append(cmd)
                        or _RunFalso(0))
    ok, _ = netops.revertir_a("Ethernet", {"dhcp": True})
    assert ok and "dhcp" in comandos[0]
    comandos.clear()
    ok, _ = netops.revertir_a("Ethernet", {})   # previa vacía: conocido-bueno
    assert ok and "dhcp" in comandos[0]


# --- Estrategias -------------------------------------------------------------
class _OpsRegistro:
    """Doble mínimo: registra qué operación se pidió y con qué argumentos."""

    def set_static(self, iface, ip, mask, gw, dns):
        self.static = (iface, ip, mask, gw, dns)
        return True, "ok"

    def set_dhcp(self, iface):
        self.dhcp = iface
        return True, "ok"


def test_ip_fija_delega_en_set_static():
    ops = _OpsRegistro()
    ok, _ = netops.IPFija("10.0.0.5", "255.255.255.0",
                          "10.0.0.1", "8.8.8.8").aplicar(ops, "Ethernet")
    assert ok
    assert ops.static == ("Ethernet", "10.0.0.5", "255.255.255.0",
                          "10.0.0.1", "8.8.8.8")


def test_dhcp_delega_en_set_dhcp():
    ops = _OpsRegistro()
    ok, _ = netops.DHCP().aplicar(ops, "Wi-Fi")
    assert ok
    assert ops.dhcp == "Wi-Fi"


def test_estrategia_de_perfil_por_defecto_ip_fija():
    e = netops.estrategia_de_perfil({"ip": "10.0.0.5", "gw": "10.0.0.1"})
    assert isinstance(e, netops.IPFija)
    assert (e.ip, e.mask, e.gw, e.dns) == ("10.0.0.5", "255.255.255.0",
                                           "10.0.0.1", "")


def test_estrategia_de_perfil_modo_dhcp():
    assert isinstance(netops.estrategia_de_perfil({"modo": "dhcp"}),
                      netops.DHCP)


# --- set_static: validación (retorna ANTES de tocar la red) ------------------
@pytest.mark.parametrize("ip,mask,gw", [
    ("no-es-ip", "255.255.255.0", ""),
    ("10.0.0.5", "no-es-mascara", ""),
    ("10.0.0.5", "255.255.255.0", "no-es-gw"),
    ("", "255.255.255.0", ""),
])
def test_set_static_rechaza_entradas_invalidas(ip, mask, gw):
    ok, msg = netops.set_static("Ethernet", ip, mask, gw)
    assert not ok
    assert msg
