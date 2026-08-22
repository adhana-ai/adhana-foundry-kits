"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending eleven fields x the
whole record is eleven times the input tokens of sending each field the section that could possibly
state it.

⚑ `Rating Domain` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every reconciliation
record in this corpus states which mediation partition it came out of; no field asks for it, so the
union of the mapped sections leaves it out and it is never sent. It is the one section a reader can
point at and say "that is what selection did" -- the rest of the saving is real but invisible,
because the sections that are sent would have been sent anyway.

⚑ `Duplicate Suspects` IS DELIBERATELY MAPPED IN, AND THAT IS NOT A CONTRADICTION. Selection is
not a filter that hides the decoys -- it is the map of where the answer lives. The suspect figure
is the louder of the two duplicate numbers and it is the one this corpus is built to see a reader
reach for, so removing it from the prompt would measure a kit that had already solved the problem
for the model. It goes in; the rule says which of the two to use; and 44 of the 55 records disagree
between them, so the choice is measured rather than assumed.

⚑ `variance_cause` IS MAPPED TO THE FIVE QUANTITIES AND THE SERVICE TYPE, NOT TO THE ANALYST NOTE.
That is a statement of the rule rather than a saving. The cause of a variance is arithmetic over
what mediation produced and what the invoice charged; the analyst's own note is evidence of nothing
about it. The note still reaches the model -- it is a field in its own right, and the union of every
field's sections is what gets sent -- so this mapping does not hide the decoy either.
"""

SECTION_HINTS = {
    "line_id": ["Invoice Line"],
    "service_type": ["Service Type"],
    "billing_period": ["Billing Period"],
    "mediated_quantity": ["Mediated Usage"],
    "invoiced_quantity": ["Invoiced Quantity"],
    "unrated_quantity": ["Unrated Usage"],
    "prior_period_quantity": ["Prior Period Usage"],
    "confirmed_duplicate_quantity": ["Confirmed Duplicates"],
    "invoice_status": ["Invoice Status"],
    "analyst_note": ["Analyst Note"],
    "variance_cause": ["Service Type", "Mediated Usage", "Invoiced Quantity", "Unrated Usage",
                       "Prior Period Usage", "Duplicate Suspects", "Confirmed Duplicates"],
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
