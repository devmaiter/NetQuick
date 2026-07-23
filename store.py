# -*- coding: utf-8 -*-
"""
Persistencia JSON de NetQuick: perfiles de red y configuración de la app.

Las rutas por defecto salen de winsetup.APP_DIR (junto a la app en
desarrollo, %APPDATA%\\NetQuick empaquetado como exe); los tests pasan
rutas propias para no tocar los archivos reales.
"""
import json
import os
import shutil
import tempfile

import winsetup

PROFILES_FILE = os.path.join(winsetup.APP_DIR, "profiles.json")
CONFIG_FILE = os.path.join(winsetup.APP_DIR, "config.json")


def _escribir_json_atomico(data, path):
    """Escritura durable: vuelca a un temporal en el mismo directorio, lo
    sincroniza a disco y lo renombra sobre el destino. os.replace es atómico
    en el mismo volumen, así que un corte a mitad deja intacto el archivo
    anterior — nunca un JSON truncado. Antes de reemplazar, conserva el
    archivo válido previo como '.bak' para poder recuperar incluso si el
    destino se corrompe más tarde por causas externas."""
    carpeta = os.path.dirname(path) or "."
    # 1) volcar el temporal COMPLETO: si esto falla, el primario ni se toca
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=".tmp-", suffix=".json")
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
    # 2) respaldar el bueno anterior y 3) intercambiar de forma atómica
    if os.path.exists(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError:
            pass
    os.replace(tmp, path)


def _leer_json(path):
    """Lee el JSON; si el principal falta o está corrupto, cae al '.bak'.
    Devuelve {} solo si ninguno de los dos es legible."""
    for candidato in (path, path + ".bak"):
        try:
            with open(candidato, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def load_profiles(path=PROFILES_FILE):
    return _leer_json(path)


def save_profiles(data, path=PROFILES_FILE):
    _escribir_json_atomico(data, path)


def load_config(path=CONFIG_FILE):
    return _leer_json(path)


def save_config(data, path=CONFIG_FILE):
    try:
        _escribir_json_atomico(data, path)
    except OSError:
        pass
