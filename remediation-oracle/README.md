# remediation-oracle

The three-round oracle, the harness, and the analysis code. The rules are in `../PRE-REGISTRATION.md`; setup and run
instructions are in `../docs/setup.md`. Modules import each other by bare name, so run commands from this directory.

| File | Role |
|---|---|
| `run_v3.py` | Entry point for the order-service batches: the validation gate, then the steps in the `STAGES` table (`--stages haiku,gemini,gemini-t900,wp4-sonnet,wp4-haiku`), then `analysis.py` and the peek, idle, and infrastructure gates of each set. Logs go to `../results/logs/` |
| `run_wp4.py` | Driver for WP4' (Sonnet 5.5 and Haiku 5.5 under isolation v4): waits for the validation run, checks isolation, runs a 6-run pilot, then `run_v3.py --stages wp4-sonnet,wp4-haiku` and `compare_wp4.py` |
| `harness.py` | Runs the trials (fault × arm × repeat) in an order shuffled with seed 20261014; resumable by fault, arm, repeat, and model; writes `pilot_results.jsonl`, `run_evidence.jsonl`, `transcripts/` |
| `oracle.py` | Sets up one run and scores the three rounds; `verdict()` returns `real`, `temp`, or `none` |
| `probes.py` | Incident load and pass criteria for each fault in each round; ticket text |
| `stack.py` | Docker control and outside measurement (psql, redis-cli, `docker stats`/`df`, the partner's admin API) |
| `sandbox.py` | The agent's working directory (`~/srv/order-service`): applies the faulty release and records what the agent changed |
| `fault_specs.py`, `faults/` | The 12 faults: group, configuration variable, replacement files (F7 uses `delete.txt`) |
| `infra/` | The simulated partner (`partner-api/server.py`, run on the host since v3) and the forwarding port inside Docker (`gateway/`) |
| `agent_llm.py` | Runs the pinned Codex CLI inside `sandbox-exec`; per-arm prompts; reads events and session logs; `peek` and `partner_inspect` flags; guards for provider quota and latency |
| `docker_guard.py` | Docker API proxy for isolation v4 (`SELFHEAL_ISOLATION=v4`): refuses host mounts outside the workspace, privileged containers and execs, swarm, and plugins, and logs every refusal. Used by WP4' |
| `check_isolation.py` | Checks isolation v4 before a batch: 49 commands inside `sandbox-exec` with the agent's environment, from normal Docker and Compose use to each known bypass; every case must meet its expectation. No model calls |
| `validate_oracle.py` | Oracle validation gate (37 scenarios × 3), no AI calls |
| `analysis.py` | RSR, SSR, MSR, AAM, RQ3, CMH, and sensitivity to the handling of peek runs, written to `<set>/analysis.md` (needs numpy and scipy) |
| `cross_model.py` | Puts the main sets side by side, runs the exploratory analyses (timeouts, pass^k, peek sensitivity, repair mechanism, cost), and draws the figures: `../results/cross_model.md`, `../results/figures/` (also needs matplotlib) |
| `mechanism.py` | Repair mechanism of a run from the evidence (where the change was made, whether it removed the fault or worked around it, per-fault repair signatures); standard library only; used by `cross_model.py` and `../paper/make_tables.py` |
| `compare_wp4.py` | WP4' comparison of Sonnet and Haiku under isolation v4, written to `../results/wp4-compare.txt` |
| `export_claims.py` | RQ3 rating package: exports the agents' closing messages for two raters (fault, arm, and model hidden) and merges their labels into `<set>/claims_labels.csv` (`--merge`); guide: `../docs/rq3-rating-guide.md` |
| `rescore_peek.py` | Rescores a set's peek flags under the 2026-11-07 definition (used for `v3-gemini-main`); it needs the command output, which the public copy removes |
| `compare_v1_v2.py` | Compares v1 with a v2 or v3 set (`../results/compare_v1_v*.md`) |
| `make_artifact.py` | Builds the public copy in a directory the agent sandbox blocks: drops private notes, replaces paths, e-mail addresses, and host names, removes captured command output, and scans for leftovers. It stays in the working repository and is not part of the public copy |
| `tests/` | `python -m unittest discover -s tests`: peek flags on real commands, session log parsing, run order, resume, action classification, the three-round verdict, the fault catalog, statistics, repair mechanism (`test_mechanism.py`), the RQ3 package, the Docker proxy logic, and the check that turning isolation v4 off keeps v3 behavior (`test_docker_guard.py`) |

Scripts removed on 2026-11-12 remain in the history of the working repository (the `harness` field of each run names the
commit that ran it): `run_pipeline.py` and `run_gemini.sh` (v2 drivers), `quarantine_slow.py` (split the slow runs of
`v2-haiku55-main`), `summarize_results.py` (replaced by `analysis.py`), and `models.py`, `metrics.py`, `classify.py`,
and `tests/test_metrics.py` (a September 2026 specification with a group C and SREGym that was never on the run path).
Version 1 of the oracle is the tag `v1-leaky` in the working repository.
