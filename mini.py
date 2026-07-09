# -*- coding: utf-8 -*-
"""
NetQuick Mini — widget flotante, siempre encima, para cambiar red/IP al vuelo.

- Campos con etiqueta clara (IP / Máscara / Gateway).
- Rueda ⚙ con configuración: iniciar con Windows + perfiles guardados.
- Perfiles: guarda combinaciones (ej. Casa / U / Trabajo) y aplícalas de 1 clic.
- Sin ventana negra: lánzalo con NetQuickMini.vbs (usa pythonw.exe).
- Icono en la bandeja del sistema: la ✕ oculta el widget; clic en el icono
  lo muestra de nuevo. "Salir" está en el menú del icono (clic derecho).
"""
import ctypes
import json
import os
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
import winreg
from tkinter import ttk

import netops

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_DISPONIBLE = True
except ImportError:
    TRAY_DISPONIBLE = False

# Paleta — estilo Dante: blanco, verde y rojo
ACCENT = "#43A047"        # verde (acción principal, borde)
ACCENT_DARK = "#2E7D32"   # verde oscuro (hover)
BG = "#FFFFFF"            # fondo blanco
CARD = "#F3F4F6"          # gris claro (campos, botones secundarios)
CARD_HOVER = "#E5E7EB"
TEXT = "#1F2937"          # texto principal oscuro
MUTED = "#6B7280"         # texto secundario
OK = "#2E7D32"            # verde estado
ERR = "#E53935"           # rojo estado / errores

# Prefijos MAC (OUI) de fabricantes habituales en redes de audio
OUI_CONOCIDOS = {
    "00-1d-c1": "Audinate (Dante)",
    "00-a0-de": "Yamaha",
    "00-0e-dd": "Shure",
    "00-60-74": "QSC",
    "00-04-c4": "Allen & Heath",
    "b8-27-eb": "Raspberry Pi",
    "dc-a6-32": "Raspberry Pi",
}

# Empaquetado con PyInstaller: __file__ apunta a una carpeta temporal, así que
# los datos del usuario (perfiles) van a %APPDATA%\NetQuick.
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
if FROZEN:
    APP_DIR = os.path.join(os.environ.get("APPDATA", HERE), "NetQuick")
    os.makedirs(APP_DIR, exist_ok=True)
else:
    APP_DIR = HERE
PROFILES_FILE = os.path.join(APP_DIR, "profiles.json")
FIRSTRUN_FILE = os.path.join(APP_DIR, ".firstrun")
VBS_SRC = os.path.join(HERE, "NetQuickMini.vbs")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS_DST = os.path.join(STARTUP_DIR, "NetQuickMini.vbs")

# Como .exe el inicio con Windows se registra en HKCU\...\Run (más fiable
# que copiar archivos y fácil de quitar desde la rueda ⚙ o el Administrador
# de tareas > Aplicaciones de inicio).
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "NetQuick"


# --- Persistencia de perfiles ----------------------------------------------
def load_profiles():
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_profiles(data):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Inicio con Windows ----------------------------------------------------
def in_startup():
    if FROZEN:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, RUN_NAME)
            return True
        except OSError:
            return False
    return os.path.exists(VBS_DST)


def set_startup(on):
    try:
        if FROZEN:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ,
                                      f'"{sys.executable}"')
                else:
                    try:
                        winreg.DeleteValue(k, RUN_NAME)
                    except FileNotFoundError:
                        pass
            return True
        if on and os.path.exists(VBS_SRC):
            shutil.copyfile(VBS_SRC, VBS_DST)
        elif not on and os.path.exists(VBS_DST):
            os.remove(VBS_DST)
        return True
    except Exception:
        return False


def primer_arranque_exe():
    """La primera vez que corre el .exe se auto-registra para iniciar con
    Windows (queda siempre en la bandeja). Solo una vez: si el usuario lo
    desactiva en ⚙, se respeta su elección."""
    if not FROZEN or os.path.exists(FIRSTRUN_FILE):
        return
    set_startup(True)
    try:
        with open(FIRSTRUN_FILE, "w") as f:
            f.write("ok")
    except Exception:
        pass


class MiniWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=ACCENT)
        self.profiles = load_profiles()
        self._map = {}
        self._display = {}

        outer = tk.Frame(self.root, bg=ACCENT)
        outer.pack(fill="both", expand=True, padx=2, pady=2)
        self.card = tk.Frame(outer, bg=BG)
        self.card.pack(fill="both", expand=True)

        self._build_header()
        self._build_form()
        self._build_profiles()
        self.status = tk.Label(self.card, text="Listo", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8, "bold"), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 6))

        self.refrescar(select_default=True)
        self._place_bottom_right()
        self.tray = None
        if TRAY_DISPONIBLE:
            self._init_tray()
        self.root.mainloop()

    def _place_bottom_right(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - w - 24}+{sh - h - 64}")

    # --- Cabecera -----------------------------------------------------------
    def _build_header(self):
        head = tk.Frame(self.card, bg=BG)
        head.pack(fill="x", padx=10, pady=(7, 2))
        tk.Label(head, text="⚡ NetQuick", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        for txt, cmd, hover in (("✕", self.cerrar, ERR),
                                ("⟳", lambda: self.refrescar(), TEXT),
                                ("⚙", self.abrir_config, TEXT),
                                ("🔍", self.abrir_scanner, TEXT)):
            tk.Button(head, text=txt, bg=BG, fg=MUTED, bd=0, activebackground=BG,
                      activeforeground=hover, font=("Segoe UI", 11),
                      cursor="hand2", command=cmd).pack(side="right", padx=3)

        head.bind("<Button-1>", self._drag_start)
        head.bind("<B1-Motion>", self._drag_move)

    def _build_form(self):
        body = tk.Frame(self.card, bg=BG)
        body.pack(fill="x", padx=10)

        tk.Label(body, text="Interfaz de red", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=0, column=0, columnspan=3, sticky="w")
        self.iface = ttk.Combobox(body, state="readonly", font=("Segoe UI", 9))
        self.iface.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 6))
        self.iface.bind("<<ComboboxSelected>>", lambda e: self._on_iface())

        # Etiquetas claras encima de cada campo
        for col, txt in ((0, "IP del equipo"), (1, "Máscara de subred"), (2, "Puerta de enlace")):
            tk.Label(body, text=txt, bg=BG, fg=MUTED,
                     font=("Segoe UI", 8)).grid(row=2, column=col, sticky="w", padx=(0, 6))

        self.ip = self._entry(body); self.ip.grid(row=3, column=0, padx=(0, 6), sticky="we")
        self.mask = self._entry(body); self.mask.grid(row=3, column=1, padx=(0, 6), sticky="we")
        self.gw = self._entry(body); self.gw.grid(row=3, column=2, sticky="we")
        for c in range(3):
            body.columnconfigure(c, weight=1)

        btns = tk.Frame(self.card, bg=BG)
        btns.pack(fill="x", padx=10, pady=(8, 4))
        self.btn_aplicar = tk.Button(btns, text="Aplicar IP", bg=ACCENT, fg="white", bd=0,
                                     activebackground=ACCENT_DARK, activeforeground="white",
                                     font=("Segoe UI", 9, "bold"), cursor="hand2",
                                     command=self.aplicar_ip)
        self.btn_aplicar.pack(side="left", ipadx=10, ipady=3)
        # El botón refleja el estado: al escribir una IP distinta vuelve a "Aplicar IP"
        self.ip.bind("<KeyRelease>", lambda e: self._update_apply_btn())
        tk.Button(btns, text="Auto (DHCP)", bg=CARD, fg=TEXT, bd=0,
                  activebackground=CARD_HOVER, activeforeground=TEXT,
                  font=("Segoe UI", 9), cursor="hand2",
                  command=self.aplicar_dhcp).pack(side="left", padx=6, ipadx=8, ipady=3)

    def _build_profiles(self):
        self.prof_frame = tk.Frame(self.card, bg=BG)
        self.prof_frame.pack(fill="x", padx=10, pady=(0, 2))
        self._render_profiles()

    def _render_profiles(self):
        for w in self.prof_frame.winfo_children():
            w.destroy()
        if not self.profiles:
            return
        tk.Label(self.prof_frame, text="Perfiles:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        # El perfil cuya IP coincide con la actual se resalta en verde con ✔
        ip_actual = self._map.get(self._iface_name(), "")
        for nombre, p in self.profiles.items():
            activo = bool(ip_actual) and p.get("ip") == ip_actual
            tk.Button(self.prof_frame,
                      text=("✔ " + nombre) if activo else nombre,
                      bg=ACCENT if activo else CARD,
                      fg="white" if activo else TEXT, bd=0,
                      activebackground=ACCENT, activeforeground="white",
                      font=("Segoe UI", 8, "bold"), cursor="hand2",
                      command=lambda n=nombre: self.aplicar_perfil(n)
                      ).pack(side="left", padx=2, ipadx=5, ipady=1)

    def _entry(self, parent):
        return tk.Entry(parent, bg=CARD, fg=TEXT, bd=0, insertbackground=TEXT,
                        font=("Consolas", 9), justify="center")

    # --- Helpers de campos --------------------------------------------------
    def _val(self, e):
        return e.get().strip()

    def _put(self, e, value):
        e.delete(0, "end")
        if value:
            e.insert(0, value)

    # --- Bandeja del sistema -------------------------------------------------
    def _tray_image(self):
        """Dibuja el icono: cuadrito azul con un rayo blanco."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 4, 60, 60), radius=14, fill=ACCENT)
        d.polygon([(37, 9), (17, 36), (29, 36), (26, 55), (47, 27), (34, 27)],
                  fill="white")
        return img

    def _init_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar / Ocultar", self._tray_toggle, default=True),
            pystray.MenuItem("Salir", self._tray_quit),
        )
        self.tray = pystray.Icon("NetQuickMini", self._tray_image(),
                                 "NetQuick Mini — clic para mostrar/ocultar", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_toggle(self, icon=None, item=None):
        # pystray corre en otro hilo: pasar la orden al hilo de tkinter
        self.root.after(0, self._toggle_visible)

    def _toggle_visible(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self._place_bottom_right()
        else:
            self.root.withdraw()

    def _tray_quit(self, icon=None, item=None):
        if self.tray:
            self.tray.stop()
        self.root.after(0, self.root.destroy)

    def cerrar(self):
        """✕: si hay icono de bandeja, solo oculta; si no, cierra del todo."""
        if self.tray:
            self.root.withdraw()
        else:
            self.root.destroy()

    # --- Arrastre -----------------------------------------------------------
    def _drag_start(self, ev):
        self._dx, self._dy = ev.x, ev.y

    def _drag_move(self, ev):
        self.root.geometry(f"+{self.root.winfo_x() + ev.x - self._dx}"
                           f"+{self.root.winfo_y() + ev.y - self._dy}")

    # --- Lógica -------------------------------------------------------------
    def _iface_name(self):
        """Nombre real de la interfaz elegida (el combo muestra 'nombre — IP')."""
        return self._display.get(self.iface.get(), self.iface.get())

    def refrescar(self, select_default=False):
        ifaces = netops.list_interfaces()
        actual = self._iface_name()
        self._map = {i["nombre"]: i["ip"] for i in ifaces}
        # El combo muestra también la IP para distinguir las interfaces de un vistazo
        self._display = {f"{n} — {ip or 'sin IP'}": n for n, ip in self._map.items()}
        self.iface["values"] = list(self._display.keys())
        nombres = list(self._map.keys())
        if nombres and (select_default or actual not in self._map):
            actual = next((n for n in nombres if n.startswith("NETLAB-")), nombres[0])
        for disp, n in self._display.items():
            if n == actual:
                self.iface.set(disp)
                break
        self._on_iface()

    def _on_iface(self):
        nombre = self._iface_name()
        ip = self._map.get(nombre, "")
        self._put(self.ip, ip)
        self._put(self.mask, "255.255.255.0")
        self._put(self.gw, "")
        # Estado siempre visible: en qué interfaz estás y con qué IP quedó
        if nombre:
            self._msg(f"● {nombre}  ·  {ip or 'sin IP'}", OK if ip else ERR)
        else:
            self._msg("Sin interfaces activas", ERR)
        self._render_profiles()
        self._update_apply_btn()

    def _update_apply_btn(self):
        """Verde de confirmación en el propio botón: '✔ IP aplicada' cuando la
        IP del campo es la que ya tiene la interfaz."""
        if not hasattr(self, "btn_aplicar"):
            return
        ip_actual = self._map.get(self._iface_name(), "")
        if ip_actual and self._val(self.ip) == ip_actual:
            self.btn_aplicar.config(text="✔ IP aplicada", bg=ACCENT_DARK)
        else:
            self.btn_aplicar.config(text="Aplicar IP", bg=ACCENT)

    def _msg(self, texto, color=MUTED):
        self.status.config(text=texto, fg=color)

    def _ensure_admin(self):
        if netops.is_admin():
            return True
        self._msg("Pidiendo permisos de administrador…", MUTED)
        netops.relaunch_as_admin(__file__)
        return False

    def aplicar_ip(self):
        nombre = self._iface_name()
        if not nombre:
            return self._msg("Elige una interfaz", ERR)
        if not self._ensure_admin():
            return
        ok, msg = netops.set_static(nombre, self._val(self.ip),
                                    self._val(self.mask) or "255.255.255.0",
                                    self._val(self.gw))
        self._msg(("✔ " if ok else "✗ ") + msg, OK if ok else ERR)
        if ok:
            self.refrescar()

    def aplicar_dhcp(self):
        nombre = self._iface_name()
        if not nombre:
            return self._msg("Elige una interfaz", ERR)
        if not self._ensure_admin():
            return
        ok, msg = netops.set_dhcp(nombre)
        self._msg(("✔ " if ok else "✗ ") + msg, OK if ok else ERR)
        if ok:
            self.refrescar()

    def aplicar_perfil(self, nombre):
        p = self.profiles.get(nombre, {})
        self._put(self.ip, p.get("ip", ""))
        self._put(self.mask, p.get("mask", "255.255.255.0"))
        self._put(self.gw, p.get("gw", ""))
        self.aplicar_ip()

    # --- Escáner de dispositivos ---------------------------------------------
    def abrir_scanner(self):
        nombre = self._iface_name()
        if not nombre:
            return self._msg("Elige una interfaz", ERR)

        win = tk.Toplevel(self.root)
        win.title("Dispositivos en la red — NetQuick")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.geometry("460x400")

        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(head, text="Dispositivos en la red", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        btn_re = tk.Button(head, text="⟳ Reescanear", bg=ACCENT, fg="white", bd=0,
                           activebackground=ACCENT_DARK, activeforeground="white",
                           font=("Segoe UI", 8, "bold"), cursor="hand2")
        btn_re.pack(side="right", ipadx=8, ipady=2)

        estado = tk.Label(win, text="", bg=BG, fg=MUTED,
                          font=("Segoe UI", 8), anchor="w")
        estado.pack(fill="x", padx=14)

        lista = tk.Frame(win, bg=BG)
        lista.pack(fill="both", expand=True, padx=14, pady=8)

        def render(dispositivos):
            if not win.winfo_exists():
                return
            for w in lista.winfo_children():
                w.destroy()
            if not dispositivos:
                estado.config(text="✗ Ningún equipo respondió", fg=ERR)
                return
            estado.config(text=f"✔ {len(dispositivos)} dispositivos encontrados",
                          fg=OK)
            for d in dispositivos:
                row = tk.Frame(lista, bg=CARD)
                row.pack(fill="x", pady=2)
                tk.Label(row, text="●", bg=CARD, fg=OK,
                         font=("Segoe UI", 10)).pack(side="left", padx=(8, 4))
                texto = d["ip"] + ("  (este PC)" if d["propia"] else "")
                tk.Label(row, text=texto, bg=CARD, fg=TEXT, font=("Consolas", 9),
                         width=22, anchor="w").pack(side="left")
                fabricante = OUI_CONOCIDOS.get(d["mac"][:8], "")
                detalle = f"{d['mac']}  {fabricante}".strip() if d["mac"] else ""
                tk.Label(row, text=detalle, bg=CARD, fg=MUTED,
                         font=("Segoe UI", 8), anchor="w"
                         ).pack(side="left", fill="x", expand=True)
                if not d["propia"]:
                    tk.Button(row, text="Web", bg=CARD, fg=ERR, bd=0,
                              activebackground=CARD_HOVER, activeforeground=ERR,
                              font=("Segoe UI", 8, "bold"), cursor="hand2",
                              command=lambda ip=d["ip"]:
                                  webbrowser.open(f"http://{ip}")
                              ).pack(side="right", padx=8, pady=2)

        def escanear():
            ip = netops.get_ip(nombre)
            if not ip:
                estado.config(text="✗ La interfaz no tiene IP", fg=ERR)
                return
            prefijo = ip.rsplit(".", 1)[0]
            estado.config(text=f"Escaneando {prefijo}.1–254…", fg=ERR)
            btn_re.config(state="disabled")

            def trabajo():
                dispositivos = netops.scan_red(nombre)
                def terminar():
                    if win.winfo_exists():
                        btn_re.config(state="normal")
                        render(dispositivos)
                self.root.after(0, terminar)

            threading.Thread(target=trabajo, daemon=True).start()

        btn_re.config(command=escanear)
        escanear()

    # --- Ventana de configuración ------------------------------------------
    def abrir_config(self):
        win = tk.Toplevel(self.root)
        win.title("Configuración — NetQuick")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.geometry("360x420")

        tk.Label(win, text="⚙ Configuración", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 8))

        # Inicio con Windows
        self.startup_var = tk.BooleanVar(value=in_startup())
        chk = tk.Checkbutton(win, text="Iniciar con Windows (siempre visible)",
                             variable=self.startup_var, bg=BG, fg=TEXT,
                             selectcolor=CARD, activebackground=BG, activeforeground=TEXT,
                             font=("Segoe UI", 9), cursor="hand2",
                             command=lambda: self._toggle_startup(win))
        chk.pack(anchor="w", padx=16)

        tk.Frame(win, bg=CARD, height=1).pack(fill="x", padx=16, pady=12)

        # Perfiles
        tk.Label(win, text="Perfiles guardados", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16)
        tk.Label(win, text="Guarda una IP/máscara/gateway con un nombre y aplícala de 1 clic.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=320,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 6))

        self.prof_list = tk.Frame(win, bg=BG)
        self.prof_list.pack(fill="x", padx=16)
        self._render_config_profiles(win)

        # Guardar los valores actuales como perfil nuevo
        add = tk.Frame(win, bg=BG)
        add.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(add, text="Nombre:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        name_e = tk.Entry(add, bg=CARD, fg=TEXT, bd=0, insertbackground=TEXT,
                          font=("Segoe UI", 9), width=12)
        name_e.pack(side="left", padx=6, ipady=2)
        tk.Button(add, text="Guardar valores actuales", bg=ACCENT, fg="white", bd=0,
                  activebackground=ACCENT_DARK, activeforeground="white",
                  font=("Segoe UI", 8, "bold"), cursor="hand2",
                  command=lambda: self._guardar_perfil(name_e.get(), win)
                  ).pack(side="left", ipadx=4, ipady=2)

    def _render_config_profiles(self, win):
        for w in self.prof_list.winfo_children():
            w.destroy()
        if not self.profiles:
            tk.Label(self.prof_list, text="(aún no hay perfiles)", bg=BG, fg=MUTED,
                     font=("Segoe UI", 9, "italic")).pack(anchor="w")
            return
        for nombre, p in self.profiles.items():
            row = tk.Frame(self.prof_list, bg=CARD)
            row.pack(fill="x", pady=2)
            det = f"{nombre}:  {p.get('ip', '?')} / {p.get('mask', '?')}"
            if p.get("gw"):
                det += f"  gw {p['gw']}"
            tk.Label(row, text=det, bg=CARD, fg=TEXT, font=("Segoe UI", 8),
                     anchor="w").pack(side="left", fill="x", expand=True, padx=8, pady=4)
            tk.Button(row, text="🗑", bg=CARD, fg=ERR, bd=0, activebackground=CARD,
                      cursor="hand2", font=("Segoe UI", 9),
                      command=lambda n=nombre: self._borrar_perfil(n, win)
                      ).pack(side="right", padx=6)

    def _guardar_perfil(self, nombre, win):
        nombre = nombre.strip()
        if not nombre:
            return
        self.profiles[nombre] = {
            "ip": self._val(self.ip),
            "mask": self._val(self.mask) or "255.255.255.0",
            "gw": self._val(self.gw),
        }
        save_profiles(self.profiles)
        self._render_config_profiles(win)
        self._render_profiles()

    def _borrar_perfil(self, nombre, win):
        self.profiles.pop(nombre, None)
        save_profiles(self.profiles)
        self._render_config_profiles(win)
        self._render_profiles()

    def _toggle_startup(self, win):
        ok = set_startup(self.startup_var.get())
        if not ok:
            self.startup_var.set(in_startup())


def _ya_corriendo():
    """Evita instancias (e iconos de bandeja) duplicados."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "NetQuickMini_Instancia")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if not _ya_corriendo():
        primer_arranque_exe()
        MiniWidget()
