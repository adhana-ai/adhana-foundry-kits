"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending twenty fields x the
whole record is twenty times the input tokens of sending each field the section that could possibly
state it.

⚑ `Managing Agent` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every reconciliation line
in this corpus names the firm managing the property; no field asks for it, so the union of the
mapped sections leaves it out and it is never sent. It is the one section a reader can point at
and say "that is what selection did" -- the rest of the saving is real but invisible, because the
sections that are sent would have been sent anyway.

⚑ `permitted_amount_usd` AND `line_ok` ARE MAPPED TO THE THIRTEEN FACTS THE ARITHMETIC ACTUALLY
USES, AND NOT TO THE ACCOUNTANT'S NOTE. That is a statement of the rule rather than a saving. What
a lease permits is four stages of arithmetic over structured values; the property accountant's own
note is evidence of nothing about it. The note still reaches the model -- it is a field in its own
right, and the union of every field's sections is what gets sent -- so this mapping is not a filter
that hides the decoy. It is the map of where the answer actually lives.

⚠︎ AND `Expense Category` IS MAPPED TO THE CATEGORY FIELD ONLY, NEVER TO THE ARITHMETIC. That is
the second planted ambiguity stated as a mapping: on 14 of these 55 records the category NAME reads
like an exclusion -- "Parking lot resurfacing", "Property management fee" -- while `Expense Class`
says routine_operating. The class decides. The name is a label somebody typed.
"""

# The thirteen sections the four-stage arithmetic reads, in document order.
_ARITHMETIC = ["Expense Class", "Pool Gross Cost", "Amortization Years", "Occupancy Sensitive",
               "Building Occupancy", "Building Area", "Tenant Area", "Expansion Area",
               "Expansion Month", "Cap Type", "Cap Percent", "Cap Basis", "Cap Periods"]

SECTION_HINTS = {
    "line_id": ["Statement Line"],
    "expense_category": ["Expense Category"],
    "expense_class": ["Expense Class"],
    "pool_gross_usd": ["Pool Gross Cost"],
    "amortization_years": ["Amortization Years"],
    "occupancy_sensitive": ["Occupancy Sensitive"],
    "building_occupancy_pct": ["Building Occupancy"],
    "building_area_sf": ["Building Area"],
    "tenant_area_sf": ["Tenant Area"],
    "expansion_area_sf": ["Expansion Area"],
    "expansion_month": ["Expansion Month"],
    "cap_type": ["Cap Type"],
    "cap_pct": ["Cap Percent"],
    "cap_basis_usd": ["Cap Basis"],
    "cap_years": ["Cap Periods"],
    "billed_to_tenant_usd": ["Billed To Tenant"],
    "statement_status": ["Statement Status"],
    "accountant_note": ["Accountant Notes"],
    "permitted_amount_usd": list(_ARITHMETIC),
    "line_ok": _ARITHMETIC + ["Billed To Tenant"],
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
