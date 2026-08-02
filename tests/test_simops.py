# -*- coding: utf-8 -*-
"""Tests of SimOps (issue #28): the simulated backend honors the netops
contract, and the real UI runs whole flows against it — including the
auto-revert rehearsal of #21 — without touching the network."""
import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netquick
import simops


# --- The backend alone -------------------------------------------------------
def test_set_static_mutates_the_simulated_state():
    sim = simops.SimOps()
    ok, _ = sim.set_static("Sim Ethernet", "10.0.0.60", "255.255.255.0",
                             "10.0.0.1", "8.8.8.8")
    assert ok
    assert sim.get_config("Sim Ethernet") == {
        "dhcp": False, "ip": "10.0.0.60", "mask": "255.255.255.0",
        "gw": "10.0.0.1", "dns": "8.8.8.8"}
    assert sim.list_interfaces() == [{"name": "Sim Ethernet", "ip": "10.0.0.60"}]


def test_occupied_ip_is_rejected_like_the_real_backend():
    sim = simops.SimOps()
    ok, msg = sim.set_static("Sim Ethernet", "10.0.0.7", "255.255.255.0")
    assert not ok and "already in use" in msg
    assert sim.config["ip"] != "10.0.0.7"


def test_preflight_is_the_same_as_netops():
    sim = simops.SimOps()
    ok, msg = sim.set_static("Sim Ethernet", "10.0.0.5", "255.255.255.0",
                             "192.168.99.1")
    assert not ok and "outside the subnet" in msg


def test_set_dhcp_returns_to_the_lease():
    sim = simops.SimOps()
    sim.set_static("Sim Ethernet", "10.0.0.60", "255.255.255.0")
    ok, _ = sim.set_dhcp("Sim Ethernet")
    assert ok and sim.config["dhcp"] and sim.config["ip"] == simops.DHCP_LEASE


def test_revert_to_restores_the_previous_static_config():
    sim = simops.SimOps()
    previous = sim.get_config("Sim Ethernet") | {
        "dhcp": False, "ip": "10.0.0.42"}
    ok, _ = sim.revert_to("Sim Ethernet", previous)
    assert ok and sim.config["ip"] == "10.0.0.42"


def test_scan_finds_neighbors_dante_and_self():
    sim = simops.SimOps()
    devices = sim.scan_network("Sim Ethernet")
    by_ip = {d["ip"]: d for d in devices}
    assert by_ip[sim.config["ip"]]["own"]
    assert by_ip["10.0.0.7"]["dante"] == "SimConsole"
    assert sim.mac_vendor(by_ip["10.0.0.7"]["mac"]) == "Audinate (Dante)"


def test_inject_raises_once_and_disarms():
    sim = simops.SimOps()
    sim.inject = RuntimeError("chaos")
    with pytest.raises(RuntimeError):
        sim.set_static("Sim Ethernet", "10.0.0.60", "255.255.255.0")
    ok, _ = sim.set_static("Sim Ethernet", "10.0.0.60", "255.255.255.0")
    assert ok


# --- Acceptance: the real UI against SimOps ----------------------------------
def _widget(monkeypatch):
    monkeypatch.setattr(netquick, "TRAY_AVAILABLE", False)
    sim = simops.SimOps()
    error = None
    for _ in range(3):
        try:
            return netquick.MiniWidget(ops=sim, store_mod=simops.SimStore()), sim
        except tk.TclError as e:
            error = e
    pytest.skip(f"Tkinter can't open windows in this environment: {error}")


def test_widget_starts_and_applying_ip_mutates_the_sim(monkeypatch):
    w, sim = _widget(monkeypatch)
    try:
        assert w._iface_name() == "Sim Ethernet"
        w._put(w.ip, "10.0.0.60")
        w._put(w.mask, "255.255.255.0")
        w._put(w.gw, "10.0.0.1")
        w._put(w.dns, "8.8.8.8")
        w.apply_ip()
        assert sim.config["ip"] == "10.0.0.60" and not sim.config["dhcp"]
        # ...and the UI reflects the simulated state after the refresh
        assert w._val(w.ip) == "10.0.0.60"
        assert "10.0.0.60" in w.status["text"]
    finally:
        w.root.destroy()


def test_widget_dhcp_mutates_the_sim(monkeypatch):
    w, sim = _widget(monkeypatch)
    try:
        w._put(w.ip, "10.0.0.60")
        w.apply_ip()
        w.apply_dhcp()
        assert sim.config["dhcp"] and sim.config["ip"] == simops.DHCP_LEASE
    finally:
        w.root.destroy()


def test_auto_revert_rehearsal_runs_entirely_in_the_sim(monkeypatch):
    """The #21 scenario as an automated test: apply a static IP whose gateway
    doesn't exist in the sim -> the countdown arms; when it expires the sim
    state goes back to the previous config. No network involved."""
    w, sim = _widget(monkeypatch)
    try:
        w._put(w.ip, "10.0.0.60")
        w._put(w.mask, "255.255.255.0")
        w._put(w.gw, "10.0.0.2")           # inside the subnet, but nobody there
        w._put(w.dns, "")
        w.apply_ip()
        assert sim.config["ip"] == "10.0.0.60"
        assert w._revert_previous is not None
        w._revert_remaining = 0
        w._revert_tick()
        assert sim.config["dhcp"] and sim.config["ip"] == simops.DHCP_LEASE
        assert w._revert_previous is None
    finally:
        w.root.destroy()
