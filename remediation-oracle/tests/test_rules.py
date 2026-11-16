"""Rules that decided the data: run order, resume, action classification, three-round verdict, fault catalog."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fault_specs  # noqa: E402
import harness  # noqa: E402
import oracle  # noqa: E402

AI_ARMS = ["agent_mitigate", "agent_remediate", "agent_free"]


class Plan(unittest.TestCase):
    def test_seed_reproduces_recorded_gemini_order(self):
        # first 4 runs of results/v3-gemini-main (logs/v3_gemini.log)
        items = harness.plan(list(fault_specs.FAULTS), AI_ARMS, 5, 20261014)
        self.assertEqual(items[:4], [("F6", "agent_remediate", 3), ("F1", "agent_mitigate", 4),
                                     ("F5", "agent_remediate", 1), ("F4", "agent_remediate", 0)])
        self.assertEqual(len(items), 180)
        self.assertEqual(len(harness.plan(list(fault_specs.FAULTS), list(harness.ARMS), 10, 20261014)), 600)

    def test_resume_key_separates_models_and_ignores_model_for_baselines(self):
        rows = [{"problem_id": "F1", "arm": "agent_free", "run_index": 0, "model": "gemini-3.8-flash"},
                {"problem_id": "F1", "arm": "idle", "run_index": 0, "model": None}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pilot_results.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in rows) + "\n")
            done = harness.load_done(p, "gemini-3.8-flash")
        self.assertIn(("F1", "agent_free", 0, "gemini-3.8-flash"), done)
        self.assertIn(("F1", "idle", 0, None), done)
        self.assertNotIn(("F1", "agent_free", 0, "claude-haiku-5-5"), done)


class ActionType(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(harness.action_type("idle", ["src/a.js"], True, ["restart"]), "no_action")
        self.assertEqual(harness.action_type("restart_loop", [], False, []), "mitigation_only")
        self.assertEqual(harness.action_type("agent_free", ["src/a.js"], True, []), "remediation_attempt")
        self.assertEqual(harness.action_type("agent_free", [], True, []), "mitigation_only")
        self.assertEqual(harness.action_type("agent_free", [], False, ["restart"]), "mitigation_only")
        self.assertEqual(harness.action_type("agent_free", [], False, []), "no_action")


class Verdict(unittest.TestCase):
    def test_three_rounds(self):
        v = lambda a, b, c: oracle.verdict({"vong_1": a, "vong_2": b, "vong_3": c})  # noqa: E731
        self.assertEqual(v("fail", "not_attempted", "not_attempted"), "none")
        self.assertEqual(v("pass", "fail", "not_attempted"), "temp")
        self.assertEqual(v("pass", "pass", "fail"), "temp")
        self.assertEqual(v("pass", "pass", "pass"), "real")
        self.assertEqual(v("pass", "pass", "not_attempted"), "real")  # evaluate(with_round3=False)


class FaultCatalog(unittest.TestCase):
    def test_groups_and_partner_delay(self):
        self.assertEqual(len(fault_specs.FAULTS), 12)
        self.assertEqual(sorted(k for k, v in fault_specs.FAULTS.items() if v["group"] == "A"), ["F1", "F12", "F8"])
        self.assertEqual(sorted(k for k, v in fault_specs.FAULTS.items() if v["accumulates"]), ["F11", "F2", "F6"])
        self.assertEqual({k: fault_specs.price_delay_ms(k) for k in ("F1", "F12")}, {"F1": 10, "F12": 3000})

    def test_config_faults_differ_from_previous_release_only_in_their_variable(self):
        for fid, spec in fault_specs.FAULTS.items():
            changed = {k for k, v in fault_specs.env_for(fid).items() if fault_specs.BASE_ENV[k] != v}
            self.assertEqual(changed, set(spec.get("env", {})), fid)
            self.assertEqual(fault_specs.env_for(fid, with_bug=False), fault_specs.BASE_ENV)


if __name__ == "__main__":
    unittest.main()
