"""Assemble the extraction prompt. One prompt per certificate of analysis, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `conforms_to_spec` RULE, AND IT IS ARITHMETIC. Stated in full
rather than left for the model to infer, because the measurable failure this kit exists to catch is
a model that answers the question from the analyst's own disposition note instead of doing the
comparison itself -- reading "within normal range, released" as conformance when the measured value
is a hair outside the stated limits, or reading "borderline, recommend re-test" as a failure when
the value sits cleanly inside them.

The rule is spelled out with its boundary convention, because "within limits" is ambiguous at the
limit and a model that guesses the convention is guessing on the one field that matters.

⚑ ONE CALL PER CERTIFICATE, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a certificate of analysis for one manufactured batch. "
    "You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the certificate does not state a field, return null for it. Do not infer it and do "
    "not use what you know about the world. A specification limit the certificate explicitly "
    "says is not specified is null, not a number you supply.\n"
    "2. `conforms_to_spec` is decided by ARITHMETIC ON THE NUMBERS, never by how the analyst's "
    "disposition note reads. Answer 'yes' when measured_value >= spec_lower_limit AND "
    "measured_value <= spec_upper_limit; answer 'no' otherwise. Both limits are INCLUSIVE -- a "
    "value exactly on a limit conforms. A limit the certificate does not state places no "
    "constraint on that side, so a one-sided specification is judged on the side it does state. "
    "Do the comparison yourself before answering.\n"
    "3. The analyst's disposition note is a field to copy, not evidence about conformance. A note "
    "reading 'within normal range, released' does NOT make an out-of-limits value conform, and a "
    "note reading 'borderline, recommend re-test' does NOT make an in-limits value fail. The "
    "numbers decide; the note is the analyst's opinion and may disagree with them.\n"
    "4. Copy values verbatim from the certificate wherever possible, and report measured_value, "
    "spec_lower_limit and spec_upper_limit as bare numbers with the unit left out of them.\n"
    "5. Use the exact allowed value for a field that lists them.\n"
    "6. Return every field named in the schema, even when the answer is null."
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
            "Use null for any field the certificate does not state.\n\n"
            "CERTIFICATE OF ANALYSIS\n-----------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "certificate sections", "text": context},
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
