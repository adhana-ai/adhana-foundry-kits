"""Assemble the extraction prompt. One prompt per utility billing-account record, all ten fields
in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `rate_correct`, AND IT IS A FOUR-VALUE COMPARISON WITH A
PRIORITY ORDER. It is stated in full rather than left for the model to infer, because the
measurable failure this kit exists to catch is a model that answers from the account note's tone,
or that applies the demand threshold without first checking whether the TOU-8 override fires --
reading "Escalated last cycle for a possible rate misclassification" as proof of a mismatch when
every structured value says the applied code is correct, or seeing a 66 kW demand reading and
reaching for GS-2 on an interval-metered, 16,400 kWh account that the rule routes to TOU-8 instead.

Four things are spelled out that a model left to its own reading gets wrong:

  1. A RESIDENTIAL ACCOUNT IS ALWAYS R-1, whatever it uses. Usage and demand never move a
     Residential account off R-1.
  2. TOU-8 OUTRANKS THE DEMAND THRESHOLD. An interval-metered commercial account at or above
     15,000 kWh qualifies for TOU-8 REGARDLESS of its demand reading -- checking demand first and
     stopping there is the wrong order.
  3. THE DEMAND BOUNDARY IS INCLUSIVE. Exactly 50 kW qualifies for GS-2, not GS-1.
  4. THE ACCOUNT NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds concerned does not mean
     the rate is wrong, and a note that sounds routine does not mean it is right -- only the four
     structured values decide.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a utility billing-account record for one account. "
    "You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `rate_correct` is decided by COMPARING FOUR STRUCTURED VALUES -- service_class, "
    "meter_type, metered_usage_kwh, peak_demand_kw -- against the applied_rate_code, never by "
    "how the account note reads. Compute the correct code yourself, in this order:\n"
    "   a. If service_class is 'Residential', the correct code is 'R-1'. Usage and demand never "
    "change this.\n"
    "   b. Otherwise, if meter_type is 'interval' AND metered_usage_kwh is 15000 or more, the "
    "correct code is 'TOU-8' -- REGARDLESS of the demand reading. Check this before you check "
    "demand.\n"
    "   c. Otherwise, if peak_demand_kw is 50 or more, the correct code is 'GS-2'. Exactly 50 "
    "qualifies for GS-2, not GS-1.\n"
    "   d. Otherwise, the correct code is 'GS-1'.\n"
    "   Answer 'yes' when applied_rate_code EXACTLY equals the code you computed. Answer 'no' in "
    "every other case.\n"
    "3. THE TOU-8 CHECK COMES BEFORE THE DEMAND CHECK. An interval-metered account using 15,000 "
    "kWh or more qualifies for TOU-8 even when its demand reading looks like a GS-2 case -- do "
    "not stop at the demand threshold without first checking meter type and usage.\n"
    "4. THE ACCOUNT NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT CORRECTNESS. A note that sounds "
    "concerned or flags a past review does NOT mean the applied rate is wrong, and a note that "
    "sounds routine does NOT mean the applied rate is right. The four structured values decide; "
    "the note is the billing rep's own remark and may disagree with them.\n"
    "5. Copy values verbatim from the record wherever possible, and report metered_usage_kwh and "
    "peak_demand_kw as bare numbers with the unit left out of them. peak_demand_kw is null for a "
    "Residential account -- return null for it rather than 0 or a guess.\n"
    "6. Use the exact allowed value for a field that lists them.\n"
    "7. Return every field named in the schema, even when the answer is null."
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
            "UTILITY BILLING ACCOUNT RECORD\n-------------------------------\n%s\n"
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
