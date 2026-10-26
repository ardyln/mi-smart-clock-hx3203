# SPDX-License-Identifier: GPL-2.0-or-later
import json, urllib.request, os, time, sys
tok=open(os.path.expanduser('~/.config/ha-token')).read().strip()
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def call(dom,svc,**d):
    urllib.request.urlopen(urllib.request.Request(f'http://192.168.1.73:8123/api/services/{dom}/{svc}',data=json.dumps(d).encode(),headers=H),timeout=15).read()
L='light.lamps'; T='light.0xbc8d7efffe21ed09'; S='light.unknown_phh_treble_vanilla_screen'; A='switch.unknown_phh_treble_vanilla_adaptive_brightness'
steps=[
 ('baseline', []),
 ('dark_screen255', [('light','turn_off',dict(entity_id=L,transition=0))]),
 ('dark_screen1', [('switch','turn_off',dict(entity_id=A)),('light','turn_on',dict(entity_id=S,brightness=1))]),
 ('dark_screen255b', [('light','turn_on',dict(entity_id=S,brightness=255))]),
 ('lamps_b10_2202', [('light','turn_on',dict(entity_id=L,brightness=10,color_temp_kelvin=2202,transition=0))]),
 ('lamps_b40_2202', [('light','turn_on',dict(entity_id=L,brightness=40,transition=0))]),
 ('lamps_b100_2202', [('light','turn_on',dict(entity_id=L,brightness=100,transition=0))]),
 ('lamps_b180_2202', [('light','turn_on',dict(entity_id=L,brightness=180,transition=0))]),
 ('lamps_b255_2202', [('light','turn_on',dict(entity_id=L,brightness=255,transition=0))]),
 ('lamps_b255_2700', [('light','turn_on',dict(entity_id=L,color_temp_kelvin=2700,transition=0))]),
 ('lamps_b255_4000', [('light','turn_on',dict(entity_id=L,color_temp_kelvin=4000,transition=0))]),
 ('lamps_b255_6535', [('light','turn_on',dict(entity_id=L,color_temp_kelvin=6535,transition=0))]),
 ('tradfri_b30', [('light','turn_off',dict(entity_id=L,transition=0)),('light','turn_on',dict(entity_id=T,brightness=30,transition=0))]),
 ('tradfri_b128', [('light','turn_on',dict(entity_id=T,brightness=128,transition=0))]),
 ('tradfri_b255', [('light','turn_on',dict(entity_id=T,brightness=255,transition=0))]),
 ('all_max_6535', [('light','turn_on',dict(entity_id=L,brightness=255,color_temp_kelvin=6535,transition=0))]),
]
marks=[]
for name,acts in steps:
    for a in acts: call(a[0],a[1],**a[2])
    marks.append((int(time.time()*1000),name)); print(name,flush=True)
    time.sleep(20)
marks.append((int(time.time()*1000),'end'))
# restore
call('light','turn_off',entity_id=T,transition=0)
call('light','turn_on',entity_id=L,brightness=3,color_temp_kelvin=2202,transition=0)
call('light','turn_on',entity_id=S,brightness=255)
call('switch','turn_on',entity_id=A)
json.dump(marks,open(sys.argv[1],'w'))
print('restored')
