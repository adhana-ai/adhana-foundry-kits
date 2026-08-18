"""Draft the lift recommendation from a request's analog set. Pure code, no model.

⚠︎ THE MODEL NEVER COMPUTES THE LIFT NUMBER -- same discipline change-impact's impact.py states
about its own downstream dollar figure. The model's whole job (src/prompt.py) is to decide which
candidates are genuine analogs; once that set exists, the recommended lift is arithmetic on numbers
already sitting in the corpus (each history event's own recorded `actual_lift_pct`), never something
the model asserted about its own answer. A drafted lift is therefore never worse than the analog
selection that produced it, and never independently wrong on its own account.

⚑ WHY A MEAN, NOT A REGRESSION. This kit's whole point is measuring whether the ANALOG SELECTION is
right; a fancier aggregate over the selected set would let a smarter-looking formula quietly cover
for a bad selection, and nobody could tell which one moved the published number. Mean of the
selected set's actual_lift_pct is the simplest honest aggregate there is.

⚑ MIN_ANALOGS_REQUIRED IS A JUDGEMENT, STATED ONCE, NOT FITTED TO THIS CORPUS'S NUMBERS. Below it,
a draft is not issued at all -- one or zero precedents is not a basis for a number a planner will
act on, it is a basis for asking a person to look. There is no setting that is simply correct: raise
it and more requests get no draft even when the ones found were solid; lower it and a single
coincidental analog can carry a published estimate on its own.
"""
MIN_ANALOGS_REQUIRED = 2

# A tight spread across the selected precedents is worth naming — same discipline data-reconcile's
# materiality band applies to a dollar figure, applied here to a percentage spread instead.
TIGHT_SPREAD_PCT = 15.0
WIDE_SPREAD_PCT = 25.0


def draft(analog_events):
    """`analog_events` is the list of history-event dicts already decided ANALOG for one request
    (src/decide.py). Returns the recommendation, or the explicit escalate state -- never a number
    computed from fewer precedents than the policy requires."""
    n = len(analog_events)
    if n < MIN_ANALOGS_REQUIRED:
        return {"decision": "insufficient_precedent", "n_analogs": n,
                "recommended_lift_pct": None, "lift_low_pct": None, "lift_high_pct": None,
                "confidence": None,
                "why": "fewer than %d confirmed analogs (%d found) -- a person should look, not "
                       "a formula" % (MIN_ANALOGS_REQUIRED, n)}

    lifts = [e["actual_lift_pct"] for e in analog_events]
    mean = round(sum(lifts) / n, 1)
    lo, hi = round(min(lifts), 1), round(max(lifts), 1)
    spread = round(hi - lo, 1)
    if n >= 4 and spread <= TIGHT_SPREAD_PCT:
        conf = "high"
    elif n >= MIN_ANALOGS_REQUIRED and spread <= WIDE_SPREAD_PCT:
        conf = "medium"
    else:
        conf = "low"
    return {"decision": "draft_ready", "n_analogs": n, "recommended_lift_pct": mean,
            "lift_low_pct": lo, "lift_high_pct": hi, "spread_pct": spread, "confidence": conf,
            "why": "mean of %d confirmed analogs, range %.1f-%.1f pts" % (n, lo, hi)}


def tally(drafts):
    """Counts of draft_ready vs insufficient_precedent, for the report. Pure arithmetic."""
    c = {"draft_ready": 0, "insufficient_precedent": 0}
    for d in drafts:
        c[d["decision"]] = c.get(d["decision"], 0) + 1
    total = sum(c.values())
    return {"counts": c, "total": total,
            "insufficient_pct": (round(100.0 * c.get("insufficient_precedent", 0) / total, 1)
                                 if total else None)}
