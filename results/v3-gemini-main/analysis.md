# Analysis: ../results/v3-gemini-main

Runs: 180; excluded for peek: 9; tamper: 2; timed out: 86. Model: gemini-3.8-flash

## RSR / SSR / MSR by arm (95% CI, fault-level bootstrap)

| Arm | N | Real recovery (RSR) | Temporary recovery (SSR) | MSR | SSR/MSR |
|---|---|---|---|---|---|
| agent_mitigate | 57 | 0.421 [0.16–0.68] | 0.211 [0.03–0.43] | 0.632 [0.38–0.86] | 0.333 [0.05–0.71] |
| agent_remediate | 55 | 0.545 [0.31–0.77] | 0.036 [0.00–0.12] | 0.582 [0.34–0.81] | 0.062 [0.00–0.20] |
| agent_free | 59 | 0.644 [0.40–0.87] | 0.034 [0.00–0.10] | 0.678 [0.45–0.88] | 0.050 [0.00–0.19] |

## Pairwise arm comparisons (CMH stratified by fault; rate difference with fault-level bootstrap CI)

| Pair | Metric | Rate difference | OR (MH) | p |
|---|---|---|---|---|
| agent_mitigate − agent_remediate | RSR | -0.124 [-0.51–0.26] | 0.68 | 0.2680 |
| agent_mitigate − agent_remediate | MSR | 0.050 [-0.30–0.38] | 1.35 | 0.5071 |
| agent_mitigate − agent_free | RSR | -0.223 [-0.54–0.08] | 0.28 | 0.0014 |
| agent_mitigate − agent_free | MSR | -0.046 [-0.33–0.20] | 0.72 | 0.5779 |
| agent_remediate − agent_free | RSR | -0.099 [-0.24–0.04] | 0.25 | 0.0774 |
| agent_remediate − agent_free | MSR | -0.096 [-0.22–0.02] | 0.22 | 0.0836 |

## RQ1: AAM of agent_free

| Group | N | AAM |
|---|---|---|
| A | 14 | 0.857 [0.50–1.00] |
| B | 45 | 0.622 [0.33–0.89] |
| A+B | 59 | 0.678 [0.43–0.90] |

## RQ3: AI reports done vs. verified outcome

No rater labels yet (run export_claims.py). The table below is only a keyword SCREEN.

| Arm | N | AI reports done | Reports done but no real recovery |
|---|---|---|---|
| agent_mitigate | 57 | 0.719 [0.50–0.91] | 0.512 [0.20–0.83] |
| agent_remediate | 55 | 0.345 [0.12–0.59] | 0.000 [0.00–0.00] |
| agent_free | 59 | 0.542 [0.28–0.81] | 0.000 [0.00–0.00] |

## Sensitivity to the handling of peek runs

Peek rate: 9/180 AI runs. By fault: F1 1/15, F2 2/15, F4 2/15, F8 1/15, F10 2/15, F12 1/15

| Arm | Peek excluded (primary) | Peek = no recovery | Peek kept as scored |
|---|---|---|---|
| agent_mitigate (RSR) | 0.421 [0.16–0.68] | 0.400 [0.15–0.67] | 0.417 [0.17–0.67] |
| agent_remediate (RSR) | 0.545 [0.31–0.77] | 0.500 [0.28–0.73] | 0.517 [0.28–0.75] |
| agent_free (RSR) | 0.644 [0.40–0.87] | 0.633 [0.38–0.87] | 0.633 [0.38–0.87] |
| agent_mitigate − agent_remediate (RSR, CMH) | OR 0.68, p=0.2680 | OR 0.69, p=0.2840 | OR 0.70, p=0.2815 |
| agent_mitigate − agent_free (RSR, CMH) | OR 0.28, p=0.0014 | OR 0.30, p=0.0015 | OR 0.32, p=0.0024 |

## Excluded runs (peek)

- F4 agent_mitigate run4
- F12 agent_free run0
- F2 agent_mitigate run1
- F4 agent_remediate run1
- F2 agent_remediate run1
- F8 agent_mitigate run0
- F1 agent_remediate run0
- F10 agent_remediate run2
- F10 agent_remediate run0
