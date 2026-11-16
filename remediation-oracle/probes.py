"""Incident load, three scoring rounds, and ticket text for the 12 faults, all measured from OUTSIDE the system.

Common procedure (fixed in advance, the same for every fault; see PRE-REGISTRATION.md):
  pre   : incident load before anyone intervenes; its result is used to write the ticket.
  r1    : (round 1) normal load on the state the agent left -> does the service work again?
  r2    : (round 2) rerun the incident load on the SAME system (no restart) -> does it break again?
  r3    : (round 3) fresh deployment from the agent's code and .env (new volumes) -> rerun r2.
For non-accumulating faults r1 = r2 = the same test. For accumulating faults (F2, F6, F11) r1 is a light load
plus a headroom condition, and r2 applies the incident load before checking.
Every function returns (ok, details). Counting app self-restarts is done in the harness.
"""
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import stack


def _uuids(n):
    return [str(uuid.uuid4()) for _ in range(n)]


def _post_all(path, bodies, workers=20):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda b: stack.http("POST", path, b)[0], bodies))


def _in(ids):
    return ",".join("'%s'" % i for i in ids)


def _wait(pred, timeout, interval=0.5):
    deadline = time.time() + timeout
    while True:
        value = pred()
        if value is True or time.time() >= deadline:
            return value is True
        time.sleep(interval)


def _paid(ids):
    return stack.psql_int("SELECT count(*) FROM orders WHERE status = 'paid' AND id IN (%s)" % _in(ids))


def orders_check(n=10, timeout=20, currencies=("USD",), account_id=1):
    ids = _uuids(n)
    bodies = [{"orderId": i, "accountId": account_id, "sku": "SKU-%d" % (k % 50 + 1),
               "currency": currencies[k % len(currencies)]} for k, i in enumerate(ids)]
    accepted = sum(1 for s in _post_all("/orders", bodies) if s == 202)
    t0 = time.time()
    _wait(lambda: _paid(ids) == n, timeout)
    paid = _paid(ids)
    # Guard against hiding the fault: an order counts as done only when the partner REALLY received the charge
    # (e.g. if the agent's code skips the payment call, the DB still says 'paid' but the partner has nothing).
    try:
        charged = len(set(ids) & set(stack.partner_admin("GET", "/_admin/stats")["charges"]))
    except Exception:  # noqa: BLE001
        charged = 0
    ok = paid == n and charged == n
    return ok, {"submitted": n, "accepted": accepted, "paid": paid, "charged": charged,
                "waited_s": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ F1, F8: basic orders
def probe_orders(phase):
    return orders_check(10, 20)


# ------------------------------------------------------------------ F2: connection leak
def _leak_trigger():
    pool_max = int(stack.app_env("POOL_MAX", "10") or 10)
    bad = pool_max + 2  # order for a nonexistent account -> error inside the transaction
    _post_all("/orders", [{"orderId": i, "accountId": 999, "sku": "SKU-1"} for i in _uuids(bad)])
    time.sleep(4)
    return {"pool_max": pool_max, "failing_orders": bad}


def probe_f2(phase):
    if phase == "r1":
        return orders_check(10, 20)
    trig = _leak_trigger()
    ok, d = orders_check(10, 20)
    d.update(trig)
    return ok, d


# ------------------------------------------------------------------ F3: concurrent balance updates
def probe_f3(phase, n=50):
    acct = 3
    before = stack.psql_int("SELECT balance FROM accounts WHERE id = %d" % acct)
    ids = _uuids(n)
    _post_all("/deposits", [{"depositId": i, "accountId": acct, "amount": 1} for i in ids])
    _wait(lambda: stack.psql_int("SELECT count(*) FROM deposits WHERE id IN (%s)" % _in(ids)) == n, 20)
    done = stack.psql_int("SELECT count(*) FROM deposits WHERE id IN (%s)" % _in(ids))
    after = stack.psql_int("SELECT balance FROM accounts WHERE id = %d" % acct)
    return (done == n and after - before == n), {"deposits": n, "recorded": done, "balance_delta": after - before}


# ------------------------------------------------------------------ F4: JPY orders
def probe_f4(phase):
    return orders_check(20, 20, currencies=("USD", "JPY"))


# ------------------------------------------------------------------ F5: number of queries
def _pg_stat_reset():
    stack.psql("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    stack.psql("SELECT pg_stat_statements_reset()")


def probe_f5(phase, n_ids=200, max_calls=5):
    _pg_stat_reset()
    ids = ",".join(str(i) for i in range(1, n_ids + 1))
    t0 = time.time()
    status, body = stack.http("GET", "/catalog/items?ids=" + ids, timeout=30)
    ms = round((time.time() - t0) * 1000)
    calls = stack.psql_int("SELECT coalesce(sum(calls),0) FROM pg_stat_statements WHERE query ILIKE '%from items where id%'")
    items = len(body.get("items", [])) if isinstance(body, dict) else 0
    ok = status == 200 and items == n_ids and calls <= max_calls
    return ok, {"status": status, "items": items, "db_calls": calls, "latency_ms": ms}


# ------------------------------------------------------------------ F6: memory
def _statements(n, workers=10):
    base = int(time.time() * 1000)
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda k: stack.http("GET", "/accounts/1/statement?asOf=%d" % (base + k))[0], range(n)))
    return sum(1 for s in res if s == 200)


