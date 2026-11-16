# Comparison of v1 (v1-leaky-n10) and v2 (v3-haiku55-main)

v1: 480 runs. v2: 600 runs, 7 peek runs excluded.

Each cell: real / temporary recovery rate. v1 has 2 rounds, so its 'real recovery' never went through a redeploy.

## Totals by arm

| Arm | v1 | v2 |
|---|---|---|
| idle | 0.25 / 0.00 (n=120) | 0.00 / 0.00 (n=120) |
| restart_loop | 0.25 / 0.00 (n=120) | 0.00 / 0.25 (n=120) |
| agent_mitigate | 0.42 / 0.08 (n=120) | 0.25 / 0.16 (n=120) |
| agent_remediate | 0.87 / 0.01 (n=120) | 0.84 / 0.06 (n=116) |
| agent_free | – | 0.76 / 0.02 (n=117) |

## By fault

| Fault | Arm | v1 | v2 |
|---|---|---|---|
| F1 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F1 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F1 | agent_mitigate | 1.00 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F1 | agent_remediate | 0.60 / 0.00 (n=10) | 0.90 / 0.10 (n=10) |
| F1 | agent_free | – | 1.00 / 0.00 (n=10) |
| F2 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F2 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 1.00 (n=10) |
| F2 | agent_mitigate | 0.00 / 1.00 (n=10) | 0.00 / 1.00 (n=10) |
| F2 | agent_remediate | 0.90 / 0.10 (n=10) | 1.00 / 0.00 (n=10) |
| F2 | agent_free | – | 1.00 / 0.00 (n=10) |
| F3 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F3 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F3 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F3 | agent_remediate | 1.00 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F3 | agent_free | – | 0.90 / 0.00 (n=10) |
| F4 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F4 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F4 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F4 | agent_remediate | 0.60 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F4 | agent_free | – | 0.20 / 0.00 (n=10) |
| F5 | idle | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F5 | restart_loop | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F5 | agent_mitigate | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F5 | agent_remediate | 1.00 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F5 | agent_free | – | 1.00 / 0.00 (n=10) |
| F6 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F6 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 1.00 (n=10) |
| F6 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.00 / 0.90 (n=10) |
| F6 | agent_remediate | 1.00 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F6 | agent_free | – | 1.00 / 0.00 (n=10) |
| F7 | idle | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F7 | restart_loop | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F7 | agent_mitigate | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F7 | agent_remediate | 1.00 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F7 | agent_free | – | 1.00 / 0.00 (n=10) |
| F8 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F8 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F8 | agent_mitigate | 1.00 / 0.00 (n=10) | 0.90 / 0.00 (n=10) |
| F8 | agent_remediate | 0.60 / 0.00 (n=10) | 0.67 / 0.00 (n=6) |
| F8 | agent_free | – | 1.00 / 0.00 (n=9) |
| F9 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F9 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F9 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.60 / 0.00 (n=10) |
| F9 | agent_remediate | 0.70 / 0.00 (n=10) | 1.00 / 0.00 (n=10) |
| F9 | agent_free | – | 1.00 / 0.00 (n=10) |
| F10 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F10 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F10 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F10 | agent_remediate | 1.00 / 0.00 (n=10) | 0.80 / 0.10 (n=10) |
| F10 | agent_free | – | 0.88 / 0.00 (n=8) |
| F11 | idle | 0.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F11 | restart_loop | 0.00 / 0.00 (n=10) | 0.00 / 1.00 (n=10) |
| F11 | agent_mitigate | 0.00 / 0.00 (n=10) | 0.30 / 0.00 (n=10) |
| F11 | agent_remediate | 1.00 / 0.00 (n=10) | 0.30 / 0.50 (n=10) |
| F11 | agent_free | – | 0.10 / 0.20 (n=10) |
| F12 | idle | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F12 | restart_loop | 1.00 / 0.00 (n=10) | 0.00 / 0.00 (n=10) |
| F12 | agent_mitigate | 1.00 / 0.00 (n=10) | 0.20 / 0.00 (n=10) |
| F12 | agent_remediate | 1.00 / 0.00 (n=10) | 0.40 / 0.00 (n=10) |
| F12 | agent_free | – | 0.10 / 0.00 (n=10) |

## Where v1 measured wrongly

- Faults where v1's idle arm still 'recovered' (weak oracle): F5, F7, F12
- Faults where v2's idle arm still 'recovered': none
- Large changes (>= 0.30) in the real recovery rate between v1 and v2:
  - F1/agent_remediate: real recovery 0.60 -> 0.90
  - F4/agent_remediate: real recovery 0.60 -> 1.00
  - F5/agent_mitigate: real recovery 1.00 -> 0.00
  - F7/agent_mitigate: real recovery 1.00 -> 0.00
  - F9/agent_mitigate: real recovery 0.00 -> 0.60
  - F9/agent_remediate: real recovery 0.70 -> 1.00
  - F11/agent_mitigate: real recovery 0.00 -> 0.30
  - F11/agent_remediate: real recovery 1.00 -> 0.30
  - F12/agent_mitigate: real recovery 1.00 -> 0.20
  - F12/agent_remediate: real recovery 1.00 -> 0.40
