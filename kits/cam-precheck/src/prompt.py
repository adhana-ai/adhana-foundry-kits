"""Assemble the extraction prompt. One prompt per CAM reconciliation line, all twenty fields in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `permitted_amount_usd` AND `line_ok`, AND THEY ARE FOUR
STAGES OF ARITHMETIC WITH AN ORDER. The order is stated in full rather than left for the model to
infer, because the measurable failures this kit exists to catch are all ORDER failures or
NAME failures:

  1. A CAPITAL ITEM THE LEASE PERMITS AMORTIZING IS PARTLY BILLABLE. "Capital is excluded" is the
     rule most readers carry, and it is wrong on exactly the records that cost the most: the
     poolable figure is one annual instalment, gross / years, not the whole cost and not zero.
  2. THE CATEGORY NAME IS A LABEL, THE CLASS IS THE CLASSIFICATION. Fourteen of these 55 records
     carry a category called "Parking lot resurfacing", "Property management fee", "Roof membrane
     patching" -- names that read like an exclusion -- on a line whose `expense_class` says
     routine_operating. The class decides.
  3. THE GROSS-UP COMES BEFORE THE CAP, AND ONLY FOR OCCUPANCY-SENSITIVE LINES. Skipping it does
     not merely produce a low number: on three records in this corpus it also hides the cap, whose
     ceiling sits between the ungrossed and the grossed-up share. And applying it to a line whose
     occupancy_sensitive is `no` is an overcharge that looks exactly like diligence.
  4. A CUMULATIVE CAP COMPOUNDS. Applying it once, as though it were an annual cap, undercharges.
  5. A MID-YEAR EXPANSION IS A WEIGHTED AVERAGE, not the starting area and not the expanded area
     for all twelve months. Both wrong answers are one number away from the right one.
  6. THE ACCOUNTANT'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds concerned does not
     mean the line is wrong, and a note that sounds routine does not mean it is right -- only the
     arithmetic decides.

⚑ ONE CALL PER LINE, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You check one line of a commercial-property operating-expense (CAM) reconciliation against "
    "the tenant's own lease terms. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `permitted_amount_usd` is what the lease permits the landlord to bill THIS tenant for "
    "THIS line. Compute it yourself, in FOUR STAGES, IN THIS ORDER:\n"
    "   STAGE 1 -- POOLABLE. Start from pool_gross_usd and decide how much of the pool is "
    "billable to tenants at all, from `expense_class` and nothing else:\n"
    "     - landlord_overhead or leasing_cost -> 0. Nothing of it is billable.\n"
    "     - capital_improvement with amortization_years null -> 0.\n"
    "     - capital_improvement with amortization_years N -> pool_gross_usd / N. ONE ANNUAL "
    "INSTALMENT. Not the whole cost, and NOT zero -- an amortizable capital item is PARTLY "
    "billable, which is the case 'capital is excluded' gets wrong.\n"
    "     - routine_operating -> the whole of pool_gross_usd.\n"
    "   STAGE 2 -- GROSS-UP. If occupancy_sensitive is 'yes' AND building_occupancy_pct is below "
    "95, multiply the stage-1 amount by 95 and divide by building_occupancy_pct. Otherwise leave "
    "it exactly as it is. NEVER gross up a line whose occupancy_sensitive is 'no', however low "
    "the building's occupancy is.\n"
    "   STAGE 3 -- PRO RATA. Multiply by the tenant's weighted share of the building. With no "
    "expansion that share is tenant_area_sf / building_area_sf. With an expansion of A square "
    "feet taking effect in month M it is (tenant_area_sf + A * (13 - M) / 12) / building_area_sf "
    "-- the expansion counts for the months it was actually occupied, INCLUDING month M.\n"
    "   STAGE 4 -- CAP. Work out the ceiling: cap_type 'annual' -> cap_basis_usd * (1 + "
    "cap_pct/100); cap_type 'cumulative' -> cap_basis_usd * (1 + cap_pct/100) ** cap_years, "
    "COMPOUNDED over cap_years periods; cap_type 'none' -> there is no ceiling. Then take the "
    "LOWER of the stage-3 amount and the ceiling. Round the result to two decimals.\n"
    "3. `line_ok` is 'yes' when billed_to_tenant_usd is within 1.00 US dollar of the "
    "permitted_amount_usd you computed, and 'no' otherwise. Nothing else decides it.\n"
    "4. THE EXPENSE CATEGORY IS A LABEL, `expense_class` IS THE CLASSIFICATION. A line called "
    "'Parking lot resurfacing', 'Roof membrane patching', 'Property management fee' or 'HVAC "
    "compressor overhaul' whose expense_class says routine_operating is a routine operating "
    "expense and its whole pool is billable. Do NOT exclude a line because of what it is called.\n"
    "5. THE STAGES ARE IN THAT ORDER FOR A REASON. Gross up before you cap: a ceiling that has "
    "slack against the ungrossed share can bind against the grossed-up one, so skipping stage 2 "
    "can also silently skip stage 4.\n"
    "6. THE ACCOUNTANT'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT CORRECTNESS. A note that "
    "sounds concerned or mentions a past query does NOT mean the line is wrong, and a note that "
    "sounds routine does NOT mean the line is right. The arithmetic decides; the note is the "
    "property accountant's own remark and may disagree with it.\n"
    "7. Copy values verbatim from the record wherever possible, and report every money, area, "
    "percentage, month and year figure as a bare number with the unit left out of it.\n"
    "8. Use the exact allowed value for a field that lists them.\n"
    "9. Return every field named in the schema, even when the answer is null."
)


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the record does not state.\n\n"
            "CAM RECONCILIATION LINE\n-----------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "record sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
