# SPDX-License-Identifier: GPL-2.0-or-later
# Heater on/off step per half-cycle: ir_an.py <label>
import json, sys, re, statistics as st, datetime as dt
L = sys.argv[1]
c = [l.split() for l in open(f'ir_{L}.log') if re.match(r'^\d{13} ', l)]
c = [(int(x[0]), int(x[1]), int(x[2])) for x in c]
m = [(t, s) for t, s in json.load(open(f'marks_ir_{L}.json')) if s.endswith((' on', ' off', ' end'))]
z = {}
day = None
for l in open(f'ir_{L}_zorn.log'):
    r = re.search(r'wall=(\d+):(\d+):(\d+\.\d+)\) ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)', l)
    if r:
        b = dt.datetime.fromtimestamp(c[0][0] / 1000).replace(hour=int(r[1]), minute=int(r[2]), second=0, microsecond=0)
        z[int((b.timestamp() + float(r[3])) * 1000)] = [float(r[i]) for i in (4, 5, 6, 7)]
print('phase  n   ch0   ch1  ratio_raw  zorn raw0 raw1 raw2 raw3')
rows = []
for i, (t, s) in enumerate(m):
    e = m[i + 1][0] if i + 1 < len(m) else c[-1][0]
    # skip the first 25 s of each phase: element warm-up / cool-down
    w = [x for x in c if t + 25000 <= x[0] < e]
    if not w: continue
    zw = [v for k, v in z.items() if t + 25000 <= k < e]
    a, b = st.mean(x[1] for x in w), st.mean(x[2] for x in w)
    zm = [round(st.mean(v[j] for v in zw)) for j in range(4)] if zw else None
    rows.append((s, a, b, zm)); print(f'{s:14} {len(w):3} {a:7.1f} {b:7.1f} {(b-15.5)/(a-3.4):.3f} {zm}')
for i in range(1, len(rows) - 1):
    if rows[i][0].endswith(' on'):
        p, q = rows[i - 1], rows[i + 1]
        d0 = rows[i][1] - (p[1] + q[1]) / 2; d1 = rows[i][2] - (p[2] + q[2]) / 2
        dz = [rows[i][3][j] - (p[3][j] + q[3][j]) / 2 for j in range(4)] if rows[i][3] and p[3] and q[3] else None
        print(f'step {d0:+.1f} ch0  {d1:+.1f} ch1  ratio {d1/d0 if d0 else 0:.2f}  zorn {dz}')
