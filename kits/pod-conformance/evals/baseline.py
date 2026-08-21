"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `delivery_complete` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the driver's exception note and nothing else: a note carrying one of a
fixed list of worried-sounding phrases ("sorry", "apolog", "not happy", "flagging", "mess",
"rushed", "chaotic", "ran late") means "no", and anything else means "yes". That is precisely the
shortcut the prompt's rules forbid -- deciding completeness from prose instead of from the two
counts and the condition code.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
comparison is one line, and the baseline already regexes both quantities and the condition code
out of the document. A rules baseline that did the comparison would score 100 pct on this corpus
and tell you nothing about the model -- so the floor is deliberately the SHORTCUT, not the rule,
and the gap it opens is the gap between reading prose and comparing two numbers.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived `delivery_complete`
produces a tone-derived review flag: the floor gets the signature right by regex every time and
the completeness wrong on the planted records, and the flag inherits the error. That is worth
publishing rather than hiding -- a business-condition guardrail is only ever as good as the field
it reads, which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# ⚠︎ "flagging" WAS IN THIS LIST AND IS NOT ANY MORE, AND THE REASON IS WORTH THE THREE LINES.
# One of the corpus's breezy notes ends "nothing worth flagging" -- a NEGATION -- and a substring
# match fired on it, so four records were classified worried on a note that says the opposite. Two
# of those four were records the corpus had deliberately made ambiguous, so the bug flipped them
# back to the RIGHT answer for the wrong reason, and the floor's published error count came out
# 24 where the corpus plants 22. A floor that is wrong in two directions at once is not measuring
# register, it is measuring its own regex, and the gap it opens against a model stops meaning what
# the page says it means.
#
# The fix is the list, not the corpus: "Bit of a mess at the bay. Flagging it..." is still caught
# on "mess", so the anxious register is fully covered without the word that negates.
# evals/check_labels.py now asserts, for free and before any run, that every note in the corpus
# classifies to the register it was written as -- see `floor is a faithful register detector`.
WORRIED_KEYWORDS = ("sorry", "apolog", "not happy", "mess", "rushed", "chaotic", "ran late")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '120 units' into 120. Returns None when the line states no number."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+)\b", s)
    return int(m.group(1)) if m else None


def extract_one(text, fields):
    shipment_id = _section(text, "Shipment")
    carrier_name = _section(text, "Carrier")
    delivery_date = _section(text, "Delivery Date")
    pod_timestamp = _section(text, "POD Timestamp")
    ordered_quantity = _units(_section(text, "Ordered Quantity"))
    delivered_quantity = _units(_section(text, "Delivered Quantity"))
    condition_code = _section(text, "Condition Code")
    signature = _section(text, "Recipient Signature On File")
    note = _section(text, "Driver Exception Note")

    low = (note or "").lower()
    complete = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"

    values = {
        "shipment_id": shipment_id, "carrier_name": carrier_name,
        "delivery_date": delivery_date, "ordered_quantity": ordered_quantity,
        "delivered_quantity": delivered_quantity, "condition_code": condition_code,
        "recipient_signature_present": signature, "driver_exception_note": note,
        "pod_timestamp": pod_timestamp, "delivery_complete": complete,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values), "recomputed_complete": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
