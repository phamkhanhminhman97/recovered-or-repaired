"""WP2 (main batch run only after the PRE-REGISTRATION entry was approved): idle, restart, and AI runs on SREGym.

Plan: 8 problems x (idle 3, restart 3 except the cronjob problem, AI 5), order shuffled with SEED. Every run redeploys and
reinjects the fault from scratch.
Results: results/sregym-wp2[-pilot][-hydrogen]/runs.jsonl, one line per run; logs in logs/. A rerun skips finished runs.
  python3 sregym-oracle/run_wp2.py --dry-run
  python3 sregym-oracle/run_wp2.py --pilot <problem> <problem> <problem>     # gate G3: trial AI runs, not analyzed
  python3 sregym-oracle/run_wp2.py                                 # main batch
  add --model hydrogen: AI arm only with gemini-4-hydrogen (added 2026-11-14), same problems, run counts, order, limits
Design: docs/sregym-design.md section 9.
"""
import argparse
import calendar
import csv
import hashlib
import http.client
import json
import os
import random
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
SREGYM = Path.home() / "srv" / "SREGym"
GATE = REPO / "sregym-oracle" / "gate.py"
SEED = 20261114
PROBLEMS = [
    "service_wrong_pod_selection_hotel_reservation",
    "kafka_poison_pill_hol_block",
    "secret_rotation_stale_env_credentials_astronomy_shop",
    "internal_traffic_policy_local_astronomy_shop",
    "cronjob_sidecar_blocks_completion_hotel_reservation",
    "finalizer_deadlock_controller_hotel_reservation",
    "namespace_memory_limit",
    "search_rate_retry_collapse_hotel_reservation",
]
N = {"idle": 3, "restart": 3, "ai": 5}  # fixed by the author on 2026-11-14: 5 AI runs per problem (3 before)
NO_RESTART = {"cronjob_sidecar_blocks_completion_hotel_reservation"}  # no Deployment to restart
IDLE_WAIT_S = 120
# Added 2026-11-14 (approved by the author): a second model runs only the AI arm; idle and restart do not depend on
# the model, so they are shared.
# 2026-11-15: the Hydrogen name needs the provider prefix (otherwise the proxy routes it to OpenAI); gemini38 is the
# fallback model under the selection rule of run_wp2_google.py (PRE-REGISTRATION 2026-11-15).
# sonnet: third AI arm (requested by the author on 2026-11-15, PRE-REGISTRATION the same day).
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "hydrogen": "google/gemini-4-hydrogen",
          "gemini38": "gemini-3.8-flash"}
AGENT_TIMEOUT_S = 900  # fixed by the author on 2026-11-14: 15 minutes (SREGym default 1800 s)
# Profile svelte: drops Grafana, OpenSearch, and Jaeger shipped with astronomy-shop (no part of SREGym reads them). Under
# the full profile Grafana starved for CPU on this machine and the SREGym oracle failed for unrelated reasons (G2 run 2,
# 2026-11-14).
PROFILE = "svelte"
# Codex version pinned in agents.yaml of the SREGym copy (agent_version: 0.163.0-alpha.11.1), not through the environment.
# Bridge to the model-proxy proxy (G3 run 1 broke here, 2026-11-14). The proxy listens only on 127.0.0.1:10100 and then
# refuses every request whose Host is not localhost/127.0.0.1 (403 origin_rejected, regardless of key); containers call
# through host.docker.internal, so they are refused.
# The bridge listens on 127.0.0.1:10101, accepts only the two model paths from the Hosts in BRIDGE_HOSTS, and rewrites
# Host to 127.0.0.1:10100; the proxy configuration is unchanged. SREGym rewrites 127.0.0.1 to host.docker.internal for
# containers and opens this port through its filter.
# In loopback mode the proxy checks no key, so AGENT_API_KEY is only a dummy value that SREGym's Codex driver requires.
PROXY = ("127.0.0.1", 10100)
BRIDGE_PORT = 10101
BRIDGE_PATHS = ("/v1/responses", "/v1/models")
BRIDGE_HOSTS = {"host.docker.internal", "127.0.0.1", "localhost"}
SKIP_HEADERS = {"connection", "keep-alive", "proxy-connection", "proxy-authorization", "transfer-encoding", "upgrade", "te",
                "trailer", "host", "origin", "date", "server"}
AGENT_ENV = {"AGENT_API_BASE": f"http://127.0.0.1:{BRIDGE_PORT}/v1", "AGENT_API_KEY": "sregym-local",
             "SELFHEAL_GATE": str(GATE)}
