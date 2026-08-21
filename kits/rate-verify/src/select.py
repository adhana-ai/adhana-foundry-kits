"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole record is ten times the input tokens of sending each field the section that could possibly
state it.

⚑ `Service Territory` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every account record
in this corpus states which division it belongs to; no field asks for it, so the union of the
mapped sections leaves it out and it is never sent. It is the one section a reader can point at
and say "that is what selection did" -- the rest of the saving is real but invisible, because the
sections that are sent would have been sent anyway.

⚑ `rate_correct` IS MAPPED TO THE FOUR FACTS THE RULE ACTUALLY USES, AND NOT TO ACCOUNT NOTES.
That is a statement of the rule rather than a saving. Rate correctness is a comparison between a
service class, a meter type, a usage figure and a demand reading; the billing rep's own note is
evidence of nothing about it. The note still reaches the model -- it is a field in its own right,
and the union of every field's sections is what gets sent -- so this mapping is not a filter that
hides the decoy. It is the map of where the answer actually lives.
"""

SECTION_HINTS = {
    "account_id": ["Account"],
    "service_class": ["Service Class"],
    "meter_type": ["Meter Type"],
    "billing_period": ["Billing Period"],
    "metered_usage_kwh": ["Metered Usage"],
    "peak_demand_kw": ["Peak Demand"],
    "applied_rate_code": ["Applied Rate Code"],
    "bill_status": ["Bill Status"],
    "account_notes": ["Account Notes"],
    "rate_correct": ["Service Class", "Meter Type", "Metered Usage", "Peak Demand",
                      "Applied Rate Code"],
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
