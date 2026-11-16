"""Pooled analysis of the two main datasets (Haiku v3, Gemini v3) for the thesis and the paper.

The primary analysis of each model remains analysis.py (PRE-REGISTRATION section 9). This file pools the sets, puts
them side by side, draws the figures, and adds EXPLORATORY analyses (marked in the report): timeouts, pass^k, CMH
pooled across models, and sensitivity to the peek definition. Runs flagged peek are excluded, as in the primary analysis.

Run (needs numpy, scipy, matplotlib; see requirements.txt):
  ../.venv/bin/python cross_model.py   ->  ../results/cross_model.md, ../results/figures/*.pdf|png
"""
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

import analysis as A
import agent_llm
from mechanism import (CODE_FIX, FAULT_FILES, NEUTRALIZE_SIG, REMOVAL, REPAIR_SIG, config_repair,  # noqa: F401
                       defect_gone, diff_lines, env_changes, mechanism, removes_defect, repair)

RESULTS = Path(__file__).resolve().parent.parent / "results"
FIG = RESULTS / "figures"
DATASETS = [  # (display name, directory, figure label)
    ("Haiku 5.5", "v3-haiku55-main", "Haiku 5.5"),
    ("Gemini 3.8 Flash", "v3-gemini-main", "Gemini Flash, 300 s"),
]
AI_ARMS = ["agent_mitigate", "agent_remediate", "agent_free"]
# Auxiliary sets for checking that the repair-mechanism findings repeat (not pooled; see results/README.md)
AUX = [("v2 Haiku 5.5 (peek gate failed)", "v2-haiku55-main"), ("Haiku 4.5 pilot (reasoning high)", "v2-haiku-pilot")]
ARM_EN = {"idle": "idle", "restart_loop": "restart", "agent_mitigate": "AI mitigate", "agent_remediate": "AI remediate",
          "agent_free": "AI free"}
FAULTS = ["F%d" % i for i in range(1, 13)]
# Figure width = sn-jnl text width (372 pt). At \linewidth, 8 pt text stays about 8 pt in the Springer build and about 9.8 pt
# in the article build (455 pt text width); Springer's figure guide asks for 8-12 pt text at print size.
FIG_W = 5.1
real, temp, mitig = A.real, A.temp, A.mitig
timed_out = lambda r: bool(r["flags"].get("timed_out"))  # noqa: E731
peek = lambda r: bool(r["flags"].get("peek"))  # noqa: E731


def load(d):
    p = RESULTS / d / "pilot_results.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows


def pct(x):
    return "–" if x != x else f"{x:.2f}"


def pass_hat_k(c, n, k):
    """Unbiased estimate of P(all k repeats really recover) from c/n (the tau-bench method)."""
    return comb(c, k) / comb(n, k) if n >= k else float("nan")


def section_outcomes(data):
    out = ["## 1. Results by arm (peek runs excluded; 95% CI, fault-level bootstrap)", "",
           "| Model | Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | Usual scoring calls it recovered (MSR) | Temporary share of MSR | Timed out |",
           "|---|---|---|---|---|---|---|---|"]
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        for arm in A.ARMS:
            g = [r for r in main if r["arm"] == arm]
            if not g:
                continue
            out.append(f"| {name} | {arm} | {len(g)} | {A.fmt(*A.boot_ci(g, A.rate(real)))} | {A.fmt(*A.boot_ci(g, A.rate(temp)))} | "
                       f"{A.fmt(*A.boot_ci(g, A.rate(mitig)))} | {A.fmt(*A.boot_ci(g, A.ratio(temp, mitig)))} | "
                       f"{sum(map(timed_out, g))}/{len(g)} |")
    return out


def section_contrasts(data):
    out = ["", "## 2. Arm comparisons within each model (CMH stratified by fault, as in the primary analysis)", "",
           "| Model | Pair | Metric | Rate difference [CI] | OR (MH) | p |", "|---|---|---|---|---|---|"]
    pairs = [("agent_mitigate", "agent_remediate"), ("agent_mitigate", "agent_free"), ("agent_remediate", "agent_free")]
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        for a, b in pairs:
            ra = [r for r in main if r["arm"] == a]
            rb = [r for r in main if r["arm"] == b]
            if not ra or not rb:
                continue
            for label, pred in (("RSR", real), ("MSR", mitig)):
                def diff(rr, pred=pred, a=a, b=b):
                    x = [r for r in rr if r["arm"] == a]
                    y = [r for r in rr if r["arm"] == b]
                    return A.rate(pred)(x) - A.rate(pred)(y) if x and y else float("nan")
                d, ci = A.boot_ci(ra + rb, diff)
                o, p = A.cmh(ra, rb, pred)
                out.append(f"| {name} | {a} − {b} | {label} | {A.fmt(d, ci)} | {o:.2f} | {p:.4f} |")
    return out


