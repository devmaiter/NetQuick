# -*- coding: utf-8 -*-
"""Tests de las funciones puras de netops (sin red ni admin)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netops  # noqa: E402


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
    assert netops._decodificar("Sí, está bien".encode("utf-8")) == "Sí, está bien"


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
