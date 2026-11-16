"""Validate the oracle before any agent runs. No AI calls.

Scenarios per fault:
  bug_idle : faulty release, incident load, nobody acts             -> expected: not recovered
  restart  : faulty release, incident load, app restarted twice     -> expected: temporary if the fault accumulates, else none
  fix      : faulty release, incident load, reference fix, app restarted -> expected: real recovery
  hotfix   : (F7 only) index created by hand in the DB               -> expected: temporary (round 3 fails)
  clean    : clean application, no fault                            -> expected: real recovery

Run: python3 validate_oracle.py [--reps 3] [F2 F6 ...]
Results: results/v2-oracle-validation/validation.jsonl (one line per run) plus a summary table.
"""
import argparse
import json
import sys
import time
from datetime import datetime

import fault_specs
import oracle
import sandbox
import stack

OUT_DIR = stack.ORACLE_DIR.parent / "results" / "v2-oracle-validation"


def expected(fault_id, scenario):
    if scenario in ("fix", "clean"):
        return "real"
    if scenario == "hotfix":
        return "temp"
    if scenario == "restart":
        return "temp" if fault_specs.FAULTS[fault_id]["accumulates"] else "none"
    return "none"


def run_scenario(fault_id, scenario):
    ready, pre = oracle.start_run(fault_id, with_bug=(scenario != "clean"))
    if scenario == "restart":
        for _ in range(2):
            stack.restart_app()
            stack.wait_ready(oracle.READY_TIMEOUT_S)
    elif scenario == "fix":
        sandbox.apply_reference_fix(fault_id)
        stack.compose("up", "-d", "--build", "app")
    elif scenario == "hotfix":
        stack.psql("CREATE INDEX IF NOT EXISTS items_value_hotfix ON items (value)", timeout=120)
    result = oracle.evaluate(fault_id)
    return {"ready": ready, "pre": pre, **result}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("faults", nargs="*")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--scenarios", default="bug_idle,restart,fix")
    args = ap.parse_args()
    fault_ids = args.faults or list(fault_specs.FAULTS)
    scenarios = args.scenarios.split(",")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "validation.jsonl"
    rows = []
    for rep in range(args.reps):
        for fid in fault_ids:
            scs = list(scenarios) + (["hotfix"] if fid == "F7" and "hotfix" not in scenarios else [])
            for sc in scs:
                t0 = time.time()
                try:
                    res = run_scenario(fid, sc)
                    got = oracle.verdict(res)
                except Exception as e:  # noqa: BLE001 -- record it and keep the validation batch going
                    res, got = {"error": repr(e)}, "error"
                row = {"fault": fid, "scenario": sc, "rep": rep, "expected": expected(fid, sc), "got": got,
                       "ok": got == expected(fid, sc), "seconds": round(time.time() - t0, 1),
                       "at": datetime.now().isoformat(timespec="seconds"), **res}
                rows.append(row)
                with open(out_path, "a") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{fid:<4}{sc:<9}rep{rep} du_kien={row['expected']:<5} thuc_te={got:<5} "
                      f"{'OK ' if row['ok'] else 'SAI'} v=({res.get('vong_1')},{res.get('vong_2')},{res.get('vong_3')}) "
                      f"{row['seconds']}s", flush=True)
    stack.down()
    bad = [r for r in rows if not r["ok"]]
    print(f"\nTotal: {len(rows) - len(bad)}/{len(rows)} as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
