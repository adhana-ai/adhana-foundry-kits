"""Score a set of predicted per-candidate verdicts against the pairwise gold. Pure code, shared by
evals/baseline.py and evals/run.py so the free floor and the real run are graded by the identical
function -- a baseline and a model scored by two different scorers cannot be compared honestly,
same discipline every sibling kit's scoring.py states about its own.

Precision and recall are over the LIKE_ITEM label, at the pair level (one request, one
candidate). `false_merge` (a candidate wrongly counted into the forecast estimate) is the
expensive direction -- same shape data-match's decide.py states about its own false merges --
because it corrupts a number a planner acts on, invisibly. `missed_match` is recoverable: a real
comparable just does not get used.
"""
from src import decide as D


def score_request(per_candidate, gold_by_pair, request_id, expects_verdict=True):
    """Every candidate's outcome for one request. `per_candidate` is src/match.py::check()'s own
    `per_candidate` list.

    ⚠︎ `expects_verdict` DISTINGUISHES A MODEL ROW FROM A FLOOR ROW. The free floor
    (evals/baseline.py) never calls a model, so its rows carry `verdict: None` BY DESIGN -- that
    is not a failure to answer, it is the deterministic path (score vs threshold). A real run's
    row also carries `verdict: None` when the candidate list came back incomplete, and THAT is a
    genuine `no_verdict`. Treating the two the same would count every one of the floor's rows as a
    reliability failure it never had."""
    rows = []
    for c in per_candidate:
        label = gold_by_pair.get((request_id, c["item_id"]))
        if label is None:
            continue
        replied = (c.get("verdict") is not None) if expects_verdict else True
        verdict = c.get("verdict") if expects_verdict else None
        out = D.outcome(label, c["similarity_score"], verdict=verdict, replied=replied)
        rows.append({**c, "label": label, "outcome": out})
    return rows


def aggregate(all_rows):
    """⚠︎ `no_verdict` IS SPLIT BY GOLD LABEL FOR THE PRECISION/RECALL ROLL-UP, NOT LEFT IN ITS OWN
    BUCKET UNCOUNTED. A candidate the model never answered still had a real label -- if it was a
    true like item, a real comparable silently went unused (the same cost as missed_match); if it
    was not, no harm was done (the same as apart_correct). `counts` itself still reports the raw
    `no_verdict` total unsplit, so a reader can see the reliability problem on its own terms too."""
    counts = {k: 0 for k in D.OUTCOMES}
    for r in all_rows:
        counts[r["outcome"]] += 1
    total = len(all_rows)

    no_verdict_like = sum(1 for r in all_rows
                          if r["outcome"] == "no_verdict" and r["label"] == "like_item")
    no_verdict_not = counts["no_verdict"] - no_verdict_like

    tp = counts["merged_correct"]
    fp = counts["false_merge"]
    fn = counts["missed_match"] + no_verdict_like
    tn = counts["apart_correct"] + no_verdict_not
    n_no_verdict = counts["no_verdict"]

    precision = round(100.0 * tp / (tp + fp), 1) if (tp + fp) else None
    recall = round(100.0 * tp / (tp + fn), 1) if (tp + fn) else None
    f1 = (round(2 * precision * recall / (precision + recall), 1)
         if precision is not None and recall is not None and (precision + recall) else None)
    accuracy = round(100.0 * (tp + tn) / total, 1) if total else None

    return {"pairs_scored": total, "counts": counts,
           "precision_pct": precision, "recall_pct": recall, "f1_pct": f1,
           "accuracy_pct": accuracy, "no_verdict": n_no_verdict,
           "true_positive": tp, "false_positive": fp, "false_negative": fn,
           "true_negative": tn}


def score(rows_by_request, gold_by_pair, expects_verdict=True):
    """`rows_by_request` is {request_id: per_candidate list}. Returns the overall aggregate plus
    the per-request rows, so a report can drill into any single request's own outcomes."""
    all_rows = []
    per_request = {}
    for rid, per_candidate in rows_by_request.items():
        rows = score_request(per_candidate, gold_by_pair, rid, expects_verdict=expects_verdict)
        per_request[rid] = rows
        all_rows.extend(rows)
    return {"overall": aggregate(all_rows), "per_request": per_request, "rows": all_rows}
