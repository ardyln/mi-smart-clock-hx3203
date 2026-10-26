#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# One-shot HX3203 light logger for calibration against HA's MYGGSPRAY sensor.
# Runs once after boot, logs the light channels for 15 minutes, unloads i2c-dev and deletes itself.
D=/data/local/tmp/hx3203
rm -f "$0"
while [ "$(getprop sys.boot_completed)" != 1 ]; do sleep 1; done
sleep 30
insmod $D/i2c-dev.ko || { echo "insmod failed" > $D/calib.log; exit 1; }
w() { i2cset -f -y 0 0x44 $1 $2 b; }
w 0x01 0x70; w 0x02 0x06; w 0x0c 0x22; w 0x16 0x36; w 0x0b 0x00; w 0x01 0x74; w 0x0c 0x22
end=$(( $(date +%s) + 900 ))
while [ "$(date +%s)" -lt "$end" ]; do
    printf "%s" "$(date +%s.%N | cut -c1-14)"
    for r in 0x08 0x09 0x0a 0x0d 0x0e 0x0f 0x80 0x81 0x87; do
        printf " %s" "$(i2cget -f -y 0 0x44 $r)"
    done
    echo
    sleep 1
done > $D/calib.log 2>&1
rmmod i2c_dev
