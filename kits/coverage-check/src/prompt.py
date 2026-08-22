"""Assemble the adjudication prompt. One prompt per warranty claim record, all thirteen fields in
it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `covered`, AND IT IS A SIX-BRANCH RULE WITH A PRIORITY ORDER
PLUS A DATE CALCULATION. It is stated in full rather than left for the model to infer, because the
measurable failures this kit exists to catch are all failures of ORDER or of DEFAULT:

  1. READING THE TECHNICIAN'S CLOSING OPINION INSTEAD OF APPLYING THE TERMS. Every narrative in
     this corpus ends with the technician's own guess about whether the claim will pay, and on 22
     of 55 records that guess is wrong. It is the loudest sentence in the record and it is the one
     part of it that is nobody's measurement.
  2. READING THE CODED `Cause Code` FIELD INSTEAD OF WHAT THE NARRATIVE DESCRIBES. Six records
     describe a curb strike, a spliced-in aftermarket controller or a skipped service interval and
     are coded `defect`; six describe a plain internal failure and are coded as damage, a
     modification or missed maintenance. The narrative decides.
  3. REACHING FOR "THE 3/36". The bumper-to-bumper term is the one everybody quotes, and it is the
     wrong limit for a claim filed under a powertrain, emissions or extended plan. Five records
     are past 36 months and 36,000 miles and comfortably inside the plan that actually applies.
  4. ANSWERING "WEAR ITEM, THEREFORE NO". A wear item that fails inside 12 months AND 12,000 miles
     is covered under a bumper-to-bumper plan as a premature failure. Four records are exactly
     that, and four more are the same components just past the window.
  5. GETTING THE MONTH ARITHMETIC WRONG AT A BOUNDARY. Six records sit EXACTLY on a month or
     mileage limit, which is inside the term, and seven sit exactly one month or one mile outside
     it. Both are settled by a calculation, not by a reading.

⚑ ONE CALL PER CLAIM, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You are a warranty claim adjudicator. You read one dealer warranty claim record and return "
    "structured JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about any real manufacturer's warranty.\n"
    "2. THE COVERAGE TERMS ARE THE ONES BELOW AND NOTHING ELSE. Each plan has its own month and "
    "mileage limit, and its own list of covered components:\n"
    "   - basic       36 months / 36,000 miles  -- covers every component below except wear items\n"
    "   - powertrain  60 months / 60,000 miles  -- covers ONLY transmission_assembly, "
    "engine_short_block, drive_axle\n"
    "   - emissions   96 months / 80,000 miles  -- covers ONLY catalytic_converter, "
    "oxygen_sensor, evap_canister\n"
    "   - extended    84 months / 100,000 miles -- covers every component below except wear items\n"
    "   Wear items are brake_pads, wiper_blades and clutch_disc. They are on NO plan's component "
    "list.\n"
    "   Each component has exactly one labor operation:\n"
    "   transmission_assembly=LOP-4412, engine_short_block=LOP-4101, drive_axle=LOP-4520, "
    "catalytic_converter=LOP-2203, oxygen_sensor=LOP-2217, evap_canister=LOP-2240, "
    "infotainment_head_unit=LOP-8310, power_window_motor=LOP-8422, hvac_blower_motor=LOP-8155, "
    "brake_pads=LOP-5701, wiper_blades=LOP-5140, clutch_disc=LOP-5330.\n"
    "3. `months_in_service` IS A CALCULATION, NOT A READING. It is (repair year - in-service "
    "year) x 12 + (repair month - in-service month), minus 1 if the repair day-of-month is "
    "EARLIER than the in-service day-of-month. Compute it before you decide coverage; the answer "
    "to several of these claims turns on one month.\n"
    "4. `covered` IS DECIDED BY SIX CHECKS IN THIS EXACT ORDER. Stop at the first that fires:\n"
    "   a. If narrative_finding is collision_damage, unauthorized_modification or "
    "missed_maintenance, answer 'no'. An exclusion the technician describes outranks every "
    "coverage term, however new the vehicle is.\n"
    "   b. Otherwise, if claimed_labor_op is not the operation listed above for this "
    "failed_component, answer 'no'. The claim is not payable as coded.\n"
    "   c. Otherwise, if failed_component is a wear item, answer 'yes' when coverage_plan is "
    "basic or extended AND months_in_service is 12 or less AND odometer_miles is 12,000 or less "
    "-- a premature wear failure IS covered. In every other case answer 'no'.\n"
    "   d. Otherwise, if failed_component is not on this coverage_plan's own component list, "
    "answer 'no'.\n"
    "   e. Otherwise, if months_in_service is GREATER THAN this plan's month limit, or "
    "odometer_miles is GREATER THAN this plan's mileage limit, answer 'no'. USE THE PLAN'S OWN "
    "LIMIT, NEVER THE 36/36,000 BASIC ONE. The limits are inclusive: exactly 36 months on a basic "
    "plan is inside the term, not outside it.\n"
    "   f. Otherwise answer 'yes'.\n"
    "5. `narrative_finding` IS READ FROM THE TECHNICIAN NARRATIVE, NOT FROM THE CAUSE CODE FIELD. "
    "The Cause Code is what the dealer coded on the form; the narrative is what the technician "
    "says they actually found, and on this corpus the two often disagree. Copy the Cause Code "
    "into `cause_code` and then ignore it completely when deciding anything else.\n"
    "6. THE TECHNICIAN'S CLOSING OPINION ABOUT WHETHER THE CLAIM WILL PAY IS NOT EVIDENCE. Every "
    "narrative ends with one. A narrative that says 'should be covered, no question' does NOT "
    "make the claim covered, and one that says 'I expect this gets denied' does NOT make it "
    "denied. Only the six checks above decide, and they never read that sentence.\n"
    "7. Copy values verbatim from the record wherever possible, and report months_in_service and "
    "odometer_miles as bare numbers with the unit left out of them.\n"
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
            "WARRANTY CLAIM RECORD\n---------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "claim sections", "text": context},
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
