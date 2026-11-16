"""Repair mechanism of a run, read from the evidence (files the agent changed, diff); standard library only.

Used by cross_model.py (exploratory analysis, section 5.4 of results/cross_model.md) and paper/make_tables.py.
The rules come from the fault catalog (faults/, fault_specs.py) and the reference fixes (target-app/), not from the results;
runs that match no signature were read by hand and are reported in cross_model.md. This analysis was designed after seeing
the data (PRE-REGISTRATION log, 2026-11-12).
"""
import re
from pathlib import Path

import fault_specs

FAULTS = ["F%d" % i for i in range(1, 13)]

FAULT_FILES = {f: [str(p.relative_to(Path(__file__).resolve().parent / "faults" / f / "overlay"))
                   for p in (Path(__file__).resolve().parent / "faults" / f / "overlay").rglob("*") if p.is_file()]
               for f in FAULTS}
FAULT_FILES["F7"] = ["db/migrations/"]  # F7 deletes a migration; the correct fix adds back the migration that creates the index


def env_changes(diff):
    """New values of the .env variables in the agent's diff (only the +++ b/.env part)."""
    out, cur = {}, None
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            cur = line[4:].strip()
            continue
        if line.startswith("--- "):
            continue
        if cur == "b/.env" and line.startswith("+") and "=" in line:
            k, v = line[1:].split("=", 1)
            out[k.strip()] = v.strip()
    return out


def mechanism(r, e):
    """Mechanism of a run from the files the agent changed; the rules come from the fault catalog, not from results."""
    code = e.get("code_files") or []
    f = r["problem_id"]
    if r["fault_group"] == "B":
        if any(c.startswith(ff) for c in code for ff in FAULT_FILES[f]):
            return "B: code fix, faulty file"
        if code:
            return "B: code fix, other layer"
        if e.get("config_changed"):
            return "B: configuration workaround"
        return "B: operational actions only"
    var = next(iter(fault_specs.FAULTS[f]["env"]))
    new = env_changes(e.get("diff")).get(var)
    if code:
        return "A: code change"
    if new == fault_specs.BASE_ENV[var]:
        return "A: rollback to the previous value"
    if new is not None:
        return "A: faulty setting changed to another value"
    return "A: other"


CODE_FIX = {"B: code fix, faulty file", "B: code fix, other layer"}

# Repair signatures in the lines the agent ADDED, per group-B fault, derived from the faulty release (faults/Fx/overlay)
# and the reference fix (target-app), not from results; checked by hand on 2026-11-12 (cross_model.md section 5.4).
REPAIR_SIG = {
    "F2": r"finally|release\(",  # release the connection on every path
    "F3": r"balance\s*=\s*balance\s*\+|FOR UPDATE|pg_advisory|SERIALIZABLE",  # atomic balance update
    "F4": r"JPY",  # add the JPY rate back
    "F5": r"ANY\(|\bIN\s*\(|JOIN",  # a single query
    "F6": r"MAX_|\.size\b|\.delete\(|LRU|\$\{month\}",  # bounded cache, or cache keyed by month
    "F7": r"CREATE\s+(UNIQUE\s+)?INDEX",  # migration that recreates the index
    "F9": r"sort\(|Math\.min|\?\s*\[|ORDER BY|ANY\(|(?:from|to)Id\)?\s*[<>]=?\s*(?:Number\()?(?:from|to)Id",  # lock in a fixed order
    "F10": r"attempts|backoff|retry|Retry|429",  # retry when the partner rate-limits
    "F11": r"rename|truncate|unlink|MAX_\w*\s*=|size\s*>",  # rotate or cap the log file
}
# No signature match, but the faulty part was removed outright:
# (pattern in the deleted lines, description, whether the feature still works)
REMOVAL = {"F2": (r"BEGIN", "drops the transaction", True), "F6": (r"cache", "drops the cache", True),
           "F4": (r"toUsdCents", "drops currency conversion, wrong amount", False)}


