#!/bin/zsh
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E006b' queue_p4.txt 2>/dev/null; do sleep 30; done
for e in E009b-warm-churn; do
  echo "$(date +%T) start $e load: $(uptime | sed 's/.*averages: //')" >> queue_p4.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_p4.txt
done