# Quota exhausted or provider overloaded: the same expression as the thesis harness (agent_llm.LIMIT_RE), plus
# Google's RESOURCE_EXHAUSTED.
# An AI run with such an error event (at any time) is dropped and not recorded; wait LIMIT_WAIT_S and rerun it from
# scratch, at most LIMIT_MAX_WAITS times, then stop (rerunning the command after the quota resets skips finished runs).
LIMIT_RE = re.compile(r"429|rate.?limit|usage.?limit|quota|overloaded|too many requests|529|resource.?exhausted", re.I)
# Model no longer served or provider authentication error (2026-11-15: Hydrogen returned 404 model_unavailable): not
# agent behavior. It counts as an infrastructure error (one rerun, stop after 3 in a row), so it is never recorded as an
# agent that failed to fix the problem.
PROVIDER_DOWN_RE = re.compile(r"\b404\b|not found|model_unavailable|invalid_api_key|authentication_error|\b401\b", re.I)
LIMIT_WAIT_S = 900
LIMIT_MAX_WAITS = 48
INFRA_MAX_CONSECUTIVE = 3  # consecutive infrastructure errors (e.g. a broken SREGym preflight) stop the batch instead of burning the plan


class Bridge(BaseHTTPRequestHandler):
    def forward(self):
        u = urlsplit(self.path)
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in BRIDGE_HOSTS or self.headers.get("Origin"):
            return self.send_error(403)
        if not any(u.path == p or u.path.startswith(p + "/") for p in BRIDGE_PATHS):
            return self.send_error(404)
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            return self.send_error(411)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIP_HEADERS}
        try:
            conn = http.client.HTTPConnection(*PROXY, timeout=AGENT_TIMEOUT_S)
            conn.request(self.command, u.path + (f"?{u.query}" if u.query else ""), body=body or None, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in SKIP_HEADERS:
                    self.send_header(k, v)
            self.end_headers()  # HTTP/1.0: the connection closes after each response, so the SSE stream needs no chunking
            while chunk := resp.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
            conn.close()
        except OSError as e:
            self.log_message("upstream error: %s", e)

    do_GET = do_POST = forward

    def log_message(self, fmt, *args):  # log only the request line and status, no headers (Authorization)
        with open(self.server.log_path, "a") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + fmt % args + "\n")


def start_bridge(out):
    try:
        server = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), Bridge)
    except OSError:
        raise SystemExit(f"port {BRIDGE_PORT} is in use: another run_wp2 may be running; stopping")
    server.daemon_threads = True
    server.log_path = out / "bridge.log"
    threading.Thread(target=server.serve_forever, daemon=True).start()


def plan(model="haiku"):
    runs = [{"problem": p, "arm": a, "rep": i} for p in PROBLEMS for a, n in N.items()
            if not (a == "restart" and p in NO_RESTART) for i in range(n)]
    random.Random(SEED).shuffle(runs)
    runs = [r | {"run_id": f"{r['problem']}-{r['arm']}-{r['rep']}"} for r in runs]
    if model == "haiku":
        return runs
    # Other models: AI runs in the same order as Haiku, with a renamed arm so run_id does not collide
    return [r | {"arm": f"ai_{model}", "run_id": f"{r['problem']}-ai_{model}-{r['rep']}"} for r in runs if r["arm"] == "ai"]


def run(cmd, log, env=None):
    env = (env or os.environ) | {"SREGYM_PROFILE": PROFILE}
    with open(log, "w") as f:
        return subprocess.run(cmd, cwd=SREGYM, stdout=f, stderr=subprocess.STDOUT, env=env).returncode


def json_lines(path):
    p = Path(path)
    return [json.loads(x) for x in p.read_text().splitlines() if x.startswith("{")] if p.exists() else []


def disk_full():
    for node in ("kind-worker", "kind-worker2", "kind-worker3"):
        out = subprocess.run(["docker", "exec", node, "df", "--output=pcent", "/"], capture_output=True, text=True).stdout
        if int(re.sub(r"\D", "", out.splitlines()[-1])) > 95:
            return node
    return None


