"""What a simple, dumb rule catches, over the same corpus. Free. No key, no dependency, no model
call.

    python -m evals.baseline

Every sibling kit publishes this floor -- fin-payrun's rule-order baseline, data-reconcile's regex
baseline -- and this kit's version of the same idea is a classifier someone free-texting a quick
script would actually write: if there's a carrier exception note on the case, blame the carrier.

⚠︎ THE BUG THIS BASELINE HAS, ON PURPOSE, AND WHY IT IS HONEST RATHER THAN A STRAWMAN. A person
asked to write "who's liable" in five minutes reaches for the field that most directly answers the
question -- an exception note naming a transit problem -- and stops there. That is the WRONG check:
the mechanic this kit measures requires confirming the note actually names the SAME SKU as the
discrepant line before crediting it, not just noting that a note exists somewhere on the case.
Checking presence-only is not a bug someone would need to be clever to introduce; it is the natural
first thing to check, and it is exactly why the eval exists.

**This baseline is correct on every non-trap case.** The corpus never plants a carrier exception on
a `vendor` or `insufficient_evidence` case (see data/SOURCES.md), so presence-of-exception and
correct-SKU-match agree everywhere except the corpus's planted trap set: the 6 `internal` cases
where a real exception note is on file but names a different SKU. On every one of those, this
baseline calls `carrier` when gold says `internal` -- get the trap wrong, get everything else
right, which is what a passing score here actually means.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import resolve as R                                   # noqa: E402
from evals import scoring as S                                  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def classify(case):
    """Finding the discrepant line and its three quantities is a mechanical equality check, not a
    judgment call, so this baseline gets that part right every time -- its one and only weakness
    is the liable_party call itself, checked in the wrong order. Returns a dict shaped like
    src/resolve.py's check() so both feed the same scorer."""
    lines = case["lines"]
    disc = next(l for l in lines if not (l["po_qty"] == l["bol_qty"] == l["received_qty"]))
    po, bol, rec, sku = disc["po_qty"], disc["bol_qty"], disc["received_qty"], disc["sku"]

    if case.get("carrier_exception"):
        # THE BUG: any exception note on the case is read as "the carrier did it" -- never
        # checked against which SKU the note actually names.
        liable, doc_a, qty_a, doc_b, qty_b = "carrier", "bol", bol, "received", rec
    elif bol < po and rec == bol:
        liable, doc_a, qty_a, doc_b, qty_b = "vendor", "po", po, "bol", bol
    elif bol == po and rec < bol:
        liable, doc_a, qty_a, doc_b, qty_b = "internal", "bol", bol, "received", rec
    else:
        liable, doc_a, qty_a, doc_b, qty_b = "insufficient_evidence", "po", po, "received", rec

    return {"case_id": case["case_id"], "liable_party": liable, "discrepant_sku": sku,
           "doc_a": doc_a, "qty_a": qty_a, "doc_b": doc_b, "qty_b": qty_b,
           "delta": abs(qty_a - qty_b), "notice_text": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-exception-first")
    a = ap.parse_args()

    gold = R.load_gold()
    records = []
    misses = []
    for case in R.cases():
        rec = classify(case)
        records.append(rec)
        g = gold[case["case_id"]]
        if rec["liable_party"] != g["liable_party"]:
            misses.append((case["case_id"], g["liable_party"], rec["liable_party"], g["trap"]))

    scored = S.score(records, gold)
    out = {"run_id": a.run_id, "baseline": True, "cases": len(records),
          "scores": scored["overall"], "per_liable_party": scored["per_liable_party"],
          "misses": [{"case_id": c, "gold": go, "predicted": pr, "trap": tr}
                    for c, go, pr, tr in misses]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("exception-first baseline (blames the carrier on ANY exception note) over %d cases"
         % len(records))
    print("liable_party accuracy: %s%%" % o["liable_accuracy_pct"])
    print("false_confident_call: %s of %s (%s%%)" % (o["false_confident_call"],
                                                     o["false_confident_call_denominator"],
                                                     o["false_confident_call_rate_pct"]))
    print("wrong_sku_exception_misread: %s of %s (%s%%)"
         % (o["wrong_sku_exception_misread"], o["wrong_sku_exception_misread_denominator"],
            o["wrong_sku_exception_misread_rate_pct"]))
    print("discrepant_sku accuracy: %s%%" % o["discrepant_sku_accuracy_pct"])
    print("quantity_citation accuracy: %s%%" % o["quantity_citation_accuracy_pct"])
    for lp, pl in scored["per_liable_party"].items():
        print("  %-22s accuracy %s%%  (gold %s)" % (lp, pl["accuracy_pct"], pl["gold_total"]))
    print("\nmisses (%d) -- every one a trap case, exception read without checking its SKU:"
         % len(misses))
    for c, go, pr, tr in misses:
        print("  %-14s gold=%-22s predicted=%-22s trap=%s" % (c, go, pr, tr))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
