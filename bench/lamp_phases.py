# SPDX-License-Identifier: GPL-2.0-or-later
"""Drive the TRADFRI lamp through calibration phases after the panel reboots, logging HA's reference lux.

Waits for the panel to drop off and come back (ping), gives its one-shot logger time to start,
then runs the phases. Writes phase boundaries and reference lux with epoch timestamps.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

LAMP = "light.0xbc8d7efffe21ed09"
REF = "sensor.bedroom_myggspray_wrlss_mtn_sensor_illuminance"
PHASES = [("off", None, 60), ("100%", 100, 150), ("30%", 30, 150), ("off-end", None, 90)]
OUT = sys.argv[1]
TOKEN = open(os.path.expanduser("~/.config/ha-token")).read().strip()


def ha(method, path, body=None):
    req = urllib.request.Request("http://homeassistant:8123" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def up():
    return subprocess.run(["ping", "-c1", "-W2", "192.168.1.42"], capture_output=True).returncode == 0


def log(f, *fields):
    f.write("\t".join(str(x) for x in (round(time.time(), 1),) + fields) + "\n")
    f.flush()


with open(OUT, "w") as f:
    while up():
        time.sleep(2)
    log(f, "panel-down")
    while not up():
        time.sleep(2)
    log(f, "panel-up")
    time.sleep(120)  # boot_completed + the logger's own 30 s delay, with margin
    try:
        for name, pct, dur in PHASES:
            if pct is None:
                ha("POST", "/api/services/light/turn_off", {"entity_id": LAMP})
            else:
                ha("POST", "/api/services/light/turn_on", {"entity_id": LAMP, "brightness_pct": pct})
            log(f, "phase", name)
            end = time.time() + dur
            while time.time() < end:
                try:
                    log(f, "ref", ha("GET", f"/api/states/{REF}")["state"])
                except Exception as e:
                    log(f, "ref-error", type(e).__name__)
                time.sleep(5)
    finally:
        ha("POST", "/api/services/light/turn_off", {"entity_id": LAMP})
        log(f, "lamp-off")
print("done", flush=True)
