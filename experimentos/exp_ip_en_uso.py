# -*- coding: utf-8 -*-
r"""
EXPERIMENTO ② — ¿`ip_en_uso` cumple su promesa en TU LAN real?

Discrimina entre dos hipótesis sobre el hallazgo FM-2 de la revisión:
  H0: "el falso negativo es teórico, en la práctica casi nunca pasa"
  H1: "un equipo silencioso a ping y ausente del ARP se ve como 'libre'
       con frecuencia -> NetQuick aplicaría una IP duplicada"

El resultado te dice si la función central del producto cumple su promesa
("nunca aplico una IP ya en uso") o no.

CÓMO USARLO (requiere una LAN real con un equipo de IP conocida):
  1. Elige un equipo de tu red con IP FIJA conocida, p.ej. una consola
     Dante, un switch gestionado o un PC. Anota su IP  ->  IP_OBJETIVO.
  2. (Caso realista) Haz que NO responda a ping: en muchos equipos el
     firewall ya bloquea ICMP; en un PC Windows, activa "Firewall de
     Windows" con ICMP entrante bloqueado. El equipo sigue ENCENDIDO y
     usando la IP, solo que calla al ping.
  3. Vacía la entrada ARP para forzar el peor caso (ventana fría):
        arp -d *        (como admin)   o    arp -d IP_OBJETIVO
  4. Ejecuta:  python experimentos\exp_ip_en_uso.py IP_OBJETIVO N
     (N = repeticiones, por defecto 50). Corre desde una IP de la MISMA
     subred que IP_OBJETIVO.

INTERPRETACIÓN:
  - "en uso" en el 100% de las N  -> H0: la detección aguanta, promesa OK.
  - aunque sea 1 sola vez "LIBRE" -> H1: falso negativo REAL y reproducible.
    Con la caché ARP fría (paso 3) el % de "LIBRE" estima la probabilidad
    de que NetQuick pise una IP ocupada por un equipo silencioso.

NOTA DE HONESTIDAD: este script NO puede correrse de forma significativa en
un sandbox sin tu LAN ni tus equipos. Debe ejecutarse en la máquina y red
donde usas NetQuick. La parte de abajo (--smoke) sí corre en cualquier
Windows y solo demuestra que la mecánica ping+ARP responde con datos reales.
"""
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 2)[0])  # raíz del repo
import netops


def experimento(ip_objetivo, n):
    print(f"Objetivo: {ip_objetivo}   repeticiones: {n}")
    print("Vacía la caché ARP antes (arp -d *) para el peor caso.\n")
    libres = 0
    for i in range(1, n + 1):
        # Cada vuelta parte de ARP frío para el objetivo: worst case honesto
        subprocess.run(["arp", "-d", ip_objetivo], capture_output=True)
        en_uso = netops.ip_en_uso(ip_objetivo)
        if not en_uso:
            libres += 1
        marca = "EN USO" if en_uso else ">>> LIBRE (falso negativo) <<<"
        print(f"  [{i:>3}/{n}] ip_en_uso = {en_uso}   {marca}")
        time.sleep(0.2)
    print(f"\nRESULTADO: {libres}/{n} veces reportado LIBRE.")
    if libres == 0:
        print("VEREDICTO: H0 — la detección aguantó en todas. Promesa OK "
              "para este equipo/condición.")
    else:
        pct = 100 * libres / n
        print(f"VEREDICTO: H1 — FALSO NEGATIVO reproducible ({pct:.0f}%). "
              "NetQuick aplicaría una IP ocupada. FM-2 confirmado en tu LAN.")


def smoke():
    """Corre en cualquier Windows: demuestra la mecánica con datos reales,
    NO discrimina H0/H1 (no hay equipo silencioso controlado)."""
    ifaces = netops.list_interfaces()
    print("Interfaces activas:", ifaces)
    if not ifaces:
        print("Sin interfaces activas; nada que medir.")
        return
    propia = next((i["ip"] for i in ifaces if i["ip"]), "")
    print(f"IP propia: {propia}  (ip_en_uso debe dar False para la propia)")
    if propia:
        print("  ip_en_uso(propia) =", netops.ip_en_uso(propia))
    print("Tabla ARP vista por _parsear_arp:")
    res = netops.run(["arp", "-a"])
    tabla = netops._parsear_arp(res.stdout if res else "")
    for ip, mac in list(tabla.items())[:10]:
        print(f"    {ip:<16} {mac}  {netops.fabricante_mac(mac)}")
    print(f"  ({len(tabla)} entradas válidas en la caché ARP)")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--smoke":
        smoke()
    elif len(sys.argv) >= 2:
        ip = sys.argv[1]
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 50
        experimento(ip, n)
    else:
        print(__doc__)
        print("Uso: python exp_ip_en_uso.py IP_OBJETIVO [N]")
        print("     python exp_ip_en_uso.py --smoke")
