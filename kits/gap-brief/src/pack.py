"""SEAM 2 -- Pack. Deterministic assembly of one cycle's material gaps and its notes log into the
context the model actually sees, ordered to a token budget. Pure code, no model -- same split
docs-summarise's src/pack.py makes between assembly and the one call that reads the assembly.

⚠︎ ONLY MATERIAL GAPS ARE ITEMIZED. A clean item is real work the three teams already agree on;
sending it to the model would burn tokens on nothing to reconcile and would let a model "detect"
a gap that src/segment.py already ruled out -- the itemizing decision belongs to code, once,
before the model ever sees a number.

⚠︎ THE NOTES LOG IS SENT WHOLE, NEVER PRE-FILTERED BY ITEM. Pre-selecting "the two notes that
explain this item" for the model would hand it the answer and turn cause-tag agreement into a
copy check. The model has to do the same correlation a human reader does: read every line, decide
which (if any) explain which item.
"""
MAX_NOTES = 40                  # a corpus cycle carries far fewer; this is the stated ceiling
MAX_GAPS = 20                   # ditto -- named so a bigger corpus doesn't silently balloon a call


def pack(cycle, notes, gaps):
    """`gaps` is already the material-only list from src/segment.py::material_gaps. Returns the
    packed dict the prompt is built from, plus how much of the budget it used -- so Cost can
    report packing cost as $0 and Architecture can show the seam actually ran."""
    kept_gaps = gaps[:MAX_GAPS]
    kept_notes = list(notes)[:MAX_NOTES]
    packed = {
        "cycle_id": cycle["cycle_id"],
        "business_unit": cycle["business_unit"],
        "period": cycle["period"],
        "gaps": [
            {
                "item_id": g["item_id"],
                "item_label": g["item_label"],
                "views": g["views"],
                "missing_view": g["missing_view"],
                "delta_usd": g["delta_usd"],
                "delta_pct": g["delta_pct"],
            }
            for g in kept_gaps
        ],
        "notes": kept_notes,
    }
    return packed, {
        "gaps_total": len(gaps), "gaps_packed": len(kept_gaps),
        "notes_total": len(notes), "notes_packed": len(kept_notes),
        "truncated": len(kept_gaps) < len(gaps) or len(kept_notes) < len(notes),
    }
