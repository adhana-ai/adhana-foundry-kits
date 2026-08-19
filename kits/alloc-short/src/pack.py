"""SEAM 2 -- Pack. Deterministic assembly of one session's flagged events and its merchant notes
log into the context the model actually sees, ordered to a token budget. Pure code, no model --
same split gap-brief's src/pack.py makes between assembly and the one call that reads it.

⚠︎ ONLY FLAGGED EVENTS ARE ITEMIZED. A clean event is a shortage the written policy already
resolved without a review -- sending it to the model would burn tokens on nothing to explain and
would let a model 'find' a conflict src/allocate.py already ruled out. The itemizing decision
belongs to code, once, before the model ever sees an event.

⚠︎ THE NOTES LOG IS SENT WHOLE, NEVER PRE-FILTERED BY EVENT. Pre-selecting 'the two notes that
explain this event' for the model would hand it the answer and turn cause-tag agreement into a
copy check -- same discipline gap-brief's src/pack.py states for its own notes log.

⚠︎ trade_area_tier NEVER LEAVES src/allocate.py'S OUTPUT INTO THE PACK. It is not itemized here
either, for the same reason it is not a parameter of allocate() -- the model drafting the review
brief never sees it, so it cannot even accidentally reason from it.
"""
MAX_NOTES = 40
MAX_EVENTS = 20


def pack(session, notes, flagged):
    """`flagged` is already the flagged-only list from src/allocate.py::flagged_events. Returns
    the packed dict the prompt is built from, plus how much of the budget it used."""
    kept = flagged[:MAX_EVENTS]
    kept_notes = list(notes)[:MAX_NOTES]
    packed = {
        "session_id": session["session_id"],
        "region": session["region"],
        "week": session["week"],
        "events": [
            {
                "event_id": fx["event_id"],
                "sku": fx["sku"],
                "available_units": fx["available_units"],
                "total_ask": fx["total_ask"],
                "promo_protected": fx["promo_protected"],
                "customer_protected": fx["customer_protected"],
                "floor_breach_stores": fx["floor_breach"],
                "per_store": [
                    {"store_id": p["store_id"], "ask_units": p["ask_units"],
                     "allocated_units": p["allocated_units"]}
                    for p in fx["per_store"]
                ],
            }
            for fx in kept
        ],
        "notes": kept_notes,
    }
    return packed, {
        "events_total": len(flagged), "events_packed": len(kept),
        "notes_total": len(notes), "notes_packed": len(kept_notes),
        "truncated": len(kept) < len(flagged) or len(kept_notes) < len(notes),
    }
