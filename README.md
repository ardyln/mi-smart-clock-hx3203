# Ambient light sensor for the Xiaomi Mi Smart Clock (X04G) on GSI ROMs

The Xiaomi Mi Smart Clock (X04G, MediaTek MT8167) has a light sensor that has never worked: the
fitted chip is a **TYHX HX3203** at I2C bus 0, address 0x44, but Xiaomi's kernel only carries a
driver for the EM3071X. The MediaTek sensor framework gives up at boot, and Android's LIGHT sensor
never produces a value.

This repository has a kernel module that drives the HX3203 and plugs it into the stock MediaTek
sensor HAL, packaged as a Magisk module, plus the measurements behind its calibration.

Tested on one clock: stock Xiaomi kernel `4.14.141+` (firmware 1.7.5), phh-treble Lineage 20 GSI
(Android 13), Magisk 30.7. It reports to Home Assistant through Kiosk Satellite.

## Install

1. Download `hx3203-als.zip` from [Releases](../../releases) and install it in Magisk.
2. Reboot. Android's light sensor (and anything using it: adaptive brightness, Kiosk Satellite's
   `ambient_light` sensor in Home Assistant) starts reporting lux.

The module is built for exactly this kernel (`vermagic 4.14.141+ SMP preempt mod_unload modversions
ARMv7 thumb2 p2v8`). On another kernel, rebuild it (see below) or don't install it.

**Crash guard:** `post-fs-data.sh` leaves a marker that `service.sh` removes once boot completes.
If a boot with the driver loaded never completes, the next boot skips the driver and disables the
module, so a driver bug can't trap the clock in a boot loop.

## How it works

- The I2C client `0-0044` (`compatible = "mediatek,alsps-hx3203"`) is already in Xiaomi's device
  tree, unbound. The module binds it.
- It replaces the light half of MediaTek's `alsps` framework. It registers `/dev/m_als_misc` (minor
  `ID_LIGHT` = 4) with the kernel's own `sensor_attr_register`, and serves the sysfs protocol the
  vendor HAL (`sensors.mt8167.so`) uses in `/sys/class/sensor/m_als_misc/`: `alsactive` (`"4,1"`),
  `alsbatch` (`"4,flag,delay_ns,latency_ns"`), `alsflush`, `alsdevnum`, `alscali`.
- While the HAL has the sensor enabled, it polls the chip every 200 ms (or at the HAL's rate, minimum
  100 ms), smooths both channels over about 1 s, and reports whole lux on a change of at least 0.75 lx. It
  sends the same "value+1, then value" kick after enabling as the stock framework does.
- Xiaomi's framework object (`alsps_context`, 496 bytes, laid out like MediaTek's) is left alone.
  After boot its pointer is NULL and the code that would allocate it was freed with init text
  (details in [docs/KERNEL.md](docs/KERNEL.md)). The `sensor_attr_*` / `sensor_event_*` helpers aren't exported, so they're resolved with
  `kallsyms_lookup_name`. On this Thumb-2 kernel those addresses come back with bit 0 clear and
  must be ORed with 1 before calling. The first version didn't do that and oopsed with
  "undefined instruction" at `sensor_attr_register+0x2`.
- The Magisk module loads it at `post-fs-data`, before the HAL opens `/dev/m_als_misc`. It then
  applies the owners and modes the vendor `init.sensor_1_0.rc` sets (`system:system 0660`).

No proximity sensor is registered. No proximity registers responded, and a hand in front of the
sensor changed nothing; the part looks ALS-only (see [docs/NOTES.md](docs/NOTES.md)).

## Calibration

```
ch0 = (r09 << 8) | ((r0a & 0x0f) << 4) | (r0f & 0x0f) | ((r0f & 0x30) << 12)
ch1 = (r08 << 3) | ((r0d & 0x3f) << 11) | (r0e & 7)
x0 = ch0 − 3.4
x1 = max(ch1 − 15.5, 0)
ratio = (x1 + 0.18 × 100) / (x0 + 100)
k = 0.157 at ratio ≤ 0.18, falling linearly to 0.055 at ratio ≥ 0.383
lux = k × x0
```

ch1 is more sensitive to infrared than ch0, so the ratio tells LED light (about 0.18) from daylight
(0.383). The clock gives about 2.3× more counts per lux in daylight than under this LED, and v0.2,
which used 0.157 for everything, read daylight about 3× too high. The `100` pulls dim light towards
the LED value, because ch1 is unreliable at low levels. Lux still rises steadily with light, with no
threshold.

All constants are module parameters, writable at runtime in `/sys/module/hx3203/parameters/`:
`lux_per_kcount` (157), `day_lux_per_kcount` (55), `led_ratio_pm` (180), `day_ratio_pm` (383),
`dark_x10` (34), `dark1_x10` (155) and `ratio_prior_x10` (1000).

