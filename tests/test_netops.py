# -*- coding: utf-8 -*-
"""Tests of the pure netops functions (no network, no admin)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import netops


# --- is_valid_ip -------------------------------------------------------------
@pytest.mark.parametrize("value", [
    "192.168.1.1",
    "10.0.0.1",
    " 10.0.0.1 ",          # with spaces: they get trimmed
    "255.255.255.0",       # a mask is also a valid IPv4
    "0.0.0.0",
])
def test_is_valid_ip_accepts(value):
    assert netops.is_valid_ip(value)


@pytest.mark.parametrize("value", [
    "",
    "abc",
    "999.1.1.1",
    "192.168.1",           # incomplete
    "192.168.1.1.5",       # one octet too many
    "192.168.1.-1",
    None,
])
def test_is_valid_ip_rejects(value):
    assert not netops.is_valid_ip(value)


# --- _decode -----------------------------------------------------------------
def test_decode_empty():
    assert netops._decode(b"") == ""
    assert netops._decode(None) == ""


def test_decode_utf8():
    assert netops._decode("Sí, está bien".encode()) == "Sí, está bien"


def test_decode_oem():
    # Classic netsh answers in the OEM code page (cp850/cp437): the es-ES
    # accents fall in the range shared by both, so this test doesn't depend
    # on the locale of the machine running the tests.
    text = "Dirección física"
    assert netops._decode(text.encode("cp850")) == text


# --- _reg_ip -----------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    (["10.0.0.1\x00", "other"], "10.0.0.1"),
    ([], ""),
    ("10.0.0.1\x00", "10.0.0.1"),
    ("  10.0.0.1  ", "10.0.0.1"),
    (None, ""),
])
def test_reg_ip(value, expected):
    assert netops._reg_ip(value) == expected


# --- _mdns_name --------------------------------------------------------------
def test_mdns_name_literal():
    # DNS label: [len]MyConsole[len]_netaudio-arc[len]_udp[len]local[0]
    data = (b"\x00" * 12
            + bytes([9]) + b"MyConsole"
            + bytes([13]) + b"_netaudio-arc"
            + bytes([4]) + b"_udp"
            + bytes([5]) + b"local" + b"\x00")
    assert netops._mdns_name(data) == "MyConsole"


def test_mdns_name_no_name():
    assert netops._mdns_name(b"reply without the expected label") == ""
    assert netops._mdns_name(b"") == ""


# --- _parse_arp --------------------------------------------------------------
# Real output of 'arp -a' on a Spanish Windows: headers, dynamic/static
# entries, broadcast, multicast and junk that must be discarded.
ARP_SAMPLE = """
Interfaz: 10.0.0.5 --- 0x10
  Dirección de Internet          Dirección física      Tipo
  10.0.0.1              aa-bb-cc-00-11-22     dinámico
  10.0.0.7              00-1d-c1-33-44-55     dinámico
  10.0.0.255            ff-ff-ff-ff-ff-ff     estático
  224.0.0.251           01-00-5e-00-00-fb     estático
  192.168.50.9          11-22-33-44-55-66     dinámico
  not-an-ip             aa-aa-aa-aa-aa-aa     dinámico
