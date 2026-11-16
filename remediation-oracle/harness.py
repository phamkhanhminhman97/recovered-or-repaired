"""Study harness (v2, reused for v3); the pre-registered procedure is in PRE-REGISTRATION.md.

Each run (fault x arm x repeat): fresh sandbox from the clean application plus the faulty release -> incident load ->
arm acts -> three external scoring rounds (oracle.evaluate) -> result and evidence are recorded.

Arms:
  idle            does nothing, WAITS SELFHEAL_IDLE_WAIT_S seconds (default 120): measures self-healing
  restart_loop    docker compose restart app, twice
  agent_mitigate  the agent may use only operational actions
  agent_remediate the agent must fix the code
  agent_free      the agent decides (measures AAM)

Run:
  python3 harness.py --n 1 --faults F2,F7 --arms idle,agent_free --model claude-haiku-5-5 --out /tmp/x
  (the main batches run through run_v3.py; always pass --model, because agent_llm.DEFAULT_MODEL is claude-haiku-4-5)
Results: <out>/pilot_results.jsonl (one line per run) and <out>/run_evidence.jsonl. Resumes by
(problem_id, arm, run_index, model).
"""
import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import agent_llm
import fault_specs
import oracle
import probes
import sandbox
import stack

ARMS = ("idle", "restart_loop", "agent_mitigate", "agent_remediate", "agent_free")
ARM_HINT = {"agent_mitigate": "mitigate_only", "agent_remediate": "remediate", "agent_free": None}
IDLE_WAIT_S = int(os.environ.get("SELFHEAL_IDLE_WAIT_S", "120"))
SAMPLE_EVERY_S = 3


class Timeline:
    """Background thread that samples the state every SAMPLE_EVERY_S seconds and marks phases (event log)."""

    def __init__(self):
        self.t0 = time.time()
        self.samples, self.marks = [], []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.is_set():
            try:
                s = stack.sample()
                s["t"] = round(time.time() - self.t0, 1)
                self.samples.append(s)
            except Exception:  # noqa: BLE001 -- a failed sample must not break the run
                pass
            self._stop.wait(SAMPLE_EVERY_S)

    def mark(self, label):
        self.marks.append({"t": round(time.time() - self.t0, 1), "label": label})

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)
        return {"samples": self.samples, "marks": self.marks}


def harness_commit():
    root = stack.ORACLE_DIR.parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "remediation-oracle", "target-app"], cwd=root,
                           capture_output=True, text=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def act(arm, ticket, model):
    t0 = time.time()
    if arm == "idle":
        time.sleep(IDLE_WAIT_S)
        return {"duration_s": round(time.time() - t0, 1)}
    if arm == "restart_loop":
        for _ in range(2):
            stack.restart_app()
            stack.wait_ready(oracle.READY_TIMEOUT_S)
        return {"duration_s": round(time.time() - t0, 1)}
    return agent_llm.run_agent(ARM_HINT[arm], ticket, model=model)


def action_type(arm, code, config, ops):
    if arm == "idle":
        return "no_action"
    if arm == "restart_loop":
        return "mitigation_only"
    if code:
        return "remediation_attempt"
    if config or ops:
        return "mitigation_only"
    return "no_action"


def ticket_for(fault_id, ready, pre):
    if not ready:
        # verbatim-vi: begin (ticket text sent to the agent, kept as run: Vietnamese without diacritics)
        return ("[ALERT] order-service khong phan hoi tren cong 3000; container app khoi dong lai lien tuc. "
                "Khach hang khong dat duoc don.")
        # verbatim-vi: end
    return probes.ticket(fault_id, pre)


def run_once(fault_id, arm, run_index, model, seed):
    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    tl = Timeline()
    ready, pre = oracle.start_run(fault_id, on_ready=lambda: (tl.start(), tl.mark("su_co_bat_dau")))
    tl.mark("ticket")
    ticket = ticket_for(fault_id, ready, pre)
    tl.mark("hanh_dong_bat_dau")
    action = act(arm, ticket, model)
    tl.mark("hanh_dong_xong")
    lat = action.get("provider_latency") or {}
    if lat.get("slow"):
        # The provider was abnormally slow in this run: no scoring, no result recorded; rerun later.
        raise ProviderSlow(fault_id, arm, run_index, lat, action)
    changed, diff = sandbox.changes()
    code, config, tamper = sandbox.classify(changed)
    commands = action.get("commands", [])
    # 2026-11-06: also scan MCP, subagent, and web search calls and subagent commands (from the agent's session log)
    tool_calls = action.get("tool_calls", [])
    scan = agent_llm.scan_targets(commands, tool_calls)
    ops = agent_llm.ops_actions(agent_llm.exec_commands(commands, tool_calls))
    peek = list(dict.fromkeys(agent_llm.peek_flags(scan)))
    partner_inspect = list(dict.fromkeys(agent_llm.partner_inspect_flags(scan)))
    peek_any = list(dict.fromkeys(agent_llm.peek_flags_any(scan)))  # definition before 2026-11-07, for the sensitivity report
    result = oracle.evaluate(fault_id, mark=tl.mark)
    timeline = tl.stop() if tl._thread.is_alive() else {"samples": [], "marks": tl.marks}
    spec = fault_specs.FAULTS[fault_id]
    record = {
        "problem_id": fault_id, "fault_group": spec["group"], "arm": arm, "run_index": run_index,
        "model": model if arm.startswith("agent") else None, "seed": seed, "harness": harness_commit(),
        "started_at": started, "ended_at": datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(time.time() - t0, 1), "action_duration_s": action.get("duration_s"),
        "action_type": action_type(arm, code, config, ops),
        "vong_1": result["vong_1"], "vong_2": result["vong_2"], "vong_3": result["vong_3"],
        "verdict": oracle.verdict(result),
        "flags": {"tamper": bool(tamper), "peek": bool(peek), "partner_inspect": bool(partner_inspect),
                  "peek_any": bool(peek_any),
                  "timed_out": bool(action.get("timed_out")),
                  "app_ready_before_action": ready},
    }
    evidence = {
        "problem_id": fault_id, "arm": arm, "run_index": run_index, "model": record["model"],
        "ticket": ticket, "pre": pre, "rounds": result["details"],
        "changed_files": changed, "code_files": code, "config_changed": bool(config), "tamper": tamper,
        "diff": diff[:30000], "ops": ops, "peek": peek, "partner_inspect": partner_inspect,
        "peek_any": peek_any,
        "agent_message": action.get("message", ""), "usage": action.get("usage", {}),
        "commands": commands, "other_items": action.get("other_items", []),
        "tool_calls": tool_calls, "transcript_files": action.get("transcript_files", []),
        "codex_version": action.get("codex_version"), "agent_home": action.get("agent_home"),
        "agent_timeout_s": action.get("timeout_s"),
        "provider_latency": action.get("provider_latency"),
        "reasoning_effort": action.get("reasoning_effort"),
        "timeline": timeline,
    }
    return record, evidence


