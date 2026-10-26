#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
MODDIR=${0%/*}
until [ "$(getprop sys.boot_completed)" = 1 ]; do sleep 5; done
rm -f "$MODDIR/booting"
