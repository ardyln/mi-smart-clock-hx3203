#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# HX3203 proximity check with a hand: bit 7 of 0x01 set, sample channel registers ~2/s for 60 s.
# One root session; restores 0x01=0x74 and unloads i2c-dev at the end.
D=/data/local/tmp/hx3203
grep -q '^i2c_dev ' /proc/modules || insmod $D/i2c-dev.ko || exit 1
w() { i2cset -f -y 0 0x44 $1 $2 b; }
g() { i2cget -f -y 0 0x44 $1; }
w 0x01 0x70; w 0x02 0x06; w 0x0c 0x22; w 0x16 0x36; w 0x0b 0x04; w 0x0c 0x22; w 0x01 0xf4
t0=$(date +%s)
while [ $(( $(date +%s) - t0 )) -lt 60 ]; do
    echo "$(( $(date +%s) - t0 )) $(g 0x08) $(g 0x09) $(g 0x0a) $(g 0x0d) $(g 0x0e) $(g 0x0f) $(g 0x03) $(g 0x10) $(g 0x11) $(g 0x87)"
    sleep 0.4
done
w 0x01 0x74
rmmod i2c_dev
