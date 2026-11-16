# Analysis: ../results/v2-haiku55-main

Runs: 600; excluded for peek: 31; tamper: 12; timed out: 1. Model: claude-haiku-5-5

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| idle | 120 | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | – |
| restart_loop | 120 | 0.000 [0.00–0.00] | 0.250 [0.00–0.50] | 0.250 [0.00–0.50] | 1.000 [1.00–1.00] |
| agent_mitigate | 111 | 0.252 [0.06–0.49] | 0.180 [0.00–0.44] | 0.432 [0.19–0.70] | 0.417 [0.00–0.83] |
| agent_remediate | 110 | 0.845 [0.68–0.98] | 0.045 [0.00–0.11] | 0.891 [0.77–0.98] | 0.051 [0.00–0.14] |
| agent_free | 108 | 0.796 [0.61–0.97] | 0.019 [0.00–0.04] | 0.815 [0.65–0.97] | 0.023 [0.00–0.06] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| idle − restart_loop | RSR | 0.000 [0.00–0.00] | nan | nan |
| idle − restart_loop | MSR | -0.250 [-0.50–0.00] | 0.00 | 0.0000 |
| idle − agent_mitigate | RSR | -0.252 [-0.49–-0.06] | 0.00 | 0.0000 |
| idle − agent_mitigate | MSR | -0.432 [-0.70–-0.19] | 0.00 | 0.0000 |
| idle − agent_remediate | RSR | -0.845 [-0.98–-0.68] | 0.00 | 0.0000 |
| idle − agent_remediate | MSR | -0.891 [-0.98–-0.77] | 0.00 | 0.0000 |
| idle − agent_free | RSR | -0.796 [-0.97–-0.61] | 0.00 | 0.0000 |
| idle − agent_free | MSR | -0.815 [-0.97–-0.65] | 0.00 | 0.0000 |
| restart_loop − agent_mitigate | RSR | -0.252 [-0.49–-0.06] | 0.00 | 0.0000 |
| restart_loop − agent_mitigate | MSR | -0.182 [-0.47–0.10] | 0.32 | 0.0001 |
| restart_loop − agent_remediate | RSR | -0.845 [-0.98–-0.68] | 0.00 | 0.0000 |
| restart_loop − agent_remediate | MSR | -0.641 [-0.89–-0.35] | 0.05 | 0.0000 |
| restart_loop − agent_free | RSR | -0.796 [-0.97–-0.61] | 0.00 | 0.0000 |
| restart_loop − agent_free | MSR | -0.565 [-0.86–-0.22] | 0.11 | 0.0000 |
| agent_mitigate − agent_remediate | RSR | -0.593 [-0.85–-0.30] | 0.10 | 0.0000 |
| agent_mitigate − agent_remediate | MSR | -0.458 [-0.73–-0.17] | 0.11 | 0.0000 |
| agent_mitigate − agent_free | RSR | -0.544 [-0.79–-0.30] | 0.04 | 0.0000 |
| agent_mitigate − agent_free | MSR | -0.382 [-0.62–-0.16] | 0.04 | 0.0000 |
| agent_remediate − agent_free | RSR | 0.049 [-0.10–0.18] | 1.61 | 0.3471 |
| agent_remediate − agent_free | MSR | 0.076 [-0.08–0.21] | 2.05 | 0.1118 |

## RQ1: AAM of agent_free

| Group | N | AAM |
|---|---|---|
| A | 25 | 0.840 [0.60–1.00] |
| B | 83 | 0.843 [0.63–1.00] |
| A+B | 108 | 0.843 [0.68–1.00] |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 111 | 0.784 [0.64–0.90] | 0.793 [0.55–0.98] |
| agent_remediate | 110 | 0.845 [0.75–0.93] | 0.118 [0.02–0.27] |
| agent_free | 108 | 0.796 [0.64–0.93] | 0.233 [0.04–0.44] |

## Sensitivity to the handling of peek runs

Peek rate: 31/360 AI runs. By fault: F2 2/30, F6 2/30, F8 14/30, F10 13/30

| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |
|---|---|---|---|
| agent_mitigate (RSR) | 0.252 [0.06–0.49] | 0.233 [0.06–0.45] | 0.258 [0.06–0.50] |
| agent_remediate (RSR) | 0.845 [0.68–0.98] | 0.775 [0.58–0.94] | 0.850 [0.71–0.98] |
| agent_free (RSR) | 0.796 [0.61–0.97] | 0.717 [0.54–0.88] | 0.817 [0.64–0.97] |
| agent_mitigate − agent_remediate (RSR, CMH) | OR 0.10, p=0.0000 | OR 0.12, p=0.0000 | OR 0.09, p=0.0000 |
| agent_mitigate − agent_free (RSR, CMH) | OR 0.04, p=0.0000 | OR 0.09, p=0.0000 | OR 0.03, p=0.0000 |

## Excluded runs (peek)

- F10 agent_mitigate run7
- F8 agent_remediate run0
- F10 agent_free run9
- F8 agent_free run9
- F8 agent_free run4
- F10 agent_mitigate run8
- F10 agent_mitigate run9
- F8 agent_free run2
- F8 agent_remediate run8
- F10 agent_mitigate run0
- F8 agent_free run6
- F10 agent_mitigate run1
- F10 agent_free run2
- F6 agent_free run6
- F2 agent_remediate run2
- F10 agent_mitigate run4
- F8 agent_remediate run6
- F8 agent_mitigate run4
- F10 agent_remediate run0
- F10 agent_free run3
- F8 agent_mitigate run0
- F10 agent_remediate run7
- F10 agent_free run6
- F8 agent_mitigate run6
- F2 agent_remediate run7
- F6 agent_free run9
- F8 agent_remediate run1
- F8 agent_free run3
- F8 agent_remediate run3
- F8 agent_remediate run4
- F10 agent_free run0
