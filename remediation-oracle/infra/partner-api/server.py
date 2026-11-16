"""Simulated partner API (payments, notifications, pricing), running OUTSIDE the agent's workspace.

Public API (the app calls it, and so can the agent):
  POST /v1/charges        Authorization: Bearer <key>  -> 401 on a wrong key
  POST /v1/notifications  Authorization: Bearer <key>  -> 429 + Retry-After above RATE_LIMIT per second
  GET  /v1/prices/<sku>   answers after PRICE_DELAY_MS (adjustable through /_admin/config)

Admin API (oracle only, needs the X-Admin-Token header):
  GET  /_admin/stats   POST /_admin/reset   POST /_admin/config {"priceDelayMs": int}
"""
import json
import hashlib
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Only HASHES of the key and token are stored: an agent with Docker access could read the source and environment
# of this container (it happened in the first pilot), so nothing is kept in plain text here.
# Host mode: read the configuration from a file (not from the process environment).
_CONF = {}
if os.environ.get("PARTNER_CONFIG_FILE"):
    with open(os.environ["PARTNER_CONFIG_FILE"]) as _f:
        _CONF = json.load(_f)
PAYMENT_KEY_SHA256 = _CONF.get("PAYMENT_KEY_SHA256") or os.environ.get("PAYMENT_KEY_SHA256", "")
ADMIN_TOKEN_SHA256 = _CONF.get("ADMIN_TOKEN_SHA256") or os.environ.get("ADMIN_TOKEN_SHA256", "")
RATE_LIMIT = int(_CONF.get("RATE_LIMIT_PER_SEC") or os.environ.get("RATE_LIMIT_PER_SEC", "5"))
BIND = (_CONF.get("BIND") or "0.0.0.0", int(_CONF.get("PORT") or 8080))


def _sha256(value):
    return hashlib.sha256(value.encode()).hexdigest()

lock = threading.Lock()
state = {}


def reset():
    with lock:
        state.clear()
        state.update(
            charges=set(), charge_unauthorized=0, notifications=set(), notify_rate_limited=0,
            notify_unauthorized=0, price_calls=0, price_delay_ms=10, recent_notify=[],
        )


reset()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload, headers=None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _key_ok(self):
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and _sha256(auth[7:]) == PAYMENT_KEY_SHA256

    def _admin_ok(self):
        token = self.headers.get("X-Admin-Token") or ""
        return bool(ADMIN_TOKEN_SHA256) and _sha256(token) == ADMIN_TOKEN_SHA256

    def do_GET(self):
        if self.path.startswith("/v1/prices/"):
            with lock:
                state["price_calls"] += 1
                delay = state["price_delay_ms"]
            time.sleep(delay / 1000)
            sku = self.path.rsplit("/", 1)[-1]
            return self._send(200, {"sku": sku, "priceCents": 500 + (sum(map(ord, sku)) % 50) * 25})
        if self.path == "/_admin/stats":
            if not self._admin_ok():
                return self._send(403, {"error": "forbidden"})
            with lock:
                return self._send(200, {
                    "charges": sorted(state["charges"]),
                    "chargeUnauthorized": state["charge_unauthorized"],
                    "notifications": sorted(state["notifications"]),
                    "notifyRateLimited": state["notify_rate_limited"],
                    "notifyUnauthorized": state["notify_unauthorized"],
                    "priceCalls": state["price_calls"],
                    "priceDelayMs": state["price_delay_ms"],
                })
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/charges":
            body = self._body()
            if not self._key_ok():
                with lock:
                    state["charge_unauthorized"] += 1
                return self._send(401, {"error": "invalid api key"})
            with lock:
                state["charges"].add(str(body.get("orderId")))
            return self._send(200, {"status": "captured", "orderId": body.get("orderId")})
        if self.path == "/v1/notifications":
            body = self._body()
            if not self._key_ok():
                with lock:
                    state["notify_unauthorized"] += 1
                return self._send(401, {"error": "invalid api key"})
            now = time.time()
            with lock:
                recent = [t for t in state["recent_notify"] if now - t < 1.0]
                if len(recent) >= RATE_LIMIT:
                    state["recent_notify"] = recent
                    state["notify_rate_limited"] += 1
                    return self._send(429, {"error": "rate limited"}, {"Retry-After": "1"})
                recent.append(now)
                state["recent_notify"] = recent
                state["notifications"].add(str(body.get("notificationId")))
            return self._send(200, {"status": "sent"})
        if self.path in ("/_admin/reset", "/_admin/config"):
            if not self._admin_ok():
                return self._send(403, {"error": "forbidden"})
            if self.path == "/_admin/reset":
                reset()
                return self._send(200, {"status": "reset"})
            body = self._body()
            with lock:
                if "priceDelayMs" in body:
                    state["price_delay_ms"] = int(body["priceDelayMs"])
            return self._send(200, {"status": "ok"})
        self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(BIND, Handler).serve_forever()
