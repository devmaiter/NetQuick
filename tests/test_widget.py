# -*- coding: utf-8 -*-
"""Tests de MiniWidget con un doble de netops (sin red, admin ni netsh).

La UI recibe las operaciones por parámetro (ops), así que aquí se le pasa
un FakeOps que responde en memoria: se prueba la lógica de la ventana sin
tocar el sistema. Si el entorno no puede abrir ventanas Tk (CI sin
escritorio), los tests se saltan.
"""
import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netquick


class FakeOps:
    """Mismo contrato que netops, con respuestas fijas y registro de llamadas."""

    def __init__(self, dhcp=False, interfaces=None, gw_responde=True):
        self.dhcp = dhcp
        self.interfaces = interfaces if interfaces is not None else \
            [{"nombre": "Ethernet", "ip": "10.0.0.5"}]
        self.gw_responde = gw_responde
        self.static_llamado = None
        self.dhcp_llamado = None
        self.revert_llamado = None

    def list_interfaces(self):
        return self.interfaces

    def get_config(self, nombre):
        return {"dhcp": self.dhcp, "ip": "10.0.0.5",
                "mask": "255.255.255.0", "gw": "10.0.0.1", "dns": "8.8.8.8"}

    def get_ip(self, nombre):
        return "10.0.0.5"

    def is_admin(self):
        return True

    def set_static(self, nombre, ip, mask, gw=None, dns=None):
        self.static_llamado = (nombre, ip, mask, gw, dns)
        return True, "IP aplicada"

    def set_dhcp(self, nombre):
        self.dhcp_llamado = nombre
        return True, "DHCP activado"

    def fabricante_mac(self, mac):
        return ""

    def gateway_responde(self, gw):
        return self.gw_responde

    def revertir_a(self, nombre, previa):
        self.revert_llamado = (nombre, previa)
        return True, f"Revertido a {previa.get('ip', '')}"


class FakeStore:
    """Persistencia en memoria: los tests no leen ni escriben JSON reales."""

    def __init__(self, profiles=None, config=None):
        self.profiles = profiles or {}
        self.config = config or {}

    def load_profiles(self):
        return dict(self.profiles)

    def load_config(self):
        return dict(self.config)

    def save_profiles(self, data):
        self.profiles = dict(data)

    def save_config(self, data):
        self.config = dict(data)


def _crear(monkeypatch, **kwargs):
    # Sin icono de bandeja en tests: evita hilos de pystray sueltos
    monkeypatch.setattr(netquick, "TRAY_DISPONIBLE", False)
    fake = FakeOps(**kwargs)
    # Crear intérpretes Tk seguidos en un mismo proceso a veces falla con
    # "invalid command name tcl_findLibrary" (carrera al inicializar Tcl):
    # se reintenta antes de dar el entorno por incapaz de abrir ventanas.
    error = None
    for _ in range(3):
        try:
            return netquick.MiniWidget(ops=fake, store_mod=FakeStore()), fake
        except tk.TclError as e:
            error = e
    pytest.skip(f"Tkinter no puede abrir ventanas en este entorno: {error}")


@pytest.fixture
def widget(monkeypatch):
    w, fake = _crear(monkeypatch)
    yield w, fake
    w.root.destroy()


def test_instanciar_no_bloquea(widget):
    w, _ = widget
    assert w.root.winfo_exists()


def test_refrescar_puebla_combo(widget):
    w, _ = widget
    assert w._map == {"Ethernet": "10.0.0.5"}
    assert w.iface.get() == "Ethernet — 10.0.0.5"
    assert w._iface_name() == "Ethernet"


def test_campos_reflejan_config(widget):
    w, _ = widget
    assert w._val(w.ip) == "10.0.0.5"
    assert w._val(w.mask) == "255.255.255.0"
    assert w._val(w.gw) == "10.0.0.1"
    assert w._val(w.dns) == "8.8.8.8"


def test_aplicar_ip_llama_set_static(widget):
    w, fake = widget
    w._put(w.ip, "192.168.1.50")
    w._put(w.mask, "255.255.255.0")
    w._put(w.gw, "192.168.1.1")
    w._put(w.dns, "8.8.8.8")
    w.aplicar_ip()
    assert fake.static_llamado == ("Ethernet", "192.168.1.50",
                                   "255.255.255.0", "192.168.1.1", "8.8.8.8")


