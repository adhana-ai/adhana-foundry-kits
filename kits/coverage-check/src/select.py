"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending thirteen fields x the whole
record is thirteen times the input tokens of sending each field the section that could possibly
state it.

⚑ `Servicing Dealer` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every claim in this
corpus names the dealership that filed it; no field asks for it, so the union of the mapped
sections leaves it out and it is never sent. It is the one section a reader can point at and say
"that is what selection did" -- the rest of the saving is real but invisible, because the sections
that are sent would have been sent anyway.

⚑ `covered` IS MAPPED TO THE SIX FACTS THE RULE ACTUALLY READS, AND `Cause Code` IS NOT ONE OF
THEM. That is a statement of the rule rather than a saving. Coverage is decided by the plan, the
two dates, the odometer, the failed component, the claimed labor operation and what the narrative
DESCRIBES -- the coded cause is the dealer's own classification and is evidence of nothing.

⚠︎ THE TECHNICIAN NARRATIVE IS MAPPED, DELIBERATELY, AND THIS IS NOT A FILTER THAT HIDES THE DECOY.
The narrative reaches the model on every call: it is a field in its own right (copied verbatim), it
is where `narrative_finding` is read from, and it carries the closing opinion this kit exists to
test resistance to. Selection is the map of where each answer lives, not a way of protecting the
model from the hard part of the record.
"""

SECTION_HINTS = {
    "claim_id": ["Claim"],
    "vehicle_id": ["Vehicle"],
    "coverage_plan": ["Coverage Plan"],
    "in_service_date": ["In-Service Date"],
    "repair_date": ["Repair Date"],
    "months_in_service": ["In-Service Date", "Repair Date"],
    "odometer_miles": ["Odometer"],
    "failed_component": ["Failed Component"],
    "claimed_labor_op": ["Claimed Labor Operation"],
    "cause_code": ["Cause Code"],
    "claim_status": ["Claim Status"],
    "technician_narrative": ["Technician Narrative"],
    "narrative_finding": ["Technician Narrative"],
    "covered": ["Coverage Plan", "In-Service Date", "Repair Date", "Odometer",
                "Failed Component", "Claimed Labor Operation", "Technician Narrative"],
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
