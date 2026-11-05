# SPDX-License-Identifier: GPL-2.0-or-later
# TRADFRI 0/255 square wave on top of daylight: does its step shrink at high counts?
import json, urllib.request, os, time, sys
tok = open(os.path.expanduser('~/.config/ha-token')).read().strip()
H = {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}
C = 'light.0xbc8d7efffe21ed09'
def call(svc, **d):
    urllib.request.urlopen(urllib.request.Request(f'http://192.168.1.73:8123/api/services/light/{svc}',
                           data=json.dumps(d).encode(), headers=H), timeout=15).read()
marks = []
def mark(s):
    marks.append((int(time.time() * 1000), s)); json.dump(marks, open(sys.argv[1], 'w'))
    print(time.strftime('%H:%M:%S'), s, flush=True)
call('turn_off', entity_id=C, transition=0); mark('off'); time.sleep(20)
for i in range(15):
    call('turn_on', entity_id=C, brightness=255, transition=0); mark('on'); time.sleep(20)
    call('turn_off', entity_id=C, transition=0); mark('off'); time.sleep(20)
mark('end')
call('turn_on', entity_id=C, brightness=3, transition=0); print('restored brightness 3', flush=True)
