# -*- coding: utf-8 -*-
"""Tests of winsetup that don't touch the system (scheduled-task XML)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import winsetup


def test_task_xml_contains_the_exe():
    xml = winsetup._task_xml(r"C:\Program Files\NetQuick\NetQuick.exe")
    assert r"<Command>C:\Program Files\NetQuick\NetQuick.exe</Command>" in xml


def test_task_xml_starts_elevated_and_without_limits():
    # Regression of the XML that took effort to tune: elevated at logon, no
    # execution-time limit and no battery restrictions.
    xml = winsetup._task_xml("x.exe")
    assert "<RunLevel>HighestAvailable</RunLevel>" in xml
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "<LogonTrigger><Enabled>true</Enabled></LogonTrigger>" in xml


# --- FM-5: the task.xml is written in an admin-only folder, not %APPDATA% ----
def test_xml_dir_is_not_user_writable():
    """The XML must be generated under %SystemRoot%\\Temp (admin/SYSTEM only),
    not in %APPDATA% (user-writable) — closing the TOCTOU window."""
    folder = winsetup._admin_only_dir().lower()
    system_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
    assert folder.startswith(system_root)
    assert "appdata" not in folder


def test_create_task_writes_xml_in_admin_only_dir(monkeypatch, tmp_path):
    """Verify _create_startup_task passes schtasks an XML located in the
    admin-only folder, with the exe inside, and deletes it afterwards."""
    monkeypatch.setattr(winsetup, "_admin_only_dir", lambda: str(tmp_path))
    seen = {}

    def fake_run(cmd, quiet=False):
        # /XML <path>: read the XML exactly as schtasks will see it
        path = cmd[cmd.index("/XML") + 1]
        seen["path"] = path
        with open(path, encoding="utf-16") as f:
            seen["content"] = f.read()

        class _R:
            returncode = 0
            stdout = stderr = ""
        return _R()

    monkeypatch.setattr(winsetup.netops, "run", fake_run)
    ok = winsetup._create_startup_task(r"C:\Program Files\NetQuick\NetQuick.exe")
    assert ok
    assert os.path.dirname(seen["path"]) == str(tmp_path)
    assert "NetQuick.exe" in seen["content"]
    assert not os.path.exists(seen["path"])       # deleted after creating the task


# --- #29: the .vbs branch of set_startup (the barely-exercised path) ---------
# Knight Capital's pattern: two code paths, only one ever tested. The FROZEN
# branch (schtasks) is covered above; this is the development branch that
# writes a .vbs into the Startup folder.
def _vbs_env(monkeypatch, tmp_path):
    monkeypatch.setattr(winsetup, "FROZEN", False)
    monkeypatch.setattr(winsetup, "VBS_DST", str(tmp_path / "NetQuick.vbs"))
    monkeypatch.setattr(winsetup.netops, "pythonw",
                        lambda: r"C:\Py\pythonw.exe")


def test_vbs_startup_on_writes_absolute_paths(monkeypatch, tmp_path):
    _vbs_env(monkeypatch, tmp_path)
    assert winsetup.set_startup(True)
    content = (tmp_path / "NetQuick.vbs").read_text(encoding="utf-8")
    # Absolute pythonw and script, both quoted (spaces in paths), hidden run
    assert '""C:\\Py\\pythonw.exe""' in content
    assert "netquick.py" in content
    assert ", 0, False" in content
    assert winsetup.in_startup()


def test_vbs_startup_off_removes_and_is_idempotent(monkeypatch, tmp_path):
    _vbs_env(monkeypatch, tmp_path)
    winsetup.set_startup(True)
    assert winsetup.set_startup(False)
    assert not (tmp_path / "NetQuick.vbs").exists()
    assert not winsetup.in_startup()
    assert winsetup.set_startup(False)     # already off: still fine


def test_vbs_startup_failure_returns_false(monkeypatch):
    monkeypatch.setattr(winsetup, "FROZEN", False)
    monkeypatch.setattr(winsetup, "VBS_DST",
                        r"Z:\does-not-exist\NetQuick.vbs")
    monkeypatch.setattr(winsetup.netops, "pythonw",
                        lambda: r"C:\Py\pythonw.exe")
    assert winsetup.set_startup(True) is False


def test_create_task_without_safe_dir_does_not_use_insecure_path(monkeypatch):
    """If the protected folder can't be written to, the task is NOT created in
    an insecure spot: returns False and doesn't even call schtasks."""
    monkeypatch.setattr(winsetup, "_admin_only_dir",
                        lambda: r"Z:\does-not-exist\nor-writable")

    def _must_not_be_called(cmd, quiet=False):
        raise AssertionError("must not invoke schtasks without a safe XML")

    monkeypatch.setattr(winsetup.netops, "run", _must_not_be_called)
    assert winsetup._create_startup_task("x.exe") is False
