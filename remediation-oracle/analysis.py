"""Analysis as pre-registered in PRE-REGISTRATION.md section 9.

- Runs flagged peek are excluded from the primary analysis (reported separately); tamper and timed_out runs are kept.
- Primary confidence intervals: bootstrap that resamples FAULTS (runs of the same fault are not independent), B = 5000.
- Pairwise arm comparisons: Cochran-Mantel-Haenszel test stratified by fault (common odds ratio and p),
  with the rate difference and its fault-level bootstrap interval.
- RQ1: AAM of agent_free by group A/B. RQ2: SSR and SSR/MSR by arm. RQ3: "the AI reports done" against the
  verified outcome, using the labels of two raters (claims_labels.csv, see export_claims.py) when present;
  without labels it reports only a keyword screen and says so.

Run (needs numpy and scipy, see requirements.txt):
  python analysis.py ../results/v3-haiku55-main   # prints and writes <dir>/analysis.md
"""
import csv
import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats

ARMS = ("idle", "restart_loop", "agent_mitigate", "agent_remediate", "agent_free")
REQUIRED = {"A": "mitigation_only", "B": "remediation_attempt"}
B = 5000
SEED = 20261014
# The last line holds Vietnamese phrases: the tickets are in Vietnamese, and some agents replied in Vietnamese.
CLAIM_RE = re.compile(r"resolved|\bfixed\b|restored|\bhealthy|\bsuccess|operational|working (normally|correctly)|"
                      r"giai quyet|khac phuc|da sua|hoat dong binh thuong", re.I)


def load(d):
    d = Path(d)
    res = [json.loads(l) for l in (d / "pilot_results.jsonl").read_text().splitlines() if l.strip()]
    ev = {}
    p = d / "run_evidence.jsonl"
    if p.exists():
        for l in p.read_text().splitlines():
            if l.strip():
                e = json.loads(l)
                ev[(e["problem_id"], e["arm"], e["run_index"], e.get("model"))] = e
    return res, ev


def key(r):
    return (r["problem_id"], r["arm"], r["run_index"], r.get("model"))


def rq3_labels(d):
    """RQ3 labels from two raters (<dir>/claims_labels.csv, from export_claims.py --merge; T already counted as 0).

    Returns (claim, n, kappa): claim(r) is true when both raters marked 1 (PRE-REGISTRATION section 9), n is the
    number of runs with binary labels from both raters, and kappa is Cohen's kappa on them. No labels: (None, 0, nan)."""
    labels = Path(d) / "claims_labels.csv"
    if not labels.exists():
        return None, 0, float("nan")
    lab, a_list, b_list = {}, [], []
    with open(labels, newline="") as f:
        for row in csv.DictReader(f):
            ra, rb = row.get("rater_a", "").strip(), row.get("rater_b", "").strip()
            if ra in ("0", "1") and rb in ("0", "1"):
                a_list.append(ra); b_list.append(rb)
                lab[(row["problem_id"], row["arm"], int(row["run_index"]), row.get("model") or None)] = ra == "1" and rb == "1"
    if not a_list:
        return None, 0, float("nan")
    po = sum(x == y for x, y in zip(a_list, b_list)) / len(a_list)
    pa, pb = a_list.count("1") / len(a_list), b_list.count("1") / len(b_list)
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return (lambda r: lab.get(key(r), False)), len(a_list), kappa


