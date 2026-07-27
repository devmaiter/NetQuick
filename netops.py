# -*- coding: utf-8 -*-
"""
Shared network operations for NetQuick (used by the mini-widget).

- Every subprocess runs HIDDEN (no flickering black console window).
- Elevation to admin uses pythonw.exe so NO console ever appears.
"""
import ctypes
import ipaddress
import logging
import os
import subprocess
import sys
import time
import winreg
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Protocol

import psutil

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# --- File log ----------------------------------------------------------------
# For diagnosing on other machines: %LOCALAPPDATA%\NetQuick\netquick.log
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA")
                       or os.path.expanduser("~"), "NetQuick")
LOG_FILE = os.path.join(LOG_DIR, "netquick.log")

log = logging.getLogger("netquick")
if not log.handlers:
    log.setLevel(logging.INFO)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _h = RotatingFileHandler(LOG_FILE, maxBytes=256 * 1024,
                                 backupCount=1, encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(_h)
    except OSError:
        log.addHandler(logging.NullHandler())


def _log_op(op, result, reason="", dur_ms=None, **fields):
    """One structured line per ATTEMPT (not only per success), so success
    rate and latency can be computed from the log. result in
    {ok, reject, error}: 'reject' = validation/user (outside the SLO),
    'error' = the OS failed (inside the SLO)."""
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if v != "")
    if dur_ms is not None:
        extra = f"dur_ms={dur_ms} {extra}".strip()
    log.info("op=%s result=%s reason=%s %s", op, result, reason, extra)


def _hidden_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def _decode(b):
    """netsh answers in UTF-8 when Windows has 'Beta: Use Unicode UTF-8'
    enabled and in the classic OEM code page otherwise: try in order until
    it fits, so accents (Sí, está, Dirección…) don't arrive mangled."""
    if not b:
        return ""
    for enc in ("utf-8", "oem", "cp1252"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")


def run(cmd, quiet=False):
    """Run a command (list) without showing any window.

    quiet: don't record the failure in the log (for commands whose error is
    normal, such as pinging a free IP)."""
    try:
        res = subprocess.run(
            cmd, capture_output=True,
            startupinfo=_hidden_startupinfo(), creationflags=_NO_WINDOW,
        )
        res.stdout = _decode(res.stdout)
        res.stderr = _decode(res.stderr)
        if res.returncode != 0 and not quiet:
            log.warning("cmd %s -> %s: %s", cmd, res.returncode,
                        (res.stderr or res.stdout).strip())
        return res
    except Exception:
        log.exception("cmd %s could not be run", cmd)
        return None


# --- Admin / elevation -----------------------------------------------------
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pythonw():
    """Path to pythonw.exe (no console). Falls back to sys.executable."""
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.exists(cand) else sys.executable


def relaunch_as_admin(script, extra=None):
    """Restart the app as administrator (no black window).

    Packaged as .exe (PyInstaller): relaunch the .exe itself.
    In development: relaunch the script with pythonw.

    extra: optional dict {"--flag": value} forwarded to the new process so
    whatever the user already typed is not lost (issue #17).
    """
    if getattr(sys, "frozen", False):
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, None, None, 1
        )
    else:
        params = f'"{os.path.abspath(script)}"'
        for flag, value in (extra or {}).items():
            if value:
                params += f' {flag} "{value}"'
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", pythonw(), params, None, 1
        )
    sys.exit(0)


# --- Interface queries -----------------------------------------------------
def list_interfaces():
    """Return [{'name', 'ip'}] of active interfaces (excluding loopback 'lo').

    The try is PER interface: a weird interface (half-installed driver, broken
    virtual adapter) skips itself without taking down the whole list."""
    data = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception:
        return data
    for name, addr_list in addrs.items():
        try:
            st = stats.get(name)
            if st and st.isup and not name.lower().startswith("lo"):
                ip = next((d.address for d in addr_list if d.family.name == "AF_INET"), "")
                data.append({"name": name, "ip": ip})
        except Exception:
            continue
    return data


def get_ip(name):
    for i in list_interfaces():
        if i["name"] == name:
            return i["ip"]
    return ""


