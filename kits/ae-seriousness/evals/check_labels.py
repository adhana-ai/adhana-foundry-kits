"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                  # noqa: E402
from src.extract import compute as _compute    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ ONE FIELD IS ALLOWED TO BE NULL AND IT IS NAMED HERE RATHER THAN INFERRED. A report that
# reaches for no severity word has none to extract, and null is the correct answer -- the prompt
# asks for it explicitly. Every OTHER field is required on every row: a null there means the
# generator failed to state something it promised to state, and would be scored as a model miss.
NULLABLE = ("narrative_severity_word",)

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
                % (f["name"], n_null, ", ".join(NULLABLE)))

    # The nullable field must actually EXERCISE both states, or the null branch of the prompt,
    # the scorer and the UI all ship untested.
    for name in NULLABLE:
        n_null = sum(1 for r in by_id.values() if r.get(name) is None)
        if n_null == 0:
            bad("%s is never null -- the abstention case this corpus claims to test is absent"
                % name)
        elif n_null == len(by_id):
            bad("%s is null on every row -- there is nothing to extract" % name)
        else:
            print("  info  %s is null on %d of %d rows (correct abstention is scored as a hit)"
                  % (name, n_null, len(by_id)))

    n_flagged = sum(1 for r in by_id.values() if _compute(r))
    if n_flagged == 0:
        bad("no gold row ever computes needs_review=true — the recall figure this kit exists "
            "to publish would be undefined")
    else:
        print("  info  %d of %d cases should be flagged (needs_review=true)"
              % (n_flagged, len(by_id)))

    # The corpus's whole claim is that a severity-word reader fails on a real slice of it. If the
    # confusable slice were empty the baseline would tie the model and nothing would be measured.
    n_conf = sum(1 for r in by_id.values() if r.get("_register") == "confusable")
    if n_conf == 0:
        bad("no gold row is in the confusable register — the ambiguity this kit measures is absent")
    else:
        print("  info  %d of %d cases carry a severity word from the wrong register"
              % (n_conf, len(by_id)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus"
          % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
