"""Check isolation v4 (agent_llm, SELFHEAL_ISOLATION=v4: Docker proxy docker_guard.py, sandbox profile, minimal
environment) before every batch that uses it.

Runs commands an agent could type, inside sandbox-exec, with the agent's environment (agent_llm.agent_env) and a fake
workspace ~/srv/guard-check, and compares the outcome with expectations: normal operations must work (Docker, compose,
killing child processes, timeout, the Codex binary); every way to mount host directories, run privileged containers,
bypass the proxy, signal processes outside the sandbox, use credentials, or run commands outside the sandbox must be
blocked. No model calls, no quota used.

Run (Docker running, no experiment running):  ../.venv/bin/python check_isolation.py
Exits 1 if any case misses its expectation.
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "srv" / "guard-check"
os.environ["SELFHEAL_SANDBOX"] = str(ROOT)
os.environ["SELFHEAL_ISOLATION"] = "v4"
import agent_llm  # noqa: E402
import docker_guard  # noqa: E402

IMG = "alpine:latest"
H = str(Path.home())
FAKE_SOCK = Path.home() / ".colima" / "guard-check.sock"


def create(body):
    """Call the container-create API directly through the proxy (not through the docker CLI) and print the HTTP code."""
    return ("curl -s -o /dev/null -w '%{http_code}' --unix-socket " + str(agent_llm.GUARD_SOCK)
            + " -X POST -H 'Content-Type: application/json' -d '" + body + "' http://x/v1.47/containers/create")


CASES = [
    ("version", "docker version --format '{{.Server.Version}}'", "ok"),
    ("ps", "docker ps -q", "ok"),
    ("run", f"docker run --rm {IMG} echo ok", "ok"),
    ("run -i (stdin, hijack)", f"echo hi | docker run --rm -i {IMG} cat", "ok"),
    ("bind inside the workspace (-v)", f"docker run --rm -v {ROOT}/src:/x {IMG} cat /x/hello.txt", "ok"),
    ("bind inside the workspace (--mount)", f"docker run --rm --mount type=bind,src={ROOT}/src,dst=/x {IMG} ls /x", "ok"),
    ("exec, logs, cp", f"docker run -d --name gc-a {IMG} sleep 60 >/dev/null && echo hi | docker exec -i gc-a cat && "
                       f"docker logs gc-a && docker cp gc-a:/etc/hostname ./h.txt && docker cp ./src/hello.txt gc-a:/tmp/ "
                       f"&& docker exec gc-a cat /tmp/hello.txt; docker rm -f gc-a >/dev/null", "ok"),
    ("named volume", f"docker volume create gc-vol >/dev/null && docker run --rm -v gc-vol:/v {IMG} ls /v && "
                     f"docker volume rm gc-vol >/dev/null", "ok"),
    ("compose up --build, down -v", "docker compose -p guardcheck up -d --build --quiet-pull 2>&1 | tail -1 && "
                                    "docker compose -p guardcheck exec -T app cat /src/hello.txt && "
                                    "docker compose -p guardcheck down -v 2>&1 | tail -1", "ok"),
    ("-v $HOME", f"docker run --rm -v {H}:/h {IMG} ls /h", "deny"),
    ("-v /", f"docker run --rm -v /:/host {IMG} ls /host", "deny"),
    ("-v ~/Documents", f"docker run --rm -v {H}/Documents:/d {IMG} ls /d", "deny"),
    ("-v workspace/../", f"docker run --rm -v {ROOT}/../:/x {IMG} ls /x", "deny"),
    ("--mount bind $HOME", f"docker run --rm --mount type=bind,src={H},dst=/h {IMG} ls /h", "deny"),
    ("-v docker.sock", f"docker run --rm -v /var/run/docker.sock:/s {IMG} ls /s", "deny"),
    ("--privileged", f"docker run --rm --privileged {IMG} id", "deny"),
    ("--pid host", f"docker run --rm --pid host {IMG} id", "deny"),
    ("--cap-add SYS_ADMIN", f"docker run --rm --cap-add SYS_ADMIN {IMG} id", "deny"),
    ("--device", f"docker run --rm --device /dev/fuse {IMG} id", "deny"),
    ("seccomp=unconfined", f"docker run --rm --security-opt seccomp=unconfined {IMG} id", "deny"),
    ("volume bind $HOME (volume create)", f"docker volume create --driver local --opt type=none --opt o=bind "
                                          f"--opt device={H} gc-home", "deny"),
    ("volume bind $HOME (--mount volume-opt)", f"docker run --rm --mount type=volume,dst=/h,volume-driver=local,"
                                               f"volume-opt=type=none,volume-opt=o=bind,volume-opt=device={H} {IMG} ls /h",
     "deny"),
    ("exec --privileged", f"docker run -d --name gc-b {IMG} sleep 60 >/dev/null; docker exec --privileged gc-b id; "
                          f"r=$?; docker rm -f gc-b >/dev/null; exit $r", "deny"),
    ("--volumes-from", f"docker run -d --name gc-c {IMG} sleep 60 >/dev/null; docker run --rm --volumes-from gc-c {IMG} "
                       f"ls; r=$?; docker rm -f gc-c >/dev/null; exit $r", "deny"),
    ("swarm init", "docker swarm init", "deny"),
    ("raw API: lowercase keys", create('{"Image":"%s","hostconfig":{"binds":["%s:/h"]}}' % (IMG, H)), "deny"),
    ("raw API: repeated keys", create('{"Image":"%s","HostConfig":{"Binds":[]},"hostConfig":{"Binds":["%s:/h"]}}'
                                     % (IMG, H)), "deny"),
    ("DOCKER_HOST to the real socket", f"DOCKER_HOST=unix://{H}/.docker/run/docker.sock docker ps", "deny"),
    ("context desktop-linux", "docker --context desktop-linux ps", "deny"),
    ("Docker Desktop raw socket", f"curl -s -m 3 --unix-socket {H}/Library/Containers/com.docker.docker/Data/"
                                      f"docker.raw.sock http://x/_ping", "deny"),
    ("socket in the Colima directory", f"curl -s -m 3 --unix-socket {FAKE_SOCK} http://x/", "deny"),
    ("symlink in the workspace", f"ln -s {H}/Documents link", "deny"),
    ("kill a child process", "sleep 30 & p=$!; kill $p; wait $p; test $? = 143", "ok"),
    ("pkill a child process", "sleep 31 & sleep 0.2; pkill -f 'sleep 31'; wait; true", "ok"),
    ("timeout", "timeout 1 sleep 5; test $? = 124", "ok"),
    ("binary Codex", f"{agent_llm.CODEX_BIN} --version", "ok"),
    ("minimal environment", "! env | grep -E '^(SSH_AUTH_SOCK|TMUX|CODEX_APP|CODEX_THREAD|BROWSER_USE|SELFHEAL_)'", "ok"),
    ("kill a process outside the sandbox", "kill -TERM @PID@", "deny"),
    ("harness tmux", "tmux -L guard-check ls", "deny"),
    ("ssh-agent", "SSH_AUTH_SOCK=@SSH@ ssh-add -l", "deny"),
    ("read ~/.ssh", f"ls {H}/.ssh", "deny"),
    ("keychain: security", "/usr/bin/security list-keychains", "deny"),
    ("keychain: git credential", "git credential-osxkeychain", "deny"),
    ("open", "/usr/bin/open", "deny"),
    ("osascript", "osascript -e 'return 1'", "deny"),
    ("clipboard", "pbpaste > /dev/null", "deny"),
    ("screen capture", "screencapture -h", "deny"),
    ("write Docker Desktop settings", f"touch '{H}/Library/Group Containers/group.com.docker/guard-check-probe'", "deny"),
    ("Docker TCP port", "curl -s -m 2 http://localhost:2375/_ping", "deny"),
]
BLOCKED = (docker_guard.DENY_MSG.lower(), "operation not permitted", "permission denied", "no such process")
PROBE = Path.home() / "Library" / "Group Containers" / "group.com.docker" / "guard-check-probe"


def setup():
    shutil.rmtree(ROOT, ignore_errors=True)
    (ROOT / "src").mkdir(parents=True)
    (ROOT / "src" / "hello.txt").write_text("hello\n")
    (ROOT / "Dockerfile").write_text(f"FROM {IMG}\nCMD [\"sleep\", \"300\"]\n")
    (ROOT / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n    volumes:\n      - ./src:/src\n"
                                             "      - data:/data\nvolumes:\n  data:\n")


def blocked(cmd, rc, out):
    if "curl" in cmd and "http_code" in cmd:
        return out.strip() == "403"
    return rc != 0 and (any(b in out.lower() for b in BLOCKED) or ("curl" in cmd and rc == 7))


def main():
    setup()
    fake = socket.socket(socket.AF_UNIX)
    FAKE_SOCK.unlink(missing_ok=True)
    fake.bind(str(FAKE_SOCK))
    fake.listen(1)
    outside = subprocess.Popen(["sleep", "600"])
    subprocess.run(["tmux", "-L", "guard-check", "new-session", "-d", "sleep 600"], check=True)
    guard = agent_llm.start_guard()
    env = agent_llm.agent_env()
    failures = 0
    cases = [(n, c.replace("@PID@", str(outside.pid)).replace("@SSH@", os.environ.get("SSH_AUTH_SOCK", "/nonexistent")), e)
             for n, c, e in CASES]
    try:
        for name, cmd, expect in cases:
            r = subprocess.run(["sandbox-exec", "-p", agent_llm.sandbox_profile(), "/bin/zsh", "-c", cmd], cwd=ROOT,
                               env=env, capture_output=True, text=True, timeout=300)
            out = (r.stdout + r.stderr).strip()
            got = "deny" if blocked(cmd, r.returncode, out) else ("ok" if r.returncode == 0 else "loi")
            ok = got == expect
            if name == "kill a process outside the sandbox" and outside.poll() is not None:
                ok, got = False, "ok"
            failures += not ok
            print(f"{'DAT ' if ok else 'SAI '} {expect:4} {name:40} -> {got} {out.splitlines()[-1][:90] if out else ''}")
    finally:
        denied = agent_llm.stop_guard(guard)
        outside.kill()
        subprocess.run(["tmux", "-L", "guard-check", "kill-server"], capture_output=True)
        PROBE.unlink(missing_ok=True)
        fake.close()
        FAKE_SOCK.unlink(missing_ok=True)
        subprocess.run(["docker", "compose", "-p", "guardcheck", "down", "-v"], cwd=ROOT, capture_output=True)
        subprocess.run(["docker", "rm", "-f", "gc-a", "gc-b", "gc-c"], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "gc-vol", "gc-home"], capture_output=True)
        shutil.rmtree(ROOT, ignore_errors=True)
    print(f"\nThe proxy logged {len(denied)} refusals. {len(CASES) - failures}/{len(CASES)} cases met their expectation.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
