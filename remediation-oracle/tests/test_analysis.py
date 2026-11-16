"""Statistics of analysis.py: fault-level bootstrap and CMH stratified by fault. Needs numpy, scipy (requirements.txt)."""
import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import analysis
except ImportError:  # macOS Python has no numpy/scipy
    analysis = None


def rows(fault, arm, real, n):
    return [{"problem_id": fault, "arm": arm, "verdict": "real" if i < real else "none"} for i in range(n)]


@unittest.skipIf(analysis is None, "can numpy va scipy")
class Statistics(unittest.TestCase):
    def test_bootstrap_by_fault_is_deterministic_and_degenerate_when_faults_agree(self):
        data = rows("F1", "x", 5, 10) + rows("F2", "x", 5, 10)
        rate = analysis.rate(lambda r: r["verdict"] == "real")
        self.assertEqual(analysis.boot_ci(data, rate, b=200), (0.5, (0.5, 0.5)))
        mixed = rows("F1", "x", 10, 10) + rows("F2", "x", 0, 10)
        p, ci = analysis.boot_ci(mixed, rate, b=200)
        self.assertEqual(p, 0.5)
        self.assertEqual(ci, analysis.boot_ci(mixed, rate, b=200)[1])
        self.assertTrue(ci[0] < 0.5 < ci[1])

    def test_cmh_detects_consistent_difference_and_none_without_one(self):
        real = lambda r: r["verdict"] == "real"  # noqa: E731
        a = rows("F1", "a", 9, 10) + rows("F2", "a", 8, 10) + rows("F3", "a", 9, 10)
        b = rows("F1", "b", 1, 10) + rows("F2", "b", 2, 10) + rows("F3", "b", 1, 10)
        or_mh, p = analysis.cmh(a, b, real)
        self.assertGreater(or_mh, 10)
        self.assertLess(p, 0.001)
        or_same, p_same = analysis.cmh(a, [dict(r, arm="b") for r in a], real)
        self.assertAlmostEqual(or_same, 1.0)
        self.assertGreater(p_same, 0.5)

    def test_rq3_labels_need_both_raters_and_give_cohens_kappa(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(analysis.rq3_labels(d)[:2], (None, 0))  # labels not merged yet
        rows_ = [("F1", "agent_free", "1", "1"), ("F2", "agent_free", "1", "0"),
                 ("F3", "agent_mitigate", "0", "0"), ("F4", "agent_mitigate", "0", "0")]
        with open(d / "claims_labels.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["problem_id", "arm", "run_index", "model", "rater_a", "rater_b"])
            w.writeheader()
            for p, arm, a, b in rows_:
                w.writerow({"problem_id": p, "arm": arm, "run_index": 0, "model": "m", "rater_a": a, "rater_b": b})
        claim, n, kappa = analysis.rq3_labels(d)
        self.assertEqual(n, 4)
        self.assertAlmostEqual(kappa, 0.5)  # po = 3/4, pe = 1/2
        run = lambda p, arm: {"problem_id": p, "arm": arm, "run_index": 0, "model": "m"}  # noqa: E731
        self.assertTrue(claim(run("F1", "agent_free")))
        self.assertFalse(claim(run("F2", "agent_free")))  # only one rater marked 1
        self.assertFalse(claim(run("F9", "agent_free")))  # run without a label


if __name__ == "__main__":
    unittest.main()
