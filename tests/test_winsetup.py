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
