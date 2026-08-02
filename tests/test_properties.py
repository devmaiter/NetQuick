# -*- coding: utf-8 -*-
"""Property-based tests of the pure netops parsers/validators (issue #23).

Generated cases instead of hand-picked tables: the parsers face arbitrary
text/bytes (they must never raise), and the validators face whole generated
configurations (coherent ones must pass, and acceptance must round-trip with
the stdlib). Derandomized via the 'netquick' profile in conftest.py, so any
failure reproduces with the same minimal example anywhere.
"""
import ipaddress
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st

import netops


# --- Parsers never blow up on arbitrary input --------------------------------
@given(st.text())
def test_parse_arp_never_raises_on_text(text):
    table = netops._parse_arp(text)
    assert isinstance(table, dict)
    for ip, mac in table.items():
        ipaddress.IPv4Address(ip)          # keys are always real IPs
        assert mac.count("-") == 5         # values are always MAC-shaped


@given(st.binary())
def test_mdns_name_never_raises_on_bytes(data):
    assert isinstance(netops._mdns_name(data), str)


@given(st.binary())
def test_decode_never_raises_on_bytes(data):
    assert isinstance(netops._decode(data), str)


@given(st.text())
def test_first_dns_never_raises(text):
    assert isinstance(netops._first_dns(text), str)


@given(st.one_of(st.text(), st.lists(st.text()), st.none()))
def test_reg_ip_never_raises(value):
    assert isinstance(netops._reg_ip(value), str)


@given(st.one_of(st.text(), st.none()))
def test_mac_vendor_never_raises(mac):
    assert isinstance(netops.mac_vendor(mac), str)


# --- _parse_arp round-trip ----------------------------------------------------
_ip_in_24 = st.integers(1, 254).map(lambda n: f"10.0.0.{n}")
_mac = st.lists(st.integers(0, 255), min_size=6, max_size=6) \
    .map(lambda bs: "-".join(f"{b:02x}" for b in bs)) \
    .filter(lambda m: m != "ff-ff-ff-ff-ff-ff" and not m.startswith("01-00-5e"))


@given(st.dictionaries(_ip_in_24, _mac, min_size=1, max_size=20))
def test_parse_arp_roundtrips_generated_tables(table):
    """Lines built like 'arp -a' output parse back to exactly the same
    {ip: mac} — nothing lost, nothing invented."""
    text = "Interfaz: 10.0.0.5 --- 0x10\n" + "\n".join(
        f"  {ip}              {mac}     dinámico"
        for ip, mac in table.items())
    assert netops._parse_arp(text) == table
    assert netops._parse_arp(
        text, ipaddress.ip_network("10.0.0.0/24")) == table


# --- Validators agree with the stdlib ----------------------------------------
@given(st.text())
def test_is_valid_ip_accepted_implies_stdlib_parses(value):
    if netops.is_valid_ip(value):
        ipaddress.IPv4Address(value.strip())   # must not raise


@given(st.ip_addresses(v=4))
def test_is_valid_ip_accepts_every_real_ipv4(address):
    assert netops.is_valid_ip(str(address))


@given(st.integers(1, 32))
def test_is_valid_mask_accepts_every_real_prefix(prefix):
    mask = str(ipaddress.ip_network(f"0.0.0.0/{prefix}").netmask)
    assert netops.is_valid_mask(mask)


@given(st.ip_addresses(v=4))
def test_is_valid_mask_agrees_with_contiguous_bits(address):
    m = int(address)
    contiguous = m != 0 and (m | (m - 1)) == 0xFFFFFFFF
    assert netops.is_valid_mask(str(address)) == contiguous


# --- _validate_static over whole generated configurations ---------------------
@given(st.text(), st.text(), st.text(), st.text())
def test_validate_static_never_raises(ip, mask, gw, dns):
    error = netops._validate_static(ip, mask, gw, dns)
    assert error is None or isinstance(error, str)


@st.composite
def coherent_static_config(draw):
    """A config that must pass the preflight: real subnet, host addresses
    strictly inside it (not network/broadcast), gateway != ip."""
    prefix = draw(st.integers(8, 30))
    base = draw(st.integers(0, 2**32 - 1))
    network = ipaddress.ip_network(
        (base & (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF, prefix))
    span = network.num_addresses - 2
    off_ip = draw(st.integers(1, span))
    off_gw = draw(st.integers(1, span).filter(lambda n: n != off_ip))
    dns = draw(st.one_of(st.just(""), st.ip_addresses(v=4).map(str)))
    return (str(network.network_address + off_ip), str(network.netmask),
            str(network.network_address + off_gw), dns)


@given(coherent_static_config())
def test_validate_static_accepts_every_coherent_config(config):
    ip, mask, gw, dns = config
    assert netops._validate_static(ip, mask, gw, dns) is None


@given(coherent_static_config())
def test_validate_static_rejects_the_network_and_broadcast_addresses(config):
    ip, mask, _gw, _dns = config
    network = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    assert "network address" in netops._validate_static(
        str(network.network_address), mask, "", "")
    assert "broadcast address" in netops._validate_static(
        str(network.broadcast_address), mask, "", "")
