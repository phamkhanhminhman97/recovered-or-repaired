# Analysis: ../results/v3-haiku55-main

Runs: 600; excluded for peek: 7; tamper: 7; timed out: 0. Model: claude-haiku-5-5

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| idle | 120 | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | – |
| restart_loop | 120 | 0.000 [0.00–0.00] | 0.250 [0.00–0.50] | 0.250 [0.00–0.50] | 1.000 [1.00–1.00] |
| agent_mitigate | 120 | 0.250 [0.07–0.47] | 0.158 [0.00–0.39] | 0.408 [0.18–0.65] | 0.388 [0.00–0.81] |
| agent_remediate | 116 | 0.845 [0.69–0.97] | 0.060 [0.00–0.15] | 0.905 [0.79–0.98] | 0.067 [0.00–0.17] |
| agent_free | 117 | 0.761 [0.54–0.97] | 0.017 [0.00–0.05] | 0.778 [0.57–0.97] | 0.022 [0.00–0.08] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| idle − restart_loop | RSR | 0.000 [0.00–0.00] | nan | nan |
| idle − restart_loop | MSR | -0.250 [-0.50–0.00] | 0.00 | 0.0000 |
| idle − agent_mitigate | RSR | -0.250 [-0.47–-0.07] | 0.00 | 0.0000 |
| idle − agent_mitigate | MSR | -0.408 [-0.65–-0.18] | 0.00 | 0.0000 |
| idle − agent_remediate | RSR | -0.845 [-0.97–-0.69] | 0.00 | 0.0000 |
| idle − agent_remediate | MSR | -0.905 [-0.98–-0.79] | 0.00 | 0.0000 |
| idle − agent_free | RSR | -0.761 [-0.97–-0.54] | 0.00 | 0.0000 |
| idle − agent_free | MSR | -0.778 [-0.97–-0.57] | 0.00 | 0.0000 |
| restart_loop − agent_mitigate | RSR | -0.250 [-0.47–-0.07] | 0.00 | 0.0000 |
| restart_loop − agent_mitigate | MSR | -0.158 [-0.43–0.09] | 0.30 | 0.0002 |
| restart_loop − agent_remediate | RSR | -0.845 [-0.97–-0.69] | 0.00 | 0.0000 |
| restart_loop − agent_remediate | MSR | -0.655 [-0.89–-0.38] | 0.03 | 0.0000 |
| restart_loop − agent_free | RSR | -0.761 [-0.97–-0.54] | 0.00 | 0.0000 |
| restart_loop − agent_free | MSR | -0.528 [-0.83–-0.20] | 0.10 | 0.0000 |
| agent_mitigate − agent_remediate | RSR | -0.595 [-0.85–-0.32] | 0.08 | 0.0000 |
| agent_mitigate − agent_remediate | MSR | -0.497 [-0.75–-0.25] | 0.06 | 0.0000 |
| agent_mitigate − agent_free | RSR | -0.511 [-0.78–-0.24] | 0.07 | 0.0000 |
| agent_mitigate − agent_free | MSR | -0.369 [-0.61–-0.14] | 0.08 | 0.0000 |
| agent_remediate − agent_free | RSR | 0.084 [-0.05–0.23] | 2.59 | 0.0392 |
| agent_remediate − agent_free | MSR | 0.127 [-0.01–0.29] | 4.39 | 0.0015 |

## RQ1: AAM of agent_free

| Group | N | AAM |
|---|---|---|
| A | 29 | 0.862 [0.60–1.00] |
| B | 88 | 0.830 [0.58–1.00] |
| A+B | 117 | 0.838 [0.67–1.00] |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 120 | 0.783 [0.65–0.89] | 0.819 [0.64–0.96] |
| agent_remediate | 116 | 0.845 [0.71–0.96] | 0.133 [0.02–0.29] |
| agent_free | 117 | 0.718 [0.54–0.87] | 0.226 [0.03–0.46] |

## Sensitivity to the handling of peek runs

Peek rate: 7/360 AI runs. By fault: F8 5/30, F10 2/30

| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |
|---|---|---|---|
| agent_mitigate (RSR) | 0.250 [0.07–0.47] | 0.250 [0.07–0.47] | 0.250 [0.07–0.47] |
| agent_remediate (RSR) | 0.845 [0.69–0.97] | 0.817 [0.66–0.95] | 0.817 [0.66–0.95] |
| agent_free (RSR) | 0.761 [0.54–0.97] | 0.742 [0.53–0.93] | 0.767 [0.55–0.97] |
| agent_mitigate − agent_remediate (RSR, CMH) | OR 0.08, p=0.0000 | OR 0.12, p=0.0000 | OR 0.12, p=0.0000 |
| agent_mitigate − agent_free (RSR, CMH) | OR 0.07, p=0.0000 | OR 0.08, p=0.0000 | OR 0.07, p=0.0000 |

## Excluded runs (peek)

- F8 agent_remediate run9
- F8 agent_remediate run6
- F8 agent_free run0
- F10 agent_free run4
- F8 agent_remediate run3
- F10 agent_free run0
- F8 agent_remediate run7
