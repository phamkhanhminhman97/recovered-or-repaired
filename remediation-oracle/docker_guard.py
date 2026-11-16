"""Docker API proxy for the agent: Docker works normally, but host directories outside the agent's workspace cannot
be mounted, and privileged containers or execs cannot be created.

Reason (E1, 2026-11-12): a Gemini agent ran 'docker run -v /Users/user:/host' (the Docker daemon runs outside the sandbox)
to read the thesis repository and the oracle. When enabled (agent_llm, SELFHEAL_ISOLATION=v4), the agent uses
DOCKER_HOST=unix://<proxy socket>;
sandbox-exec blocks every Docker Desktop socket and forbids creating symlinks in the workspace, so a checked path cannot
be swapped afterwards.

Each connection carries a single HTTP request: the proxy forces 'Connection: close' (keeping 'Upgrade' for exec/attach),
so a second request on the same connection cannot slip through. Checks:
  - POST containers/create: bind mounts (Binds, Mounts) outside the workspace, volumes with a device, Privileged,
    Pid/Ipc/UsernsMode=host, dangerous CapAdd, Devices, DeviceCgroupRules, SecurityOpt unconfined, VolumesFrom;
  - POST containers/{id}/start|restart: binds inside the workspace must still point into it (realpath);
  - POST containers/{id}/exec: Privileged; POST volumes/create: devices outside the workspace;
  - swarm, services, plugins, secrets, configs, nodes, tasks: blocked.
JSON keys are matched case-insensitively (as Go encoding/json does); keys repeated in that sense are refused.

Run: python3 docker_guard.py <proxy socket> <workspace> [log file]   (without a log file it writes to stdout, one
JSON line per refusal; agent_llm reads that stdout, which the agent cannot modify)
"""
import asyncio
import json
import os
import re
import sys
import time

UPSTREAM = os.environ.get("SELFHEAL_DOCKER_UPSTREAM", os.path.expanduser("~/.docker/run/docker.sock"))
DENY_MSG = "is not allowed in this environment"  # agent_llm.access_kind treats this message as "blocked"
CAPS = {"ALL", "SYS_ADMIN", "SYS_PTRACE", "SYS_MODULE", "SYS_RAWIO", "DAC_READ_SEARCH", "SYS_BOOT"}
API = r"(?:/v[0-9.]+)?"
ROUTES = [("POST", re.compile(API + r"/containers/create"), "create"),
          ("POST", re.compile(API + r"/containers/([A-Za-z0-9_.-]+)/(?:start|restart)"), "start"),
          ("POST", re.compile(API + r"/containers/([A-Za-z0-9_.-]+)/exec"), "exec"),
          ("POST", re.compile(API + r"/volumes/create"), "volume"),
          (None, re.compile(API + r"/(?:swarm|services|plugins|secrets|configs|nodes|tasks)(?:/.*)?"), "deny")]
MAX_BODY = 1 << 20


class Denied(Exception):
    pass


def ci(d, key):
    """Value for a key matched case-insensitively; a key repeated with different case is refused."""
    if not isinstance(d, dict):
        return None
    hits = [v for k, v in d.items() if k.lower() == key.lower()]
    if len(hits) > 1:
        raise Denied(f"duplicate key {key} {DENY_MSG}")
    return hits[0] if hits else None


def inside(path, root):
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def check_source(src, root):
    if src.startswith("/") and not inside(src, root):
        raise Denied(f"mounting host path {src} {DENY_MSG}")
    if not src.startswith("/") and ("/" in src or src in ("", ".", "..")):
        raise Denied(f"mount source {src!r} {DENY_MSG}")


def check_volume_opts(opts, root):
    for k, v in (opts or {}).items():
        if k.lower() == "device" and not (isinstance(v, str) and v.startswith("/") and inside(v, root)):
            raise Denied(f"volume device {v} {DENY_MSG}")


def check_create(body, root):
    hc = ci(body, "HostConfig") or {}
    for b in ci(hc, "Binds") or []:
        check_source(str(b).split(":", 1)[0], root)
    for m in ci(hc, "Mounts") or []:
        kind = str(ci(m, "Type") or "volume").lower()
        if kind == "bind":
            check_source(str(ci(m, "Source") or ""), root)
        elif kind == "volume":
            check_volume_opts(ci(ci(ci(m, "VolumeOptions") or {}, "DriverConfig") or {}, "Options"), root)
        elif kind not in ("tmpfs", "image"):
            raise Denied(f"mount type {kind} {DENY_MSG}")
    if ci(hc, "Privileged"):
        raise Denied(f"privileged containers {DENY_MSG}")
    for k in ("PidMode", "IpcMode", "UsernsMode"):
        if str(ci(hc, k) or "").lower() == "host":
            raise Denied(f"{k}=host {DENY_MSG}")
    caps = {str(c).upper().removeprefix("CAP_") for c in ci(hc, "CapAdd") or []}
    if caps & CAPS:
        raise Denied(f"capability {', '.join(sorted(caps & CAPS))} {DENY_MSG}")
    for k in ("Devices", "DeviceCgroupRules", "VolumesFrom"):
        if ci(hc, k):
            raise Denied(f"{k} {DENY_MSG}")
    if any("unconfined" in str(s).lower() or "disable" in str(s).lower() for s in ci(hc, "SecurityOpt") or []):
        raise Denied(f"security option {DENY_MSG}")


