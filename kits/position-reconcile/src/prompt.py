"""Assemble the extraction prompt. One prompt per break record, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `is_true_break` RULE, stated in full rather than left for the
model to infer. The measurable failure this kit exists to catch is classifying a break by which
words its memo uses rather than by what the memo actually says happened -- a genuine break whose
memo still carries a now-stale "pending settlement" note, or a fully-resolved item whose memo
opens with an alarming word.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

SYSTEM = (
    "You extract structured fields from a position reconciliation break record. You return "
    "JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world.\n"
    "2. `is_true_break` means the reconciling memo describes a GENUINE, unresolved discrepancy "
    "-- no explanation on file, custodian unresponsive, no correction submitted -- as opposed "
    "to a BENIGN, explainable and self-resolving timing difference (a trade pending settlement "
    "that is on track, a corporate action in process, a dividend timing difference). Judge by "
    "what the memo says ACTUALLY HAPPENED, not by which words it uses. A memo that still says "
    "'pending settlement' after the settlement date has clearly passed with no confirmation is "
    "a true break despite using settlement language. A memo that opens with an alarming word "
    "('URGENT', 'mismatch flagged') but is fully accounted for by its own end is not a true "
    "break. Read the whole memo before deciding.\n"
    "3. Copy values verbatim from the record wherever possible.\n"
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
            "Use null for any field the record does not state.\n\n"
            "BREAK RECORD\n------------\n%s\n" % (schema, ", ".join(names), context))

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