def section_aam(data):
    out = ["", "## 3. AAM of the free arm, split by timeout", "",
           "| Model | All | Group A | Group B | Not timed out | Timed out |", "|---|---|---|---|---|---|"]
    for name, rows in data:
        free = [r for r in rows if r["arm"] == "agent_free" and not peek(r)]
        ok = lambda r: r["action_type"] == A.REQUIRED[r["fault_group"]]  # noqa: E731
        cell = lambda g: f"{sum(map(ok, g))}/{len(g)}" if g else "–"  # noqa: E731
        out.append(f"| {name} | {A.fmt(*A.boot_ci(free, A.rate(ok)))} | {cell([r for r in free if r['fault_group'] == 'A'])} | "
                   f"{cell([r for r in free if r['fault_group'] == 'B'])} | {cell([r for r in free if not timed_out(r)])} | "
                   f"{cell([r for r in free if timed_out(r)])} |")
    return out


def section_faults(data):
    out = ["", "## 4. By fault: real / temporary / runs (peek excluded)", ""]
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        arms = [a for a in A.ARMS if any(r["arm"] == a for r in main)]
        out += [f"**{name}**", "", "| Fault | Group | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
        for f in FAULTS:
            g = [r for r in main if r["problem_id"] == f]
            if not g:
                continue
            cells = []
            for a in arms:
                h = [r for r in g if r["arm"] == a]
                to = sum(map(timed_out, h))
                cells.append(f"{sum(map(real, h))}/{sum(map(temp, h))}/{len(h)}" + (f" (timeout {to})" if to else ""))
            out.append(f"| {f} | {g[0]['fault_group']} | " + " | ".join(cells) + " |")
        out.append("")
    out.append("Cell: real/temporary/runs; \"timeout\" = runs that timed out.")
    return out


def section_exploratory(data):
    out = ["", "## 5. Exploratory analyses (outside the pre-registered plan)", "",
           "### 5.1 pass^k: probability that k repeats on the same fault all really recover (mean over faults)", "",
           "| Model | Arm | k=1 | k=3 |", "|---|---|---|---|"]
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        for arm in AI_ARMS:
            vals = defaultdict(list)
            for f in FAULTS:
                h = [r for r in main if r["arm"] == arm and r["problem_id"] == f]
                for k in (1, 3):
                    v = pass_hat_k(sum(map(real, h)), len(h), k)
                    if v == v:
                        vals[k].append(v)
            if vals[1]:
                out.append(f"| {name} | {arm} | " + " | ".join(pct(sum(vals[k]) / len(vals[k])) if vals[k] else "–"
                                                            for k in (1, 3)) + " |")
    out += ["", "Unbiased estimate C(c,k)/C(n,k) per fault, then the mean; faults left with fewer than k runs (after peek exclusion) are dropped.", "",
            "### 5.2 Real recovery without timeouts", "", "| Model | Arm | Not timed out: real recovery | Timed out: real recovery |",
            "|---|---|---|---|"]
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        for arm in AI_ARMS:
            g = [r for r in main if r["arm"] == arm]
            a = [r for r in g if not timed_out(r)]
            b = [r for r in g if timed_out(r)]
            out.append(f"| {name} | {arm} | {sum(map(real, a))}/{len(a)} | {sum(map(real, b))}/{len(b)} |")
    return out


def key(r):
    return r["problem_id"], r["arm"], r["run_index"]


def peek_sets(d, rows):
    """Two peek definitions for a set: (successful access, string match). Sets with the peek_any flag (since
    2026-11-07) store both; earlier sets stored only the string-match flag (peek), so the success definition is
    recomputed from the evidence with the same agent_llm function, without changing the data. The recomputation needs
    the command output, which the public copy removes, so its result is cached in <set>/peek_success.json
    (written by --write-peek-success from the full evidence) and read from there when present."""
    if any("peek_any" in r["flags"] for r in rows):
        return {key(r) for r in rows if peek(r)}, {key(r) for r in rows if r["flags"].get("peek_any")}
    cache = RESULTS / d / "peek_success.json"
    if cache.exists():
        return {tuple(k) for k in json.loads(cache.read_text())}, {key(r) for r in rows if peek(r)}
    return success_peeks(d), {key(r) for r in rows if peek(r)}


def success_peeks(d):
    """Runs of a set flagged under the success definition, recomputed from the full evidence (agent_llm.peek_flags)."""
    succ = set()
    for l in (RESULTS / d / "run_evidence.jsonl").read_text().splitlines():
        e = json.loads(l)
        files = [str(RESULTS / d / f) for f in e.get("transcript_files") or []]
        calls = agent_llm.transcript_calls(files) if files else e.get("tool_calls", [])
        if agent_llm.peek_flags(agent_llm.scan_targets(e.get("commands", []), calls)):
            succ.add(key(e))
    return succ


def section_peek_definitions(dirs):
    out = ["", "### 5.3 Sensitivity to the peek definition", "",
           "String match: a command containing a marker counts (the definition used when Haiku v3 ran). Successful access: counts only when "
           "the output shows the command obtained information, or the command went through Docker (definition fixed 2026-11-07, primary analysis of "
           "Gemini v3). Sets that lack the second flag are recomputed from the evidence (`agent_llm.peek_flags`), without changing the data.", "",
           "| Model | Arm | Primary analysis uses | Peek: successful / string match | RSR, excluding by successful access "
           "| RSR, excluding by string match |", "|---|---|---|---|---|---|"]
    for name, d, rows in dirs:
        succ, string = peek_sets(d, rows)
        primary = "successful" if any("peek_any" in r["flags"] for r in rows) else "string match"
        for arm in AI_ARMS:
            g = [r for r in rows if r["arm"] == arm]
            g1 = [r for r in g if key(r) not in succ]
            g2 = [r for r in g if key(r) not in string]
            out.append(f"| {name} | {arm} | {primary} | {len(g) - len(g1)} / {len(g) - len(g2)} | "
                       f"{A.fmt(*A.boot_ci(g1, A.rate(real)))} (N={len(g1)}) | {A.fmt(*A.boot_ci(g2, A.rate(real)))} (N={len(g2)}) |")
    out += ["", "| Model | Pair (RSR, CMH) | OR, p: excluding by successful access | OR, p: excluding by string match |", "|---|---|---|---|"]
    for name, d, rows in dirs:
        succ, string = peek_sets(d, rows)
        for b in ("agent_remediate", "agent_free"):
            cells = []
            for drop in (succ, string):
                kept = [r for r in rows if key(r) not in drop]
                o, p = A.cmh([r for r in kept if r["arm"] == "agent_mitigate"], [r for r in kept if r["arm"] == b], real)
                cells.append(f"{o:.2f}, {p:.4f}")
            out.append(f"| {name} | agent_mitigate − {b} | {cells[0]} | {cells[1]} |")
    return out




def load_evidence(d):
    ev = {}
    with open(RESULTS / d / "run_evidence.jsonl") as fh:
        for l in fh:
            e = json.loads(l)
            ev[(e["problem_id"], e["arm"], e["run_index"])] = {k: e.get(k) for k in ("code_files", "config_changed", "diff")}
    return ev


def section_mechanism(dirs):
    out = ["", "### 5.4 Mechanism of the real recoveries (by the files the agent changed)", "",
           "Group-B faults live in the code and the reference fix is code. A real recovery without a code change (only `.env`) is a durable workaround: "
           "it passes all three rounds but does not fix the cause (for example `POOL_MAX=1` on F9 removes concurrency, `LOG_LEVEL=warn` on F11 "
           "only slows the log growth). \"Other layer\" means a code fix outside the faulty file, listed by fault at the end of this section. Group A: "
           "rollback to the previous release's value, or the faulty variable changed to another value (the remediation prompt forces a code change).", "",
           "| Model | Arm | Real recoveries | Mechanism (runs) |", "|---|---|---|---|"]
    evs = {}
    for name, d, rows in dirs:
        ev = evs[d] = load_evidence(d)
        for arm in AI_ARMS:
            g = [r for r in rows if r["arm"] == arm and not peek(r) and real(r)]
            c = Counter(mechanism(r, ev[(r["problem_id"], r["arm"], r["run_index"])]) for r in g)
            out.append(f"| {name} | {arm} | {len(g)} | " + "; ".join(f"{k} {v}" for k, v in sorted(c.items())) + " |")
    out += ["", "Group-B faults only (9): real recovery by the oracle, and real recovery with the fault removed from the code (code changed and matches "
            "that fault's repair signature, or the faulty part was removed while the feature still works; `REPAIR_SIG`, `REMOVAL`), 95% CI, fault-level bootstrap. "
            "The \"strict\" column counts F2 runs that drop the transaction as workarounds: the connection leak is gone, but an order whose charge fails stays "
            "`pending` instead of being deleted by `ROLLBACK` (the F2 criterion does not check this):", "",
            "| Model | Arm | N | RSR (oracle) | RSR, fault removed from code | RSR, fault removed, strict | Configuration workaround | Workaround in code "
            "| Faulty part removed |",
            "|---|---|---|---|---|---|---|---|---|"]
    for name, d, rows in dirs:
        ev = evs[d]
        for arm in AI_ARMS:
            g = [r for r in rows if r["arm"] == arm and not peek(r) and r["fault_group"] == "B"]
            e_of = lambda r, ev=ev: ev[(r["problem_id"], r["arm"], r["run_index"])]  # noqa: E731
            rc = lambda r: real(r) and removes_defect(r, e_of(r))  # noqa: E731
            strict = lambda r: rc(r) and not repair(r, e_of(r)).endswith("drops the transaction")  # noqa: E731
            fixed = [r for r in g if real(r)]
            wk = sum(1 for r in fixed if mechanism(r, e_of(r)) == "B: configuration workaround")
            code = [repair(r, e_of(r)) for r in fixed if mechanism(r, e_of(r)) in CODE_FIX]
            out.append(f"| {name} | {arm} | {len(g)} | {A.fmt(*A.boot_ci(g, A.rate(real)))} | {A.fmt(*A.boot_ci(g, A.rate(rc)))} | "
                       f"{A.fmt(*A.boot_ci(g, A.rate(strict)))} | "
                       f"{wk} | {sum(k.startswith('workaround') for k in code)} | {sum(k.startswith('removes') for k in code)} |")
    out += ["", "Real recoveries that changed code but do not \"fix the cause\":", ""]
    for name, d, rows in dirs:
        c = Counter((r["problem_id"], repair(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]))
                    for r in rows if not peek(r) and real(r) and r["fault_group"] == "B"
                    and mechanism(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) in CODE_FIX
                    and repair(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) != "fixes the cause")
        out.append(f"- {name}: " + ("; ".join(f"{f} {k} {n}" for (f, k), n in sorted(c.items())) or "none"))
    out += ["", "A second check, independent of the repair signature (`defect_gone`: the faulty structure of the release is gone; only F2, F3, "
            "F5, F7), on the runs that \"fix the cause\". For F4, F6, F9, F10, F11 the lines that carry each fix were read for every run "
            "of both v3 sets (full diffs for the exceptions):", ""]
    for name, d, rows in dirs:
        g = [defect_gone(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) for r in rows
             if not peek(r) and real(r) and r["fault_group"] == "B"
             and mechanism(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) in CODE_FIX
             and repair(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) == "fixes the cause"]
        out.append(f"- {name}: pass {sum(x is True for x in g)}, fail {sum(x is False for x in g)}")
    out += ["", "Group A (configuration faults): real recoveries by how the faulty variable was handled (`config_repair`):", "",
            "| Model | Arm | Real recoveries | Handling (runs) |", "|---|---|---|---|"]
    for name, d, rows in dirs:
        for arm in AI_ARMS:
            g = [r for r in rows if r["arm"] == arm and not peek(r) and real(r) and r["fault_group"] == "A"]
            c = Counter(config_repair(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) for r in g)
            out.append(f"| {name} | {arm} | {len(g)} | " + "; ".join(f"{k} {v}" for k, v in sorted(c.items())) + " |")
    out += ["", "Real recoveries with \"code fix, other layer\", by fault and by the files the agent changed:", ""]
    for name, d, rows in dirs:
        c = Counter((r["problem_id"], ", ".join(sorted(evs[d][(r["problem_id"], r["arm"], r["run_index"])]["code_files"])))
                    for r in rows if not peek(r) and real(r)
                    and mechanism(r, evs[d][(r["problem_id"], r["arm"], r["run_index"])]) == "B: code fix, other layer")
        out.append(f"- {name}: " + ("; ".join(f"{f} `{files}` {n}" for (f, files), n in sorted(c.items())) or "none"))
    out += ["", "Read by hand (2026-11-12, both v3 sets): all 14 F10 runs add a retry mechanism (`attempts`/`backoff` on the "
            "queue, or a retry loop in the worker; 6 runs name status 429 directly), which fixes the cause. The single F4 run (Haiku, agent_remediate, run 7) deletes the currency conversion step in `orders.js`: JPY orders are "
            "charged the unconverted amount, yet the run passes the oracle because the F4 criterion checks only that orders are paid and that the partner accepts the "
            "transaction, not the amount. The other nine real F4 recoveries by Haiku add the JPY rate back in `currency.js` "
            "(7 runs use 0.0067 as in the reference; 2 runs use 0.67 and 0.633, which are right if JPY amounts are taken as yen under ISO 4217)."]
    out += ["", "Runs that match no repair signature, read by hand (2026-11-12, both v3 sets): 7 F2 runs (Haiku) drop the transaction, "
            "running each statement with `pool.query`: no connection is held, including during the partner call; all 7 diffs are the same and add no "
            "error handling, so when a charge fails the order stays `pending` (the original `ROLLBACK` deleted it), a change in failure behavior "
            "that the F2 criterion does not check (reread 2026-11-12). 4 F6 runs (Haiku) remove the "
            "cache entirely: no memory leak, no cache. The F11 run (Haiku, agent_free, run 7) sets `LOG_LEVEL=warn` and wraps the log write "
            "in `try/catch` (swallowing the error when the disk is full), without restoring log rotation. Sampled runs that match a signature: F9 locks "
            "in a fixed order (sorting, `Math.min`, a ternary, `ANY` with `ORDER BY`), F6 caps the number of cache entries, F11 rotates "
            "or truncates the log file."]
    out += ["", "Group A, read by hand: the 5 F12 runs that leave the faulty variable unchanged (2026-11-12): 2 Haiku runs cap the partner call timeout at 500 ms "
            "in the code (neutralizing the bad setting); 3 runs raise the number of parallel workers (Haiku agent_remediate runs 4 and 7; Gemini "
            "agent_free run 2, with a price cache): 20 orders finish within 10 s although each still waits 3 s for the slow partner, and the 60 s timeout stays."]
    return out


