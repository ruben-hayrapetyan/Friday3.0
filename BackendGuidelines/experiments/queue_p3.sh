#!/bin/zsh
# Runs the P3 experiments one after another (never in parallel: timings must not compete).
cd "$(dirname "$0")"
until grep -q '^done' E002-baseline-tuning/progress.txt 2>/dev/null; do sleep 20; done
for e in E003-strict-qubo E004-representations E005-deadline-guarantee E006-stages; do
  echo "$(date +%T) start $e" >> queue_p3.txt
  (cd $e && uv run python run.py > run.out 2>&1)
  echo "$(date +%T) end $e ($?)" >> queue_p3.txt
done
