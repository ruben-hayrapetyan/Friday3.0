#!/bin/bash
# Program 2, third queue: E023 (pick learning), then E025 (end to end; reads its config when it starts).
cd "$(dirname "$0")/.."
source experiments/env_quiet.sh
echo "queue c started $(date)" >> experiments/queue_p2.txt
for k in 0 1; do nice -n 19 uv run python experiments/E023-pick-learning/run.py $k 2 > experiments/E023-pick-learning/progress_$k.txt 2>&1 & done
wait
echo "E023 done $(date)" >> experiments/queue_p2.txt
for k in 0 1; do nice -n 19 uv run python experiments/E025-end-to-end/run.py $k 2 > experiments/E025-end-to-end/progress_$k.txt 2>&1 & done
wait
echo "E025 done $(date)" >> experiments/queue_p2.txt
