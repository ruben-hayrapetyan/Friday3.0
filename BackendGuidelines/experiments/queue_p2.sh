#!/bin/bash
# Program 2 queue: at most two shards at a time (shared machine), nice 19, BLAS threads 1.
cd "$(dirname "$0")/.."
source experiments/env_quiet.sh
wait_for() { while pgrep -f "$1" > /dev/null; do sleep 20; done; }
wait_for "E021-durations-downstream/run.py r1"
uv run python experiments/E021-durations-downstream/run.py report > experiments/E021-durations-downstream/report_r1.txt 2>&1
for k in 0 1; do nice -n 19 uv run python experiments/E022-three-schedules/run.py r1 $k 2 > experiments/E022-three-schedules/progress_r1_$k.txt 2>&1 & done
wait
echo "E022 r1 done $(date)" >> experiments/queue_p2.txt
# then: E021 round 2 (frontier) and E024 (asking), two shards each in turn
for k in 0 1; do nice -n 19 uv run python experiments/E021-durations-downstream/run.py r2 $k 2 > experiments/E021-durations-downstream/progress_r2_$k.txt 2>&1 & done
wait
for k in 0 1; do nice -n 19 uv run python experiments/E021-durations-downstream/run.py r2b $k 2 > experiments/E021-durations-downstream/progress_r2b_$k.txt 2>&1 & done
wait
echo "E021 r2 done $(date)" >> experiments/queue_p2.txt
for k in 0 1; do nice -n 19 uv run python experiments/E024-asking-policy/run.py $k 2 > experiments/E024-asking-policy/progress_$k.txt 2>&1 & done
wait
echo "E024 done $(date)" >> experiments/queue_p2.txt
