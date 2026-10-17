#!/bin/zsh
# P5-P7 experiments (no timing claims), one at a time, at background priority.
cd "$(dirname "$0")"
for e in E011-learning E013-hidden-units E014-missing-features E016-active-queries E015-soften-walls E012-rbm-from-data; do
  echo "$(date +%T) start $e load: $(uptime | sed 's/.*averages: //')" >> queue_learn.txt
  (cd $e && nice -n 19 uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_learn.txt
done
