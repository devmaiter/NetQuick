# -*- coding: utf-8 -*-
"""
Simulated network backend for NetQuick (issue #28, SimOps).

The refactor left the `ops` seam injectable; SimOps honors the same contract
as `netops` (list_interfaces, get_config, set_static, set_dhcp, scan_network,
is_admin, mac_vendor, gateway_responds, revert_to) over a mutable in-memory
state: the full flow — apply IP, DHCP, scanner, profiles, auto-revert — can be
exercised without touching the real network or requiring admin. It's the
"rehearsal on a replica" at the scale of one process (Chaos Kong / CrystalNet).

Run the real UI against it with:  pythonw netquick.py --sim
"""
import netops

DHCP_LEASE = "10.0.0.50"


class SimOps:
    """In-memory twin of netops. One simulated interface plus a small
    neighborhood: the gateway and a Dante device."""

    def __init__(self):
        self.iface = "Sim Ethernet"
        self.config = {"dhcp": True, "ip": DHCP_LEASE, "mask": "255.255.255.0",
                       "gw": "10.0.0.1", "dns": "8.8.8.8"}
        self.neighbors = {"10.0.0.1": "aa-bb-cc-00-00-01",
                          "10.0.0.7": "00-1d-c1-00-00-07"}
        self.dante = {"10.0.0.7": "SimConsole"}
        # Chaos hook (issues #25/#21): the next mutating operation raises this
        # exception instead of running, then the hook disarms itself.
        self.inject = None

    def _maybe_inject(self):
        if self.inject is not None:
            exc, self.inject = self.inject, None
            raise exc

    # --- Queries -------------------------------------------------------------
    def is_admin(self):
        return True

    def relaunch_as_admin(self, script, extra=None):
        raise AssertionError("SimOps is always admin: nothing should relaunch")

    def list_interfaces(self):
        return [{"name": self.iface, "ip": self.config["ip"]}]

    def get_ip(self, name):
        return self.config["ip"] if name == self.iface else ""

    def get_config(self, name):
        return dict(self.config)

    def mac_vendor(self, mac):
        return netops.mac_vendor(mac)

    def gateway_responds(self, gw):
        return gw in self.neighbors

    def scan_network(self, name, timeout_ms=250):
        return netops._combine_devices(dict(self.neighbors), dict(self.dante),
                                       self.config["ip"])

    # --- Mutations -----------------------------------------------------------
    def set_static(self, name, ip, mask, gw=None, dns=None):
        self._maybe_inject()
        ip, mask = ip.strip(), mask.strip()
        gw = gw.strip() if gw else ""
        dns = dns.strip() if dns else ""
        # Same preflight as the real backend: the dry run must reject exactly
        # what the real one would reject.
        error = netops._validate_static(ip, mask, gw, dns)
        if error:
            return False, error
        if ip in self.neighbors:
            return False, f"⚠ {ip} is already in use — nothing applied"
        self.config = {"dhcp": False, "ip": ip, "mask": mask,
                       "gw": gw, "dns": dns}
        return True, f"IP {ip} applied (simulated)"

    def set_dhcp(self, name):
        self._maybe_inject()
        self.config = {"dhcp": True, "ip": DHCP_LEASE, "mask": "255.255.255.0",
                       "gw": "10.0.0.1", "dns": "8.8.8.8"}
        return True, "DHCP enabled (simulated)"

    def revert_to(self, name, previous):
        previous = previous or {}
        if previous.get("dhcp") or not (previous.get("ip") and previous.get("mask")):
            return self.set_dhcp(name)
        self.config = {"dhcp": False, "ip": previous["ip"],
                       "mask": previous["mask"], "gw": previous.get("gw", ""),
                       "dns": previous.get("dns", "")}
        return True, f"Reverted to {previous['ip']}"


class SimStore:
    """In-memory persistence so the dry run doesn't touch the real profiles."""

    def __init__(self):
        self.profiles = {}
        self.config = {}

    def load_profiles(self):
        return dict(self.profiles)

    def save_profiles(self, data):
        self.profiles = dict(data)

    def load_config(self):
        return dict(self.config)

    def save_config(self, data):
        self.config = dict(data)
