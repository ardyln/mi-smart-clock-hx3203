# SPDX-License-Identifier: GPL-2.0-or-later
# IR heater square wave via its plug: ir_heater.py <marks.json> <label> [cycles] [on_s] [off_s]
# The selector (400/800/1200 W) is set by hand. The plug is always left off on exit.
import json, urllib.request, os, time, sys, signal
tok = open(os.path.expanduser('~/.config/ha-token')).read().strip()
H = {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}
P = 'switch.grillplats_plug'
A = 'automation.air_freshener'
BASE = 'http://192.168.1.73:8123/api'
def call(dom, svc, ent):
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/services/{dom}/{svc}',
        data=json.dumps({'entity_id': ent}).encode(), headers=H), timeout=15).read()
def state(ent):
    r = urllib.request.Request(f'{BASE}/states/{ent}', headers=H)
    return json.load(urllib.request.urlopen(r, timeout=15))['state']
def power(): return state('sensor.grillplats_plug_power')
out, label = sys.argv[1], sys.argv[2]
cycles = int(sys.argv[3]) if len(sys.argv) > 3 else 3
on_s = int(sys.argv[4]) if len(sys.argv) > 4 else 60
off_s = int(sys.argv[5]) if len(sys.argv) > 5 else 60
marks = []
def mark(s):
    marks.append((int(time.time() * 1000), s)); json.dump(marks, open(out, 'w'))
    print(time.strftime('%H:%M:%S'), s, flush=True)
def term(*_): sys.exit(1)
signal.signal(signal.SIGTERM, term)
signal.signal(signal.SIGHUP, term)
auto_was_on = state(A) == 'on'  # restore what we found, never force it on
if auto_was_on: call('automation', 'turn_off', A)
try:
    call('switch', 'turn_off', P); mark(label + ' off'); time.sleep(off_s)
    for i in range(cycles):
        call('switch', 'turn_on', P); mark(label + ' on'); time.sleep(on_s)
        mark(f'{label} power {power()}')
        call('switch', 'turn_off', P); mark(label + ' off'); time.sleep(off_s)
    mark(label + ' end')
finally:
    # A heater must not outlive this script: HA can be down for minutes, so keep
    # trying and only stop once HA itself reports the plug off.
    for _ in range(600):
        try:
            call('switch', 'turn_off', P)
            if state(P) == 'off': print('plug confirmed off', flush=True); break
        except Exception as e: print('retry off', e, flush=True)
        time.sleep(2)
    else: print('PLUG NOT CONFIRMED OFF, CHECK THE HEATER', flush=True)
    for _ in range(30 if auto_was_on else 0):  # HA may be restarting; never leave it off if it was on
        try: call('automation', 'turn_on', A); break
        except Exception as e: print('retry automation', e, flush=True); time.sleep(5)
    else:
        if auto_was_on: print('AUTOMATION STILL OFF', flush=True)
    print('automation restore done', flush=True)