def diff_lines(diff, sign):
    """Lines the agent added (sign '+') or deleted ('-') in the diff, without the file headers."""
    return "\n".join(l[1:] for l in (diff or "").splitlines() if l.startswith(sign) and not l.startswith(sign * 3 + " "))


def repair(r, e):
    """Group-B run with a code change: fixes the cause, removes the faulty part, or works around it in code."""
    f, plus, minus = r["problem_id"], diff_lines(e.get("diff"), "+"), diff_lines(e.get("diff"), "-")
    if re.search(REPAIR_SIG[f], plus):
        return "fixes the cause"
    pat, what, ok = REMOVAL.get(f, (None, "", False))
    if pat and re.search(pat, minus) and not re.search(pat, plus):
        return ("removes the faulty part: " if ok else "workaround in code: ") + what
    return "workaround in code: no repair signature"


def removes_defect(r, e):
    """Group-B run that removed the fault from the code: it changed code and is not a workaround."""
    return mechanism(r, e) in CODE_FIX and not repair(r, e).startswith("workaround")


# Second check, independent of REPAIR_SIG, for faults whose release has a clear faulty structure (added 2026-11-12, after
# reading the exceptions by hand): F3 drops the read-then-write pattern (newBalance) or locks the row before reading; F5
# drops the per-id query; F2 releases the connection in finally; F7 adds an index on items(value). The diffs for the other
# faults were read in full.
DEFECT_GONE = {
    "F2": lambda plus, minus: "finally" in plus and "release(" in plus + minus,
    "F3": lambda plus, minus: ("newBalance" in minus and "newBalance" not in plus) or "FOR UPDATE" in plus,
    "F5": lambda plus, minus: "WHERE id = $1" in minus and "WHERE id = $1" not in plus,
    "F7": lambda plus, minus: re.search(r"CREATE\s+(UNIQUE\s+)?INDEX[^;]*ON\s+items\s*\(\s*value", plus, re.I) is not None,
}


def defect_gone(r, e):
    """True/False from the second check; None if the fault has no entry in DEFECT_GONE."""
    check = DEFECT_GONE.get(r["problem_id"])
    return None if check is None else bool(check(diff_lines(e.get("diff"), "+"), diff_lines(e.get("diff"), "-")))


# Group A: code that clamps the faulty variable (neutralizes the bad setting in code). Checked by hand on 2026-11-12.
NEUTRALIZE_SIG = {"F1": r"MIN_\w*TIMEOUT|Math\.max\(|<\s*min\b", "F8": r"(?!)", "F12": r"Math\.min\(|MAX_\w*TIMEOUT"}


def config_repair(r, e):
    """Group-A run: the faulty setting was restored, changed to another value, neutralized in code, or left as is."""
    f = r["problem_id"]
    var = next(iter(fault_specs.FAULTS[f]["env"]))
    new = env_changes(e.get("diff")).get(var)
    if new == fault_specs.BASE_ENV[var]:
        return "restores the previous value"
    if new is not None:
        return "changes to another value"
    if re.search(NEUTRALIZE_SIG[f], diff_lines(e.get("diff"), "+")):
        return "neutralized in code"
    return "workaround: faulty setting kept"


def summary(r, e):
    """A one-line label for an agent run that really recovered (verdict real); None otherwise."""
    if r.get("verdict") != "real" or not str(r.get("arm", "")).startswith("agent"):
        return None
    if r["fault_group"] == "A":
        kind = config_repair(r, e)
        return {"restores the previous value": "restored the previous release's configuration",
                "changes to another value": "changed the faulty setting to another value",
                "neutralized in code": "blocked the faulty setting in code"}.get(kind, "durable workaround: faulty setting kept")
    m = mechanism(r, e)
    if m == "B: configuration workaround":
        return "durable configuration workaround: the fault stays in the code"
    if m in CODE_FIX:
        kind = repair(r, e)
        return kind if not kind.startswith("workaround") else "durable workaround in code: " + kind.split(": ", 1)[1]
    return "operational actions only"
