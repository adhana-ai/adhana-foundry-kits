"""Candidate history items for one new-item setup request. Pure code, no model -- the step that
decides whether this kit can be pointed at a real item catalog at all.

⚑ WHY THIS EXISTS, SAME CLAIM AS data-match's AND precedent-match's block.py. Comparing one new
item against every item ever set up is a different product from comparing it against the handful
that could plausibly seed its forecast. Blocking is what makes that set small; it is also the step
that can silently lose a true comparable, because a candidate that is never generated can never be
judged. That recall cost is measured (`stats()`), not assumed.

THE KEY: `category`, and only `category`. A cookware item has nothing to teach a pet-supplies item
about early sell-through, whatever its material or season -- so this kit's one blocking key is a
hard scope, not a heuristic one. Everything downstream (the similarity floor, the model, the merge
threshold) only ever compares items that already share it.
"""
def candidates(request, history):
    """Every history item in the request's own category, oldest-id-first."""
    cat = request["category"]
    return sorted((h for h in history if h["category"] == cat), key=lambda h: h["item_id"])


def stats(requests, history, gold_by_pair):
    """What blocking bought and what it cost, over the whole corpus."""
    total_true, surviving = 0, 0
    sizes = []
    for r in requests:
        cand = candidates(r, history)
        sizes.append(len(cand))
        cand_ids = {c["item_id"] for c in cand}
        for (rid, iid), label in gold_by_pair.items():
            if rid != r["request_id"] or label != "like_item":
                continue
            total_true += 1
            if iid in cand_ids:
                surviving += 1
    return {"requests": len(requests), "history_items": len(history),
            "true_like_item_pairs": total_true, "true_like_item_pairs_surviving": surviving,
            "blocking_recall": round(surviving / total_true, 4) if total_true else None,
            "candidate_set_size_avg": round(sum(sizes) / len(sizes), 2) if sizes else None,
            "candidate_set_size_max": max(sizes) if sizes else None}
