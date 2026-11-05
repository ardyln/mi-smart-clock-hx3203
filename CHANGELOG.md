# Changelog

## v0.3-rc1 (pre-release)
- Separates LED light from daylight using the ch1/ch0 ratio. Daylight no longer reads about 3× too high.
- New module parameters: `day_lux_per_kcount`, `led_ratio_pm`, `day_ratio_pm`, `dark1_x10`, `ratio_prior_x10`.
- Known issue: dim LED light reads 9–40 % low. `dark1_x10=300` fixed this in a live test, but it isn't
  the default until it has been measured at dusk.
- Known limit, in all versions: below about 2–3 lx the driver reports 0.
- Not yet measured: dusk, and linearity above 5400 counts.

## v0.2
- Calibrated against a reference beside the clock: lux = 0.157 × (ch0 − 3.4). The ch1 / "offset" terms
  from the reference driver are dropped; they pushed all indoor readings to 0.
- ch0 smoothed over ~1 s; whole-lux reports with 0.75 lx hysteresis.
- Module parameters `lux_per_kcount` and `dark_x10` replace `lux_scale`.

## v0.1
- First working driver: `/dev/m_als_misc` for the stock MediaTek sensor HAL, loaded by Magisk at
  post-fs-data, with a boot-loop guard.
