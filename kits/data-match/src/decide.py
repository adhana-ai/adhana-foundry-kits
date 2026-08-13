"""The merge decision, and the five outcomes it can produce. Pure code, no model.

⚑ THE THRESHOLD IS THE PRODUCT, NOT A TUNING KNOB. Nothing merges below it. There is no setting that is
simply correct: raise it and you keep duplicates, lower it and you fuse real people, and the two costs
are not symmetric — a duplicate left in place is annoying and somebody fixes it next quarter, while a
false merge destroys records that cannot be un-merged. So this module refuses to hide the choice: it
takes the threshold as an argument, records it on every decision, and `sweep()` exists so the report can
show the trade instead of asserting a winner.

⚑ WHY IT RUNS AFTER THE MODEL AND NOT INSTEAD OF IT. The model returns a word, not a probability, so its
verdict is a vote and the score is the evidence. A SAME verdict on a pair the floor scores 0.31 is
exactly the case a person should see — the model claims a match that nothing measurable supports.

THE FIVE OUTCOMES, and the reason each one is its own state:

    merged_correct    merged, and the labels agree
    false_merge       merged two different entities — THE EXPENSIVE ERROR, never averaged with below
    missed_match      kept apart, and the labels say same — recoverable
    apart_correct     kept apart, and the labels agree
    no_verdict        nothing usable came back from the model

⚠︎ `no_verdict` MUST NOT COLLAPSE INTO `missed_match`. An empty reply does not merge anything, so it
LOOKS like the cautious outcome; treating it as one converts every failed call into a quality figure and
hides the failure. Three kits in this repo have recorded replies that spent the whole output ceiling and
returned an empty string, which is precisely how common this is.
"""
OUTCOMES = ("merged_correct", "false_merge", "missed_match", "apart_correct", "no_verdict")

MEANS = {
    "merged_correct": "merged, labels agree",
    "false_merge": "merged two different entities — destroys data, cannot be undone",
    "missed_match": "kept apart, labels say same — a duplicate survives",
    "apart_correct": "kept apart, labels agree",
    "no_verdict": "nothing usable came back",
}


def merges(score, threshold, verdict=None):
    """Does this pair merge?

    With no verdict the score alone decides — that is the deterministic floor. With a verdict the
    model decides and the score is evidence beside it, except that `UNSURE` never merges: the point of
    the third verdict is to stop rather than guess, so honouring it is the whole reason it exists.
    """
    if verdict is None:
        return score >= threshold
    if verdict == "SAME":
        return True
    return False                      # DIFFERENT and UNSURE both keep the pair apart


def outcome(label, score, threshold, verdict=None, replied=True):
    """One pair's outcome. `replied` is False when the model returned nothing usable."""
    if not replied:
        return "no_verdict"
    merged = merges(score, threshold, verdict)
    same = label == "same"
    if merged:
        return "merged_correct" if same else "false_merge"
    return "missed_match" if same else "apart_correct"


def tally(rows):
    """Counts per outcome plus the two rates, kept apart on purpose.

    ⚠︎ NO F-SCORE IS RETURNED HERE AND THAT IS DELIBERATE. Precision and recall answer two different
    questions — "of what we merged, how much should have been?" and "of what should have merged, how
    much did?" — and a kit whose two failure directions cost different amounts must publish both. An
    F-score is one number that moves when either does, which is the opposite of what this report needs.
    """
    c = {k: 0 for k in OUTCOMES}
    for r in rows:
        c[r["outcome"]] = c.get(r["outcome"], 0) + 1
    merged = c["merged_correct"] + c["false_merge"]
    should = c["merged_correct"] + c["missed_match"]
    return {"counts": c, "pairs": len(rows),
            "precision": round(c["merged_correct"] / merged, 4) if merged else None,
            "recall": round(c["merged_correct"] / should, 4) if should else None,
            "false_merges": c["false_merge"], "missed_matches": c["missed_match"],
            "no_verdict": c["no_verdict"],
            "reconciles": sum(c.values()) == len(rows)}


def sweep(rows, thresholds=(0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)):
    """The same rows at every threshold, so the trade is shown rather than argued.

    Each row needs `label` and `score`. Used by the baseline and by the report; it calls nothing and
    costs nothing, so there is no excuse for publishing a single threshold as if it were the answer.
    """
    out = []
    for t in thresholds:
        scored = [{"outcome": outcome(r["label"], r["score"], t)} for r in rows]
        rec = tally(scored)
        rec["threshold"] = t
        out.append(rec)
    return out
