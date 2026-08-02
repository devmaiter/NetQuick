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

    def __init__(self, dhcp=False, interfaces=None, gw_responds=True,
                 static_exc=None, scan_exc=None, revert_exc=None):
        self.dhcp = dhcp
        self.interfaces = interfaces if interfaces is not None else \
            [{"name": "Ethernet", "ip": "10.0.0.5"}]
        self.gw_responds = gw_responds
        self.static_exc = static_exc
        self.scan_exc = scan_exc
        self.revert_exc = revert_exc
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
        if self.static_exc:
            raise self.static_exc
        self.static_called = (name, ip, mask, gw, dns)
        return True, "IP applied"

    def scan_network(self, name, timeout_ms=250):
        if self.scan_exc:
            raise self.scan_exc
        return [{"ip": "10.0.0.5", "mac": "", "own": True, "dante": None}]

    def set_dhcp(self, name):
        self.dhcp_called = name
        return True, "DHCP enabled"

    def mac_vendor(self, mac):
        return ""

    def gateway_responds(self, gw):
        return self.gw_responds

    def revert_to(self, name, previous):
        if self.revert_exc:
            raise self.revert_exc
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


# --- #25: an unexpected failure must not leave the widget zombie --------------
def test_arbitrary_exception_in_apply_leaves_widget_usable(monkeypatch, caplog):
    """The issue's acceptance criterion: FakeOps blows up with an arbitrary
    exception; the widget stays usable (buttons enabled, honest message) and
    the error lands in the structured log — never a silent traceback."""
    w, _ = _create(monkeypatch, static_exc=RuntimeError("chaos"))
    try:
        w._put(w.ip, "192.168.1.50")
        with caplog.at_level("ERROR", logger="netquick"):
            w.apply_ip()                       # must NOT raise
        assert "✗" in w.status["text"]
        assert str(w.btn_apply["state"]) == "normal"
        assert str(w.btn_dhcp["state"]) == "normal"
        line = "".join(r.message for r in caplog.records)
        assert "op=ui_apply" in line and "result=error" in line
        assert any("chaos" in (r.exc_text or "") for r in caplog.records)
    finally:
        w.root.destroy()


def test_exception_during_revert_reports_and_survives(monkeypatch, caplog):
    w, _ = _create(monkeypatch, gw_responds=False,
                   revert_exc=RuntimeError("chaos"))
    try:
        _apply_bad_ip(w)
        w._revert_remaining = 0
        with caplog.at_level("ERROR", logger="netquick"):
            w._revert_tick()                   # must NOT raise
        assert "Could not revert" in w.status["text"]
        assert w._revert_previous is None      # the countdown is disarmed
        assert "op=ui_revert" in "".join(r.message for r in caplog.records)
    finally:
        w.root.destroy()


class _SyncThread:
    """Runs the scanner 'thread' inline so the test is deterministic."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _find_widgets(root, cls):
    found = []
    for child in root.winfo_children():
        if isinstance(child, cls):
            found.append(child)
        found.extend(_find_widgets(child, cls))
    return found


def test_exception_in_scanner_reenables_and_says_so(monkeypatch, caplog):
    """The real zombie: the scan thread dies -> 'Scanning…' and a disabled
    Rescan button forever. Supervised: button back, clear message, logged."""
    w, _ = _create(monkeypatch, scan_exc=RuntimeError("chaos"))
    try:
        monkeypatch.setattr(netquick.threading, "Thread", _SyncThread)
        with caplog.at_level("ERROR", logger="netquick"):
            w.open_scanner()
            w.root.update()                    # delivers the after(0, finish)
        win = _find_widgets(w.root, tk.Toplevel)[0]
        rescan = next(b for b in _find_widgets(win, tk.Button)
                      if "Rescan" in b["text"])
        assert str(rescan["state"]) == "normal"
        labels = [lb["text"] for lb in _find_widgets(win, tk.Label)]
        assert any("scan failed" in t for t in labels)
        assert "op=ui_scan" in "".join(r.message for r in caplog.records)
    finally:
        w.root.destroy()
