"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole certificate is ten times the input tokens of sending each field the section that could
possibly state it.

⚑ `conforms_to_spec` IS MAPPED TO THE THREE NUMERIC SECTIONS AND NOT TO THE DISPOSITION NOTE, and
that is a statement of the rule rather than a saving. The verdict is a comparison between the
measured result and the two limits; the analyst's note is evidence of nothing about it. The note
still reaches the model -- it is a field in its own right, and the union of every field's sections
is what gets sent -- so this mapping is not a filter that hides the decoy. It is the map of where
the answer actually lives.
"""

SECTION_HINTS = {
    "batch_id": ["Batch"],
    "product_name": ["Product"],
    "test_parameter": ["Test Parameter"],
    "measured_value": ["Measured Result"],
    "unit": ["Measured Result"],
    "spec_lower_limit": ["Specification Lower Limit"],
    "spec_upper_limit": ["Specification Upper Limit"],
    "analyst_disposition_note": ["Analyst Disposition Note"],
    "test_date": ["Test Date"],
    "conforms_to_spec": ["Measured Result", "Specification Lower Limit",
                         "Specification Upper Limit"],
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
