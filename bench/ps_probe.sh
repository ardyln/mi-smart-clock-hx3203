#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# HX3203 proximity hunt: try candidate enable bits in reg 0x01 and dump which registers change.
# One root session, ~20 dumps; restores 0x01=0x74 and unloads i2c-dev at the end.
D=/data/local/tmp/hx3203
grep -q '^i2c_dev ' /proc/modules || insmod $D/i2c-dev.ko || exit 1
w() { i2cset -f -y 0 0x44 $1 $2 b; }
dump() { i2cdump -f -y 0 0x44 | sed -n '2,3p;9,10p' | cut -c5-52 | tr '\n' ' '; echo; }
w 0x01 0x70; w 0x02 0x06; w 0x0c 0x22; w 0x16 0x36; w 0x0b 0x04; w 0x01 0x74; w 0x0c 0x22
sleep 1
echo "baseline 0x01=0x74: $(dump)"
for v in 0x7c 0xf4 0xfc 0x75 0x76 0x77 0x7d 0x7e 0x7f 0xff; do
    w 0x01 $v
    sleep 1
    echo "0x01=$v: $(dump)"
    sleep 1
    echo "0x01=$v: $(dump)"
done
w 0x01 0x74
rmmod i2c_dev
