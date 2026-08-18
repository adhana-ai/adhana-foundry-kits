"""The downstream impact of accepting a requested change, and the threshold that decides whether
it auto-accepts. Pure code, no model -- the same discipline data-match's decide.py states for its
own merge threshold: the number a reader trusts must be arithmetic on a record and an extracted
value, never something the model asserted about its own answer.

⚑ WHY THE MODEL NEVER COMPUTES THE IMPACT ITSELF. Asking a model for "the cost impact" invites it
to do arithmetic in its head and round confidently to a wrong number -- the same failure mode
docs-comply's false-clean rows show for verdicts. This module takes only the RECORD (known, on
disk) and the EXTRACTED CHANGE (change_type + new_value, the two things a model or a baseline
actually has to get right) and computes the rest deterministically. Impact accuracy is therefore
never better than match+extraction accuracy, and never worse either -- it is not a third thing that
can independently go wrong.

FIVE CHANGE TYPES, FIVE FORMULAS:

    expedite       ship date pulled forward. Costs a per-day, per-unit rush fee.
    delay          ship date pushed back. Costs nothing UNLESS it pushes past a live promotion's
                   end date, in which case the whole promotion value is lost -- not a per-day fee,
                   a cliff.
    cancel         the line is pulled entirely. Frees the committed spend (qty x unit_cost),
                   reported as a negative cost_impact_usd -- money not spent, not money lost.
    qty_change     the quantity changes. Cost moves by (new_qty - qty) x unit_cost.
    price_change   the unit cost is renegotiated. Cost moves by (new_cost - unit_cost) x qty.

⚑ THE MATERIALITY THRESHOLD IS THE PRODUCT, NOT A TUNING KNOB -- same claim data-match's decide.py
makes about its merge threshold, for the same reason. Below it, a change auto-accepts with no human
in the loop; above it, or when a live promotion is missed outright, it escalates. There is no
setting that is simply correct: raise it and a human sees fewer changes but a costlier one might
slip through un-escalated; lower it and every trivial expedite request lands in a queue. The number
below is a judgement, stated once, not fitted to this corpus's numbers after the fact.
"""
import datetime

EXPEDITE_RATE_PER_UNIT_DAY = 0.35     # invented rush-fee rate: $/unit/day pulled forward

# ⚑ STATED BEFORE ANY EVAL RUN, NOT TUNED TO IT. Escalate if the dollar swing exceeds this, OR if
# a delay pushes shipment past a live promotion's end date -- the promo miss escalates regardless
# of its dollar size, because a missed promotion is a binary event a human should always see once.
MATERIALITY_THRESHOLD_USD = 250.0


def _d(s):
    return datetime.date.fromisoformat(s)


def compute(record, change_type, new_value):
    """The record and the extracted change in, the impact dict out. `new_value` is exactly what
    src/prompt.py::parse() or evals/baseline.py extracted -- this function does not know or care
    which one produced it."""
    qty, unit_cost = record["qty"], record["unit_cost"]
    ship_date = _d(record["ship_date"])

    if change_type == "expedite":
        if not new_value or not new_value.get("new_ship_date"):
            return None
        new_date = _d(new_value["new_ship_date"])
        pulled_days = (ship_date - new_date).days       # positive = pulled forward (earlier)
        cost = round(EXPEDITE_RATE_PER_UNIT_DAY * qty * max(0, pulled_days), 2)
        return {"in_stock_date_delta_days": -pulled_days, "cost_impact_usd": cost,
               "promo_missed": False}

    if change_type == "delay":
        if not new_value or not new_value.get("new_ship_date"):
            return None
        new_date = _d(new_value["new_ship_date"])
        pushed_days = (new_date - ship_date).days        # positive = later
        promo_end = record.get("promo_end")
        promo_missed = bool(promo_end and new_date > _d(promo_end))
        cost = round(record["promo_value_usd"], 2) if (promo_missed and record.get("promo_value_usd")) else 0.0
        return {"in_stock_date_delta_days": pushed_days, "cost_impact_usd": cost,
               "promo_missed": promo_missed}

    if change_type == "cancel":
        return {"in_stock_date_delta_days": None,
               "cost_impact_usd": round(-(qty * unit_cost), 2), "promo_missed": False,
               "units_removed": qty}

    if change_type == "qty_change":
        if not new_value or "new_qty" not in (new_value or {}):
            return None
        new_qty = new_value["new_qty"]
        delta_qty = new_qty - qty
        return {"in_stock_date_delta_days": 0, "cost_impact_usd": round(delta_qty * unit_cost, 2),
               "promo_missed": False, "delta_qty": delta_qty}

    if change_type == "price_change":
        if not new_value or "new_unit_cost" not in (new_value or {}):
            return None
        new_cost = new_value["new_unit_cost"]
        delta_price = round(new_cost - unit_cost, 4)
        return {"in_stock_date_delta_days": 0, "cost_impact_usd": round(delta_price * qty, 2),
               "promo_missed": False, "delta_price_usd": delta_price}

    return None       # unknown change_type -- never guessed at


def decide(impact):
    """auto_accept or escalate. None impact (nothing computable) always escalates -- a change that
    could not even be priced is not a candidate for auto-accept."""
    if impact is None:
        return "escalate"
    if impact.get("promo_missed"):
        return "escalate"
    cost = impact.get("cost_impact_usd")
    if cost is None:
        return "escalate"
    return "escalate" if abs(cost) > MATERIALITY_THRESHOLD_USD else "auto_accept"


def tally(rows):
    """Counts of auto_accept vs escalate, for the report. Pure arithmetic, no model anywhere."""
    c = {"auto_accept": 0, "escalate": 0}
    for r in rows:
        c[r] = c.get(r, 0) + 1
    total = sum(c.values())
    return {"counts": c, "total": total,
           "escalate_pct": round(100.0 * c.get("escalate", 0) / total, 1) if total else None}
