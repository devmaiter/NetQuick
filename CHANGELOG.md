# Changelog

Historial de cambios de NetQuick. La versión del código vive en
`netquick.py` (`__version__`) y es la única fuente de verdad.

## [1.3.0-beta] — sin publicar

- Auto-revert (issue #21): tras aplicar IP fija se verifica el gateway; si no
  responde, cuenta regresiva de 30 s con botón "Mantener cambio" y vuelta
  automática a la configuración anterior. El revert va por netsh directo,
  sin depender de la red (lección Meta 2021).
- Detección de IP en uso reforzada (issue #20 / FM-2): sonda ARP dirigida para
  equipos que callan al ping; fuera de la subred local ya no se finge certeza —
  se aplica con el aviso "no se pudo verificar que la IP estuviera libre".
- Honestidad transaccional (issue #22): si el DNS falla tras aplicar la IP, el
  resultado es fallo (rojo), no éxito con letra pequeña; tercer estado ámbar
  para "aplicado con avisos".
- Escritura durable de perfiles/config y log estructurado por intento
  (op/resultado/motivo/duración) en `%LOCALAPPDATA%\NetQuick\netquick.log`.
- Refactor testeable: UI instanciable con operaciones y persistencia
  inyectables (`store.py`, `winsetup.py`); 90 tests con fakes, ruff y
  cobertura mínima en CI.
- Docs: backlog de confiabilidad (`docs/backlog-confiabilidad.md`) y
  experimento de validación FM-2 (`experimentos/exp_ip_en_uso.py`).

## [1.2.2-beta] — 2026-07-18

- Campo DNS al aplicar IP estática — adiós al "tengo IP pero no internet".
- Validación real de la máscara de subred y aviso de gateway fuera de subred.
- Se recuerda la última interfaz elegida (fuera el `NETLAB-` fijo en el código).
- Log de diagnóstico en `%LOCALAPPDATA%\NetQuick` y errores de netsh con causa real.
- Una interfaz con error ya no tumba la lista completa de adaptadores.
- Conciencia de DPI: el widget se ve nítido con escalado de Windows (125/150 %).
- Al relanzar como administrador (modo fuente) ya no se pierden los valores tecleados.
- Versión visible en el widget y el tooltip de la bandeja; `__version__` en el código.
- Tests de `netops` con pytest + CI en GitHub Actions.
- Release automatizado: al crear un tag `v*` se compila el `.exe` y se publica con su hash SHA256.
- Desinstalador `uninstall.ps1` (revierte archivos, PATH, accesos, inicio con Windows y firewall).
- Lanzadores con ruta absoluta de `pythonw.exe` (ya no dependen del PATH).

## [1.2.1-beta] — 2026-07

- Refactor: una sola app clara (`netquick.py`); se eliminan `main.py` y `mini.py`.
- Estado de red sin depender del idioma/codificación de Windows (registro + psutil, sin parsear netsh).
- Elevación compatible con el `.exe` empaquetado (`uac_admin` en el manifest).
- La ventana ya nunca se cierra al aplicar cambios.
- UX: el color indica el modo activo (DHCP vs IP fija); el botón del modo activo queda en verde ✔.

## [1.2.0] — 2026-07

- Icono en la bandeja del sistema (la ✕ oculta; "Salir" en clic derecho).
- Escáner de red compatible con Dante: máscara real, link-local /16 y descubrimiento mDNS nativo.
- Detección de conflicto de IP antes de aplicar.
- Empaquetado `.exe` con PyInstaller.

## [1.1.0] — 2026-07

- Mini-widget flotante, perfiles guardados y validación de IP.

## [1.0.0] — 2026-07

- Primera versión: cambio de IP/DHCP por interfaz desde una ventana simple.
