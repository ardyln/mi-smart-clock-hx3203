#!/bin/bash
# ir_run.sh <label> [cycles on off]: clock + zorn loggers around one heater square wave
L=$1; C=${2:-3}; ON=${3:-60}; OFF=${4:-60}
A="adb -s ${CLOCK:-192.168.1.44:35925}"; Z="adb -s ${ZORN:-192.168.1.36:35645}"
S=$((OFF + C*(ON+OFF) + 25))
$Z shell 'svc power stayon true'
$A shell "su -c '/data/local/tmp/alslog $S 5'" > ir_$L.log 2>&1 &
PA=$!
$Z shell "t=0; while [ \$t -lt $S ]; do dumpsys sensorservice | grep -A10 -E 'Ambient Light Sensor (Raw Data )?Non-wakeup: last'; sleep 1; t=\$((t+1)); done" > ir_${L}_zorn.log 2>&1 &
PZ=$!
sleep 8
python3 ir_heater.py marks_ir_$L.json $L $C $ON $OFF
wait $PA
kill $PZ 2>/dev/null
$Z shell 'svc power stayon false'
echo done $L; wc -l ir_$L.log ir_${L}_zorn.log
