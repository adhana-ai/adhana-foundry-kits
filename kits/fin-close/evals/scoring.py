"""Score a set of predicted per-check verdicts against gold. Pure code, shared by
evals/baseline.py and evals/run.py so the free floor and the real run are graded by the identical
function -- a baseline and a model scored by two different scorers cannot be compared honestly.

⚑ FALSE CLEAN IS COUNTED SEPARATELY FROM ACCURACY, NOT FOLDED INTO IT — same discipline as
data-reconcile's own scorer, which took it from docs-comply's FALSE MET. A verdict of `clean` where
gold says `defect` is the expensive direction: it ships a silently-changed basis, a misposted
account, or an unexplained above-threshold residual with a tick on it. `false_alarm` (predicted
`defect`, gold `clean`) costs a preparer's trust in the queue but never lets a real defect through.
The two are not interchangeable and a single accuracy number hides which one a given error rate is
made of.

⚑ `unverifiable` PREDICTED WHERE GOLD IS `clean` OR `defect` IS COUNTED AS WRONG, NOT AS A SAFE
ABSTENTION. A checker that says "can't tell" on every check would score suspiciously well on a
naive abstention-is-free scorer; it is exactly as useless as one that guesses. It is wrong in a
DIFFERENT, cheaper direction than false_clean or false_alarm, and reported as its own class in the
confusion matrix rather than hidden inside a single "wrong" bucket.
"""
from collections import Counter

CHECKS = ("account", "amount", "basis", "residual")
LABELS = ("clean", "defect", "unverifiable")


def score(records, gold):
    matrix = Counter()                    # (gold, predicted) -> count, across all checks
    per_check = {c: Counter() for c in CHECKS}
    per_check_gold_total = {c: 0 for c in CHECKS}
    answered = 0
    scored = 0
    false_clean = 0
    false_alarm = 0
    gold_defect_total = 0
    gold_clean_total = 0

    for rec in records:
        g = gold.get(rec["close_id"])
        if not g:
            continue
        pred_by_check = {row["check"]: row.get("verdict") for row in rec["checks"]}
        for c in CHECKS:
            gold_v = g["checks"][c]
            pred_v = pred_by_check.get(c)
            per_check_gold_total[c] += 1
            scored += 1
            if gold_v == "defect":
                gold_defect_total += 1
            if gold_v == "clean":
                gold_clean_total += 1
            if pred_v is None:
                continue
            answered += 1
            matrix[(gold_v, pred_v)] += 1
            if pred_v == gold_v:
                per_check[c]["correct"] += 1
            per_check[c][pred_v] += 1
            if gold_v == "defect" and pred_v == "clean":
                false_clean += 1
            if gold_v == "clean" and pred_v == "defect":
                false_alarm += 1

    correct_total = sum(matrix[(v, v)] for v in LABELS)
    overall = {
        "checks_scored": scored,
        "answered": answered,
        "answered_pct": round(100.0 * answered / scored, 1) if scored else None,
        "accuracy_pct": round(100.0 * correct_total / answered, 1) if answered else None,
        "false_clean": false_clean,
        "false_clean_rate_pct": (round(100.0 * false_clean / gold_defect_total, 1)
                                 if gold_defect_total else None),
        "false_alarm": false_alarm,
        "false_alarm_rate_pct": (round(100.0 * false_alarm / gold_clean_total, 1)
                                 if gold_clean_total else None),
        "gold_defect_total": gold_defect_total,
        "gold_clean_total": gold_clean_total,
    }

    per_check_out = {}
    for c in CHECKS:
        cnt = per_check[c]
        total = per_check_gold_total[c]
        per_check_out[c] = {
            "gold_total": total,
            "correct": cnt.get("correct", 0),
            "accuracy_pct": round(100.0 * cnt.get("correct", 0) / total, 1) if total else None,
            "predicted_unverifiable": cnt.get("unverifiable", 0),
        }

    return {"overall": overall, "per_check": per_check_out,
           "matrix": {"%s->%s" % k: v for k, v in matrix.items()}}
