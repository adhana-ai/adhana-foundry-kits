"""What a simple, dumb rule catches, over the same corpus. Free. No key, no dependency, no model
call.

    python -m evals.baseline

Every sibling kit publishes this floor -- fin-close's regex-against-one-phrasing score,
ops-triage's rule-and-threshold floor -- and this kit's version of the same idea is a classifier
someone free-texting a quick script would actually write: check the field that answers the
question you actually care about FIRST.

⚠︎ THE BUG THIS BASELINE HAS, ON PURPOSE, AND WHY IT IS HONEST RATHER THAN A STRAWMAN. A person
asked to write "is this invoice paid" in five minutes reaches for the field that answers that
question directly -- `remittance.remitted` -- checks it first, and works backward through
`run_inclusion`, `approval`, `match` only if that one is false. That is the WRONG order: the
mechanic this kit measures requires reading match, then approval, then run_inclusion, then
remittance, and stopping at the first one that is not clean -- a downstream field can look complete
while an earlier one governs. Checking downstream-first is not a bug someone would need to be
clever to introduce; it is the natural order to write, and it is exactly why the eval exists.

**This baseline is correct on every non-trap invoice.** Reversing the check order only produces a
wrong answer when a downstream field has been deliberately built to look complete despite an
earlier exception -- the corpus's planted trap set. On every other invoice, the two orders agree
(there is nothing downstream to be misled by), so a passing score here is not free: it is what "get
the trap wrong, get everything else right" looks like in a number. See the printed per-stage
breakdown below for exactly which invoices this baseline misses.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import payrun as C                                    # noqa: E402
from src import prompt as P                                     # noqa: E402
from evals import scoring as S                                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def classify(inv):
    """Check remittance, then run_inclusion, then approval, then match -- the reverse of the
    correct precedence order. Returns (current_stage, requires_ap_review, stated_date)."""
    m, a, r, x = inv["match"], inv["approval"], inv["run_inclusion"], inv["remittance"]

    if x["remitted"]:
        stage = "remitted"
    elif r["included"]:
        stage = "in_scheduled_run"
    elif a["status"] == "exception":
        stage = "approval_exception"
    elif not m["matched"]:
        stage = "match_exception"
    else:
        stage = "awaiting_run_inclusion"

    review = stage in P.REVIEW_STAGES
    if stage == "in_scheduled_run":
        stated_date = r["scheduled_date"]
    elif stage == "remitted":
        stated_date = x["remittance_date"]
    else:
        stated_date = None
    return stage, review, stated_date


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-ruleorder")
    a = ap.parse_args()

    gold = C.load_gold()
    records = []
    misses = []
    for inv in C.invoices():
        stage, review, stated_date = classify(inv)
        records.append({"invoice_id": inv["invoice_id"], "current_stage": stage,
                        "requires_ap_review": review, "stated_date": stated_date, "reply": None})
        g = gold[inv["invoice_id"]]
        if stage != g["current_stage"]:
            misses.append((inv["invoice_id"], g["current_stage"], stage,
                          g.get("trap_field")))

    scored = S.score(records, gold)
    out = {"run_id": a.run_id, "baseline": True, "invoices": len(records),
          "scores": scored["overall"], "per_stage": scored["per_stage"],
          "misses": [{"invoice_id": i, "gold": go, "predicted": pr, "trap_field": tf}
                    for i, go, pr, tf in misses]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("rule-order baseline (checks remittance first) over %d invoices" % len(records))
    print("overall stage accuracy: %s%%" % scored["overall"]["stage_accuracy_pct"])
    print("requires_ap_review accuracy: %s%%" % scored["overall"]["review_accuracy_pct"])
    print("false_paid: %s of %s (%s%%)" % (scored["overall"]["false_paid"],
                                          scored["overall"]["false_paid_denominator"],
                                          scored["overall"]["false_paid_rate_pct"]))
    print("date accuracy: %s%%" % scored["overall"]["date_accuracy_pct"])
    for s, ps in scored["per_stage"].items():
        print("  %-24s accuracy %s%%  (gold %s)" % (s, ps["accuracy_pct"], ps["gold_total"]))
    print("\nmisses (%d) -- every one is a trap invoice, checked downstream-first:" % len(misses))
    for i, go, pr, tf in misses:
        print("  %-16s gold=%-20s predicted=%-20s trap_field=%s" % (i, go, pr, tf))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
