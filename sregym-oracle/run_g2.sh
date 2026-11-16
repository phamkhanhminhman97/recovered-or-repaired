#!/bin/zsh
# WP1 gate G2: 3 repeats; each repeat redeploys and reinjects every problem, then runs gate.py. Arguments: <pid>:<step>,<step>,...
cd ~/srv/SREGym || exit 1
LOGDIR=${G2_LOGDIR:-~/Documents/thesis-selfheal-snapshots/sregym/g2}
mkdir -p $LOGDIR
GATE=/Users/user/Documents/workspace/research/thesis-selfheal-agent/sregym-oracle/gate.py
# REPS selects the repeats (default all three), to resume after an interruption
for rep in ${=REPS:-1 2 3}; do
  for spec in "$@"; do
    pid=${spec%%:*}
    steps=(${(s:,:)${spec#*:}})
    for n in kind-worker kind-worker2 kind-worker3; do
      used=$(docker exec $n df --output=pcent / | tail -1 | tr -dc 0-9)
      if (( used > 95 )); then echo "$(date +%H:%M:%S) STOP disk $n ${used}%" >> $LOGDIR/progress; exit 2; fi
    done
    echo "$(date +%H:%M:%S) r$rep deploy $pid" >> $LOGDIR/progress
    { time uv run main.py --problem $pid --use-external-harness ; } > $LOGDIR/$pid-r$rep-deploy.log 2>&1
    if ! rg -q 'Fault injected for problem' $LOGDIR/$pid-r$rep-deploy.log; then
      echo "$(date +%H:%M:%S) r$rep DEPLOY_FAILED $pid" >> $LOGDIR/progress; continue
    fi
    uv run python $GATE $pid ${steps[@]} > $LOGDIR/$pid-r$rep-gate.log 2>&1
    echo "$(date +%H:%M:%S) r$rep done $pid rc=$?" >> $LOGDIR/progress
  done
done
echo "$(date +%H:%M:%S) all done" >> $LOGDIR/progress
