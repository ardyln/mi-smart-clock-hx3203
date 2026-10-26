#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Step HX3203 reg 0x02 (PD selection on the sibling HX3229) and log mean ch0/ch1, then restore the driver's init.
cd /data/local/tmp/hx3203
w() { i2cset -f -y 0 0x44 $1 $2 b; }
echo "start r02=$(i2cget -f -y 0 0x44 0x02)"
for v in 0x06 0x04 0x02 0x00 0x16 0x26 0x46 0x0e 0x06; do
    w 0x02 $v; sleep 2
    rb=$(i2cget -f -y 0 0x44 0x02)
    ./alslog 3 5 | awk -v v=$v -v rb=$rb '{a+=$2;b+=$3;n++} END{printf "02=%s rb=%s ch0=%.1f ch1=%.1f\n", v, rb, a/n, b/n}'
done
w 0x01 0x70; w 0x02 0x06; w 0x0c 0x22; w 0x16 0x36; w 0x0b 0x04; w 0x01 0x74; w 0x0c 0x22
echo "restored r01=$(i2cget -f -y 0 0x44 0x01) r02=$(i2cget -f -y 0 0x44 0x02) r0b=$(i2cget -f -y 0 0x44 0x0b)"