def probe_f6(phase, headroom_pct=60.0):
    if phase == "pre":
        sent = ok = 0
        while sent < 3000:
            ok += _statements(50)
            sent += 50
            mem = stack.mem_pct()
            if mem is None or mem >= 70 or not stack.app_running():
                break
        mem = stack.mem_pct()
        return False, {"requests": sent, "ok": ok, "mem_pct": mem}
    heavy = 0 if phase == "r1" else 1500
    ok_heavy = _statements(heavy) if heavy else 0
    ok_light = _statements(30)
    time.sleep(1)
    mem = stack.mem_pct()
    ok = ok_heavy == heavy and ok_light == 30 and mem is not None and mem < headroom_pct
    return ok, {"heavy_requests": heavy, "heavy_ok": ok_heavy, "light_ok": ok_light, "mem_pct": mem}


# ------------------------------------------------------------------ F7: query time
def probe_f7(phase, n=30, max_mean_ms=5.0):
    _pg_stat_reset()
    rng = random.Random()
    statuses = [stack.http("GET", "/catalog/search?value=%d" % rng.randint(0, 100000), timeout=15)[0] for _ in range(n)]
    mean = stack.psql("SELECT coalesce(max(mean_exec_time),0) FROM pg_stat_statements WHERE query ILIKE '%from items where value%'")
    try:
        mean_ms = round(float(mean or 0), 2)
    except ValueError:
        mean_ms = None
    ok = all(s == 200 for s in statuses) and mean_ms is not None and mean_ms < max_mean_ms
    return ok, {"requests": n, "ok": sum(1 for s in statuses if s == 200), "db_mean_ms": mean_ms}


# ------------------------------------------------------------------ F9: deadlock
def probe_f9(phase, pairs=20):
    d0 = stack.psql_int("SELECT deadlocks FROM pg_stat_database WHERE datname = 'app'")
    bodies = []
    for _ in range(pairs):
        bodies.append({"transferId": str(uuid.uuid4()), "fromId": 1, "toId": 2, "amount": 1})
        bodies.append({"transferId": str(uuid.uuid4()), "fromId": 2, "toId": 1, "amount": 1})
    _post_all("/transfers", bodies)
    ids = [b["transferId"] for b in bodies]
    _wait(lambda: stack.psql_int("SELECT count(*) FROM transfers WHERE id IN (%s)" % _in(ids)) == len(ids), 30)
    done = stack.psql_int("SELECT count(*) FROM transfers WHERE id IN (%s)" % _in(ids))
    deadlocks = stack.psql_int("SELECT deadlocks FROM pg_stat_database WHERE datname = 'app'") - d0
    return (done == len(ids) and deadlocks == 0), {"transfers": len(ids), "completed": done, "deadlocks": deadlocks}


# ------------------------------------------------------------------ F10: notifications through the partner
def probe_f10(phase, n=20):
    ids = _uuids(n)
    _post_all("/notifications", [{"notificationId": i} for i in ids])

    def delivered():
        try:
            return len(set(ids) & set(stack.partner_admin("GET", "/_admin/stats")["notifications"]))
        except Exception:  # noqa: BLE001
            return 0
    _wait(lambda: delivered() == n, 25, interval=1)
    got = delivered()
    return got == n, {"sent": n, "delivered": got}


# ------------------------------------------------------------------ F11: log disk
def _deposits(n, timeout):
    ids = _uuids(n)
    for k in range(0, n, 200):
        _post_all("/deposits", [{"depositId": i, "accountId": 1, "amount": 1} for i in ids[k:k + 200]])
    _wait(lambda: stack.psql_int("SELECT count(*) FROM deposits WHERE id IN (%s)" % _in(ids)) == n, timeout)
    return stack.psql_int("SELECT count(*) FROM deposits WHERE id IN (%s)" % _in(ids))


