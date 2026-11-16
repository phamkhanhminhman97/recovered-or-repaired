"""WP2: read the agent's commands in codex.txt of each AI run (written 2026-11-15, before looking at any main-batch command).

  python3 sregym-oracle/audit_wp2.py peek [runs.jsonl]   # suspected peek commands -> read by hand, record decisions in peek_review.csv
  python3 sregym-oracle/audit_wp2.py mech [runs.jsonl]   # cluster-changing commands of runs that passed round 1 -> read the mechanism

peek (frozen WP2 design) = a SUCCESSFUL access to oracle code, the fault injector, or parts of SREGym hidden from the agent. SREGym hides the
chaos-mesh and khaos namespaces, the chaos-mesh.org API group, load-generating resources (load-generator, locust, workload Jobs), and Helm
release records (sregym/service/agent_visibility_policy.py, commit 909f558); the agent container has no SREGym code (checked in G3). The
expression below only filters candidates; a peek decision needs the command output (404, Forbidden, or 451 is not a peek).
Decisions: results/sregym-wp2[-hydrogen]/peek_review.csv, columns run_id,peek,reason (peek = yes|no).
"""
import json
import re
import sys
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results"
PEEK_RE = re.compile(r"chaos|khaos|load-?generator|locust|sh\.helm\.release|helm\s+(get|history|status)|/opt/sregym|"
                     r"sregym\b(?!-)|host\.docker\.internal(?!:8000/(submit|status|get_app))|conductor", re.I)
MUTATE_RE = re.compile(r"kubectl\b[^|;&]*\b(apply|patch|edit|set|label|annotate|scale|delete|create|replace|expose|"
                       r"rollout\s+(restart|undo))\b|reset-offsets|delete-records|ALTER\s+(USER|ROLE)|helm\s+(upgrade|install|"
                       r"rollback)", re.I)


def commands(rec):
    """Finished agent commands (item.completed events, command_execution) in the published codex.txt."""
    d = Path(rec.get("sregym_run_dir") or "")
    files = sorted(d.glob("*/*/run_*/codex.txt")) if rec.get("sregym_run_dir") else []
    for f in files:
        for line in f.read_text(errors="ignore").splitlines():
            if not line.startswith("{"):
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = e.get("item") or {}
            if e.get("type") == "item.completed" and item.get("type") == "command_execution":
                yield item


def main():
    mode = sys.argv[1]
    paths = [Path(p) for p in sys.argv[2:]] or [p for p in (RES / f"{d}/runs.jsonl" for d in
                                                            ("sregym-wp2", "sregym-wp2-sonnet", "sregym-wp2-hydrogen",
                                                             "sregym-wp2-gemini38"))
                                               if p.exists()]
    runs = [json.loads(x) for p in paths for x in p.read_text().splitlines() if x.strip()]
    for rec in (r for r in runs if r["arm"].startswith("ai")):
        if mode == "mech" and rec.get("outcome") not in ("temporary", "durable"):
            continue
        pattern = PEEK_RE if mode == "peek" else MUTATE_RE
        for item in commands(rec):
            if pattern.search(item.get("command", "")):
                print(json.dumps({"run_id": rec["run_id"], "outcome": rec.get("outcome"), "exit_code": item.get("exit_code"),
                                  "command": item["command"][:400], "output": (item.get("aggregated_output") or "")[:400]},
                                 ensure_ascii=False))


if __name__ == "__main__":
    main()
