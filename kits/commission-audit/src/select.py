"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending fourteen fields x
the whole record is fourteen times the input tokens of sending each field the section that could
possibly state it.

⚑ `Property` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every claim record in this
corpus names the property the folio belongs to; no field asks for it, so the union of the mapped
sections leaves it out and it is never sent. It is the one section a reader can point at and say
"that is what selection did" -- the rest of the saving is real but invisible, because the sections
that are sent would have been sent anyway.

⚑ `claim_valid` IS MAPPED TO THE SEVEN FACTS THE RULE ACTUALLY USES, AND NOT TO THE REVIEWER NOTE.
That is a statement of the rule rather than a saving. Whether a commission claim is owed is a
computation over a booking source, a folio status, a room-revenue figure, a refund, a penalty, a
contracted percentage and the amount claimed; the property reviewer's own note is evidence of
nothing about it. The note still reaches the model -- it is a field in its own right, and the union
of every field's sections is what gets sent -- so this mapping is not a filter that hides the
decoy. It is the map of where the answer actually lives.

⚠︎ `Non-Room Charges` IS MAPPED TO ITS OWN FIELD AND TO NOTHING ELSE, INCLUDING `claim_valid`.
That is deliberate and it is the one mapping that could be argued the other way: taxes and fees
are the single most common thing a wrong claim puts into the base, so it is tempting to map them
to the verdict "so the model can see the trap". It must not be. The base is defined by what it
EXCLUDES, and a field mapped into the verdict's context is a field the verdict's own prompt is
inviting the model to use. The section still reaches the model as its own field's context; what
this refuses is to name it as evidence about validity.
"""

SECTION_HINTS = {
    "claim_id": ["Claim Line"],
    "confirmation_number": ["Confirmation Number"],
    "folio_status": ["Folio Status"],
    "booking_source": ["Booking Source"],
    "room_revenue_usd": ["Room Revenue"],
    "room_revenue_refunded_usd": ["Room Revenue Refunded"],
    "non_room_charges_usd": ["Non-Room Charges"],
    "penalty_charged_usd": ["Cancellation Penalty"],
    "contract_rate_pct": ["Contract Rate"],
    "claimed_commission_usd": ["Claimed Commission"],
    "already_commissioned": ["Previously Commissioned"],
    "invoice_status": ["Invoice Status"],
    "reviewer_note": ["Reviewer Note"],
    "claim_valid": ["Folio Status", "Booking Source", "Room Revenue",
                    "Room Revenue Refunded", "Cancellation Penalty", "Contract Rate",
                    "Claimed Commission", "Previously Commissioned"],
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
