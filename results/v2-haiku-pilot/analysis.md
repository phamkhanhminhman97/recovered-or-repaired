# Analysis: ../results/v2-haiku-pilot

Runs: 180; excluded for peek: 5; tamper: 14; timed out: 9. Model: claude-haiku-4-5

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| idle | 36 | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | – |
| restart_loop | 36 | 0.000 [0.00–0.00] | 0.250 [0.00–0.50] | 0.250 [0.00–0.50] | 1.000 [1.00–1.00] |
| agent_mitigate | 34 | 0.206 [0.00–0.43] | 0.294 [0.06–0.56] | 0.500 [0.24–0.77] | 0.588 [0.18–1.00] |
| agent_remediate | 34 | 0.676 [0.47–0.86] | 0.059 [0.00–0.18] | 0.735 [0.56–0.89] | 0.080 [0.00–0.27] |
| agent_free | 35 | 0.771 [0.54–0.97] | 0.086 [0.00–0.22] | 0.857 [0.67–1.00] | 0.100 [0.00–0.27] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| idle − restart_loop | RSR | 0.000 [0.00–0.00] | nan | nan |
| idle − restart_loop | MSR | -0.250 [-0.50–0.00] | 0.00 | 0.0006 |
| idle − agent_mitigate | RSR | -0.206 [-0.43–0.00] | 0.00 | 0.0073 |
| idle − agent_mitigate | MSR | -0.500 [-0.77–-0.24] | 0.00 | 0.0000 |
| idle − agent_remediate | RSR | -0.676 [-0.86–-0.47] | 0.00 | 0.0000 |
| idle − agent_remediate | MSR | -0.735 [-0.89–-0.56] | 0.00 | 0.0000 |
| idle − agent_free | RSR | -0.771 [-0.97–-0.54] | 0.00 | 0.0000 |
| idle − agent_free | MSR | -0.857 [-1.00–-0.67] | 0.00 | 0.0000 |
| restart_loop − agent_mitigate | RSR | -0.206 [-0.43–0.00] | 0.00 | 0.0073 |
| restart_loop − agent_mitigate | MSR | -0.250 [-0.52–-0.02] | 0.00 | 0.0006 |
| restart_loop − agent_remediate | RSR | -0.676 [-0.86–-0.47] | 0.00 | 0.0000 |
| restart_loop − agent_remediate | MSR | -0.485 [-0.75–-0.19] | 0.11 | 0.0001 |
| restart_loop − agent_free | RSR | -0.771 [-0.97–-0.54] | 0.00 | 0.0000 |
| restart_loop − agent_free | MSR | -0.607 [-0.89–-0.31] | 0.04 | 0.0000 |
| agent_mitigate − agent_remediate | RSR | -0.471 [-0.74–-0.19] | 0.10 | 0.0001 |
| agent_mitigate − agent_remediate | MSR | -0.235 [-0.50–0.03] | 0.35 | 0.0886 |
| agent_mitigate − agent_free | RSR | -0.566 [-0.81–-0.32] | 0.00 | 0.0000 |
| agent_mitigate − agent_free | MSR | -0.357 [-0.61–-0.10] | 0.06 | 0.0005 |
| agent_remediate − agent_free | RSR | -0.095 [-0.23–0.04] | 0.25 | 0.2500 |
| agent_remediate − agent_free | MSR | -0.122 [-0.24–-0.01] | 0.17 | 0.1414 |

## RQ1: AAM of agent_free

| Group | N | AAM |
|---|---|---|
| A | 8 | 0.875 [0.67–1.00] |
| B | 27 | 0.963 [0.89–1.00] |
| A+B | 35 | 0.943 [0.86–1.00] |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 34 | 0.971 [0.91–1.00] | 0.788 [0.56–1.00] |
| agent_remediate | 34 | 0.853 [0.74–0.94] | 0.207 [0.03–0.42] |
| agent_free | 35 | 0.971 [0.91–1.00] | 0.206 [0.03–0.41] |

## Sensitivity to the handling of peek runs

Peek rate: 5/108 AI runs. By fault: F2 1/9, F8 2/9, F11 1/9, F12 1/9

| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |
|---|---|---|---|
| agent_mitigate (RSR) | 0.206 [0.00–0.43] | 0.194 [0.00–0.42] | 0.194 [0.00–0.42] |
| agent_remediate (RSR) | 0.676 [0.47–0.86] | 0.639 [0.42–0.83] | 0.667 [0.44–0.86] |
| agent_free (RSR) | 0.771 [0.54–0.97] | 0.750 [0.53–0.94] | 0.778 [0.56–0.97] |
| agent_mitigate − agent_remediate (RSR, CMH) | OR 0.10, p=0.0001 | OR 0.13, p=0.0001 | OR 0.09, p=0.0000 |
| agent_mitigate − agent_free (RSR, CMH) | OR 0.00, p=0.0000 | OR 0.03, p=0.0000 | OR 0.00, p=0.0000 |

## Excluded runs (peek)

- F11 agent_mitigate run1
- F12 agent_remediate run2
- F2 agent_mitigate run2
- F8 agent_free run1
- F8 agent_remediate run0
