# -*- coding: utf-8 -*-
"""
Persistencia JSON de NetQuick: perfiles de red y configuración de la app.

Las rutas por defecto salen de winsetup.APP_DIR (junto a la app en
desarrollo, %APPDATA%\\NetQuick empaquetado como exe); los tests pasan
rutas propias para no tocar los archivos reales.
"""
import json
import os

import winsetup

PROFILES_FILE = os.path.join(winsetup.APP_DIR, "profiles.json")
CONFIG_FILE = os.path.join(winsetup.APP_DIR, "config.json")


def load_profiles(path=PROFILES_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_profiles(data, path=PROFILES_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config(path=CONFIG_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data, path=CONFIG_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
