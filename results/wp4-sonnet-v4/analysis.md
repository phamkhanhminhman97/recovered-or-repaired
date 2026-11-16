# Analysis: ../results/wp4-sonnet-v4

Runs: 72; excluded for peek: 0; tamper: 1; timed out: 0. Model: claude-sonnet-5-5

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| agent_mitigate | 36 | 0.250 [0.06–0.47] | 0.083 [0.00–0.25] | 0.333 [0.11–0.58] | 0.250 [0.00–0.75] |
| agent_remediate | 36 | 0.917 [0.75–1.00] | 0.000 [0.00–0.00] | 0.917 [0.75–1.00] | 0.000 [0.00–0.00] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| agent_mitigate − agent_remediate | RSR | -0.667 [-0.89–-0.42] | 0.00 | 0.0000 |
| agent_mitigate − agent_remediate | MSR | -0.583 [-0.83–-0.33] | 0.00 | 0.0000 |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 36 | 0.917 [0.83–1.00] | 0.788 [0.56–0.97] |
| agent_remediate | 36 | 0.833 [0.69–0.97] | 0.033 [0.00–0.12] |
