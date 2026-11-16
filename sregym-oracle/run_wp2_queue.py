"""WP2 after the Haiku batch (written 2026-11-15, before any Sonnet or Google run).

Order (fixed by the author on 2026-11-15): Haiku 85/85 done -> Sonnet 5.5 (3 pilot runs to measure tokens, then 40 AI runs)
-> Google arm
(gemini-4-hydrogen if reachable, 3 tries 10 minutes apart; otherwise gemini-3.8-flash; 3 pilot runs, then 40 AI runs).
- If a model's pilot fails (missing record, infrastructure error, no codex.txt), that model is dropped, logged, and the queue moves on.
- If a main batch stops unfinished (e.g. run_wp2's 12-hour quota wait), the queue moves on; at the end it retries unfinished batches
  every hour, for at most 96 hours (Claude's weekly quota resets on a schedule).
- Sonnet pilot: tokens per run (turn.completed events in codex.txt) and the Anthropic quota level before and after go to
  results/sregym-wp2-pilot-sonnet/tokens.json.
Replaces run_wp2_google.py (which had only the Google arm).
  screen -dmS wp2q /bin/sh -c 'caffeinate -is python3 sregym-oracle/run_wp2_queue.py >> results/sregym-wp2-queue.log 2>&1'
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_wp2 as R  # noqa: E402

PILOT = ["kafka_poison_pill_hol_block", "secret_rotation_stale_env_credentials_astronomy_shop",
         "service_wrong_pod_selection_hotel_reservation"]
PROBES, PROBE_GAP_S = 3, 600
RETRY_GAP_S, RETRY_MAX_S = 3600, 96 * 3600
RES = R.REPO / "results"


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


def records(out):
    p = RES / out / "runs.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def complete(model):
    out = "sregym-wp2" if model == "haiku" else f"sregym-wp2-{model}"
    return {r["run_id"] for r in R.plan(model)} <= {r["run_id"] for r in records(out)}


def run(args, out):
    (RES / out).mkdir(parents=True, exist_ok=True)
    with open(RES / out / "run.log", "a") as f:
        return subprocess.run([sys.executable, str(HERE / "run_wp2.py"), *args], cwd=R.REPO, stdout=f,
                              stderr=subprocess.STDOUT).returncode


def haiku_running():
    return subprocess.run(["pgrep", "-f", "sregym-oracle/run_wp2.py$"], capture_output=True).returncode == 0


def anthropic_quota():
    out = subprocess.run(["ocx", "account", "list", "anthropic", "--quota", "--json"], capture_output=True, text=True).stdout
    try:
        return [{"id": a["id"][:8], "active": a.get("active"), **{k: (a.get("quota") or {}).get(k) for k in
                                                                    ("fiveHourPercent", "weeklyPercent")}}
                for a in json.loads(out)["accounts"]]
    except (ValueError, KeyError):
        return None


def run_tokens(rec):
    """Total tokens of one run from the turn.completed events in the published codex.txt."""
    tot = {}
    for f in sorted(Path(rec.get("sregym_run_dir") or "/nonexistent").glob("*/*/run_*/codex.txt")):
        for line in f.read_text(errors="ignore").splitlines():
            if '"turn.completed"' in line:
                for k, v in (json.loads(line).get("usage") or {}).items():
                    tot[k] = tot.get(k, 0) + (v or 0)
    return tot


def pilot(model):
    out = f"sregym-wp2-pilot-{model}"
    before = anthropic_quota() if model == "sonnet" else None
    run(["--pilot", *PILOT, "--model", model], out)
    recs = records(out)
    bad = [r["run_id"] for r in recs if r.get("infra_error") or not r.get("codex_logs")]
    if model == "sonnet":
        (RES / out / "tokens.json").write_text(json.dumps({
            "quota_before": before, "quota_after": anthropic_quota(),
            "runs": [{"run_id": r["run_id"], "seconds": r.get("seconds"), "outcome": r.get("outcome"), "tokens": run_tokens(r)}
                     for r in recs]}, indent=1) + "\n")
    ok = len(recs) >= len(PILOT) and not bad
    log(f"pilot {model}: {'passed' if ok else 'NOT PASSED'}; {[(r['run_id'], r.get('outcome')) for r in recs]}; broken {bad}")
    return ok


def choose_google():
    for i in range(PROBES):
        body = json.dumps({"model": R.MODELS["hydrogen"], "input": "Reply with the single word OK.",
                           "max_output_tokens": 32}).encode()
        req = urllib.request.Request(f"http://{R.PROXY[0]}:{R.PROXY[1]}/v1/responses", body,
                                     {"Content-Type": "application/json", "Authorization": "Bearer sregym-local"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status == 200 and json.loads(r.read()).get("status") == "completed":
                    return "hydrogen"
        except Exception as e:  # noqa: BLE001
            log(f"Hydrogen try {i + 1}: {str(e)[:120]}")
        if i < PROBES - 1:
            time.sleep(PROBE_GAP_S)
    return "gemini38"


def main():
    restarts = 0
    while not complete("haiku"):
        if haiku_running():
            time.sleep(60)
            continue
        if restarts >= 3:
            raise SystemExit("Haiku batch unfinished after 3 restarts; stopping")
        restarts += 1
        log(f"Haiku batch stopped unfinished; restart {restarts}")
        run([], "sregym-wp2")
    log("Haiku batch done 85/85")
    pending = []
    if pilot("sonnet"):
        run(["--model", "sonnet"], "sregym-wp2-sonnet")
        log(f"dot Sonnet: {len(records('sregym-wp2-sonnet'))}/40")
        if not complete("sonnet"):
            pending.append("sonnet")
    google = choose_google()
    log(f"Google arm model: {google} ({R.MODELS[google]})")
    (RES / "sregym-wp2-google-choice.json").write_text(json.dumps(
        {"model": google, "model_id": R.MODELS[google], "chosen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    if pilot(google):
        run(["--model", google], f"sregym-wp2-{google}")
        log(f"dot {google}: {len(records(f'sregym-wp2-{google}'))}/40")
        if not complete(google):
            pending.append(google)
    t0 = time.time()
    while pending and time.time() - t0 < RETRY_MAX_S:
        time.sleep(RETRY_GAP_S)
        for m in list(pending):
            run(["--model", m], f"sregym-wp2-{m}")
            log(f"retry {m}: {len(records(f'sregym-wp2-{m}'))}/40")
            if complete(m):
                pending.remove(m)
    log(f"finished; still pending: {pending}")


if __name__ == "__main__":
    main()
