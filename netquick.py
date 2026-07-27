# -*- coding: utf-8 -*-
"""
NetQuick Mini — floating widget, always on top, to change network/IP on the fly.

- Fields with clear labels (IP / Mask / Gateway).
- ⚙ gear with settings: start with Windows + saved profiles.
- Profiles: save combinations (e.g. Home / Uni / Work) and apply them in 1 click.
- No black window: launch it with NetQuick.vbs (uses pythonw.exe).
- System tray icon: the ✕ hides the widget; clicking the icon shows it
  again. "Quit" is in the icon's menu (right-click).
"""
import argparse
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import netops
import store
import winsetup

__version__ = "1.3.0-beta"

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Palette — Dante style: white, green and red
ACCENT = "#43A047"        # green (primary action, border)
ACCENT_DARK = "#2E7D32"   # dark green (hover)
BG = "#FFFFFF"            # white background
CARD = "#F3F4F6"          # light gray (fields, secondary buttons)
CARD_HOVER = "#E5E7EB"
TEXT = "#1F2937"          # dark primary text
MUTED = "#6B7280"         # secondary text
OK = "#2E7D32"            # green status (clean success)
WARN = "#B45309"          # amber (applied, but with warnings)
ERR = "#E53935"           # red status / errors (nothing applied)

