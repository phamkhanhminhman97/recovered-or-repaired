"""Check the G2 gate logs (WP1, SREGym): compare each gate.py step with the expected result for each problem.

  python3 sregym-oracle/check_g2.py [log directory]   # default results/sregym-gate/g2-svelte
Logs: <problem>-r<repeat>-gate.log, one JSON line per step. Design and result table: docs/sregym-design.md section 8.
"""
import json
import re
import sys
from pathlib import Path

F, T = False, True
# Step sequence in run_g2.sh: faulty, restart, workaround, rounds 2/3, fix, rounds 2/3 (False = the oracle must fail)
EXPECTED = {
    "service_wrong_pod_selection_hotel_reservation": [F, F, T, F, T, T],
    "kafka_poison_pill_hol_block": [F, F, T, F, T, T, T],
    "cronjob_sidecar_blocks_completion_hotel_reservation": [F, T, T, T],
    "secret_rotation_stale_env_credentials_astronomy_shop": [F, T, T, T, T, F, T, T, T, T],
    "finalizer_deadlock_controller_hotel_reservation": [F, F, T, T, T],
    "internal_traffic_policy_local_astronomy_shop": [F, F, T, T, T, T, T, T],
    "namespace_memory_limit": [F, F, T, T],
    "search_rate_retry_collapse_hotel_reservation": [F, F, F, T, T, T],
}


def main():
    logdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "results/sregym-gate/g2-svelte"
    for pid, exp in EXPECTED.items():
        ok, mismatches = 0, []
        for f in sorted(logdir.glob(f"{pid}-r*-gate.log")):
            lines = [json.loads(x) for x in f.read_text().splitlines() if x.startswith("{")]
            got = [x["success"] for x in lines]
            if got == exp:
                ok += 1
            else:
                rep = re.search(r"-r(\d+)-", f.name).group(1)
                mismatches.append((rep, [(x["step"], x["success"]) for x, e in zip(lines, exp) if x["success"] != e]))
        print(f"{pid}: {ok}/{ok + len(mismatches)} khop")
        for rep, m in mismatches:
            print(f"   lan {rep} lech: {m}")


if __name__ == "__main__":
    main()
