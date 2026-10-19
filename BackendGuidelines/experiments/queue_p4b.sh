#!/bin/zsh
# Second-round timing experiments, after queue_p4, one at a time, background priority.
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E010' queue_p4.txt 2>/dev/null; do sleep 30; done
for e in E004b-penalty-scale; do
  echo "$(date +%T) start $e load: $(uptime | sed 's/.*averages: //')" >> queue_p4.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_p4.txt
done
