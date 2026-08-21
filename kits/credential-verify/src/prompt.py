"""Assemble the extraction prompt. One prompt per file, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `sanction_or_adverse_action_found` RULE, stated in full
rather than left for the model to infer. The measurable failure this kit exists to catch is a
mild-sounding adverse action -- a reprimand, a consent order, a letter of concern -- getting
waved through as clean because it reads gently, often beside reassuring language like "otherwise
active and in good standing" in the very same sentence.

⚑ ONE CALL PER FILE, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

SYSTEM = (
    "You extract structured fields from a provider credentialing file. You return JSON and "
    "nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the file does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world.\n"
    "2. `sanction_or_adverse_action_found` means the PSV finding describes ANY adverse action "
    "against the provider -- a reprimand, consent order, letter of concern, restriction, "
    "suspension, revocation or exclusion -- HOWEVER MILDLY IT IS WORDED. A finding that says "
    "the license is 'otherwise active' or imposes 'no practice restriction' is still 'yes' if "
    "any adverse action is named anywhere in it. Only answer 'no' when the finding describes "
    "no adverse action of any kind.\n"
    "3. Copy values verbatim from the file wherever possible.\n"
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
            "Use null for any field the file does not state.\n\n"
            "CREDENTIALING FILE\n-------------------\n%s\n" % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "file sections", "text": context},
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
