#!/bin/zsh
# P4 timing experiments, after P3, one at a time, at background priority (the machine is shared).
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E006' queue_p3.txt 2>/dev/null; do sleep 30; done
for e in E007-samplers E008-move-ablation E009-warm-determinism E010-diversity-calibration; do
  echo "$(date +%T) start $e load: $(uptime | sed 's/.*averages: //')" >> queue_p4.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_p4.txt
done
