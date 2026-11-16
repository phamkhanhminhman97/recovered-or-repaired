"""The 12 faults of the study (defined for v2). This file stays on the oracle side and is NEVER copied into the agent's
working directory (see sandbox.py).

Each fault is a "faulty release" applied to the clean application target-app/:
  - code fault: overwrite files from faults/<ID>/overlay/ (and/or delete the files listed in delete.txt)
  - config fault: change a variable in .env relative to the previous release (releases/2026-10-01.env)

group A = the correct action is a config rollback; group B = the code must be fixed.
accumulates = symptoms build up under load (a restart clears them for a while) -> "temporary recovery" expected.
"""

BASE_ENV = {
    "DB_TIMEOUT_MS": "5000",
    "POOL_MAX": "10",
    "PAYMENT_API_KEY": "pk_live_7f3a9c",
    "DOWNSTREAM_TIMEOUT_MS": "500",
    "LOG_LEVEL": "info",
}

FAULTS = {
    "F1": {"group": "A", "env": {"DB_TIMEOUT_MS": "1"}, "accumulates": False,
           "name": "DB timeout of 1 ms in the new configuration release"},
    "F2": {"group": "B", "accumulates": True, "name": "DB connection leak on the order error path"},
    "F3": {"group": "B", "accumulates": False, "name": "Unlocked read-then-write of balances (lost updates)"},
    "F4": {"group": "B", "accumulates": False, "name": "Missing JPY rate, JPY orders land in the DLQ"},
    "F5": {"group": "B", "accumulates": False, "name": "N+1 queries when listing items"},
    "F6": {"group": "B", "accumulates": True, "name": "Unbounded statement cache (memory leak)"},
    "F7": {"group": "B", "accumulates": False, "name": "Migration thieu index items.value"},
    "F8": {"group": "A", "env": {"PAYMENT_API_KEY": "pk_live_7f3a9d"}, "accumulates": False,
           "name": "Wrong partner API key in the new configuration release"},
    "F9": {"group": "B", "accumulates": False, "name": "Two accounts locked in inconsistent order (deadlock)"},
    "F10": {"group": "B", "accumulates": False, "name": "No retry when the partner returns 429"},
    "F11": {"group": "B", "accumulates": True, "name": "Logs not rotated, log disk fills up"},
    "F12": {"group": "A", "env": {"DOWNSTREAM_TIMEOUT_MS": "60000"}, "accumulates": False,
            "partner_price_delay_ms": 3000, "name": "60 s partner call timeout in the new configuration release"},
}


def env_for(fault_id, with_bug=True):
    env = dict(BASE_ENV)
    if with_bug:
        env.update(FAULTS[fault_id].get("env", {}))
    return env


def price_delay_ms(fault_id):
    return FAULTS[fault_id].get("partner_price_delay_ms", 10)
