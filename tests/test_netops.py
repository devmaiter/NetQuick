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
