#!/bin/zsh
# P8: after the learning and timing queues. E014's threshold is computed first.
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E012' queue_learn.txt 2>/dev/null && grep -q 'end E006b' queue_p4.txt 2>/dev/null; do sleep 60; done
(cd E014-missing-features && uv run python analyze.py > analysis.txt 2>&1)
for e in E017-semesters E018-weakness-hunt; do
  echo "$(date +%T) start $e load: $(uptime | sed 's/.*averages: //')" >> queue_final.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_final.txt
done
