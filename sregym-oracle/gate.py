"""WP2: gate for the three-round oracle on SREGym, run on a problem that is already deployed with its fault injected.

Round 1 = SREGym's mitigation oracle (mitigation_oracle), unchanged. Round 2 = replay the fault's trigger (written per
problem, ROUND2).
Round 3 = recreate the pods of every application workload (Deployment, StatefulSet) from the current spec, except data stores and
infrastructure without durable volumes (recreating them would lose data or service registrations and fail the oracle for reasons
unrelated to the fix), then score again with the SREGym oracle.
Design: docs/sregym-design.md.

Run from the SREGym directory (needs SREGym's uv environment and the kind cluster):
  cd ~/srv/SREGym && uv run main.py --problem <id> --use-external-harness      # deploy, inject the fault, exit
  uv run python <repo>/sregym-oracle/gate.py <id> faulty workaround round3 reference round3   # or durable, round2
Each step prints one JSON line: step, oracle result (success), time.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

from sregym.conductor.problems.registry import ProblemRegistry

ROLLOUT_TIMEOUT_S = 600
# Data stores and infrastructure: not recreated in round 3 (no durable volume, or they hold service registrations)
NOT_RECREATED = re.compile(r"kafka|mongo|memcached|postgres|valkey|redis|consul|jaeger|opensearch|otel|prometheus|grafana")
KAFKA_WINDOW_S = 180
CRONJOB_WINDOW_S = 300
FINALIZER_WINDOW_S = 60
# Round 3: wait for stability after every rollout before scoring; rescore if it fails. G2 run 2 (2026-11-14): after all pods
# were recreated, /api/products returned 500 while the frontend reconnected, with a correct configuration; the real workaround
# (removing the pod label) failed all three times.
ROUND3_SETTLE_S = 20
ROUND3_ATTEMPTS = 3
# Restart arm: restart the faulty Deployment of each problem twice, then score. The cronjob problem has no Deployment,
# so it has no restart arm.
RESTART = {
    "service_wrong_pod_selection_hotel_reservation": ["search"],
    "kafka_poison_pill_hol_block": ["orders-validator"],
    "secret_rotation_stale_env_credentials_astronomy_shop": ["product-catalog"],
    "internal_traffic_policy_local_astronomy_shop": ["recommendation"],
    "finalizer_deadlock_controller_hotel_reservation": ["cleanup-controller"],
    "namespace_memory_limit": ["search"],
    "search_rate_retry_collapse_hotel_reservation": ["rate", "search"],
}


def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd}: {r.stderr.strip()[-500:]}")
    return r.stdout.strip()


def oracle(problem):
    r = problem.mitigation_oracle.evaluate()
    return bool(r.get("success")), r


def app_workloads(namespace):
    return [n for kind in ("deployment", "statefulset")
            for n in sh(f"kubectl get {kind} -n {namespace} -o name").splitlines() if n]


def wait_rollouts(namespace):
    """Wait for every workload in the namespace to finish its rollout (some recover_fault calls return before replicas are
    ready)."""
    for n in app_workloads(namespace):
        sh(f"kubectl rollout status {n} -n {namespace} --timeout={ROLLOUT_TIMEOUT_S}s", check=False)


def restart_twice(problem, pid):
    for _ in range(2):
        for d in RESTART[pid]:
            sh(f"kubectl rollout restart deployment/{d} -n {problem.namespace}")
            # 180 s: in the memory-quota problem new pods are blocked, so the rollout never finishes
            sh(f"kubectl rollout status deployment/{d} -n {problem.namespace} --timeout=180s", check=False)


def recreate_all_pods(namespace):
    """Round 3: recreate the pods of every application workload from its controller's current spec; return their names."""
    names = [n for n in app_workloads(namespace) if not NOT_RECREATED.search(n.split("/", 1)[1])]
    for n in names:
        sh(f"kubectl rollout restart {n} -n {namespace}")
    for n in names:
        sh(f"kubectl rollout status {n} -n {namespace} --timeout={ROLLOUT_TIMEOUT_S}s")
    return names


