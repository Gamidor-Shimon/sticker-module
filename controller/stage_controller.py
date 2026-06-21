"""
Gamidor Motorized Stage - Desktop Controller
Talks to ESP32 firmware over USB serial. Tkinter GUI + config file.
"""

import json
import os
import sys
import time
import threading
import queue
from pathlib import Path

import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox


# ---------- Config ----------

DEFAULT_CONFIG = {
    "COM_PORT": "Auto",
    "BAUD_RATE": 115200,
    "POS1_VALUE": 2000,
    "POS2_VALUE": 6000,
    "DEFAULT_SPEED": 1000,
    "MOVE_TIMEOUT_SEC": 30,
}


def app_dir() -> Path:
    # Works for both `python script.py` and PyInstaller --onefile
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def load_config() -> dict:
    cfg_path = app_dir() / "config.json"
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        return dict(DEFAULT_CONFIG)
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


# ---------- Serial layer ----------

ESP32_VID_HINTS = ("CP210", "CH340", "Silicon Labs", "USB-SERIAL", "FTDI", "wchusbserial")


def auto_detect_port() -> str | None:
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        if any(h.lower() in desc.lower() for h in ESP32_VID_HINTS):
            return p.device
    ports = list(serial.tools.list_ports.comports())
    return ports[0].device if ports else None


class StageLink:
    def __init__(self, port: str, baud: int, on_event):
        self.port = port
        self.baud = baud
        self.on_event = on_event   # callback(str)
        self.ser: serial.Serial | None = None
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None

    def open(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
        time.sleep(2.0)  # ESP32 auto-reset after open
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self):
        self._stop.set()
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send(self, cmd: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial not open")
        line = (cmd.strip() + "\n").encode("ascii")
        self.ser.write(line)
        self.ser.flush()

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(64)
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("ascii", errors="ignore").strip()
                        if text:
                            self.on_event(text)
            except Exception as e:
                self.on_event(f"ERR LINK {e}")
                break


# ---------- GUI ----------

class App(tk.Tk):
    def __init__(self, cfg: dict):
        super().__init__()
        self.title("Gamidor Motorized Stage")
        self.geometry("520x420")
        self.cfg = cfg
        self.link: StageLink | None = None
        self.busy = False
        self.events = queue.Queue()

        self._build_ui()
        self._poll_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._connect)

    # UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        top = ttk.LabelFrame(self, text="Connection")
        top.pack(fill="x", **pad)
        self.lbl_port = ttk.Label(top, text="Port: -")
        self.lbl_port.pack(side="left", padx=6)
        self.lbl_state = ttk.Label(top, text="State: disconnected", foreground="red")
        self.lbl_state.pack(side="right", padx=6)

        ctl = ttk.LabelFrame(self, text="Commands")
        ctl.pack(fill="x", **pad)

        self.btn_init = ttk.Button(ctl, text="INIT (Home)", command=lambda: self._cmd("INIT"))
        self.btn_pos1 = ttk.Button(ctl, text=f"POS1 ({cfg['POS1_VALUE']})",
                                   command=lambda: self._cmd("POS1"))
        self.btn_pos2 = ttk.Button(ctl, text=f"POS2 ({cfg['POS2_VALUE']})",
                                   command=lambda: self._cmd("POS2"))
        self.btn_init.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self.btn_pos1.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        self.btn_pos2.grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        for i in range(3):
            ctl.columnconfigure(i, weight=1)

        goto = ttk.Frame(ctl)
        goto.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        ttk.Label(goto, text="GOTO:").pack(side="left")
        self.ent_goto = ttk.Entry(goto, width=10)
        self.ent_goto.pack(side="left", padx=4)
        self.btn_goto = ttk.Button(goto, text="Go", command=self._do_goto)
        self.btn_goto.pack(side="left")

        ttk.Label(goto, text="   SPEED:").pack(side="left", padx=(20, 0))
        self.ent_speed = ttk.Entry(goto, width=8)
        self.ent_speed.insert(0, str(self.cfg["DEFAULT_SPEED"]))
        self.ent_speed.pack(side="left", padx=4)
        self.btn_speed = ttk.Button(goto, text="Set", command=self._do_speed)
        self.btn_speed.pack(side="left")

        logf = ttk.LabelFrame(self, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(logf, height=10, state="disabled", bg="#111", fg="#0f0",
                           font=("Consolas", 10))
        self.txt.pack(fill="both", expand=True)

        self._set_buttons_enabled(False)

    def _set_buttons_enabled(self, en: bool):
        state = "normal" if en else "disabled"
        for b in (self.btn_init, self.btn_pos1, self.btn_pos2,
                  self.btn_goto, self.btn_speed):
            b.configure(state=state)

    def _log(self, s: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", s + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    # Lifecycle
    def _connect(self):
        port = self.cfg["COM_PORT"]
        if str(port).lower() == "auto":
            port = auto_detect_port()
        if not port:
            messagebox.showerror("Connection", "No serial port found.")
            return
        self.lbl_port.configure(text=f"Port: {port}")
        try:
            self.link = StageLink(port, int(self.cfg["BAUD_RATE"]),
                                  on_event=lambda s: self.events.put(s))
            self.link.open()
            self.lbl_state.configure(text="State: connected", foreground="green")
            self._set_buttons_enabled(True)
            # Push default speed on connect
            self.after(2200, lambda: self._cmd(f"SPEED {int(self.cfg['DEFAULT_SPEED'])}",
                                                track_busy=False))
        except Exception as e:
            messagebox.showerror("Connection", f"Open failed: {e}")

    def _on_close(self):
        if self.link:
            self.link.close()
        self.destroy()

    # Commands
    def _cmd(self, cmd: str, track_busy: bool = True):
        if not self.link:
            return
        if self.busy and track_busy:
            return
        self._log(f"> {cmd}")
        try:
            self.link.send(cmd)
        except Exception as e:
            self._log(f"! send failed: {e}")
            return
        if track_busy:
            self.busy = True
            self._set_buttons_enabled(False)

    def _do_goto(self):
        v = self.ent_goto.get().strip()
        if not v.lstrip("-").isdigit():
            messagebox.showwarning("GOTO", "Enter integer step value.")
            return
        self._cmd(f"GOTO {int(v)}")

    def _do_speed(self):
        v = self.ent_speed.get().strip()
        if not v.isdigit() or int(v) <= 0:
            messagebox.showwarning("SPEED", "Enter positive integer.")
            return
        self._cmd(f"SPEED {int(v)}", track_busy=False)

    # Event pump (serial reader thread -> Tk main thread)
    def _poll_events(self):
        try:
            while True:
                line = self.events.get_nowait()
                self._handle_event(line)
        except queue.Empty:
            pass
        self.after(50, self._poll_events)

    def _handle_event(self, line: str):
        self._log(f"< {line}")
        u = line.upper()
        if u in ("DONE", "HOME_DONE") or u.startswith("ERR"):
            self.busy = False
            self._set_buttons_enabled(True)
        elif u == "BUSY":
            self.busy = True
            self._set_buttons_enabled(False)


def main():
    cfg = load_config()
    App(cfg).mainloop()


if __name__ == "__main__":
    main()
