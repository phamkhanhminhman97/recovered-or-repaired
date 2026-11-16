# Analysis: ../results/wp4-haiku-v4

Runs: 72; excluded for peek: 1; tamper: 1; timed out: 0. Model: claude-haiku-5-5

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| agent_mitigate | 36 | 0.222 [0.00–0.47] | 0.167 [0.00–0.42] | 0.389 [0.14–0.67] | 0.429 [0.00–1.00] |
| agent_remediate | 35 | 0.800 [0.59–1.00] | 0.057 [0.00–0.18] | 0.857 [0.66–1.00] | 0.067 [0.00–0.21] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| agent_mitigate − agent_remediate | RSR | -0.578 [-0.89–-0.21] | 0.13 | 0.0000 |
| agent_mitigate − agent_remediate | MSR | -0.468 [-0.80–-0.08] | 0.15 | 0.0000 |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 36 | 0.944 [0.83–1.00] | 0.765 [0.50–1.00] |
| agent_remediate | 35 | 0.829 [0.63–1.00] | 0.069 [0.00–0.21] |

## Sensitivity to the handling of peek runs

Peek rate: 1/72 AI runs. By fault: F10 1/6

| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |
|---|---|---|---|
| agent_mitigate (RSR) | 0.222 [0.00–0.47] | 0.222 [0.00–0.47] | 0.222 [0.00–0.47] |
| agent_remediate (RSR) | 0.800 [0.59–1.00] | 0.778 [0.58–0.94] | 0.806 [0.61–1.00] |
| agent_mitigate − agent_remediate (RSR, CMH) | OR 0.13, p=0.0000 | OR 0.13, p=0.0000 | OR 0.12, p=0.0000 |
| agent_mitigate − agent_free (RSR, CMH) | - | - | - |

## Excluded runs (peek)

- F10 agent_remediate run1
