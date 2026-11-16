# Setup and running the experiments

Written on 2026-11-12 from the handover notes made when the study moved from a Mac mini to a MacBook (2026-10-23). It
has been run on macOS 27 with an Apple M1 Pro, 32 GB of memory, and Docker Desktop with 2 CPUs and 4 GB.

## Requirements

| Component | Notes |
|---|---|
| macOS | The agent is isolated with `sandbox-exec`, which exists only on macOS |
| Docker Desktop | Each run starts the application (app, Postgres, Redis) and the partner's forwarding port |
| Python 3.9 or later | The harness, the oracle, and the validation use only the standard library. `analysis.py` and `cross_model.py` need `requirements.txt` (numpy, scipy, matplotlib; numpy 2.4 needs Python 3.11 or later) |
| A local model proxy | An OpenAI-compatible endpoint at `http://127.0.0.1:10100/v1` that serves the models under test (`agent_llm.AGENT_CONFIG`). Codex reads the model list from `model-proxy-catalog.json` in the agent tools directory |
| Codex CLI pinned to `0.163.0-alpha.11.1` | Installed as below; the `codex` on `PATH` is not used |

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt   # the analysis runs with .venv/bin/python
npm install --prefix ~/.local/share/oncall-tools/codex-0.163.0-alpha.11.1 @openai/codex@0.163.0-alpha.11.1
cp <your-model-catalog>.json ~/.local/share/oncall-tools/model-proxy-catalog.json
```

`remediation-oracle/infra/.admin_token` is generated on the first run and ignored by git.

## Agent isolation (v3)

- The agent is `codex exec` from the pinned build, with a clean `CODEX_HOME` recreated for each run at
  `~/.local/share/oncall-tools/codex-home` (no MCP, plugins, `AGENTS.md`, or session history). It runs inside
  `sandbox-exec` with the profile `agent_llm.SANDBOX_PROFILE`, which
  - denies reads and writes to the research repository, `~/srv/acme-payments` (the partner code), `~/Documents` (the
    repository's real git directory sat under the parent workspace's `.git/modules/`), and the data of AI tools on the
    machine (`agent_llm.DENY_PATHS`). When a machine has a new AI tool, add its data and log directories and record the
    change in the pre-registration. Since 2026-11-12 the list includes `~/Library/Logs/com.openai.codex`, where the Codex
    app writes reasoning summaries of its sessions;
  - denies outbound connections to `localhost:18080`, the partner port on the host.
- While an experiment runs, keep all study material inside the denied directories. The sandbox blocks only the list above,
  and the agent can read `/tmp`, `~/.local/share`, Desktop, Downloads, and most of `~/Library` (a Gemini agent once read
  `/tmp`). Keep repository copies, rendered pages of the paper, analysis output, and backups in `~/Documents`
  (pre-registration log, 2026-11-12).
- The agent's working directory is `~/srv/order-service`, rebuilt for each run from `target-app/` plus the faulty release,
  as a git repository with a single commit.
- The partner (`infra/partner-api/server.py`) runs with `python3` on the host at `127.0.0.1:18080` and stores only hashes
  of its key and token. Docker holds only the forwarding port `acme-payments-gateway-1` (alias `partner-api`, network
  `shop-partners`).
- Limits of v3, which apply to the sets already run: the Docker daemon runs outside the sandbox, so `docker run -v <repo>`
  still works and is caught only by the `peek` flag (E1 stopped for this reason). The sandbox does not stop signals: one
  Gemini run's `kill -9 $(lsof -t -i:18080)` killed both the partner and the Docker Desktop process, and the agent then
  reopened Docker. The agent inherits every environment variable of the harness shell (`SSH_AUTH_SOCK`, the Codex app's
  tool socket, `TMUX`), and it can read `~/.ssh`, query the keychain, attach to the harness's tmux session, and open
  applications (`open`, `osascript`). Apart from Docker in E1, no run used these paths (pre-registration log,
  2026-11-13). Isolation v4 closes them.
- Flags: `peek` (excluded from the primary analysis) is a successful access to the repository, the oracle, the partner
  directory or port, or the admin token, or any access through Docker (`agent_llm.access_kind`). `peek_any` is the earlier
  definition (any command containing a marker). `partner_inspect`, `tamper`, and `timed_out` are kept and reported
  separately.

## Isolation v4 (built 2026-11-13, used in WP4')

`SELFHEAL_ISOLATION=v4` turns it on. When it is off, the sandbox profile and the agent's environment are identical to v3
(`tests/test_docker_guard.py`). A new batch that uses it needs its protocol fixed in the pre-registration first.

- Docker goes through the proxy `docker_guard.py`: one process per run, a socket at
  `~/.local/share/oncall-tools/docker-api.sock`, and the agent's `DOCKER_HOST` pointing to it. The proxy refuses bind
  mounts and `device` volumes outside the workspace, privileged containers and execs, `--pid/--ipc/--userns host`,
  dangerous capabilities, devices, `--volumes-from`, `seccomp=unconfined`, swarm, plugins, and secrets. The sandbox blocks
  every other runtime socket (Docker Desktop, OrbStack, Colima, Lima, Rancher, Podman) and forbids creating symlinks in the
  workspace. Each refusal is recorded under `docker_denied` in the evidence, and its message contains
  `docker_guard.DENY_MSG`, so a refused command counts as blocked when `peek` is scored.
- The environment is minimal: only `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `TMPDIR`, `LANG`, `LC_*`, and `TERM`
  (`agent_llm.AGENT_ENV_KEYS`), plus `CODEX_HOME` and `DOCKER_HOST`.
