# NetQuick — Reglas para agentes

## Identidad de git (OBLIGATORIO)
- Commitear SIEMPRE como `devmaiter <f1000161620@gmail.com>` (el correo de la
  cuenta de GitHub del dueño). No usar otro correo ni otra identidad.
- PROHIBIDO cualquier atribución de IA en commits, PRs o issues: nada de
  `Co-Authored-By: Claude ...`, `Generated with Claude Code`, enlaces
  `Claude-Session`, ni ramas `claude/*`. El dueño del proyecto lo exige.
- No crear PRs ni ramas con identidad de bot; trabajar sobre `main` o ramas
  `feat/...` / `fix/...` con la identidad de arriba.

## Qué es este proyecto
- **Una sola app**: `netquick.py` — widget flotante Tkinter con icono en la
  bandeja del sistema para cambiar red/IP en Windows.
- `netops.py`: operaciones de red (netsh, psutil, escáner, mDNS Dante).
- `NetQuick.vbs`: lanzador sin consola. `NetQuick.spec`: build del exe.
- NO existe `main.py` ni `mini.py` — fueron eliminados; no recrearlos.

## Cómo ejecutar
- Desarrollo: `pythonw netquick.py` o doble clic en `NetQuick.vbs`.
- Dependencias: `.\setup.ps1` (o `pip install -r requirements.txt`).
- Build del exe: `pyinstaller NetQuick.spec` → `dist\NetQuick.exe`.

## Reglas de releases
- El asset del release "latest" debe llamarse `NetQuick.exe` (el instalador
  `install.ps1` lo busca por `*.exe` en el último release).
- Nunca reescribir historial ni forzar push sin pedirlo explícitamente al dueño.
