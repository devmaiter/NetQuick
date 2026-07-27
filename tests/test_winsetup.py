# -*- coding: utf-8 -*-
"""Tests de winsetup que no tocan el sistema (XML de la tarea programada)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import winsetup


def test_task_xml_contiene_el_exe():
    xml = winsetup._task_xml(r"C:\Program Files\NetQuick\NetQuick.exe")
    assert r"<Command>C:\Program Files\NetQuick\NetQuick.exe</Command>" in xml


def test_task_xml_arranca_elevada_y_sin_limites():
    # Regresión del XML que costó afinar: elevada al iniciar sesión, sin
    # límite de tiempo de ejecución ni restricciones de batería.
    xml = winsetup._task_xml("x.exe")
    assert "<RunLevel>HighestAvailable</RunLevel>" in xml
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "<LogonTrigger><Enabled>true</Enabled></LogonTrigger>" in xml


# --- FM-5: el task.xml se escribe en carpeta solo-admin, no en %APPDATA% ------
def test_dir_del_xml_no_es_escribible_por_el_usuario():
    """El XML debe generarse bajo %SystemRoot%\\Temp (solo admin/SYSTEM), no en
    %APPDATA% (escribible por el usuario) — cierre de la ventana TOCTOU."""
    carpeta = winsetup._dir_solo_admin().lower()
    system_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
    assert carpeta.startswith(system_root)
    assert "appdata" not in carpeta


def test_crear_tarea_escribe_el_xml_en_dir_solo_admin(monkeypatch, tmp_path):
    """Verifica que _crear_tarea_inicio pasa a schtasks un XML ubicado en la
    carpeta solo-admin, con el exe dentro, y que lo borra al terminar."""
    monkeypatch.setattr(winsetup, "_dir_solo_admin", lambda: str(tmp_path))
    visto = {}

    def fake_run(cmd, quiet=False):
        # /XML <ruta>: leer el XML tal como lo verá schtasks
        ruta = cmd[cmd.index("/XML") + 1]
        visto["ruta"] = ruta
        with open(ruta, encoding="utf-16") as f:
            visto["contenido"] = f.read()

        class _R:
            returncode = 0
            stdout = stderr = ""
        return _R()

    monkeypatch.setattr(winsetup.netops, "run", fake_run)
    ok = winsetup._crear_tarea_inicio(r"C:\Program Files\NetQuick\NetQuick.exe")
    assert ok
    assert os.path.dirname(visto["ruta"]) == str(tmp_path)
    assert "NetQuick.exe" in visto["contenido"]
    assert not os.path.exists(visto["ruta"])       # se borró tras crear la tarea


def test_crear_tarea_sin_dir_seguro_no_usa_ruta_insegura(monkeypatch):
    """Si no se puede escribir en la carpeta protegida, NO se crea la tarea en
    un sitio inseguro: devuelve False y ni siquiera llama a schtasks."""
    monkeypatch.setattr(winsetup, "_dir_solo_admin",
                        lambda: r"Z:\no-existe\ni-escribible")

    def _no_debe_llamarse(cmd, quiet=False):
        raise AssertionError("no debe invocar schtasks sin XML seguro")

    monkeypatch.setattr(winsetup.netops, "run", _no_debe_llamarse)
    assert winsetup._crear_tarea_inicio("x.exe") is False
