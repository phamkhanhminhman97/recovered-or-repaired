# Recovered or Repaired?

This repository is the artifact of the paper "Recovered or Repaired? A Three-Round External Oracle for LLM Agents on
Backend Incident Remediation" by Pham Khanh Minh Man (The University of Danang, University of Science and Technology). It
holds the oracle and the harness, the faulty releases, the port of the oracle to SREGym, the pre-registration log with its
edit history, every run record, the analysis code, and the LaTeX sources of the paper.

Benchmarks for incident-handling agents usually ask one question at the end of an episode: is the system healthy again? A
restart, a bigger connection pool, or an emptied log directory can make a symptom go away while the fault stays in the
code. The oracle here scores from outside the system in three rounds. Round 1 replays normal traffic; round 2 replays the
incident-inducing load on the same system; round 3 replays it on a system rebuilt from the code and configuration the
agent left. A run that passes all three rounds is a real recovery, and a run that passes round 1 but fails a later round
is a temporary one.

## Results

The order service has 12 injected faults and five arms: do nothing, restart, and an LLM agent (Codex CLI) that may only
mitigate, must fix the code, or decides freely. The oracle was validated first on 37 scenarios with reference fixes, and
111 of 111 runs came out as expected.

| v3 study | Claude Haiku 5.5 (600 runs) | Gemini 3.8 Flash (180 runs) |
|---|---|---|
| Real recovery (RSR): mitigate / remediate / free | 0.25 / 0.84 / 0.76 | 0.42 / 0.55 / 0.64 |
| Temporary share of the conventional successes, mitigation arm | 39% | 33% |
| AAM (free arm picks the right kind of action) | 0.84 | 0.68 |
| Mitigate against remediate on real recovery (CMH) | OR 0.08, p < 0.0001 | OR 0.68, p = 0.27 |
| Runs that hit the 300 s limit | 0 | 86 of 180 |
| Peek gate (at most 5% of AI runs) | passed, 7 of 360 | passed narrowly, 9 of 180 |
| Exploratory: real recovery with the fault removed from the code, 9 code faults (mitigate / remediate / free) | 0 / 0.89 / 0.77 | 0 / 0.61 / 0.58 |

Auditing the fixes shows a second gap. Every real recovery of the mitigation arm on a code fault was a durable
configuration workaround, such as `POOL_MAX=1`, a one-connection database pool that avoids the F9 deadlock, or
`LOG_LEVEL=warn`, which slows the F11 log growth past the load window; the three rounds credit both. Five more real
recoveries changed code without repairing the defect. With one fault left out at a time, Haiku's
mitigate-against-remediate comparison holds, while Gemini's p ranges from 0.017 to 1.0, so its non-significant result says
little. The two models ran under different isolation, and Gemini timed out in almost half of its runs; read
`docs/methodology.md` before comparing them.