def section_drop_one(data):
    out = ["", "### 5.7 Leave one fault out (robustness with only 12 faults as units)", "",
           "CMH on RSR recomputed with each fault left out in turn; the same for the temporary share of MSR in the mitigation arm.", "",
           "| Model | Comparison | OR, all 12 faults | OR with one fault left out | Largest p (fault left out) | Smallest p (fault left out) |",
           "|---|---|---|---|---|---|"]
    shares = []
    for name, rows in data:
        main = [r for r in rows if not peek(r)]
        for a, b in (("agent_mitigate", "agent_remediate"), ("agent_mitigate", "agent_free")):
            res = []
            for f in FAULTS:
                o, p = A.cmh([r for r in main if r["arm"] == a and r["problem_id"] != f],
                             [r for r in main if r["arm"] == b and r["problem_id"] != f], real)
                res.append((f, o, p))
            o, p = A.cmh([r for r in main if r["arm"] == a], [r for r in main if r["arm"] == b], real)
            hi, lo = max(res, key=lambda x: x[2]), min(res, key=lambda x: x[2])
            out.append(f"| {name} | {a} − {b} | {o:.2f} (p = {p:.4f}) | {min(x[1] for x in res):.2f}–{max(x[1] for x in res):.2f} | "
                       f"{hi[2]:.4f} ({hi[0]}) | {lo[2]:.4f} ({lo[0]}) |")
        mit = [r for r in main if r["arm"] == "agent_mitigate"]
        s = [(f, A.ratio(temp, mitig)([r for r in mit if r["problem_id"] != f])) for f in FAULTS]
        lo, hi = min(s, key=lambda x: x[1]), max(s, key=lambda x: x[1])
        shares.append(f"- {name}: {A.ratio(temp, mitig)(mit):.2f} with all 12 faults; {lo[1]:.2f} (without {lo[0]}) to {hi[1]:.2f} (without {hi[0]})")
    return out + ["", "Temporary share of MSR, mitigation arm, with one fault left out:", ""] + shares


