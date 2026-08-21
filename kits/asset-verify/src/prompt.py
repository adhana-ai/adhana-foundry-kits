"""Assemble the extraction prompt. One prompt per statement, all ten fields in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS THE `deposit_documented` RULE, and it is stated in full rather
than left for the model to infer from examples. The measurable failure this kit exists to catch
is not a wrong balance -- it is a large deposit whose source was never actually verified getting
waved through because a description merely SOUNDS like payroll. So the rule is spelled out:
documented means a NAMED, verifiable institutional counterparty (an employer, IRS, a named
pension fund, SSA, or a named bank/brokerage on a transfer), never a keyword alone and never a
personal P2P transfer or cash deposit however specific-looking.

⚑ ONE CALL PER STATEMENT, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit
here: nine extra calls would be nine times the fixed prompt overhead for no benefit, since the
sections are unioned once and the model fills the whole record.
"""
import json

SYSTEM = (
    "You extract structured fields from a bank or brokerage statement. You return JSON and "
    "nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the statement does not state a field, return null for it. Do not infer it, do not "
    "compute it, and do not use what you know about the world. A null is a correct answer -- a "
    "statement with no deposits this period correctly has null for every deposit field.\n"
    "2. `deposit_documented` means the largest deposit's description names a SPECIFIC, "
    "VERIFIABLE INSTITUTIONAL counterparty: a named employer, \"IRS TREAS\", a named pension "
    "fund, \"SSA\"/Social Security, or a named bank/brokerage on a wire or transfer. It is 'no' "
    "for a personal P2P transfer (Zelle, Venmo, cash app), a cash deposit, a mobile check "
    "deposit with no payer named, or a generic \"Deposit\"/\"Payroll Deposit\"/\"Direct "
    "Deposit\" line that does NOT name an employer -- the word 'payroll' alone is not a "
    "counterparty. Read the whole description; do not decide from one keyword.\n"
    "3. Copy values verbatim from the statement wherever possible.\n"
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
    """Return (messages, parts, sections_used). `parts` is the decomposition the LLM lens
    publishes -- a real one: every part's text occurs verbatim in what is sent, in this order."""
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
            "Use null for any field the statement does not state.\n\n"
            "STATEMENT\n---------\n%s\n" % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "statement sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    """Pull the JSON object out of a model reply, tolerantly but never creatively. An
    unparseable reply yields {} -- every field then reads as 'not extracted'."""
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
