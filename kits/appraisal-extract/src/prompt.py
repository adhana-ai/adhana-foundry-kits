"""Assemble the extraction prompt. One prompt per report, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `extraordinary_assumption_present` RULE, stated in full
rather than left for the model to infer. The measurable failure this kit exists to catch is not a
wrong dollar figure -- it is a stated extraordinary assumption that never gets flagged because it
was not sitting under an obviously-labelled heading. So the rule is spelled out: check the WHOLE
report, not just a section named "Extraordinary Assumptions".

⚑ ONE CALL PER REPORT, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

SYSTEM = (
    "You extract structured fields from a real-estate appraisal report. You return JSON and "
    "nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the report does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world.\n"
    "2. `extraordinary_assumption_present` means the report states an extraordinary assumption "
    "SOMEWHERE in its text -- this may be under a dedicated 'Extraordinary Assumptions' "
    "heading, OR embedded in the prose of a different section (Scope of Work, Comments, or "
    "elsewhere) with no special heading at all. Read the entire report before answering 'no'; "
    "a report with no dedicated Extraordinary Assumptions section may still contain one "
    "embedded in another section's text.\n"
    "3. Copy values verbatim from the report wherever possible.\n"
    "4. Use the exact allowed value for a field that lists them.\n"
    "5. Return every field named in the schema, even when the answer is null."
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
            "Use null for any field the report does not state.\n\n"
            "REPORT\n------\n%s\n" % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "report sections", "text": context},
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
