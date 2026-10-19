#!/bin/zsh
cd "$(dirname "$0")"
source ./env_quiet.sh
echo "$(date +%T) start E013b-gated-units x2" >> queue_learn.txt
for i in 0 1; do (cd E013b-gated-units && nice -n 19 uv run python run.py --shard=$i/2 > run_shard$i.out 2>&1) & done
wait
echo "$(date +%T) end E013b-gated-units" >> queue_learn.txt
