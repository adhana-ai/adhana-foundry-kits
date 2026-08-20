"""Score a set of predicted liable-party determinations against gold. Pure code, shared by
evals/baseline.py and evals/run.py so the free floor and the real run are graded by the identical
function -- a baseline and a model scored by two different scorers cannot be compared honestly.

Four things are scored, kept separate, never folded into one accuracy number -- same discipline
fin-payrun's and fin-invval's own scoring.py files state for their own scorers:

    liable_party                  the core 4-way classification.
    false_confident_call          THE metric this kit exists to measure first -- a confident
                                   (non-insufficient_evidence) call where gold says the evidence
                                   does not support one. Same weight data-reconcile's citation
                                   fidelity check gets: this is the expensive-direction error.
    wrong_sku_exception_misread   the trap-specific metric -- of the gold `internal` cases with a
                                   carrier exception on file naming the WRONG SKU, how many did the
                                   reader call `carrier` anyway. Answers "did it check which SKU
                                   the note names, or just register that a note exists."
    discrepant_sku / quantity     did the drafted notice identify the right line and cite the
                                   right two quantities and delta -- independent of whether the
                                   liable-party call itself was right.

⚑ `false_confident_call`'S DENOMINATOR IS GOLD `insufficient_evidence` CASES, NOT ALL CASES --
same discipline fin-payrun's `false_paid_denominator` and fin-invval's `false_fully_explained`
use. A model that never once says `insufficient_evidence` can still score well on plain accuracy
if the corpus's other three buckets are large; this metric is scoped to exactly the cases where
guessing confident is the mistake, so it cannot be diluted by every case where confidence was fine.

⚑ QUANTITY-CITATION ACCURACY REQUIRES THE SAME PAIR OF DOCUMENTS, NOT JUST TWO CORRECT NUMBERS.
`doc_a`/`doc_b` name WHICH two of po/bol/received disagree; a reply that states the right numbers
under the wrong pair of labels (or the right numbers for the wrong SKU) has not actually cited the
discrepancy, it has produced two numbers that happen to match. Compared as an unordered pair so
the model naming them in either order is not penalised.
"""
from collections import Counter

LIABLE_PARTIES = ("vendor", "carrier", "internal", "insufficient_evidence")


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def score(records, gold):
    matrix = Counter()                                 # (gold, predicted) -> count
    per_liable = {lp: Counter() for lp in LIABLE_PARTIES}
    per_liable_gold_total = {lp: 0 for lp in LIABLE_PARTIES}

    scored = 0
    answered = 0
    liable_correct = 0

    false_confident_call = 0
    false_confident_denom = 0

    wrong_sku_exception_misread = 0
    trap_denom = 0

    sku_correct = 0
    qty_correct = 0

    for rec in records:
        g = gold.get(rec["case_id"])
        if not g:
            continue
        scored += 1
        per_liable_gold_total[g["liable_party"]] += 1

        pred_liable = rec.get("liable_party")
        if pred_liable is not None:
            answered += 1
            matrix[(g["liable_party"], pred_liable)] += 1
            per_liable[g["liable_party"]][pred_liable] += 1
            if pred_liable == g["liable_party"]:
                liable_correct += 1
                per_liable[g["liable_party"]]["correct"] += 1

        if g["liable_party"] == "insufficient_evidence":
            false_confident_denom += 1
            if pred_liable is not None and pred_liable != "insufficient_evidence":
                false_confident_call += 1

        if g["trap"]:
            trap_denom += 1
            if pred_liable == "carrier":
                wrong_sku_exception_misread += 1

        if rec.get("discrepant_sku") is not None and rec.get("discrepant_sku") == g["discrepant_sku"]:
            sku_correct += 1

        pred_pair = frozenset([(rec.get("doc_a"), rec.get("qty_a")),
                               (rec.get("doc_b"), rec.get("qty_b"))])
        gold_pair = frozenset([(g["doc_a"], g["qty_a"]), (g["doc_b"], g["qty_b"])])
        if pred_pair == gold_pair and rec.get("delta") == g["delta"]:
            qty_correct += 1

    overall = {
        "cases_scored": scored,
        "answered": answered,
        "answered_pct": _pct(answered, scored),
        "liable_accuracy_pct": _pct(liable_correct, answered),
        "false_confident_call": false_confident_call,
        "false_confident_call_denominator": false_confident_denom,
        "false_confident_call_rate_pct": _pct(false_confident_call, false_confident_denom),
        "wrong_sku_exception_misread": wrong_sku_exception_misread,
        "wrong_sku_exception_misread_denominator": trap_denom,
        "wrong_sku_exception_misread_rate_pct": _pct(wrong_sku_exception_misread, trap_denom),
        "discrepant_sku_accuracy_pct": _pct(sku_correct, scored),
        "quantity_citation_accuracy_pct": _pct(qty_correct, scored),
    }

    per_liable_out = {}
    for lp in LIABLE_PARTIES:
        total = per_liable_gold_total[lp]
        correct = per_liable[lp].get("correct", 0)
        per_liable_out[lp] = {"gold_total": total, "correct": correct,
                              "accuracy_pct": _pct(correct, total)}

    return {"overall": overall, "per_liable_party": per_liable_out,
           "matrix": {"%s->%s" % k: v for k, v in matrix.items()}}
