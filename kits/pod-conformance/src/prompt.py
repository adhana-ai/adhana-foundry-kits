"""Assemble the extraction prompt. One prompt per proof-of-delivery record, all ten fields in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `delivery_complete`, AND IT IS A COMPARISON BETWEEN TWO
STRUCTURED VALUES. It is stated in full rather than left for the model to infer, because the
measurable failure this kit exists to catch is a model that answers the question from the driver's
own exception note instead of comparing the counts -- reading "all good on my end, no issues to
report" as a complete delivery when eleven units of a hundred and eighty never arrived, or reading
"sorry for the mix-up, had to leave it at the gate" as an incomplete one when every unit was
scanned and the condition code says undamaged.

Three things are spelled out that a model left to its own reading gets wrong:

  1. EQUALITY IS EXACT IN BOTH DIRECTIONS. "Did at least the ordered quantity arrive" is the
     natural reading and it is the wrong one -- a surplus is still not the order that was booked.
  2. THE CONDITION CODE IS PART OF THE TEST, not a separate remark. Counts that match with a
     `damaged` code is not a complete delivery.
  3. `unknown` IS NOT A PASS. A condition nobody assessed at the drop is not an undamaged one, and
     a rule that treats an absent assessment as a clean one is the rule that lets damage through.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a proof-of-delivery record for one shipment. "
    "You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `delivery_complete` is decided by COMPARING THE STRUCTURED VALUES, never by how the "
    "driver's exception note reads. Answer 'yes' when delivered_quantity is EXACTLY EQUAL to "
    "ordered_quantity AND condition_code is exactly 'undamaged'. Answer 'no' in every other "
    "case. Do the comparison yourself before answering.\n"
    "3. EXACTLY EQUAL MEANS EQUAL IN BOTH DIRECTIONS. A delivery that is short of the ordered "
    "quantity is not complete, and neither is one that delivered MORE units than were ordered -- "
    "a surplus is not the order that was booked. Do not read the rule as 'at least the ordered "
    "quantity arrived'.\n"
    "4. THE CONDITION CODE IS PART OF THE TEST. A condition_code of 'damaged' means the delivery "
    "is not complete even when the two quantities match exactly. So does a condition_code of "
    "'unknown': a condition nobody assessed at the drop is not an undamaged one, and only the "
    "exact value 'undamaged' passes.\n"
    "5. The driver's exception note is a field to copy, not evidence about completeness. A note "
    "reading 'all good on my end, no issues to report' does NOT make a short or damaged delivery "
    "complete, and a note reading 'sorry for the mix-up, had to leave it at the gate' does NOT "
    "make a delivery with matching counts and an undamaged code incomplete. The structured "
    "values decide; the note is the driver's own account of the stop and may disagree with "
    "them.\n"
    "6. Copy values verbatim from the record wherever possible, and report ordered_quantity and "
    "delivered_quantity as bare numbers with the word 'units' left out of them.\n"
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
            "PROOF OF DELIVERY RECORD\n------------------------\n%s\n"
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