def _iface_guid(name):
    """Interface GUID from its visible name, via the registry.
    Does not depend on the Windows language or encoding."""
    base = (r"SYSTEM\CurrentControlSet\Control\Network"
            r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as net:
            for i in range(winreg.QueryInfoKey(net)[0]):
                guid = winreg.EnumKey(net, i)
                try:
                    with winreg.OpenKey(net, guid + r"\Connection") as con:
                        if winreg.QueryValueEx(con, "Name")[0] == name:
                            return guid
                except OSError:
                    continue
    except OSError:
        pass
    return ""


def _reg_ip(value):
    """First useful value of a registry network entry (REG_MULTI_SZ)."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return (value or "").strip("\x00").strip()


def _first_dns(text):
    """First server of a registry DNS list ('8.8.8.8,1.1.1.1')."""
    return text.replace(",", " ").split()[0] if text else ""


def _registry_config(guid):
    """Interface DHCP mode, gateway and DNS, read from the registry
    (Tcpip\\Parameters\\Interfaces\\{GUID}). Best effort: anything that can't
    be read keeps its default value."""
    info = {"dhcp": False, "gw": "", "dns": ""}
    path = (r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            "\\" + guid)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            info["dhcp"] = bool(winreg.QueryValueEx(k, "EnableDHCP")[0])
            gw_key = "DhcpDefaultGateway" if info["dhcp"] else "DefaultGateway"
            try:
                info["gw"] = _reg_ip(winreg.QueryValueEx(k, gw_key)[0])
            except OSError:
                pass
            # DNS: 'NameServer' (static, "8.8.8.8,1.1.1.1") or 'DhcpNameServer'
            dns_key = "DhcpNameServer" if info["dhcp"] else "NameServer"
            try:
                info["dns"] = _first_dns(
                    _reg_ip(winreg.QueryValueEx(k, dns_key)[0]))
            except OSError:
                pass
    except OSError:
        pass
    return info


def get_config(name):
    """Real interface config: {'dhcp', 'ip', 'mask', 'gw', 'dns'}.

    No netsh text parsing: IP and mask come from psutil and DHCP mode, gateway
    and DNS from the registry. Works the same in any Windows language/config.
    """
    info = {"dhcp": False, "ip": "", "mask": "", "gw": "", "dns": ""}
    try:
        for d in psutil.net_if_addrs().get(name, []):
            if d.family.name == "AF_INET":
                info["ip"] = d.address
                info["mask"] = d.netmask or ""
                break
    except Exception:
        pass
    guid = _iface_guid(name)
    if guid:
        info.update(_registry_config(guid))
    return info


# --- Validation ------------------------------------------------------------
def is_valid_ip(value):
    try:
        ipaddress.IPv4Address(str(value).strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_mask(value):
    """True only for real subnet masks: contiguous ones then zeros
    (255.255.255.0 yes; 1.2.3.4 or 255.7.0.255 no — netsh would later fail
    with a cryptic error)."""
    value = str(value).strip()
    if not is_valid_ip(value):
        return False
    m = int(ipaddress.IPv4Address(value))
    return m != 0 and (m | (m - 1)) == 0xFFFFFFFF


# --- Conflict detection ----------------------------------------------------
def _parse_arp(text, network=None):
    """{ip: mac} from the output of 'arp -a'. Discards broadcast, multicast
    (01-00-5e) and incomplete entries; with 'network', only IPs of that
    subnet (excluding its broadcast address)."""
    table = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ip, mac = parts[0], parts[1].lower()
        if mac.count("-") != 5 or mac == "ff-ff-ff-ff-ff-ff" \
           or mac.startswith("01-00-5e"):
            continue
        try:
            address = ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            continue
        if network is not None and (address not in network
                                    or ip == str(network.broadcast_address)):
            continue
        table[ip] = mac
    return table


def _local_subnets():
    """Directly connected IPv4 networks (from each active interface's
    IP/mask). Only within them does asking via ARP make sense."""
    networks = []
    try:
        for addr_list in psutil.net_if_addrs().values():
            for d in addr_list:
                if d.family.name == "AF_INET" and d.netmask:
                    try:
                        networks.append(ipaddress.ip_network(
                            f"{d.address}/{d.netmask}", strict=False))
                    except ValueError:
                        continue
    except Exception:
        pass
    return networks


def _trigger_arp(ip):
    """Force the OS to resolve the MAC of ip: a UDP datagram to any port
    triggers the ARP request even if the target stays silent to ping.
    Short wait so the reply reaches the cache. No admin required."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"", (ip, 9))  # discard port; the content doesn't matter
        s.close()
    except OSError:
        pass
    time.sleep(0.4)


def _ip_in_arp(ip):
    res = run(["arp", "-a"])
    return bool(res and ip in _parse_arp(res.stdout))


def check_ip(ip):
    """Verdict on an IP before applying it (issue #20 / FM-2):
    'in_use', 'free' or 'unverified'.

    A firewalled host that stays silent to ping still HAS to answer ARP, so
    within the local subnet a directed ARP probe is forced and the cache
    re-read before declaring it free. Outside the local subnets there is no
    ARP available: if it also doesn't answer ping the evidence is weak, so
    'unverified' is returned instead of faking certainty.
    This machine's own IPs don't count as a conflict.
    """
    ip = ip.strip()
    for i in list_interfaces():
        if i["ip"] == ip:
            return "free"
    res = run(["ping", "-n", "1", "-w", "400", ip], quiet=True)
    # returncode 0 with "unreachable" also happens: require a real reply (TTL)
    if res and res.returncode == 0 and "ttl=" in (res.stdout or "").lower():
        return "in_use"
    if _ip_in_arp(ip):
        return "in_use"
    try:
        address = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return "unverified"
    if any(address in network for network in _local_subnets()):
        _trigger_arp(ip)
        return "in_use" if _ip_in_arp(ip) else "free"
    return "unverified"


def ip_in_use(ip):
    """True if another device on the network already answers on that IP."""
    return check_ip(ip) == "in_use"


# --- Dante discovery (mDNS) --------------------------------------------------
def _mdns_name(data):
    """Device name in an mDNS reply ('MyConsole._netaudio-arc...').

    The name label precedes '_netaudio' either literally or followed by a
    compressed DNS pointer (0xC0 xx) pointing at '_netaudio'. Best effort: if
    it can't be extracted, an empty string is returned.
    """
    positions = []
    i = data.find(b"_netaudio")
    while i != -1:
        positions.append(i - 1)  # length byte of '_netaudio-...'
        i = data.find(b"_netaudio", i + 1)
    for p in range(len(data) - 1):
        if data[p] & 0xC0 == 0xC0:  # compressed pointer
            target = ((data[p] & 0x3F) << 8) | data[p + 1]
            if data[target + 1:target + 10] == b"_netaudio":
                positions.append(p)
    for end in positions:
        if end < 2:
            continue
        for k in range(max(0, end - 64), end):
            if k + 1 + data[k] == end and 0 < data[k] <= 63:
                try:
                    name = data[k + 1:end].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if name.isprintable() and not name.startswith("_"):
                    return name
    return ""


def discover_dante(name, timeout=2.0):
    """Native Dante device discovery, just like Dante Controller: an
    mDNS/DNS-SD query for '_netaudio-arc._udp.local' to 224.0.0.251:5353
    (official Audinate documentation). Sent from an ephemeral port
    ('legacy unicast', RFC 6762) so each device replies directly.
    Returns {ip: dante_name}. No admin required.
    """
    import socket
    import struct
    import time

    own_ip = get_ip(name)
    if not own_ip:
        return {}

    def qname(domain):
        out = b""
        for part in domain.split("."):
            out += bytes([len(part)]) + part.encode()
        return out + b"\x00"

    # Standard DNS header + 1 PTR question, class IN
    query = (struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
             + qname("_netaudio-arc._udp.local")
             + struct.pack(">HH", 12, 1))

    found = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                     socket.inet_aton(own_ip))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        s.bind((own_ip, 0))
        s.settimeout(0.3)
        for _ in range(2):  # repeat in case a device misses the first one
            s.sendto(query, ("224.0.0.251", 5353))
            end = time.time() + timeout / 2
            while time.time() < end:
                try:
                    data, src = s.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                ip = src[0]
                found[ip] = _mdns_name(data) or found.get(ip, "")
        s.close()
    except OSError:
        pass
    return found


