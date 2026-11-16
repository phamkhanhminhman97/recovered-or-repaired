# WP2: the three-round oracle on SREGym

This document condenses the WP2 design notes, written on 2026-11-14 from the source of SREGym commit `909f558`. The
frozen design was copied into `../PRE-REGISTRATION.md` on 2026-11-14, before the first WP2 run, and the additions that
followed are logged there with dates. The code is in `../sregym-oracle/`.

## Question

RQ4, fixed before any run: on the SREGym-Lite problems that run on our machine, how many runs that SREGym's mitigation
oracle accepts break when the fault's own trigger fires again (round 2) or when every application pod is recreated from
its current spec (round 3)? And on the problems where SREGym already checks durability, does our round 2 agree with its
check? The second part tests how we designed round 2.

## Three rounds on Kubernetes

| Round | In the order service | On SREGym |
|---|---|---|
| 1 | Normal load | SREGym's own mitigation oracle (`mitigation_oracle`, no LLM), unchanged |
| 2 | Replay the incident load on the same system | Fire the fault's trigger again without reinjecting the defect: a new poison record, another password rotation, and so on (tables below). A problem without a separable trigger has no round 2 |
| 3 | Rebuild from the code and `.env` the agent left | Recreate the pods of every application workload (Deployment, StatefulSet) from the current spec, then rerun SREGym's oracle. This catches fixes that live only in the running state of a pod (a label set by hand on a pod, a runtime process setting). Data stores and infrastructure without durable volumes (Kafka, Mongo, Memcached, Postgres, Valkey, consul, jaeger, the monitoring stack) are not recreated: doing so loses data or service registrations and fails the oracle for reasons unrelated to the fix. Unlike round 3 in the order service, volumes are not rebuilt |

Round 3 does not rebuild from the Helm chart. SREGym injects faults into running objects, not into the chart, so a rebuild
from the chart would erase both the fault and the fix and measure nothing.

## The eight problems

Group A has a separable trigger, and SREGym does not check durability, so these problems measure the gap.

| Problem | Application | Where the fault is | SREGym accepts when | Rounds 2 and 3 | A workaround that can pass round 1 |
|---|---|---|---|---|---|
| `kafka_poison_pill_hol_block` | astronomy-shop | The consumer (code in the ConfigMap `orders-pipeline-scripts`) stops for good at an unreadable record | The consumer gets past the poison record, data stay intact, and it survives one consumer restart | Round 2: send a new poison record between valid records and measure progress again | Move the offset past the poison record (SREGym describes this as the mitigation); a durable fix routes bad records to a separate queue |
| `secret_rotation_stale_env_credentials_astronomy_shop` | astronomy-shop | product-catalog reads the database connection string once at start | Old pods replaced; the Secret, Postgres, and the init ConfigMap carry the new password; the value of product-catalog's setting equals the new string (a string hard-coded in the Deployment also passes); `/api/products` returns data | Round 2: rotate the password once more with the injector's steps (change the Postgres password, update the Secret, kill database sessions) plus the product-catalog restart that the rotation procedure includes; pass if `/api/products` returns data. Without that restart even SREGym's reference fix fails, because the app reads its environment only at start, and round 2 would lose its power to discriminate | Hard-code the new connection string in the Deployment: passes rounds 1 and 3, breaks at the next rotation |
| `internal_traffic_policy_local_astronomy_shop` | astronomy-shop | The Service has `internalTrafficPolicy: Local`, and one replica is pinned to one node | The policy is no longer Local, or every worker has an endpoint at scoring time | Round 3 is repeated three times (the scheduler places the pods anew each time); pass if SREGym's oracle passes all three times | Remove the node pin and scale to one replica per worker while keeping Local, with no spread constraint. Round 3 has a random element from the scheduler, so the rate across repeats is reported |
| `service_wrong_pod_selection_hotel_reservation` | hotel-reservation | The Service selector is widened, and the route label sits in the search Deployment's template | The frontend endpoints are clean and reachable | Round 3: recreate the search pods | Remove the label from the running pod; the template still carries it, so new pods dirty the endpoints again |

Group B already has a durability step in SREGym's oracle, so these problems test our round 2.

| Problem | Application | Step in SREGym's oracle | Our round 2 |
|---|---|---|---|
| `cronjob_sidecar_blocks_completion_hotel_reservation` | hotel-reservation | Runs a new Job from the fixed template (`fresh_job_did_not_complete`) | Wait for two scheduled runs |
| `finalizer_deadlock_controller_hotel_reservation` | hotel-reservation | Creates a new cleanup request (`cleanup_request_not_reconciled`) | Delete a new ConfigMap that carries the finalizer |
| `namespace_memory_limit` | hotel-reservation | Creates a new pod without a memory request (`fresh_pod_admission_failed`) | Recreate the pods of the other Deployments |
| `search_rate_retry_collapse_hotel_reservation` | hotel-reservation | Replays the load burst (`did_not_recover_after_trigger`) | Replay the load burst with the same configuration |

