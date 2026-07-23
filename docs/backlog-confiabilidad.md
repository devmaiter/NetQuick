# Backlog de confiabilidad — NetQuick

Ideas de operación de sistemas grandes, traídas a la escala real de NetQuick
(utilidad de escritorio Windows, un proceso, un usuario). Cada issue cita la
lección de la que sale. Varias lecciones **no aplican** a esta escala y se
listan al final para no hacer cargo-cult.

## Qué transfiere y qué no

| Lección | ¿Aplica a NetQuick? | Forma en miniatura |
|---|---|---|
| 9. SRE / error budget | **Sí** | SLO medible de `set_static`/`set_dhcp` desde el log estructurado (Issue A) |
| 10. Chaos Kong (evacuar región) | **Sí, en miniatura** | Ensayar la recuperación (botón DHCP) tras dejar la interfaz rota (Issue D) |
| 11. FoundationDB (sim. determinista) | **Sí, en miniatura** | Fuzzing con semilla fija → todo hallazgo reproducible (Issue E) |
| 12. CrystalNet (clonar la red) | **Sí, en miniatura** | Backend `SimOps`/dry-run que ensaya sin tocar el adaptador (Issue C) |
| 16. Erlang "let it crash" + supervisor | **Sí** | Supervisar el hilo del escáner: hoy un fallo lo deja colgado (Issue B) |
| 17/18. Plano de control corre elevado | **Sí (seguridad)** | Hallazgo de seguridad del arranque elevado — se maneja en privado (Issue F) |
| Knight Capital / deploy gradual + rollback | **Sí, en miniatura** | Rollback ensayado del .exe + probar el camino de arranque poco ejercitado (Issue G) |
| 13. Zelkova/Tiros (SMT, alcanzabilidad) | **No** | Overkill; la pregunta de red aquí es un escaneo LAN, no verificar políticas. El aviso "gateway fuera de subred" ya cubre lo útil. |
| 14. B4 (SDN WAN al 100%) | **No** | Sin relación con una app de escritorio. |
| 15. Meta PTP (tiempo como infra) | **No (sería feature, no fiabilidad)** | NetQuick no toca sincronización de reloj. Posible feature futura: mostrar grandmaster PTP en el escáner Dante — fuera de alcance de fiabilidad. |
| BGP / Pakistán (no confiar en anuncios) | **Ya cubierto** | El equivalente es no confiar en respuestas mDNS (spoofing FM-6 de la revisión); el botón "Web" abre la IP anunciada. Se refuerza en Issue B/F. |

---

## Issue A — SLO y presupuesto de error para aplicar red
**Lección 9 (Google SRE).** Prioridad: media. Etiquetas: `observabilidad`.

Ya se loggea cada intento (`op/resultado/motivo/dur_ms`). Falta convertir eso
en un SLO **medible**, no aspiracional.

- SLO propuesto: tasa de éxito de `set_static`/`set_dhcp` ≥ 99 % **excluyendo**
  `resultado=rechazo` (errores de validación del usuario, fuera del SLO);
  p99 de `dur_ms` < 1500 ms.
- Entregable: `tools/slo_report.py` que parsea `%LOCALAPPDATA%\NetQuick\netquick.log`
  y reporta conteo por resultado, tasa de éxito y p99 de latencia.
- Presupuesto de error en miniatura: si en las últimas N operaciones la tasa
  cae del SLO, es señal de que toca dedicar la próxima sesión a fiabilidad y no
  a features.
- Aceptación: `slo_report.py` corre sobre un log real y emite las 3 métricas.

## Issue B — Supervisar el hilo del escáner (bug de estado colgado)
**Lección 16 (Erlang "let it crash" + supervisores).** Prioridad: media-alta.
Etiquetas: `bug`.

`abrir_scanner.trabajo()` (`netquick.py:480`) llama `self.ops.scan_red(nombre)`
sin `try/except`. Si `scan_red` lanza (subprocess, sockets, parseo de una
interfaz en estado raro), el hilo muere, `terminar` nunca se agenda, y el botón
"Reescanear" queda **deshabilitado para siempre** con el estado congelado en
"Escaneando…". No hay supervisor que reponga el estado.

- Fix: envolver el trabajo en `try/except`; en el `after(0, …)` reactivar el
  botón y mostrar el error en `estado` en vez de tragarlo.
- Test: `FakeOps.scan_red` que lanza → el botón vuelve a `normal` y `estado`
  muestra error (con `FakeStore`, sin red).
- Aceptación: el escáner se recupera de un `scan_red` que falla; test en verde.

## Issue C — Modo dry-run (`SimOps`): ensayar sin tocar el adaptador
**Lecciones 10 + 12 (Chaos Kong / CrystalNet en miniatura).** Prioridad: media.
Etiquetas: `testing`, `arquitectura`.

El refactor ya dejó la costura `ops` inyectable. Un backend `SimOps` que simula
interfaces y `netsh` en memoria permite ejercitar el flujo completo (aplicar IP,
DHCP, escáner, perfiles) y los tests de caos **sin riesgo de romper la red real**
ni requerir admin. Es el "ensayo en réplica" a escala de un proceso.

- Entregable: `simops.py` con el mismo contrato que `netops` (list_interfaces,
  get_config, set_static, set_dhcp, scan_red, is_admin, fabricante_mac) sobre un
  estado en memoria mutable; opción `--sim` en el arranque para lanzar la UI real
  contra él.
