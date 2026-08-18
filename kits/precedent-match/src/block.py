"""Candidate history events for one planned request. Pure code, no model -- the step that decides
whether this kit can be pointed at a real event log at all.

⚑ WHY THIS EXISTS, SAME CLAIM AS data-match's AND change-impact's block.py. Comparing one planned
request against every historical event ever run is a different product from comparing it against the
handful that could plausibly be a precedent. Blocking is what makes that set small; it is also the
step that can silently lose a true analog, because a candidate that is never generated can never be
judged. That recall cost is measured (`stats()`), not assumed.

THE KEY: `category`, and only `category`. A snacks promotion has nothing to teach a home-goods
promotion about lift, whatever its mechanic or season -- so this kit's one blocking key is a hard
scope, not a heuristic one. Everything downstream (the similarity floor, the model, the merge
threshold) only ever compares events that already share it.
"""
def candidates(request, history):
    """Every history event in the request's own category, oldest-id-first."""
    cat = request["category"]
    return sorted((h for h in history if h["category"] == cat), key=lambda h: h["event_id"])


def stats(requests, history, gold_by_pair):
    """What blocking bought and what it cost, over the whole corpus."""
    total_true, surviving = 0, 0
    sizes = []
    for r in requests:
        cand = candidates(r, history)
        sizes.append(len(cand))
        cand_ids = {c["event_id"] for c in cand}
        for (rid, eid), label in gold_by_pair.items():
            if rid != r["request_id"] or label != "analog":
                continue
            total_true += 1
            if eid in cand_ids:
                surviving += 1
    return {"requests": len(requests), "history_events": len(history),
            "true_analog_pairs": total_true, "true_analog_pairs_surviving": surviving,
            "blocking_recall": round(surviving / total_true, 4) if total_true else None,
            "candidate_set_size_avg": round(sum(sizes) / len(sizes), 2) if sizes else None,
            "candidate_set_size_max": max(sizes) if sizes else None}