SREGym's own reference fix for the Kafka problem (`KafkaFaultInjector.recover`) moves the consumer group past the poison
record, which is exactly the mitigation that round 2 scores as temporary. This fits SREGym's framing of the problem as a
mitigation task: the first mitigation is correct but not durable. The paper therefore says that round 2 measures
durability, not that SREGym's oracle is wrong. Gate G2 needed a hand-written durable fix for this problem (the consumer
logs, commits, and skips unreadable records); it is in `sregym-oracle/gate.py`.

Excluded before any run: the WAF regex problem `edge_request_filter_cpu_saturation` (the fault did not reproduce on this
machine; Perl 5.34 matched `^([a-zA-Z]+)*$` against 5000 letters plus `!` in 0.19 s, so there was no exponential
backtracking to exploit), five static configuration problems with no separable trigger, and four social-network problems
whose images exist only for amd64.

## Agent isolation

SREGym's agent runs in its own container and reaches Kubernetes through `sregym/service/k8s_proxy.py`, which hides the
namespaces of the scoring infrastructure and the chaos resources and filters resources with a hidden label (the load
generators) out of listings. The oracle and the triggers run on the host (`main.py`), outside the container. By default
the container receives a copy of the host's Codex credential file; WP2 points `CODEX_HOME` of the `main.py` process to
an empty directory so that no credential reaches the container, and checks before the first run that
`/root/.codex/auth.json` does not exist in the container, that `~/srv/SREGym` is not readable, and that no other host port
is reachable. Runs use `--internet-access filtered` and `--container-hardening on`. A `peek` is a successful access to
oracle code, the fault injector, or SREGym's hidden namespaces (`sregym/service/agent_visibility_policy.py`); `audit_wp2.py`
lists candidates, and each decision, read by hand from the command output, is recorded in `peek_review.csv`.

The model proxy listens only on `127.0.0.1` and refuses requests whose `Host` is not `localhost` or `127.0.0.1`, while
SREGym's container calls `host.docker.internal`. `run_wp2.py` therefore runs a small bridge on `127.0.0.1:10101` that
forwards only the two model paths and rewrites `Host`; the proxy configuration is unchanged.

## Validation before any agent run

Gate G1 (2026-11-14) ran 12 of 17 SREGym-Lite problems once each on the MacBook. In all 12, SREGym's oracle failed while
the fault was active and passed after the reference fix (or a hand-written fix), and round 3 passed after the fix. In
three of the four group A problems SREGym accepted a hand-written workaround that round 2 or 3 caught: removing the pod
label (wrong pod selection; round 3 fails), moving the Kafka offset (round 2 fails, 5 of 10 records), and hard-coding the
rotated connection string (round 2 fails). The internal traffic policy workaround survived three pod recreations, so
SREGym's acceptance of it is reasonable on this cluster.

Gate G2 (2026-11-14, `svelte` profile) ran each of the eight problems three times, redeploying and reinjecting the fault
each time, and compared every step with its expected result (`sregym-oracle/check_g2.py`, logs in
`../results/sregym-gate/g2-svelte/`):

