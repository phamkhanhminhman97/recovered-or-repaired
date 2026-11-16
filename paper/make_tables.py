"""Generate the LaTeX tables for paper/main.tex directly from results/ (no numbers typed by hand).

Run: ../.venv/bin/python make_tables.py   ->  paper/tables/*.tex
Datasets follow cross_model.DATASETS (the two main sets; E1 was stopped on 2026-11-12 and is not analyzed).
RQ4 (WP2, SREGym) reads results/sregym-wp2[-hydrogen]/runs.jsonl from sregym-oracle/run_wp2.py; skipped when absent.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "remediation-oracle"))
sys.path.insert(0, str(HERE.parent / "sregym-oracle"))
import analysis as A  # noqa: E402
import analyze_wp2 as W  # noqa: E402
import cross_model as CM  # noqa: E402

OUT = HERE / "tables"
ARM_TEX = {"idle": "Idle", "restart_loop": "Restart", "agent_mitigate": "AI-mitigate", "agent_remediate": "AI-remediate",
           "agent_free": "AI-free"}
MODEL_TEX = {"v3-haiku55-main": "Haiku~5.5", "v3-gemini-main": "Gemini Flash"}
WP2_ARMS = {"idle": "Idle", "restart": "Restart", "ai": "AI (Haiku~5.5)", "ai_sonnet": "AI (Sonnet~5.5)",
            "ai_hydrogen": "AI (Hydrogen~4)", "ai_gemini38": "AI (Gemini Flash)"}
WP2_DIRS = ("sregym-wp2", "sregym-wp2-sonnet")  # the stopped Google arm is released but not analyzed
WP2_TAGS = (("ai", "Haiku"), ("ai_sonnet", "Sonnet"), ("ai_hydrogen", "Hydrogen"), ("ai_gemini38", "Gemini"))
WP2_PROBLEMS = {  # table order: group A first (SREGym has no durability step), then group B
    "service_wrong_pod_selection_hotel_reservation": "Wrong pod selector",
    "kafka_poison_pill_hol_block": "Kafka poison pill",
    "secret_rotation_stale_env_credentials_astronomy_shop": "Rotated DB secret",
    "internal_traffic_policy_local_astronomy_shop": "Local traffic policy",
    "cronjob_sidecar_blocks_completion_hotel_reservation": "CronJob sidecar",
    "finalizer_deadlock_controller_hotel_reservation": "Finalizer deadlock",
    "namespace_memory_limit": "Namespace memory limit",
    "search_rate_retry_collapse_hotel_reservation": "Retry collapse",
}
WP2_OUTCOMES = ("not_recovered", "temporary", "durable")
WP4_SETS = (("Sonnet~5.5", "wp4-sonnet-v4", "Sonnet"), ("Haiku~5.5", "wp4-haiku-v4", "HaikuV"))
WP4_ARMS = ("agent_mitigate", "agent_remediate")


def ci(rows, stat):
    p, (lo, hi) = A.boot_ci(rows, stat)
    if p != p:
        return "--"
    return f"{p:.2f} [{lo:.2f}, {hi:.2f}]"


def datasets():
    out = []
    for _, d, _ in CM.DATASETS:
        rows = CM.load(d)
        if rows:
            out.append((d, rows))
    return out


def table_outcomes(data):
    lines = [r"\begin{tabular}{llrlllr}", r"\toprule",
             r"Model & Arm & $N$ & MSR (conventional) & RSR (durable fix) & SSR (temporary) & Time-outs \\", r"\midrule"]
    for d, rows in data:
        main = [r for r in rows if not CM.peek(r)]
        arms = [a for a in A.ARMS if any(r["arm"] == a for r in main)]
        for i, arm in enumerate(arms):
            g = [r for r in main if r["arm"] == arm]
            lines.append(f"{MODEL_TEX[d] if i == 0 else ''} & {ARM_TEX[arm]} & {len(g)} & {ci(g, A.rate(CM.mitig))} & "
                         f"{ci(g, A.rate(CM.real))} & {ci(g, A.rate(CM.temp))} & {sum(map(CM.timed_out, g))} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def table_contrasts(data):
    lines = [r"\begin{tabular}{lllrr}", r"\toprule", r"Model & Contrast & Difference in RSR [95\% CI] & OR$_{\mathrm{MH}}$ & $p$ \\",
             r"\midrule"]
    pairs = [("agent_mitigate", "agent_remediate"), ("agent_mitigate", "agent_free"), ("agent_remediate", "agent_free")]
    for d, rows in data:
        main = [r for r in rows if not CM.peek(r)]
        for i, (a, b) in enumerate(pairs):
            ra = [r for r in main if r["arm"] == a]
            rb = [r for r in main if r["arm"] == b]

            def diff(rr, a=a, b=b):
                x = [r for r in rr if r["arm"] == a]
                y = [r for r in rr if r["arm"] == b]
                return A.rate(CM.real)(x) - A.rate(CM.real)(y) if x and y else float("nan")
            p, (lo, hi) = A.boot_ci(ra + rb, diff)
            o, pv = A.cmh(ra, rb, CM.real)
            pstr = "$<$0.001" if pv < 0.001 else f"{pv:.3f}"
            lines.append(f"{MODEL_TEX[d] if i == 0 else ''} & {ARM_TEX[a]} $-$ {ARM_TEX[b]} & {p:+.2f} [{lo:+.2f}, {hi:+.2f}] & "
                         f"{o:.2f} & {pstr} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def table_aam(data):
    lines = [r"\begin{tabular}{llll}", r"\toprule",
             r"Model & AAM [95\% CI] & Group A (config) & Group B (code) \\", r"\midrule"]
    for d, rows in data:
        free = [r for r in rows if r["arm"] == "agent_free" and not CM.peek(r)]
        ok = lambda r: r["action_type"] == A.REQUIRED[r["fault_group"]]  # noqa: E731
        cell = lambda g: f"{sum(map(ok, g))}/{len(g)}"  # noqa: E731
        lines.append(f"{MODEL_TEX[d]} & {ci(free, A.rate(ok))} & {cell([r for r in free if r['fault_group'] == 'A'])} & "
                     f"{cell([r for r in free if r['fault_group'] == 'B'])} \\\\")
        nt = [r for r in free if not CM.timed_out(r)]
        if len(nt) < len(free):
            lines.append(f"\\quad without time-outs & {sum(map(ok, nt))}/{len(nt)} & "
                         f"{cell([r for r in nt if r['fault_group'] == 'A'])} & {cell([r for r in nt if r['fault_group'] == 'B'])} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def table_mechanism(data):
    lines = [r"\begin{tabular}{llrllll}", r"\toprule",
             r"Model & Arm & $N$ & RSR (oracle) & RSR, defect removed & Config workarounds & Code workarounds \\", r"\midrule"]
    for d, rows in data:
        ev = CM.load_evidence(d)
        for i, arm in enumerate(CM.AI_ARMS):
            g = [r for r in rows if r["arm"] == arm and not CM.peek(r) and r["fault_group"] == "B"]
            e_of = lambda r: ev[(r["problem_id"], r["arm"], r["run_index"])]  # noqa: E731
            rc = lambda r: CM.real(r) and CM.removes_defect(r, e_of(r))  # noqa: E731
            fixed = [r for r in g if CM.real(r)]
            wk = Counter(r["problem_id"] for r in fixed if CM.mechanism(r, e_of(r)) == "B: configuration workaround")
            ck = Counter(r["problem_id"] for r in fixed
                         if CM.mechanism(r, e_of(r)) in CM.CODE_FIX and CM.repair(r, e_of(r)).startswith("workaround"))
            fmt = lambda c: ", ".join(f"{k}: {v}" for k, v in sorted(c.items(), key=lambda kv: int(kv[0][1:]))) or "0"  # noqa: E731
            lines.append(f"{MODEL_TEX[d] if i == 0 else ''} & {ARM_TEX[arm]} & {len(g)} & {ci(g, A.rate(CM.real))} & "
                         f"{ci(g, A.rate(rc))} & {fmt(wk)} & {fmt(ck)} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def numbers(data):
    """Macros \\num... used in the text, so the prose cannot drift from the data."""
    m = {}
    for d, rows in data:
        tag = {"v3-haiku55-main": "Haiku", "v3-gemini-main": "Gemini"}[d]
        main = [r for r in rows if not CM.peek(r)]
        ai = [r for r in rows if r["arm"].startswith("agent")]
        m[f"runs{tag}"] = len(rows)
        m[f"airuns{tag}"] = len(ai)
        m[f"peek{tag}"] = sum(map(CM.peek, ai))
        succ, string = CM.peek_sets(d, rows)  # both peek definitions, AI runs only (cross_model section 5.3)
        m[f"peekSuccess{tag}"] = sum(CM.key(r) in succ for r in ai)
        m[f"peekString{tag}"] = sum(CM.key(r) in string for r in ai)
        m[f"timeouts{tag}"] = sum(map(CM.timed_out, main))
        mit = [r for r in main if r["arm"] == "agent_mitigate"]
        m[f"mitTempShare{tag}"] = f"{A.ratio(CM.temp, CM.mitig)(mit) * 100:.0f}"
        oc = CM.oracle_cost_summary(rows, d)  # cross_model section 5.8 (descriptive)
        m[f"oracleAdded{tag}"] = f"{oc['added']:.0f}"
        m[f"oracleShare{tag}"] = f"{oc['share'] * 100:.0f}"
        m[f"roundThree{tag}"] = f"{oc['r3']:.0f}"
        claim, n_lab, kappa = A.rq3_labels(CM.RESULTS / d)
        if claim is not None:  # RQ3: only once the labels of two raters are merged
            m[f"rqkappa{tag}"] = f"{kappa:.2f}"
            m[f"rqlabelled{tag}"] = n_lab
            m[f"rqclaimMit{tag}"] = f"{A.rate(claim)(mit):.2f}"
            m[f"rqfalseMit{tag}"] = f"{A.ratio(lambda r: claim(r) and not CM.real(r), claim)(mit):.2f}"
    m |= rq4_numbers(wp2_runs())
    m |= wp4_numbers()
    lines = [f"\\newcommand{{\\num{k}}}{{{v}}}" for k, v in sorted(m.items())]
    return lines


def wp4_rows():
    """WP4' (PRE-REGISTRATION 2026-11-15): runs of both v4 sets, peek excluded; None if a set is missing."""
    data = {d: CM.load(d) for _, d, _ in WP4_SETS}
    if any(not v for v in data.values()):
        return None
    return {d: [r for r in rows if not CM.peek(r)] for d, rows in data.items()}, data


