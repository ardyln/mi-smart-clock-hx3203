# SPDX-License-Identifier: GPL-2.0-or-later
# Daylight session 3 (2026-11-02): clock raw ch0/ch1 (daylight3.log, alslog 5 Hz) against the
# zorn phone's light sensor read over adb (daylight3_zorn.log, dumpsys sensorservice ~1 Hz).
import re, sys, datetime as dt, statistics as st

DAY = dt.datetime(2026, 11, 2, tzinfo=dt.timezone(dt.timedelta(hours=3)))
EV = re.compile(r'^\s+\d+ \(ts=([\d.]+), wall=(\d+):(\d+):(\d+)\.(\d+)\) (.*)$')

def zorn(path):
    lux, raw, sec = {}, {}, None
    for line in open(path):
        if 'Raw Data Non-wakeup: last' in line: sec = raw; continue
        if 'Ambient Light Sensor Non-wakeup: last' in line: sec = lux; continue
        if not line.startswith('\t'): sec = None if not line.startswith('T ') else sec; continue
        m = EV.match(line)
        if not m or sec is None: continue
        h, mi, s, ms = map(int, m.group(2, 3, 4, 5))
        t = int(DAY.replace(hour=h, minute=mi, second=s).timestamp() * 1000) + ms
        sec[m.group(1)] = (t, [float(v) for v in m.group(6).split(',') if v.strip()])
    return sorted(lux.values()), sorted(raw.values())

def clock(path):
    out = []
    for line in open(path):
        p = line.split()
        if len(p) == 6 and p[0].isdigit(): out.append((int(p[0]), int(p[1]), int(p[2])))
    return out

def near(cl, t, w=600):
    v = [(a, b) for (tt, a, b) in cl if abs(tt - t) <= w]
    return (st.mean(x for x, _ in v), st.mean(y for _, y in v)) if v else None

lux, raw = zorn(sys.argv[2] if len(sys.argv) > 2 else 'daylight3_zorn.log')
cl = clock(sys.argv[1] if len(sys.argv) > 1 else 'daylight3.log')
print(f'clock samples {len(cl)}, zorn lux events {len(lux)}, zorn raw events {len(raw)}')
import bisect
rt = [t for t, _ in raw]
def raw_at(t, w=300):
    i = bisect.bisect_left(rt, t)
    c = [j for j in (i - 1, i) if 0 <= j < len(rt) and abs(rt[j] - t) <= w]
    return raw[min(c, key=lambda j: abs(rt[j] - t))][1] if c else None
t0, t1 = cl[0][0], cl[-1][0]
# zorn's lux is on-change only (~1 event per 20-60 s); its raw stream is 5 Hz, so scale raw ch1 to lux.
# zorn's lux follows raw1: lux/raw1 stayed the same with the TRADFRI on or off, lux/raw0 did not (lockin1).
pairs = [(v[0], r[1]) for t, v in lux if t0 <= t <= t1 and (r := raw_at(t))]
k = st.median(l / r for l, r in pairs)
print(f'lux events in session {len(pairs)}, lux/raw1 = {k*1e3:.4f}e-3 '
      f'(spread {min(l/r for l,r in pairs)*1e3:.4f}..{max(l/r for l,r in pairs)*1e3:.4f})')
# 5 s bins: zorn reference vs clock
B = 5000
bins = {}
for t, v in raw:
    if t0 <= t <= t1: bins.setdefault(t // B, [[], []])[0].append(k * v[1])
for t, a, b in cl: bins.setdefault(t // B, [[], []])[1].append((a, b))
rows = []
for key in sorted(bins):
    z, c = bins[key]
    if len(z) < 10 or len(c) < 10: continue
    x0 = st.mean(a for a, _ in c) - 3.4; x1 = st.mean(b for _, b in c) - 15.5
    rows.append((key * B, st.mean(z), x0, x1))
print(f'{len(rows)} bins of 5 s')
print('time      zorn_lx    x0     x1   v0.2_lx  ratio  zorn/v0.2')
for t, z, x0, x1 in rows[::max(1, len(rows) // 40)]:
    print(f'{dt.datetime.fromtimestamp(t/1000):%H:%M:%S} {z:8.1f} {x0:6.0f} {x1:6.0f} {0.157*x0:8.1f}  {x1/x0:.3f}  {z/(0.157*x0):.3f}')
f = [z / (0.157 * x0) for _, z, x0, _ in rows]; r = [x1 / x0 for _, _, x0, x1 in rows]
print(f'\nzorn/v0.2: mean {st.mean(f):.3f} sd {st.stdev(f):.3f} range {min(f):.3f}..{max(f):.3f}')
print(f'ratio x1/x0: mean {st.mean(r):.4f} sd {st.stdev(r):.4f} range {min(r):.4f}..{max(r):.4f}')
for name, fn in (('v0.3a 0.39*(x0-2.25x1)', lambda x0, x1: 0.39 * (x0 - 2.25 * x1)),
                 ('v0.3b 0.157*(2.25x0-5x1)', lambda x0, x1: 0.157 * (2.25 * x0 - 5 * x1))):
    q = [z / fn(x0, x1) for _, z, x0, x1 in rows]
    print(f'zorn/{name}: mean {st.mean(q):.3f} sd {st.stdev(q):.3f}')
# least squares lux = a*x0 + b*x1 (no intercept)
sxx = sum(x0 * x0 for _, _, x0, _ in rows); syy = sum(x1 * x1 for *_, x1 in rows)
sxy = sum(x0 * x1 for _, _, x0, x1 in rows)
szx = sum(z * x0 for _, z, x0, _ in rows); szy = sum(z * x1 for _, z, _, x1 in rows)
d = sxx * syy - sxy * sxy
a = (szx * syy - szy * sxy) / d; b = (szy * sxx - szx * sxy) / d
print(f'free fit: lux = {a:.4f}*x0 + {b:.4f}*x1   (one-term: lux = {szx/sxx:.4f}*x0)')
