"""Score a set of predicted (verdict, proposed_value) rows against gold. Pure code, shared by
evals/baseline.py and evals/run.py so the free floor and the real run are graded through the
identical function -- a baseline and a model scored by two different scorers cannot be compared
honestly, same discipline as change-impact's evals/scoring.py.

Reports precision and recall of drift detection AND the agreement rate of the proposed corrected
value, PER CATEGORY as well as overall -- the exact pair `eval_intent` asks for. See
`src/decide.py` for why these are separate axes and why neither ever collapses into one number.
"""
from src import decide as D

CATEGORIES = ("lead_time", "safety_margin", "service_target")


def score_row(row, gold):
    """One parameter's outcome. `row` carries `verdict`, `replied`, `proposed_value` (whatever the
    pipeline under test produced); `gold` is that parameter's labelled.jsonl entry."""
    out = D.outcome(gold["label"], row.get("verdict"), row.get("replied", True))
    v_outcome = None
    if out == "correct_flag":
        agrees = D.value_agrees(gold.get("gold_corrected_value"), row.get("proposed_value"))
        if agrees is not None:
            v_outcome = "value_agrees" if agrees else "value_disagrees"
    return {"outcome": out, "value_outcome": v_outcome}


def _rate(a, b):
    total = a + b
    return round(100.0 * a / total, 1) if total else None


def score(rows, gold_by_id, params_by_id):
    scored = []
    for row in rows:
        g = gold_by_id.get(row["parameter_id"])
        if not g:
            continue
        s = score_row(row, g)
        cat = params_by_id[row["parameter_id"]]["category"]
        scored.append({**row, **s, "gold": g, "category": cat})

    def _summarise(rows_):
        counts = {k: 0 for k in D.OUTCOMES}
        vcounts = {k: 0 for k in D.VALUE_OUTCOMES}
        for s in rows_:
            counts[s["outcome"]] += 1
            if s["value_outcome"]:
                vcounts[s["value_outcome"]] += 1
        n_drift = sum(1 for s in rows_ if s["gold"]["label"] == "drift")
        n_no_drift = len(rows_) - n_drift
        return {
            "n": len(rows_), "n_drift": n_drift, "n_no_drift": n_no_drift,
            "counts": counts,
            "recall_pct": _rate(counts["correct_flag"], counts["missed_drift"]),
            "precision_pct": _rate(counts["correct_flag"], counts["false_flag"]),
            "value_agreement_pct": _rate(vcounts["value_agrees"], vcounts["value_disagrees"]),
            "value_counts": vcounts,
            "no_verdict": counts["no_verdict"],
        }

    overall = _summarise(scored)
    per_category = {cat: _summarise([s for s in scored if s["category"] == cat])
                    for cat in CATEGORIES}
    per_trap = {}
    for s in scored:
        t = s["gold"]["trap"]
        per_trap.setdefault(t, []).append(s)
    per_trap = {t: _summarise(rows_) for t, rows_ in per_trap.items()}

    return {"overall": overall, "per_category": per_category, "per_trap": per_trap, "rows": scored}
