# SPDX-License-Identifier: GPL-2.0-or-later
# Clock steps against zorn raw0 as a reference, per heater cycle and as a response curve: ir_curve.py <label>...
import json, sys, re, statistics as st, datetime as dt, bisect
def load(L):
    c = [l.split() for l in open(f'ir_{L}.log') if re.match(r'^\d{13} ', l)]
    c = [(int(x[0]), int(x[1]), int(x[2]), int(x[5])) for x in c]
    m = [(t, s) for t, s in json.load(open(f'marks_ir_{L}.json')) if s.endswith((' on', ' off', ' end'))]
    z = {}
    for l in open(f'ir_{L}_zorn.log'):
        r = re.search(r'wall=(\d+):(\d+):(\d+\.\d+)\) ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)', l)
        if r:
            b = dt.datetime.fromtimestamp(c[0][0] / 1000).replace(hour=int(r[1]), minute=int(r[2]), second=0, microsecond=0)
            z[int((b.timestamp() + float(r[3])) * 1000)] = (float(r[4]), float(r[5]))
    return c, m, sorted(z.items())
def mean(xs, i): return st.mean(x[i] for x in xs)
for L in sys.argv[1:]:
    c, m, z = load(L)
    zt = [t for t, _ in z]
    print(L, 'r0c flips (s):', [(round((a[0] - c[0][0]) / 1000), a[3], b[3]) for a, b in zip(c, c[1:]) if a[3] != b[3]])
    ons = [t for t, s in m if s.endswith(' on')]
    pts = []
    for n, on in enumerate(ons):
        bw = [x for x in c if on - 25000 <= x[0] < on - 2000 and x[3] == 34]
        zb = [v[0] for t, v in z if on - 25000 <= t < on - 2000]
        if not bw or not zb: print(f'  cycle {n+1}: no baseline samples'); continue
        b0, b1, bz = mean(bw, 1), mean(bw, 2), st.mean(zb)
        top = [x for x in c if on + 45000 <= x[0] < on + 60000]
        zt_ = [v[0] for t, v in z if on + 45000 <= t < on + 60000]
        if not zt_: print(f'  cycle {n+1}: no zorn top samples'); continue
        print(f'  cycle {n+1}: base ch0 {b0:.1f} ch1 {b1:.1f} z {bz:.0f} | top d0 {mean(top,1)-b0:.1f} d1 {mean(top,2)-b1:.1f} dz {st.mean(zt_)-bz:.0f} | d0/dz*1000 {(mean(top,1)-b0)/(st.mean(zt_)-bz)*1000:.1f} d1/dz*1000 {(mean(top,2)-b1)/(st.mean(zt_)-bz)*1000:.1f}')
        for x in c:
            if on <= x[0] < on + 60000:
                i = bisect.bisect(zt, x[0]) - 1
                if i >= 0 and x[0] - zt[i] < 1500: pts.append((z[i][1][0] - bz, x[1] - b0, x[2] - b1))
    bins = {}
    for p in pts: bins.setdefault(int(p[0] // 500), []).append(p)
    print('  dz bin   n   d0   d1')
    for k in sorted(bins):
        w = bins[k]
        if len(w) > 15: print(f'  {k*500+250:6} {len(w):4} {st.mean(p[1] for p in w):7.1f} {st.mean(p[2] for p in w):7.1f}')
