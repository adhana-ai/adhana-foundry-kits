"""Assemble the extraction prompt. One prompt per stub, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `bonus_recurring` RULE, stated in full rather than left for
the model to infer from examples. The measurable failure this kit exists to catch is not a wrong
dollar figure -- it is a one-time bonus getting folded into qualifying income because its label
merely SOUNDS recurring. So the rule is spelled out: recurring means an ACTUAL STATED PAYMENT
HISTORY of two or more prior payments, never a keyword like "annual" alone.

⚑ ONE CALL PER STUB, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

SYSTEM = (
    "You extract structured fields from a pay stub. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the stub does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world. A null is a correct answer -- "
    "a stub with no overtime this year correctly has null for every overtime field, and a stub "
    "with no bonus correctly has null for every bonus field.\n"
    "2. `bonus_recurring` means the Bonus History note states an ACTUAL PAYMENT HISTORY of two "
    "or more prior payments (e.g. \"paid in 2024 and 2025\", \"paid each quarter for two "
    "years\"). It is 'no' for a note that only uses a word like \"annual\" or \"recurring\" "
    "WITHOUT stating any payment history (\"Annual performance bonus\" with no history given), "
    "and 'no' for an explicitly one-time or discretionary bonus. The label alone is not "
    "history -- read for a stated history, not a keyword.\n"
    "3. Copy values verbatim from the stub wherever possible.\n"
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
            "Use null for any field the stub does not state.\n\n"
            "PAY STUB\n--------\n%s\n" % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "pay stub sections", "text": context},
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