def unstick_namespaces(log):
    """Background thread (main batch, 2026-11-15): when a namespace stays in Terminating for over 100 s because child
    objects carry finalizers, remove the finalizers. Idle and restart runs of the finalizer problem (external harness
    mode, no fault removal) leave a ConfigMap whose finalizer controller is locked; SREGym's next run deletes the
    namespace, waits 120 s, and gives up (the 100 s threshold falls inside that wait and above the normal deletion time,
    under 60 s so far). It only cleans the cluster between runs and never touches a measurement."""
    kinds = None
    while True:
        time.sleep(30)
        try:
            items = json.loads(subprocess.run(["kubectl", "get", "ns", "-o", "json"], capture_output=True, text=True,
                                              timeout=30).stdout or "{}").get("items", [])
            for n in items:
                ts = n["metadata"].get("deletionTimestamp")
                if not ts or time.time() - calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")) < 100:
                    continue
                ns = n["metadata"]["name"]
                kinds = kinds or ",".join(subprocess.run(["kubectl", "api-resources", "--verbs=list", "--namespaced", "-o", "name"],
                                                         capture_output=True, text=True, timeout=60).stdout.split())
                objs = json.loads(subprocess.run(["kubectl", "get", kinds, "-n", ns, "-o", "json", "--ignore-not-found"],
                                                 capture_output=True, text=True, timeout=60).stdout or "{}").get("items", [])
                for o in (o for o in objs if o["metadata"].get("finalizers")):
                    ref = f"{o['kind'].lower()}/{o['metadata']['name']}"
                    subprocess.run(["kubectl", "patch", ref, "-n", ns, "--type=merge", "-p", '{"metadata":{"finalizers":null}}'],
                                   capture_output=True, timeout=30)
                    with open(log, "a") as f:
                        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {ns} {ref} {o['metadata']['finalizers']}\n")
        except (ValueError, KeyError, subprocess.TimeoutExpired):
            continue


def sregym_dirs():
    return {d.name for d in (SREGYM / "results").iterdir() if d.is_dir()}


def sregym_round1(results_dir, problem):
    """SREGym's mitigation oracle result in the AI run, read from the CSV in the run's new result directory (G3 run 2: rich
    wrapped log lines at 80 columns, so the path cannot be read from the log; column name Mitigation.success)."""
    csvs = sorted(results_dir.glob(f"*/{problem}/{problem}_*_results.csv")) if results_dir else []
    rows = list(csv.DictReader(csvs[0].open())) if csvs else []
    if not rows:
        return None, None
    value = next((v for k, v in rows[-1].items() if k.lower() == "mitigation.success"), None)
    return (None if value in (None, "") else value == "True"), str(csvs[0])


def outcome(round1, rounds):
    if round1 is None:
        return "unscored"
    if not round1:
        return "not_recovered"
    if not rounds:
        return "unscored"
    return "durable" if all(r["success"] for r in rounds) else "temporary"


def codex_errors(results_dir):
    """Codex model errors (error and turn.failed events) in codex.txt of the SREGym result directory. Only error events
    are read, never the agent's command output (e.g. 'kubectl get resourcequota' in the memory-quota problem)."""
    # published copy (codex/<problem>/run_N); if SREGym could not publish it, the temporary copy in .runtime
    files = (sorted(results_dir.glob("*/*/run_*/codex.txt")) or sorted(results_dir.rglob("codex.txt"))) if results_dir else []
    errors = []
    for line in (x for f in files for x in f.read_text(errors="ignore").splitlines()):
        try:
            e = json.loads(line) if line.startswith("{") else {}
        except json.JSONDecodeError:
            continue
        if e.get("type") == "error":
            errors.append(str(e.get("message", ""))[:300])
        elif e.get("type") == "turn.failed":
            errors.append(str((e.get("error") or {}).get("message", ""))[:300])
    return errors, len(files)


