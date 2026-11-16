"""WP4' (PRE-REGISTRATION 2026-11-15, written before the data existed): Sonnet 5.5 against Haiku 5.5 on order-service
under isolation v4 (results/wp4-sonnet-v4, results/wp4-haiku-v4; same seed, hence the same run order).

Primary: agent_mitigate arm, temporary share among recoveries (SSR/MSR); CMH stratified by fault on the recovered runs
(outcome: temporary; Sonnet against Haiku). Secondary: agent_remediate arm, RSR (CMH on real recovery). Fault-level
bootstrap CI (12 clusters, B = 5000). Peek runs excluded. The comparison with v3-haiku55-main (isolation v3) is descriptive.
  ../.venv/bin/python compare_wp4.py
"""
import analysis as A
import cross_model as CM

SETS = [("Sonnet 5.5, v4", "wp4-sonnet-v4"), ("Haiku 5.5, v4", "wp4-haiku-v4"), ("Haiku 5.5, v3 (descriptive)", "v3-haiku55-main")]
ARMS = ("agent_mitigate", "agent_remediate")


def main():
    data = {d: [r for r in (CM.load(d) or []) if not CM.peek(r)] for _, d in SETS}
    for arm in ARMS:
        print(f"## {arm}")
        for name, d in SETS:
            g = [r for r in data[d] if r["arm"] == arm]
            if g:
                print(f"{name}: N={len(g)}, MSR {A.fmt(*A.boot_ci(g, A.rate(A.mitig)))}, RSR {A.fmt(*A.boot_ci(g, A.rate(A.real)))}, "
                      f"SSR {A.fmt(*A.boot_ci(g, A.rate(A.temp)))}, SSR/MSR {A.fmt(*A.boot_ci(g, A.ratio(A.temp, A.mitig)))}")
        s = [r for r in data["wp4-sonnet-v4"] if r["arm"] == arm]
        h = [r for r in data["wp4-haiku-v4"] if r["arm"] == arm]
        if s and h:
            if arm == "agent_mitigate":
                o, p = A.cmh([r for r in s if A.mitig(r)], [r for r in h if A.mitig(r)], A.temp)
                print(f"PRIMARY     temporary among recovered, Sonnet vs Haiku: OR_MH {o:.2f}, p {p:.4f}")
            o, p = A.cmh(s, h, A.real)
            tag = "SECONDARY  " if arm == "agent_remediate" else "DESCRIPTIVE"
            print(f"{tag} real recovery, Sonnet vs Haiku: OR_MH {o:.2f}, p {p:.4f}")
        peeked = {d: sum(CM.peek(r) for r in (CM.load(d) or []) if r["arm"] == arm) for _, d in SETS[:2]}
        print("peek (excluded):", peeked)


if __name__ == "__main__":
    main()