"""


def test_parse_arp_no_network():
    table = netops._parse_arp(ARP_SAMPLE)
    assert table == {"10.0.0.1": "aa-bb-cc-00-11-22",
                     "10.0.0.7": "00-1d-c1-33-44-55",
                     "192.168.50.9": "11-22-33-44-55-66"}


def test_parse_arp_filters_by_subnet():
    import ipaddress
    network = ipaddress.ip_network("10.0.0.0/24")
    table = netops._parse_arp(ARP_SAMPLE, network)
    assert "192.168.50.9" not in table       # outside the subnet
    assert "10.0.0.255" not in table         # subnet broadcast
    assert set(table) == {"10.0.0.1", "10.0.0.7"}


def test_parse_arp_empty():
    assert netops._parse_arp("") == {}
    assert netops._parse_arp(None) == {}


# --- _combine_devices --------------------------------------------------------
def test_combine_sorts_and_marks_own():
    arp = {"10.0.0.20": "aa-aa-aa-aa-aa-01", "10.0.0.3": "aa-aa-aa-aa-aa-02"}
    devices = netops._combine_devices(arp, {}, "10.0.0.5")
    assert [d["ip"] for d in devices] == ["10.0.0.3", "10.0.0.5", "10.0.0.20"]
    assert [d["own"] for d in devices] == [False, True, False]


def test_combine_dante_outside_subnet_appears():
    # A Dante device with a wrong static IP isn't in ARP: it's included anyway
    devices = netops._combine_devices({}, {"169.254.3.3": "MyConsole"},
                                      "10.0.0.5")
    dante = next(d for d in devices if d["ip"] == "169.254.3.3")
    assert dante["dante"] == "MyConsole"


def test_combine_dante_without_name_says_dante():
    devices = netops._combine_devices({}, {"10.0.0.9": ""}, "10.0.0.5")
    assert next(d for d in devices if d["ip"] == "10.0.0.9")["dante"] == "Dante"


# --- _first_dns --------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("8.8.8.8,1.1.1.1", "8.8.8.8"),
    ("8.8.8.8 1.1.1.1", "8.8.8.8"),
    ("8.8.8.8", "8.8.8.8"),
    ("", ""),
])
def test_first_dns(text, expected):
    assert netops._first_dns(text) == expected


# --- _validate_static --------------------------------------------------------
@pytest.mark.parametrize("ip,mask,gw,dns,fragment", [
    ("not-an-ip", "255.255.255.0", "", "", "Invalid IP"),
    ("10.0.0.5", "1.2.3.4", "", "", "Invalid subnet mask"),
    ("10.0.0.5", "255.255.255.0", "not-a-gw", "", "Invalid gateway"),
    ("10.0.0.5", "255.255.255.0", "10.0.0.1", "not-a-dns", "Invalid DNS"),
])
def test_validate_static_detects_each_field(ip, mask, gw, dns, fragment):
    assert fragment in netops._validate_static(ip, mask, gw, dns)


def test_validate_static_accepts_all_valid():
    assert netops._validate_static("10.0.0.5", "255.255.255.0",
                                   "10.0.0.1", "8.8.8.8") is None
    assert netops._validate_static("10.0.0.5", "255.255.255.0", "", "") is None


# --- mac_vendor --------------------------------------------------------------
@pytest.mark.parametrize("mac,expected", [
    ("00-1d-c1-11-22-33", "Audinate (Dante)"),
    ("00-1D-C1-11-22-33", "Audinate (Dante)"),   # uppercase: normalized
    ("b8-27-eb-aa-bb-cc", "Raspberry Pi"),
    ("aa-bb-cc-dd-ee-ff", ""),                    # unknown OUI
    ("", ""),
    (None, ""),
])
def test_mac_vendor(mac, expected):
    assert netops.mac_vendor(mac) == expected


# --- Observability: every attempt is logged ---------------------------------
class _FakeRun:
    def __init__(self, rc, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_set_static_logs_validation_reject(monkeypatch, caplog):
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "not-an-ip", "255.255.255.0")
    line = "".join(r.message for r in caplog.records)
    assert "op=set_static" in line and "result=reject" in line


def test_set_static_logs_netsh_error(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_in_use", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _FakeRun(1, "denied"))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0")
    line = "".join(r.message for r in caplog.records)
    assert "result=error" in line


def test_set_static_logs_ok_with_duration(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_in_use", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _FakeRun(0))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0")
    line = "".join(r.message for r in caplog.records)
    assert "result=ok" in line and "dur_ms=" in line


# --- #22: don't report success with a half-done config (Rogers 2022) --------
def test_set_static_half_done_dns_does_not_report_success(monkeypatch):
    """If the IP is applied but DNS fails, the transaction is NOT a clean
    success: ok=False, and the message makes clear the IP yes, DNS no."""
    monkeypatch.setattr(netops, "ip_in_use", lambda ip: False)
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False:
                        _FakeRun(1) if "dns" in cmd else _FakeRun(0))
    ok, msg = netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0",
                                "", "8.8.8.8")
    assert ok is False
    assert "IP 10.0.0.5 applied" in msg and "DNS" in msg


def test_set_static_half_done_dns_logs_partial(monkeypatch, caplog):
    monkeypatch.setattr(netops, "ip_in_use", lambda ip: False)
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False:
                        _FakeRun(1) if "dns" in cmd else _FakeRun(0))
    with caplog.at_level("INFO", logger="netquick"):
        netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0", "", "8.8.8.8")
    assert "result=partial" in "".join(r.message for r in caplog.records)


def test_set_static_gateway_outside_subnet_is_warning_not_failure(monkeypatch):
    """A gateway outside the subnet IS a success (it may be intentional): the
    IP was applied; it's left as a warning, not a failure."""
    monkeypatch.setattr(netops, "ip_in_use", lambda ip: False)
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _FakeRun(0))
    ok, msg = netops.set_static("Ethernet", "10.0.0.5", "255.255.255.0",
                                "192.168.99.1", "")
    assert ok is True
    assert "gateway outside the subnet" in msg


