"""The merge decision -- does one candidate count as a like-item -- and the five outcomes it can
produce. Pure code, no model. Same shape as data-match's and precedent-match's decide.py.

⚑ THE THRESHOLD IS THE PRODUCT, NOT A TUNING KNOB. With no verdict (the free-floor path), a
candidate counts as a like item only when its similarity score meets SIM_THRESHOLD. There is no
setting that is simply correct: raise it and real comparables get excluded from the forecast
(missed_match); lower it and a candidate that only superficially resembles the request gets folded
into the number a planner will act on (false_merge) -- and that second error is the expensive
direction, because it is invisible in the published forecast.

THE FIVE OUTCOMES:

    merged_correct    counted as like item, and gold agrees
    false_merge        counted as like item, gold says it is not -- THE EXPENSIVE ERROR: it
                       quietly pollutes the forecast a planner will act on
    missed_match       kept apart, gold says it IS a like item -- a real comparable goes unused
    apart_correct      kept apart, and gold agrees
    no_verdict          nothing usable came back from the model
"""
SIM_THRESHOLD = 1.00      # the free floor's own bar: all four fields exact, nothing looser

OUTCOMES = ("merged_correct", "false_merge", "missed_match", "apart_correct", "no_verdict")

MEANS = {
    "merged_correct": "counted as like item, gold agrees",
    "false_merge": "counted as like item, gold disagrees -- pollutes the forecast",
    "missed_match": "excluded, gold says it is a real like item -- a comparable goes unused",
    "apart_correct": "excluded, gold agrees",
    "no_verdict": "nothing usable came back",
}


def counts_as_like_item(score, threshold=SIM_THRESHOLD, verdict=None):
    """Does this pair count toward the drafted forecast?

    With no verdict, the similarity score alone decides -- the deterministic floor. With a
    verdict, the model decides and the score is evidence beside it, except UNSURE never counts --
    the point of the third verdict is to stop rather than guess, so honouring it is the whole
    reason it exists.
    """
    if verdict is None:
        return score >= threshold
    if verdict == "LIKE_ITEM":
        return True
    return False          # NOT_LIKE_ITEM and UNSURE both stay apart


def outcome(label, score, threshold=SIM_THRESHOLD, verdict=None, replied=True):
    """One pair's outcome. `label` is the gold 'like_item' / 'not_like_item'. `replied` is False
    when the model returned nothing usable for this candidate."""
    if not replied:
        return "no_verdict"
    merged = counts_as_like_item(score, threshold, verdict)
    is_like = label == "like_item"
    if merged:
        return "merged_correct" if is_like else "false_merge"
    return "missed_match" if is_like else "apart_correct"
