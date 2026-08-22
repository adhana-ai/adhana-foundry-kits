"""Pick which sections of a contract pack are sent. Pure code -- the last deterministic step
before the model.

⚑ `Customer Reference` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING -- and on this shape of
document it is also the one section a real deal desk would most mind sending anywhere. Every pack
names the customer, its segment, an account number and a billing-contact reference; no field asks
for any of it, so the union of the mapped sections leaves the section out and it never leaves the
machine. It is the one section a reader can point at and say "that is what selection did".

⚠︎ AND EVERYTHING ELSE IS SENT, DELIBERATELY. A cheaper selection is available here and it would
break the kit: the Professional Services Rate Card and the Continuing Items sections are DECOYS,
and the whole identification score is "did the run leave those codes off the worksheet". A selector
that dropped them would be marking the model's homework for it. They cost tokens and they buy the
only honest version of the number.

⚑ SECTION NAMES ARE MATCHED BY PREFIX, NOT BY A FIXED LIST. A pack has one section per ordered
line, headed `Item PO-4417`, and the codes differ on every contract -- so a dict of literal names
the way a fixed-layout sheet uses cannot work here. `for_field` matches "Item " as a prefix and the
rest by exact name; anything unmatched falls back to the whole document, which is slower, more
expensive and always correct.
"""

# Exact section names every pack carries.
ORDER_FORM = "Order Form"
CONTRACT = "Contract"
NOTES = "Contract Notes"
RATE_CARD = "Professional Services Rate Card"
CARRYOVER = "Continuing Items From An Earlier Order Form"

# The per-line sections, matched on this prefix.
ITEM_PREFIX = "Item "

# ⚠︎ NEVER MAPPED, THEREFORE NEVER SENT. Named here rather than merely omitted, so that a reader
# can see the omission is a decision and a future editor cannot "helpfully" add it back without
# reading this line.
NEVER_SENT = ("Customer Reference",)

SECTION_HINTS = {
    "contract_id": [CONTRACT],
    "item_code": [ORDER_FORM, NOTES, RATE_CARD, CARRYOVER],
    "item_label": [ORDER_FORM, ITEM_PREFIX],
    "item_type": [ITEM_PREFIX],
    "charge": [ORDER_FORM, ITEM_PREFIX],
    "dependency": [ITEM_PREFIX],
    "timing": [ITEM_PREFIX],
    "separation": [ORDER_FORM, ITEM_PREFIX],
    "pattern": [ITEM_PREFIX],
}


def _matches(name, want):
    for w in want:
        if w.endswith(" ") and name.startswith(w):
            return True
        if name == w:
            return True
    return False


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if _matches(s["name"], want)]
    return hit or list(secs)


def sent(secs):
    """Every section that reaches the model, in document order -- the union over all fields.

    ⚑ THE DECOY SECTIONS ARE IN HERE AND `Customer Reference` IS NOT. That is the whole of this
    module's behaviour in one function, and evals/check_labels.py asserts both halves before any
    run may spend.
    """
    keep, seen = [], set()
    for field in SECTION_HINTS:
        for s in for_field(secs, field):
            if s["start"] not in seen:
                seen.add(s["start"])
                keep.append(s)
    keep.sort(key=lambda s: s["start"])
    return keep


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
