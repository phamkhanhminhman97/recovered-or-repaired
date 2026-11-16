"""Compare v1 (leaky harness, tag v1-leaky) with v2.

v1: 2 rounds (vong_1 = normal load, vong_2 = load again); "recovered" = vong_1 passes,
    "real recovery" = vong_1 and vong_2 pass. The faulty code had a FAULT_FIXED branch and answer
    comments that the agent could read; the F5/F7/F12 oracles passed even when nothing was done.
v2: 3 rounds (adds a redeploy round from the agent's code and .env), hidden answers, corrected oracles.
    Runs flagged peek are excluded.

Usage: python3 compare_v1_v2.py [v1_dir] [v2_dir] > ../results/compare_v1_v2.md
  v1 against v3: python3 compare_v1_v2.py ../results/v1-leaky-n10 ../results/v3-haiku55-main > ../results/compare_v1_v3.md
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "results"
ARMS = ["idle", "restart_loop", "agent_mitigate", "agent_remediate", "agent_free"]


def load(p):
    return [json.loads(l) for l in (Path(p) / "pilot_results.jsonl").read_text().splitlines() if l.strip()]


def v1_status(r):
    if r["vong_1"] != "pass":
        return "none"
    return "real" if r["vong_2"] == "pass" else "temp"


def v2_status(r):
    return r["verdict"]


def table(rows, status_fn, key):
    out = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))  # real, temp, n
    for r in rows:
        s = status_fn(r)
        c = out[r[key]][r["arm"]]
        c[2] += 1
        if s == "real":
            c[0] += 1
        elif s == "temp":
            c[1] += 1
    return out


def fmt(c):
    real, temp, n = c
    if n == 0:
        return "–"
    return f"{real/n:.2f} / {temp/n:.2f} (n={n})"


def main():
    v1_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "v1-leaky-n10"
    v2_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "v2-haiku55-main"
    v1 = load(v1_dir)
    v2_all = load(v2_dir)
    v2 = [r for r in v2_all if not r["flags"].get("peek")]
    for r in v1 + v2:
        r["_all"] = "all"

    print(f"# Comparison of v1 ({v1_dir.name}) and v2 ({v2_dir.name})\n")
    print(f"v1: {len(v1)} runs. v2: {len(v2_all)} runs, {len(v2_all) - len(v2)} peek runs excluded.\n")
    print("Each cell: real / temporary recovery rate. v1 has 2 rounds, so its 'real recovery' never went through a redeploy.\n")

    t1, t2 = table(v1, v1_status, "_all"), table(v2, v2_status, "_all")
    print("## Totals by arm\n")
    print("| Arm | v1 | v2 |\n|---|---|---|")
    for a in ARMS:
        print(f"| {a} | {fmt(t1['all'][a])} | {fmt(t2['all'][a])} |")

    f1, f2 = table(v1, v1_status, "problem_id"), table(v2, v2_status, "problem_id")
    faults = sorted(set(f1) | set(f2), key=lambda x: int(x[1:]))
    print("\n## By fault\n")
    print("| Fault | Arm | v1 | v2 |\n|---|---|---|---|")
    for f in faults:
        for a in ARMS:
            if f1[f][a][2] or f2[f][a][2]:
                print(f"| {f} | {a} | {fmt(f1[f][a])} | {fmt(f2[f][a])} |")

    print("\n## Where v1 measured wrongly\n")
    weak = [f for f in faults if f1[f]["idle"][2] and (f1[f]["idle"][0] + f1[f]["idle"][1]) > 0]
    print(f"- Faults where v1's idle arm still 'recovered' (weak oracle): {', '.join(weak) or 'none'}")
    weak2 = [f for f in faults if f2[f]["idle"][2] and (f2[f]["idle"][0] + f2[f]["idle"][1]) > 0]
    print(f"- Faults where v2's idle arm still 'recovered': {', '.join(weak2) or 'none'}")
    shifts = []
    for f in faults:
        for a in ("agent_mitigate", "agent_remediate"):
            c1, c2 = f1[f][a], f2[f][a]
            if c1[2] and c2[2]:
                d = c2[0] / c2[2] - c1[0] / c1[2]
                if abs(d) >= 0.3:
                    shifts.append(f"{f}/{a}: real recovery {c1[0]/c1[2]:.2f} -> {c2[0]/c2[2]:.2f}")
    print("- Large changes (>= 0.30) in the real recovery rate between v1 and v2:")
    for s in shifts or ["none"]:
        print(f"  - {s}")


if __name__ == "__main__":
    main()
