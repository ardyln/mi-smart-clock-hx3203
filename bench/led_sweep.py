# SPDX-License-Identifier: GPL-2.0-or-later
# TRADFRI brightness staircase: led_sweep.py <marks.json> <step_s>. Leaves the bulb off.
import json, urllib.request, os, time, sys, subprocess, signal
tok = open(os.path.expanduser('~/.config/ha-token')).read().strip()
H = {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}
C = 'light.0xbc8d7efffe21ed09'
ADB = ['adb', '-s', os.environ.get('CLOCK', '192.168.1.44:35925'), 'shell']
def call(svc, **d):
    urllib.request.urlopen(urllib.request.Request(f'http://192.168.1.73:8123/api/services/light/{svc}',
                           data=json.dumps(d).encode(), headers=H), timeout=15).read()
def verify(b):
    # HA accepts commands even when the bulb is unreachable, so check what it reports
    time.sleep(1.5)
    r = urllib.request.Request(f'http://192.168.1.73:8123/api/states/{C}', headers=H)
    s = json.load(urllib.request.urlopen(r, timeout=15))
    got = s['attributes'].get('brightness') or 0
    if s['state'] != ('on' if b else 'off') or abs(got - b) > 5:
        print(f'ABORT: bulb did not reach b{b}: {s["state"]} {got}', flush=True); sys.exit(2)
def lux():
    o = subprocess.run(ADB + ["dumpsys sensorservice | sed -n '/LIGHT: last 50/,/^[A-Z]/p'"],
                       capture_output=True, text=True, timeout=20).stdout
    ev = [l for l in o.splitlines() if 'wall=' in l]
    return ev[-1].split(')')[1].split(',')[0].strip() if ev else None
out, step = sys.argv[1], int(sys.argv[2])
marks = []
def mark(s):
    marks.append((int(time.time() * 1000), s)); json.dump(marks, open(out, 'w'))
    print(time.strftime('%H:%M:%S'), s, flush=True)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
try:
    for b in (0, 40, 60, 80, 110, 150, 200, 255, 0):
        call('turn_on', entity_id=C, brightness=b, transition=0) if b else call('turn_off', entity_id=C, transition=0)
        mark(f'b{b}'); verify(b); time.sleep(step - 3.5)
        mark(f'b{b} lux {lux()}'); time.sleep(1)
    mark('end')
finally:
    for _ in range(30):
        try:
            call('turn_on', entity_id=C, brightness=3, transition=0); time.sleep(1)
            call('turn_off', entity_id=C, transition=0); print('bulb off', flush=True); break
        except Exception as e: print('retry', e, flush=True); time.sleep(5)