A follow-up (WP4') ran Sonnet 5.5 and Haiku 5.5 on the same faults under one isolation level (v4), 72 runs each.

| WP4' | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|
| Mitigation arm: temporary share of MSR | 0.25 | 0.43 |
| Remediation arm: RSR | 0.92 | 0.80 |

On the four faults that both models mitigated, every run got the same verdict, so the pre-registered CMH test of the
mitigation arm is undefined; on those faults, whether a fix was temporary depended on the fault alone. The
remediation-arm difference is OR 5.00, p = 0.153.

WP2 applied the extra rounds to eight SREGym-Lite problems (commit `909f558`). In group A, SREGym's oracle has no
durability step; in group B it already replays the load or reruns the work.

| WP2 | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Group A: accepted by SREGym's oracle | 16 of 20 | 17 of 20 |
| Group A: temporary among accepted (Wilson 95% CI) | 0 of 16 (0.00 to 0.19) | 0 of 17 (0.00 to 0.18) |
| Group B: accepted by SREGym's oracle | 0 of 20 | 3 of 20, all durable |

Before any agent ran, hand-written workarounds that SREGym's oracle accepts failed round 2 or 3 in three of the four
group A problems, three repeats each. The agents' accepted fixes were all durable, and no run was flagged `peek`.

Keeping the agents from reading the answer took four rounds of isolation. Agents located the grader with `lsof`, read the
partner's code through `docker exec`, called hidden ports, and mounted the home directory into a new container; each
episode is in the pre-registration log and in `docs/methodology.md`.

## Layout

```
PRE-REGISTRATION.md      the pre-registration log, English translation (the Vietnamese original is authoritative)
PRE-REGISTRATION.vi.md   the original log: the frozen protocol and every later change, with dates
docs/                    methodology, setup, fault catalog, RQ3 rating guide, SREGym design, pre-registration history
target-app/              the clean order service (Node, Express, BullMQ, Postgres, Redis), without faults
remediation-oracle/      the three-round oracle, harness, faulty releases (faults/), simulated partner (infra/), analysis
sregym-oracle/           rounds 2 and 3 for SREGym, the WP2 driver, its analysis, and the SREGym patch
results/                 every run record, the analysis reports, and the figures (index: results/README.md)
paper/                   LaTeX sources; tables/ is generated from results/ by make_tables.py
```

## Reproducing the numbers from the released data

This needs Python 3.11 or later and no Docker or model access. The statistics use a fixed seed, so the regenerated files
match the committed ones; the figures are byte-identical.

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd remediation-oracle
../.venv/bin/python -m unittest discover -s tests             # 41 tests
for s in v3-haiku55-main v3-gemini-main wp4-sonnet-v4 wp4-haiku-v4; do ../.venv/bin/python analysis.py ../results/$s; done
../.venv/bin/python cross_model.py                            # results/cross_model.md and results/figures/
../.venv/bin/python compare_wp4.py                            # WP4' comparison
python3 ../sregym-oracle/analyze_wp2.py ../results/sregym-wp2/runs.jsonl ../results/sregym-wp2-sonnet/runs.jsonl
cd ../paper && ../.venv/bin/python make_tables.py             # paper/tables/*.tex
git status --short                                            # no changes expected
```

`analysis.py` takes a few minutes per set because of the bootstrap.

## Rerunning the experiments

The order-service study runs on macOS (the agent is confined with `sandbox-exec`) with Docker Desktop, the pinned Codex
CLI `0.163.0-alpha.11.1`, and an OpenAI-compatible endpoint that serves the models under test. `docs/setup.md` covers the
installation, the isolation levels, the run commands, and recovery after a reboot. The validation gate
(`validate_oracle.py`, about two hours, no model calls) must pass on a new machine before any agent run. The SREGym study
needs SREGym at commit `909f558` with `sregym-oracle/sregym-909f558.patch` and a kind cluster; see
`docs/sregym-design.md`.

## Pre-registration

The protocol, the per-fault criteria, the run counts, and the analysis were fixed before the runs in a log kept in the
repository, and every later change was added to the log with its date and reason. The log was written in Vietnamese;
`PRE-REGISTRATION.vi.md` is the original and `PRE-REGISTRATION.md` is a translation. The log was not filed with a public
registry, so its dates rest on the log itself and on the git history of the working repository, exported to
`docs/pre-registration-history.patch`. The author often committed several entries at once, so a commit date shows that an
entry existed by then; it does not prove that each entry preceded its runs.

## Material in Vietnamese

Some files stay in Vietnamese because they are part of the experiment or its record:

- the incident tickets that the harness writes (`remediation-oracle/probes.py`; the prompt around them is English) and the
  keyword screen for Vietnamese closing messages in `analysis.py`;
- the agents' messages and commands in the run records (92 of 360 Haiku v3 closing messages are mainly Vietnamese, as are
  many in the RQ3 rating package);
- the original pre-registration and its history;
- the `*.patch` files that record the exact code that ran, including the SREGym patch, whose hash is in the
  pre-registration.

Commit IDs in the run records refer to the private working repository, whose history holds personal notes. Editors and
reviewers can ask the author for access.

## Data in the public copy

`results/README.md` describes every set and what the public copy changes: home directory paths, e-mail addresses, host
names, and the names of the local model proxy and its providers are replaced; captured command output is removed from the
run evidence and session logs; the operational logs, the agent logs of the stopped Google arm of WP2, and the RQ3 keys are
left out. The withheld files are available to editors and reviewers on request.

## License and citation

Code (`remediation-oracle/`, `sregym-oracle/`, `target-app/`, and the scripts in `paper/`) is under the MIT license in
`LICENSE`. Data and documentation (`results/`, `docs/`, `paper/`, and the Markdown files) are under CC BY 4.0 in
`LICENSE-DATA`. `paper/sn-jnl.cls` and `paper/sn-mathphys-ay.bst` belong to the Springer Nature LaTeX template and are
under the LPPL. To cite this work, see `CITATION.cff`.