def kafka_round2(problem):
    """Round 2 of kafka_poison_pill_hol_block: send 5 valid records, one poison record (the injector's string), and 5 more
    valid records; pass if all 10 new valid records reach the result topic within KAFKA_WINDOW_S (the consumer gets past
    the new poison record and drops no valid one). The pipeline is not redeployed, so the agent's ConfigMap fix stays."""
    inj = problem.injector
    tag = uuid.uuid4().hex[:6]
    ids = [f"R2-{tag}-{i}" for i in range(10)]
    valid = [json.dumps({"order_id": i, "amount": 1}) for i in ids]
    inj.broker.publish_lines(inj.TOPIC, valid[:5] + [inj.INVALID_RECORD] + valid[5:])
    deadline = time.time() + KAFKA_WINDOW_S
    done = set()
    while time.time() < deadline:
        state = inj.broker.pipeline_snapshot(inj.TOPIC, inj.OUTPUT_TOPIC, inj.CONSUMER_GROUP)
        done = {json.loads(r["value"]).get("order_id") for r in state["output"]} & set(ids)
        if len(done) == len(ids):
            return True, {"processed": len(done)}
        time.sleep(10)
    return False, {"processed": len(done), "expected": len(ids)}


def secret_round2(problem):
    """Round 2 of secret_rotation_stale_env_credentials_astronomy_shop: rotate the DB password once more with the injector's
    steps (change the Postgres password, update the Secret, kill DB sessions), plus the product-catalog restart step of the
    rotation procedure (without it even SREGym's reference fix fails, since the app reads its environment only at start).
    Pass if /api/products returns data again. Then restore the password SREGym expects, so later steps see the old state."""
    pw3 = f"otelp_r2{uuid.uuid4().hex[:6]}"
    conn3 = problem.new_conn.replace(problem.new_password, pw3)
    problem._rotate_postgres_password(problem.new_password, pw3)
    problem._apply_secret(conn3)
    problem._drop_postgres_connections(pw3)
    sh(f"kubectl rollout restart deployment/{problem.faulty_service} -n {problem.namespace}")
    rolled = "successfully rolled out" in sh(
        f"kubectl rollout status deployment/{problem.faulty_service} -n {problem.namespace} --timeout=180s", check=False)
    ok = False
    for _ in range(3):
        ok = problem.mitigation_oracle._run_product_probe()
        if ok:
            break
        time.sleep(10)
    # Restore state: kill DB sessions as the injector does. G2 run 2 (svelte): after the pod with the hard-coded string also
    # failed to start in round 2, /api/products hung until the DB sessions were killed, so round 3 and the reference fix
    # right after failed for an unrelated reason.
    problem._rotate_postgres_password(pw3, problem.new_password)
    problem._apply_secret(problem.new_conn)
    problem._drop_postgres_connections(problem.new_password)
    sh(f"kubectl rollout restart deployment/{problem.faulty_service} -n {problem.namespace}")
    sh(f"kubectl rollout status deployment/{problem.faulty_service} -n {problem.namespace} --timeout=300s", check=False)
    restored = False
    for _ in range(3):
        restored = problem.mitigation_oracle._run_product_probe()
        if restored:
            break
        time.sleep(10)
    return ok, {"rollout_reported": rolled, "restored": restored}


def cronjob_round2(problem):
    """Round 2 of the cronjob problem (matches SREGym's 'run a new Job' step): wait for two new Jobs from the minute
    schedule; pass if both complete within CRONJOB_WINDOW_S."""
    before = {j.metadata.name for j in problem._list_owned_jobs()}
    deadline = time.time() + CRONJOB_WINDOW_S
    while time.time() < deadline:
        new = sorted((j for j in problem._list_owned_jobs() if j.metadata.name not in before),
                     key=lambda j: j.metadata.creation_timestamp)[:2]
        if len(new) == 2 and all((j.status.succeeded or 0) >= 1 for j in new):
            return True, {"jobs": [j.metadata.name for j in new]}
        time.sleep(10)
    return False, {"new_jobs": len({j.metadata.name for j in problem._list_owned_jobs()} - before)}


