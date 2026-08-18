"""SEAM 2 -- Pack. Deterministic assembly of one review batch's material exceptions and its
merchant notes log into the context the model actually sees, ordered to a token budget. Pure code,
no model -- same split gap-brief's src/pack.py and docs-summarise's src/pack.py both make between
assembly and the one call that reads the assembly.

⚠︎ ONLY MATERIAL EXCEPTIONS ARE ITEMIZED. A clean item is a forecast the statistical baseline
already got right; sending it to the model would burn tokens on nothing to review and would let a
model "detect" an exception that src/segment.py already ruled out -- the itemizing decision belongs
to code, once, before the model ever sees a number.

⚠︎ THE NOTES LOG IS SENT WHOLE, NEVER PRE-FILTERED BY ITEM. Pre-selecting "the two notes that
explain this item" for the model would hand it the answer and turn cause-tag agreement into a copy
check. The model has to do the same correlation a human planner does: read every line, decide which
(if any) explain which item.
"""
MAX_NOTES = 40                  # a corpus batch carries far fewer; this is the stated ceiling
MAX_ITEMS = 20                  # ditto -- named so a bigger corpus doesn't silently balloon a call


def pack(batch, notes, exceptions):
    """`exceptions` is already the material-only list from src/segment.py::material_exceptions.
    Returns the packed dict the prompt is built from, plus how much of the budget it used -- so
    Cost can report packing cost as $0 and Architecture can show the seam actually ran."""
    kept = exceptions[:MAX_ITEMS]
    kept_notes = list(notes)[:MAX_NOTES]
    packed = {
        "batch_id": batch["batch_id"],
        "region": batch["region"],
        "review_week": batch["review_week"],
        "items": [
            {
                "item_id": f["item_id"],
                "item_label": f["item_label"],
                "location": f["location"],
                "forecast_units": f["forecast_units"],
                "actual_pos_units": f["actual_pos_units"],
                "lost_sales_oos_flag": f["lost_sales_oos_flag"],
                "promo_flag": f["promo_flag"],
                "prior_year_analog_units": f["prior_year_analog_units"],
                "unreliable_evidence": f["unreliable_evidence"],
                "delta_units": f["delta_units"],
                "delta_pct": f["delta_pct"],
            }
            for f in kept
        ],
        "notes": kept_notes,
    }
    return packed, {
        "items_total": len(exceptions), "items_packed": len(kept),
        "notes_total": len(notes), "notes_packed": len(kept_notes),
        "truncated": len(kept) < len(exceptions) or len(kept_notes) < len(notes),
    }
