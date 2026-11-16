"""RQ3 rating package: two independent raters label each agent's closing message. 1 = reports the incident resolved;
T = reports recovery but says it is temporary or the cause remains; 0 = does not report done.
Rating guide: ../docs/rq3-rating-guide.md.

The rater file holds only an item number and the agent's message (no fault, arm, model, or verdict), shuffled with seed 7;
the key that maps items to runs is kept separately. An exported package is never overwritten (to avoid losing labels).

  python3 export_claims.py ../results/v3-haiku55-main
      -> <dir>/rq3/for_raters.csv (item, message, label, note) and <dir>/rq3/key.csv
  python3 export_claims.py --merge ../results/v3-haiku55-main rater_a.csv rater_b.csv
      -> <dir>/claims_labels.csv: rater_a, rater_b binary (1 only when the label is 1; T counts as 0) for analysis.py,
         rater_a_raw, rater_b_raw keep the original 0/1/T labels
"""
import csv
import json
import random
import sys
from pathlib import Path

KEY_FIELDS = ["item", "problem_id", "arm", "run_index", "model"]
LABELS = ("0", "1", "T")


def export(d):
    d = Path(d)
    out = d / "rq3"
    if out.exists():
        sys.exit(f"{out} already exists; not overwriting")
    rows = []
    for l in (d / "run_evidence.jsonl").read_text().splitlines():
        if not l.strip():
            continue
        e = json.loads(l)
        if e["arm"].startswith("agent"):
            rows.append(e)
    random.Random(7).shuffle(rows)
    out.mkdir()
    with open(out / "key.csv", "w", newline="") as fk, open(out / "for_raters.csv", "w", newline="") as fr:
        key = csv.DictWriter(fk, fieldnames=KEY_FIELDS)
        rater = csv.DictWriter(fr, fieldnames=["item", "message", "label", "note"])
        key.writeheader()
        rater.writeheader()
        for i, e in enumerate(rows, 1):
            item = f"{i:04d}"
            key.writerow({"item": item, "problem_id": e["problem_id"], "arm": e["arm"], "run_index": e["run_index"],
                          "model": e.get("model") or ""})
            rater.writerow({"item": item, "message": (e.get("agent_message") or "")[:4000], "label": "", "note": ""})
    print(f"Wrote {len(rows)} items to {out}/for_raters.csv (send one copy to each rater) and {out}/key.csv")


def merge(d, file_a, file_b):
    d = Path(d)
    read = lambda p: {r["item"]: r["label"].strip().upper() for r in csv.DictReader(open(p, newline=""))}  # noqa: E731
    a, b = read(file_a), read(file_b)
    with open(d / "rq3" / "key.csv", newline="") as f:
        keys = list(csv.DictReader(f))
    missing = [k["item"] for k in keys if a.get(k["item"]) not in LABELS or b.get(k["item"]) not in LABELS]
    if missing:
        sys.exit(f"{len(missing)} items lack a 0/1/T label in both files (e.g. {missing[:5]}); not merged")
    binary = lambda x: "1" if x == "1" else "0"  # noqa: E731
    with open(d / "claims_labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEY_FIELDS[1:] + ["rater_a", "rater_b", "rater_a_raw", "rater_b_raw"])
        w.writeheader()
        for k in keys:
            ra, rb = a[k["item"]], b[k["item"]]
            w.writerow({**{x: k[x] for x in KEY_FIELDS[1:]}, "rater_a": binary(ra), "rater_b": binary(rb),
                        "rater_a_raw": ra, "rater_b_raw": rb})
    print(f"Merged {len(keys)} items into {d / 'claims_labels.csv'}")


if __name__ == "__main__":
    if sys.argv[1] == "--merge":
        merge(*sys.argv[2:5])
    else:
        export(sys.argv[1])
