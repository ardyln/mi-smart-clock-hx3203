# SPDX-License-Identifier: GPL-2.0-or-later
# TRADFRI 255 square wave on daylight (2026-11-02): step size on the clock (and zorn) per cycle.
# Night reference: TRADFRI 255 alone gives ch0 137/140/154/124 counts over dark (sweeps 1-4).
import json, sys, statistics as st, datetime as dt
sys.argv[1:] = sys.argv[1:] or ['lockin.log', 'lockin_zorn.log', 'marks_lockin1.json']
src = open('analyze_daylight3.py').read()
exec(src[:src.index('lux, raw = ')])  # parsers only
lux, raw = zorn(sys.argv[2]); cl = clock(sys.argv[1])
marks = json.load(open(sys.argv[3]))

def mean_in(series, a, b, f):
    v = [f(x) for x in series if a <= x[0] <= b]
    return st.mean(v) if len(v) >= 5 else None

def steps(series, f, lag=0):
    out = []
    ev = [(t + lag, s) for t, s in marks]
    for i in range(1, len(ev) - 1):
        t, s = ev[i]
        if s != 'on': continue
        pre = mean_in(series, ev[i - 1][0] + 4000, t - 1000, f)
        on = mean_in(series, t + 4000, ev[i + 1][0] - 1000, f)
        nxt = ev[i + 2][0] if i + 2 < len(ev) else ev[i + 1][0] + 20000
        post = mean_in(series, ev[i + 1][0] + 4000, nxt - 1000, f)
        if None in (pre, on, post): continue
        out.append((t, (pre + post) / 2, on - (pre + post) / 2))
    return out

for name, series, f in (('clock ch0', cl, lambda x: x[1]), ('clock ch1', cl, lambda x: x[2]),
                        ('zorn raw0', raw, lambda x: x[1][0]), ('zorn raw1', raw, lambda x: x[1][1])):
    s = steps(series, f)
    print(f'\n{name}: cycle  base  step')
    for t, b, d in s:
        print(f'  {dt.datetime.fromtimestamp(t/1000):%H:%M:%S} {b:10.1f} {d:9.1f}')
    d = [x[2] for x in s]
    print(f'  mean step {st.mean(d):.1f}  sd {st.stdev(d):.1f}  sem {st.stdev(d)/len(d)**.5:.1f}  (n={len(d)})')

# zorn lux follows raw1 (lux/raw1 is the same with the bulb on and off; lux/raw0 is not)
import bisect
rt = [t for t, _ in raw]
def raw_at(t, w=300):
    i = bisect.bisect_left(rt, t)
    c = [j for j in (i - 1, i) if 0 <= j < len(rt) and abs(rt[j] - t) <= w]
    return raw[min(c, key=lambda j: abs(rt[j] - t))][1] if c else None
k1 = st.median(v[0] / r[1] for t, v in lux if marks[0][0] <= t <= marks[-1][0] and (r := raw_at(t)))
c = steps(cl, lambda x: x[1]); z = steps(raw, lambda x: x[1][1])
led = k1 * st.mean(x[2] for x in z) / st.mean(x[2] for x in c)
day = st.mean(k1 * b2 / (b1 - 3.4) for (_, b1, _), (_, b2, _) in zip(c, z))
print(f'\nk1 = {k1*1e3:.3f}e-3 lx/raw1; TRADFRI step on zorn {k1*st.mean(x[2] for x in z):.1f} lx')
print(f'lux per clock ch0 count: TRADFRI {led:.4f}, daylight {day:.4f}, ratio {led/day:.2f} (v0.2 uses 0.157)')
