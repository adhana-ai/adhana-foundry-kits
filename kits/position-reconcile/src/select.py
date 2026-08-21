"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole record is ten times the input tokens of sending each field the section that could possibly
state it.
"""

SECTION_HINTS = {
    "account_id": ["Account"],
    "security_id": ["Security"],
    "security_name": ["Security"],
    "as_of_date": ["As Of Date"],
    "internal_quantity": ["Internal Quantity"],
    "custodian_quantity": ["Custodian Quantity"],
    "break_age_days": ["Break Age (Business Days)"],
    "assigned_analyst": ["Assigned Analyst"],
    "reconciling_memo": ["Reconciling Memo"],
    "is_true_break": ["Reconciling Memo"],
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
