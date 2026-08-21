"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["stmt_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate stmt_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for stmt_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (stmt_id, f["name"], v, f["values"]))

    for stmt_id, r in by_id.items():
        stated = (r.get("stated") or {}).get("extraordinary_assumption_text")
        value_present = r.get("extraordinary_assumption_text") is not None
        if stated != value_present:
            bad("%s: stated[extraordinary_assumption_text]=%s but value is %r"
                % (stmt_id, stated, r.get("extraordinary_assumption_text")))
        present = r.get("extraordinary_assumption_present")
        if (present == "yes") != value_present:
            bad("%s: extraordinary_assumption_present=%s but text is %r"
                % (stmt_id, present, r.get("extraordinary_assumption_text")))

    for f in fields:
        n = sum(1 for stmt_id, r in by_id.items()
                if stmt_id in docs and (r.get("stated") or {}).get(f["name"], True))
        if n == 0:
            bad("%s is stated in 0 documents" % f["name"])
        elif n < 5:
            print("  warn  %s is stated in only %d document(s) — thin, but scoreable" % (f["name"], n))

    from evals.judge import score_flags
    fs = score_flags({}, by_id)
    n_flagged = fs["true_positive"] + fs["false_negative"]
    if n_flagged == 0:
        bad("no gold row ever computes needs_review=true — the recall figure this kit exists "
            "to publish would be undefined")
    else:
        print("  info  %d of %d reports should be flagged (needs_review=true)"
              % (n_flagged, len(by_id)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus"
          % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
