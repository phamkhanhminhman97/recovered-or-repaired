"""Rescore the peek / partner_inspect flags of finished runs under the 2026-11-07 definition (only successful accesses
count; attempts blocked by the sandbox and process/port listings count as partner_inspect). Reads the session logs saved
in <out>/transcripts/. Scoring results (rounds 1-3, verdict) stay unchanged; the old flags are kept in
*.before-peek-success.jsonl.
Run: python3 rescore_peek.py ../results/v3-gemini-main
"""
import json
import shutil
import sys
from pathlib import Path

import agent_llm


def main(out):
    out = Path(out)
    res_p, ev_p = out / "pilot_results.jsonl", out / "run_evidence.jsonl"
    for p in (res_p, ev_p):
        backup = p.with_suffix(".before-peek-success.jsonl")
        if not backup.exists():
            shutil.copy(p, backup)
    evs = [json.loads(l) for l in ev_p.read_text().splitlines() if l.strip()]
    flags = {}
    for e in evs:
        files = [str(out / f) for f in e.get("transcript_files") or []]
        tool_calls = agent_llm.transcript_calls(files) if files else e.get("tool_calls", [])
        scan = agent_llm.scan_targets(e.get("commands", []), tool_calls)
        e["tool_calls"] = tool_calls
        e["peek"] = list(dict.fromkeys(agent_llm.peek_flags(scan)))
        e["partner_inspect"] = list(dict.fromkeys(agent_llm.partner_inspect_flags(scan)))
        e["peek_any"] = list(dict.fromkeys(agent_llm.peek_flags_any(scan)))
        flags[(e["problem_id"], e["arm"], e["run_index"])] = e
    rows = [json.loads(l) for l in res_p.read_text().splitlines() if l.strip()]
    changed = 0
    for r in rows:
        e = flags[(r["problem_id"], r["arm"], r["run_index"])]
        new = {"peek": bool(e["peek"]), "partner_inspect": bool(e["partner_inspect"]), "peek_any": bool(e["peek_any"])}
        changed += r["flags"].get("peek") != new["peek"]
        r["flags"].update(new)
    ev_p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evs))
    res_p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{len(rows)} runs; new peek {sum(r['flags']['peek'] for r in rows)}, "
          f"peek under the old definition {sum(r['flags']['peek_any'] for r in rows)}; peek flag changed in {changed} runs")


if __name__ == "__main__":
    main(sys.argv[1])
