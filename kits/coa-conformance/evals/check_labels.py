"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                            # noqa: E402
from src.extract import recompute_conformance as _rc     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ THE ONLY TWO FIELDS ALLOWED TO BE NULL, AND THEY ARE NULL FOR A REASON. A one-sided
# specification ("not more than X") states no lower limit; a corpus that invented one would be
# testing a different question. Every other field is stated on every certificate.
NULLABLE = {"spec_lower_limit", "spec_upper_limit"}

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

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s may be null in this corpus"
                % (f["name"], n_null, " and ".join(sorted(NULLABLE))))

    # A certificate with NEITHER limit states no specification at all, and the verdict would be
    # vacuously "yes" -- a record that cannot test anything.
    unbounded = [i for i, r in by_id.items()
                 if r.get("spec_lower_limit") is None and r.get("spec_upper_limit") is None]
    if unbounded:
        bad("%d record(s) state no limit on either side: %s" % (len(unbounded), unbounded[:5]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN ARITHMETIC. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the note, it is the comparison.
    disagree = []
    for stmt_id, r in sorted(by_id.items()):
        want = _rc(r.get("measured_value"), r.get("spec_lower_limit"), r.get("spec_upper_limit"))
        if want != r.get("conforms_to_spec"):
            disagree.append(stmt_id)
    if disagree:
        bad("%d gold row(s) label a conformance their own numbers do not support: %s"
            % (len(disagree), disagree[:5]))

    n_no = sum(1 for r in by_id.values() if r.get("conforms_to_spec") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one conformance class (%d yes, %d no) — the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d certificates are out of specification (conforms_to_spec=no)"
              % (n_no, len(by_id)))
        print("  info  %d record(s) carry a one-sided specification"
              % sum(1 for r in by_id.values()
                    if r.get("spec_lower_limit") is None or r.get("spec_upper_limit") is None))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own arithmetic" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