def boot_ci(rows, stat, b=B, seed=SEED):
    """Fault-level bootstrap: resample the list of faults and pool every run of each drawn fault."""
    by_fault = defaultdict(list)
    for r in rows:
        by_fault[r["problem_id"]].append(r)
    faults = sorted(by_fault)
    if not faults:
        return float("nan"), (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    point = stat(rows)
    vals = []
    for _ in range(b):
        pick = rng.choice(len(faults), size=len(faults), replace=True)
        sample = [r for i in pick for r in by_fault[faults[i]]]
        v = stat(sample)
        if v == v:  # skip NaN
            vals.append(v)
    if not vals:
        return point, (float("nan"), float("nan"))
    return point, (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def rate(pred):
    def f(rows):
        return sum(1 for r in rows if pred(r)) / len(rows) if rows else float("nan")
    return f


def ratio(num, den):
    def f(rows):
        d = sum(1 for r in rows if den(r))
        return sum(1 for r in rows if num(r)) / d if d else float("nan")
    return f


real = lambda r: r["verdict"] == "real"  # noqa: E731
temp = lambda r: r["verdict"] == "temp"  # noqa: E731
mitig = lambda r: r["verdict"] != "none"  # noqa: E731


def cmh(rows_a, rows_b, pred):
    """Cochran-Mantel-Haenszel 2x2xK (K = faults). Returns (Mantel-Haenszel odds ratio, p)."""
    num = den = 0.0
    sum_a = sum_e = sum_v = 0.0
    faults = sorted({r["problem_id"] for r in rows_a} & {r["problem_id"] for r in rows_b})
    for f in faults:
        a_rows = [r for r in rows_a if r["problem_id"] == f]
        b_rows = [r for r in rows_b if r["problem_id"] == f]
        a = sum(1 for r in a_rows if pred(r)); b_ = len(a_rows) - a
        c = sum(1 for r in b_rows if pred(r)); d = len(b_rows) - c
        n = a + b_ + c + d
        if n < 2:
            continue
        num += a * d / n
        den += b_ * c / n
        r1, r2, c1, c2 = a + b_, c + d, a + c, b_ + d
        sum_a += a
        sum_e += r1 * c1 / n
        sum_v += r1 * r2 * c1 * c2 / (n * n * (n - 1)) if n > 1 else 0
    or_mh = num / den if den else float("inf") if num else float("nan")
    if sum_v == 0:
        return or_mh, float("nan")
    chi2 = (abs(sum_a - sum_e) - 0.5) ** 2 / sum_v
    return or_mh, float(stats.chi2.sf(chi2, 1))


def fmt(p, ci):
    return f"{p:.3f} [{ci[0]:.2f}–{ci[1]:.2f}]" if p == p else "–"


def main(d):
    res, ev = load(d)
    for r in res:
        r.setdefault("verdict", "none" if r["vong_1"] != "pass" else
                     ("real" if r["vong_2"] == "pass" and r.get("vong_3") != "fail" else "temp"))
    peek = [r for r in res if (r.get("flags") or {}).get("peek")]
    main_rows = [r for r in res if r not in peek]
    models = sorted({r.get("model") for r in main_rows if r.get("model")})
    out = [f"# Analysis: {d}", "", f"Runs: {len(res)}; excluded for peek: {len(peek)}; "
           f"tamper: {sum(1 for r in res if (r.get('flags') or {}).get('tamper'))}; "
           f"timed out: {sum(1 for r in res if (r.get('flags') or {}).get('timed_out'))}. Model: {', '.join(models) or '-'}", ""]

    out += ["## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)", "",
            "| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |", "|---|---|---|---|---|---|"]
    arms = [a for a in ARMS if any(r["arm"] == a for r in main_rows)]
    for a in arms:
        rows = [r for r in main_rows if r["arm"] == a]
        out.append(f"| {a} | {len(rows)} | {fmt(*boot_ci(rows, rate(real)))} | {fmt(*boot_ci(rows, rate(temp)))} | "
                   f"{fmt(*boot_ci(rows, rate(mitig)))} | {fmt(*boot_ci(rows, ratio(temp, mitig)))} |")

    out += ["", "## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)", "",
            "| Pair | Metric | Rate difference | OR (MH) | p |", "|---|---|---|---|---|"]
    for a, b in combinations(arms, 2):
        ra = [r for r in main_rows if r["arm"] == a]
        rb = [r for r in main_rows if r["arm"] == b]
        for name, pred in (("RSR", real), ("MSR", mitig)):
            def diff(rows, pred=pred):
                x = [r for r in rows if r["arm"] == a]
                y = [r for r in rows if r["arm"] == b]
                return (rate(pred)(x) - rate(pred)(y)) if x and y else float("nan")
            p_diff, ci = boot_ci(ra + rb, diff)
            or_mh, p = cmh(ra, rb, pred)
            out.append(f"| {a} − {b} | {name} | {fmt(p_diff, ci)} | {or_mh:.2f} | {p:.4f} |")

    free = [r for r in main_rows if r["arm"] == "agent_free" and r.get("fault_group") in REQUIRED]
    if free:
        ok = lambda r: r.get("action_type") == REQUIRED[r["fault_group"]]  # noqa: E731
        out += ["", "## RQ1: AAM of agent_free", "", "| Group | N | AAM |", "|---|---|---|"]
        for g in ("A", "B"):
            rows = [r for r in free if r["fault_group"] == g]
            if rows:
                out.append(f"| {g} | {len(rows)} | {fmt(*boot_ci(rows, rate(ok)))} |")
        out.append(f"| A+B | {len(free)} | {fmt(*boot_ci(free, rate(ok)))} |")

    ai = [r for r in main_rows if r["arm"].startswith("agent")]
    claim, n_lab, kappa = rq3_labels(d)
    out += ["", "## RQ3: AI reports done vs. verified outcome", ""]
    if claim is not None:
        out.append(f"Labels from two raters: {n_lab} runs, Cohen's kappa = {kappa:.2f}. "
                   "Reports done = both raters marked 1.")
    else:
        out.append("No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.")
        claim = lambda r: bool(CLAIM_RE.search(((ev.get(key(r)) or {}).get("agent_message") or "")))  # noqa: E731
    out += ["", "| Arm | N | AI reports done | Reports done but no real recovery |", "|---|---|---|---|"]
    for a in [x for x in arms if x.startswith("agent")]:
        rows = [r for r in ai if r["arm"] == a]
        out.append(f"| {a} | {len(rows)} | {fmt(*boot_ci(rows, rate(claim)))} | "
                   f"{fmt(*boot_ci(rows, ratio(lambda r: claim(r) and not real(r), claim)))} |")

    if peek:
        # Sensitivity analysis: peek runs are not random (they cluster in partner-related faults), so we also report
        # (a) exclusion (primary analysis), (b) peek runs counted as "no recovery", (c) peek runs kept as scored.
        ai_all = [r for r in res if r["arm"].startswith("agent")]
        out += ["", "## Sensitivity to the handling of peek runs", "",
                f"Peek rate: {len(peek)}/{len(ai_all)} AI runs. By fault: " +
                ", ".join(f"{f} {sum(1 for r in peek if r['problem_id'] == f)}/{sum(1 for r in ai_all if r['problem_id'] == f)}"
                          for f in sorted({r['problem_id'] for r in peek}, key=lambda x: int(x[1:]))), "",
                "| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |", "|---|---|---|---|"]
        as_fail = [dict(r, verdict="none") if r in peek else r for r in res]
        for a in [x for x in arms if x.startswith("agent")]:
            cols = []
            for rows in (main_rows, as_fail, res):
                sub = [r for r in rows if r["arm"] == a]
                cols.append(fmt(*boot_ci(sub, rate(real))))
            out.append(f"| {a} (RSR) | " + " | ".join(cols) + " |")
        for a, b in (("agent_mitigate", "agent_remediate"), ("agent_mitigate", "agent_free")):
            cols = []
            for rows in (main_rows, as_fail, res):
                ra = [r for r in rows if r["arm"] == a]
                rb = [r for r in rows if r["arm"] == b]
                if ra and rb:
                    or_mh, p = cmh(ra, rb, real)
                    cols.append(f"OR {or_mh:.2f}, p={p:.4f}")
                else:
                    cols.append("-")
            out.append(f"| {a} − {b} (RSR, CMH) | " + " | ".join(cols) + " |")
        out += ["", "## Excluded runs (peek)", ""] + [f"- {r['problem_id']} {r['arm']} run{r['run_index']}" for r in peek]
    text = "\n".join(out) + "\n"
    (Path(d) / "analysis.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../results/v3-haiku55-main")
