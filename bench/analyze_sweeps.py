# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the HX3203 calibration tables from the raw sweep data in this directory.

Inputs per sweep N (1-4):
  sweepN.log    alslog output: epoch_ms ch0 ch1 off gain r0c  (panel clock, ~1 s behind)
  marksN.json   [[epoch_ms, step], ...] when each lighting step was commanded (host clock)
  ha_sweepN.json  Home Assistant history for the lights and reference lux sensors

Usage: python3 analyze_sweeps.py   (run from bench/)
See README.md in this directory for what each step actually lit; the sweep 1/2 labels are misleading.
"""
import json
import statistics as st

PANEL_CLOCK_OFFSET_MS = 1000   # panel clock was ~1 s behind the host that wrote the marks
SETTLE_MS = 5000               # skip the first 5 s of each step (bulb transition, smoothing)
PHONE = 'sensor.24117rk2cg_light_sensor'
MYGG = 'sensor.bedroom_myggspray_wrlss_mtn_sensor_illuminance'
PANEL = 'sensor.unknown_phh_treble_vanilla_ambient_light'


def load(n):
    rows = []
    for line in open(f'sweep{n}.log'):
        f = line.split()
        if f and f[0].isdigit():
            rows.append((int(f[0]) + PANEL_CLOCK_OFFSET_MS, int(f[1]), int(f[2])))
    marks = json.load(open(f'marks{n}.json'))
    ha = json.load(open(f'ha_sweep{n}.json'))
    return rows, marks, ha


def steps(n):
    rows, marks, ha = load(n)
    out = []
    for (t0, name), (t1, _) in zip(marks, marks[1:]):
        s = [r for r in rows if t0 + SETTLE_MS <= r[0] <= t1 - 500]
        if not s:
            continue
        refs = {}
        for e in (PHONE, MYGG, PANEL):
            v = [x['state'] for x in ha.get(e, []) if t0 + 4000 <= x['t_ms'] <= t1]
            refs[e] = v
        out.append(dict(step=name if isinstance(name, str) else tuple(name), t0=t0, n=len(s),
                        ch0=st.mean(r[1] for r in s), sd0=st.pstdev(r[1] for r in s),
                        ch1=st.mean(r[2] for r in s), sd1=st.pstdev(r[2] for r in s), refs=refs))
    return out


def table(n):
    print(f'\n=== sweep {n}')
    print(f"{'step':22} {'n':>3} {'ch0':>7} {'sd':>5} {'ch1':>6} {'sd':>4}  phone / mygg / panel(HA)")
    for s in steps(n):
        r = s['refs']
        print(f"{str(s['step']):22} {s['n']:3} {s['ch0']:7.1f} {s['sd0']:5.1f} {s['ch1']:6.1f} {s['sd1']:4.1f}  "
              f"{r[PHONE]} / {r[MYGG]} / {r[PANEL]}")


def superposition(n, levels):
    """Sweep 2/3 steps are (e14, e27, tradfri) brightness tuples."""
    S = {s['step']: s for s in steps(n) if isinstance(s['step'], tuple)}
    dark = S[(0, 0, 0)]
    print(f'\n=== superposition, sweep {n} (dark-subtracted; linear sensor + reliable bulbs => ratio 1)')
    for x in levels:
        singles = [(x, 0, 0), (0, x, 0), (0, 0, x)]
        if not all(k in S for k in singles + [(x, x, x)]):
            continue
        for ch in ('ch0', 'ch1'):
            a = sum(S[k][ch] - dark[ch] for k in singles)
            b = S[(x, x, x)][ch] - dark[ch]
            print(f'  x={x:3} {ch}: singles={a:7.1f} together={b:7.1f}')


def dark_levels():
    print('\n=== dark steps (ch1 dark level wanders; ch0 does not)')
    for n in (1, 2, 3, 4):
        for s in steps(n):
            name = s['step']
            if name in ((0, 0, 0),) or (isinstance(name, str) and name.startswith('dark')):
                print(f"  sweep {n} {str(name):18} ch0={s['ch0']:4.1f} ch1={s['ch1']:5.1f}")


def phone_fit(dark=3.4):
    pts = []
    for s in steps(4):
        name = s['step']
        if isinstance(name, tuple) and name[0] == 0 and name[1] == 0 and s['refs'][PHONE]:
            pts.append((s['ch0'] - dark, float(s['refs'][PHONE][0])))
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    a = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    c = my - a * mx
    print(f'\n=== phone fit, sweep 4 (TRADFRI only): phone = {a:.4f} * (ch0 - {dark}) + {c:.2f}')
    for x, y in pts:
        print(f'  ch0-{dark}={x:6.1f} phone={y:5.1f} fit={a * x + c:5.1f} resid={y - (a * x + c):+.1f}')


def replay_driver(n=4, lux_per_kcount=157, dark_x10=34):
    """Integer replay of hx3203.c v0.2 (EMA >>2, x16 fixed point, 0.75 lx hysteresis)."""
    rows, marks, _ = load(n)
    first, avg, last, rep = True, 0, 0, []
    for t, c0, _ in rows:
        avg = c0 << 4 if first else avg + (((c0 << 4) - avg) >> 2)
        ml = max(0, int((int(avg * 10 / 16) - dark_x10) * lux_per_kcount / 10))
        if first:
            last, first = (ml + 500) // 1000, False
            rep.append((t, last))
        elif abs(ml - last * 1000) >= 750:
            last = (ml + 500) // 1000
            rep.append((t, last))
    print(f'\n=== driver v0.2 replay on sweep {n}: value reported at the end of each step')
    for (t0, name), (t1, _) in zip(marks, marks[1:]):
        settled = [v for t, v in rep if t < t1][-1]
        print(f'  {str(tuple(name) if not isinstance(name, str) else name):18} {settled} lx')


if __name__ == '__main__':
    for n in (1, 2, 3, 4):
        table(n)
    superposition(2, (255, 140, 80))
    superposition(3, (255,))
    dark_levels()
    phone_fit()
    replay_driver()
