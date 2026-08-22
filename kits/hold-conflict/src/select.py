"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending twelve fields x the
whole record is twelve times the input tokens of sending each field the section that could
possibly state it.

⚑ `Custodian Office` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every disposition
review in this corpus names the office that holds the series; no field asks for it, so the union
of the mapped sections leaves it out and it is never sent. It is the one section a reader can
point at and say "that is what selection did" -- the rest of the saving is real but invisible,
because the sections that are sent would have been sent anyway.

⚑ `disposition_eligible` AND `binding_hold_id` ARE MAPPED TO THE FACTS THE RULE ACTUALLY USES, AND
NOT TO OFFICER NOTES. That is a statement of the rule rather than a saving. Whether a series may
be proposed for destruction is a derivation over a category, a project, a closed date, two expiry
dates and a hold registry; the records officer's own note is evidence of none of it. The note
still reaches the model -- it is a field in its own right, and the union of every field's sections
is what gets sent -- so this mapping is not a filter that hides the decoy. It is the map of where
the answer actually lives.
"""

SECTION_HINTS = {
    "series_id": ["Record Series"],
    "series_title": ["Series Title"],
    "record_category": ["Record Category"],
    "related_project": ["Related Project"],
    "record_closed": ["Record Closed"],
    "retention_code": ["Retention Schedule"],
    "retention_expires": ["Retention Expires"],
    "overlapping_expires": ["Overlapping Series"],
    "binding_hold_id": ["Record Category", "Related Project", "Record Closed", "Hold Registry"],
    "queue_status": ["Disposition Queue"],
    "officer_notes": ["Officer Notes"],
    "disposition_eligible": ["Record Category", "Related Project", "Record Closed",
                             "Retention Expires", "Overlapping Series", "Hold Registry"],
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