def finalizer_round2(problem):
    """Round 2 of the finalizer problem (matches SREGym's 'new cleanup request' step): create a new ConfigMap with the
    finalizer and the label the controller watches, then delete it; pass if it disappears within FINALIZER_WINDOW_S."""
    api = problem.kubectl.core_v1_api
    name = f"round2-cleanup-{uuid.uuid4().hex[:6]}"
    api.create_namespaced_config_map(problem.namespace, {"metadata": {
        "name": name, "finalizers": [problem.finalizer], "labels": {"app.kubernetes.io/component": "reservation-cleanup"}}})
    api.delete_namespaced_config_map(name, problem.namespace)
    deadline = time.time() + FINALIZER_WINDOW_S
    while time.time() < deadline:
        if name not in sh(f"kubectl get configmap -n {problem.namespace} -o name"):
            return True, {}
        time.sleep(3)
    # Clean up so later steps do not trip over a stuck ConfigMap
    api.patch_namespaced_config_map(name, problem.namespace, {"metadata": {"finalizers": None}})
    return False, {"stuck": name}


ROUND2 = {
    "kafka_poison_pill_hol_block": kafka_round2,
    "secret_rotation_stale_env_credentials_astronomy_shop": secret_round2,
    "cronjob_sidecar_blocks_completion_hotel_reservation": cronjob_round2,
    "finalizer_deadlock_controller_hotel_reservation": finalizer_round2,
    # SREGym's oracle for this problem already replays the load; our round 2 replays it once more, same configuration
    "search_rate_retry_collapse_hotel_reservation": oracle,
}


def kafka_durable_fix(problem):
    """Hand-written durable fix (to check that round 2 can pass): the consumer logs, commits, and skips unreadable
    records instead of stopping."""
    inj = problem.injector
    api = problem.kubectl.core_v1_api
    cm = api.read_namespaced_config_map(inj.SCRIPTS_CONFIGMAP, problem.namespace)
    src = cm.data["consumer.py"]
    start = src.index("        except Exception as exc:\n")
    end = src.index("            break\n", start) + len("            break\n")
    cm.data["consumer.py"] = src[:start] + (
        "        except Exception as exc:\n"
        "            log.error(\"record validation failed at offset=%d: %s; skipped\", msg.offset(), exc)\n"
        "            consumer.commit(message=msg, asynchronous=False)\n"
        "            continue\n") + src[end:]
    api.replace_namespaced_config_map(inj.SCRIPTS_CONFIGMAP, problem.namespace, cm)
    sh(f"kubectl rollout restart deployment/{inj.CONSUMER_DEPLOYMENT} -n {problem.namespace}")
    sh(f"kubectl rollout status deployment/{inj.CONSUMER_DEPLOYMENT} -n {problem.namespace} --timeout=300s")


def itp_scale_workaround(problem):
    """Workaround for the internal traffic policy problem: remove the node pin and scale recommendation to the number of
    workers, keep policy Local, add no spread constraint. At scoring time every worker usually has an endpoint, but a
    later reschedule can leave a node without one."""
    workers = len(problem.worker_nodes())
    problem._clear_deployment_node_selector(problem.FAULTY_SERVICE)
    sh(f"kubectl scale deployment/{problem.FAULTY_SERVICE} -n {problem.namespace} --replicas={workers}")
    sh(f"kubectl rollout status deployment/{problem.FAULTY_SERVICE} -n {problem.namespace} --timeout=300s")


def env_shadow_fix(problem):
    """Reference fix for env_variable_shadowing (recover_fault needs the template captured at injection): remove the
    injected duplicate definition."""
    dep = problem.kubectl.get_deployment(problem.faulty_service, problem.namespace)
    idx, env = problem._target_container_and_env(dep)
    dups = [i for i, e in enumerate(env) if e.name == problem.ENV_NAME and e.value == problem.SHADOW_VALUE]
    problem.kubectl.apps_v1_api.patch_namespaced_deployment(problem.faulty_service, problem.namespace, [
        {"op": "remove", "path": f"/spec/template/spec/containers/{idx}/env/{i}"} for i in reversed(dups)])
    problem._wait_for_rollout()


