# Methodology

The procedure, the per-fault criteria, the run counts, and every change are fixed in `../PRE-REGISTRATION.md`; the
faults are listed in `fault-catalog.md`. This document collects the terms, what version 1 of the harness taught us, how
agent isolation evolved, and the threats to validity.

## Terms

| Term | Meaning |
|---|---|
| Fault (F1 to F12) | A faulty release applied to the clean application in `target-app/` |
| Group A / B | A (F1, F8, F12): the correct action is a configuration rollback. B (the other 9): the code must be fixed |
| Arm | `idle` (does nothing, waits 120 s), `restart_loop` (restarts twice), `agent_mitigate` (the agent may use only operational actions), `agent_remediate` (the agent must fix the code), `agent_free` (the agent decides) |
| Round 1 | The fault's criterion on the system the arm left: a light load for F2, F6, F11, and the same probe as round 2 for the other nine |
| Round 2 | The same incident-inducing load on the same system, without a restart: does it break again? The fault is not reinjected |
| Round 3 | Rebuild from scratch from the code and `.env` the agent left, then rerun the incident load: does the fix live in code or configuration? |
| Durable fix (RSR) | Passes all three rounds; called real recovery in the pre-registration and the analysis reports. It can still leave the defect in place (threats below) |
| Temporary recovery (SSR) | Passes round 1 but fails round 2 or 3 |
| MSR | Passes round 1, so durable plus temporary; this is what a single check records |
| AAM | Share of runs in which the agent picks the right kind of action (`agent_free` only): operational actions only for group A, a code fix for group B |
| Flags | `peek` (successful access to the oracle or the partner's infrastructure; the run is excluded), `peek_any` (the earlier definition, kept for the sensitivity report), `partner_inspect`, `tamper`, `timed_out` (kept and reported separately) |

Statistics (`remediation-oracle/analysis.py`): 95% confidence intervals from a bootstrap that resamples faults (B = 5000,
seed 20261014); arm comparisons with a Cochran-Mantel-Haenszel test stratified by fault. RQ3 needs labels from two
independent raters (`export_claims.py`, `rq3-rating-guide.md`) and is deferred in the first paper.

## What version 1 taught us

Each item was fixed from v2 on.

- The agent could see the answer: "correct answer" notes, `manifest.js`, an `if (fixed)` branch, `FAULT_ID` in the logs.
  Since v2 the application is clean, faults ship as releases, the agent works outside the repository, and commands that
  read the oracle are detected.
- The oracle trusted numbers the app reported about itself (`/metrics`, `/debug/state`), and the agent could edit that
  code. The oracle now measures in Postgres, Redis, Docker, and on the partner side.
- Readiness waits differed between arms and produced a spurious SSR for F2 (with no agent at all it "passed, then broke" in
  3 of 3 runs). Every arm now uses one HTTP readiness wait, and the rebuild after each AI run is gone.
- Three criteria could not tell the faulty release from the fixed one (F5, F7, F12), and two measured implementation details
  (F9, F10). The criteria are now behavioral, and an oracle validation gate is mandatory.
- Agent processes that outlived the time limit kept running and ran `git add`, contaminating 214 runs. The whole process
  tree is now killed, and each run gets its own sandbox.
- The do-nothing arm was scored at once, so self-healing went unmeasured. It now waits 120 s.

## Agent isolation across batches

| Batch | Partner | Agent | Leaks caught |
|---|---|---|---|
| v2 | Inside Docker | Detection from the command list only | Haiku 5.5: peek 31/360 (`docker exec` read the partner code); Gemini: `lsof` found the repository, then `docker exec` (peek 46%) |
| v3, Haiku | On the host; Docker holds only a forwarding port | `sandbox-exec` denies the repository and the partner directory | Peek 7/360 |
| v3, Gemini | As above | Also denies `~/Documents`, AI tool data, and port 18080; pinned Codex with a clean `CODEX_HOME`; peek counts only successful accesses | Peek 9/180 (manual review: 1 run touched the real partner with `kill -9` on the partner process) |
| E1, Gemini, 900 s | As above | Also denies the remaining logs and AI tool data, including the Codex app log, which holds reasoning summaries about the study design; no v3 run touched these directories | Stopped after 6 runs: 1 run used `docker run -v` on the home directory to read the repository, the faults, the oracle, and earlier results |
| v4 (built 2026-11-13, used in WP4') | As above | Also a Docker API proxy that refuses host mounts and privileged containers; a minimal environment; denies `~/.ssh`, ssh-agent, keychain, tmux, Codex tool sockets, launching apps, screen capture, and the clipboard; signals only within the sandbox (`setup.md`) | Host review after the data, and a command scan of every set: no run used these paths apart from listings (`env`, `tmux list-sessions`) and 1 run that restarted Docker after its own `kill -9` crashed it. `check_isolation.py` 49/49. WP4': peek 0/72 (Sonnet), 1/72 (Haiku) |
| WP2 (SREGym) | SREGym's own deployment | SREGym's agent container with filtered egress and hardening, and an empty `CODEX_HOME` (`sregym-design.md`) | Peek 0/40 (Haiku), 0/40 (Sonnet) |

## Threats to validity

- One application with 12 injected faults. The faults imitate common incident types and do not come from real incidents,
  so the results may not carry over to other systems. WP2 applies the oracle to eight SREGym problems written by another
  group (`sregym-design.md`).
- Agents run on a real machine with Docker access. In the v3 sets the sandbox blocked file reads and connections to the
  partner, but the Docker daemon ran outside the sandbox, the agent could still signal host processes, and it inherited the
  environment of the harness shell (`SSH_AUTH_SOCK`, Codex tool sockets). Runs flagged `peek` are excluded, and both
  definitions are reported (Haiku: string match 7/360, successful access 4/360; Gemini: 51/180 and 9/180;
  `../results/cross_model.md` section 5.3). In E1 (900 s) one agent mounted the home directory into a new container
  (`docker run -v`) to read the oracle. Isolation v4 (table above) closes these paths and was used for WP4'.
- The two models of the main study ran under different infrastructure (different isolation, different machines, different
  `peek` definitions; table above), so cross-model comparisons carry this caveat. The Haiku runs used the author's agent
  configuration, under which 17 of 360 agent runs called MCP tools, a subagent, or web search whose content was not
  recorded. WP4' reran Haiku next to Sonnet under v4, and Haiku's numbers stayed close to its main-study values
  (`../results/wp4-compare.txt`).
- The 300 s limit per agent run. Gemini timed out in 86 of 180 runs and Haiku in none; in the remediation and free arms,
  every Gemini run that did not time out recovered for real. Much of the gap between the models comes from this limit
  (`../results/v3-gemini-main/aam-by-timeout.md`). E1 (Gemini, 900 s, fixed in advance on 2026-11-12) was meant to separate
  this factor and stopped after 6 runs (table above), so the limit remains a confound.
- The oracle credits durable configuration workarounds (exploratory; `../results/cross_model.md` section 5.4). Round 3
  rebuilds from the code and `.env` the agent left, so a configuration change that removes the symptom for good passes all
  three rounds: `POOL_MAX=1` on F9 (no concurrency, hence no deadlock) and `LOG_LEVEL=warn` on F11 (the log fills more
  slowly than the load window lasts). In group B these are all the durable fixes of the mitigation arm (Haiku 9,
  Gemini 10). A code change is not always a fix either. Two Haiku runs work around the fault in code (F4 drops the currency
  conversion, F11 swallows log write errors), and 7 F2 runs drop the transaction, which ends the connection leak but leaves
  an order whose charge failed in `pending` (counting those as workarounds lowers Haiku's fault-removed RSR in the
  remediation arm from 0.89 to 0.82). Group B is therefore also reported as "RSR, fault removed from code"
  (`mechanism.repair`). Configuration faults show the same pattern: 3 F12 runs raise the number of parallel workers instead
  of returning the timeout to 500 ms (`mechanism.config_repair`).
- The criteria measure what the fault breaks, not every property of the service. The F4 criterion checks that orders are
  paid and that the partner accepts the transaction, not the amount, so one Haiku run that deleted the currency conversion
  was scored as a durable fix. The criteria were not changed after the data were seen (PRE-REGISTRATION log, 2026-11-12).
- Repeats on the same fault are not independent. The analysis works at the fault level (fault-level bootstrap, stratified
  CMH), and there are only 12 units. With one fault left out at a time (`../results/cross_model.md` section 5.7), Haiku's
  conclusions hold. For Gemini the mitigation-versus-remediation comparison always has an OR below 1 (0.42 to 0.93), but p
  ranges from 0.017 (without F12) to 1.0 (without F3), so no conclusion can be drawn.
- The pre-registration log lives in the repository and was not filed in a public registry, so its dates rest on the log
  itself and on the git history (`pre-registration-history.patch`). In the two main sets only one change happened
  mid-batch: the success-based `peek` definition, fixed after 15 Gemini runs whose scores had been seen (log 2026-11-07).
  It only rescored the flag, changed no score, and the earlier definition is reported alongside.
- Few models. The order-service study has Haiku 5.5 and Gemini 3.8 Flash, and WP4' adds Sonnet 5.5 next to Haiku 5.5. WP2
  has Haiku 5.5 and Sonnet 5.5; its Gemini arm stopped after the provider disabled the account.
- The oracle thresholds (time, memory, disk) were chosen for local Docker. They were fixed in advance and validated on the
  faulty and reference releases on both machines (111/111), but they may be sensitive to the machine.
- The harness writes the tickets from measurements, and their wording may steer the agent's diagnosis. The tickets are in
  Vietnamese without diacritics, while the prompt around them is in English (`remediation-oracle/probes.py`,
  `agent_llm.PROMPT`). Some closing messages are in Vietnamese as a result: 92 of 360 for Haiku v3, 8 of 72 for Haiku and
  3 of 72 for Sonnet in WP4', none of 180 for Gemini v3.
- RQ3 raters do not see the condition, but a message can reveal the arm indirectly (for example, "the incident scope does
  not allow code changes"), and timed-out runs often end mid-sentence and get the label `0`.
- Version 1 had measurement errors, found and fixed as listed above; v1 data are used only for description.