def wp4_numbers():
    m, got = {}, wp4_rows()
    if got is None:
        return m
    data, raw = got
    for _, d, tag in WP4_SETS:
        m[f"wpfourRuns{tag}"] = len(raw[d])
        m[f"wpfourPeek{tag}"] = sum(map(CM.peek, raw[d]))
        m[f"wpfourTimeouts{tag}"] = sum(map(CM.timed_out, data[d]))
        for arm in WP4_ARMS:
            g = [r for r in data[d] if r["arm"] == arm]
            a = "Mit" if arm == "agent_mitigate" else "Rem"
            m[f"wpfourShare{a}{tag}"] = f"{A.ratio(A.temp, A.mitig)(g):.2f}"
            m[f"wpfourRsr{a}{tag}"] = f"{A.rate(A.real)(g):.2f}"
            m[f"wpfourMsr{a}{tag}"] = f"{A.rate(A.mitig)(g):.2f}"
    s, h = data["wp4-sonnet-v4"], data["wp4-haiku-v4"]
    for _, d, tag in WP4_SETS:  # mechanism (cross_model 5.4): 9 code faults, fault removed from code; config workarounds
        ev = CM.load_evidence(d)
        e_of = lambda r, ev=ev: ev[(r["problem_id"], r["arm"], r["run_index"])]  # noqa: E731
        for arm, a in (("agent_mitigate", "Mit"), ("agent_remediate", "Rem")):
            g = [r for r in data[d] if r["arm"] == arm and r["fault_group"] == "B"]
            m[f"wpfourCodeFix{a}{tag}"] = f"{A.rate(lambda r: CM.real(r) and CM.removes_defect(r, e_of(r)))(g):.2f}"
            m[f"wpfourCfgWk{a}{tag}"] = sum(1 for r in g if CM.real(r) and CM.mechanism(r, e_of(r)) == "B: configuration workaround")
    v3 = [r for r in CM.load("v3-haiku55-main") if not CM.peek(r)]  # descriptive: Haiku under isolation v3
    m["wpfourShareMitHaikuThree"] = f"{A.ratio(A.temp, A.mitig)([r for r in v3 if r['arm'] == 'agent_mitigate']):.2f}"
    m["wpfourRsrRemHaikuThree"] = f"{A.rate(A.real)([r for r in v3 if r['arm'] == 'agent_remediate']):.2f}"
    for arm, a in (("agent_mitigate", "Mit"), ("agent_remediate", "Rem")):
        sa, ha = [r for r in s if r["arm"] == arm], [r for r in h if r["arm"] == arm]
        o, p = A.cmh([r for r in sa if A.mitig(r)], [r for r in ha if A.mitig(r)], A.temp)
        m[f"wpfourTempOr{a}"], m[f"wpfourTempP{a}"] = f"{o:.2f}", f"{p:.3f}"
        o, p = A.cmh(sa, ha, A.real)
        m[f"wpfourRealOr{a}"], m[f"wpfourRealP{a}"] = f"{o:.2f}", f"{p:.3f}"
    return m