- Habilita el Issue D como test automatizado.
- Aceptación: `MiniWidget(ops=SimOps())` arranca y aplicar IP/DHCP muta el estado
  simulado y se refleja en la UI.

## Issue D — Test de recuperación: config rota → volver con DHCP
**Lección 10 (Chaos Kong) + 18 (Meta: la recuperación no depende de lo roto).**
Prioridad: media. Etiquetas: `testing`, `fiabilidad`.

"El failover que nunca ejecutaste no existe." El plano de recuperación de
NetQuick es el botón DHCP, y es **local** (`netsh`, sin red ni DNS) — bien, no
depende de lo que rompió. Hay que **demostrarlo**, no suponerlo.

- Sobre `SimOps` (Issue C): dejar la interfaz en estado inconsistente y verificar
  que `aplicar_dhcp` la devuelve a un estado sano.
- Assert explícito del invariante de Meta 2021: la ruta de recuperación no invoca
  nada que dependa de la red (ni resolución DNS ni descubrimiento).
- Complemento manual: correr NetQuick en una VM Windows, aplicar una IP que corte
  la conectividad y confirmar recuperación con un clic (checklist en el issue).
- Aceptación: test de recuperación en verde sobre `SimOps`.

## Issue E — Fuzzing reproducible con semilla fija
**Lección 11 (FoundationDB / simulación determinista).** Prioridad: media-baja.
Etiquetas: `testing`.

Los experimentos de la revisión ya usaron `random.seed`. Formalizarlo: property
tests con Hypothesis, semilla fija en CI (`derandomize`), y la base de ejemplos
de Hypothesis versionada para que un fallo se reproduzca al instante.

- Entregable: `tests/test_propiedades.py` (parseo mDNS/ARP sin crash, `mascara_valida`
  ⇔ máscara contigua, `_validar_static`), `hypothesis` en un `requirements-dev.txt`,
  y el paso en CI.
- Aceptación: la suite property-based corre en CI de forma determinista.

## Issue F — Hallazgo de seguridad (se maneja en privado)
**Lección 17/18 (el plano de control corre elevado).** Prioridad: media (seguridad).

Se identificó un vector de elevación de privilegios local en el flujo de
auto-arranque elevado (FM-5 de la revisión formal). Los detalles del vector y el
experimento de confirmación **no se documentan en este repo público**: se
manejan en privado hasta confirmarlo y blindarlo. Archivar como issue con los
detalles cuando el repositorio pase a privado.

## Issue G — Rollback ensayado del release y camino de arranque poco probado
**Lección Knight Capital + Meta (deploy gradual, rollback ensayado, no reutilizar
rutas muertas).** Prioridad: media-baja. Etiquetas: `release`, `testing`.

- Rollback ensayado: documentar y probar volver a un release anterior del `.exe`
  (que `install.ps1` consume por `*.exe` del último release) — el rollback que no
  ensayaste no existe (Knight quebró en 45 min por eso).
- Camino poco ejercitado: `winsetup.set_startup` tiene dos ramas — `FROZEN`
  (schtasks) y desarrollo (.vbs). La rama no-FROZEN casi no se prueba: es el
  patrón "dos caminos, uno solo testeado" que hundió a Knight. Añadir un test del
  camino .vbs (crear/leer/borrar en `tmp_path`).
- Aceptación: procedimiento de rollback documentado y test del camino .vbs en verde.

---

## Ideas capturadas (2ª tanda, aún sin issue)

De las lecciones AT&T 1990 / Facebook 2021 / Cloudflare 2019 / Rogers 2022:

- **Mutation testing del validador** (Facebook 2021: el bug estaba en el *audit
  tool*). Correr `mutmut` apuntado a `_validar_static`/`mascara_valida`/`ip_valida`:
  si un mutante sobrevive, falta un test. El validador es el que decide si tocar
  la red — merece cobertura mutante, no solo de línea.
- **Assert de tiempo máximo por parse + "botón de pánico"** (Cloudflare 2019:
  ReDoS + *global kill*). (a) Añadir a los property tests de `_nombre_mdns`/
  `_parsear_arp` un assert de tiempo tope por parse, no solo de corrección.
  (b) Un comando/atajo de pánico que ponga la interfaz en DHCP conocido-bueno
  por el camino más tonto posible, sin pasar por validación ni estrategias.
- **Rollback con MÁS tests que el happy path** (AT&T 1990: falló el código de
  *recovery*). Refuerza #29: el camino de reversión se ejecuta solo cuando algo
  ya salió mal, así que es el que más pruebas necesita.

Nota: el hallazgo de seguridad FM-5 se maneja en privado; archivar como issue
con los detalles cuando el repo pase a privado y/o tras confirmarlo.

### Lecciones descartadas (por qué NO aplican)
- **Zelkova/Tiros (SMT):** verificación formal de políticas; NetQuick no tiene
  políticas de alcanzabilidad que probar. El check gateway-en-subred ya cubre lo útil.
- **B4 (SDN WAN):** infraestructura planetaria; nada que tomar para un widget.
- **Meta PTP:** sería una *feature* (mostrar reloj PTP en el escáner), no fiabilidad.
