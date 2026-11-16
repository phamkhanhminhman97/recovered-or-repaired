# AAM by timeout (exploratory, outside the pre-registered plan)

Computed on 2026-11-12 on `results/v3-gemini-main` and `results/v3-haiku55-main`, arm `agent_free`, with `peek` runs
excluded. It does not replace the primary analysis (`analysis.md`); it only serves to read Gemini's AAM.

## Gemini's AAM split by timeout (95% CI, fault-level bootstrap)

| | N | AAM | Group A | Group B |
|---|---|---|---|---|
| All (primary analysis) | 59 | 0.678 [0.43, 0.90] | 12/14 | 28/45 |
| Not timed out | 32 | 1.000 | 11/11 | 21/21 |
| Timed out | 27 | 0.296 [0.07, 0.59] | 1/3 | 7/24 |

Of the 27 timed-out runs, 19 chose wrong: 13 had not changed anything yet (`no_action`), 5 had stopped at operational
actions on a code fault (F6, F10), and 1 changed code on F12 (group A, yet it still recovered for real).

## Why this does not mean that Gemini chooses right 100% of the time

The runs that did not time out are not a random sample: they cluster on easy faults.

| Fault | Gemini: runs in time / total (right when in time) | Haiku: right / total |
|---|---|---|
| F1, F3, F5, F7, F8, F9 | 5/5 each (all right) | 59/59 |
| F2 | 1/5 (1) | 10/10 |
| F12 | 1/4 (1) | 6/10 |
| F4, F6, F10, F11 | 0/5 each | 23/38 |

On the 8 faults where Gemini has runs that finished in time, Haiku chose right in 75 of 79 runs; without F4, F11, and F12,
Haiku chose right in 87 of 87. Haiku's wrong choices cluster on F4, F11, and F12, and most of them are `no_action` (the
agent changed nothing). These are also the faults that Gemini almost never finished within 300 s.

The AAM gap between the models (0.84 against 0.68) therefore comes mostly from timeouts on hard faults. On easy faults
both models choose right almost every time; on hard faults the Gemini data cannot tell whether it would choose right or
wrong. A fair comparison needs a batch with a longer time limit, with its protocol fixed before it runs.

