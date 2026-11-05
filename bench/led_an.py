# SPDX-License-Identifier: GPL-2.0-or-later
# Per-step table for led_sweep.py: led_an.py <label> [<label2>]
import json, sys, re, statistics as st, datetime as dt
def v3(c0, c1, dark1, K=100, led=.18, day=.383, lpk=157, dpk=55):
    x0, x1 = c0 - 3.4, max(c1 - dark1, 0)
    if x0 <= 0: return 0
    f = min(1, max(0, ((x1 + led * K) / (x0 + K) - led) / (day - led)))
    return x0 * (lpk + (dpk - lpk) * f) / 1000
for L in sys.argv[1:]:
    c = [l.split() for l in open(f'{L}.log') if re.match(r'^\d{13} ', l)]
    c = [(int(x[0]), int(x[1]), int(x[2]), int(x[5])) for x in c]
    m = json.load(open(f'marks_{L}.json'))
    st_ = [(t, s) for t, s in m if ' ' not in s]
    rep = {s.split()[0] + str(i): s.split()[-1] for i, (t, s) in enumerate(x for x in m if ' lux ' in x[1])}
    z = {}
    for l in open(f'{L}_zorn.log'):
        r = re.search(r'wall=(\d+):(\d+):(\d+\.\d+)\) ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)', l)
        if r:
            b = dt.datetime.fromtimestamp(c[0][0] / 1000).replace(hour=int(r[1]), minute=int(r[2]), second=0, microsecond=0)
            z[int((b.timestamp() + float(r[3])) * 1000)] = float(r[5])
    print(L, 'idle samples', sum(1 for x in c if x[3] != 34), 'of', len(c))
    print('step      ch0    ch1  v0.2  155   300  driver  zorn')
    for i in range(len(st_) - 1):
        t, e = st_[i][0], st_[i + 1][0]
        w = [x for x in c if t + 15000 <= x[0] < e - 3000 and x[3] == 34]
        zw = [v for k, v in z.items() if t + 15000 <= k < e - 3000]
        if not w: print(st_[i][1], 'no data'); continue
        a, b = st.mean(x[1] for x in w), st.mean(x[2] for x in w)
        lz = 4.29e-3 * st.mean(zw) if zw else float('nan')
        print(f'{st_[i][1]:6} {a:7.1f} {b:6.1f} {max(0,.157*(a-3.4)):5.1f} {v3(a,b,15.5):5.1f} {v3(a,b,30):5.1f}  {rep.get(st_[i][1]+str(i)):>5}  {lz:5.1f}')