# Hand-written workarounds (to check that the oracle reports "temporary"), not reference fixes.
WORKAROUNDS = {
    # Remove the route label from the running search pod: the frontend endpoint is clean at once, but the template
    # still carries the label, so new pods break it again.
    "service_wrong_pod_selection_hotel_reservation":
        lambda p: sh(f"kubectl label pod -n {p.namespace} -l io.kompose.service=search service-route-"),
    # SREGym's reference fix for kafka moves the offset past the poison record (recover_fault); that is exactly the
    # mitigation to test.
    "kafka_poison_pill_hol_block": lambda p: p.recover_fault(),
    # Hard-code the new connection string in the Deployment instead of reading the Secret: SREGym's oracle only compares
    # values and lets it pass; the next rotation breaks it.
    "secret_rotation_stale_env_credentials_astronomy_shop": lambda p: (
        p._set_product_catalog_literal_env(p.new_conn),
        sh(f"kubectl rollout status deployment/{p.faulty_service} -n {p.namespace} --timeout=300s")),
    "internal_traffic_policy_local_astronomy_shop": itp_scale_workaround,
}
DURABLE = {
    "kafka_poison_pill_hol_block": kafka_durable_fix,
    "env_variable_shadowing_astronomy_shop": env_shadow_fix,
}


def emit(pid, step, ok, t0, detail):
    line = json.dumps({"problem": pid, "step": step, "success": ok, "seconds": round(time.time() - t0, 1), "detail": detail},
                      default=str)
    print(line, flush=True)
    # AI runs of WP2: run_wp2.py sets this variable to get round 2 and 3 results when the bench and conductor call it
    if os.environ.get("SELFHEAL_ROUNDS_LOG"):
        with open(os.environ["SELFHEAL_ROUNDS_LOG"], "a") as f:
            f.write(line + "\n")


def run_step(problem, pid, step):
    """Run one step, print one JSON line, return the scoring result."""
    t0 = time.time()
    extra = {}
    if step == "workaround":
        WORKAROUNDS[pid](problem)
        time.sleep(10)
    elif step == "reference":
        problem.recover_fault()
        wait_rollouts(problem.namespace)
    elif step == "durable":
        DURABLE[pid](problem)
        wait_rollouts(problem.namespace)
    elif step == "restart":
        restart_twice(problem, pid)
    elif step == "round3":
        extra["recreated"] = recreate_all_pods(problem.namespace)
        for attempt in range(1, ROUND3_ATTEMPTS + 1):
            time.sleep(ROUND3_SETTLE_S)
            ok, detail = oracle(problem)
            if ok:
                break
        emit(pid, step, ok, t0, {k: v for k, v in detail.items() if k != "success"} | extra | {"attempts": attempt})
        return ok
    elif step == "round2":
        ok, detail = ROUND2[pid](problem)
        emit(pid, step, ok, t0, detail)
        return ok
    elif step != "faulty":
        raise SystemExit(f"unknown step: {step}")
    ok, detail = oracle(problem)
    emit(pid, step, ok, t0, {k: v for k, v in detail.items() if k != "success"} | extra)
    return ok


def main():
    pid, steps = sys.argv[1], sys.argv[2:]
    problem = ProblemRegistry().get_problem_instance(pid)
    if pid == "search_rate_retry_collapse_hotel_reservation":
        # This oracle needs the list of Deployments captured before injection (the conductor captured it inside the
        # injection process, which has exited); the fault adds or removes no Deployment, so capturing it now gives the same set.
        problem.mitigation_oracle.capture_baseline()
    last_ok = None
    for step in steps:
        if step != "post":
            last_ok = run_step(problem, pid, step)
            continue
        # "post" (WP2): round 2 if the problem has one, then round 3; skipped when the previous scoring step in the same
        # command failed. SREGym's bench and conductor call "post" only after round 1 passed, so last_ok is None there.
        if last_ok is False:
            emit(pid, "post", None, time.time(), {"skipped": "round1_failed"})
            continue
        for sub in (["round2"] if pid in ROUND2 else []) + ["round3"]:
            run_step(problem, pid, sub)


if __name__ == "__main__":
    main()
