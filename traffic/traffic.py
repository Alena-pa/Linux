from scapy.all import sniff, IP, TCP, UDP
import time
import threading
import subprocess
from collections import defaultdict
import tkinter as tk
from tkinter import scrolledtext

#CONFIG
MAX_PACKETS_PER_IP = 5
SYN_LIMIT = 20
MAX_PACKET_SIZE = 1500
INTERFACE = None  # None = default interface

#GLOBAL DATA

packet_count = defaultdict(int)
syn_count = defaultdict(int)
blocked_ips = set()
logs = []

sniffer_running = False

#LOGGING

def log_event(text):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {text}"
    logs.append(line)

    if gui_log_box:
        gui_log_box.insert(tk.END, line + "\n")
        gui_log_box.see(tk.END)

#FIREWALL

def block_ip(ip):
    if ip in blocked_ips:
        return

    try:
        subprocess.run(
            ["sudo", "iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        blocked_ips.add(ip)
        log_event(f"BLOCKED IP: {ip}")

        if gui_blocked_box:
            gui_blocked_box.insert(tk.END, ip + "\n")

    except Exception as e:
        log_event(f"Block error: {e}")

#DETECTION

# Новая версия detect_threat с дополнительными проверками
WINDOW_SECONDS = 5  # окно времени для портов и повторов
ports_seen = defaultdict(dict)  # src_ip -> {port: timestamp}
times_seen = defaultdict(list)  # src_ip -> [timestamps]

def detect_threat(packet):
    if not packet.haslayer(IP):
        return

    ip = packet[IP].src
    packet_size = len(packet)
    now = time.time()

    # --- Существующие проверки ---
    packet_count[ip] += 1

    if packet_size > MAX_PACKET_SIZE:
        log_event(f"Large packet from {ip}")
        return "BLOCK"

    if packet_count[ip] > MAX_PACKETS_PER_IP:
        log_event(f"Too many packets from {ip}")
        return "BLOCK"

    if packet.haslayer(TCP):
        if packet[TCP].flags == "S":
            syn_count[ip] += 1
            if syn_count[ip] > SYN_LIMIT:
                log_event(f"SYN flood suspected from {ip}")
                return "BLOCK"

    # --- Новые проверки ---

    # 1. Port scan
    if packet.haslayer(TCP) or packet.haslayer(UDP):
        dport = packet[TCP].dport if packet.haslayer(TCP) else packet[UDP].dport
        ports_seen[ip][dport] = now
        # оставляем только порты за последние WINDOW_SECONDS
        ports_seen[ip] = {p: t for p, t in ports_seen[ip].items() if now - t <= WINDOW_SECONDS}
        PORT_THRESHOLD = 10  # порог портов для подозрения
        if len(ports_seen[ip]) >= PORT_THRESHOLD:
            log_event(f"Port scan suspected from {ip}")
            return "BLOCK"

    # 2. Повторные запросы
    times_seen[ip].append(now)
    times_seen[ip] = [t for t in times_seen[ip] if now - t <= WINDOW_SECONDS]
    REPEAT_THRESHOLD = 5
    if len(times_seen[ip]) >= REPEAT_THRESHOLD:
        log_event(f"Repeated requests suspected from {ip}")
        return "BLOCK"

    return "OK"

#PACKET HANDLER

def packet_handler(packet):
    if not packet.haslayer(IP):
        return

    ip = packet[IP].src

    if ip in blocked_ips:
        return

    result = detect_threat(packet)

    if result == "BLOCK":
        block_ip(ip)

#SNIFFER

def sniff_loop():
    global sniffer_running

    while sniffer_running:
        sniff(
            iface=INTERFACE,
            prn=packet_handler,
            store=False,
            timeout=1
        )

def start_sniffer():
    global sniffer_running
    if sniffer_running:
        return

    sniffer_running = True
    threading.Thread(target=sniff_loop, daemon=True).start()
    log_event("Sniffer started")

def stop_sniffer():
    global sniffer_running
    sniffer_running = False
    log_event("Sniffer stopped")

#SETTINGS

def apply_settings():
    global MAX_PACKETS_PER_IP, SYN_LIMIT, MAX_PACKET_SIZE

    try:
        new_packets = int(entry_max_packets.get())
        new_syn = int(entry_syn_limit.get())
        new_size = int(entry_max_size.get())

        if new_packets <= 0 or new_syn <= 0 or new_size <= 0:
            raise ValueError("Values must be positive")

        MAX_PACKETS_PER_IP = new_packets
        SYN_LIMIT = new_syn
        MAX_PACKET_SIZE = new_size

        log_event(f"Settings updated — MAX_PACKETS_PER_IP={MAX_PACKETS_PER_IP}, SYN_LIMIT={SYN_LIMIT}, MAX_PACKET_SIZE={MAX_PACKET_SIZE}")
        settings_status.config(text="✓ Applied", fg="green")

    except ValueError as e:
        settings_status.config(text=f"✗ Invalid input: {e}", fg="red")

def block_ip(ip):
    if ip in blocked_ips:
        return

    try:
        subprocess.run(
            ["sudo", "iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        blocked_ips.add(ip)
        log_event(f"BLOCKED IP: {ip}")

        # Добавляем в GUI список заблокированных IP
        if blocked_listbox:
            blocked_listbox.insert(tk.END, ip)

    except Exception as e:
        log_event(f"Block error: {e}")

def unblock_selected_gui():
    selected_indices = blocked_listbox.curselection()
    for i in reversed(selected_indices):
        ip = blocked_listbox.get(i)
        try:
            subprocess.run(
                ["sudo", "iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            blocked_listbox.delete(i)
            blocked_ips.discard(ip)
            log_event(f"UNBLOCKED IP: {ip}")
        except Exception as e:
            log_event(f"Failed to unblock {ip}: {e}")

#GUI

gui_log_box = None
gui_blocked_box = None
entry_max_packets = None
entry_syn_limit = None
entry_max_size = None
settings_status = None

def start_gui():
    global gui_log_box, blocked_listbox
    global entry_max_packets, entry_syn_limit, entry_max_size, settings_status

    root = tk.Tk()
    root.title("Simple Network Monitor")

    # Кнопки Start/Stop
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Start", command=start_sniffer).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="Stop", command=stop_sniffer).pack(side=tk.LEFT, padx=5)

    # Настройки
    settings_frame = tk.LabelFrame(root, text="Settings", padx=10, pady=5)
    settings_frame.pack(fill="x", padx=10, pady=5)

    row1 = tk.Frame(settings_frame)
    row1.pack(fill="x", pady=2)
    tk.Label(row1, text="Max Packets Per IP:", width=20, anchor="w").pack(side=tk.LEFT)
    entry_max_packets = tk.Entry(row1, width=10)
    entry_max_packets.insert(0, str(MAX_PACKETS_PER_IP))
    entry_max_packets.pack(side=tk.LEFT)

    row2 = tk.Frame(settings_frame)
    row2.pack(fill="x", pady=2)
    tk.Label(row2, text="SYN Limit:", width=20, anchor="w").pack(side=tk.LEFT)
    entry_syn_limit = tk.Entry(row2, width=10)
    entry_syn_limit.insert(0, str(SYN_LIMIT))
    entry_syn_limit.pack(side=tk.LEFT)

    row3 = tk.Frame(settings_frame)
    row3.pack(fill="x", pady=2)
    tk.Label(row3, text="Max Packet Size:", width=20, anchor="w").pack(side=tk.LEFT)
    entry_max_size = tk.Entry(row3, width=10)
    entry_max_size.insert(0, str(MAX_PACKET_SIZE))
    entry_max_size.pack(side=tk.LEFT)

    row4 = tk.Frame(settings_frame)
    row4.pack(fill="x", pady=4)
    tk.Button(row4, text="Apply", command=apply_settings).pack(side=tk.LEFT)
    settings_status = tk.Label(row4, text="", width=30, anchor="w")
    settings_status.pack(side=tk.LEFT, padx=8)

    # Логи
    tk.Label(root, text="Logs").pack()
    gui_log_box = scrolledtext.ScrolledText(root, width=70, height=15)
    gui_log_box.pack()

    # Заблокированные IP
    tk.Label(root, text="Blocked IPs").pack()
    blocked_listbox = tk.Listbox(root, width=70, height=5, selectmode=tk.EXTENDED)
    blocked_listbox.pack(pady=5)

    tk.Button(root, text="Unblock selected", command=unblock_selected_gui).pack(pady=2)

    root.mainloop()

#MAIN

if __name__ == "__main__":
    start_gui()