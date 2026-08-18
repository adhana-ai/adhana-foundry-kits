"""Score a set of predicted (match, change_type, new_value) rows against gold. Pure code, shared
by evals/baseline.py and evals/run.py so the free floor and the real run are graded by the
identical function -- a baseline and a model scored by two different scorers cannot be compared
honestly, same discipline as data-reconcile's evals/scoring.py.

⚑ SEVEN OUTCOMES, NOT ONE ACCURACY NUMBER. A single "correct/wrong" figure hides which of three
very different mistakes it is made of:

    correct_none              gold says no open record matches -- predicted NONE. Correct.
    match_correct_impact_correct   right record, right change, right computed impact. The win.
    match_correct_impact_wrong     right record, but the change or its value was misread -- the
                                   impact number this produces is wrong even though the match was
                                   right, which is the case a reader most needs distinguished from
                                   a clean miss.
    wrong_match                    matched to a real record that is not the gold one.
    false_none                     gold has a real match, predicted NONE -- a real change request
                                   would be silently dropped.
    false_match                    gold is NONE (no open record exists), predicted a real record
                                   anyway -- a change would be applied to the wrong thing.
    abstained_unsure               predicted UNSURE. Not a wrong guess -- a decline, counted apart
                                   so it is never folded into either "correct" or "wrong".
    no_verdict                     nothing usable came back from the model.

⚑ false_match IS THE EXPENSIVE DIRECTION, SAME SHAPE AS data-reconcile's FALSE CLEAN. Applying a
change to a record that was never the one being discussed is worse than escalating a message
nobody could place -- it silently corrupts a record nobody asked to touch.
"""
from src import impact as I

COST_TOL_USD = 0.02
DATE_TOL_DAYS = 0


def _impact_matches(computed, gold_impact):
    if gold_impact is None or computed is None:
        return False
    c1, c2 = computed.get("cost_impact_usd"), gold_impact.get("cost_impact_usd")
    if c1 is None or c2 is None or abs(c1 - c2) > COST_TOL_USD:
        return False
    d1, d2 = computed.get("in_stock_date_delta_days"), gold_impact.get("in_stock_date_delta_days")
    if (d1 is None) != (d2 is None):
        return False
    if d1 is not None and abs(d1 - d2) > DATE_TOL_DAYS:
        return False
    return True


def score_row(row, gold, records_by_id):
    """One message's outcome. `row` carries `match`, `change_type`, `new_value` (whatever the
    pipeline under test produced); `gold` is that message's gold.jsonl entry."""
    pred_match = row.get("match")
    gold_match = gold["matched_record_id"]

    if pred_match is None:
        return {"outcome": "no_verdict", "impact_correct": None, "computed_impact": None,
               "decision": None}

    if pred_match == "UNSURE":
        return {"outcome": "abstained_unsure", "impact_correct": None, "computed_impact": None,
               "decision": None}

    if pred_match == gold_match:
        if gold_match == "NONE":
            return {"outcome": "correct_none", "impact_correct": None, "computed_impact": None,
                   "decision": None}
        rec = records_by_id.get(pred_match)
        computed = None
        decision = None
        if rec is not None and row.get("change_type"):
            computed = I.compute(rec, row["change_type"], row.get("new_value"))
            decision = I.decide(computed) if computed is not None else "escalate"
        impact_ok = (row.get("change_type") == gold["change_type"]
                    and _impact_matches(computed, gold.get("impact")))
        return {"outcome": "match_correct_impact_correct" if impact_ok
                          else "match_correct_impact_wrong",
               "impact_correct": impact_ok, "computed_impact": computed, "decision": decision}

    if gold_match == "NONE":
        return {"outcome": "false_match", "impact_correct": None, "computed_impact": None,
               "decision": None}
    if pred_match == "NONE":
        return {"outcome": "false_none", "impact_correct": None, "computed_impact": None,
               "decision": None}
    return {"outcome": "wrong_match", "impact_correct": None, "computed_impact": None,
           "decision": None}


OUTCOMES = ("correct_none", "match_correct_impact_correct", "match_correct_impact_wrong",
           "wrong_match", "false_none", "false_match", "abstained_unsure", "no_verdict")


def score(rows, gold_by_id, records_by_id):
    scored = []
    for row in rows:
        g = gold_by_id.get(row["message_id"])
        if not g:
            continue
        s = score_row(row, g, records_by_id)
        scored.append({**row, **s, "gold": g})

    counts = {k: 0 for k in OUTCOMES}
    for s in scored:
        counts[s["outcome"]] += 1
    total = len(scored)
    n_real_gold = sum(1 for s in scored if s["gold"]["matched_record_id"] != "NONE")
    n_none_gold = total - n_real_gold

    matched_and_scored = counts["match_correct_impact_correct"] + counts["match_correct_impact_wrong"]
    match_correct_total = counts["correct_none"] + matched_and_scored

    per_type = {}
    for s in scored:
        ct = s["gold"]["change_type"]
        if not ct:
            continue
        d = per_type.setdefault(ct, {"n": 0, "match_correct": 0, "impact_correct": 0})
        d["n"] += 1
        if s["outcome"] in ("match_correct_impact_correct", "match_correct_impact_wrong"):
            d["match_correct"] += 1
        if s["outcome"] == "match_correct_impact_correct":
            d["impact_correct"] += 1

    ambiguous = [s for s in scored if s["gold"].get("ambiguous")]
    unambiguous = [s for s in scored if s["gold"]["matched_record_id"] != "NONE"
                  and not s["gold"].get("ambiguous")]

    def _match_acc(rows_):
        if not rows_:
            return None
        ok = sum(1 for s in rows_ if s["outcome"] in
                ("correct_none", "match_correct_impact_correct", "match_correct_impact_wrong"))
        return round(100.0 * ok / len(rows_), 1)

    overall = {
        "messages_scored": total,
        "match_accuracy_pct": round(100.0 * match_correct_total / total, 1) if total else None,
        "impact_accuracy_pct": (round(100.0 * counts["match_correct_impact_correct"] / matched_and_scored, 1)
                                if matched_and_scored else None),
        "false_none": counts["false_none"],
        "false_none_rate_pct": (round(100.0 * counts["false_none"] / n_real_gold, 1)
                                if n_real_gold else None),
        "false_match": counts["false_match"],
        "false_match_rate_pct": (round(100.0 * counts["false_match"] / n_none_gold, 1)
                                 if n_none_gold else None),
        "abstained_unsure": counts["abstained_unsure"],
        "wrong_match": counts["wrong_match"],
        "no_verdict": counts["no_verdict"],
        "counts": counts,
        "n_real_gold": n_real_gold,
        "n_none_gold": n_none_gold,
        "ambiguous_match_accuracy_pct": _match_acc(ambiguous),
        "unambiguous_match_accuracy_pct": _match_acc(unambiguous),
    }
    per_type_out = {ct: {"n": d["n"],
                        "match_accuracy_pct": round(100.0 * d["match_correct"] / d["n"], 1),
                        "impact_accuracy_pct": (round(100.0 * d["impact_correct"] / d["match_correct"], 1)
                                                if d["match_correct"] else None)}
                   for ct, d in per_type.items()}
    return {"overall": overall, "per_change_type": per_type_out, "rows": scored}