def test_aplicar_dhcp_llama_set_dhcp(widget):
    w, fake = widget
    w.aplicar_dhcp()
    assert fake.dhcp_llamado == "Ethernet"


def test_sin_interfaces_no_toca_la_red(monkeypatch):
    w, fake = _crear(monkeypatch, interfaces=[])
    try:
        w.aplicar_ip()
        w.aplicar_dhcp()
        assert fake.static_llamado is None
        assert fake.dhcp_llamado is None
        assert "Sin interfaces" in w.status["text"] or "interfaz" in w.status["text"]
    finally:
        w.root.destroy()


def test_boton_dhcp_desactivado_en_modo_dhcp(monkeypatch):
    w, _ = _crear(monkeypatch, dhcp=True)
    try:
        assert str(w.btn_dhcp["state"]) == "disabled"
        assert "✔" in w.btn_dhcp["text"]
    finally:
        w.root.destroy()


def test_boton_aplicar_marca_ip_fija_sin_cambios(monkeypatch):
    # Con IP fija aplicada y sin ediciones pendientes, el botón queda
    # desactivado mostrando el estado (lógica de _update_mode_buttons)
    w, _ = _crear(monkeypatch, dhcp=False)
    try:
        assert str(w.btn_aplicar["state"]) == "disabled"
        assert "✔" in w.btn_aplicar["text"]
    finally:
        w.root.destroy()


def test_editar_campo_enciende_aplicar(widget):
    w, _ = widget
    w._put(w.ip, "192.168.99.99")
    w._update_mode_buttons()
    assert str(w.btn_aplicar["state"]) == "normal"
    assert w.btn_aplicar["text"] == "Aplicar IP"


# --- #21: aplicar → sin confirmación → auto-revert ----------------------------
def _aplicar_ip_mala(w):
    """Aplica una IP fija cuyo gateway no va a responder."""
    w._put(w.ip, "192.168.99.50")
    w._put(w.mask, "255.255.255.0")
    w._put(w.gw, "192.168.99.1")
    w._put(w.dns, "")
    w.aplicar_ip()


def test_config_sin_salida_arma_cuenta_regresiva(monkeypatch):
    w, _ = _crear(monkeypatch, gw_responde=False)
    try:
        _aplicar_ip_mala(w)
        assert w._revert_previa is not None
        assert w.revert_frame.winfo_manager()          # la barra está visible
        assert "Mantener" in w.btn_mantener["text"]
    finally:
        w.root.destroy()


def test_sin_confirmacion_revierte_a_la_config_previa(monkeypatch):
    """El criterio de aceptación del issue: aplicar a propósito una config
    sin salida y dejar vencer el temporizador revierte sola."""
    w, fake = _crear(monkeypatch, gw_responde=False)
    try:
        _aplicar_ip_mala(w)
        w._revert_restante = 0                          # vence el temporizador
        w._revert_tick()
        nombre, previa = fake.revert_llamado
        assert nombre == "Ethernet"
        assert previa["ip"] == "10.0.0.5"               # la config de antes
        assert w._revert_previa is None
        assert not w.revert_frame.winfo_manager()       # la barra se ocultó
        assert "restaurada" in w.status["text"]
    finally:
        w.root.destroy()


def test_confirmar_mantiene_el_cambio(monkeypatch):
    w, fake = _crear(monkeypatch, gw_responde=False)
    try:
        _aplicar_ip_mala(w)
        w._confirmar_cambio()
        assert fake.revert_llamado is None
        assert w._revert_previa is None
        assert "confirmado" in w.status["text"]
    finally:
        w.root.destroy()


def test_gateway_que_responde_no_pregunta(monkeypatch):
    w, _ = _crear(monkeypatch, gw_responde=True)
    try:
        _aplicar_ip_mala(w)
        assert w._revert_previa is None
        assert not w.revert_frame.winfo_manager()
    finally:
        w.root.destroy()


def test_aplicar_dhcp_cancela_la_cuenta_regresiva(monkeypatch):
    """El botón DHCP es el rescate manual: usarlo anula el auto-revert."""
    w, fake = _crear(monkeypatch, gw_responde=False)
    try:
        _aplicar_ip_mala(w)
        assert w._revert_previa is not None
        w.aplicar_dhcp()
        assert w._revert_previa is None
        assert fake.revert_llamado is None
    finally:
        w.root.destroy()
