# Xiaomi Mi Smart Clock (X04G) — HX3203 light sensor work

> Lab notes. Paths like `tyhx/`, `hx3203-ref/`, `mtk-sensors/` and `panel-ko/` refer to local material
> (datasheets, third-party sources, Xiaomi binaries) that is not published in this repository.

The bedroom panel (192.168.1.42, Magisk root, wireless adb) has an **HX3203** light sensor at I2C bus 0 address 0x44.
Xiaomi's kernel (4.14.141+, stock fw 1.7.5) only has the EM3071X driver, so the sensor never worked.

## What is here
- `panel.config` — the panel's `/proc/config.gz`.
- `Module.symvers` — symbol CRCs harvested from the vendor modules (`panel-ko/`), for modpost.
- `modules/i2cprobe` — one-shot read-only presence probe (proved 0x44 answers, 0x24 does not).
- `modules/i2c-dev` — stock i2c-dev built for the panel; loads fine, used for register work.
- `mtk-sensors/` — MediaTek sensors-1.0 framework sources/headers (Xiaomi kernels, 4.9 + 4.19; headers identical).
- `hx3203-ref/` — Zephyr (Apache-2.0) and RTOS HX3203 drivers: register map and lux formula.
- `tyhx/` — TYHX datasheets for related parts (HX3229-39B, HX32062S); not the HX3203 itself.
- `bench/` — measurement scripts and logs (calibration, gain sweep, proximity tests).
- `modules/hx3203/` — **the driver** (`hx3203.c`, built `hx3203.ko`).
- `magisk/` + `hx3203-als.zip` — Magisk module that loads it at post-fs-data (installed on the panel 2026-10-26).

## Rebuilding the module tree (deleted to save space; ~1.6 GB)
1. Arm GNU Toolchain 10.3-2021.07 `arm-none-linux-gnueabihf` (developer.arm.com; md5 87ec580b290df2febc7c476f59484635).
2. linux-4.14.141 from kernel.org (sha256 0bb9f0812326ec4554de1bea02628840e03b6664b5abfd9d8510049e43203a17).
3. `cp panel.config linux-4.14.141/.config`, then
   `make ARCH=arm CROSS_COMPILE=<tc>/bin/arm-none-linux-gnueabihf- HOSTCFLAGS=-fcommon olddefconfig`
   and `... LOCALVERSION=+ modules_prepare` (gives vermagic `4.14.141+ SMP preempt mod_unload modversions ARMv7 thumb2 p2v8`).
4. `cp Module.symvers linux-4.14.141/` and build modules with `make ... LOCALVERSION=+ M=<dir> modules`.
   Missing CRCs (i2c_*, etc.) only warn at load ("no symbol version") on this kernel.

## HX3203 facts (measured)
- ID reg 0x00 = 0x21. Start-up: 01=70, 02=06, 0c=22, 16=36, 0b=gain, 01=74, 0c=22.
- Gain = reg 0x0b bits 2:0; 0..3 small steps, 4..7 all ~36× → use 4.
- ch0 = (r09<<8)|((r0a&0xf)<<4)|(r0f&0xf)|((r0f&0x30)<<12); ch1 = (r08<<3)|((r0d&0x3f)<<11)|(r0e&7);
  offset = ((r81&1)<<4)|(r80>>4) (=7 here); lux ≈ k·(ch0 − offset − 1.45·ch1), k≈1.35 (rough, vs MYGGSPRAY).
- Proximity: no PS registers (03, 10–15 stay 0); 0x01 bit 7 changes channel behaviour but a hand test showed
  no reaction. Probably an ALS-only part. Open: TYHX datasheet; physical check for an IR LED.

## Driver (option A)
`hx3203.ko` binds the unbound I2C client `0-0044` (`mediatek,alsps-hx3203`) and stands in for the light half of the
MTK alsps framework: it registers `m_als_misc` (minor ID_LIGHT=4) through the kernel's `sensor_attr_register`,
serves `alsactive` ("4,1"), `alsbatch`, `alsflush`, `alsdevnum`, `alscali` in `/sys/class/sensor/m_als_misc/`, and
polls the chip (200 ms) while enabled. Xiaomi's `alsps_context` (496 bytes, not the upstream layout) is not touched.
Helpers come from `kallsyms_lookup_name` — **set bit 0 on those addresses** (Thumb-2 kernel); without it the first
call oopsed ("undefined instruction" at `sensor_attr_register+0x2`, panel rebooted once).