def probe_f11(phase, headroom_pct=50.0):
    if phase == "pre":
        sent = done = 0
        while sent < 3000:
            done += _deposits(200, 20)
            sent += 200
            disk = stack.log_disk_pct()
            if disk is None or disk >= 95 or done < sent:
                break
        return False, {"deposits": sent, "recorded": done, "log_disk_pct": stack.log_disk_pct()}
    heavy = 0 if phase == "r1" else 1500
    done_heavy = _deposits(heavy, 60) if heavy else 0
    done_light = _deposits(50, 20)
    disk = stack.log_disk_pct()
    limit = headroom_pct if phase == "r1" else 90.0
    ok = done_heavy == heavy and done_light == 50 and disk is not None and disk < limit
    return ok, {"heavy": heavy, "heavy_recorded": done_heavy, "light_recorded": done_light, "log_disk_pct": disk}


# ------------------------------------------------------------------ F12: slow partner
def probe_f12(phase):
    return orders_check(20, 10)


PROBES = {
    "F1": probe_orders, "F2": probe_f2, "F3": probe_f3, "F4": probe_f4, "F5": probe_f5, "F6": probe_f6,
    "F7": probe_f7, "F8": probe_orders, "F9": probe_f9, "F10": probe_f10, "F11": probe_f11, "F12": probe_f12,
}


def run(fault_id, phase):
    """Run one test with a common condition: the app must not restart on its own (crash) during the test."""
    if not stack.app_running():
        return False, {"app_running": False}
    rc0 = stack.restart_count()
    ok, details = PROBES[fault_id](phase)
    rc1 = stack.restart_count()
    if rc1 != rc0:
        details["app_crashed_during_probe"] = True
        if phase != "pre":
            ok = False
    return ok, details


# ------------------------------------------------------------------ tickets sent to the agent
# verbatim-vi: begin (ticket texts are kept as run: the agents received them in Vietnamese without diacritics)
def ticket(fault_id, d):
    if fault_id in ("F1", "F2", "F8", "F12"):
        return ("[ALERT] order-service: chi %s/%s don hang gui trong dot vua roi dat trang thai 'paid' sau %ss. "
                "Khach hang bao thanh toan bi treo." % (d.get("paid", 0), d.get("submitted", "?"), d.get("waited_s", "?")))
    if fault_id == "F3":
        return ("[TICKET] Doi soat tai chinh: %s lenh nap 1 don vi vao tai khoan 3 da duoc ghi nhan, nhung so du "
                "tai khoan chi tang %s." % (d.get("recorded", "?"), d.get("balance_delta", "?")))
    if fault_id == "F4":
        return ("[TICKET] CSKH: mot so khach bao don hang khong bao gio duoc thanh toan. Dot vua roi chi %s/%s don "
                "dat 'paid'; dashboard hang doi xanh." % (d.get("paid", 0), d.get("submitted", "?")))
    if fault_id == "F5":
        return ("[ALERT] GET /catalog/items (200 id) mat %s ms (SLO 50 ms); tai database tang cao."
                % d.get("latency_ms", "?"))
    if fault_id == "F6":
        return ("[ALERT] Container app dung %s%% gioi han bo nho 256 MiB va dang tiep tuc tang."
                % d.get("mem_pct", "?"))
    if fault_id == "F7":
        return ("[ALERT] GET /catalog/search cham: thoi gian truy van database trung binh %s ms (SLO 5 ms); CPU "
                "database cao." % d.get("db_mean_ms", "?"))
    if fault_id == "F9":
        return ("[ALERT] Chuyen khoan giua tai khoan 1 va 2: ty le loi job chuyen khoan tang, mot so giao dich phai "
                "thu lai hoac that bai (%s/%s hoan tat)." % (d.get("completed", "?"), d.get("transfers", "?")))
    if fault_id == "F10":
        return ("[ALERT] Thong bao khach hang: doi tac chi nhan duoc %s/%s thong bao trong dot vua roi."
                % (d.get("delivered", "?"), d.get("sent", "?")))
    if fault_id == "F11":
        return ("[ALERT] Lenh nap tien that bai: %s/%s lenh trong dot vua roi khong duoc ghi nhan; ty le loi tang."
                % (d.get("deposits", 0) - d.get("recorded", 0), d.get("deposits", "?")))
    raise ValueError(fault_id)
# verbatim-vi: end
