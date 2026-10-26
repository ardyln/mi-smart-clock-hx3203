# Changelog

## v0.2
- Calibrated against a reference beside the clock: lux = 0.157 × (ch0 − 3.4). The ch1 / "offset" terms
  from the reference driver are dropped; they pushed all indoor readings to 0.
- ch0 smoothed over ~1 s; whole-lux reports with 0.75 lx hysteresis.
- Module parameters `lux_per_kcount` and `dark_x10` replace `lux_scale`.

## v0.1
- First working driver: `/dev/m_als_misc` for the stock MediaTek sensor HAL, loaded by Magisk at
  post-fs-data, with a boot-loop guard.
