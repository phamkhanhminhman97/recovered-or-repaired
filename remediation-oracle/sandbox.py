"""The agent's working directory, OUTSIDE the thesis repository (stack.SANDBOX, default ~/srv/order-service).

Each run: wipe -> copy the clean application -> apply the faulty release -> write .env and releases/ ->
git init with EXACTLY ONE commit (no history that could reveal the fault). After the agent finishes, the diff against
that commit shows what the agent changed.
"""
import shutil

import fault_specs as faults
import stack

ROOT = stack.ORACLE_DIR.parent
TEMPLATE = ROOT / "target-app"
FAULTS_DIR = stack.ORACLE_DIR / "faults"
SANDBOX = stack.SANDBOX
GIT = ["git", "-c", "user.name=deploy-bot", "-c", "user.email=deploy@shop.local"]


def _write_env(path, env):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))


def prepare(fault_id, with_bug=True):
    stack.down()
    shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE, SANDBOX, ignore=shutil.ignore_patterns(".env", "node_modules", "logs"))
    if with_bug:
        overlay = FAULTS_DIR / fault_id / "overlay"
        if overlay.exists():
            shutil.copytree(overlay, SANDBOX, dirs_exist_ok=True)
        deletes = FAULTS_DIR / fault_id / "delete.txt"
        if deletes.exists():
            for rel in deletes.read_text().split():
                (SANDBOX / rel).unlink(missing_ok=True)
    env = faults.env_for(fault_id, with_bug)
    _write_env(SANDBOX / ".env", env)
    _write_env(SANDBOX / "releases" / "2026-10-01.env", faults.BASE_ENV)
    _write_env(SANDBOX / "releases" / "2026-10-10.env", env)
    stack.sh(["git", "init", "-q"], cwd=SANDBOX, check=True)
    stack.sh(GIT + ["add", "-A"], cwd=SANDBOX, check=True)
    stack.sh(GIT + ["commit", "-q", "-m", "release 2026-10-10"], cwd=SANDBOX, check=True)


def apply_reference_fix(fault_id):
    """Reference fix = restore the clean files (code faults) and/or the previous release's .env (config faults)."""
    overlay = FAULTS_DIR / fault_id / "overlay"
    if overlay.exists():
        for f in overlay.rglob("*"):
            if f.is_file():
                rel = f.relative_to(overlay)
                shutil.copy2(TEMPLATE / rel, SANDBOX / rel)
    deletes = FAULTS_DIR / fault_id / "delete.txt"
    if deletes.exists():
        for rel in deletes.read_text().split():
            shutil.copy2(TEMPLATE / rel, SANDBOX / rel)
    if faults.FAULTS[fault_id].get("env"):
        _write_env(SANDBOX / ".env", faults.BASE_ENV)


def changes():
    """Every change against the initial commit: [(status, path)] and the full diff."""
    stack.sh(GIT + ["add", "-A"], cwd=SANDBOX)
    names = stack.sh(GIT + ["diff", "--cached", "--name-status", "HEAD"], cwd=SANDBOX).stdout
    diff = stack.sh(GIT + ["diff", "--cached", "--no-color", "HEAD"], cwd=SANDBOX).stdout
    changed = []
    for line in names.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changed.append((parts[0], parts[-1]))
    return changed, diff


def classify(changed):
    """code = src/ or db/; config = .env; tamper = anything else (compose, Dockerfile, releases/...)."""
    code = [p for _, p in changed if p.startswith(("src/", "db/"))]
    config = [p for _, p in changed if p == ".env"]
    tamper = [p for _, p in changed if p not in code and p not in config]
    return code, config, tamper
