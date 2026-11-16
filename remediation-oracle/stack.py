"""Docker control and outside measurement. Every oracle measurement goes through here: Postgres and Redis
through 'docker exec', memory and disk through 'docker stats'/'df', the partner API through its admin port (token).
Nothing is read from /metrics or from any number the application code reports about itself.
"""
import json
import hashlib
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ORACLE_DIR = Path(__file__).resolve().parent
INFRA_DIR = ORACLE_DIR / "infra"
# Partner deployment directory OUTSIDE the repository (incident 2026-10-22: the docker compose working_dir label of the
# partner container and the cwd of the harness process revealed the repository path, and a Gemini agent read the oracle).
# The agent is blocked from reading both the repository and this directory (agent_llm: sandbox-exec).
DEPLOY_INFRA_DIR = Path(os.environ.get("SELFHEAL_PARTNER_DIR", str(Path.home() / "srv" / "acme-payments")))
# docker: the partner runs in a container (an agent's 'docker exec' can read its source -> peek).
# host  : the partner runs on the host from DEPLOY_INFRA_DIR (sandbox-exec blocks agent reads); Docker holds only
#         the forwarding port 'partner-api', so the agent can call only the public API, as with a real external service.
PARTNER_MODE = os.environ.get("SELFHEAL_PARTNER_MODE", "host")  # host tu 2026-10-22 (v3)
PARTNER_PORT = 18080
PAYMENT_KEY_SHA256 = "68bd6fe7343d06fa4c9f502d90b992995b55643d44c958b0463c1d811a2aa30b"
SANDBOX = Path(os.environ.get("SELFHEAL_SANDBOX", str(Path.home() / "srv" / "order-service")))
PROJECT = "shop"
APP_URL = "http://localhost:3000"
PARTNER_ADMIN_URL = "http://127.0.0.1:18080"
_TOKEN_FILE = INFRA_DIR / ".admin_token"


def sh(args, cwd=None, timeout=300, check=False, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=check, env=env)


def admin_token():
    if not _TOKEN_FILE.exists():
        _TOKEN_FILE.write_text(secrets.token_hex(16))
    return _TOKEN_FILE.read_text().strip()


