# -*- coding: utf-8 -*-
"""
NetQuick Mini — widget flotante, siempre encima, para cambiar red/IP al vuelo.

- Campos con etiqueta clara (IP / Máscara / Gateway).
- Rueda ⚙ con configuración: iniciar con Windows + perfiles guardados.
- Perfiles: guarda combinaciones (ej. Casa / U / Trabajo) y aplícalas de 1 clic.
- Sin ventana negra: lánzalo con NetQuickMini.vbs (usa pythonw.exe).
"""
import json
import os
import shutil
import tkinter as tk
from tkinter import ttk

import netops

# Paleta
ACCENT = "#0072d5"
BG = "#1E293B"
CARD = "#273549"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
OK = "#10B981"
ERR = "#F87171"

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES_FILE = os.path.join(HERE, "profiles.json")
VBS_SRC = os.path.join(HERE, "NetQuickMini.vbs")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS_DST = os.path.join(STARTUP_DIR, "NetQuickMini.vbs")


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
    return os.path.exists(VBS_DST)


def set_startup(on):
    try:
        if on and os.path.exists(VBS_SRC):
            shutil.copyfile(VBS_SRC, VBS_DST)
        elif not on and os.path.exists(VBS_DST):
            os.remove(VBS_DST)
        return True
    except Exception:
        return False


class MiniWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=ACCENT)
        self.profiles = load_profiles()

        outer = tk.Frame(self.root, bg=ACCENT)
        outer.pack(fill="both", expand=True, padx=2, pady=2)
        self.card = tk.Frame(outer, bg=BG)
        self.card.pack(fill="both", expand=True)

        self._build_header()
        self._build_form()
        self._build_profiles()
        self.status = tk.Label(self.card, text="Listo", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 6))

        self.refrescar(select_default=True)
        self._place_bottom_right()
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

        for txt, cmd, hover in (("✕", self.root.destroy, ERR),
                                ("⟳", lambda: self.refrescar(), TEXT),
                                ("⚙", self.abrir_config, TEXT)):
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
        tk.Button(btns, text="Aplicar IP", bg=ACCENT, fg="white", bd=0,
                  activebackground="#0060b5", activeforeground="white",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=self.aplicar_ip).pack(side="left", ipadx=10, ipady=3)
        tk.Button(btns, text="Auto (DHCP)", bg=CARD, fg=TEXT, bd=0,
                  activebackground="#33465f", activeforeground="white",
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
        for nombre in self.profiles:
            tk.Button(self.prof_frame, text=nombre, bg=CARD, fg=TEXT, bd=0,
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

    # --- Arrastre -----------------------------------------------------------
    def _drag_start(self, ev):
        self._dx, self._dy = ev.x, ev.y

    def _drag_move(self, ev):
        self.root.geometry(f"+{self.root.winfo_x() + ev.x - self._dx}"
                           f"+{self.root.winfo_y() + ev.y - self._dy}")

    # --- Lógica -------------------------------------------------------------
    def refrescar(self, select_default=False):
        ifaces = netops.list_interfaces()
        self._map = {i["nombre"]: i["ip"] for i in ifaces}
        nombres = list(self._map.keys())
        self.iface["values"] = nombres
        if nombres and (select_default or self.iface.get() not in nombres):
            self.iface.set(next((n for n in nombres if n.startswith("NETLAB-")), nombres[0]))
        self._on_iface()

    def _on_iface(self):
        ip = self._map.get(self.iface.get(), "")
        self._put(self.ip, ip)
        self._put(self.mask, "255.255.255.0")
        self._put(self.gw, "")
        self._msg(f"Actual: {ip or 'sin IP'}", MUTED)

    def _msg(self, texto, color=MUTED):
        self.status.config(text=texto, fg=color)

    def _ensure_admin(self):
        if netops.is_admin():
            return True
        self._msg("Pidiendo permisos de administrador…", MUTED)
        netops.relaunch_as_admin(__file__)
        return False

    def aplicar_ip(self):
        nombre = self.iface.get()
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
        nombre = self.iface.get()
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
                  activebackground="#0060b5", activeforeground="white",
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


if __name__ == "__main__":
    MiniWidget()