**Dim LED light reads low by default.** Once any light reaches the sensor, ch1 sits about 20–34 counts
above zero, which is more than the 15.5 above. v0.3 then takes dim LED light for part daylight and
reads 9–40 % low, depending on the session. Setting `dark1_x10` to 300 removed this in a live test:
TRADFRI 110 / 150 / 200 / 255 gave 1 / 5 / 11 / 24 lx, matching the LED calibration. It is not the
default yet because its effect on dim daylight hasn't been measured. To try it (lost at reboot):

```
su -c 'echo 300 > /sys/module/hx3203/parameters/dark1_x10'
```

**Method.** A phone (Xiaomi 24117RK2CG) lay beside the clock facing the same way, reporting its light
sensor to Home Assistant once a minute. An IKEA TRADFRI bulb was stepped through brightness levels and
held 75 s each while a logger on the clock ([tools/alslog.c](tools/alslog.c)) read the raw channels
at 5 Hz.

| TRADFRI brightness | 0 | 40 | 60 | 110 | 150 | 200 | 255 |
|---|---|---|---|---|---|---|---|
| ch0 − 3.4 (mean) | 0 | 1.3 | 10.3 | 24.5 | 32.9 | 56.6 | 120.3 |
| phone (lx) | 4 | 5 | 6 | 8 | 10 | 14 | 23 |

Fit: `phone = 0.1565 × (ch0 − 3.4) + 4.5`, residuals ≤ 0.6 lx. The +4.5 lx is the phone's own
offset: it read 4–5 lx with every light off, while the clock's sensor read its dark level.

**End to end** (installed module → HAL → Kiosk Satellite → Home Assistant, 70 s holds): TRADFRI
0 / 110 / 200 / 255 → **0 / 4 / 11 / 22 lx**.

**Why the phone and not the MYGGSPRAY:** against the MYGGSPRAY, which sits elsewhere in the room,
the factor came out between 0.4 and 0.75 lx per count depending on which bulb was lit. The phone beside
the clock gave 0.157 consistently. Where a reference sits matters more than how good it is.

**Precision and its limits:**
- The chip resolves about 0.16 lx per count, with ±1–4 counts of noise. **The vendor HAL passes
  `word[0]` to Android as whole lux** (its `processEvent` converts without dividing), so Android and
  Home Assistant get 1 lx steps.
- The same TRADFRI setting gave ch0 between 124 and 154 at 255 across four runs (±10 %). That's the
  light, not the sensor.
- Absolute accuracy is only as good as the reference phone's sensor.
- **Below about 2–3 lx the driver reports 0**, measured against the phone under the TRADFRI. ch0 barely
  moves at those levels even though ch1 does, so this applies to every version of the driver. The
  phone's low-end scale is unverified, so treat the figure as approximate.
- Colour temperature moves ch0 about 10 % (2200 K vs 6500 K).
- The daylight factor rests on a few sessions with a phone beside the clock, and those readings
  scattered widely. Treat daylight lux as a rough figure. Dusk is unmeasured, and ch0 is only verified
  as linear up to about 5400 counts, while bright daylight on this clock reaches about 10 700.
- Infrared heaters clamp to the daylight factor. There's no reference lux to check that reading against.
- Kiosk Satellite sends the value to Home Assistant about every 30 s after an initial burst, so steps
  shorter than that show mid-transition values.
- The clock's own screen does not reach the sensor: screen brightness 1 vs 255 in a dark room
  changed nothing.

## What the HX3203 does (measured, no datasheet)

- ID register `0x00` = `0x21`. Start-up sequence (from the GL-iNet Zephyr driver):
  `01=70, 02=06, 0c=22, 16=36, 0b=gain, 01=74, 0c=22`; off: `0c=02`.
- Gain is `0x0b` bits 2:0. Settings 0–3 rise slowly and 4–7 are all about 36×, so 4 is used.
- **ch0 is linear in light** above the low end, tested up to about 5400 counts. A 149-count LED step on
  top of daylight matched the same step in the dark. Dark level 3.2–3.9 (±1.2). The first low-light
  "dead zone" reading came from KAJPLATS bulbs that didn't actually light up when switched from off
  ([bench/README.md](bench/README.md)), but a smaller one is real: starting from dark, ch0 comes up about
  26–31 counts short against ch1 and the phone, under both LED and infrared light
  ([docs/KERNEL.md](docs/KERNEL.md)).
