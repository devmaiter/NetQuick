# -*- coding: utf-8 -*-
"""Tests de la persistencia JSON (con rutas temporales, sin tocar la real)."""
import os
import sys

import pytest

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


# --- Durabilidad: escritura atómica (INV-4, cierra FM-1) ---------------------
def test_save_atomico_preserva_anterior_si_falla(tmp_path):
    """Si el volcado falla a mitad, el archivo anterior queda INTACTO
    (antes: quedaba truncado y load_profiles devolvía {} = pérdida total)."""
    ruta = str(tmp_path / "profiles.json")
    store.save_profiles({"Casa": {"ip": "10.0.0.5"}}, ruta)
    # un set no es serializable a JSON: json.dump falla a media escritura
    with pytest.raises(TypeError):
        store.save_profiles({"malo": {1, 2, 3}}, ruta)
    assert store.load_profiles(ruta) == {"Casa": {"ip": "10.0.0.5"}}


def test_save_no_deja_temporales_sueltos(tmp_path):
    ruta = str(tmp_path / "profiles.json")
    store.save_profiles({"Casa": {"ip": "10.0.0.5"}}, ruta)
    with pytest.raises(TypeError):
        store.save_profiles({"malo": {1, 2, 3}}, ruta)
    # un save fallido no toca el primario ni deja .tmp ni .bak sueltos
    assert sorted(os.listdir(tmp_path)) == ["profiles.json"]


def test_recupera_del_bak_si_el_primario_se_corrompe(tmp_path):
    """Reproduce el EXP-4 (corrupción externa del archivo ya escrito) y
    verifica que ahora se recupera la última versión buena desde el .bak."""
    ruta = str(tmp_path / "profiles.json")
    store.save_profiles({"Casa": {"ip": "10.0.0.5"}}, ruta)   # v1
    store.save_profiles({"Casa": {"ip": "10.0.0.9"}}, ruta)   # v2 (.bak = v1)
    (tmp_path / "profiles.json").write_text("{roto a medias", "utf-8")
    assert store.load_profiles(ruta) == {"Casa": {"ip": "10.0.0.5"}}
