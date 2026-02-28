import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import psutil
import ctypes
import sys
import threading
import time

# --- CONSTANTES DE COLOR E IMAGEN ---
COLOR_ACCENT = "#0072d5"
COLOR_SUCCESS = "#10B981"
COLOR_BG_MAIN = "#F8FAFC"
COLOR_BG_CONTENT = "#FFFFFF"
COLOR_TEXT_PRIMARY = "#1E293B"
COLOR_TEXT_SECONDARY = "#64748B"
COLOR_BORDER = "#E2E8F0"

class NetworkConfigApp:
    def __init__(self):
        self.ventana = tk.Tk()
        self.ventana.title("Configurador de Red")
        self.ventana.geometry("850x650") 
        self.ventana.configure(bg=COLOR_BG_MAIN)
        self.ventana.resizable(False, False)
        
        # Icono
        icon_data = """
        R0lGODlhIAAgAOQAAP///wAAANbW1t7e3uDg4OTk5Ovr6/Pz8////////wAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAEA
        AAgALAAAAAAgACAAAAW0QMIIjmMpEWQqo6Q8gCAhD0QACgIQAIIQhCAIBEAAgCAEIQgEQACAIAQh
        CARAAIAgBCEIBEAAgCAEIQgEQACAIAQhCARAAIAgBCEIBEAAgCAEIQgEQACAIAQhCARAAIAgBCEI
        BEAAgCAEIQgEQACAIAQhCARAAIAgBCEIBEAAgCAEIQgEQACAIAQhCARAAIAgBCEIBEAAgCAEIQgE
        QACAIAQhCARAAOtJADs=
        """
        try:
            icond = tk.PhotoImage(data=icon_data)
            self.ventana.iconphoto(True, icond)
        except: pass
        
        self.interface_seleccionada = None
        self.adaptadores_widgets = {} 
        
        self.estilos_base()
        self.mostrar_intro()

    def estilos_base(self):
        style = ttk.Style()
        try: style.theme_use('clam')
        except: pass
        style.configure('TFrame', background=COLOR_BG_CONTENT)

    def mostrar_intro(self):
        self.intro_frame = tk.Frame(self.ventana, bg=COLOR_ACCENT)
        self.intro_frame.place(x=0, y=0, relwidth=1, relheight=1)
        center = tk.Frame(self.intro_frame, bg=COLOR_ACCENT)
        center.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(center, text="⚡", font=("Segoe UI", 48), bg=COLOR_ACCENT, fg="white").pack(pady=(0, 20))
        tk.Label(center, text="Configurador de Red", font=("Segoe UI", 24, "bold"), bg=COLOR_ACCENT, fg="white").pack()
        tk.Label(center, text='"Cambia rápido, sin estresarte jajaja"', font=("Segoe UI", 12, "italic"), bg=COLOR_ACCENT, fg="#E0E0E0").pack(pady=(5, 30))
        tk.Label(center, text="Desarrollado por:", font=("Segoe UI", 10), bg=COLOR_ACCENT, fg="#BBDEFB").pack()
        tk.Label(center, text="Israel Moncayo  &  Oscar Osorio", font=("Segoe UI", 12, "bold"), bg=COLOR_ACCENT, fg="white").pack(pady=(5, 0))
        self.loading_bar = ttk.Progressbar(center, orient="horizontal", length=200, mode="determinate")
        self.loading_bar.pack(pady=(40, 0))
        self.progreso_intro(0)

    def progreso_intro(self, valor):
        if valor <= 100:
            self.loading_bar['value'] = valor
            self.ventana.after(30, lambda: self.progreso_intro(valor + 2))
        else:
            self.ventana.after(500, self.cerrar_intro)

    def cerrar_intro(self):
        self.intro_frame.destroy()
        self.iniciar_app_principal()

    def iniciar_app_principal(self):
        self.construir_layout()
        if not ctypes.windll.shell32.IsUserAnAdmin():
             self.ventana.after(100, self.pedir_admin_inicio)
        else:
             self.actualizar_lista()

    def pedir_admin_inicio(self):
        res = messagebox.askyesno("Permisos Requeridos", 
                                  "Para configurar la red sin interrupciones, se requieren permisos de Administrador.\n\n¿Reiniciar como Administrador ahora?")
        if res:
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{__file__}"', None, 1)
                self.ventana.destroy()
            except: pass
        self.actualizar_lista()

    def ejecutar_netsh(self, comando):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        try:
            return subprocess.run(
                comando, capture_output=True, text=True,
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
            )
        except: return None

    def obtener_interfaces(self):
        try:
            interfaces = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            data = []
            for nombre, direcc in interfaces.items():
                if stats[nombre].isup and not nombre.lower().startswith("lo"):
                    ip = next((d.address for d in direcc if d.family.name == "AF_INET"), "Sin IP")
                    icon = "📶" if "wi-fi" in nombre.lower() or "wireless" in nombre.lower() else "🔌"
                    data.append({'nombre': nombre, 'ip': ip, 'icon': icon})
            return data
        except: return []

    def obtener_info_detalle(self, nombre):
        cmd = ['netsh', 'interface', 'ip', 'show', 'config', f'name={nombre}']
        res = self.ejecutar_netsh(cmd)
        info = {'dhcp': False, 'ip': '', 'mask': '', 'gw': ''}
        if res and res.returncode == 0:
            out = res.stdout
            info['dhcp'] = 'DHCP enabled:                         Yes' in out
            ip = re.search(r'IP Address:\s+(\d+\.\d+\.\d+\.\d+)', out)
            if ip: info['ip'] = ip.group(1)
            msk = re.search(r'Subnet Prefix:\s+\d+\.\d+\.\d+\.\d+/(\d+)', out)
            if msk: info['mask'] = self.cidr_to_netmask(int(msk.group(1)))
            gw = re.search(r'Default Gateway:\s+(\d+\.\d+\.\d+\.\d+)', out)
            if gw: info['gw'] = gw.group(1)
        return info

    @staticmethod
    def cidr_to_netmask(cidr):
        mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"

    def construir_layout(self):
        header = tk.Frame(self.ventana, bg="white", height=70, padx=25)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        tk.Label(header, text="⚡ Configurador de Red", bg="white", fg=COLOR_TEXT_PRIMARY, 
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, pady=20)
        self.btn_refresh = self.crear_boton_redondo(header, "↻ Actualizar", bg="white", fg=COLOR_ACCENT, width=100, height=35, command=self.actualizar_lista)
        self.btn_refresh.pack(side=tk.RIGHT, pady=18)
        body = tk.Frame(self.ventana, bg=COLOR_BG_MAIN, padx=25, pady=25)
        body.pack(fill=tk.BOTH, expand=True)
        card = tk.Frame(body, bg="white")
        card.pack(fill=tk.BOTH, expand=True)
        self.sidebar = tk.Frame(card, bg="white", width=280)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, pady=20)
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="DISPOSITIVOS", bg="white", fg="#A0A0A0", 
                 font=("Segoe UI", 9, "bold"), anchor="w", padx=25).pack(fill=tk.X, pady=(0, 15))
        self.list_container = tk.Frame(self.sidebar, bg="white")
        self.list_container.pack(fill=tk.BOTH, expand=True)
        tk.Frame(card, bg=COLOR_BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)
        self.content = tk.Frame(card, bg="white", padx=40, pady=20) 
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.header_content = tk.Frame(self.content, bg="white")
        self.header_content.pack(fill=tk.X, pady=(0, 20))
        self.lbl_icon = tk.Label(self.header_content, text="🔌", bg="#EFF6FF", fg=COLOR_ACCENT, 
                                 font=("Segoe UI", 18), width=2, height=1)
        self.lbl_icon.pack(side=tk.LEFT)
        self.lbl_name = tk.Label(self.header_content, text="Seleccione red", bg="white", 
                                 fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 16, "bold"), padx=15)
        self.lbl_name.pack(side=tk.LEFT)
        self.lbl_status = tk.Label(self.header_content, text="● Conectado", bg="white", 
                                   fg=COLOR_SUCCESS, font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side=tk.RIGHT)
        tk.Frame(self.content, bg=COLOR_BORDER, height=1).pack(fill=tk.X, pady=(0, 20))
        toggle_frame = tk.Frame(self.content, bg="#F8FAFC", padx=20, pady=15)
        toggle_frame.pack(fill=tk.X, pady=(0, 20))
        self.lbl_mode_title = tk.Label(toggle_frame, text="Modo Automático (DHCP)", bg="#F8FAFC", 
                 fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        self.lbl_mode_title.pack(anchor="w")
        self.lbl_mode_desc = tk.Label(toggle_frame, text="Obtener IP del servidor automáticamente", bg="#F8FAFC", 
                 fg="#888888", font=("Segoe UI", 9))
        self.lbl_mode_desc.pack(anchor="w")
        self.switch_val = tk.BooleanVar(value=True)
        self.canvas_switch = tk.Canvas(toggle_frame, width=50, height=28, bg="#F8FAFC", bd=0, highlightthickness=0, cursor="hand2")
        self.canvas_switch.place(relx=1.0, rely=0.5, anchor="e", x=-5)
        self.canvas_switch.bind("<Button-1>", self.on_toggle_click)
        self.lbl_manual_title = tk.Label(self.content, text="Asignar IP Manual", bg="white", 
                                         fg="#CBD5E1", font=("Segoe UI", 11, "bold"))
        self.lbl_manual_title.pack(anchor="w", pady=(0, 5))
        self.form_frame = tk.Frame(self.content, bg="white")
        self.form_frame.pack(fill=tk.X)
        self.vars = {'ip': tk.StringVar(), 'mask': tk.StringVar(), 'gw': tk.StringVar()}
        def make_row(parent, label, key):
            row = tk.Frame(parent, bg="white", pady=8) 
            row.pack(fill=tk.X)
            tk.Label(row, text=label, bg="white", fg=COLOR_TEXT_SECONDARY, font=("Segoe UI", 10), width=18, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(row, textvariable=self.vars[key], font=("Consolas", 11), bg="white", fg="#333", relief="flat")
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(10, 0))
            border = tk.Frame(row, bg="#E2E8F0", height=1)
            border.place(relx=0, rely=1.0, relwidth=1.0, y=-1)
            return entry
        self.inputs = [make_row(self.form_frame, "Dirección IP", 'ip'),
                       make_row(self.form_frame, "Máscara Subred", 'mask'),
                       make_row(self.form_frame, "Puerta de Enlace", 'gw')]
        self.btn_container = tk.Frame(self.content, bg="white", pady=20)
        self.btn_container.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_action_canvas = tk.Canvas(self.btn_container, bg="white", height=60, bd=0, highlightthickness=0, cursor="hand2")
        self.btn_action_canvas.pack(fill=tk.X)
        self.btn_action_canvas.bind("<Configure>", self.redibujar_boton_accion)
        self.ventana.after(200, self.redibujar_boton_accion)
        self.btn_state = {'active': False, 'text': "Iniciando...", 'color': "#E2E8F0", 'text_color': "#94A3B8"}

    def crear_boton_redondo(self, parent, text, bg, fg, width, height, command):
        c = tk.Canvas(parent, width=width, height=height, bg=parent['bg'], bd=0, highlightthickness=0, cursor="hand2")
        def draw(color):
            c.delete("all")
            r = height // 2
            c.create_oval(0, 0, height, height, fill=color, outline=color)
            c.create_oval(width-height, 0, width, height, fill=color, outline=color)
            c.create_rectangle(r, 0, width-r, height, fill=color, outline=color)
            c.create_text(width//2, height//2, text=text, fill=fg, font=("Segoe UI", 10, "bold"))
        draw(bg) 
        c.bind("<Button-1>", lambda e: command())
        return c

    def actualizar_lista(self):
        for w in self.list_container.winfo_children(): w.destroy()
        self.interfaces = self.obtener_interfaces()
        for i in self.interfaces: self.crear_item_sidebar(i)
        if self.interfaces and not self.interface_seleccionada:
            self.seleccionar_interface(self.interfaces[0]['nombre'])

    def crear_item_sidebar(self, iface):
        nombre = iface['nombre']
        frame = tk.Frame(self.list_container, bg="white", cursor="hand2", pady=12, padx=20)
        frame.pack(fill=tk.X, pady=4)
        lbl_ico = tk.Label(frame, text=iface['icon'], bg="white", fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 14))
        lbl_ico.pack(side=tk.LEFT, padx=(0, 15))
        txt_f = tk.Frame(frame, bg="white")
        txt_f.pack(side=tk.LEFT, fill=tk.Y)
        lbl_t = tk.Label(txt_f, text=nombre, bg="white", fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 10, "bold"), anchor="w")
        lbl_t.pack(fill=tk.X)
        lbl_s = tk.Label(txt_f, text=iface['ip'], bg="white", fg="#94A3B8", font=("Segoe UI", 8), anchor="w")
        lbl_s.pack(fill=tk.X)
        wid = [frame, lbl_ico, txt_f, lbl_t, lbl_s]
        self.adaptadores_widgets[nombre] = wid
        for w in wid: w.bind("<Button-1>", lambda e, n=nombre: self.seleccionar_interface(n))

    def seleccionar_interface(self, nombre):
        if self.interface_seleccionada:
            p = self.adaptadores_widgets.get(self.interface_seleccionada)
            if p:
                p[0].config(bg="white")
                p[1].config(bg="white", fg=COLOR_TEXT_PRIMARY)
                p[2].config(bg="white")
                p[3].config(bg="white", fg=COLOR_TEXT_PRIMARY)
                p[4].config(bg="white", fg="#94A3B8")
        self.interface_seleccionada = nombre
        c = self.adaptadores_widgets[nombre]
        c[0].config(bg="#EFF6FF")
        c[1].config(bg="#EFF6FF", fg=COLOR_ACCENT)
        c[2].config(bg="#EFF6FF")
        c[3].config(bg="#EFF6FF", fg=COLOR_ACCENT)
        c[4].config(bg="#EFF6FF", fg=COLOR_ACCENT)
        self.lbl_name.config(text=nombre)
        info = self.obtener_info_detalle(nombre)
        self.vars['ip'].set(info['ip'])
        self.vars['mask'].set(info['mask'])
        self.vars['gw'].set(info['gw'])
        self.current_is_dhcp = info['dhcp']
        self.set_toggle(info['dhcp'])

    def set_toggle(self, state):
        self.switch_val.set(state)
        self.dibujar_toggle()
        self.actualizar_estado_inputs()

    def on_toggle_click(self, event):
        self.switch_val.set(not self.switch_val.get())
        self.dibujar_toggle()
        self.actualizar_estado_inputs()

    def dibujar_toggle(self):
        self.canvas_switch.delete("all")
        val = self.switch_val.get()
        bg = COLOR_ACCENT if val else "#CBD5E1"
        self.canvas_switch.create_oval(2, 2, 26, 26, fill=bg, outline=bg)
        self.canvas_switch.create_oval(24, 2, 48, 26, fill=bg, outline=bg)
        self.canvas_switch.create_rectangle(14, 2, 36, 26, fill=bg, outline=bg)
        x = 36 if val else 14
        self.canvas_switch.create_oval(x-10, 4, x+10, 24, fill="white", outline="")

    def actualizar_estado_inputs(self):
        wants_dhcp = self.switch_val.get()
        state = "disabled" if wants_dhcp else "normal"
        if wants_dhcp:
            self.lbl_manual_title.config(fg="#CBD5E1")
            if getattr(self, 'current_is_dhcp', False):
                self.btn_state['active'] = False
                self.btn_state['text'] = "Modo Automático Activado"
                self.btn_state['color'] = "#F1F5F9"
                self.btn_state['text_color'] = "#94A3B8"
            else:
                self.btn_state['active'] = True
                self.btn_state['text'] = "Aplicar Modo Automático"
                self.btn_state['color'] = COLOR_ACCENT
                self.btn_state['text_color'] = "white"
        else:
            self.lbl_manual_title.config(fg=COLOR_TEXT_PRIMARY)
            self.btn_state['active'] = True
            self.btn_state['text'] = "Guardar Configuración Manual"
            self.btn_state['color'] = COLOR_ACCENT
            self.btn_state['text_color'] = "white"
        for entry in self.inputs: entry.config(state=state)
        self.redibujar_boton_accion()

    def redibujar_boton_accion(self, event=None):
        try:
            if not self.btn_action_canvas.winfo_exists(): return
        except: return
        self.btn_action_canvas.delete("all")
        w = self.btn_action_canvas.winfo_width()
        if w < 50: w = 400 
        h = 56 
        color = self.btn_state.get('color', COLOR_ACCENT)
        txt = self.btn_state.get('text', "")
        txt_c = self.btn_state.get('text_color', "white")
        try:
            self.btn_action_canvas.create_oval(2, 2, h, h, fill=color, outline=color)
            self.btn_action_canvas.create_oval(w-h, 2, w-2, h, fill=color, outline=color)
            self.btn_action_canvas.create_rectangle(h/2, 2, w-(h/2), h, fill=color, outline=color)
            self.btn_action_canvas.create_text(w//2, h//2+2, text=txt, fill=txt_c, font=("Segoe UI", 11, "bold"))
        except: pass
        self.btn_action_canvas.unbind("<Button-1>")
        if self.btn_state.get('active'):
            self.btn_action_canvas.config(cursor="hand2")
            if self.switch_val.get(): 
                 self.btn_action_canvas.bind("<Button-1>", lambda e: self.ejecutar_dhcp_imediato())
            else: 
                 self.btn_action_canvas.bind("<Button-1>", lambda e: self.aplicar_manual())
        else:
            self.btn_action_canvas.config(cursor="arrow")

    def ejecutar_dhcp_imediato(self):
        if not self.check_admin(): return
        self.ventana.config(cursor="wait")
        cmd_ip = ['netsh', 'interface', 'ip', 'set', 'address', f'name={self.interface_seleccionada}', 'dhcp']
        res_ip = self.ejecutar_netsh(cmd_ip)
        cmd_dns = ['netsh', 'interface', 'ip', 'set', 'dns', f'name={self.interface_seleccionada}', 'dhcp']
        self.ejecutar_netsh(cmd_dns) 
        self.ventana.config(cursor="")
        if res_ip and res_ip.returncode == 0:
            self.current_is_dhcp = True
            self.actualizar_lista()
            self.actualizar_estado_inputs()
            messagebox.showinfo("Hecho", "Configuración DHCP aplicada")
        else:
            err_msg = res_ip.stdout.strip() if res_ip and res_ip.stdout else "Error interno"
            messagebox.showerror("Error DHCP", f"No se pudo asignar DHCP:\n{err_msg}")

    def aplicar_manual(self):
        if self.switch_val.get(): return 
        if not self.check_admin(): return
        ip, mask, gw = self.vars['ip'].get(), self.vars['mask'].get(), self.vars['gw'].get()
        if not ip or not mask: return messagebox.showerror("Error", "Faltan datos")
        self.ventana.config(cursor="wait")
        cmd = ['netsh', 'interface', 'ip', 'set', 'address', f'name={self.interface_seleccionada}', 'static', ip, mask]
        if gw: cmd.append(gw)
        res = self.ejecutar_netsh(cmd)
        self.ventana.config(cursor="")
        if res and res.returncode == 0:
             self.current_is_dhcp = False
             self.actualizar_lista()
             self.actualizar_estado_inputs()
             messagebox.showinfo("Hecho", "Configuración manual guardada")
        else:
             err_msg = res.stdout.strip() if res and res.stdout else "Verifica la IP/Máscara"
             messagebox.showerror("Error", f"Fallo al guardar IP:\n{err_msg}")

    def check_admin(self):
        if ctypes.windll.shell32.IsUserAnAdmin(): return True
        else:
            messagebox.showwarning("Admin Requerido", "Reiniciando app...")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{__file__}"', None, 1)
            sys.exit(0)

    def ejecutar(self):
        self.ventana.mainloop()

def main():
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--admin':
            pass
    except: pass
    app = NetworkConfigApp()
    app.ejecutar()

if __name__ == "__main__":
    main()