- **ch1 only sets the LED/daylight ratio**, never the level directly. The reference driver
  subtracts `1.45 × ch1` plus an "offset" from `0x80/0x81` (7 here). On this clock that pushes every
  indoor reading below zero. ch1's dark level moved 18 → 27 → 16 within an hour with no change in
  room light and no correlation with temperature. It responds to light weakly and not repeatably
  (a plateau at 33–35 counts from TRADFRI 60 to 200 in one run, a steady rise in another). A warmer
  colour temperature raises it slightly relative to ch0.
- Register `0x02` is writable (bits 3 and 4 don't stick), but no value changed either channel. In the
  sibling HX3229 it selects the photodiode per phase; here it doesn't.
- Register `0x01`: bits 0, 1 and 3 have no visible effect, bit 2 is set last in the init sequence,
  and bit 7 shifts both channels.
- Candidates from the sibling HX3229 datasheet, untested here: `0x16` (ADC gain; the init writes `0x36`)
  and `0x17` (current gain).

### What could ch1 be?

1. **An infrared photodiode.** The jump to 27 came while a phone lay screen-off beside the clock (phones
   pulse an infrared proximity emitter then) and fell back once the phone's screen was kept on.
   Warmer light weighting it slightly more fits a red/IR-leaning response. Test: point a TV remote at
   the clock and hold a button. ch1 should jump and ch0 shouldn't.
2. **A shielded dark-reference photodiode with leakage** (the HX3229 has one). That would fit the high
   dark level but not the clear response to bright light.
3. **A channel with automatic offset re-zeroing**, alone or on top of 1 or 2. That would fit the
   plateaus and jumps.

### Open

- Dim daylight: does ch1 follow the same intercept, so that `dark1_x10` can default to 300?
- Linearity above 5400 counts.
- `0x01` bits 6:4: integration time in the HX3229 (`111` = longest, averaged 8×). If they behave the
  same here, the current `0x74` is already the maximum. Also `0x16` / `0x17`.
- The `als_level` / `als_value` tables in Xiaomi's device-tree node, and a full dump of the board's tree.
- The TV-remote test for ch1.

## Rebuild

1. Arm GNU Toolchain 10.3-2021.07 `arm-none-linux-gnueabihf`
   (md5 `87ec580b290df2febc7c476f59484635`).
2. linux-4.14.141 from kernel.org
   (sha256 `0bb9f0812326ec4554de1bea02628840e03b6664b5abfd9d8510049e43203a17`).
3. `cp panel.config linux-4.14.141/.config`, then
   `make ARCH=arm CROSS_COMPILE=<tc>/bin/arm-none-linux-gnueabihf- HOSTCFLAGS=-fcommon olddefconfig` and
   `make ... LOCALVERSION=+ modules_prepare`.
4. `cp Module.symvers linux-4.14.141/` (CRCs taken from Xiaomi's own modules), then
   `make ... LOCALVERSION=+ M=$PWD/modules/hx3203 modules`. Symbols without a CRC (`i2c_*` etc.) only
   cause a "no symbol version" warning at load on this kernel.
5. Copy `hx3203.ko` into `magisk/` and zip `module.prop post-fs-data.sh service.sh hx3203.ko META-INF`.

`panel.config` is the clock's `/proc/config.gz`.

## Repository

- `modules/hx3203/`: the driver.
- `magisk/`: the Magisk module (the release zip adds the built `hx3203.ko`).
- `tools/alslog.c`: static raw-channel logger (`alslog <seconds> <hz>`, needs `i2c-dev`). Build:
  `arm-none-linux-gnueabihf-gcc -O2 -static -march=armv7-a -mthumb -fno-use-linker-plugin -o alslog alslog.c`.
- `modules/i2cprobe/`, `modules/i2cdev/`: the presence probe and the stock `i2c-dev` built for this
  kernel, used during bring-up.
- `bench/`: raw logs, Home Assistant reference data and `analyze_sweeps.py`, which reproduces every
  number above. **Read [bench/README.md](bench/README.md) first**: some step labels don't mean what
  they say.
- `docs/KERNEL.md`: reverse-engineering notes on the kernel, device tree and sensor HAL (sensor class,
  event rings, why `/dev/sensorlist` always fails, the stock framework's context layout and globals,
  HAL behaviour). `docs/symbols.txt`: the matching kallsyms excerpt.
- `docs/NOTES.md`: lab notes from bring-up and calibration.

## License

GPL-2.0-or-later (see [LICENSE](LICENSE)). The kernel module has to stay GPLv2-compatible: it uses GPL-only
kernel symbols and is combined with the GPL-2.0-only kernel. `modules/i2cdev/i2c-dev.c` is the kernel's own file
(GPL-2.0-or-later). Register facts come from measurements and from the GL-iNet Zephyr HX3203 driver
(Apache-2.0); no datasheet for the HX3203 was available.