def section_aux():
    out = ["", "### 5.6 Repair mechanism on the auxiliary sets (replication check; not pooled with the main results)", "",
           "Same 12 faults, same oracle, same `mechanism.py` rules; runs flagged `peek` under the definition in force at the time are excluded. v2 Haiku 5.5: "
           "the partner ran in Docker and the peek gate failed. Pilot: Haiku 4.5, N = 3, reasoning effort `high`.", "",
           "| Set | Arm | N group B | RSR (oracle) | RSR, fault removed from code | RSR, fault removed, strict | Configuration workaround | Workaround in code "
           "| Group A: faulty setting kept |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, d in AUX:
        rows = load(d)
        if not rows:
            continue
        ev = load_evidence(d)
        e_of = lambda r, ev=ev: ev[(r["problem_id"], r["arm"], r["run_index"])]  # noqa: E731
        for arm in AI_ARMS:
            g = [r for r in rows if r["arm"] == arm and not peek(r)]
            b = [r for r in g if r["fault_group"] == "B"]
            fixed = [r for r in b if real(r)]
            rc = lambda r: real(r) and removes_defect(r, e_of(r))  # noqa: E731
            strict = lambda r: rc(r) and not repair(r, e_of(r)).endswith("drops the transaction")  # noqa: E731
            wk = sum(mechanism(r, e_of(r)) == "B: configuration workaround" for r in fixed)
            ck = sum(mechanism(r, e_of(r)) in CODE_FIX and repair(r, e_of(r)).startswith("workaround") for r in fixed)
            ak = sum(config_repair(r, e_of(r)).startswith("workaround") for r in g if r["fault_group"] == "A" and real(r))
            out.append(f"| {name} | {arm} | {len(b)} | {A.fmt(*A.boot_ci(b, A.rate(real)))} | "
                       f"{A.fmt(*A.boot_ci(b, A.rate(rc)))} | {A.fmt(*A.boot_ci(b, A.rate(strict)))} | {wk} | {ck} | {ak} |")
    out += ["", "Read by hand (2026-11-12): the configuration workarounds in the mitigation arm are `POOL_MAX=1` on F9 (v2: 7, pilot: 2) and "
            "`LOG_LEVEL=warn` on F11 (v2: 1); 3 group-A runs in v2 raise the worker count on F12, as in v3; v2 run F1 agent_remediate "
            "2 clamps the timeout below the minimum in the code (neutralizing the bad setting; the F1 rule was widened after this reading). "
            "5 v2 F2 runs drop the transaction (agent_remediate runs 5, 8, 9; agent_free runs 0, 7) in the same way as in v3: three separate "
            "statements, no error handling; run 8 adds a step that skips orders already `paid`, but an order whose charge fails still stays `pending` (read by hand 2026-11-12)."]
    return out


def cost(rows, d):
    """Each agent run (peek excluded): (arm, action time in s, input tokens, cache-read share, output tokens or None)."""
    usage = {}
    with open(RESULTS / d / "run_evidence.jsonl") as fh:
        for l in fh:
            e = json.loads(l)
            usage[(e["problem_id"], e["arm"], e["run_index"])] = e.get("usage") or {}
    out = []
    for r in rows:
        if r["arm"] in AI_ARMS and not peek(r):
            u = usage.get((r["problem_id"], r["arm"], r["run_index"]), {})
            tin = u.get("input_tokens")
            out.append((r["arm"], r["action_duration_s"], tin, (u.get("cached_input_tokens") or 0) / tin if tin else None,
                        u.get("output_tokens")))
    return out


def section_cost(dirs):
    from statistics import median
    out = ["", "### 5.5 Cost per agent run (descriptive)", "",
           "Action time: from ticket handover until the agent stops (`action_duration_s`). Tokens come from Codex's final event; "
           "timed-out runs have no token count, so the token columns cover only runs that have one (for Gemini, the runs that finished in time, which lean toward easy faults).", "",
           "| Model | Arm | N | Time, median (s) | Runs with tokens | Input tokens, median (millions) | Cache-read share, median | Output tokens, median |",
           "|---|---|---|---|---|---|---|---|"]
    for name, d, rows in dirs:
        c = cost(rows, d)
        for arm in AI_ARMS:
            g = [x for x in c if x[0] == arm]
            t = [x for x in g if x[2]]
            out.append(f"| {name} | {arm} | {len(g)} | {median(x[1] for x in g):.0f} | {len(t)} | "
                       + (f"{median(x[2] for x in t) / 1e6:.2f} | {median(x[3] for x in t):.2f} | {median(x[4] for x in t):,.0f} |"
                          if t else "– | – | – |"))
    return out


def oracle_cost(rows, d):
    """Time per oracle round, each run (peek excluded): (arm, whole run s, round 1, round 2 or None, round 3 or None).
    Round boundaries come from the timeline marks (vong_1, vong_2, vong_3_trien_khai_lai); the last round ends at duration_s
    (recorded right after scoring, same t0 as the timeline). Round 3 includes teardown, stack rebuild, and the readiness wait."""
    marks = {}
    with open(RESULTS / d / "run_evidence.jsonl") as fh:
        for l in fh:
            e = json.loads(l)
            marks[key(e)] = {m["label"]: m["t"] for m in (e.get("timeline") or {}).get("marks", [])}
    out = []
    for r in rows:
        m = marks.get(key(r), {})
        if peek(r) or "vong_1" not in m:
            continue
        end = r["duration_s"]
        r1 = m.get("vong_2", end) - m["vong_1"]
        r2 = m.get("vong_3_trien_khai_lai", end) - m["vong_2"] if "vong_2" in m else None
        r3 = end - m["vong_3_trien_khai_lai"] if "vong_3_trien_khai_lai" in m else None
        out.append((r["arm"], end, r1, r2, r3))
    return out


def oracle_cost_summary(rows, d):
    """Summary numbers for the paper: median of round 2 and round 3 (runs that reached that round), the share of rounds 2+3
    in the whole run for runs with all three rounds, and the mean added time per run over all runs (a round not run counts as 0)."""
    from statistics import mean, median
    c = oracle_cost(rows, d)
    full = [x for x in c if x[4] is not None]
    return {
        "n": len(c), "n2": sum(x[3] is not None for x in c), "n3": len(full),
        "r1": median(x[2] for x in c),
        "r2": median(x[3] for x in c if x[3] is not None),
        "r3": median(x[4] for x in full),
        "episode": median(x[1] for x in full),
        "share": median((x[3] + x[4]) / x[1] for x in full),
        "added": mean((x[3] or 0) + (x[4] or 0) for x in c),
    }


def section_oracle_cost(dirs):
    out = ["", "### 5.8 Time cost of the oracle (descriptive)", "",
           "All runs (including arms without an agent), peek excluded. A round runs only if the previous one passed; round 3 includes teardown, stack rebuild, "
           "and the readiness wait. \"Added per run\" is the time of rounds 2 and 3 together, averaged over all runs (a round not run counts as 0).", "",
           "| Model | Runs | With round 2 | With round 3 | Round 1, median (s) | Round 2, median (s) | Round 3, median (s) | "
           "Whole run with all three rounds, median (s) | Share of rounds 2+3 in that run, median | Added per run, mean (s) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name, d, rows in dirs:
        s = oracle_cost_summary(rows, d)
        out.append(f"| {name} | {s['n']} | {s['n2']} | {s['n3']} | {s['r1']:.0f} | {s['r2']:.0f} | {s['r3']:.0f} | "
                   f"{s['episode']:.0f} | {s['share']:.2f} | {s['added']:.0f} |")
    return out


def save(fig, name):
    """Save the figure as PDF and PNG. The PDF has no creation date, so a rerun from a clone gives a byte-identical file."""
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight",
                    **({"metadata": {"CreationDate": None}} if ext == "pdf" else {}))


def figures(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "pdf.fonttype": 42})
    colors = {"real": "#1b7837", "temp": "#f1a340", "none": "#bdbdbd"}
    widths = [len({r["arm"] for r in rows}) for _, rows in data]
    fig, axes = plt.subplots(1, len(data), figsize=(FIG_W, 2.4), sharey=True,
                             gridspec_kw={"width_ratios": widths, "wspace": 0.12})
    axes = axes if len(data) > 1 else [axes]
    for ax, (label, rows) in zip(axes, data):
        main = [r for r in rows if not peek(r)]
        arms = [a for a in A.ARMS if any(r["arm"] == a for r in main)]
        bottom = [0.0] * len(arms)
        for v in ("real", "temp", "none"):
            vals = [sum(1 for r in main if r["arm"] == a and r["verdict"] == v) / max(1, sum(1 for r in main if r["arm"] == a))
                    for a in arms]
            ax.bar(range(len(arms)), vals, bottom=bottom, color=colors[v],
                   label={"real": "durable fix (pass R1–R3)", "temp": "temporary fix (pass R1, fail R2/R3)",
                          "none": "not recovered"}[v])
            bottom = [b + x for b, x in zip(bottom, vals)]
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels([ARM_EN[a] for a in arms], rotation=35, ha="right")
        ax.set_title(label)
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("share of runs")
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", bbox_to_anchor=(0.5, 0.98), ncol=3, frameon=False, handlelength=1.2,
               columnspacing=1.0)
    save(fig, "outcomes_by_arm")
    plt.close(fig)

    fig, axes = plt.subplots(1, len(data), figsize=(2.2 * len(data) + 0.8, 3.0), sharey=True)
    axes = axes if len(data) > 1 else [axes]
    for ax, (label, rows) in zip(axes, data):
        main = [r for r in rows if not peek(r)]
        mat = []
        for f in FAULTS:
            row = []
            for a in AI_ARMS:
                h = [r for r in main if r["problem_id"] == f and r["arm"] == a]
                row.append(sum(map(real, h)) / len(h) if h else float("nan"))
            mat.append(row)
        im = ax.imshow(mat, vmin=0, vmax=1, cmap="Greens", aspect="auto")
        ax.set_xticks(range(len(AI_ARMS)))
        ax.set_xticklabels([ARM_EN[a].replace("AI ", "") for a in AI_ARMS], rotation=35, ha="right")
        ax.set_yticks(range(len(FAULTS)))
        ax.set_yticklabels([f + (" (A)" if f in ("F1", "F8", "F12") else "") for f in FAULTS])
        ax.set_title(label)
        for i, row in enumerate(mat):
            for j, v in enumerate(row):
                if v == v:
                    ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=8, color="white" if v > 0.6 else "black")
    fig.colorbar(im, ax=axes, shrink=0.8, label="durable-fix rate")
    save(fig, "real_fix_by_fault")
    plt.close(fig)


