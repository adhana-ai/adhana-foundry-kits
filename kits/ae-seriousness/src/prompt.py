"""Assemble the extraction prompt. One prompt per case report, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `is_serious` RULE, STATED IN FULL rather than left for the
model to infer. The measurable failure this kit exists to catch is classifying a case by the
report's own severity WORDING rather than by which seriousness criterion the outcome actually met
-- a "severe" headache that resolved at home is not regulatorily serious, and a "mild" rash that
led to a three-day admission is.

⚠︎ THE SECOND RULE IS THAT `causality_assessment` IS A DIFFERENT QUESTION. Seriousness is about
how bad the outcome was; causality is about whether the drug caused it. They are easy to conflate
and a conflated pair silently changes what the downstream routing flag means, so the prompt says
so out loud rather than trusting the field hints to carry it.

⚑ ONE CALL PER REPORT, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

SYSTEM = (
    "You extract structured fields from an adverse event case report. You return JSON and "
    "nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the report does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world.\n"
    "2. `is_serious` is a REGULATORY classification -- the seriousness criteria used across "
    "pharmacovigilance reporting -- and NOT a description of how bad the event sounds. Answer "
    "`yes` when the report describes ANY of the following having actually happened: the patient "
    "died; the event was life-threatening; the patient was admitted to hospital, or an existing "
    "admission was prolonged, because of the event; the event left a persistent or significant "
    "disability or incapacity; a congenital anomaly or birth defect followed exposure; or the "
    "event was medically important enough to require an intervention to prevent one of the "
    "outcomes just listed. Answer `no` when none of those is described.\n"
    "3. DO NOT decide `is_serious` from the report's own severity wording. 'Severe', 'moderate' "
    "and 'mild' describe how the event felt and are NOT the regulatory test. A severe-sounding "
    "event that fully resolved at home with no medical attention is NOT serious. A mild-sounding "
    "event that led to a hospital admission IS serious. Read what actually happened to the "
    "patient and match it against the list in rule 2. Read the whole narrative before deciding: "
    "four of the six criteria are stated only in the narrative and never in a field of their "
    "own.\n"
    "4. `causality_assessment` is a DIFFERENT judgment from `is_serious` and must not be "
    "conflated with it. Causality is the reporter's own stated view of whether the drug caused "
    "the event; seriousness is about how bad the outcome was. A case can be serious and "
    "unrelated at the same time. Report the reporter's own stated causality; do not form your "
    "own.\n"
    "5. `narrative_severity_word` is the colloquial severity word the report itself uses, copied "
    "exactly as written. Return null when the report uses no such word -- do not supply one, and "
    "do not translate the classification back into a word.\n"
    "6. Copy values verbatim from the report wherever possible.\n"
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
            "Use null for any field the report does not state.\n\n"
            "CASE REPORT\n-----------\n%s\n" % (schema, ", ".join(names), context))

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
