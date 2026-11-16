#!/bin/zsh
# WP1: each argument has the form <pid>:<step>,<step>,... ; deploy, inject the fault, then run gate.py with those steps.
cd ~/srv/SREGym || exit 1
LOGDIR=~/Documents/thesis-selfheal-snapshots/sregym
GATE=/Users/user/Documents/workspace/research/thesis-selfheal-agent/sregym-oracle/gate.py
for spec in "$@"; do
  pid=${spec%%:*}
  steps=(${(s:,:)${spec#*:}})
  # A full Docker virtual disk broke the cluster mid-run (2026-11-14): stop if any node is above 95% used
  for n in kind-worker kind-worker2 kind-worker3; do
    used=$(docker exec $n df --output=pcent / | tail -1 | tr -dc 0-9)
    if (( used > 95 )); then echo "$(date +%H:%M:%S) STOP disk $n ${used}%" >> $LOGDIR/run_g1.progress; exit 2; fi
  done
  echo "$(date +%H:%M:%S) deploy $pid" >> $LOGDIR/run_g1.progress
  { time uv run main.py --problem $pid --use-external-harness ; } > $LOGDIR/$pid-deploy.log 2>&1
  echo "$(date +%H:%M:%S) gate $pid rc=$?" >> $LOGDIR/run_g1.progress
  uv run python $GATE $pid ${steps[@]} > $LOGDIR/$pid-gate.log 2>&1
  echo "$(date +%H:%M:%S) done $pid rc=$?" >> $LOGDIR/run_g1.progress
done
echo "$(date +%H:%M:%S) all done" >> $LOGDIR/run_g1.progress
