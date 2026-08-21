"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole record is ten times the input tokens of sending each field the section that could possibly
state it.

⚑ `Receiving Site` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every proof-of-delivery
record in this corpus states where it was dropped; no field asks for it, so the union of the
mapped sections leaves it out and it is never sent. It is the one section a reader can point at
and say "that is what selection did" -- the rest of the saving is real but invisible, because the
sections that are sent would have been sent anyway.

⚑ `delivery_complete` IS MAPPED TO THE TWO QUANTITY SECTIONS AND THE CONDITION CODE, AND NOT TO
THE DRIVER'S EXCEPTION NOTE. That is a statement of the rule rather than a saving. Completeness is
a comparison between two counts and one coded field; the driver's account of the stop is evidence
of nothing about it. The note still reaches the model -- it is a field in its own right, and the
union of every field's sections is what gets sent -- so this mapping is not a filter that hides
the decoy. It is the map of where the answer actually lives.
"""

SECTION_HINTS = {
    "shipment_id": ["Shipment"],
    "carrier_name": ["Carrier"],
    "delivery_date": ["Delivery Date"],
    "ordered_quantity": ["Ordered Quantity"],
    "delivered_quantity": ["Delivered Quantity"],
    "condition_code": ["Condition Code"],
    "recipient_signature_present": ["Recipient Signature On File"],
    "driver_exception_note": ["Driver Exception Note"],
    "pod_timestamp": ["POD Timestamp"],
    "delivery_complete": ["Ordered Quantity", "Delivered Quantity", "Condition Code"],
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
