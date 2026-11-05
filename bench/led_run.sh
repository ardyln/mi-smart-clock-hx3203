#!/bin/bash
# led_run.sh <label> <dark1_x10> [step_s]: clock + zorn loggers around one TRADFRI staircase. The parameter is set back to 155 afterwards.
L=$1; D=$2; T=${3:-60}
A="adb -s ${CLOCK:-192.168.1.44:35925}"; Z="adb -s ${ZORN:-192.168.1.36:35645}"
S=$((9*T + 15)); P=/sys/module/hx3203/parameters/dark1_x10
$Z shell 'svc power stayon true'
$A shell "su -c 'echo $D > $P; cat $P; /data/local/tmp/alslog $S 5; echo 155 > $P; cat $P'" > $L.log 2>&1 &
PA=$!
$Z shell "t=0; while [ \$t -lt $S ]; do dumpsys sensorservice | grep -A10 -E 'Ambient Light Sensor (Raw Data )?Non-wakeup: last'; sleep 1; t=\$((t+1)); done" > ${L}_zorn.log 2>&1 &
PZ=$!
sleep 6
python3 led_sweep.py marks_$L.json $T || { echo SWEEP ABORTED; $A shell "su -c 'pkill alslog'"; }
wait $PA
kill $PZ 2>/dev/null
$Z shell 'svc power stayon false'
head -1 $L.log; tail -1 $L.log; python3 led_an.py $L
