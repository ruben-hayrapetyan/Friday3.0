#!/bin/zsh
# Round-2 learning experiments after the first learning queue.
cd "$(dirname "$0")"
source ./env_quiet.sh
until grep -q 'end E012' queue_learn.txt 2>/dev/null; do sleep 60; done
for e in E011b-learning-round2; do
  echo "$(date +%T) start $e x2" >> queue_learn.txt
  for i in 0 1; do (cd $e && nice -n 19 uv run python run.py --shard=$i/2 > run_shard$i.out 2>&1) & done
  wait
  echo "$(date +%T) end $e" >> queue_learn.txt
done
