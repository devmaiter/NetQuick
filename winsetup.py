# -*- coding: utf-8 -*-
"""
NetQuick integration with Windows (Facade).

A simple interface over schtasks, netsh advfirewall, winreg and ctypes: the
UI doesn't know HOW it's done (scheduled tasks, registry keys, instance
mutex), only WHAT it can ask for — start with Windows, first exe run, single
instance and DPI awareness.
"""
import ctypes
import os
import sys
import winreg

import netops

# Packaged with PyInstaller: __file__ points to a temp folder, so the user
# data (profiles) goes to %APPDATA%\NetQuick.
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
if FROZEN:
    APP_DIR = os.path.join(os.environ.get("APPDATA", HERE), "NetQuick")
    os.makedirs(APP_DIR, exist_ok=True)
else:
    APP_DIR = HERE
VBS_SRC = os.path.join(HERE, "NetQuick.vbs")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS_DST = os.path.join(STARTUP_DIR, "NetQuick.vbs")

# As an .exe the app always runs elevated (requireAdministrator manifest): so
# applying IP/DHCP never closes or relaunches the window. Starting with
# Windows uses a privileged scheduled task (RunLevel Highest) that starts
# elevated at logon WITHOUT showing UAC.
TASK_NAME = "NetQuick"
# Run key from older versions (only to migrate/clean up)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "NetQuick"


def _task_xml(exe):
    """Scheduled task XML: at logon, elevated, with no battery or time limits
    (schtasks' defaults would otherwise impose them)."""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{exe}</Command></Exec>
  </Actions>
</Task>"""


# --- Start with Windows ----------------------------------------------------
def in_startup():
    if FROZEN:
        res = netops.run(["schtasks", "/Query", "/TN", TASK_NAME], quiet=True)
        return bool(res and res.returncode == 0)
    return os.path.exists(VBS_DST)


def _admin_only_dir():
    """Folder writable ONLY by administrators/SYSTEM, not by standard users:
    %SystemRoot%\\Temp. The task.xml is generated here (not in %APPDATA%, which
    is user-writable) to close the FM-5 TOCTOU window: an unprivileged process
    can't rewrite the XML between the elevated app creating it and schtasks
    reading it. The app runs elevated, so it can write here."""
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")


def _create_startup_task(exe):
    """Create the startup scheduled task from an XML in the admin-only folder,
    with a random name, and delete it afterwards. Returns True if schtasks
    created the task."""
    import tempfile
    try:
        fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="netquick_",
                                        dir=_admin_only_dir())
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(_task_xml(exe))
    except OSError:
        # Without a protected folder to write to, don't create the task in an
        # insecure spot: better not to enable startup than to do it unsafely.
        return False
    try:
        res = netops.run(["schtasks", "/Create", "/TN", TASK_NAME,
                          "/XML", xml_path, "/F"])
        return bool(res and res.returncode == 0)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass


def set_startup(on):
    try:
        if FROZEN:
            if on:
                return _create_startup_task(sys.executable)
            netops.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
            return True
        if on:
            # The startup .vbs carries absolute paths (script AND pythonw): if
            # pythonw is not on the PATH, a bare "pythonw" fails silently.
            script = os.path.join(HERE, "netquick.py")
            pyw = netops.pythonw()
            with open(VBS_DST, "w", encoding="utf-8") as f:
                f.write('CreateObject("WScript.Shell").Run '
                        f'"""{pyw}"" ""{script}""", 0, False\r\n')
        elif not on and os.path.exists(VBS_DST):
            os.remove(VBS_DST)
        return True
    except Exception:
        return False


def firewall_rule():
    """Firewall rule for the exe (like Dante Controller does when installed):
    without it Windows blocks the unicast mDNS replies from Dante devices to
    the scanner's ephemeral port. Idempotent: deletes the previous rule in
    case the exe changed path."""
    netops.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                "name=NetQuick"], quiet=True)
    netops.run(["netsh", "advfirewall", "firewall", "add", "rule",
                "name=NetQuick", "dir=in", "action=allow",
                f"program={sys.executable}", "profile=any", "enable=yes"])


def first_run_exe():
    """The first time the .exe runs: firewall rule and cleanup of previous
    installs. NetQuick no longer auto-registers to start with Windows — it
    opens, stays in the tray, and that's it. Start with Windows is a user
    option in ⚙ (off by default): the app must not sneak into elevated startup
    without the user asking for it."""
    if not FROZEN:
        return
    firewall_rule()
    # Migrate previous installs: remove the insecure Run key (it started
    # without permissions). The task is NOT recreated: if the user wants
    # automatic startup, they enable it themselves in ⚙.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_ALL_ACCESS) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            winreg.DeleteValue(k, RUN_NAME)
    except OSError:
        pass


# --- Process ----------------------------------------------------------------
# The mutex handle must live for the whole process (if it were released,
# another instance could start): it's kept at module level on purpose.
_MUTEX = None


def already_running():
    """Prevents duplicate instances (and tray icons)."""
    global _MUTEX
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                 "NetQuick_Instance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def dpi_awareness():
    """With Windows scaling (125/150%) Tkinter looks blurry if the process
    doesn't declare DPI awareness. Declare it BEFORE creating the window."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
