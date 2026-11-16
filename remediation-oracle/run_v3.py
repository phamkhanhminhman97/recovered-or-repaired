"""Single entry point of the v3 batch (2026-10-22), following PRE-REGISTRATION.md. Order:
  1. oracle validation gate (validate_oracle.py, 37 scenarios x 3 = 111 rows): passes when every row matches expectation
  2. Haiku 5.5 N=10, 5 arms (results/v3-haiku55-main) + gates: peek <= 5% of AI runs, idle does not recover, infra < 5%
  3. Gemini N=5, three AI arms (results/v3-gemini-main) + the same gates
  4. analysis.py for each set (needs numpy, scipy: run with the venv Python, see requirements.txt)
A failed gate is only recorded and does not stop the batch (PRE-REGISTRATION 2026-10-22).
Status: results/logs/pipeline_status.json,
log: results/logs/pipeline.log, output of each step: results/logs/<step>.log.

Run (in tmux, machine on power, lid open):
  caffeinate -is python -u run_v3.py [--stages haiku,gemini] [--skip-validation --validation-since <ISO>]

2026-11-12: the shared parts of run_pipeline.py (the v2 driver, since removed) were merged here and logs moved to
results/logs/. The gate criteria are unchanged word for word. Steps live in the STAGES table (--stages replaces the old
--gemini-only / --stop-after-haiku).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ORACLE = Path(__file__).resolve().parent
RESULTS = ORACLE.parent / "results"
LOGS = RESULTS / "logs"
STATUS = LOGS / "pipeline_status.json"
LOG = LOGS / "pipeline.log"
VALIDATION = RESULTS / "v2-oracle-validation" / "validation.jsonl"  # name kept from v2; also holds the v3 validation runs
N_VALIDATION_ROWS = 111  # 37 scenarios x 3 repeats


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def status(stage, state, detail=""):
    LOGS.mkdir(parents=True, exist_ok=True)
    data = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    data[stage] = {"state": state, "detail": detail, "at": datetime.now().isoformat(timespec="seconds")}
    data["current"] = stage
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log(f"{stage}: {state} {detail}")


def gate_validation(since):
    status("validation", "running")
    rows = [json.loads(l) for l in VALIDATION.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["at"] >= since]
    bad = [f"{r['fault']}/{r['scenario']}/rep{r['rep']}: du kien {r['expected']}, thuc te {r['got']}" for r in rows if not r["ok"]]
    if len(rows) < N_VALIDATION_ROWS or bad:
        status("validation", "FAILED", f"{len(rows)} dong, sai: {bad[:10]}")
        return False
    status("validation", "passed", f"{len(rows)}/{len(rows)} as expected")
    return True


def run_harness(stage, args, env=None, retries=3):
    for attempt in range(1, retries + 1):
        status(stage, "running", f"lan {attempt}")
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True)
        r = subprocess.run([sys.executable, "-u", "harness.py", *args], cwd=ORACLE, env=env,
                           stdout=open(LOGS / f"{stage}.log", "a"), stderr=subprocess.STDOUT)
        if r.returncode == 0:
            return True
        log(f"{stage}: harness exited with code {r.returncode}, continuing (resume)")
        time.sleep(30)
    status(stage, "FAILED", "harness failed 3 times in a row")
    return False


def gate_pilot(out, stage):
    rows = [json.loads(l) for l in (out / "pilot_results.jsonl").read_text().splitlines() if l.strip()]
    peek = [r for r in rows if r["flags"].get("peek")]
    idle_pass = [r for r in rows if r["arm"] == "idle" and r["verdict"] != "none"]
    infra = [r for r in rows if not r["flags"].get("app_ready_before_action") and r["problem_id"] != "F1"]
    problems = []
    ai_rows = [r for r in rows if r["arm"].startswith("agent")]
    if len(peek) > 0.05 * max(1, len(ai_rows)):
        problems.append(f"{len(peek)}/{len(ai_rows)} AI runs with peek")
    if idle_pass:
        problems.append("idle recovered unexpectedly: " + ", ".join(f"{r['problem_id']}/run{r['run_index']}={r['verdict']}" for r in idle_pass))
    if len(infra) >= 0.05 * len(rows):
        problems.append(f"loi ha tang {len(infra)}/{len(rows)}")
    if problems:
        status(stage, "FAILED", "; ".join(problems))
        return False
    status(stage, "passed", f"{len(rows)} runs, peek {len(peek)}/{len(ai_rows)}, idle did not self-recover, infra {len(infra)}")
    return True


def analyse(out):
    r = subprocess.run([sys.executable, "analysis.py", str(out)], cwd=ORACLE, capture_output=True, text=True)
    if r.returncode != 0:
        # 2026-11-07: macOS Python lacks numpy, so this step failed silently; it now reports FAILED so it is not missed.
        status(f"analysis_{out.name}", "FAILED", "rerun with a Python that has numpy/scipy (requirements.txt): " + r.stderr[-300:])
    else:
        log(f"analysis {out.name}: done")


AI_ARMS = "agent_mitigate,agent_remediate,agent_free"
# Each step: result directory, model, N, arms, agent time limit (s). Run order = order in --stages.
# Add a step only after it is fixed in PRE-REGISTRATION.md.
STAGES = {
    "haiku": dict(stage="v3_haiku55", out="v3-haiku55-main", model="claude-haiku-5-5", n=10, arms=None, timeout_s=300),
    "gemini": dict(stage="v3_gemini", out="v3-gemini-main", model="gemini-3.8-flash", n=5, arms=AI_ARMS, timeout_s=300),
    # E1 (PRE-REGISTRATION 2026-11-12): Gemini with a 900 s limit, to remove most timeouts of v3-gemini-main
    "gemini-t900": dict(stage="e1_gemini_t900", out="e1-gemini-t900", model="gemini-3.8-flash", n=5, arms=AI_ARMS,
                        timeout_s=900),
    # WP4' (PRE-REGISTRATION 2026-11-15, approved by the author): Sonnet and Haiku 5.5, isolation v4, two AI arms, N=3, same seed
    "wp4-sonnet": dict(stage="wp4_sonnet_v4", out="wp4-sonnet-v4", model="claude-sonnet-5-5", n=3,
                       arms="agent_mitigate,agent_remediate", timeout_s=300, env={"SELFHEAL_ISOLATION": "v4"}),
    "wp4-haiku": dict(stage="wp4_haiku_v4", out="wp4-haiku-v4", model="claude-haiku-5-5", n=3,
                      arms="agent_mitigate,agent_remediate", timeout_s=300, env={"SELFHEAL_ISOLATION": "v4"}),
}


def run_stage(name):
    st = STAGES[name]
    out = RESULTS / st["out"]
    args = ["--n", str(st["n"]), "--model", st["model"], "--out", str(out)]
    if st["arms"]:
        args += ["--arms", st["arms"]]
    env = dict(os.environ, SELFHEAL_AGENT_TIMEOUT_S=str(st["timeout_s"]), **st.get("env", {}))
    if not run_harness(st["stage"], args, env=env):
        return False
    analyse(out)
    status(st["stage"], "done")
    gate_pilot(out, st["stage"] + "_gate")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="haiku,gemini",
                    help="steps, comma-separated: " + ", ".join(STAGES) + " (default: the main v3 batch)")
    ap.add_argument("--skip-validation", action="store_true")
    ap.add_argument("--validation-since", default="", help="reuse an earlier validation run (ISO timestamp)")
    a = ap.parse_args()
    stages = [s for s in a.stages.split(",") if s]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        ap.error("unknown steps: " + ", ".join(unknown))
    if not a.skip_validation:
        since = datetime.now().isoformat(timespec="seconds")
        status("v3_validation", "running", "tu " + since)
        LOGS.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-u", "validate_oracle.py", "--reps", "3"], cwd=ORACLE,
                       stdout=open(LOGS / "v3_validation.log", "a"), stderr=subprocess.STDOUT)
        if not gate_validation(since):
            return 1
    elif a.validation_since and not gate_validation(a.validation_since):
        return 1
    for name in stages:
        if not run_stage(name):
            return 1
    status("v3", "done", ",".join(stages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
