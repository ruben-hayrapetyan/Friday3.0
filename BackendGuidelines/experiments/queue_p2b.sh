#!/bin/bash
# Program 2, second queue: E024 round 2 (p95), then E022 round 2 (ranked options). Two shards at a time, nice 19.
cd "$(dirname "$0")/.."
source experiments/env_quiet.sh
echo "queue b started $(date)" >> experiments/queue_p2.txt
for k in 0 1; do nice -n 19 uv run python experiments/E024-asking-policy/run.py r2 $k 2 > experiments/E024-asking-policy/progress_r2_$k.txt 2>&1 & done
wait
echo "E024 r2 done $(date)" >> experiments/queue_p2.txt
for k in 0 1; do nice -n 19 uv run python experiments/E022-three-schedules/run.py r2 $k 2 > experiments/E022-three-schedules/progress_r2_$k.txt 2>&1 & done
wait
echo "E022 r2 done $(date)" >> experiments/queue_p2.txt
