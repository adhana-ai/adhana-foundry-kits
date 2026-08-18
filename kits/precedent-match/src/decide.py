"""The merge decision -- does one candidate count as an analog -- and the five outcomes it can
produce. Pure code, no model. Same shape as data-match's decide.py.

⚑ THE THRESHOLD IS THE PRODUCT, NOT A TUNING KNOB. With no verdict (the free-floor path), a
candidate counts as an analog only when its similarity score meets SIM_THRESHOLD. There is no
setting that is simply correct: raise it and real analogs get excluded from the lift estimate
(missed_match); lower it and a candidate that only superficially resembles the request gets folded
into the number a planner will act on (false_merge) -- and that second error is the expensive
direction, because it is invisible in the published percentage.

THE FIVE OUTCOMES:

    merged_correct    counted as analog, and gold agrees
    false_merge        counted as analog, gold says it is not -- THE EXPENSIVE ERROR: it quietly
                       pollutes the lift estimate a planner will act on
    missed_match       kept apart, gold says it IS an analog -- a real precedent goes unused
    apart_correct      kept apart, and gold agrees
    no_verdict          nothing usable came back from the model
"""
SIM_THRESHOLD = 1.00      # the free floor's own bar: all four fields exact, nothing looser

OUTCOMES = ("merged_correct", "false_merge", "missed_match", "apart_correct", "no_verdict")

MEANS = {
    "merged_correct": "counted as analog, gold agrees",
    "false_merge": "counted as analog, gold disagrees -- pollutes the lift estimate",
    "missed_match": "excluded, gold says it is a real analog -- a precedent goes unused",
    "apart_correct": "excluded, gold agrees",
    "no_verdict": "nothing usable came back",
}


def counts_as_analog(score, threshold=SIM_THRESHOLD, verdict=None):
    """Does this pair count toward the lift estimate?

    With no verdict, the similarity score alone decides -- the deterministic floor. With a verdict,
    the model decides and the score is evidence beside it, except UNSURE never counts -- the point
    of the third verdict is to stop rather than guess, so honouring it is the whole reason it
    exists.
    """
    if verdict is None:
        return score >= threshold
    if verdict == "ANALOG":
        return True
    return False          # NOT_ANALOG and UNSURE both stay apart


def outcome(label, score, threshold=SIM_THRESHOLD, verdict=None, replied=True):
    """One pair's outcome. `label` is the gold 'analog' / 'not_analog'. `replied` is False when
    the model returned nothing usable for this candidate."""
    if not replied:
        return "no_verdict"
    merged = counts_as_analog(score, threshold, verdict)
    is_analog = label == "analog"
    if merged:
        return "merged_correct" if is_analog else "false_merge"
    return "missed_match" if is_analog else "apart_correct"
