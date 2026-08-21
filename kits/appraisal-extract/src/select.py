"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model.

`extraordinary_assumption_present`/`_text` are the one field pair sent THREE sections rather than
one, on purpose: this kit's whole guardrail is that an assumption can be stated under a dedicated
heading OR embedded in Scope of Work or Comments prose, and the model has to check all three to
answer honestly. Narrowing the hint to just the labelled heading would defeat the corpus's own
planted ambiguity before the model ever sees it.
"""

SECTION_HINTS = {
    "property_address": ["Subject Property"],
    "appraiser_name": ["Appraiser"],
    "effective_date": ["Effective Date"],
    "report_date": ["Report Date"],
    "approach_used": ["Valuation Approach"],
    "reconciled_value": ["Reconciliation"],
    "gross_living_area_sqft": ["Improvements"],
    "comparable_count": ["Improvements"],
    "extraordinary_assumption_present": ["Extraordinary Assumptions", "Scope of Work", "Comments"],
    "extraordinary_assumption_text": ["Extraordinary Assumptions", "Scope of Work", "Comments"],
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
