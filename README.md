<div align="center">

<img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows"/>
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/Version-1.3.0--beta-orange?style=for-the-badge" alt="Version"/>
<img src="https://img.shields.io/badge/Status-Beta%20%2F%20Demo%20in%20development-red?style=for-the-badge" alt="Status"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>

<br/><br/>

# ⚡ NetQuick

### *Switch fast, stress-free.*

**NetQuick** is a floating widget for Windows that lives in the system tray and lets you change your machine's IP/network in seconds — without opening Windows menus, without memorizing commands.

> ⚠️ **Beta / demo in active development.** It works and is used daily, but it may change without notice and contain bugs.

</div>

---

## 🚀 How to run NetQuick

**There is a single app: the floating widget with a system-tray icon.**

| Situation | Command |
|---|---|
| Install the `.exe` (recommended) | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install.ps1 \| iex` |
| Install from source (no .exe) | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/install-src.ps1 \| iex` |
| Repo already cloned (development) | `.\setup.ps1`, then double-click `NetQuick.vbs` |
| Directly with Python | `pythonw netquick.py` |
| **Uninstall** | `irm https://raw.githubusercontent.com/devmaiter/NetQuick/main/uninstall.ps1 \| iex` |

After installing, open a new terminal and type **`netquick`**, or use the Desktop shortcut.

> 🛡️ NetQuick needs **Administrator** permissions to change the network configuration; it only asks when needed.

---

## 🗂️ Repo structure

| File | What it is |
|---|---|
| `netquick.py` | **The application** — floating widget + tray icon |
| `netops.py` | Network operations (netsh, psutil, scanner, Dante mDNS, emergency revert) |
| `store.py` | Profile and configuration persistence (JSON with durable writes) |
| `winsetup.py` | Windows integration (auto-start, DPI, single instance) |
| `NetQuick.vbs` | Launcher without a console window (double-click) |
| `NetQuick.spec` | `.exe` packaging with PyInstaller |
| `install.ps1` / `install-src.ps1` | Terminal installers (`irm ... \| iex`) |
| `uninstall.ps1` | Uninstaller (reverts files, PATH, shortcuts and start-with-Windows) |
| `setup.ps1` | Development setup (installs dependencies) |
| `tests/` | Tests of `netops`, `store`, `winsetup` and the UI with fakes (pytest, run in CI) |
| `docs/` | [Engineering review 2026-07](docs/engineering-review-2026-07.md) — findings, invariants and follow-up backlog |
| `CHANGELOG.md` | Change history |

---

## 🚀 Features

| Feature | Description |
|---|---|
| 📌 **Floating widget** | Compact little bar, always on top, anchored bottom-right |
| 🔔 **Tray icon** | The ✕ hides the widget; clicking the icon shows it; "Quit" on right-click |
| 🏷️ **Saved profiles** | Save IP/mask/gateway combinations (*Home*, *Uni*, *Work*) and apply them in 1 click |
| 🔄 **DHCP / static IP** | Switch mode with one click; the color shows the active mode |
| 🔍 **Network scanner** | Compatible with Dante networks (real mask and link-local /16), native mDNS discovery |
| 🚫 **Duplicate-IP guard** | Before applying, checks the IP is free: ping + directed ARP probe (detects hosts silent to ping); if it can't verify, it says so |
| ⏪ **Auto-revert** | If the applied IP leaves you with no way out (the gateway doesn't respond), a 30 s countdown and automatic return to the previous config — the revert is 100% local |
| 🚦 **Honest states** | Green = clean success · amber = applied with warnings · red = not applied; never green hiding a problem |
| 📋 **Structured log** | Every attempt is recorded in `%LOCALAPPDATA%\NetQuick\netquick.log` with operation, result and duration |
| ⚙️ **Start with Windows** | Option in the widget's ⚙ gear |
| 🛡️ **Admin permissions** | Requested automatically when needed |

---

## 📦 Build the .exe

```powershell
pip install pyinstaller
pyinstaller NetQuick.spec
# result: dist\NetQuick.exe
```

> **Note:** Windows (Defender / Smart App Control) may block the `.exe` because it is unsigned. Running from source (`pythonw netquick.py`) does not have that problem.

The official `.exe` builds are compiled automatically in GitHub Actions when a `v*` tag is created, and each release publishes the executable's **SHA256 hash** so you can verify your download: `Get-FileHash NetQuick.exe -Algorithm SHA256`.

---

## 👥 Authors

<table>
  <tr>
    <td align="center"><b>Israel Moncayo</b></td>
    <td align="center"><b>Oscar Osorio</b></td>
  </tr>
</table>

---

## 📄 License

This project is under the MIT License. See the [LICENSE](LICENSE) file for details.

---

<div align="center">

*Made with ❤️ in Colombia 🇨🇴*

**Was it useful? Give the repo a ⭐!**

</div>