def check_body(kind, body, root):
    if kind == "create":
        check_create(body, root)
    elif kind == "exec" and ci(body, "Privileged"):
        raise Denied(f"privileged exec {DENY_MSG}")
    elif kind == "volume":
        check_volume_opts(ci(body, "DriverOpts"), root)


def check_started(info, root):
    """At start, a bind inside the workspace (by path) must still resolve into it (guards against symlink swaps)."""
    for m in (info or {}).get("Mounts") or []:
        src = m.get("Source") or ""
        if m.get("Type") == "bind" and os.path.abspath(src).startswith(root + os.sep) and not inside(src, root):
            raise Denied(f"mounting host path {os.path.realpath(src)} {DENY_MSG}")


def route(method, path):
    if not path.startswith("/") or "%" in path or "//" in path or "/./" in path or "/../" in path or path.endswith("/.."):
        return "bad", None
    for m, rx, kind in ROUTES:
        hit = rx.fullmatch(path)
        if hit and (m is None or m == method):
            return kind, (hit.group(1) if hit.groups() else None)
    return None, None


async def read_body(reader, headers):
    if "chunked" in headers.get("transfer-encoding", "").lower():
        out = b""
        while True:
            size = int((await reader.readline()).split(b";")[0].strip() or b"0", 16)
            if size == 0:
                await reader.readline()
                return out
            out += await reader.readexactly(size)
            await reader.readexactly(2)
            if len(out) > MAX_BODY:
                raise Denied(f"request body too large {DENY_MSG}")
    n = int(headers.get("content-length", "0") or 0)
    if n > MAX_BODY:
        raise Denied(f"request body too large {DENY_MSG}")
    return await reader.readexactly(n) if n else b""


async def inspect(cid):
    r, w = await asyncio.open_unix_connection(UPSTREAM)
    w.write(f"GET /containers/{cid}/json HTTP/1.0\r\nHost: docker\r\n\r\n".encode())
    await w.drain()
    data = await r.read()
    w.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return json.loads(body) if head.split(b"\r\n")[0].split(b" ")[1:2] == [b"200"] else None


async def pipe(src, dst):
    try:
        while data := await src.read(65536):
            dst.write(data)
            await dst.drain()
        if dst.can_write_eof():
            dst.write_eof()
    except (ConnectionError, OSError):
        pass


class Guard:
    def __init__(self, root, log=None):
        self.root, self.log = os.path.realpath(root), log

    def note(self, method, path, reason):
        line = json.dumps({"t": round(time.time(), 3), "method": method, "path": path, "reason": reason})
        if self.log:
            with open(self.log, "a") as f:
                f.write(line + "\n")
        else:
            print(line, flush=True)

    async def handle(self, cr, cw):
        try:
            head = (await cr.readuntil(b"\r\n\r\n")).decode("latin-1")
            first, *lines = head[:-4].split("\r\n")
            method, target, version = first.split(" ", 2)
            pairs = [tuple(x.strip() for x in l.split(":", 1)) for l in lines if ":" in l]
            names = [k.lower() for k, _ in pairs]
            headers = {k.lower(): v for k, v in pairs}
            path = target.split("?", 1)[0]
            if names.count("content-length") > 1 or ("content-length" in headers and "transfer-encoding" in headers):
                raise Denied(f"ambiguous request framing {DENY_MSG}")
            kind, cid = route(method, path)
            if kind in ("bad", "deny"):
                raise Denied(f"{method} {path} {DENY_MSG}")
            body = None
            if kind in ("create", "exec", "volume"):
                body = await read_body(cr, headers)
                try:
                    obj = json.loads(body or b"{}")
                except ValueError:
                    raise Denied(f"malformed request body {DENY_MSG}")
                check_body(kind, obj, self.root)
            elif kind == "start":
                check_started(await inspect(cid), self.root)
            upgrade = "upgrade" in headers.get("connection", "").lower()
            keep = [(k, v) for k, v in pairs if k.lower() not in ("connection", "keep-alive", "proxy-connection")
                    and not (body is not None and k.lower() in ("content-length", "transfer-encoding"))]
            keep.append(("Connection", "Upgrade, close" if upgrade else "close"))
            if body is not None:
                keep.append(("Content-Length", str(len(body))))
            ur, uw = await asyncio.open_unix_connection(UPSTREAM)
            uw.write((first + "\r\n" + "".join(f"{k}: {v}\r\n" for k, v in keep) + "\r\n").encode("latin-1") + (body or b""))
            await uw.drain()
            await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
            uw.close()
        except Denied as e:
            self.note(locals().get("method"), locals().get("path"), str(e))
            msg = json.dumps({"message": str(e)}).encode()
            cw.write(b"HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n"
                     b"Content-Length: %d\r\n\r\n" % len(msg) + msg)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError, ConnectionError, OSError):
            pass
        finally:
            try:
                await cw.drain()
                cw.close()
            except (ConnectionError, OSError):
                pass


async def serve(sock, root, log=None):
    if os.path.exists(sock):
        os.remove(sock)
    guard = Guard(root, log)
    server = await asyncio.start_unix_server(guard.handle, path=sock, limit=1 << 16)
    os.chmod(sock, 0o600)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
