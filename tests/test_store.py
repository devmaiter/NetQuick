# -*- coding: utf-8 -*-
"""Tests de la persistencia JSON (con rutas temporales, sin tocar la real)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store


def test_perfiles_ida_y_vuelta(tmp_path):
    ruta = str(tmp_path / "profiles.json")
    datos = {"Casa": {"ip": "192.168.1.50", "mask": "255.255.255.0",
                      "gw": "192.168.1.1", "dns": "8.8.8.8"}}
    store.save_profiles(datos, ruta)
    assert store.load_profiles(ruta) == datos


def test_perfiles_conservan_acentos(tmp_path):
    ruta = str(tmp_path / "profiles.json")
    store.save_profiles({"Camión FOH": {"ip": "10.0.0.5"}}, ruta)
    with open(ruta, encoding="utf-8") as f:
        assert "Camión FOH" in f.read()  # ensure_ascii=False: legible a mano


def test_cargar_inexistente_devuelve_vacio(tmp_path):
    assert store.load_profiles(str(tmp_path / "no-existe.json")) == {}
    assert store.load_config(str(tmp_path / "no-existe.json")) == {}


def test_cargar_json_roto_devuelve_vacio(tmp_path):
    ruta = str(tmp_path / "roto.json")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("{esto no es json")
    assert store.load_profiles(ruta) == {}


def test_config_ida_y_vuelta(tmp_path):
    ruta = str(tmp_path / "config.json")
    store.save_config({"ultima_interfaz": "Ethernet"}, ruta)
    assert store.load_config(ruta) == {"ultima_interfaz": "Ethernet"}


def test_guardar_config_en_ruta_imposible_no_lanza(tmp_path):
    # save_config traga OSError: perder la preferencia no debe tumbar la app
    store.save_config({"x": 1}, str(tmp_path / "no" / "existe" / "config.json"))
