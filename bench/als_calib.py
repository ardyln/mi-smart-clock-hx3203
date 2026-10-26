# SPDX-License-Identifier: GPL-2.0-or-later
"""Calibrate the panel's HX3203 against the bedroom MYGGSPRAY lux sensor using the TRADFRI lamp.

Streams HX3203 data registers from the panel (adb, ~2 Hz) and polls HA's reference lux, while
stepping the lamp through brightness levels. Writes one CSV row per HX3203 sample.
"""
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

PANEL = "192.168.1.42:42611"
LAMP = "light.0xbc8d7efffe21ed09"
REF = "sensor.bedroom_myggspray_wrlss_mtn_sensor_illuminance"
PHASES = [("off", None, 60), ("100%", 100, 150), ("30%", 30, 150), ("off-end", None, 90)]
OUT = sys.argv[1]
TOKEN = open(os.path.expanduser("~/.config/ha-token")).read().strip()
REGS = ["0x08", "0x09", "0x0a", "0x0d", "0x0e", "0x0f", "0x80", "0x81", "0x87"]


def ha(method, path, body=None):
    req = urllib.request.Request("http://homeassistant:8123" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def set_lamp(pct):
    if pct is None:
        ha("POST", "/api/services/light/turn_off", {"entity_id": LAMP})
    else:
        ha("POST", "/api/services/light/turn_on", {"entity_id": LAMP, "brightness_pct": pct})


ref = {"lux": None}


def poll_ref(stop):
    while not stop.is_set():
        try:
            ref["lux"] = float(ha("GET", f"/api/states/{REF}")["state"])
        except Exception:
            pass
        stop.wait(2)


ONE = "for r in " + " ".join(REGS) + "; do printf \"%s \" $(i2cget -f -y 0 0x44 $r); done"


def sample():
    try:
        out = subprocess.run(["adb", "-s", PANEL, "shell", f"su -c '{ONE}'"], capture_output=True, text=True, timeout=8).stdout
        return out.split()
    except subprocess.TimeoutExpired:
        return []
stop = threading.Event()
threading.Thread(target=poll_ref, args=(stop,), daemon=True).start()

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t", "phase", "ref_lux"] + REGS)
    t0 = time.time()
    try:
        for name, pct, dur in PHASES:
            set_lamp(pct)
            end = time.time() + dur
            while time.time() < end:
                line = sample()
                if len(line) == len(REGS):
                    w.writerow([round(time.time() - t0, 1), name, ref["lux"]] + [int(x, 16) for x in line])
                    f.flush()
            print(f"phase {name} done, ref lux {ref['lux']}", flush=True)
    finally:
        set_lamp(None)
        stop.set()
print("done; lamp switched off", flush=True)
