# Reverse-engineering notes: kernel, device tree and sensor HAL

Everything here was read from the clock itself (stock Xiaomi firmware 1.7.5 kernel, phh-treble Lineage 20 GSI)
or from the decompressed kernel `Image` of the stock `boot.img`. No Xiaomi kernel source for this device was
found. Addresses are kernel virtual addresses of this exact build. Field and function names come from
MediaTek's published sensors-1.0 sources where the disassembly matches them.

## Method

- **Symbols:** `/proc/kallsyms` with `kptr_restrict` temporarily set to 1 (stock value 2, restored afterwards).
  `CONFIG_KALLSYMS_ALL` is off, so only functions are listed; data addresses below come from disassembly.
  [symbols.txt](symbols.txt) has the relevant excerpt.
- **Code:** the gzip payload of the stock `boot.img` kernel, decompressed to `Image` (16.7 MB) and disassembled
  with `objdump -D -b binary -m arm -M force-thumb --adjust-vma=0xc0008000`. Text runs from `_stext 0xc0100000` to
  `_etext 0xc0a00000`, init text from `0xc0e002e0` to `0xc0e49648`. Init text is freed after boot but is still in
  the image.
- **Live checks:** reads of `/proc/device-tree`, `/sys/bus/i2c`, `/dev`, `/proc/devices`, the HAL binaries
  (`objdump -d`, `strings`), and a one-shot read-only I2C presence probe module (`modules/i2cprobe`).

## Kernel build

| | |
|---|---|
| Release | `4.14.141+`, vermagic `4.14.141+ SMP preempt mod_unload modversions ARMv7 thumb2 p2v8` |
| ISA | ARMv7, `CONFIG_THUMB2_KERNEL=y`: function addresses from kallsyms have bit 0 **clear**; set it before calling through a pointer (the first driver build oopsed with "undefined instruction" at `sensor_attr_register+0x2`) |
| Modules | `CONFIG_MODVERSIONS=y`, no module signing enforced. Symbol CRCs for linking were taken from Xiaomi's own `.ko` files (`Module.symvers`); symbols without a CRC load with a "no symbol version" warning |
| `kallsyms_lookup_name` | exported (`EXPORT_SYMBOL_GPL`) |
| HZ | 300 (the alsps timers compute `jiffies + delay_ms / 3`) |
| Sensor config | `CONFIG_MTK_SENSOR_SUPPORT`, `CONFIG_MTK_SENSORS_1_0`, `CONFIG_CUSTOM_KERNEL_ALSPS`, `CONFIG_MTK_EM3071X`, `CONFIG_MTK_HWMON`; no `CONFIG_NANOHUB` (so the polling / `*_enable_and_batch` paths are compiled) |
| I2C | `CONFIG_I2C_CHARDEV` not set (no `/dev/i2c-*` unless `modules/i2cdev` is loaded) |

`panel.config` in the repository root is the clock's `/proc/config.gz`.

## Device tree and I2C

- The DTB inside the kernel (`boot.img` offset `0x704cb0`, 42 311 bytes; also at `0x800840`) is the generic MT8167
  tree. In it, `/soc/i2c@11009000` (`mediatek,mt8167-i2c`) is `disabled` and has no sensor child. It does contain
  `/soc/als_ps@0` (`compatible = "mediatek,als_ps"`), the platform device for the framework's `als_ps_driver`.
- The board nodes come from an overlay that isn't available offline. As seen at runtime under
  `/proc/device-tree/soc/i2c@11009000/alsps@44`:
  - `compatible = "mediatek,alsps-hx3203"`
  - `i2c_addr = <0x24>` (the **EM3071X** address, although the node is `@44`), `i2c_num = <0>`
  - `interrupts = <10 8>` (EINT 10, level-low), `interrupt-parent = <0x17>`
  - `alsps-supply = <0x39>` (vgp2)
  - `is_batch_supported_als = <0>`, `is_batch_supported_ps = <0>`
  - `als_level`, `als_value`: present (lux tables); not decoded yet.
  - A full dump (`/sys/firmware/fdt`) is still to be taken.
- The kernel's `get_alsps_dts_func` (`0xc0517228`) reads these property names: `i2c_num`, `i2c_addr`, `power_id`,
  `power_vol`, `als_level`, `als_value`, `polling_mode_ps`, `polling_mode_als`, `ps_threshold_high`,
  `ps_threshold_low`, `is_batch_supported_ps`, `is_batch_supported_als`.
- I2C bus 0 has two clients: `0-0024` (for the EM3071X; nothing answers at 0x24) and `0-0044`, name `alsps-hx3203`.
  The HX3203 answers at 0x44 with ID `0x21`. Before this driver, `0-0044` had no driver bound.

## Stock sensor framework in this kernel

Function symbols (all in [symbols.txt](symbols.txt)):

