#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Load the HX3203 driver before the sensor HAL starts and give its nodes the
# owners/modes the vendor init.sensor_1_0.rc sets for m_als_misc.
MODDIR=${0%/*}

# Crash guard: the marker survives only if a boot with the driver loaded never
# reached boot_completed (service.sh removes it). Then stay out of the way.
if [ -f "$MODDIR/booting" ]; then
    rm -f "$MODDIR/booting"
    touch "$MODDIR/disable"
    echo "hx3203-als: previous boot did not complete, module disabled" > /dev/kmsg
    exit 0
fi
touch "$MODDIR/booting"

grep -q '^hx3203 ' /proc/modules || insmod "$MODDIR/hx3203.ko" || exit 0

chown system:system /dev/m_als_misc
chmod 0660 /dev/m_als_misc
S=/sys/class/sensor/m_als_misc
for f in alsactive alsbatch alsflush; do
    chown system:system $S/$f
    chmod 0660 $S/$f
done
