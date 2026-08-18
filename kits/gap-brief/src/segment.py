"""SEAM 1 -- the cut. Aligning three independently-maintained plan views for one line item and
deciding which gaps are material. Pure code, no model -- same discipline param-drift's
src/aggregate.py and data-reconcile's src/reconcile.py both keep: the thing that decides WHICH
gaps get itemized must be arithmetic on the three views themselves, never something the model
asserted.

⚑ ONE THRESHOLD, STATED ONCE, NOT FITTED TO THIS CORPUS AFTER THE FACT -- same honesty as
param-drift's DEVIATION_THRESHOLD_PCT. A percentage-only threshold was chosen over a percentage-OR-
dollar-floor because this corpus's line items span a wide value range ($15k-$220k); a flat dollar
floor would misclassify ordinary noise on a large item as material while missing a genuine gap on
a small one. See tools/build_corpus.py for how the corpus's own noise band (+-3%) and defect shift
band (18-42%) were sized to sit cleanly on either side of this line.

⚑ A MISSING VIEW IS MATERIAL BY ITSELF, REGARDLESS OF WHAT THE REMAINING TWO VIEWS SAY. The
guardrail this kit ships against ("missing-view caveat mandatory") is not a numeric comparison --
a line item one team never submitted a number for is worth a line in the brief even if the two
views that DO exist happen to agree, because "agree" from two of three sources is not the same
claim as "agree" from three.
"""
import statistics

VIEWS = ("demand_plan_usd", "supply_plan_usd", "financial_plan_usd")
MATERIALITY_PCT = 12.0          # (max view - min view) / median view, over the views that exist


def align(item):
    """One line item's plan-view record -> its gap facts. `item` carries the three view fields
    (any of which may be None -- not submitted this cycle) plus item_id/item_label.

    Returns a dict with the values actually present, the missing view's name (or None), the
    spread in dollars and in percent, and whether this item clears the materiality bar -- the
    ONLY inputs `pack.py` is allowed to itemize into the brief.
    """
    present = {v: item[v] for v in VIEWS if item.get(v) is not None}
    missing = [v for v in VIEWS if item.get(v) is None]
    missing_view = missing[0] if len(missing) == 1 else (missing[0] if missing else None)
    vals = list(present.values())
    delta_usd = round(max(vals) - min(vals), 2) if len(vals) >= 2 else 0.0
    denom = statistics.median(vals) if vals else None
    delta_pct = round(100.0 * delta_usd / denom, 1) if denom else None
    material = bool(missing_view) or (delta_pct is not None and delta_pct >= MATERIALITY_PCT)
    return {
        "item_id": item["item_id"],
        "item_label": item["item_label"],
        "views": {v: item.get(v) for v in VIEWS},
        "present": present,
        "missing_view": missing_view,
        "delta_usd": delta_usd,
        "delta_pct": delta_pct,
        "material": material,
    }


def align_cycle(cycle):
    """Every item in one cycle, in the cycle's own item order -- the deterministic per-line-item
    alignment the flow calls 'Segment'. No item is dropped or reordered here; `pack.py` is the
    station that decides which of these get itemized to the model."""
    return [align(it) for it in cycle["items"]]


def material_gaps(cycle):
    """The subset `pack.py` and the scorer both itemize -- material gaps only, cycle item order
    preserved so a run is reproducible byte-for-byte."""
    return [g for g in align_cycle(cycle) if g["material"]]