# --- #20 / FM-2: check_ip with a directed ARP probe --------------------------
ARP_WITH_TARGET = """
Interfaz: 10.0.0.5 --- 0x10
  10.0.0.9              aa-bb-cc-00-11-22     dinámico
"""


def _no_ttl(cmd, quiet=False):
    """fake run(): ping with no reply and empty ARP cache."""
    return _FakeRun(1 if cmd[0] == "ping" else 0, "")


def test_check_ip_silent_host_appears_after_arp_probe(monkeypatch):
    """The FM-2 scenario: powered on, silent to ping and NOT yet in ARP. The
    directed ARP probe makes it appear -> in_use (previously: false negative)."""
    import ipaddress
    calls = {"arp": 0}

    def fake_run(cmd, quiet=False):
        if cmd[0] == "ping":
            return _FakeRun(1, "")
        calls["arp"] += 1
        # The 1st ARP read comes back empty; after _trigger_arp it shows up
        return _FakeRun(0, ARP_WITH_TARGET if calls["arp"] > 1 else "")

    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", fake_run)
    monkeypatch.setattr(netops, "_trigger_arp", lambda ip: None)
    monkeypatch.setattr(netops, "_local_subnets",
                        lambda: [ipaddress.ip_network("10.0.0.0/24")])
    assert netops.check_ip("10.0.0.9") == "in_use"


def test_check_ip_free_in_local_subnet(monkeypatch):
    import ipaddress
    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", _no_ttl)
    monkeypatch.setattr(netops, "_trigger_arp", lambda ip: None)
    monkeypatch.setattr(netops, "_local_subnets",
                        lambda: [ipaddress.ip_network("10.0.0.0/24")])
    assert netops.check_ip("10.0.0.9") == "free"


def test_check_ip_outside_subnet_does_not_fake_certainty(monkeypatch):
    """Outside the local subnets there is no ARP available: if ping is silent,
    the honest answer is 'unverified', not 'free'."""
    monkeypatch.setattr(netops, "list_interfaces", lambda: [])
    monkeypatch.setattr(netops, "run", _no_ttl)
    monkeypatch.setattr(netops, "_local_subnets", lambda: [])
    assert netops.check_ip("192.168.77.9") == "unverified"


def test_check_ip_own_is_free(monkeypatch):
    monkeypatch.setattr(netops, "list_interfaces",
                        lambda: [{"name": "Ethernet", "ip": "10.0.0.5"}])
    assert netops.check_ip("10.0.0.5") == "free"


def test_set_static_unverified_applies_with_warning(monkeypatch):
    monkeypatch.setattr(netops, "check_ip", lambda ip: "unverified")
    monkeypatch.setattr(netops, "run", lambda cmd, quiet=False: _FakeRun(0))
    ok, msg = netops.set_static("Ethernet", "192.168.77.9", "255.255.255.0")
    assert ok is True
    assert "could not verify" in msg


