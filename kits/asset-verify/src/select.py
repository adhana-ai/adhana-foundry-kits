"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model.

WHY SELECT AT ALL, WHEN THESE STATEMENTS FIT IN A CONTEXT WINDOW. They do -- the largest is under
a thousand tokens -- so the real reason this node exists is the same lesson every extraction kit
here teaches: THE BILL IS DRIVEN BY THE CONTEXT, NOT BY THE QUESTION. Sending 10 fields x the
whole statement is ten times the input tokens of sending each field the section that could
possibly state it.

`SECTION_HINTS` is a per-corpus mapping and a forker pointed at a different statement layout will
have to change it; keeping it in one small dict makes that a five-minute edit. A field absent here
gets the whole document, which is slower and more expensive and always correct.
"""

SECTION_HINTS = {
    "account_holder": ["Statement Holder"],
    "institution": ["Institution"],
    "account_type": ["Account Type"],
    "period_start": ["Statement Period"],
    "period_end": ["Statement Period"],
    "beginning_balance": ["Account Summary"],
    "ending_balance": ["Account Summary"],
    "largest_deposit_amount": ["Deposits This Period"],
    "largest_deposit_description": ["Deposits This Period"],
    "deposit_documented": ["Deposits This Period"],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if s["name"] in want]
    return hit or list(secs)


def plan(secs, fields):
    """{field: [section names]} -- the whole selection, as data."""
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