class MiniWidget:
    def __init__(self, ops=netops, store_mod=store):
        # Network operations and persistence are injected: in the app they are
        # the netops/store modules, in the tests doubles that touch nothing.
        self.ops = ops
        self.store = store_mod
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=ACCENT)
        self.profiles = self.store.load_profiles()
        self.config = self.store.load_config()
        self._map = {}
        self._display = {}
        self._revert_previous = None
        self._revert_after = None

        outer = tk.Frame(self.root, bg=ACCENT)
        outer.pack(fill="both", expand=True, padx=2, pady=2)
        self.card = tk.Frame(outer, bg=BG)
        self.card.pack(fill="both", expand=True)

        self._build_header()
        self._build_form()
        self._build_profiles()
        self.status = tk.Label(self.card, text="Ready", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8, "bold"), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 2))
        self._build_revert_frame()
        tk.Label(self.card, text="© 2026 Oscar Julián Osorio & Israel Moncayo",
                 bg=BG, fg="#B9BFC7", font=("Segoe UI", 7), anchor="e"
                 ).pack(fill="x", padx=12, pady=(0, 5))

        self.refresh(select_default=True)
        self._repopulate_after_relaunch()
        self._place_bottom_right()
        self.tray = None
        if TRAY_AVAILABLE:
            self._init_tray()

    def run(self):
        self.root.mainloop()

    def _place_bottom_right(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - w - 24}+{sh - h - 64}")

    # --- Header -------------------------------------------------------------
    def _build_header(self):
        head = tk.Frame(self.card, bg=BG)
        head.pack(fill="x", padx=10, pady=(7, 2))
        tk.Label(head, text="⚡ NetQuick", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(head, text=f"v{__version__}", bg=BG, fg=ERR,
                 font=("Segoe UI", 7, "italic")).pack(side="left",
                                                      padx=(4, 0), pady=(3, 0))

        for txt, cmd, hover in (("✕", self.close, ERR),
                                ("⟳", lambda: self.refresh(), TEXT),
                                ("⚙", self.open_config, TEXT),
                                ("🔍", self.open_scanner, TEXT)):
            tk.Button(head, text=txt, bg=BG, fg=MUTED, bd=0, activebackground=BG,
                      activeforeground=hover, font=("Segoe UI", 11),
                      cursor="hand2", command=cmd).pack(side="right", padx=3)

        head.bind("<Button-1>", self._drag_start)
        head.bind("<B1-Motion>", self._drag_move)

    def _build_form(self):
        body = tk.Frame(self.card, bg=BG)
        body.pack(fill="x", padx=10)

        tk.Label(body, text="Network interface", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).grid(row=0, column=0, columnspan=4, sticky="w")
        self.iface = ttk.Combobox(body, state="readonly", font=("Segoe UI", 9))
        self.iface.grid(row=1, column=0, columnspan=4, sticky="we", pady=(0, 6))
        self.iface.bind("<<ComboboxSelected>>", lambda e: self._iface_chosen())

        # Clear labels above each field
        for col, txt in ((0, "Device IP"), (1, "Subnet mask"),
                         (2, "Gateway"), (3, "DNS (e.g. 8.8.8.8)")):
            tk.Label(body, text=txt, bg=BG, fg=MUTED,
                     font=("Segoe UI", 8)).grid(row=2, column=col, sticky="w", padx=(0, 6))

        self.ip = self._entry(body)
        self.ip.grid(row=3, column=0, padx=(0, 6), sticky="we")
        self.mask = self._entry(body)
        self.mask.grid(row=3, column=1, padx=(0, 6), sticky="we")
        self.gw = self._entry(body)
        self.gw.grid(row=3, column=2, padx=(0, 6), sticky="we")
        self.dns = self._entry(body)
        self.dns.grid(row=3, column=3, sticky="we")
        for c in range(4):
            body.columnconfigure(c, weight=1)

        btns = tk.Frame(self.card, bg=BG)
        btns.pack(fill="x", padx=10, pady=(8, 4))
        self.btn_apply = tk.Button(btns, text="Apply IP", bg=ACCENT, fg="white", bd=0,
                                   activebackground=ACCENT_DARK, activeforeground="white",
                                   font=("Segoe UI", 9, "bold"), cursor="hand2",
                                   command=self.apply_ip)
        self.btn_apply.pack(side="left", ipadx=10, ipady=3)
        self.btn_dhcp = tk.Button(btns, text="Auto (DHCP)", bg=CARD, fg=TEXT, bd=0,
                                  activebackground=CARD_HOVER, activeforeground=TEXT,
                                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                                  command=self.apply_dhcp)
        self.btn_dhcp.pack(side="left", padx=6, ipadx=8, ipady=3)
        # When editing IP/mask/gateway, "Apply IP" lights up (pending change)
        for field in (self.ip, self.mask, self.gw, self.dns):
            field.bind("<KeyRelease>", lambda e: self._update_mode_buttons())

    def _build_profiles(self):
        self.prof_frame = tk.Frame(self.card, bg=BG)
        self.prof_frame.pack(fill="x", padx=10, pady=(0, 2))
        self._render_profiles()

    def _render_profiles(self):
        for w in self.prof_frame.winfo_children():
            w.destroy()
        if not self.profiles:
            return
        tk.Label(self.prof_frame, text="Profiles:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        # The profile whose IP matches the current one is highlighted green with ✔
        current_ip = self._map.get(self._iface_name(), "")
        for name, p in self.profiles.items():
            active = bool(current_ip) and p.get("ip") == current_ip
            tk.Button(self.prof_frame,
                      text=("✔ " + name) if active else name,
                      bg=ACCENT if active else CARD,
                      fg="white" if active else TEXT, bd=0,
                      activebackground=ACCENT, activeforeground="white",
                      font=("Segoe UI", 8, "bold"), cursor="hand2",
                      command=lambda n=name: self.apply_profile(n)
                      ).pack(side="left", padx=2, ipadx=5, ipady=1)

    def _entry(self, parent):
        return tk.Entry(parent, bg=CARD, fg=TEXT, bd=0, insertbackground=TEXT,
                        font=("Consolas", 9), justify="center")

    # --- Field helpers ------------------------------------------------------
    def _val(self, e):
        return e.get().strip()

    def _put(self, e, value):
        e.delete(0, "end")
        if value:
            e.insert(0, value)

    # --- System tray --------------------------------------------------------
    def _tray_image(self):
        """Draw the icon: little green square with a white lightning bolt."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 4, 60, 60), radius=14, fill=ACCENT)
        d.polygon([(37, 9), (17, 36), (29, 36), (26, 55), (47, 27), (34, 27)],
                  fill="white")
        return img

    def _init_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._tray_toggle, default=True),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self.tray = pystray.Icon("NetQuick", self._tray_image(),
                                 f"NetQuick v{__version__} — click to show/hide",
                                 menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_toggle(self, icon=None, item=None):
        # pystray runs on another thread: hand the order to the tkinter thread
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

    def close(self):
        """✕: if there's a tray icon, only hide; otherwise close entirely."""
        if self.tray:
            self.root.withdraw()
        else:
            self.root.destroy()

    # --- Dragging -----------------------------------------------------------
    def _drag_start(self, ev):
        self._dx, self._dy = ev.x, ev.y

    def _drag_move(self, ev):
        self.root.geometry(f"+{self.root.winfo_x() + ev.x - self._dx}"
                           f"+{self.root.winfo_y() + ev.y - self._dy}")

    # --- Logic --------------------------------------------------------------
    def _iface_name(self):
        """Real name of the chosen interface (the combo shows 'name — IP')."""
        return self._display.get(self.iface.get(), self.iface.get())

    def _iface_chosen(self):
        """The user picked an interface in the combo: remember it for the next
        startup (only the explicit choice, not the automatic selection)."""
        name = self._iface_name()
        if name and name != self.config.get("last_interface"):
            self.config["last_interface"] = name
            self.store.save_config(self.config)
        self._on_iface()

    def refresh(self, select_default=False):
        ifaces = self.ops.list_interfaces()
        current = self._iface_name()
        self._map = {i["name"]: i["ip"] for i in ifaces}
        # The combo also shows the IP to tell interfaces apart at a glance
        self._display = {f"{n} — {ip or 'no IP'}": n for n, ip in self._map.items()}
        self.iface["values"] = list(self._display.keys())
        names = list(self._map.keys())
        if names and (select_default or current not in self._map):
            # Return to the last interface the user used; if it's gone, the
            # first active one.
            last = self.config.get("last_interface", "")
            current = last if last in self._map else names[0]
        for disp, n in self._display.items():
            if n == current:
                self.iface.set(disp)
                break
        self._on_iface()

    def _on_iface(self):
        name = self._iface_name()
        cfg = self.ops.get_config(name) if name else \
            {"dhcp": False, "ip": "", "mask": "", "gw": "", "dns": ""}
        ip = cfg["ip"] or self._map.get(name, "")
        self._dhcp = cfg["dhcp"]
        self._put(self.ip, ip)
        self._put(self.mask, cfg["mask"] or "255.255.255.0")
        self._put(self.gw, cfg["gw"])
        self._put(self.dns, cfg["dns"])
        # snapshot of what's applied: pending changes are detected against this
        self._applied = (self._val(self.ip), self._val(self.mask),
                         self._val(self.gw), self._val(self.dns))
        # Always-visible status: interface, resulting IP and current mode
        if name:
            mode = "Auto (DHCP)" if cfg["dhcp"] else "Static IP"
            self._msg(f"● {name}  ·  {ip or 'no IP'}  ·  {mode}",
                      OK if ip else ERR)
        else:
            self._msg("No active interfaces", ERR)
        self._render_profiles()
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """The color says which mode is selected and the active mode's button
        is disabled (green with ✔, no click possible): there's no way to
        trigger the 'already in that mode' error. Editing a field lights up
        'Apply IP'."""
        if not hasattr(self, "btn_apply"):
            return
        dhcp = getattr(self, "_dhcp", False)
        fields = (self._val(self.ip), self._val(self.mask),
                  self._val(self.gw), self._val(self.dns))
        pending = fields != getattr(self, "_applied", ("", "", "", ""))

        if dhcp:
            self.btn_dhcp.config(text="✔ Auto (DHCP)", bg=ACCENT,
                                 disabledforeground="white",
                                 state="disabled", cursor="arrow")
        else:
            self.btn_dhcp.config(text="Auto (DHCP)", bg=CARD, fg=TEXT,
                                 activebackground=CARD_HOVER,
                                 activeforeground=TEXT,
                                 state="normal", cursor="hand2")

        if not dhcp and not pending and fields[0]:
            self.btn_apply.config(text="✔ Static IP applied", bg=ACCENT_DARK,
                                  disabledforeground="white",
                                  state="disabled", cursor="arrow")
        elif pending:
            self.btn_apply.config(text="Apply IP", bg=ACCENT, fg="white",
                                  activebackground=ACCENT_DARK,
                                  activeforeground="white",
                                  state="normal", cursor="hand2")
        else:
            self.btn_apply.config(text="Apply IP", bg=CARD, fg=TEXT,
                                  activebackground=CARD_HOVER,
                                  activeforeground=TEXT,
                                  state="normal", cursor="hand2")

    def _msg(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    # --- Confirmation with auto-revert (issue #21) --------------------------
    def _build_revert_frame(self):
        """Hidden bar that appears after applying a static IP without a
        verified way out: if the user doesn't confirm before the countdown
        expires, it reverts."""
        self.revert_frame = tk.Frame(self.card, bg=BG)
        tk.Label(self.revert_frame, text="Still connected?", bg=BG, fg=WARN,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.btn_keep = tk.Button(self.revert_frame, text="✔ Keep change",
                                  bg=WARN, fg="white", bd=0,
                                  activebackground="#92400E",
                                  activeforeground="white",
                                  font=("Segoe UI", 8, "bold"), cursor="hand2",
                                  command=self._confirm_change)
        self.btn_keep.pack(side="right", ipadx=8, ipady=1)

    def _arm_confirmation(self, name, previous, gw):
        """Meta 2021 lesson: the tool that breaks the network can't be the only
        rescue. After applying a static IP the way out is verified (ping to the
        gateway); if connectivity can't be confirmed, a countdown in the style
        of the Windows resolution change — without human confirmation it goes
        back to the previous config on its own (revert is 100% local)."""
        if gw and self.ops.gateway_responds(gw):
            return  # verified way out: the change stays without asking
        self._revert_previous = (name, previous)
        self._revert_remaining = 30
        self.revert_frame.pack(fill="x", padx=12, pady=(0, 4),
                               before=self.status)
        self._revert_tick()

    def _revert_tick(self):
        if self._revert_previous is None:
            return
        if self._revert_remaining <= 0:
            return self._revert_now()
        self.btn_keep.config(
            text=f"✔ Keep change ({self._revert_remaining} s)")
        self._revert_remaining -= 1
        self._revert_after = self.root.after(1000, self._revert_tick)

    def _cancel_confirmation(self):
        if self._revert_after:
            self.root.after_cancel(self._revert_after)
            self._revert_after = None
        self._revert_previous = None
        self.revert_frame.pack_forget()

    def _confirm_change(self):
        self._cancel_confirmation()
        self._msg("✔ Change confirmed", OK)

    def _revert_now(self):
        name, previous = self._revert_previous
        self._cancel_confirmation()
        ok, _ = self.ops.revert_to(name, previous)
        self.refresh()
        # after refresh: _on_iface overwrites the status with the normal state
        if ok:
            self._msg("⏪ No confirmation in time: previous config restored",
                      WARN)
        else:
            self._msg("✗ Could not revert — check the network", ERR)

    def _repopulate_after_relaunch(self):
        """If we come from a relaunch as admin, restore the chosen interface
        and whatever the user had typed (issue #17)."""
        pend = _relaunch_args()
        if not (pend.ip or pend.mask or pend.gw):
            return
        if pend.iface:
            for disp, n in self._display.items():
                if n == pend.iface:
                    self.iface.set(disp)
                    self._on_iface()
                    break
        self._put(self.ip, pend.ip)
        self._put(self.mask, pend.mask)
        self._put(self.gw, pend.gw)
        self._update_mode_buttons()

    def _ensure_admin(self):
        if self.ops.is_admin():
            return True
        self._msg("Requesting administrator permissions…", MUTED)
        self.ops.relaunch_as_admin(__file__, {
            "--iface": self._iface_name(),
            "--ip": self._val(self.ip),
            "--mask": self._val(self.mask),
            "--gw": self._val(self.gw),
        })
        return False

    def _apply_strategy(self, strategy):
        """Common apply path: chosen interface, admin, run the strategy
        (StaticIP/DHCP) and reflect the result. Returns ok."""
        name = self._iface_name()
        if not name:
            self._msg("Pick an interface", ERR)
            return False
        if not self._ensure_admin():
            return False
        # Applying something new (including the DHCP button as a manual rescue)
        # cancels any pending countdown.
        self._cancel_confirmation()
        previous = self.ops.get_config(name)
        ok, msg = strategy.apply(self.ops, name)
        # Three honest states: green = clean success; amber = applied but with
        # warnings (e.g. gateway outside the subnet); red = not applied
        # (reject, netsh error, or half-done DNS). Never "green" hiding a
        # problem.
        if ok:
            self._msg("✔ " + msg, WARN if "⚠" in msg else OK)
            self.refresh()
            if isinstance(strategy, netops.StaticIP):
                self._arm_confirmation(name, previous, strategy.gw)
        else:
            self._msg("✗ " + msg, ERR)
        return ok

    def apply_ip(self):
        self._apply_strategy(netops.StaticIP(
            self._val(self.ip), self._val(self.mask) or "255.255.255.0",
            self._val(self.gw), self._val(self.dns)))

    def apply_dhcp(self):
        if self._apply_strategy(netops.DHCP()):
            # the DHCP server takes a couple of seconds to hand out the new IP
            self.root.after(2500, self.refresh)
            self.root.after(6000, self.refresh)

    def apply_profile(self, name):
        p = self.profiles.get(name, {})
        self._put(self.ip, p.get("ip", ""))
        self._put(self.mask, p.get("mask", "255.255.255.0"))
        self._put(self.gw, p.get("gw", ""))
        self._put(self.dns, p.get("dns", ""))
        self._apply_strategy(netops.strategy_from_profile(p))

    # --- Device scanner -----------------------------------------------------
    def open_scanner(self):
        name = self._iface_name()
        if not name:
            return self._msg("Pick an interface", ERR)

        win = tk.Toplevel(self.root)
        win.title("Devices on the network — NetQuick")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.geometry("460x400")

        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(head, text="Devices on the network", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        btn_re = tk.Button(head, text="⟳ Rescan", bg=ACCENT, fg="white", bd=0,
                           activebackground=ACCENT_DARK, activeforeground="white",
                           font=("Segoe UI", 8, "bold"), cursor="hand2")
        btn_re.pack(side="right", ipadx=8, ipady=2)

        status_lbl = tk.Label(win, text="", bg=BG, fg=MUTED,
                              font=("Segoe UI", 8), anchor="w")
        status_lbl.pack(fill="x", padx=14)

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=14, pady=8)

        def render(devices):
            if not win.winfo_exists():
                return
            for w in list_frame.winfo_children():
                w.destroy()
            if not devices:
                status_lbl.config(text="✗ No device responded", fg=ERR)
                return
            status_lbl.config(text=f"✔ {len(devices)} devices found", fg=OK)
            for d in devices:
                row = tk.Frame(list_frame, bg=CARD)
                row.pack(fill="x", pady=2)
                is_dante = bool(d.get("dante"))
                tk.Label(row, text="⚡" if is_dante else "●", bg=CARD,
                         fg=ACCENT if is_dante else OK,
                         font=("Segoe UI", 10)).pack(side="left", padx=(8, 4))
                text = d["ip"] + ("  (this PC)" if d["own"] else "")
                tk.Label(row, text=text, bg=CARD, fg=TEXT, font=("Consolas", 9),
                         width=22, anchor="w").pack(side="left")
                vendor = self.ops.mac_vendor(d["mac"])
                detail_parts = []
                if is_dante:
                    dante_name = d["dante"]
                    detail_parts.append("Dante" if dante_name == "Dante"
                                        else f"Dante · {dante_name}")
                if d["mac"]:
                    detail_parts.append(d["mac"])
                if vendor:
                    detail_parts.append(vendor)
                tk.Label(row, text="   ".join(detail_parts), bg=CARD,
                         fg=ACCENT if is_dante else MUTED,
                         font=("Segoe UI", 8, "bold" if is_dante else "normal"),
                         anchor="w").pack(side="left", fill="x", expand=True)
                if not d["own"]:
                    tk.Button(row, text="Web", bg=CARD, fg=ERR, bd=0,
                              activebackground=CARD_HOVER, activeforeground=ERR,
                              font=("Segoe UI", 8, "bold"), cursor="hand2",
                              command=lambda ip=d["ip"]:
                                  webbrowser.open(f"http://{ip}")
                              ).pack(side="right", padx=8, pady=2)

        def scan():
            ip = self.ops.get_ip(name)
            if not ip:
                status_lbl.config(text="✗ The interface has no IP", fg=ERR)
                return
            status_lbl.config(text=f"Scanning the network of {ip}…", fg=MUTED)
            btn_re.config(state="disabled")

            def work():
                devices = self.ops.scan_network(name)
                def finish():
                    if win.winfo_exists():
                        btn_re.config(state="normal")
                        render(devices)
                self.root.after(0, finish)

            threading.Thread(target=work, daemon=True).start()

        btn_re.config(command=scan)
        scan()

    # --- Settings window ----------------------------------------------------
    def open_config(self):
        win = tk.Toplevel(self.root)
        win.title("Settings — NetQuick")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.geometry("360x420")

        tk.Label(win, text="⚙ Settings", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 8))

        # Start with Windows
        self.startup_var = tk.BooleanVar(value=winsetup.in_startup())
        chk = tk.Checkbutton(win, text="Start with Windows (always visible)",
                             variable=self.startup_var, bg=BG, fg=TEXT,
                             selectcolor=CARD, activebackground=BG, activeforeground=TEXT,
                             font=("Segoe UI", 9), cursor="hand2",
                             command=lambda: self._toggle_startup(win))
        chk.pack(anchor="w", padx=16)

        tk.Frame(win, bg=CARD, height=1).pack(fill="x", padx=16, pady=12)

        # Profiles
        tk.Label(win, text="Saved profiles", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16)
        tk.Label(win, text="Save an IP/mask/gateway with a name and apply it in 1 click.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=320,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 6))

        self.prof_list = tk.Frame(win, bg=BG)
        self.prof_list.pack(fill="x", padx=16)
        self._render_config_profiles(win)

        # Save the current values as a new profile
        add = tk.Frame(win, bg=BG)
        add.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(add, text="Name:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        name_e = tk.Entry(add, bg=CARD, fg=TEXT, bd=0, insertbackground=TEXT,
                          font=("Segoe UI", 9), width=12)
        name_e.pack(side="left", padx=6, ipady=2)
        tk.Button(add, text="Save current values", bg=ACCENT, fg="white", bd=0,
                  activebackground=ACCENT_DARK, activeforeground="white",
                  font=("Segoe UI", 8, "bold"), cursor="hand2",
                  command=lambda: self._save_profile(name_e.get(), win)
                  ).pack(side="left", ipadx=4, ipady=2)

    def _render_config_profiles(self, win):
        for w in self.prof_list.winfo_children():
            w.destroy()
        if not self.profiles:
            tk.Label(self.prof_list, text="(no profiles yet)", bg=BG, fg=MUTED,
                     font=("Segoe UI", 9, "italic")).pack(anchor="w")
            return
        for name, p in self.profiles.items():
            row = tk.Frame(self.prof_list, bg=CARD)
            row.pack(fill="x", pady=2)
            det = f"{name}:  {p.get('ip', '?')} / {p.get('mask', '?')}"
            if p.get("gw"):
                det += f"  gw {p['gw']}"
            if p.get("dns"):
                det += f"  dns {p['dns']}"
            tk.Label(row, text=det, bg=CARD, fg=TEXT, font=("Segoe UI", 8),
                     anchor="w").pack(side="left", fill="x", expand=True, padx=8, pady=4)
            tk.Button(row, text="🗑", bg=CARD, fg=ERR, bd=0, activebackground=CARD,
                      cursor="hand2", font=("Segoe UI", 9),
                      command=lambda n=name: self._delete_profile(n, win)
                      ).pack(side="right", padx=6)

    def _save_profile(self, name, win):
        name = name.strip()
        if not name:
            return
        self.profiles[name] = {
            "ip": self._val(self.ip),
            "mask": self._val(self.mask) or "255.255.255.0",
            "gw": self._val(self.gw),
            "dns": self._val(self.dns),
        }
        self.store.save_profiles(self.profiles)
        self._render_config_profiles(win)
        self._render_profiles()

    def _delete_profile(self, name, win):
        self.profiles.pop(name, None)
        self.store.save_profiles(self.profiles)
        self._render_config_profiles(win)
        self._render_profiles()

    def _toggle_startup(self, win):
        ok = winsetup.set_startup(self.startup_var.get())
        if not ok:
            self.startup_var.set(winsetup.in_startup())


def _relaunch_args():
    """Values that were typed when the app relaunched as admin (issue #17):
    they arrive as arguments and are repopulated at startup."""
    p = argparse.ArgumentParser(add_help=False)
    for flag in ("--iface", "--ip", "--mask", "--gw"):
        p.add_argument(flag, default="")
    ns, _ = p.parse_known_args()
    return ns


if __name__ == "__main__":
    if not winsetup.already_running():
        winsetup.dpi_awareness()
        winsetup.first_run_exe()
        MiniWidget().run()
