import json,urllib.request,time,subprocess,re
t=open('/home/ardy/.config/ha-token').read().strip()
H={'Authorization':'Bearer '+t,'Content-Type':'application/json'}
def svc(s,d): urllib.request.urlopen(urllib.request.Request('http://192.168.1.73:8123/api/services/light/'+s,data=json.dumps(d).encode(),headers=H),timeout=10)
def ha(): return json.load(urllib.request.urlopen(urllib.request.Request('http://192.168.1.73:8123/api/states/sensor.unknown_phh_treble_vanilla_ambient_light',headers=H),timeout=10))['state']
def dev():
    o=subprocess.run(['adb','-s','192.168.1.44:36213','shell','dumpsys sensorservice'],capture_output=True,text=True,timeout=20).stdout
    o=o.split('LIGHT: last',1)[1].split('\n')[1:]; ev=[l for l in o[:60] if 'wall=' in l]
    i=0
    while i<len(o) and 'wall=' in o[i]: i+=1
    o=o[i-1] if i else ''
    m=re.search(r'wall=([\d:.]+)\) ([\d.]+)',o); return m.groups() if m else ('?','?')
B='light.0xbc8d7efffe21ed09'
phases=[('off',70)]+[('on',70),('off',70)]*3
try:
    for ph,dur in phases:
        svc('turn_on',{'entity_id':B,'brightness':255}) if ph=='on' else svc('turn_off',{'entity_id':B})
        print('MARK',time.strftime('%H:%M:%S'),ph,flush=True)
        end=time.time()+dur
        while time.time()<end:
            w,v=dev(); print(time.strftime('%H:%M:%S'),'dev',w,v,'ha',ha(),flush=True); time.sleep(5)
finally:
    svc('turn_off',{'entity_id':B}); print('DONE tradfri off',flush=True)
