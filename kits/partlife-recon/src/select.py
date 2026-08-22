"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending thirteen fields x the whole
record pack is thirteen times the input tokens of sending each field the sections that could
possibly state it.

⚑ `Holding Location` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every pack in this
corpus says which bonded store or rack the component is physically sitting in; no field asks for
it, so the union of the mapped sections leaves it out and it is never sent. It is the one section a
reader can point at and say "that is what selection did" -- the rest of the saving is real but
invisible, because the sections that are sent would have been sent anyway.

⚑ `life_status` IS MAPPED TO THE TRAIL AND THE LIMITS, AND NOT TO THE TAG. That is a statement of
the rule rather than a saving. What the records substantiate is an arithmetic result over the
service record trail, the declared gap and the two published limits; the figures written on the
component's own tag are a CLAIM to be reconciled against that, never an input to it. The tag still
reaches the model -- it is two fields in its own right, and the union of every field's sections is
what gets sent -- so this mapping is not a filter that hides the decoy. It is the map of where the
answer actually lives.

⚑ AND `tag_agrees` IS MAPPED TO BOTH SIDES OF ITS OWN COMPARISON, for the same reason: it is the
one field whose whole job is to hold the tag and the trail up against each other.
"""

SECTION_HINTS = {
    "component_id": ["Component"],
    "part_reference": ["Part Reference"],
    "life_limit_hours": ["Published Life Limit"],
    "life_limit_cycles": ["Published Life Limit"],
    "tag_hours": ["Component Tag Figures"],
    "tag_cycles": ["Component Tag Figures"],
    "trail_hours": ["Service Record Trail", "Records Gap"],
    "trail_cycles": ["Service Record Trail", "Records Gap"],
    "record_gap": ["Records Gap", "Service Record Trail"],
    "disposition_requested": ["Disposition Requested"],
    "reviewer_note": ["Reviewer Note"],
    "tag_agrees": ["Component Tag Figures", "Service Record Trail", "Records Gap"],
    "life_status": ["Published Life Limit", "Service Record Trail", "Records Gap"],
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
