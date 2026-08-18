"""Draft the starting forecast from a request's like-item set. Pure code, no model.

⚠︎ THE MODEL NEVER COMPUTES THE FORECAST NUMBER -- same discipline precedent-match's lift.py and
change-impact's impact.py state about their own downstream figures. The model's whole job
(src/prompt.py) is to decide which candidates are genuine like items; once that set exists, the
recommended starting forecast is arithmetic on numbers already sitting in the corpus (each history
item's own recorded `wk13_units_per_store`), never something the model asserted about its own
answer. A drafted forecast is therefore never worse than the like-item selection that produced it,
and never independently wrong on its own account.

⚑ WHY A MEAN, NOT A REGRESSION. This kit's whole point is measuring whether the LIKE-ITEM
SELECTION is right; a fancier aggregate over the selected set would let a smarter-looking formula
quietly cover for a bad selection, and nobody could tell which one moved the published number.
Mean of the selected set's wk13_units_per_store is the simplest honest aggregate there is.

⚑ MIN_LIKE_ITEMS_REQUIRED IS A JUDGEMENT, STATED ONCE, NOT FITTED TO THIS CORPUS'S NUMBERS. Below
it, a draft is not issued at all -- one or zero comparables is not a basis for a number a planner
will act on, it is a basis for asking a person to look. There is no setting that is simply
correct: raise it and more requests get no draft even when the ones found were solid; lower it and
a single coincidental comparable can carry a published estimate on its own.
"""
MIN_LIKE_ITEMS_REQUIRED = 2

# A tight spread across the selected comparables is worth naming — same discipline
# precedent-match's lift.py applies to a percentage spread, applied here to a units-per-store
# spread instead.
TIGHT_SPREAD_UNITS = 6.0
WIDE_SPREAD_UNITS = 12.0


def draft(like_items):
    """`like_items` is the list of history-item dicts already decided LIKE_ITEM for one request
    (src/decide.py). Returns the recommendation, or the explicit escalate state -- never a number
    computed from fewer comparables than the policy requires."""
    n = len(like_items)
    if n < MIN_LIKE_ITEMS_REQUIRED:
        return {"decision": "insufficient_comps", "n_like_items": n,
                "recommended_wk13_units": None, "wk13_low": None, "wk13_high": None,
                "confidence": None,
                "why": "fewer than %d confirmed like items (%d found) -- a person should look, "
                       "not a formula" % (MIN_LIKE_ITEMS_REQUIRED, n)}

    vals = [e["wk13_units_per_store"] for e in like_items]
    mean = round(sum(vals) / n, 1)
    lo, hi = round(min(vals), 1), round(max(vals), 1)
    spread = round(hi - lo, 1)
    if n >= 4 and spread <= TIGHT_SPREAD_UNITS:
        conf = "high"
    elif n >= MIN_LIKE_ITEMS_REQUIRED and spread <= WIDE_SPREAD_UNITS:
        conf = "medium"
    else:
        conf = "low"
    return {"decision": "draft_ready", "n_like_items": n, "recommended_wk13_units": mean,
            "wk13_low": lo, "wk13_high": hi, "spread_units": spread, "confidence": conf,
            "why": "mean of %d confirmed like items, range %.1f-%.1f units/store/wk"
                   % (n, lo, hi)}


def tally(drafts):
    """Counts of draft_ready vs insufficient_comps, for the report. Pure arithmetic."""
    c = {"draft_ready": 0, "insufficient_comps": 0}
    for d in drafts:
        c[d["decision"]] = c.get(d["decision"], 0) + 1
    total = sum(c.values())
    return {"counts": c, "total": total,
            "insufficient_pct": (round(100.0 * c.get("insufficient_comps", 0) / total, 1)
                                 if total else None)}