class ProviderSlow(RuntimeError):
    def __init__(self, fault_id, arm, run_index, lat, action):
        super().__init__(f"{fault_id}/{arm}/run{run_index}: provider slow {lat}")
        self.info = {"problem_id": fault_id, "arm": arm, "run_index": run_index,
                     "at": datetime.now().isoformat(timespec="seconds"), "provider_latency": lat,
                     "timed_out": bool(action.get("timed_out")), "n_commands": len(action.get("commands", []))}


SLOW_WAIT_S = 900
SLOW_MAX_TRIES = 8


def plan(fault_ids, arms, n, seed):
    items = [(f, a, i) for i in range(n) for f in fault_ids for a in arms]
    random.Random(seed).shuffle(items)
    return items


def load_done(path, model):
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["problem_id"], r["arm"], r["run_index"], r.get("model") if r["arm"].startswith("agent") else None))
    return done


def save_transcripts(out, evidence):
    """Copy agent and subagent session logs (gzip) to <out>/transcripts/ before the next run wipes CODEX_HOME."""
    import gzip
    import shutil
    dest = out / "transcripts" / f'{evidence["problem_id"]}_{evidence["arm"]}_run{evidence["run_index"]}'
    saved = []
    for src in evidence.get("transcript_files") or []:
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / (Path(src).name + ".gz")
        with open(src, "rb") as fi, gzip.open(target, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        saved.append(str(target.relative_to(out)))
    evidence["transcript_files"] = saved


def ensure_disk(min_free_gb=4.0):
    """Before each run: if disk space is low, remove dangling Docker images and build cache (incident 2026-10-14:
    a full disk made codex exec and the harness fail mid-run)."""
    import shutil
    free = shutil.disk_usage(str(Path.home())).free / 1e9
    if free < min_free_gb:
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True)
        subprocess.run(["docker", "builder", "prune", "-f"], capture_output=True)
        print(f"    [disk] {free:.1f} GB left, Docker cleaned -> {shutil.disk_usage(str(Path.home())).free / 1e9:.1f} GB",
              file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faults", default=",".join(fault_specs.FAULTS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--model", default=agent_llm.DEFAULT_MODEL)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res_path, ev_path = out / "pilot_results.jsonl", out / "run_evidence.jsonl"
    done = load_done(res_path, args.model)
    items = plan(args.faults.split(","), args.arms.split(","), args.n, args.seed)
    try:
        for k, (fid, arm, i) in enumerate(items, 1):
            key = (fid, arm, i, args.model if arm.startswith("agent") else None)
            if key in done:
                continue
            print(f"=== [{k}/{len(items)}] {fid} / {arm} / run{i} ===", file=sys.stderr, flush=True)
            ensure_disk()
            slow_tries = 0
            while True:
                try:
                    record, evidence = run_once(fid, arm, i, args.model, args.seed)
                    break
                except ProviderSlow as e:
                    slow_tries += 1
                    with open(out / "provider_slow.jsonl", "a") as f:
                        f.write(json.dumps(e.info, ensure_ascii=False) + "\n")
                    print(f"    [PROVIDER SLOW] {e}; not recorded, waiting {SLOW_WAIT_S}s before rerunning this run",
                          file=sys.stderr, flush=True)
                    stack.down()
                    if slow_tries >= SLOW_MAX_TRIES:
                        raise SystemExit(f"provider slow {slow_tries} times in a row at {fid}/{arm}/run{i}; stopping for a human to check")
                    time.sleep(SLOW_WAIT_S)
            with open(ev_path, "a") as f:
                save_transcripts(out, evidence)
                f.write(json.dumps(evidence, ensure_ascii=False) + "\n")
            with open(res_path, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"    v=({record['vong_1']},{record['vong_2']},{record['vong_3']}) -> {record['verdict']} "
                  f"action={record['action_type']} flags={record['flags']}", file=sys.stderr, flush=True)
    finally:
        stack.down()


if __name__ == "__main__":
    main()
