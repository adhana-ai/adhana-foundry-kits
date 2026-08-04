"""Check the gold set before anything is scored against it. Run this before spending money.

A labelled set is the one thing in a kit that nothing else can check. A wrong gold value does not
crash anything — it silently converts a correct extraction into a recorded failure, and the run
that discovers it has already been paid for. So this runs first, costs nothing, and is blunt.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                  # noqa: E402
from tools.build_corpus import _stated         # noqa: E402  (ONE copy of "is it stated")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    names = [f["name"] for f in fields]
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["nct_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate nct_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for nct, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (nct, f["name"], v, f["values"]))

    # THE `stated` MAP IS RE-DERIVED, NOT TRUSTED. It is the axis the whole eval splits on, and it
    # was computed by a different script at a different time; if the corpus was rebuilt and the
    # gold was not, every refusal verdict silently moves.
    drift = 0
    for nct, r in by_id.items():
        if nct not in docs:
            continue
        txt = EX.load_doc(nct)
        for name in names:
            if name == "nct_id":
                continue
            want = bool(_stated(r.get(name), txt))
            got = bool((r.get("stated") or {}).get(name))
            if want != got:
                drift += 1
                if drift <= 5:
                    bad("%s: stated[%s] says %s, the document says %s" % (nct, name, got, want))
    if drift > 5:
        bad("... and %d more stated-flag disagreements" % (drift - 5))

    # A field nothing states cannot be scored — this is the check that would have caught the five
    # fields cut from the wireframe's illustrative list, before a run rather than after one.
    for f in fields:
        n = sum(1 for nct, r in by_id.items()
                if nct in docs and (r.get("stated") or {}).get(f["name"], f["name"] == "nct_id"))
        if n == 0:
            bad("%s is stated in 0 documents — it cannot be extracted by anything, so an "
                "accuracy for it would be a fact about the corpus" % f["name"])
        elif n < 5:
            print("  warn  %s is stated in only %d document(s) — thin, but scoreable" % (f["name"], n))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus"
          % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
