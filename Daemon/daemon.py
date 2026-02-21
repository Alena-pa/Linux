import os
import sys
import time
import json
import shutil
import logging
from datetime import datetime
import signal
import tkinter as tk
from tkinter import scrolledtext
import subprocess

CONFIG_PATH = "config.json"


#CONFIG

def load_config():
    if not os.path.exists(CONFIG_PATH):
        default_config = {
            "source_dir": "./data",
            "backup_dir": "./backups",
            "log_file": "./backup.log",
            "pid_file": "./backup.pid",
            "interval_minutes": 1
        }
        save_config(default_config)
        return default_config

    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


def setup_logging(log_file):
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


#DAEMON

def daemonize():
    if os.fork() > 0:
        sys.exit()

    os.setsid()

    if os.fork() > 0:
        sys.exit()

    sys.stdout.flush()
    sys.stderr.flush()

    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def create_backup(source_dir, backup_dir):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = os.path.join(backup_dir, timestamp)

    try:
        shutil.copytree(source_dir, dest)
        logging.info(f"Backup created: {dest}")
    except Exception as e:
        logging.error(f"Backup failed: {e}")


def write_pid(pid_file):
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def remove_pid(pid_file):
    if os.path.exists(pid_file):
        os.remove(pid_file)


def stop_daemon(pid_file):
    if not os.path.exists(pid_file):
        return False

    with open(pid_file, "r") as f:
        pid = int(f.read())

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    remove_pid(pid_file)
    return True


def run():
    config = load_config()
    setup_logging(config["log_file"])
    write_pid(config["pid_file"])

    logging.info("Daemon started.")

    def handle_signal(signum, frame):
        logging.info("Daemon stopped.")
        remove_pid(config["pid_file"])
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)

    interval = config["interval_minutes"] * 60

    while True:
        create_backup(config["source_dir"], config["backup_dir"])
        time.sleep(interval)

def read_log_file():
    config = load_config()
    log_path = config["log_file"]

    if not os.path.exists(log_path):
        return ""

    with open(log_path, "r") as f:
        return f.read()

def refresh_logs():
    log_content = read_log_file()
    log_box.delete(1.0, tk.END)
    log_box.insert(tk.END, log_content)
    root.after(2000, refresh_logs)

def clear_logs():
    config = load_config()
    log_path = config["log_file"]

    # Очистить файл
    if os.path.exists(log_path):
        open(log_path, "w").close()

    # Очистить окно
    log_box.delete(1.0, tk.END)

#GUI

def start_daemon():
    subprocess.Popen(["python3", __file__, "start"])
    log("Daemon started.")
    update_status()


def stop_daemon_gui():
    config = load_config()
    if stop_daemon(config["pid_file"]):
        log("Daemon stopped.")
    else:
        log("Daemon is not running.")
    update_status()


def update_status():
    config = load_config()
    if os.path.exists(config["pid_file"]):
        with open(config["pid_file"], "r") as f:
            pid = f.read()
        status_label.config(text=f"Running (PID {pid})")
    else:
        status_label.config(text="Not running")


def save_from_gui():
    config = {
        "source_dir": source_entry.get(),
        "backup_dir": backup_entry.get(),
        "log_file": log_entry.get(),
        "pid_file": pid_entry.get(),
        "interval_minutes": int(interval_entry.get())
    }
    save_config(config)
    log("Configuration saved.")


def log(message):
    log_box.insert(tk.END, message + "\n")
    log_box.see(tk.END)


def run_gui():
    global source_entry, backup_entry, log_entry, pid_entry, interval_entry
    global status_label, log_box, root

    config = load_config()

    root = tk.Tk()
    root.title("Backup Daemon")
    root.geometry("500x500")

    # ==== Config Fields ====
    fields = tk.Frame(root)
    fields.pack(pady=10)

    tk.Label(fields, text="Source dir").grid(row=0, column=0, sticky="w")
    source_entry = tk.Entry(fields, width=40)
    source_entry.grid(row=0, column=1)
    source_entry.insert(0, config["source_dir"])

    tk.Label(fields, text="Backup dir").grid(row=1, column=0, sticky="w")
    backup_entry = tk.Entry(fields, width=40)
    backup_entry.grid(row=1, column=1)
    backup_entry.insert(0, config["backup_dir"])

    tk.Label(fields, text="Log file").grid(row=2, column=0, sticky="w")
    log_entry = tk.Entry(fields, width=40)
    log_entry.grid(row=2, column=1)
    log_entry.insert(0, config["log_file"])

    tk.Label(fields, text="PID file").grid(row=3, column=0, sticky="w")
    pid_entry = tk.Entry(fields, width=40)
    pid_entry.grid(row=3, column=1)
    pid_entry.insert(0, config["pid_file"])

    tk.Label(fields, text="Interval (minutes)").grid(row=4, column=0, sticky="w")
    interval_entry = tk.Entry(fields, width=40)
    interval_entry.grid(row=4, column=1)
    interval_entry.insert(0, str(config["interval_minutes"]))

    tk.Button(root, text="Save config", command=save_from_gui).pack(pady=5)

    # ==== Control Buttons ====
    controls = tk.Frame(root)
    controls.pack(pady=10)

    tk.Button(controls, text="Start", width=10, command=start_daemon).grid(row=0, column=0, padx=5)
    tk.Button(controls, text="Stop", width=10, command=stop_daemon_gui).grid(row=0, column=1, padx=5)
    tk.Button(controls, text="Status", width=10, command=update_status).grid(row=0, column=2, padx=5)
    tk.Button(controls, text="Clear", width=10, command=clear_logs).grid(row=0, column=3, padx=5)

    status_label = tk.Label(root, text="Unknown")
    status_label.pack(pady=5)

    log_box = scrolledtext.ScrolledText(root, height=8)
    log_box.pack(fill="both", expand=True, padx=10, pady=10)

    update_status()
    refresh_logs()
    root.mainloop()


#ENTRY

if __name__ == "__main__":
    if len(sys.argv) == 2:
        config = load_config()

        if sys.argv[1] == "start":
            daemonize()
            run()

        elif sys.argv[1] == "stop":
            stop_daemon(config["pid_file"])

        elif sys.argv[1] == "status":
            if os.path.exists(config["pid_file"]):
                print("Daemon is running.")
            else:
                print("Daemon is not running.")

    else:
        run_gui()