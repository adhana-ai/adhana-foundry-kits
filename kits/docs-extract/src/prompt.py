"""Assemble the extraction prompt. One prompt per document, all nine fields in it.

⚠︎ THE REFUSAL INSTRUCTION IS THE GUARDRAIL OF THIS KIT, and it is the only one.
UC001's guardrail is "cite the passages you used". That does not transfer: a field value is one
token and there is no passage to cite. What replaces it is the instruction below to return null
for anything the document does not state — because the measurable failure here is not a wrong
answer, it is a CONFIDENT INVENTED one. 146 of this corpus's 456 field-cells have no value in the
document at all, so a model that guesses plausibly scores well on the cells that exist and fails
every one of those, and only a per-field breakdown ever shows it.

⚑ ONE CALL PER DOCUMENT, NOT ONE PER FIELD. Nine calls would let each field carry only its own
selected sections and would be the cheaper-looking design on paper; it is nine times the fixed
prompt overhead and nine round trips. The sections are unioned once, in document order, and the
model fills the whole record. The cost lesson lands the same way either side.
"""
import json

SYSTEM = (
    "You extract structured fields from documents. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the document does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world. A null is a correct answer.\n"
    "2. Copy values verbatim from the document wherever possible, so they can be located in it.\n"
    "3. Use the exact allowed value for a field that lists them.\n"
    "4. Return every field named in the schema, even when the answer is null."
)


def field_schema(fields):
    """The schema as the model sees it: name, type, allowed values, and the one-line hint."""
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " — %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes.

    THE PARTS ARE A REAL DECOMPOSITION, NOT A TIDY BREAKDOWN. Every part's text occurs verbatim
    in what is sent, in this order — the kit standard requires exactly that, because a breakdown
    that does not match the bytes on the wire looks like evidence and is not.
    """
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
            "Use null for any field the document does not state.\n\n"
            "DOCUMENT\n--------\n%s\n" % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "document sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    """Pull the JSON object out of a model reply, tolerantly but never creatively.

    A model that wraps JSON in a fence or adds a sentence is handled. A model that returns
    something unparseable yields {} — every field then reads as "not extracted", which is the
    truthful rendering. It does NOT fall back to regex-scraping values out of the prose: that
    would silently turn a broken model call into a mediocre extraction and the run record would
    show a working system.
    """
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
