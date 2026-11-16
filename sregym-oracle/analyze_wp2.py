"""WP2: analysis of run_wp2.py's runs.jsonl following section 9 of docs/sregym-design.md (written before real data existed).

Primary: in group A, the share of AI runs that recovered only temporarily among runs that passed round 1 (Wilson 95%), per
problem and pooled; compared with the restart arm.
Group B: runs that SREGym passed but that failed round 2 or 3. Infrastructure errors (infra_error) and unscored runs are
reported separately.
Hydrogen addition (2026-11-14): each AI arm (ai = Haiku, ai_hydrogen) gets the same metrics side by side (descriptive).
peek (2026-11-15): runs marked peek=yes in peek_review.csv next to runs.jsonl (candidates from audit_wp2.py, read by hand)
are excluded from the primary analysis and reported separately; the 5% gate applies as in earlier batches.
  python3 sregym-oracle/analyze_wp2.py [runs.jsonl ...]   # default results/sregym-wp2 and sregym-wp2-hydrogen if present
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

GROUP_A = {"service_wrong_pod_selection_hotel_reservation", "kafka_poison_pill_hol_block",
           "secret_rotation_stale_env_credentials_astronomy_shop", "internal_traffic_policy_local_astronomy_shop"}
OUTCOMES = ("not_recovered", "temporary", "durable", "unscored", "infra_error")


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def rate(runs):
    passed = [r for r in runs if r.get("outcome") in ("temporary", "durable")]
    k = sum(r["outcome"] == "temporary" for r in passed)
    lo, hi = wilson(k, len(passed))
    return f"{k}/{len(passed)}" + (f" ({lo:.0%}–{hi:.0%})" if passed else "")


def peeked(paths):
    out = set()
    for p in paths:
        f = Path(p).parent / "peek_review.csv"
        if f.exists():
            out |= {r["run_id"] for r in csv.DictReader(f.open()) if r["peek"].strip().lower() == "yes"}
    return out


def main():
    res = Path(__file__).resolve().parents[1] / "results"
    paths = [Path(p) for p in sys.argv[1:]] or [p for p in (res / f"{d}/runs.jsonl" for d in
                                                            ("sregym-wp2", "sregym-wp2-sonnet", "sregym-wp2-hydrogen",
                                                             "sregym-wp2-gemini38"))
                                               if p.exists()]
    runs = [json.loads(x) for path in paths for x in path.read_text().splitlines() if x.strip()]
    peek = peeked(paths)
    for arm in sorted({r["arm"] for r in runs if r["arm"].startswith("ai")}):
        a = [r for r in runs if r["arm"] == arm]
        k = sum(r["run_id"] in peek for r in a)
        print(f"peek, arm {arm}: {k}/{len(a)} ({k / len(a):.0%}; gate 5%)" if a else "")
    runs = [r for r in runs if r["run_id"] not in peek]
    for r in runs:
        r.setdefault("outcome", "infra_error" if r.get("infra_error") else "unscored")
    cells = defaultdict(Counter)
    for r in runs:
        cells[(r["problem"], r["arm"])][r["outcome"]] += 1
    print("| Problem | Group | Arm | " + " | ".join(OUTCOMES) + " |")
    print("|---|---|---|" + "---|" * len(OUTCOMES))
    for (p, arm), c in sorted(cells.items()):
        print(f"| {p} | {'A' if p in GROUP_A else 'B'} | {arm} | " + " | ".join(str(c[o]) for o in OUTCOMES) + " |")
    print()
    for arm in sorted({r["arm"] for r in runs if r["arm"].startswith("ai")}) + ["restart"]:
        a = [r for r in runs if r["arm"] == arm and r["problem"] in GROUP_A]
        print(f"Group A, arm {arm}: temporary / passed round 1 = {rate(a)}")
        for p in sorted(GROUP_A):
            print(f"  {p}: {rate([r for r in a if r['problem'] == p])}")
    b = [r for r in runs if r["problem"] not in GROUP_A and r.get("outcome") in ("temporary", "durable")]
    print(f"Group B: SREGym passed but round 2 or 3 failed = {sum(r['outcome'] == 'temporary' for r in b)}/{len(b)}")


if __name__ == "__main__":
    main()

