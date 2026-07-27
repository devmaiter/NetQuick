# -*- coding: utf-8 -*-
"""Tests of MiniWidget with a netops double (no network, admin or netsh).

The UI receives its operations as a parameter (ops), so here it's given a
FakeOps that answers in memory: the window logic is tested without touching
the system. If the environment can't open Tk windows (headless CI), the
tests are skipped.
"""
import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netquick


class FakeOps:
    """Same contract as netops, with fixed answers and call recording."""

    def __init__(self, dhcp=False, interfaces=None, gw_responds=True):
        self.dhcp = dhcp
        self.interfaces = interfaces if interfaces is not None else \
            [{"name": "Ethernet", "ip": "10.0.0.5"}]
        self.gw_responds = gw_responds
        self.static_called = None
        self.dhcp_called = None
        self.revert_called = None

    def list_interfaces(self):
        return self.interfaces

    def get_config(self, name):
        return {"dhcp": self.dhcp, "ip": "10.0.0.5",
                "mask": "255.255.255.0", "gw": "10.0.0.1", "dns": "8.8.8.8"}

    def get_ip(self, name):
        return "10.0.0.5"

    def is_admin(self):
        return True

    def set_static(self, name, ip, mask, gw=None, dns=None):
        self.static_called = (name, ip, mask, gw, dns)
        return True, "IP applied"

    def set_dhcp(self, name):
        self.dhcp_called = name
        return True, "DHCP enabled"

    def mac_vendor(self, mac):
        return ""

    def gateway_responds(self, gw):
        return self.gw_responds

    def revert_to(self, name, previous):
        self.revert_called = (name, previous)
        return True, f"Reverted to {previous.get('ip', '')}"


class FakeStore:
    """In-memory persistence: the tests don't read or write real JSON."""

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


def _create(monkeypatch, **kwargs):
    # No tray icon in tests: avoids stray pystray threads
    monkeypatch.setattr(netquick, "TRAY_AVAILABLE", False)
    fake = FakeOps(**kwargs)
    # Creating several Tk interpreters in a row in one process sometimes fails
    # with "invalid command name tcl_findLibrary" (a race initializing Tcl):
    # retry before declaring the environment unable to open windows.
    error = None
    for _ in range(3):
        try:
            return netquick.MiniWidget(ops=fake, store_mod=FakeStore()), fake
        except tk.TclError as e:
            error = e
    pytest.skip(f"Tkinter can't open windows in this environment: {error}")


@pytest.fixture
def widget(monkeypatch):
    w, fake = _create(monkeypatch)
    yield w, fake
    w.root.destroy()


def test_instantiating_does_not_block(widget):
    w, _ = widget
    assert w.root.winfo_exists()


def test_refresh_populates_combo(widget):
    w, _ = widget
    assert w._map == {"Ethernet": "10.0.0.5"}
    assert w.iface.get() == "Ethernet — 10.0.0.5"
    assert w._iface_name() == "Ethernet"


def test_fields_reflect_config(widget):
    w, _ = widget
    assert w._val(w.ip) == "10.0.0.5"
    assert w._val(w.mask) == "255.255.255.0"
    assert w._val(w.gw) == "10.0.0.1"
    assert w._val(w.dns) == "8.8.8.8"


def test_apply_ip_calls_set_static(widget):
    w, fake = widget
    w._put(w.ip, "192.168.1.50")
    w._put(w.mask, "255.255.255.0")
    w._put(w.gw, "192.168.1.1")
    w._put(w.dns, "8.8.8.8")
    w.apply_ip()
    assert fake.static_called == ("Ethernet", "192.168.1.50",
                                  "255.255.255.0", "192.168.1.1", "8.8.8.8")


def test_apply_dhcp_calls_set_dhcp(widget):
    w, fake = widget
    w.apply_dhcp()
    assert fake.dhcp_called == "Ethernet"


def test_no_interfaces_does_not_touch_network(monkeypatch):
    w, fake = _create(monkeypatch, interfaces=[])
    try:
        w.apply_ip()
        w.apply_dhcp()
        assert fake.static_called is None
        assert fake.dhcp_called is None
        assert ("No active interfaces" in w.status["text"]
                or "interface" in w.status["text"])
    finally:
        w.root.destroy()


def test_dhcp_button_disabled_in_dhcp_mode(monkeypatch):
    w, _ = _create(monkeypatch, dhcp=True)
    try:
        assert str(w.btn_dhcp["state"]) == "disabled"
        assert "✔" in w.btn_dhcp["text"]
    finally:
        w.root.destroy()


def test_apply_button_marks_static_ip_without_changes(monkeypatch):
    # With a static IP applied and no pending edits, the button stays disabled
    # showing the state (_update_mode_buttons logic)
    w, _ = _create(monkeypatch, dhcp=False)
    try:
        assert str(w.btn_apply["state"]) == "disabled"
        assert "✔" in w.btn_apply["text"]
    finally:
        w.root.destroy()


def test_editing_field_lights_up_apply(widget):
    w, _ = widget
    w._put(w.ip, "192.168.99.99")
    w._update_mode_buttons()
    assert str(w.btn_apply["state"]) == "normal"
    assert w.btn_apply["text"] == "Apply IP"


# --- #21: apply → no confirmation → auto-revert ------------------------------
def _apply_bad_ip(w):
    """Apply a static IP whose gateway won't respond."""
    w._put(w.ip, "192.168.99.50")
    w._put(w.mask, "255.255.255.0")
    w._put(w.gw, "192.168.99.1")
    w._put(w.dns, "")
    w.apply_ip()


def test_config_without_way_out_arms_countdown(monkeypatch):
    w, _ = _create(monkeypatch, gw_responds=False)
    try:
        _apply_bad_ip(w)
        assert w._revert_previous is not None
        assert w.revert_frame.winfo_manager()          # the bar is visible
        assert "Keep" in w.btn_keep["text"]
    finally:
        w.root.destroy()


def test_no_confirmation_reverts_to_previous_config(monkeypatch):
    """The issue's acceptance criterion: apply a config without a way out on
    purpose and let the timer expire — it reverts on its own."""
    w, fake = _create(monkeypatch, gw_responds=False)
    try:
        _apply_bad_ip(w)
        w._revert_remaining = 0                          # the timer expires
        w._revert_tick()
        name, previous = fake.revert_called
        assert name == "Ethernet"
        assert previous["ip"] == "10.0.0.5"              # the previous config
        assert w._revert_previous is None
        assert not w.revert_frame.winfo_manager()        # the bar hid itself
        assert "restored" in w.status["text"]
    finally:
        w.root.destroy()


def test_confirming_keeps_the_change(monkeypatch):
    w, fake = _create(monkeypatch, gw_responds=False)
    try:
        _apply_bad_ip(w)
        w._confirm_change()
        assert fake.revert_called is None
        assert w._revert_previous is None
        assert "confirmed" in w.status["text"]
    finally:
        w.root.destroy()


def test_responding_gateway_does_not_ask(monkeypatch):
    w, _ = _create(monkeypatch, gw_responds=True)
    try:
        _apply_bad_ip(w)
        assert w._revert_previous is None
        assert not w.revert_frame.winfo_manager()
    finally:
        w.root.destroy()


def test_apply_dhcp_cancels_the_countdown(monkeypatch):
    """The DHCP button is the manual rescue: using it cancels the auto-revert."""
    w, fake = _create(monkeypatch, gw_responds=False)
    try:
        _apply_bad_ip(w)
        assert w._revert_previous is not None
        w.apply_dhcp()
        assert w._revert_previous is None
        assert fake.revert_called is None
    finally:
        w.root.destroy()
