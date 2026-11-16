"""Repair-mechanism rules (mechanism.py): the paper's durable-workaround finding rests entirely on these functions."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fault_specs  # noqa: E402
import mechanism as C  # noqa: E402


def env_diff(pairs, other_file=True):
    lines = []
    if other_file:  # "+" lines of another file must not count as .env variables
        lines += ["--- a/src/config.js", "+++ b/src/config.js", "+const POOL_MAX = 99;"]
    lines += ["--- a/.env", "+++ b/.env"] + ["-%s=old" % k for k, _ in pairs] + ["+%s=%s" % kv for kv in pairs]
    return "\n".join(lines)


class Mechanism(unittest.TestCase):
    def test_env_changes_reads_only_dotenv_additions(self):
        self.assertEqual(C.env_changes(env_diff([("POOL_MAX", "1"), ("LOG_LEVEL", "warn")])),
                         {"POOL_MAX": "1", "LOG_LEVEL": "warn"})
        self.assertEqual(C.env_changes(None), {})

    def test_group_b_split_by_where_the_change_is(self):
        run = {"problem_id": "F9", "fault_group": "B"}
        fault_file = C.FAULT_FILES["F9"][0]
        self.assertEqual(C.mechanism(run, {"code_files": [fault_file]}), "B: code fix, faulty file")
        self.assertEqual(C.mechanism(run, {"code_files": ["src/unrelated.js"]}), "B: code fix, other layer")
        self.assertEqual(C.mechanism(run, {"code_files": [], "config_changed": True,
                                           "diff": env_diff([("POOL_MAX", "1")], other_file=False)}),
                         "B: configuration workaround")
        self.assertEqual(C.mechanism(run, {"code_files": [], "config_changed": False}), "B: operational actions only")

    def test_group_a_rollback_means_previous_release_value(self):
        run = {"problem_id": "F1", "fault_group": "A"}
        base = fault_specs.BASE_ENV["DB_TIMEOUT_MS"]
        self.assertEqual(C.mechanism(run, {"diff": env_diff([("DB_TIMEOUT_MS", base)])}), "A: rollback to the previous value")
        self.assertEqual(C.mechanism(run, {"diff": env_diff([("DB_TIMEOUT_MS", base + "0")])}),
                         "A: faulty setting changed to another value")
        self.assertEqual(C.mechanism(run, {"code_files": ["src/db.js"]}), "A: code change")

    def test_repair_separates_defect_removal_from_workarounds_in_code(self):
        def diff(minus, plus):
            return "\n".join(["--- a/src/x.js", "+++ b/src/x.js"] + ["-" + l for l in minus] + ["+" + l for l in plus])
        f9 = {"problem_id": "F9"}
        ordered = diff(["lock(fromId); sleep(20); lock(toId);"],
                       ["const a = Number(fromId) < Number(toId) ? fromId : toId;", "lock(a); lock(b);"])
        self.assertEqual(C.repair(f9, {"diff": ordered}), "fixes the cause")
        self.assertTrue(C.repair(f9, {"diff": diff(["sleep(20);"], ["// no wait"])}).startswith("workaround"))
        f2 = {"problem_id": "F2"}
        no_tx = diff(['await client.query("BEGIN");'], ['await pool.query("INSERT ...");'])
        self.assertEqual(C.repair(f2, {"diff": no_tx}), "removes the faulty part: drops the transaction")
        f4 = {"problem_id": "F4"}
        no_fx = diff(["const cents = currency.toUsdCents(price, cur);"], ["const cents = price;"])
        self.assertTrue(C.repair(f4, {"diff": no_fx}).startswith("workaround in code"))
        run = {"problem_id": "F4", "fault_group": "B"}
        self.assertFalse(C.removes_defect(run, {"code_files": ["src/services/orders.js"], "diff": no_fx}))

    def test_config_repair_flags_capacity_workaround_on_config_fault(self):
        run = {"problem_id": "F12", "fault_group": "A"}
        base = fault_specs.BASE_ENV["DOWNSTREAM_TIMEOUT_MS"]
        restore = env_diff([("DOWNSTREAM_TIMEOUT_MS", base)], other_file=False)
        self.assertEqual(C.config_repair(run, {"diff": restore}), "restores the previous value")
        cap = "--- a/src/config.js\n+++ b/src/config.js\n+  timeoutMs: Math.min(config.downstreamTimeoutMs, 500),"
        self.assertEqual(C.config_repair(run, {"diff": cap}), "neutralized in code")
        more_workers = "--- a/src/worker.js\n+++ b/src/worker.js\n-  concurrency: 5\n+  concurrency: 20"
        self.assertTrue(C.config_repair(run, {"diff": more_workers}).startswith("workaround"))
        clamp = "--- a/src/config.js\n+++ b/src/config.js\n+  if (!Number.isFinite(n) || n < min) {"
        self.assertEqual(C.config_repair({"problem_id": "F1", "fault_group": "A"}, {"diff": clamp}), "neutralized in code")


    def test_defect_gone_accepts_batched_lookup_and_row_lock(self):
        def diff(minus, plus):
            return "\n".join(["--- a/x.js", "+++ b/x.js"] + ["-" + l for l in minus] + ["+" + l for l in plus])
        f5 = {"problem_id": "F5"}
        batched = diff(['const { rows } = await pool.query("SELECT id FROM items WHERE id = $1", [id]);'],
                       ['const { rows } = await pool.query("SELECT id FROM items WHERE id = ANY($1::int[])", [ids]);'])
        self.assertTrue(C.defect_gone(f5, {"diff": batched}))
        self.assertFalse(C.defect_gone(f5, {"diff": diff(["// old"], ["// new"])}))
        f3 = {"problem_id": "F3"}
        lock = diff(['await pool.query("SELECT balance FROM accounts WHERE id = $1")'],
                    ['await client.query("SELECT balance FROM accounts WHERE id = $1 FOR UPDATE")'])
        self.assertTrue(C.defect_gone(f3, {"diff": lock}))
        self.assertIsNone(C.defect_gone({"problem_id": "F9"}, {"diff": lock}))

    def test_summary_labels_real_agent_fixes_only(self):
        e = {"code_files": [], "config_changed": True, "diff": env_diff([("POOL_MAX", "1")], other_file=False)}
        run = {"problem_id": "F9", "fault_group": "B", "arm": "agent_mitigate", "verdict": "real"}
        self.assertTrue(C.summary(run, e).startswith("durable configuration workaround"))
        self.assertIsNone(C.summary({**run, "verdict": "temp"}, e))
        self.assertIsNone(C.summary({**run, "arm": "restart_loop"}, e))

if __name__ == "__main__":
    unittest.main()
