"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole file is ten times the input tokens of sending each field the section that could possibly
state it. THE BILL IS DRIVEN BY THE CONTEXT, NOT BY THE QUESTION.
"""

SECTION_HINTS = {
    "provider_name": ["Provider"],
    "npi": ["NPI"],
    "license_number": ["License Number"],
    "provider_type": ["Provider Type"],
    "license_expiration_date": ["License Expiration Date"],
    "credentialing_effective_date": ["Credentialing Effective Date"],
    "psv_check_date": ["PSV Check Date"],
    "psv_source": ["PSV Source"],
    "psv_raw_finding": ["PSV Finding"],
    "sanction_or_adverse_action_found": ["PSV Finding"],
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
