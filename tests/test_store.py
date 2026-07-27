# -*- coding: utf-8 -*-
"""Tests of the JSON persistence (with temp paths, never touching the real one)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store


def test_profiles_round_trip(tmp_path):
    path = str(tmp_path / "profiles.json")
    data = {"Home": {"ip": "192.168.1.50", "mask": "255.255.255.0",
                     "gw": "192.168.1.1", "dns": "8.8.8.8"}}
    store.save_profiles(data, path)
    assert store.load_profiles(path) == data


def test_profiles_keep_accents(tmp_path):
    path = str(tmp_path / "profiles.json")
    store.save_profiles({"Camión FOH": {"ip": "10.0.0.5"}}, path)
    with open(path, encoding="utf-8") as f:
        assert "Camión FOH" in f.read()  # ensure_ascii=False: readable by hand


def test_load_missing_returns_empty(tmp_path):
    assert store.load_profiles(str(tmp_path / "does-not-exist.json")) == {}
    assert store.load_config(str(tmp_path / "does-not-exist.json")) == {}


def test_load_broken_json_returns_empty(tmp_path):
    path = str(tmp_path / "broken.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{this is not json")
    assert store.load_profiles(path) == {}


def test_config_round_trip(tmp_path):
    path = str(tmp_path / "config.json")
    store.save_config({"last_interface": "Ethernet"}, path)
    assert store.load_config(path) == {"last_interface": "Ethernet"}


def test_save_config_to_impossible_path_does_not_raise(tmp_path):
    # save_config swallows OSError: losing the preference must not crash the app
    store.save_config({"x": 1}, str(tmp_path / "no" / "way" / "config.json"))


# --- Durability: atomic write (INV-4, closes FM-1) ---------------------------
def test_atomic_save_preserves_previous_on_failure(tmp_path):
    """If the dump fails midway, the previous file stays INTACT (before: it was
    left truncated and load_profiles returned {} = total loss)."""
    path = str(tmp_path / "profiles.json")
    store.save_profiles({"Home": {"ip": "10.0.0.5"}}, path)
    # a set is not JSON-serializable: json.dump fails mid-write
    with pytest.raises(TypeError):
        store.save_profiles({"bad": {1, 2, 3}}, path)
    assert store.load_profiles(path) == {"Home": {"ip": "10.0.0.5"}}


def test_save_leaves_no_stray_temp_files(tmp_path):
    path = str(tmp_path / "profiles.json")
    store.save_profiles({"Home": {"ip": "10.0.0.5"}}, path)
    with pytest.raises(TypeError):
        store.save_profiles({"bad": {1, 2, 3}}, path)
    # a failed save touches neither the primary nor leaves .tmp/.bak stray
    assert sorted(os.listdir(tmp_path)) == ["profiles.json"]


def test_recovers_from_bak_if_primary_is_corrupted(tmp_path):
    """Reproduces EXP-4 (external corruption of the already-written file) and
    verifies the last good version is now recovered from the .bak."""
    path = str(tmp_path / "profiles.json")
    store.save_profiles({"Home": {"ip": "10.0.0.5"}}, path)   # v1
    store.save_profiles({"Home": {"ip": "10.0.0.9"}}, path)   # v2 (.bak = v1)
    (tmp_path / "profiles.json").write_text("{broken midway", "utf-8")
    assert store.load_profiles(path) == {"Home": {"ip": "10.0.0.5"}}