```
c05170e4 get_accel_dts_func ... c05178a0 get_accelgyro_dts_func, c0517228 get_alsps_dts_func
c051798c sensor_attr_open        c0517a80 sensor_attr_register    c0517b34 sensor_attr_deregister
c0517ba0 sensor_input_event      c0517cac sensor_event_read       c0517e08 sensor_event_poll
c0517e48 sensor_event_register   c0517f20 sensor_event_deregister
c0517f40 sensorlist_open         c0517f44 sensorlist_read         c0517fdc sensor_to_handle
c0518018 sensorlist_register_deviceinfo
c0518080 als_ps_remove ... c05192e8 alsps_factory_unlocked_ioctl   (alsps.c, see below)
init:  c0e29bcc sensor_attr_init   c0e29c44 (sensor_event init)   c0e29c70 sensorlist_init
       c0e29cb4 alsps_init         c0e29e70 AAL_init              c0e29e94 em3071x_init
```

### sensor_attr (the `m_*_misc` character devices)

- `sensor_attr_init`: `__class_create("sensor")` → stored at `0xc111be9c`. `__register_chrdev(0, 0, 256, "sensor",
  fops)` → major stored at `0xc0f98cdc + 0x1c` (251 on the clock). It prints `<HWMSEN> unable to get major %d for
  misc devices` on failure.
- `struct sensor_attr_t` matches MediaTek's header: `minor` @0 (u8), `name` @4, `fops` @8, `list` @12,
  `parent` @20, `this_device` @24.
- `sensor_attr_register(misc)`: takes the mutex at `0xc0f98cdc`, walks the list (head at `+0x14`), returns `-EBUSY`
  if the minor is taken. Otherwise it calls `device_create(class, misc->parent, MKDEV(major, minor), misc, "%s",
  name)`, stores the result in `this_device`, adds the entry to the list, then **tail-calls
  `sensor_event_register(minor)`**, which allocates the event ring. A replacement driver gets its ring for free.
- `sensor_attr_deregister`: removes from the list, `device_destroy`, then `sensor_event_deregister(minor)`.
- `sensor_attr_open` swaps in the registered `fops`, like `misc_open`.
- Resulting node: `/dev/m_als_misc`, char `251:4`, SELinux `u:object_r:m_als_misc_device:s0`, created `root 0600`.
  The vendor `init.sensor_1_0.rc` (`on post-fs-data`) does `chmod 0660` / `chown system system` on it and on
  `/sys/class/sensor/m_als_misc/{alsactive,alsdelay,alsbatch,alsflush}`.

### sensor_event (event ring per handle)

- `struct sensor_event` (packed, 36 bytes): `int64 time_stamp` @0, `int8 handle` @8, `int8 flush_action` @9
  (0 data, 1 flush, 2 bias, 3 cali, 4 temp, 5 test), `int8 status` @10, `int8 reserved` @11, `int32 word[6]` @12.
- `sensor_input_event(handle, ev)` copies the event into the handle's ring under a spinlock and wakes readers. It
  does not set `time_stamp`. A full ring logs ` input buffull, handle:%d, head:%d, tail:%d`.

### sensorlist (`/dev/sensorlist`): always fails

- Data at `0xc111bea4`: 7 × `char name[16]` (all initialised to `"NULL"`), then a "ready" word at `+0x70` and a
  spinlock at `+0x74`.
- Sensor ID → slot (`sensor_to_handle`, `sensorlist_register_deviceinfo`): ID 0 (accel) → 0, 3 (gyro) → 1, 1 (mag)
  → 2, **4 (light) → 3**, 7 (proximity) → 4, 5 (pressure) → 5, 71 → 6.
- `sensorlist_read` returns `-EINVAL` unless the ready word is non-zero and `count >= 16`. Otherwise it copies
  `min(count, 112)` bytes under the spinlock (`-EFAULT` if the copy fails).
- `sensorlist_init` is the only code that writes the ready word, and it writes **0** after `misc_register`
  succeeds. No other code in the image touches that address. So `/dev/sensorlist` (misc `10:125`, `root 0600`,
  `sensorlist_device`) always fails with `EINVAL` (confirmed on the clock).
- Consequence: the HAL falls back to its built-in list ("read /dev/sensorlist fail we use defaultsensorlist"),
  which advertises LIGHT and PROXIMITY. `dumpsys sensorservice` listed both before any driver existed.

### alsps.c (Xiaomi's variant of MediaTek's framework)

- `alsps_init` (`__init`, freed after boot) has `alsps_probe`, `alsps_context_alloc_object` and
  `alsps_real_driver_init` inlined. It `kzalloc`s **0x1f0 (496) bytes**, initialises the object, and stores it in
  **`alsps_context_obj` at `0xc111bf20`**. It then calls `init()` (offset 4 of `struct alsps_init_info`) for each
  of the 5 slots of **`alsps_init_list` at `0xc111bf24`**. If every init fails, it prints `alsps real driver init
  fail`, `kfree`s the object, sets `alsps_context_obj = NULL` and returns `-ENODEV`. That's what happens on this
  clock (EM3071X absent), so after boot the framework has no context and no code left to make one.