def figure_mechanism(dirs):
    """Figure 3: the 9 group-B faults, real recovery split into fault removal and durable workarounds (config or code)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    en = {d: label for _, d, label in DATASETS}
    parts = [("repair", "durable fix, defect removed", "#1b7837"), ("workaround", "durable workaround, defect remains", "#762a83"),
             ("temp", "temporary fix", "#f1a340"), ("none", "not recovered", "#bdbdbd")]
    plt.rcParams.update({"font.size": 8, "pdf.fonttype": 42})
    fig, axes = plt.subplots(1, len(dirs), figsize=(FIG_W, 2.4), sharey=True)
    axes = axes if len(dirs) > 1 else [axes]
    for ax, (_, d, rows) in zip(axes, dirs):
        ev = load_evidence(d)

        def part(r):
            if real(r):
                return "repair" if removes_defect(r, ev[(r["problem_id"], r["arm"], r["run_index"])]) else "workaround"
            return "temp" if temp(r) else "none"
        bottom = [0.0] * len(AI_ARMS)
        for key, label, color in parts:
            vals = []
            for a in AI_ARMS:
                g = [r for r in rows if r["arm"] == a and not peek(r) and r["fault_group"] == "B"]
                vals.append(sum(part(r) == key for r in g) / max(1, len(g)))
            ax.bar(range(len(AI_ARMS)), vals, bottom=bottom, color=color, label=label)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(range(len(AI_ARMS)))
        ax.set_xticklabels([ARM_EN[a] for a in AI_ARMS], rotation=35, ha="right")
        ax.set_title(en[d])
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("share of runs, code faults")
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", bbox_to_anchor=(0.5, 0.98), ncol=2, frameon=False, handlelength=1.2,
               columnspacing=1.0)
    save(fig, "code_fault_mechanism")
    plt.close(fig)


def main():
    data, labels, dirs = [], [], []
    for name, d, en in DATASETS:
        rows = load(d)
        if rows:
            data.append((name, rows))
            labels.append((en, rows))
            dirs.append((name, d, rows))
    head = ["# Pooled analysis of the datasets", "",
            "Generated by `remediation-oracle/cross_model.py`. Primary analysis of each model: `<set>/analysis.md`. "
            "Sets included: " + ", ".join(f"{n} ({len(r)} runs, peek {sum(map(peek, r))})" for n, r in data) + ".", ""]
    text = "\n".join(head + section_outcomes(data) + section_contrasts(data) + section_aam(data) + section_faults(data)
                     + section_exploratory(data) + section_peek_definitions(dirs) + section_mechanism(dirs)
                     + section_cost(dirs) + section_aux() + section_drop_one(data) + section_oracle_cost(dirs)) + "\n"
    (RESULTS / "cross_model.md").write_text(text)
    figures(labels)
    figure_mechanism(dirs)
    print(text)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--write-peek-success"]:  # run on the full evidence of the working repository
        for d in sys.argv[2:]:
            (RESULTS / d / "peek_success.json").write_text(json.dumps(sorted(success_peeks(d))) + "\n")
        sys.exit(0)
    sys.exit(main())
