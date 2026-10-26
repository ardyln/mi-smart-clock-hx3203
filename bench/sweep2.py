# SPDX-License-Identifier: GPL-2.0-or-later
import json, urllib.request, os, time, sys
tok=open(os.path.expanduser('~/.config/ha-token')).read().strip()
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def call(svc,**d):
    urllib.request.urlopen(urllib.request.Request(f'http://192.168.1.73:8123/api/services/light/{svc}',data=json.dumps(d).encode(),headers=H),timeout=15).read()
A='light.kajplats_e14_ws_globe_806lm'; B='light.kajplats_e27_ws_globe_1521lm'; C='light.0xbc8d7efffe21ed09'
def setl(a,b,c):
    for e,v in ((A,a),(B,b),(C,c)):
        if v: call('turn_on',entity_id=e,brightness=v,transition=0,**({} if e==C else {'color_temp_kelvin':2700}))
        else: call('turn_off',entity_id=e,transition=0)
steps=[(0,0,0)]
for x in (255,140,80):
    steps += [(x,0,0),(0,x,0),(0,0,x),(x,x,x)]
steps += [(0,20,0),(0,40,0),(0,60,0),(0,100,0),(0,0,0)]
marks=[]
for s in steps:
    setl(*s); marks.append((int(time.time()*1000),s)); print(s,flush=True); time.sleep(15)
marks.append((int(time.time()*1000),'end'))
call('turn_on',entity_id=A,brightness=3,color_temp_kelvin=2202,transition=0)
call('turn_on',entity_id=B,brightness=3,color_temp_kelvin=2202,transition=0)
call('turn_off',entity_id=C,transition=0)
json.dump(marks,open(sys.argv[1],'w')); print('restored')