- Other globals: `pltfm_dev` at `0xc111bf1c` (set by `als_ps_probe`), `last_als_report_data` at `0xc0f98d9c`.
- **Context layout.** Offsets seen in the disassembly all match MediaTek's `struct alsps_context` for 32-bit ARM
  with this config (no lockdep, `CONFIG_MUTEX_SPIN_ON_OWNER`):

  | offset | field | init value |
  |---|---|---|
  | 0x04 | `als_mdev.minor` | |
  | 0x3c | `report_ps` work (`func` @0x48 = `ps_work_func`) | |
  | 0x4c | `report_als` work (`func` @0x58 = `als_work_func`) | |
  | 0x5c | `alsps_op_mutex` | |
  | 0x70 | `timer_als` (`expires` @0x78, `function` @0x7c = `als_poll`, `data` @0x80) | |
  | 0x88 | `timer_ps` (`expires` @0x90, `function` @0x94 = `ps_poll`, `data` @0x98) | |
  | 0xa4 / 0xa8 / 0xac | `delay_als` / `delay_ps` / `wake` | 200 / 200 / 0 |
  | 0x174 | `ps_ctl.batch` | |
  | 0x189 | `ps_ctl.is_support_batch` | |
  | 0x19c–0x1a1 | first-data / polling-run / batch flags | false |
  | 0x1a3 | `is_get_valid_als_data_after_enable` | |
  | 0x1a4 / 0x1ac | `als_power` / `als_enable` | 0 |
  | 0x1b8 / 0x1c0 | `als_delay_ns` / `als_latency_ns` | −1 |
  | 0x1d8 / 0x1dc | `ps_power` / `ps_enable` | 0 |
  | 0x1e0 / 0x1e8 | `ps_delay_ns` / `ps_latency_ns` | −1 |

- **Xiaomi additions:** `als_data_report_t(value, status, int64 ts)`, `rgbw_data_report_t`, `ps_data_report_t` put a
  timestamp into the event. `als_data_report(v, s)` is `als_data_report_t(v, s, 0)`. On the first report after
  enable (flag @0x1a3) it sends `value + 1`, then `value` when it differs from `last_als_report_data`.
- Exported: `alsps_driver_add`, `ps_report_interrupt_data` (`EXPORT_SYMBOL_GPL`). Everything else (`als_*`,
  `ps_*`, `sensor_*`) is resolvable with `kallsyms_lookup_name`, but `als_register_*` dereference the NULL context.
- `em3071x` driver: probe/ALS/PS/EINT functions present (`em3071x_i2c_probe`, `em3071x_read_als`, ...), registered
  through `alsps_driver_add`.

**Why the replacement driver doesn't reuse this:** the context pointer is NULL after boot, and the code that
allocates and wires it was freed with init text. Rebuilding the context in a module and patching
`alsps_context_obj` (address above) would work in principle. Registering a fresh `m_als_misc` through
`sensor_attr_register` was simpler and touches no framework state.

## Vendor sensor HAL

- Service `sensors-hal-1-0` → `/vendor/bin/hw/android.hardware.sensors@1.0-service-mediatek` (user `system`, groups
  `system readproc`), impl `android.hardware.sensors@1.0-impl-mediatek.so` → `/vendor/lib/hw/sensors.mt8167.so`
  (MediaTek `vendor/mediatek/proprietary/hardware/sensor/sensors-1.0`).
- Light path: opens `/dev/m_als_misc` when the HAL starts (`AmbiLightSensor` constructor), so the device must exist
  before the HAL starts; loading the module later does nothing until the HAL restarts. It controls the sensor
  through `/sys/class/sensor/m_als_misc/`: `alsactive` (`"%d,%d"` = handle 4, on/off), `alsbatch`
  (`"%d,%d,%lld,%lld"`), `alsflush`.
- `AmbiLightSensor::processEvent` reads `time_stamp` (@0/@4), `handle` (@8), `flush_action` (@9) and converts
  `word[0..3]` with `vcvt.f32.s32`, **with no division**. Android therefore gets whole lux. A "divisor" read back
  from `alsactive` has no effect on the value.
- Event time stamps: the stock framework sends 0, and so does this driver. Values reach Android and Home Assistant;
  the HAL's handling of a zero time stamp wasn't examined further.
- Other HAL paths seen in `strings`: `/dev/m_{acc,mag,gyro,ps,baro,hmdy,pedo,act,situ,step_c,fusion,bio}_misc`, the
  matching `/sys/class/sensor/m_*_misc/`, `/dev/sensorlist`, `/mnt/vendor/nvcfg/sensor`, `/data/vendor/sensor`.

## HX3203 register notes (beyond the README)

- The GL-iNet Zephyr driver computes `ch0` with `(r0f & 0x30) << 16`; bits 5:4 of `0x0f` are ch0 bits 17:16, so the
  shift is **12**. Its "offset" (`0x80`/`0x81`, 7 here) and `1.45 × ch1` correction don't fit this clock (README).
- Sibling HX3229 (TYHX datasheet; different register map): `0x01[6:4]` integration time, `0x02` photodiode
  selection per phase (visible / IR / shielded dark), `0x16` ADC gain, `0x17` current gain. On the HX3203, `0x02`
  doesn't select photodiodes (no effect on either channel); `0x01`, `0x16` and `0x17` are untested here.
