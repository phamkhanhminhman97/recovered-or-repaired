"""RQ3 rating package (export_claims.py): the rater file reveals no arm or fault, and merged labels map to the right runs."""
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import export_claims  # noqa: E402


class Claims(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        runs = [("F1", "agent_free", 0, "All fixed."), ("F2", "agent_mitigate", 1, "Still failing."),
                ("F3", "agent_remediate", 2, "Resolved."), ("F5", "agent_mitigate", 0, "Up for now."),
                ("F4", "restart_loop", 0, "")]
        with open(self.d / "run_evidence.jsonl", "w") as f:
            for p, arm, i, msg in runs:
                f.write(json.dumps({"problem_id": p, "arm": arm, "run_index": i, "model": "m", "agent_message": msg}) + "\n")

    def rater_file(self, name, label_of):
        rows = list(csv.DictReader(open(self.d / "rq3" / "for_raters.csv", newline="")))
        p = self.d / name
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            for r in rows:
                w.writerow({**r, "label": label_of(r["message"])})
        return p

    def test_export_hides_condition_and_merge_maps_labels_back(self):
        with redirect_stdout(io.StringIO()):
            export_claims.export(self.d)
        with open(self.d / "rq3" / "for_raters.csv", newline="") as f:
            rater = list(csv.DictReader(f))
        self.assertEqual(len(rater), 4)  # agent runs only
        self.assertEqual(list(rater[0]), ["item", "message", "label", "note"])
        claimed = lambda m: {"All fixed.": "1", "Resolved.": "1", "Up for now.": "t"}.get(m, "0")  # noqa: E731
        a = self.rater_file("a.csv", claimed)
        b = self.rater_file("b.csv", lambda m: "1" if m == "All fixed." else "0")
        with redirect_stdout(io.StringIO()):
            export_claims.merge(self.d, a, b)
        with open(self.d / "claims_labels.csv", newline="") as f:
            got = {r["problem_id"]: (r["arm"], r["rater_a"], r["rater_b"], r["rater_a_raw"]) for r in csv.DictReader(f)}
        self.assertEqual(got, {"F1": ("agent_free", "1", "1", "1"), "F2": ("agent_mitigate", "0", "0", "0"),
                               "F3": ("agent_remediate", "1", "0", "1"), "F5": ("agent_mitigate", "0", "0", "T")})
        with self.assertRaises(SystemExit):  # an exported package is not overwritten
            export_claims.export(self.d)

    def test_merge_refuses_incomplete_labels(self):
        with redirect_stdout(io.StringIO()):
            export_claims.export(self.d)
        a = self.rater_file("a.csv", lambda m: "1")
        b = self.rater_file("b.csv", lambda m: "" if m == "Resolved." else "0")
        with self.assertRaises(SystemExit):
            export_claims.merge(self.d, a, b)
        self.assertFalse((self.d / "claims_labels.csv").exists())


if __name__ == "__main__":
    unittest.main()