# --- #21: emergency revert and gateway verification --------------------------
def test_gateway_responds_requires_ttl(monkeypatch):
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: _FakeRun(0, "Reply TTL=64"))
    assert netops.gateway_responds("10.0.0.1")
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: _FakeRun(0, "unreachable"))
    assert not netops.gateway_responds("10.0.0.1")
    assert not netops.gateway_responds("")


def test_revert_to_static_uses_direct_netsh_without_check_ip(monkeypatch):
    """The rescue takes the dumbest path possible: direct netsh, without going
    through check_ip or validation (the previous config was already applied)."""
    commands = []

    def fake_run(cmd, quiet=False):
        commands.append(cmd)
        return _FakeRun(0)

    def _boom(ip):
        raise AssertionError("the revert must not consult the network")

    monkeypatch.setattr(netops, "run", fake_run)
    monkeypatch.setattr(netops, "check_ip", _boom)
    ok, _ = netops.revert_to("Ethernet", {
        "dhcp": False, "ip": "10.0.0.5", "mask": "255.255.255.0",
        "gw": "10.0.0.1", "dns": "8.8.8.8"})
    assert ok
    assert commands[0] == ["netsh", "interface", "ip", "set", "address",
                           "name=Ethernet", "static", "10.0.0.5",
                           "255.255.255.0", "10.0.0.1", "1"]
    assert commands[1][:6] == ["netsh", "interface", "ip", "set", "dns",
                               "name=Ethernet"]


def test_revert_to_dhcp_or_no_data_falls_back_to_dhcp(monkeypatch):
    commands = []
    monkeypatch.setattr(netops, "run",
                        lambda cmd, quiet=False: commands.append(cmd)
                        or _FakeRun(0))
    ok, _ = netops.revert_to("Ethernet", {"dhcp": True})
    assert ok and "dhcp" in commands[0]
    commands.clear()
    ok, _ = netops.revert_to("Ethernet", {})   # empty previous: known-good
    assert ok and "dhcp" in commands[0]


# --- Strategies --------------------------------------------------------------
class _RecordingOps:
    """Minimal double: records which operation was asked and with what args."""

    def set_static(self, iface, ip, mask, gw, dns):
        self.static = (iface, ip, mask, gw, dns)
        return True, "ok"

    def set_dhcp(self, iface):
        self.dhcp = iface
        return True, "ok"


def test_static_ip_delegates_to_set_static():
    ops = _RecordingOps()
    ok, _ = netops.StaticIP("10.0.0.5", "255.255.255.0",
                            "10.0.0.1", "8.8.8.8").apply(ops, "Ethernet")
    assert ok
    assert ops.static == ("Ethernet", "10.0.0.5", "255.255.255.0",
                          "10.0.0.1", "8.8.8.8")


def test_dhcp_delegates_to_set_dhcp():
    ops = _RecordingOps()
    ok, _ = netops.DHCP().apply(ops, "Wi-Fi")
    assert ok
    assert ops.dhcp == "Wi-Fi"


def test_strategy_from_profile_defaults_to_static_ip():
    e = netops.strategy_from_profile({"ip": "10.0.0.5", "gw": "10.0.0.1"})
    assert isinstance(e, netops.StaticIP)
    assert (e.ip, e.mask, e.gw, e.dns) == ("10.0.0.5", "255.255.255.0",
                                           "10.0.0.1", "")


def test_strategy_from_profile_mode_dhcp():
    assert isinstance(netops.strategy_from_profile({"mode": "dhcp"}),
                      netops.DHCP)


# --- set_static: validation (returns BEFORE touching the network) ------------
@pytest.mark.parametrize("ip,mask,gw", [
    ("not-an-ip", "255.255.255.0", ""),
    ("10.0.0.5", "not-a-mask", ""),
    ("10.0.0.5", "255.255.255.0", "not-a-gw"),
    ("", "255.255.255.0", ""),
])
def test_set_static_rejects_invalid_input(ip, mask, gw):
    ok, msg = netops.set_static("Ethernet", ip, mask, gw)
    assert not ok
    assert msg
