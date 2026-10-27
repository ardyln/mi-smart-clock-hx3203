# Bench data

Raw measurements behind the calibration. `python3 analyze_sweeps.py` (run from this directory) reproduces every table
and the fit in the top-level README from the files here.

## Setup

- Clock: logger `tools/alslog.c` reading ch0/ch1 at 5 Hz over `/dev/i2c-0` (stock `i2c-dev` from `modules/i2cdev`),
  in parallel with the driver. Its clock ran ~1 s behind the host; `analyze_sweeps.py` corrects that.
- Lights (Home Assistant): two IKEA KAJPLATS bulbs (`kajplats_e14_ws_globe_806lm`, `kajplats_e27_ws_globe_1521lm`,
  2202–6535 K) and an IKEA TRADFRI (`0xbc8d7efffe21ed09`, dimmable only). The HA group `light.lamps` contains **all
  three**, the TRADFRI included.
- References: the bedroom MYGGSPRAY motion sensor's lux (elsewhere in the room, reports roughly once a minute) and,
  in sweep 4 only, a phone (Xiaomi 24117RK2CG) lying beside the clock facing the same way (HA app "fast while
  charging": about one update per minute).
- `ha_sweepN.json`: HA history of those entities (state, brightness, colour temperature) around each sweep.
  The clock's own HA value (`unknown_phh_treble_vanilla_ambient_light`) in sweeps 1–4 came from driver **v0.1**
  (the old formula), not the calibrated v0.2.

## Sweeps (2026-10-26/27, night, LED light only)

| | steps | hold | what the labels mean | caveats |
|---|---|---|---|---|
| `sweep1` | baseline, dark with screen 255/1/255, `lamps_b*` brightness 10–255 at 2202 K, 255 at 2700/4000/6535 K, `tradfri_b*`, `all_max_6535` | 20 s | **`lamps_*` = all three bulbs** (the group includes the TRADFRI, which ignores colour temperature); `tradfri_*` = TRADFRI alone | `all_max_6535` read the same as TRADFRI alone, so the KAJPLATS bulbs probably didn't come on. My restore at the end left the TRADFRI on (fixed by hand). |
| `sweep2` | tuples `(e14, e27, tradfri)` brightness: singles and all-three at 255/140/80, then e27 20–100 | 15 s | exact per-bulb commands, KAJPLATS at 2700 K | KAJPLATS switched **from off** with brightness in one command registered as nothing on the clock, MYGGSPRAY and phone alike, though HA said "on". Treat the KAJPLATS steps as invalid. |
| `sweep3` | TRADFRI-only and KAJPLATS steps, phone beside the clock | 18 s | same tuple format | Phone updates were throttled (3 updates), so it's unusable as a reference. KAJPLATS together read +15 counts, +84 on top of the TRADFRI. Superposition fails there, which I first misread as a sensor "dead zone". ch1 dark level was 27 here (phone screen off beside the clock). |
| `sweep4` | TRADFRI 0/40/60/80/110/150/200/255, KAJPLATS e27, e14+e27, all, dark | 75 s | KAJPLATS: turn on first, then set brightness | **The calibration sweep.** Phone beside the clock, screen kept on (Caffeine), one reading per step. First dark step includes the transition from the previous lights (sd 12.9). KAJPLATS steps still wobble (sd 6–14 counts). |

Results used in the README: the phone fit (sweep 4, TRADFRI steps only), the dark levels (all sweeps), the colour
temperature spread (sweep 1, 255 at 2202–6535 K) and the TRADFRI run-to-run spread (ch0 at 255: 137, 140, 154, 124 in
sweeps 1–4).

## Other files

- `pdsel.sh`: steps register `0x02` and logs both channels (no effect), then restores the init sequence.
- `gain_sweep.*`: gain register `0x0b` values 0–7 and others under fixed light (earlier session).
- `ps_probe.*`, `ps_hand.*`: the proximity hunt (candidate enable bits in `0x01`; hand test with bit 7 set).
- `als_calib*`, `lamp_phases.*`, `calib_panel.log`, `zz-hx3203-calib.sh`: the first, rougher calibration against
  the MYGGSPRAY (earlier session).
- `sweep*.py`: the scripts that drove the lights for each sweep. They read an HA token from `~/.config/ha-token`
  and use this home's entity IDs.
