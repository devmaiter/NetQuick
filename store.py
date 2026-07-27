# -*- coding: utf-8 -*-
"""
NetQuick JSON persistence: network profiles and app configuration.

Default paths come from winsetup.APP_DIR (next to the app in development,
%APPDATA%\\NetQuick when packaged as an exe); the tests pass their own paths
so they don't touch the real files.
"""
import json
import os
import shutil
import tempfile

import winsetup

PROFILES_FILE = os.path.join(winsetup.APP_DIR, "profiles.json")
CONFIG_FILE = os.path.join(winsetup.APP_DIR, "config.json")


def _atomic_write_json(data, path):
    """Durable write: dump to a temp file in the same directory, sync it to
    disk and rename over the destination. os.replace is atomic on the same
    volume, so a crash midway leaves the previous file intact — never a
    truncated JSON. Before replacing, it keeps the previous valid file as
    '.bak' so it can be recovered even if the destination is later corrupted
    by external causes."""
    folder = os.path.dirname(path) or "."
    # 1) dump the temp file COMPLETELY: if this fails, the primary isn't touched
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    # 2) back up the previous good one and 3) swap atomically
    if os.path.exists(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError:
            pass
    os.replace(tmp, path)


def _read_json(path):
    """Read the JSON; if the primary is missing or corrupt, fall back to the
    '.bak'. Returns {} only if neither is readable."""
    for candidate in (path, path + ".bak"):
        try:
            with open(candidate, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def load_profiles(path=PROFILES_FILE):
    return _read_json(path)


def save_profiles(data, path=PROFILES_FILE):
    _atomic_write_json(data, path)


def load_config(path=CONFIG_FILE):
    return _read_json(path)


def save_config(data, path=CONFIG_FILE):
    try:
        _atomic_write_json(data, path)
    except OSError:
        pass
