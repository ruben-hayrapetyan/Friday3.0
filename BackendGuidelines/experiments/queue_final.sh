#!/bin/zsh
# P8: after the learning and timing queues. E014's threshold is computed first.
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E012' queue_learn.txt 2>/dev/null && grep -q 'end E006b' queue_p4.txt 2>/dev/null; do sleep 60; done
(cd E014-missing-features && uv run python analyze.py > analysis.txt 2>&1)
echo "$(date +%T) start E017-semesters x2 load: $(uptime | sed 's/.*averages: //')" >> queue_final.txt
for i in 0 1; do (cd E017-semesters && nice -n 19 uv run python run.py --shard=$i/2 > run_shard$i.out 2>&1) & done
wait
echo "$(date +%T) end E017-semesters" >> queue_final.txt
echo "$(date +%T) start E018-weakness-hunt load: $(uptime | sed 's/.*averages: //')" >> queue_final.txt
(cd E018-weakness-hunt && nice -n 19 uv run python run.py > run.out 2>&1)
echo "$(date +%T) end E018-weakness-hunt ($?)" >> queue_final.txt