# MAC prefixes (OUI) of vendors common on audio networks
KNOWN_OUIS = {
    "00-1d-c1": "Audinate (Dante)",
    "00-a0-de": "Yamaha",
    "00-0e-dd": "Shure",
    "00-60-74": "QSC",
    "00-04-c4": "Allen & Heath",
    "b8-27-eb": "Raspberry Pi",
    "dc-a6-32": "Raspberry Pi",
}


def mac_vendor(mac):
    """Vendor from the OUI prefix of the MAC ('aa-bb-cc-…'), or ''."""
    return KNOWN_OUIS.get((mac or "")[:8].lower(), "")


# --- Subnet scan -------------------------------------------------------------
def _ping_sweep(network, timeout_ms):
    """Short parallel ping to every IP of the subnet. The replies are not
    inspected: the goal is to populate the ARP cache."""
    import concurrent.futures

    def _ping(ip):
        run(["ping", "-n", "1", "-w", str(timeout_ms), str(ip)], quiet=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping, network.hosts()))


def _combine_devices(arp, dante, own_ip):
    """Merge the ARP table {ip: mac} with the Dante devices {ip: name} and
    mark this machine. Dante devices are included even if outside the subnet
    (so the ones left with a wrong static IP still show up). Returns the list
    [{'ip','mac','own','dante'}] sorted numerically by IP."""
    found = {ip: {"ip": ip, "mac": mac, "own": False, "dante": None}
             for ip, mac in arp.items()}
    for ip, dante_name in dante.items():
        if ip == own_ip:
            continue
        e = found.setdefault(ip, {"ip": ip, "mac": "", "own": False,
                                  "dante": None})
        e["dante"] = dante_name or "Dante"
    found[own_ip] = {"ip": own_ip, "mac": "", "own": True, "dante": None}
    return sorted(found.values(),
                  key=lambda d: tuple(int(x) for x in d["ip"].split(".")))


