"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending fourteen fields x
the whole case pack is fourteen times the input tokens of sending each field the section that
could possibly state it.

⚑ `Property And Shift` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every case in this
corpus states which floor and shift the cage was working; no field asks for it, so the union of the
mapped sections leaves it out and it never reaches the provider. It is the one section a reader can
point at and say "that is what selection did" -- the rest of the saving is real but invisible,
because the sections that are sent would have been sent anyway.

⚑ `defects_found` IS MAPPED TO THE FACTS THE RULEBOOK ACTUALLY READS, AND NOT TO `Preparer Note`.
That is a statement of the rule rather than a saving, and it is the map of this kit's decoy: the
preparer's note is prose written by the person whose work is being checked, and on this corpus it
often reads the opposite way from what the numbers say. A confident note on a defective filing and
an anxious one on a clean filing are both in here, in equal measure.

The note still reaches the model -- it is a field in its own right, and the union of every field's
sections is what gets sent -- so this mapping is not a filter that hides the decoy. It is the map
of where the answer actually lives.
"""

SECTION_HINTS = {
    "filing_id": ["Draft Filing"],
    "patron_record_id": ["Patron Record"],
    "gaming_day": ["Gaming Day"],
    "draft_direction": ["Direction Reported"],
    "draft_reported_total": ["Reported Total"],
    "log_qualifying_total": ["Gaming Day", "Direction Reported", "Cage Transaction Log",
                             "Other Patron Records In This Log",
                             "Patron Identification On The Draft"],
    "draft_window_applied": ["Window Applied"],
    "linked_record_id": ["Other Patron Records In This Log",
                         "Patron Identification On The Draft"],
    "draft_includes_linked_record": ["Transactions Included On The Draft",
                                     "Other Patron Records In This Log",
                                     "Cage Transaction Log"],
    "missing_identification_elements": ["Patron Identification On The Draft"],
    "identification_captured_on": ["Patron Identification On The Draft"],
    "miscoded_transaction_ids": ["Transactions Included On The Draft", "Cage Transaction Log"],
    "preparer_note": ["Preparer Note"],
    "defects_found": ["Gaming Day", "Direction Reported", "Window Applied", "Reported Total",
                      "Transactions Included On The Draft",
                      "Patron Identification On The Draft", "Cage Transaction Log",
                      "Other Patron Records In This Log"],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if s["name"] in want]
    return hit or list(secs)


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