Loaded by the Magisk module `hx3203-als` (`magisk/`, `hx3203-als.zip`) at post-fs-data, before the vendor HAL opens
`/dev/m_als_misc`; it applies the vendor rc's owners/modes. Crash guard: a `booting` marker removed at boot_completed;
if still present next boot, the module disables itself.

### v0.2 calibration (2026-10-27, night, LED light only)
- `lux = lux_per_kcount/1000 · (ch0 − dark_x10/10)`, defaults 157 and 34; both writable in
  `/sys/module/hx3203/parameters/`. ch0 smoothed by an EMA (~1 s); reports on a ≥0.75 lx change, rounded.
- Reference: a phone (24117RK2CG) beside the panel, same direction, HA app "fast while charging" (1 update/min).
  phone = 0.1565·(ch0 − 3.4) + 4.5 over 0–23 lx, residuals ≤0.6 lx (tradfri ladder 40–255). The +4.5 is the phone's own
  offset (reads 4–5 lx with all lights off).
- End to end via HA after install (70 s holds): tradfri 0/110/200/255 → 0/4/11/22 lx. Run-to-run spread of the same
  tradfri level is ±10 % in raw ch0 (124–154 at 255), so that is the repeatability of the scene, not the driver.
- Resolution: ~0.16 lx/count, noise ±1–4 counts. **The vendor HAL passes `word[0]` as whole lux** (`processEvent`
  converts without dividing), so Android/HA get 1 lx steps.
- Kiosk Satellite sends the light value to HA about every 30 s after an initial burst; test steps must be held >60 s.
- Not yet tested: daylight / IR-rich light (ch0 may need IR correction there), CCT effect is ~10 % (2200→6500 K).

### ch0 / ch1 / registers (what is known)
- Dark: ch0 3.3–3.9 (±1.2), not affected by the panel's own screen. ch0 is linear in light (see above); the earlier
  "dead zone" idea came from the KAJPLATS bulbs, which behave erratically when switched from off (±5–14 count wobble,
  different results for the same command) — use the tradfri for tests. `light.lamps` includes the tradfri.
- ch1 is not used. Its dark level moved 18 → 27 → 16 with no change in room light and no CPU-temperature correlation
  (27 while the phone lay beside the panel screen-off; 16 once the phone screen was kept on). Light response is weak
  and not repeatable (plateau at 33–35 for tradfri 60–200 in one run, steady rise in another).
- Reg 0x02 is writable (bits 3/4 don't stick) but no value changed either channel → not a PD selector here
  (unlike the HX3229 sibling, whose register map does not carry over).
- Reg 0x01: init 0x70 → 0x74 (bit 2 = enable?). Bits 0/1/3 no effect; bit 7 shifts channels. HX3229 hint: bits 6:4 =
  integration time (111 = longest, avg 8×) — untested here. Next: step bits 6:4 under a fixed tradfri level.

## Original driver plan (superseded)
- The MTK alsps framework tore itself down at boot (EM3071X failed): `alsps_context_obj` = NULL, and
  `alsps_probe`/`alsps_real_driver_init`/`alsps_context_alloc_object` were inlined into `__init alsps_init` (freed).
- Exported only: `alsps_driver_add`, `ps_report_interrupt_data`. Others (`als_register_*`, `als_data_report`, ...)
  exist in kallsyms and can be resolved with `kallsyms_lookup_name`.
- Steps: find `&alsps_context_obj` by disassembling `als_data_report` (0xc0518d7c) in the identical kernel image
  (`~/Downloads/clock/boot.img`, kernel at gzip offset in the zImage); in the module, rebuild the context like
  `alsps_context_alloc_object` (MTK source), set the pointer, register an i2c driver for `mediatek,alsps-hx3203`,
  register als control/data paths, report from the driver's own timer (`is_report_input_direct`).
- Load from Magisk `post-fs-data.d` (before the sensor HAL starts). Worst case of a bug is a kernel crash/reboot.

## Panel etiquette
1 GB RAM and heavy swap. Run each job as **one** `su` session (every `su` call starts the Magisk app).
No polling loops over adb.