# ---------------------------------------------------------------- partner API (phia oracle)
def infra_up():
    if PARTNER_MODE == "host":
        return _infra_up_host()
    env = dict(os.environ, ADMIN_TOKEN_SHA256=hashlib.sha256(admin_token().encode()).hexdigest())
    import shutil
    DEPLOY_INFRA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INFRA_DIR / "docker-compose.yml", DEPLOY_INFRA_DIR / "docker-compose.yml")
    shutil.copytree(INFRA_DIR / "partner-api", DEPLOY_INFRA_DIR / "partner-api", dirs_exist_ok=True)
    r = sh(["docker", "compose", "up", "-d", "--build"], cwd=DEPLOY_INFRA_DIR, env=env, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("infra up that bai: " + r.stderr[-2000:])
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            partner_admin("GET", "/_admin/stats")
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError("partner API not ready")


def _partner_alive():
    try:
        partner_admin("GET", "/_admin/stats")
        return True
    except Exception:  # noqa: BLE001
        return False


def _infra_up_host():
    import shutil
    d = DEPLOY_INFRA_DIR
    d.mkdir(parents=True, exist_ok=True)
    # Remove the old partner container (docker mode) if any, then start the forwarding port.
    old = sh(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=acme-payments",
              "--filter", "label=com.docker.compose.service=api"]).stdout.split()
    if old:
        sh(["docker", "rm", "-f", *old])
    shutil.copy2(INFRA_DIR / "partner-api" / "server.py", d / "server.py")
    shutil.copy2(INFRA_DIR / "docker-compose.host.yml", d / "docker-compose.yml")
    shutil.copytree(INFRA_DIR / "gateway", d / "gateway", dirs_exist_ok=True)
    conf = {"PAYMENT_KEY_SHA256": PAYMENT_KEY_SHA256, "RATE_LIMIT_PER_SEC": 5, "BIND": "127.0.0.1",
            "PORT": PARTNER_PORT, "ADMIN_TOKEN_SHA256": hashlib.sha256(admin_token().encode()).hexdigest()}
    (d / "partner.json").write_text(json.dumps(conf))
    if not _partner_alive():
        import subprocess as _sp
        _sp.Popen(["python3", "-u", str(d / "server.py")], cwd=str(d), start_new_session=True,
                  env=dict(PATH=os.environ.get("PATH", ""), PARTNER_CONFIG_FILE=str(d / "partner.json")),
                  stdout=open(d / "partner.log", "a"), stderr=_sp.STDOUT)
    r = sh(["docker", "compose", "up", "-d", "--build", "--remove-orphans"], cwd=d, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("gateway up that bai: " + r.stderr[-2000:])
    deadline = time.time() + 60
    while time.time() < deadline:
        if _partner_alive():
            return
        time.sleep(1)
    raise RuntimeError("partner API (host) not ready")


def partner_admin(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PARTNER_ADMIN_URL + path, data=data, method=method,
                                 headers={"X-Admin-Token": admin_token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"{}")


def partner_prepare(price_delay_ms):
    partner_admin("POST", "/_admin/reset", {})
    partner_admin("POST", "/_admin/config", {"priceDelayMs": price_delay_ms})


# ---------------------------------------------------------------- application in the sandbox
def compose(*args, timeout=600):
    return sh(["docker", "compose", *args], cwd=SANDBOX, timeout=timeout)


def up():
    r = compose("up", "-d", "--build")
    return r.returncode == 0, r.stderr[-2000:]


def down():
    if (SANDBOX / "docker-compose.yml").exists():
        compose("down", "-v", "--remove-orphans", timeout=180)
    # In case the agent renamed the project or compose file: remove every container with the shop project label.
    ids = sh(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split()
    if ids:
        sh(["docker", "rm", "-f", *ids])
    vols = sh(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split()
    if vols:
        sh(["docker", "volume", "rm", "-f", *vols])


def restart_app():
    compose("restart", "app", timeout=180)


def cid(service):
    out = sh(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}",
              "--filter", f"label=com.docker.compose.service={service}"]).stdout.split()
    return out[0] if out else None


def psql(sql, timeout=60):
    c = cid("postgres")
    if not c:
        return ""
    r = sh(["docker", "exec", "-i", c, "psql", "-U", "app", "-d", "app", "-tAc", sql], timeout=timeout)
    return r.stdout.strip()


def psql_int(sql, default=0):
    try:
        return int(float(psql(sql) or default))
    except ValueError:
        return default


def app_env(name, default=None):
    c = cid("app")
    if not c:
        return default
    r = sh(["docker", "exec", c, "printenv", name])
    return r.stdout.strip() if r.returncode == 0 else default


def app_running():
    c = cid("app")
    if not c:
        return False
    return sh(["docker", "inspect", "-f", "{{.State.Running}}", c]).stdout.strip() == "true"


def restart_count():
    c = cid("app")
    if not c:
        return -1
    out = sh(["docker", "inspect", "-f", "{{.RestartCount}}", c]).stdout.strip()
    return int(out) if out.isdigit() else -1


def mem_pct():
    c = cid("app")
    if not c:
        return None
    out = sh(["docker", "stats", "--no-stream", "--format", "{{.MemPerc}}", c]).stdout.strip().rstrip("%")
    try:
        return float(out)
    except ValueError:
        return None


def log_disk_pct():
    c = cid("app")
    if not c:
        return None
    lines = sh(["docker", "exec", c, "df", "-k", "/app/logs"]).stdout.strip().splitlines()
    if len(lines) < 2:
        return None
    parts = lines[-1].split()
    try:
        return float(parts[4].rstrip("%"))
    except (IndexError, ValueError):
        return None


def http(method, path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(APP_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        return None, {}


def wait_ready(timeout=90):
    """Ready = the app answers HTTP (any status) on /health. The SAME check for every arm."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _ = http("GET", "/health", timeout=8)
        if status is not None:
            return True
        time.sleep(1)
    return False


def sample():
    """One system state sample for the timeline (web demo screen 1/4): app DB connections, memory, log disk."""
    conns = psql("SELECT count(*) FROM pg_stat_activity WHERE datname = 'app' AND backend_type = 'client backend' "
                 "AND pid <> pg_backend_pid()", timeout=10)
    return {"db_conns": int(conns) if conns.isdigit() else None, "mem_pct": mem_pct(),
            "log_disk_pct": log_disk_pct(), "app_running": app_running()}