| Problem | Step sequence (P = pass, F = fail) | Matched |
|---|---|---|
| Wrong pod selection | faulty F, restart F, remove pod label P, round 3 F, reference fix P, round 3 P | 3/3 |
| Kafka | faulty F, restart F, move offset P, round 2 F, durable fix P, round 2 P, round 3 P | 3/3 |
| Password rotation | faulty F, restart P, round 2 P, round 3 P, hard-coded string P, round 2 F, round 3 P, reference fix P, round 2 P, round 3 P | 3/3 with the final code (repeats 3 to 5); repeat 2 differed |
| Internal traffic policy | faulty F, restart F, more replicas P, round 3 P three times, reference fix P, round 3 P | 3/3 |
| CronJob | faulty F, reference fix P, round 2 P, round 3 P | 3/3 |
| Finalizer | faulty F, restart F, reference fix P, round 2 P, round 3 P | 3/3 |
| Memory quota | faulty F, restart F, reference fix P, round 3 P | 3/3 |
| Search rate | faulty F, restart F (caught by SREGym's own replay step), round 2 F, reference fix P, round 2 P, round 3 P | 3/3 |

Repeat 2 of the password rotation problem differed in two steps (round 3 after the workaround and after the reference fix,
both `product_probe_failed` with `/api/products` hanging) because round 2's state restore did not kill database sessions
after the pod with the hard-coded string failed to start. After the fix (the restore kills sessions as the injector does,
checks `/api/products`, and records `restored`), repeats 4 and 5 matched. In the password rotation problem the restart arm
passes all three rounds: SREGym injects the fault so that the Deployment already reads the Secret and only the running pod
holds the old value, so a restart is the correct fix. The `gate.py` hash after G2 is `05f0de7e90a4` (first 12 hex digits
of the SHA-256). G2 took 3 h 49 min for 24 repeats.

## Frozen design (2026-11-14) and its additions

System: SREGym commit `909f558` plus `sregym-oracle/sregym-909f558.patch` (13 lines in `Conductor._evaluate_mitigation`
that call `gate.py <problem> post` after round 1 passes and before cleanup, and `agents.yaml` pinning Codex
`0.163.0-alpha.11.1`), a four-node kind cluster on the MacBook (arm64; Docker with 8 CPUs, 16 GB, 120 GB disk), and the
`svelte` profile, which drops components that no part of SREGym reads (Grafana, OpenSearch, and Jaeger bundled with
astronomy-shop, Alertmanager, Pushgateway, OpenEBS NDM). Scores are therefore not comparable with SREGym's leaderboard,
and WP2 does not compare with it. SREGym's mitigation oracle is unchanged.

Rounds: round 1 is SREGym's mitigation oracle within the run. Rounds 2 and 3 run through `gate.py` right after round 1, on
the state the agent left. Round 2 exists for Kafka (5 valid records, 1 poison record, 5 valid records; pass if all 10 are
processed within 180 s), password rotation (one more rotation, sessions killed, product-catalog restarted; pass if
`/api/products` returns data), CronJob (two new scheduled Jobs both complete within 300 s), finalizer (a new ConfigMap with
the finalizer is fully deleted within 60 s), and search rate (replay the burst, scored by SREGym's oracle). Round 3 runs on
all eight problems: recreate the pods, wait for every rollout plus 20 s, and score with SREGym's oracle up to 3 times, 20 s
apart; it passes if one attempt passes, and the number of attempts is recorded. Each run ends as not recovered (round 1
fails), temporary (round 1 passes, round 2 or 3 fails), or durable (every round the problem has passes).

Arms and runs: idle (score after 120 s) N = 3; restart (restart the faulty Deployment twice; the `RESTART` table in
`gate.py`; the CronJob problem has no such arm) N = 3; AI N = 5, using SREGym's built-in `codex` agent with SREGym's
standard task prompt, `--stages mitigation`, a 900 s limit (`--agent-timeout 900`; SREGym's default is 1800 s), and Codex
pinned to `0.163.0-alpha.11.1`. `run_wp2.py` runs 85 runs for Haiku 5.5 (40 AI, 24 idle, 21 restart) in an order shuffled
with seed `20261114`, redeploying and reinjecting the fault for every run, and writes `results/sregym-wp2/runs.jsonl` with
the `gate.py` hash in each record.

Repair signatures, fixed in advance to read the mechanism of durable and temporary runs: wrong pod selection is durable when
the route label is gone from the search Deployment's template or the Service selector is back to
`io.kompose.service=frontend`, and temporary when only a pod label changed; Kafka is durable when the consumer handles bad
records (code in the ConfigMap) or has an error queue, and temporary when the offset moved; password rotation is durable
when the Deployment references the Secret, and temporary when the connection string is hard-coded; internal traffic policy
is durable when the policy is no longer Local, and scaling replicas is reported separately (G1 showed that it survives pod
recreation on this cluster).

Analysis: primary, in group A, the share of AI runs that recovered only temporarily among the runs that passed round 1,
with a Wilson 95% interval, per problem and pooled, compared with the restart arm; in group B, the number of runs SREGym
passed that failed round 2 or 3 (expected near 0), reported as a check on the design of rounds 2 and 3; descriptive:
tokens, time, and repair mechanism by signature. Infrastructure errors (all three deployments failed, node disk above 95%)
do not count and are rerun once.

Additions, each logged in the pre-registration before the runs it governs:

- 2026-11-14, quota: an AI run in which Codex reports a provider error (429, rate limit, usage limit, quota, overloaded,
  resource exhausted) at any point is dropped without a result and rerun from scratch after 15 minutes, for at most
  12 hours; rerunning the command after the quota resets resumes from the unfinished runs. Runs dropped for quota are
  reported in the paper.
- 2026-11-14, a second AI arm with Gemini 4 Hydrogen, with everything else as for Haiku. It never ran: the model was
  withdrawn from the account before the batch (404 `model_unavailable`).
- 2026-11-15, the rule for the Google arm: try Hydrogen 3 times 10 minutes apart, otherwise run the same design with
  `gemini-3.8-flash` after 3 pilot runs. This arm stopped after its pilot and two main runs (the second cut off before
  scoring) when the provider disabled the account. Its run records are in `results/sregym-wp2-pilot-gemini38/` and
  `results/sregym-wp2-gemini38/` (agent logs
  withheld) and are not analyzed.
- 2026-11-15, a third AI arm with Sonnet 5.5, same design as Haiku (8 problems x 5 runs, 900 s, the same order; idle and
  restart shared), after 3 pilot runs that measured tokens (`results/sregym-wp2-pilot-sonnet/tokens.json`), driven by
  `sregym-oracle/run_wp2_queue.py`. The comparison of Sonnet with Haiku is descriptive.

