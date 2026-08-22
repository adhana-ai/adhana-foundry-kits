"""Assemble the extraction prompt. One prompt per student-account tuition assessment, all twelve
fields in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `assessment_correct` AND `variance_reason`, AND THEY ARE
ARITHMETIC OVER A FOUR-STEP RATE TABLE WITH AN ORDER. The whole table is stated rather than left
for the model to infer, because the measurable failures this kit exists to catch are a model that
answers from the bursar's tone, a model that re-prices tuition because a residency reclassification
is sitting on the account, and a model that runs the four steps in the wrong order.

Five things are spelled out that a model left to its own reading gets wrong:

  1. THE FULL-TIME THRESHOLD IS INCLUSIVE, AND THE FLAT BAND IS CHEAPER. Exactly 12 credits is
     full-time, so tuition is the flat term rate -- NOT 12 times the per-credit rate. The two
     numbers differ by $320 in-state and $960 out-of-state, so getting the band wrong is not a
     rounding difference.
  2. A MID-TERM RESIDENCY RECLASSIFICATION DOES NOT CHANGE THIS TERM. Every reclassification in
     this corpus took effect after the term's census date, so it applies from the FOLLOWING term.
     The tier of record in the Residency Tier section is the one that prices this assessment.
  3. THE DIFFERENTIAL FEE IS ZERO FOR LOWER DIVISION AND PER CREDIT FOR THE OTHER TWO. It is
     charged on top of the flat full-time band as well as on top of a part-time load -- being
     full-time does not fold it in.
  4. NO WAIVER EVER TOUCHES THE DIFFERENTIAL FEE, AND ONLY ONE OF THE FOUR TOUCHES THE MANDATORY
     FEE. A waiver that legitimately does not cover a charge is not an error to be corrected.
  5. THE BURSAR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds concerned does not mean
     the assessment is wrong, and a note that sounds routine does not mean it is right -- only the
     arithmetic decides.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a student-account tuition assessment record for one "
    "student, for one academic term. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `assessment_correct` is decided by ARITHMETIC over four structured values -- "
    "residency_tier, enrolled_credits, course_level and waiver_type -- compared against the "
    "assessed_total_usd the record already states. It is never decided by how the bursar's note "
    "reads and never by the residency action line. Compute the correct total yourself, in this "
    "order:\n"
    "   a. TUITION. enrolled_credits of 12 or more is a FULL-TIME load, and tuition is the flat "
    "term rate: 4600 In-State, 13200 Out-of-State. Under 12 credits it is enrolled_credits times "
    "the per-credit rate: 410 In-State, 1180 Out-of-State. EXACTLY 12 CREDITS IS FULL-TIME -- use "
    "the flat rate, not 12 times the per-credit rate.\n"
    "   b. COURSE-LEVEL DIFFERENTIAL FEE. enrolled_credits times 0 for Lower Division, times 38 "
    "for Upper Division, times 65 for Graduate. It is charged per enrolled credit whether the load "
    "is full-time or part-time.\n"
    "   c. MANDATORY FEE. 612 for a full-time load, 306 for a part-time one.\n"
    "   d. WAIVER, applied LAST. 'None' waives nothing. 'Employee Tuition Remission' waives 100 "
    "percent of the tuition from step a and nothing else. 'Staff Dependent Waiver' waives 50 "
    "percent of the tuition from step a and nothing else. 'Regents Fee Waiver' waives 100 percent "
    "of the tuition from step a AND 100 percent of the mandatory fee from step c. NO WAIVER EVER "
    "REDUCES THE DIFFERENTIAL FEE FROM STEP b.\n"
    "   The correct total is (a) + (b) + (c) minus the amount waived in (d). Answer 'yes' when "
    "assessed_total_usd EXACTLY equals that number, and 'no' in every other case.\n"
    "3. THE RESIDENCY TIER OF RECORD IS THE ONE THAT PRICES THIS TERM. The Residency Action line "
    "may state a reclassification to the other tier. Every such reclassification in these records "
    "took effect AFTER the term's census date, so it applies from the FOLLOWING term and changes "
    "nothing here. Price the assessment at the tier in the Residency Tier section, and copy the "
    "action line into residency_action unchanged.\n"
    "4. THE BURSAR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT CORRECTNESS. A note that sounds "
    "concerned or flags a past review does NOT mean the assessment is wrong, and a note that "
    "sounds routine does NOT mean it is right. The arithmetic decides; the note is the bursar's "
    "own remark and may disagree with it.\n"
    "5. `variance_reason` names WHICH SINGLE STEP the assessed total departs from when "
    "assessment_correct is 'no': 'credit band' for step a's full-time/part-time choice, "
    "'residency tier' for step a priced at the wrong tier, 'differential fee' for step b, "
    "'waiver coverage' for step d reaching a charge it does not cover or missing one it does, and "
    "'mandatory fee' for step c taken at the wrong band. Exactly one of them explains any "
    "variance in these records. Answer 'none' when assessment_correct is 'yes'.\n"
    "6. Copy values verbatim from the record wherever possible, and report enrolled_credits and "
    "assessed_total_usd as bare numbers with the unit left out of them. Copy "
    "assessed_total_usd as stated -- it is what the bursar system charged, not what you compute.\n"
    "7. Use the exact allowed value for a field that lists them.\n"
    "8. Return every field named in the schema, even when the answer is null."
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
            "STUDENT ACCOUNT TUITION ASSESSMENT\n----------------------------------\n%s\n"
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