def table_wp4(data):
    """WP4' table: MSR, RSR, SSR, SSR/MSR by model and arm (fault-level bootstrap CI); a comment until both sets exist."""
    got = wp4_rows()
    if got is None:
        return ["% Both WP4' sets are not available yet (results/wp4-sonnet-v4, results/wp4-haiku-v4)"]
    rows, _ = got
    lines = [r"\begin{tabular}{llrllll}", r"\toprule",
             r"Model & Arm & $N$ & MSR [95\% CI] & RSR [95\% CI] & SSR [95\% CI] & SSR/MSR [95\% CI] \\", r"\midrule"]
    for name, d, _ in WP4_SETS:
        for i, arm in enumerate(WP4_ARMS):
            g = [r for r in rows[d] if r["arm"] == arm]
            lines.append(f"{name if i == 0 else ''} & {ARM_TEX[arm]} & {len(g)} & {ci(g, A.rate(A.mitig))} & "
                         f"{ci(g, A.rate(A.real))} & {ci(g, A.rate(A.temp))} & {ci(g, A.ratio(A.temp, A.mitig))} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def wp2_runs():
    """WP2 runs with the peek flag from peek_review.csv (analyze_wp2.peeked); table and main macros exclude peek runs."""
    paths = [p for p in (CM.RESULTS / d / "runs.jsonl" for d in WP2_DIRS) if p.exists()]
    runs = [json.loads(x) for p in paths for x in p.read_text().splitlines() if x.strip()]
    peek = W.peeked(paths)
    for r in runs:
        r.setdefault("outcome", "infra_error" if r.get("infra_error") else "unscored")
        r["peek"] = r["run_id"] in peek
    return runs


def rq4_numbers(runs):
    """RQ4 macros as pre-registered (WP2): temporary share among runs that passed round 1, group A, Wilson 95%; group B."""
    m = {}
    if not runs:
        return m
    for arm, tag in WP2_TAGS:
        if any(r["arm"] == arm for r in runs):
            m[f"rqfourPeek{tag}"] = sum(r["peek"] for r in runs if r["arm"] == arm)
    runs = [r for r in runs if not r["peek"]]
    m["rqfourRuns"] = len(runs)
    for arm, tag in (*WP2_TAGS, ("restart", "Restart")):
        passed = [r for r in runs if r["arm"] == arm and r["problem"] in W.GROUP_A and r["outcome"] in ("temporary", "durable")]
        if not any(r["arm"] == arm for r in runs):
            continue
        k, n = sum(r["outcome"] == "temporary" for r in passed), len(passed)
        lo, hi = W.wilson(k, n)
        m[f"rqfourTemp{tag}k"], m[f"rqfourTemp{tag}n"] = k, n
        m[f"rqfourTemp{tag}ci"] = f"{k / n:.2f} [{max(lo, 0):.2f}, {min(hi, 1):.2f}]" if n else "--"
        m[f"rqfourRuns{tag}"] = sum(r["arm"] == arm for r in runs)
    b = [r for r in runs if r["problem"] not in W.GROUP_A and r["outcome"] in ("temporary", "durable")]
    m["rqfourBk"], m["rqfourBn"] = sum(r["outcome"] == "temporary" for r in b), len(b)
    m["rqfourUnscored"] = sum(r["outcome"] in ("unscored", "infra_error") for r in runs)
    # Reruns under the infrastructure-failure rule (infra.jsonl next to runs.jsonl; those records are not analyzed)
    m["rqfourInfraReruns"] = sum(len([x for x in p.read_text().splitlines() if x.strip()]) for p in
                                 (CM.RESULTS / d / "infra.jsonl" for d in WP2_DIRS) if p.exists())
    for arm, tag in (*WP2_TAGS, ("idle", "Idle"), ("restart", "Restart")):  # runs passing round 1 by group, for the text
        a = [r for r in runs if r["arm"] == arm]
        if not a:
            continue
        for grp, inside in (("A", True), ("B", False)):
            g = [r for r in a if (r["problem"] in W.GROUP_A) == inside]
            m[f"rqfourPass{grp}{tag}"] = sum(r["outcome"] in ("temporary", "durable") for r in g)
            m[f"rqfourN{grp}{tag}"] = len(g)
        k = [r for r in a if r["problem"] == "kafka_poison_pill_hol_block"]
        m[f"rqfourKafkaPass{tag}"], m[f"rqfourKafkaN{tag}"] = sum(r["outcome"] in ("temporary", "durable") for r in k), len(k)
    return m


def table_rq4(data):
    """RQ4 table: result per problem x arm on SREGym-Lite. Only a comment until runs.jsonl exists."""
    runs = [r for r in wp2_runs() if not r["peek"]]
    if not runs:
        return ["% No WP2 results yet (results/sregym-wp2/runs.jsonl)"]
    cells = {}
    for r in runs:
        cells.setdefault((r["problem"], r["arm"]), Counter())[r["outcome"]] += 1
    lines = [r"\begin{tabular}{llrrrrr}", r"\toprule",
             r"Problem & Arm & $N$ & Not recovered & Temporary & Durable & Unscored \\", r"\midrule"]
    for group, title in ((True, "Group A: no durability step in SREGym's oracle"), (False, "Group B: SREGym's oracle "
                                                                                         "replays load or reruns work")):
        lines.append(rf"\multicolumn{{7}}{{l}}{{\emph{{{title}}}}} \\")
        for p, name in WP2_PROBLEMS.items():
            if (p in W.GROUP_A) != group:
                continue
            arms = [a for a in WP2_ARMS if (p, a) in cells]
            for i, a in enumerate(arms):
                c = cells[(p, a)]
                lines.append(f"{name if i == 0 else ''} & {WP2_ARMS[a]} & {sum(c.values())} & "
                             + " & ".join(str(c[o]) for o in WP2_OUTCOMES) + f" & {c['unscored'] + c['infra_error']} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def table_rq3(data):
    """RQ3 table (labels from two raters, PRE-REGISTRATION section 9) once every set has claims_labels.csv; until then
    only a comment, and content.tex does not \\input this table."""
    labelled = [(d, rows, *A.rq3_labels(CM.RESULTS / d)) for d, rows in data]
    missing = [d for d, _, claim, _, _ in labelled if claim is None]
    if missing:
        return ["% No RQ3 labels from two raters yet for: " + ", ".join(missing)]
    lines = [r"\begin{tabular}{llrlll}", r"\toprule",
             r"Model & Arm & $N$ & Claims resolution [95\% CI] & Claimed, not a durable fix [95\% CI] & $\kappa$ \\",
             r"\midrule"]
    for d, rows, claim, n_lab, kappa in labelled:
        main = [r for r in rows if not CM.peek(r)]
        for i, a in enumerate(CM.AI_ARMS):
            g = [r for r in main if r["arm"] == a]
            lines.append(f"{MODEL_TEX[d] if i == 0 else ''} & {ARM_TEX[a]} & {len(g)} & {ci(g, A.rate(claim))} & "
                         f"{ci(g, A.ratio(lambda r: claim(r) and not CM.real(r), claim))} & "
                         f"{f'{kappa:.2f}' if i == 0 else ''} \\\\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return lines


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = datasets()
    for name, fn in (("outcomes", table_outcomes), ("contrasts", table_contrasts), ("aam", table_aam),
                     ("mechanism", table_mechanism), ("rq3", table_rq3), ("rq4", table_rq4), ("wp4", table_wp4),
                     ("numbers", numbers)):
        (OUT / f"{name}.tex").write_text("\n".join(fn(data)) + "\n")
    print("tables:", ", ".join(sorted(p.name for p in OUT.glob("*.tex"))), "| datasets:", ", ".join(d for d, _ in data))


if __name__ == "__main__":
    main()