def scan_network(name, timeout_ms=250):
    """Scan the interface's REAL subnet (according to its mask).

    - Normal subnets (up to ~1000 hosts, e.g. /24): ping all IPs in parallel
      and read the ARP cache.
    - Huge subnets (e.g. Dante on link-local 169.254.0.0/16): the sweep is
      infeasible, but it isn't needed — Dante devices announce over multicast
      constantly and fill the ARP cache on their own; it's read whole.
    Returns [{'ip','mac','own','dante'}] sorted by IP. No admin required.
    """
    own_ip = get_ip(name)
    if not own_ip:
        return []
    mask = get_config(name).get("mask") or "255.255.255.0"
    try:
        network = ipaddress.ip_network(f"{own_ip}/{mask}", strict=False)
    except ValueError:
        network = ipaddress.ip_network(f"{own_ip}/24", strict=False)

    if network.num_addresses <= 1024:
        _ping_sweep(network, timeout_ms)

    res = run(["arp", "-a"])
    arp = _parse_arp(res.stdout if res else "", network)
    return _combine_devices(arp, discover_dante(name), own_ip)


# --- Apply configuration ---------------------------------------------------
def _validate_static(ip, mask, gw, dns):
    """Error message of the first invalid field, or None if everything fits."""
    if not is_valid_ip(ip):
        return f"Invalid IP: {ip}"
    if not is_valid_mask(mask):
        return f"Invalid subnet mask: {mask} (use 255.255.255.0)"
    if gw and not is_valid_ip(gw):
        return f"Invalid gateway: {gw}"
    if dns and not is_valid_ip(dns):
        return f"Invalid DNS: {dns}"
    return None


def set_static(name, ip, mask, gw=None, dns=None):
    """Apply a static IP (and DNS if given). Returns (ok, message)."""
    t0 = time.perf_counter()
    def _dur():
        return round((time.perf_counter() - t0) * 1000)

    ip, mask = ip.strip(), mask.strip()
    gw = gw.strip() if gw else ""
    dns = dns.strip() if dns else ""
    error = _validate_static(ip, mask, gw, dns)
    if error:
        _log_op("set_static", "reject", error, _dur(), iface=name, ip=ip)
        return False, error
    verdict = check_ip(ip)
    if verdict == "in_use":
        _log_op("set_static", "reject", "ip_in_use", _dur(), iface=name, ip=ip)
        return False, f"⚠ {ip} is already in use — nothing applied"
    cmd = ["netsh", "interface", "ip", "set", "address", f"name={name}", "static", ip, mask]
    if gw:
        cmd += [gw, "1"]
    res = run(cmd)
    if not (res and res.returncode == 0):
        detail = ((res.stderr or res.stdout) or "").strip() if res else ""
        _log_op("set_static", "error", detail or "netsh_fail", _dur(),
                iface=name, ip=ip)
        return False, (detail or "Error (admin?)")
    warnings = []
    if verdict == "unverified":
        warnings.append(f"could not verify that {ip} was free")
    dns_ok = True
    if dns:
        r2 = run(["netsh", "interface", "ip", "set", "dns",
                  f"name={name}", "static", dns])
        if not (r2 and r2.returncode == 0):
            dns_ok = False
            warnings.append("DNS could not be applied")
    if gw:
        network = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
        if ipaddress.IPv4Address(gw) not in network:
            warnings.append("gateway outside the subnet")
    # Rogers 2022 lesson: an operation that leaves the system half-done must
    # not report a clean success. If DNS was requested and failed, the
    # transaction did not meet its goal -> ok=False (a gateway outside the
    # subnet is only a warning).
    result = "ok" if dns_ok else "partial"
    _log_op("set_static", result, " ".join(warnings), _dur(),
            iface=name, ip=ip, mask=mask, gw=gw, dns=dns)
    msg = "  ".join([f"IP {ip} applied", *(f"⚠ {w}" for w in warnings)])
    return dns_ok, msg