def run_one(r, out, model):
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base, p = logs / r["run_id"], r["problem"]
    # logs of the previous attempt (infrastructure error, quota, interruption) move to superseded/, never overwritten
    if old := sorted(logs.glob(f"{r['run_id']}-*")):
        keep = logs / "superseded"
        keep.mkdir(exist_ok=True)
        for f in old:
            f.rename(keep / f"{time.strftime('%Y%m%dT%H%M%S')}-{f.name}")
    rec = r | {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "gate_sha": hashlib.sha256(GATE.read_bytes()).hexdigest()[:12]}
    t0 = time.time()
    if r["arm"].startswith("ai"):
        rec["model"] = MODELS[model]
        home = out / "codex-home-empty"  # empty CODEX_HOME: SREGym does not copy the machine's auth.json into the container (R7)
        home.mkdir(exist_ok=True)
        rounds_log = Path(f"{base}-rounds.jsonl")
        rounds_log.unlink(missing_ok=True)
        env = os.environ | AGENT_ENV | {"CODEX_HOME": str(home), "SELFHEAL_ROUNDS_LOG": str(rounds_log)}
        before = sregym_dirs()
        rec["rc"] = run(["uv", "run", "main.py", "--problem", p, "--agent", "codex", "--model", MODELS[model],
                         "--stages", "mitigation", "--agent-timeout", str(AGENT_TIMEOUT_S),
                         "--internet-access", "filtered", "--container-hardening", "on"], f"{base}-agent.log", env)
        new = sorted(sregym_dirs() - before)
        results_dir = SREGYM / "results" / new[-1] if new else None
        rec["sregym_run_dir"] = str(results_dir) if results_dir else None
        rec["round1"], rec["sregym_results"] = sregym_round1(results_dir, p)
        errors, rec["codex_logs"] = codex_errors(results_dir)
        if limited := [e for e in errors if LIMIT_RE.search(e)]:
            return rec | {"provider_limit": limited[:3], "seconds": round(time.time() - t0)}
        if down := [e for e in errors if PROVIDER_DOWN_RE.search(e)]:
            return rec | {"infra_error": "provider_error", "provider_errors": down[:3], "seconds": round(time.time() - t0)}
        if rec["round1"] is None:
            # SREGym produced no round-1 result (broken preflight or deployment; the CSV may still exist): infrastructure error
            return rec | {"infra_error": "no_sregym_verdict", "seconds": round(time.time() - t0)}
        lines = json_lines(rounds_log)
    else:
        run(["uv", "run", "main.py", "--problem", p, "--use-external-harness"], f"{base}-deploy.log")
        if "Fault injected for problem" not in Path(f"{base}-deploy.log").read_text(errors="ignore"):
            return rec | {"infra_error": "deploy_failed", "seconds": round(time.time() - t0)}
        if r["arm"] == "idle":
            time.sleep(IDLE_WAIT_S)
        steps = ["faulty" if r["arm"] == "idle" else "restart", "post"]
        rec["rc"] = run(["uv", "run", "python", str(GATE), p, *steps], f"{base}-gate.log")
        lines = json_lines(f"{base}-gate.log")
        rec["round1"] = lines[0]["success"] if lines else None
        lines = lines[1:]
        # the external harness mode leaves the MCP server's port-forward on port 9954; the next AI run would trip over it
        subprocess.run(["pkill", "-f", "port-forward svc/mcp-server"], check=False)
        if rec["round1"] is None:
            # gate.py produced no round-1 result (e.g. kubectl refuses two 'rollout restart' in one second): infrastructure error
            return rec | {"infra_error": "gate_failed", "seconds": round(time.time() - t0)}
    rec["rounds"] = [{"step": x["step"], "success": x["success"]} for x in lines if x["step"] != "post"]
    return rec | {"outcome": outcome(rec["round1"], rec["rounds"]), "seconds": round(time.time() - t0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot", nargs="+", metavar="PROBLEM")
    ap.add_argument("--model", choices=sorted(MODELS), default="haiku")
    a = ap.parse_args()
    suffix = "" if a.model == "haiku" else f"-{a.model}"
    if a.pilot:
        arm = "ai" if a.model == "haiku" else f"ai_{a.model}"
        runs = [{"problem": p, "arm": arm, "rep": 0, "run_id": f"pilot{suffix}-{p}"} for p in a.pilot]
        out = f"sregym-wp2-pilot{suffix}"
    else:
        runs, out = plan(a.model), f"sregym-wp2{suffix}"
    out = REPO / "results" / out
    if a.dry_run:
        for r in runs:
            print(r["run_id"])
        print(len(runs), "runs")
        return
    out.mkdir(parents=True, exist_ok=True)
    start_bridge(out)
    threading.Thread(target=unstick_namespaces, args=(out / "unstick.log",), daemon=True).start()
    done = {json.loads(x)["run_id"] for x in (out / "runs.jsonl").read_text().splitlines()} if (out / "runs.jsonl").exists() else set()
    todo, waits, infra_streak, retried = [r for r in runs if r["run_id"] not in done], 0, 0, set()
    while todo:
        r = todo[0]
        if node := disk_full():
            raise SystemExit(f"node {node} disk above 95%, stopping")
        rec = run_one(r, out, a.model)
        if rec.get("provider_limit"):
            with open(out / "limited.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
            waits += 1
            if waits > LIMIT_MAX_WAITS:
                raise SystemExit("quota exhausted for over 12 hours; rerun this command after the quota resets (finished runs are skipped)")
            print(rec["run_id"], f"quota exhausted/overloaded, waiting {LIMIT_WAIT_S}s before rerunning ({waits}/{LIMIT_MAX_WAITS})", flush=True)
            time.sleep(LIMIT_WAIT_S)
            continue
        waits = 0
        if rec.get("infra_error"):
            # frozen design: infrastructure errors do not count; rerun once; if it fails again record infra_error (not counted), go on
            with open(out / "infra.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
            infra_streak += 1
            if infra_streak >= INFRA_MAX_CONSECUTIVE:
                raise SystemExit(f"{infra_streak} consecutive infrastructure errors ({rec['infra_error']}); stopping for a check")
            if r["run_id"] not in retried:
                retried.add(r["run_id"])
                print(rec["run_id"], "infrastructure error, rerunning once", flush=True)
                continue
        else:
            infra_streak = 0
        todo.pop(0)
        with open(out / "runs.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(rec["run_id"], rec.get("outcome", rec.get("infra_error")), flush=True)


if __name__ == "__main__":
    main()

