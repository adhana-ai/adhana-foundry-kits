"""SEAM 1 -- the cut. Deciding which flagged item/location exceptions in a review batch are
MATERIAL. Pure code, no model -- same discipline gap-brief's src/segment.py and param-drift's
src/aggregate.py both keep: the thing that decides WHICH exceptions get itemized to the model must
be arithmetic on the evidence itself, never something the model asserted.

⚑ ONE THRESHOLD, STATED ONCE, NOT FITTED TO THIS CORPUS AFTER THE FACT -- same honesty as
gap-brief's MATERIALITY_PCT and param-drift's DEVIATION_THRESHOLD_PCT. A percentage-only threshold
was chosen because ordinary statistical-forecast noise scales with volume; a flat unit floor would
misclassify noise on a high-volume item as material while missing a genuine exception on a
low-volume one. See tools/build_corpus.py for how the corpus's own noise band (+-5%) and defect
shift band (22-48%) were sized to sit cleanly on either side of this line.

⚑ AN ITEM WHOSE RECENT POS IS UNRELIABLE IS MATERIAL BY ITSELF, REGARDLESS OF THE DELTA. The
guardrail this kit ships against ("unreliable-evidence caveat mandatory") is not a numeric
comparison -- when the POS feed for an item/location is flagged unreliable (a register/data outage),
there is no trustworthy actual to compare against the statistical forecast at all, and that absence
is itself worth a line in the packet even if no percentage was ever computed.
"""

MATERIALITY_PCT = 18.0          # abs(actual - forecast) / forecast, in percent


def flag(item):
    """One flagged item/location's evidence record -> its exception facts. `item` carries
    forecast_units, actual_pos_units (may be None -- POS unreliable this week), lost_sales_oos_flag
    and promo_flag (evidence signals, not materiality inputs), and prior_year_analog_units.

    Returns a dict with the delta in units and percent, whether the evidence itself is unreliable,
    and whether this item clears the materiality bar -- the ONLY inputs `pack.py` is allowed to
    itemize into the review packet.
    """
    forecast = item["forecast_units"]
    actual = item.get("actual_pos_units")
    unreliable_evidence = actual is None
    if unreliable_evidence:
        delta_units = None
        delta_pct = None
    else:
        delta_units = round(actual - forecast, 1)
        delta_pct = round(100.0 * delta_units / forecast, 1) if forecast else None
    material = unreliable_evidence or (delta_pct is not None and abs(delta_pct) >= MATERIALITY_PCT)
    return {
        "item_id": item["item_id"],
        "item_label": item["item_label"],
        "location": item.get("location"),
        "forecast_units": forecast,
        "actual_pos_units": actual,
        "lost_sales_oos_flag": bool(item.get("lost_sales_oos_flag")),
        "promo_flag": bool(item.get("promo_flag")),
        "prior_year_analog_units": item.get("prior_year_analog_units"),
        "unreliable_evidence": unreliable_evidence,
        "delta_units": delta_units,
        "delta_pct": delta_pct,
        "material": material,
    }


def flag_batch(batch):
    """Every item in one review batch, in the batch's own item order -- the deterministic
    per-item flagging the flow calls 'Segment'. No item is dropped or reordered here; `pack.py` is
    the station that decides which of these get itemized to the model."""
    return [flag(it) for it in batch["items"]]


def material_exceptions(batch):
    """The subset `pack.py` and the scorer both itemize -- material exceptions only, batch item
    order preserved so a run is reproducible byte-for-byte."""
    return [f for f in flag_batch(batch) if f["material"]]