def set_dhcp(name):
    """Put the interface in automatic mode (DHCP). Returns (ok, message)."""
    t0 = time.perf_counter()
    r1 = run(["netsh", "interface", "ip", "set", "address", f"name={name}", "dhcp"])
    run(["netsh", "interface", "ip", "set", "dns", f"name={name}", "dhcp"])
    dur_ms = round((time.perf_counter() - t0) * 1000)
    if r1 and r1.returncode == 0:
        _log_op("set_dhcp", "ok", "", dur_ms, iface=name)
        return True, "DHCP enabled"
    detail = ((r1.stderr or r1.stdout) or "").strip() if r1 else ""
    _log_op("set_dhcp", "error", detail or "netsh_fail", dur_ms, iface=name)
    return False, (detail or "Error (admin?)")


def gateway_responds(gw):
    """True if the gateway answers a short ping: basic connectivity verified
    after applying a static IP (issue #21)."""
    if not gw:
        return False
    res = run(["ping", "-n", "1", "-w", "700", gw], quiet=True)
    return bool(res and res.returncode == 0
                and "ttl=" in (res.stdout or "").lower())


def revert_to(name, previous):
    """Emergency path (issue #21, Meta 2021 lesson): go back to the previous
    configuration the simplest way possible. Direct netsh, no validation and
    no check_ip — the rescue tool can't depend on the network that just broke,
    and the previous config was already applied. Returns (ok, message)."""
    t0 = time.perf_counter()
    previous = previous or {}
    ip, mask = previous.get("ip", ""), previous.get("mask", "")
    if previous.get("dhcp") or not (ip and mask):
        # No reliable data: DHCP is the simplest known-good state
        ok, msg = set_dhcp(name)
        _log_op("revert", "ok" if ok else "error", "via_dhcp",
                round((time.perf_counter() - t0) * 1000), iface=name)
        return ok, msg
    cmd = ["netsh", "interface", "ip", "set", "address",
           f"name={name}", "static", ip, mask]
    if previous.get("gw"):
        cmd += [previous["gw"], "1"]
    res = run(cmd)
    if previous.get("dns"):
        run(["netsh", "interface", "ip", "set", "dns",
             f"name={name}", "static", previous["dns"]])
    dur_ms = round((time.perf_counter() - t0) * 1000)
    if res and res.returncode == 0:
        _log_op("revert", "ok", "", dur_ms, iface=name, ip=ip)
        return True, f"Reverted to {ip}"
    detail = ((res.stderr or res.stdout) or "").strip() if res else ""
    _log_op("revert", "error", detail or "netsh_fail", dur_ms,
            iface=name, ip=ip)
    return False, (detail or "Could not revert")


# --- Apply strategies -------------------------------------------------------
# The Strategy pattern in its Pythonic form: a Protocol (typed duck typing)
# and dataclasses that pack the parameters and delegate to set_static/set_dhcp.
# apply() receives the operations module so the UI can inject doubles in the
# tests, just like it does with everything else.
class NetworkStrategy(Protocol):
    def apply(self, ops, iface): ...


@dataclass
class StaticIP:
    ip: str
    mask: str = "255.255.255.0"
    gw: str = ""
    dns: str = ""

    def apply(self, ops, iface):
        return ops.set_static(iface, self.ip, self.mask, self.gw, self.dns)


@dataclass
class DHCP:
    def apply(self, ops, iface):
        return ops.set_dhcp(iface)


def strategy_from_profile(p):
    """The strategy that corresponds to a saved profile. Today's profiles are
    always static IP; a future {"mode": "dhcp"} already has a path."""
    if p.get("mode") == "dhcp":
        return DHCP()
    return StaticIP(p.get("ip", ""), p.get("mask", "255.255.255.0"),
                    p.get("gw", ""), p.get("dns", ""))