- The sandbox also blocks `~/.ssh`; the ssh-agent, tmux, and Codex app tool sockets; running `security`,
  `git-credential-osxkeychain`, `open`, `osascript`, `shortcuts`, `automator`, `screencapture`, and `pbpaste`; the
  Docker TCP ports 2375 and 2376; writes to the Docker Desktop settings; and signals to processes outside the sandbox (the
  agent can still stop its own processes).
- Before each batch, `../.venv/bin/python check_isolation.py` (with Docker running and no experiment running) must pass
  all 49 cases.
- Two gaps are handled by operation. Containers the agent creates can reach the Internet, because the daemon runs outside
  the sandbox, so the repository must stay private while a batch runs. `ps` shows the harness command line, so give the
  tmux session a neutral name (for example `tmux new -s oncall`).

## Running

```bash
cd remediation-oracle
../.venv/bin/python -m unittest discover -s tests          # unit tests (without numpy the statistics tests are skipped)
python3 validate_oracle.py --reps 3                         # oracle validation gate, about 2 hours, no AI calls, must be 111/111
caffeinate -is ../.venv/bin/python -u run_v3.py --stages haiku,gemini   # in tmux: gate, each step, analysis, per-set gates
../.venv/bin/python analysis.py ../results/v3-gemini-main   # rerun the analysis of one set
../.venv/bin/python cross_model.py                         # pooled analysis and figures (../results/cross_model.md, figures/)
python3 harness.py --n 1 --faults F2 --arms agent_free --model gemini-3.8-flash --out /tmp/try   # one trial run
```

- For long runs on a laptop, use `tmux`, keep the machine on power, and keep the lid open (`caffeinate` does not prevent
  sleep when the lid is closed).
- Progress is in `results/logs/pipeline_status.json`, `results/logs/pipeline.log`, and `results/logs/<step>.log`.
- The steps of `run_v3.py` live in the `STAGES` table: `haiku` (N = 10, 5 arms), `gemini` (N = 5, 3 AI arms, 300 s),
  `gemini-t900` (E1: like `gemini` with a 900 s limit, writing to `results/e1-gemini-t900`; stopped on 2026-11-12, data in
  `results/e1-gemini-t900-stopped-6runs`), and `wp4-sonnet` and `wp4-haiku` (WP4', driven by `run_wp4.py`). The time
  limit reaches the harness through `SELFHEAL_AGENT_TIMEOUT_S` and is recorded in each run's evidence
  (`agent_timeout_s`).
- After a shutdown or reboot, start Docker and rerun with `--skip-validation --validation-since <start time of the gate>`.
  The harness resumes from the missing runs; an interrupted run is dropped and run again.
- On a new machine, rerun the validation gate there before any agent run and record its time in the pre-registration.
- The SREGym study (WP2) has its own setup: SREGym commit `909f558` with `sregym-oracle/sregym-909f558.patch`, a
  four-node kind cluster, and the `svelte` profile. See `sregym-design.md`.

## Environment variables

| Variable | Default | Used for |
|---|---|---|
| `SELFHEAL_SANDBOX` | `~/srv/order-service` | The agent's working directory (`stack.py`) |
| `SELFHEAL_PARTNER_DIR` | `~/srv/acme-payments` | Where the partner is deployed (`stack.py`) |
| `SELFHEAL_PARTNER_MODE` | `host` | `docker` is the v2 mode, in which the agent could read the partner code |
| `SELFHEAL_AGENT_TOOLS` | `~/.local/share/oncall-tools` | The pinned Codex and the agent's `CODEX_HOME` (`agent_llm.py`) |
| `SELFHEAL_AGENT_TIMEOUT_S` | `300` | Time limit per agent run |
| `SELFHEAL_REASONING_EFFORT` | `medium` | Fixed reasoning effort for the agent |
| `SELFHEAL_MODEL` | `claude-haiku-4-5` | Default model of `harness.py` when `--model` is not given (`run_v3.py` always passes it) |
| `SELFHEAL_IDLE_WAIT_S` | `120` | Wait time of the `idle` arm |
| `SELFHEAL_ISOLATION` | (empty) | `v4` turns on isolation v4 (`agent_llm.py`) |
| `SELFHEAL_DOCKER_UPSTREAM` | `~/.docker/run/docker.sock` | The real Docker socket that `docker_guard.py` forwards to |

