"""WP4' (PRE-REGISTRATION 2026-11-15, approved by the author): Sonnet 5.5 and Haiku 5.5 on order-service, isolation v4.

Order (after the WP2 Google arm stopped on 2026-11-15): wait for the running oracle validation (validate_oracle.py),
docker pause the kind cluster, run check_isolation.py (must be 49/49, otherwise stop), 6 pilot runs (3 per model: F1, F2,
F9, agent_mitigate arm; not analyzed; tokens from run_evidence.jsonl go to results/wp4-pilot-tokens.json; stop if a record
is missing), then run_v3.py --stages wp4-sonnet,wp4-haiku --skip-validation --validation-since <ISO> (the 111/111 gate of
the validation run starting at <ISO>; run_v3 stops if it fails), then compare_wp4.py.
  cd remediation-oracle && screen -dmS wp4 /bin/sh -c 'caffeinate -is ../.venv/bin/python -u run_wp4.py <ISO> >> ../results/logs/wp4.log 2>&1'
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ORACLE = Path(__file__).resolve().parent
REPO = ORACLE.parent
RES = REPO / "results"
PY = sys.executable
KIND = ["kind-control-plane", "kind-worker", "kind-worker2", "kind-worker3"]
PILOT = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


def validation_running():
    return subprocess.run(["pgrep", "-f", "validate_oracle.py"], capture_output=True).returncode == 0


def main():
    since = sys.argv[1]
    while validation_running():
        time.sleep(60)
    log("validation done; pausing the kind cluster")
    subprocess.run(["docker", "pause", *KIND], capture_output=True)
    r = subprocess.run([PY, "-u", "check_isolation.py"], cwd=ORACLE, capture_output=True, text=True)
    (RES / "logs").mkdir(parents=True, exist_ok=True)
    (RES / "logs" / "wp4_check_isolation.log").write_text(r.stdout + r.stderr)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    log(f"check_isolation: {last}")
    if r.returncode != 0:
        raise SystemExit("check_isolation failed; stopping")
    tokens = {}
    for name, model in PILOT.items():
        out = RES / f"wp4-pilot-{name}"
        env = dict(os.environ, SELFHEAL_ISOLATION="v4", SELFHEAL_AGENT_TIMEOUT_S="300")
        with open(RES / "logs" / f"wp4_pilot_{name}.log", "a") as f:
            subprocess.run([PY, "-u", "harness.py", "--n", "1", "--faults", "F1,F2,F9", "--arms", "agent_mitigate",
                            "--model", model, "--out", str(out)], cwd=ORACLE, env=env, stdout=f, stderr=subprocess.STDOUT)
        rows = [json.loads(x) for x in (out / "pilot_results.jsonl").read_text().splitlines() if x.strip()] \
            if (out / "pilot_results.jsonl").exists() else []
        ev = [json.loads(x) for x in (out / "run_evidence.jsonl").read_text().splitlines() if x.strip()] \
            if (out / "run_evidence.jsonl").exists() else []
        tokens[name] = [{"fault": e["problem_id"], "usage": e.get("usage")} for e in ev]
        log(f"pilot {name}: {[(r['problem_id'], r['verdict'], r['flags'].get('peek')) for r in rows]}")
        if len(rows) < 3:
            (RES / "wp4-pilot-tokens.json").write_text(json.dumps(tokens, indent=1) + "\n")
            raise SystemExit(f"pilot {name} is missing records ({len(rows)}/3); stopping")
    (RES / "wp4-pilot-tokens.json").write_text(json.dumps(tokens, indent=1) + "\n")
    log(f"starting run_v3.py --stages wp4-sonnet,wp4-haiku (validation since {since})")
    subprocess.run([PY, "-u", "run_v3.py", "--stages", "wp4-sonnet,wp4-haiku", "--skip-validation", "--validation-since",
                    since], cwd=ORACLE)
    r = subprocess.run([PY, "compare_wp4.py"], cwd=ORACLE, capture_output=True, text=True)
    (RES / "wp4-compare.txt").write_text(r.stdout + r.stderr)
    log("WP4' done; comparison in results/wp4-compare.txt")


if __name__ == "__main__":
    main()
