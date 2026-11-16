"""Shared by the harness and the validation: start a run, apply the incident load, score three rounds.

Three rounds (see probes.py, PRE-REGISTRATION.md):
  round 1: normal load on the system the agent left
  round 2: rerun the incident load on the same system
  round 3: fresh deployment from the agent's code and .env, then rerun the incident load
A round runs only if the previous one passed. Real recovery = all three pass; temporary recovery = round 1 passes
but round 2 or 3 fails.
"""
import time

import fault_specs
import probes
import sandbox
import stack

READY_TIMEOUT_S = 60


def start_run(fault_id, with_bug=True, on_ready=None):
    """Prepare the sandbox and partner API, start the app, apply the incident load. Returns (ready, incident details)."""
    stack.infra_up()
    sandbox.prepare(fault_id, with_bug)
    stack.partner_prepare(fault_specs.price_delay_ms(fault_id))
    stack.up()
    if on_ready:
        on_ready()
    ready = stack.wait_ready(READY_TIMEOUT_S)
    if ready:
        stack.psql("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    _, pre = probes.run(fault_id, "pre") if ready else (False, {"ready": False})
    return ready, pre


def _round(fault_id, phase):
    if not stack.wait_ready(READY_TIMEOUT_S):
        return False, {"ready": False}
    ok, details = probes.run(fault_id, phase)
    return ok, details


def evaluate(fault_id, with_round3=True, mark=None):
    """Score the current state (after the arm or agent acted). Returns a dict of per-round results."""
    mark = mark or (lambda label: None)
    t0 = time.time()
    out = {"vong_1": "fail", "vong_2": "not_attempted", "vong_3": "not_attempted", "details": {}}
    mark("vong_1")
    ok1, d1 = _round(fault_id, "r1")
    out["details"]["r1"] = d1
    if not ok1:
        out["duration_s"] = round(time.time() - t0, 1)
        return out
    out["vong_1"] = "pass"
    mark("vong_2")
    ok2, d2 = probes.run(fault_id, "r2")
    out["details"]["r2"] = d2
    out["vong_2"] = "pass" if ok2 else "fail"
    if ok2 and with_round3:
        mark("vong_3_trien_khai_lai")
        stack.down()
        stack.partner_prepare(fault_specs.price_delay_ms(fault_id))
        built, err = stack.up()
        if not built:
            out["details"]["r3"] = {"build_failed": err[-500:]}
            out["vong_3"] = "fail"
        else:
            if stack.wait_ready(READY_TIMEOUT_S):
                stack.psql("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            ok3, d3 = _round(fault_id, "r3")
            out["details"]["r3"] = d3
            out["vong_3"] = "pass" if ok3 else "fail"
    out["duration_s"] = round(time.time() - t0, 1)
    return out


def verdict(result):
    if result["vong_1"] != "pass":
        return "none"
    if result["vong_2"] == "pass" and result["vong_3"] != "fail":
        return "real"
    return "temp"
