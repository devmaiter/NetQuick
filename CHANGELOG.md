# Changelog

NetQuick change history. The code version lives in `netquick.py`
(`__version__`) and is the single source of truth.

## [1.3.0-beta] — unreleased

- Static coherence preflight (issue #26): before any netsh, the whole config is
  checked as a set — gateway inside the subnet (now a rejection, no longer an
  applied-with-warning), IP not the network/broadcast address, IP ≠ gateway —
  with a specific message per rule.
- Simulated dry run (issue #28): `pythonw netquick.py --sim` runs the real UI
  against an in-memory network (`simops.py`) — no admin, nothing real touched;
  the auto-revert flow is now an automated test on top of it.
- Supervised operations (issue #25): an unexpected exception while applying,
  reverting or scanning can no longer leave the widget zombie — it's logged
  with its traceback, reported honestly in red, and every control stays usable.
- Error-budget report (issue #24): `python report.py` summarizes the structured
  log — success rate per operation vs a 99% target, top failure reasons and
  duration percentiles; exit code 1 on breach.
- Property-based tests (issue #23): hypothesis generates the cases for the
  parsers and validators, derandomized so failures reproduce identically.
- Rehearsed rollback (issue #29): `install.ps1` accepts `NETQUICK_TAG` to pin a
  previous release and verifies the published SHA256 of the download; procedure
  and rehearsal record in `docs/rollback.md`.
- The July engineering review is versioned in
  `docs/engineering-review-2026-07.md` (issue #27).
- Security (FM-5): NetQuick no longer auto-registers to start with Windows on
  first run — it opens, stays in the tray, and start-with-Windows is a user
  option in ⚙ (off by default). When enabled, the `task.xml` is generated in
  `%SystemRoot%\Temp` (admin only), not in `%APPDATA%`, closing the local
  privilege-escalation TOCTOU window. The insecure `Run` key from previous
  versions is removed without recreating the task.
- Auto-revert (issue #21): after applying a static IP the gateway is verified;
  if it doesn't respond, a 30 s countdown with a "Keep change" button and an
  automatic return to the previous configuration. The revert goes through
  direct netsh, with no dependency on the network (Meta 2021 lesson).
- Stronger in-use IP detection (issue #20 / FM-2): a directed ARP probe for
  hosts silent to ping; outside the local subnet certainty is no longer faked
  — it applies with the warning "could not verify that the IP was free".
- Transactional honesty (issue #22): if DNS fails after applying the IP, the
  result is a failure (red), not a success with fine print; a third amber
  state for "applied with warnings".
- Durable profile/config writes and a structured per-attempt log
  (op/result/reason/duration) in `%LOCALAPPDATA%\NetQuick\netquick.log`.
- Testable refactor: instantiable UI with injectable operations and
  persistence (`store.py`, `winsetup.py`); 93 tests with fakes, ruff and a
  minimum coverage gate in CI.

## [1.2.2-beta] — 2026-07-18

- DNS field when applying a static IP — goodbye to "I have an IP but no internet".
- Real subnet-mask validation and a warning for a gateway outside the subnet.
- The last chosen interface is remembered (out with the hardcoded `NETLAB-`).
- Diagnostic log in `%LOCALAPPDATA%\NetQuick` and netsh errors with the real cause.
- An interface with an error no longer takes down the whole adapter list.
- DPI awareness: the widget looks crisp with Windows scaling (125/150%).
- Relaunching as administrator (source mode) no longer loses the typed values.
- Version visible in the widget and the tray tooltip; `__version__` in the code.
- `netops` tests with pytest + CI on GitHub Actions.
- Automated release: creating a `v*` tag builds the `.exe` and publishes it with its SHA256 hash.
- `uninstall.ps1` uninstaller (reverts files, PATH, shortcuts, start-with-Windows and firewall).
- Launchers with the absolute path to `pythonw.exe` (no longer depend on the PATH).

## [1.2.1-beta] — 2026-07

- Refactor: a single clear app (`netquick.py`); `main.py` and `mini.py` removed.
- Network state independent of Windows language/encoding (registry + psutil, no netsh parsing).
- Elevation compatible with the packaged `.exe` (`uac_admin` in the manifest).
- The window never closes on applying changes anymore.
- UX: the color shows the active mode (DHCP vs static IP); the active mode's button turns green ✔.

## [1.2.0] — 2026-07

- System-tray icon (the ✕ hides; "Quit" on right-click).
- Dante-compatible network scanner: real mask, link-local /16 and native mDNS discovery.
- IP conflict detection before applying.
- `.exe` packaging with PyInstaller.

## [1.1.0] — 2026-07

- Floating mini-widget, saved profiles and IP validation.

## [1.0.0] — 2026-07

- First version: change IP/DHCP per interface from a simple window.
