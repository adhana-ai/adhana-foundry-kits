"""The outcome vocabulary. Pure code, no model -- shared by the app, the baseline and the real run
so a verdict is graded the same way everywhere.

⚑ FIVE PRIMARY OUTCOMES, NEVER ONE ACCURACY NUMBER -- same discipline as ops-triage's five and
change-impact's seven. A single "accuracy" figure on a 45%-drift set hides which of two very
different mistakes it is made of: a MISSED_DRIFT is a parameter that stays wrong until someone
notices some other way; a FALSE_FLAG is a person's attention spent on a parameter that was fine.
Neither is free, and they are not the same cost.

    correct_flag    gold says drift, verdict says FLAG -- the parameter was surfaced.
    correct_hold    gold says no_drift, verdict says HOLD -- correctly left alone.
    false_flag      gold says no_drift, verdict says FLAG -- a review spent on nothing.
    missed_drift    gold says drift, verdict says HOLD -- a real mismatch, not surfaced.
    no_verdict      nothing usable came back from the model.

⚠︎ `no_verdict` MUST NOT COLLAPSE INTO `correct_hold`, SAME TRAP OPS-TRIAGE NAMES FOR ITS OWN
`no_verdict`. A model that returns nothing flags nothing, so a broken run looks exactly like a
calm set of parameters -- an excellent-looking false-flag rate hiding a total reliability failure.
Counted apart, excluded from both published rates.

⚑ VALUE AGREEMENT IS A SEPARATE AXIS FROM THE VERDICT, ON PURPOSE. Whether the proposed corrected
value agrees with what a historical analyst actually approved is only meaningful once the
parameter was correctly flagged in the first place -- `value_outcome` is therefore only ever
`value_agrees` or `value_disagrees` on a `correct_flag` row, and `None` everywhere else. The
corrected value itself is computed by `src/formulas.py` from the observed window alone, never
asserted by the model -- see its own header.
"""
OUTCOMES = ("correct_flag", "correct_hold", "false_flag", "missed_drift", "no_verdict")

MEANS = {
    "correct_flag": "a real mismatch, surfaced for review",
    "correct_hold": "no mismatch, correctly left alone",
    "false_flag": "a review spent on a parameter that was fine",
    "missed_drift": "a real mismatch that stayed hidden",
    "no_verdict": "nothing usable came back",
}

VALUE_OUTCOMES = ("value_agrees", "value_disagrees")

# ⚑ STATED ONCE, NOT FITTED TO THIS CORPUS. A proposed value is scored as agreeing with the gold
# corrected value when it is within 15% relative (or 0.5 absolute, whichever is larger, so a small
# gold value near zero is not held to an unreasonably tight relative bar).
VALUE_TOL_PCT = 15.0
VALUE_TOL_ABS_FLOOR = 0.5

FLAG, HOLD = "FLAG", "HOLD"


def outcome(gold_label, verdict, replied=True):
    """One parameter's primary outcome. `replied` is False when the model returned nothing usable."""
    if not replied or verdict not in (FLAG, HOLD):
        return "no_verdict"
    should = gold_label == "drift"
    if verdict == FLAG:
        return "correct_flag" if should else "false_flag"
    return "missed_drift" if should else "correct_hold"


def value_agrees(gold_value, proposed_value):
    """None when not applicable (no gold value, or nothing was computed); else a bool."""
    if gold_value is None or proposed_value is None:
        return None
    tol = max(VALUE_TOL_ABS_FLOOR, abs(gold_value) * VALUE_TOL_PCT / 100.0)
    return abs(proposed_value - gold_value) <= tol
