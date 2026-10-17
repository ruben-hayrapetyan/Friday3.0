#!/bin/zsh
# P5-P7 experiments (no timing claims), sharded over processes, at background priority.
cd "$(dirname "$0")"
run_sharded() {  # $1 = folder, $2 = shards
  echo "$(date +%T) start $1 x$2 load: $(uptime | sed 's/.*averages: //')" >> queue_learn.txt
  for i in $(seq 0 $(($2 - 1))); do
    (cd $1 && nice -n 19 uv run python run.py --shard=$i/$2 > run_shard$i.out 2>&1) &
  done
  wait
  echo "$(date +%T) end $1" >> queue_learn.txt
}
run_sharded E011-learning 5
run_sharded E013-hidden-units 5
run_sharded E014-missing-features 4
for e in E016-active-queries E015-soften-walls E012-rbm-from-data; do
  echo "$(date +%T) start $e" >> queue_learn.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_learn.txt
done
