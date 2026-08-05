"""Assemble the summarisation prompt. One prompt per document, the whole rubric in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS "SAY WHAT THE DOCUMENT SAYS, AND SAY WHEN IT DOES NOT SAY".
UC001's is "cite the passages you used"; UC002's is "return null for anything the document does
not state". Neither transfers cleanly. There is no passage to cite for a synthesised paragraph,
and a section of a brief is prose rather than a value that can be null. What replaces both is
below: every figure must be copied rather than computed, recommendations must be the document's
own rather than the model's, and a section with nothing to say must say so IN WORDS.

⚑ WHY AN ABSENT SECTION MUST BE SPELLED, NOT OMITTED. The rubric is a fixed shape, so a missing
section is a finding — and it is the ONE thing this kit can detect mechanically, without a person.
If the model simply skips a heading, `parse()` cannot tell that apart from a parsing failure. The
instruction to write "Not stated in this document." makes the model's refusal explicit and
scoreable, exactly as UC002's null does for a field.

⚑ ONE CALL PER DOCUMENT, NOT ONE PER SECTION. Six calls would let each section carry only the
parts of the document that concern it, and it is six times the fixed prompt overhead for a
document that was packed to fit anyway. It would also destroy the thing the brief is for: the
sections have to be consistent with each other, and six independent calls have no way to be.
"""
import json
import re

SYSTEM = (
    "You write briefs. You are given one long document and a fixed set of sections to fill, and "
    "you return those sections and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. Every claim must be supported by the document. Do not add what you know about the "
    "subject from anywhere else, however certain you are.\n"
    "2. Copy figures verbatim, with their units and their period. Never compute a number the "
    "document does not state — not a total, not a percentage, not a difference.\n"
    "3. Recommendations are the ones the DOCUMENT makes. If it recommends nothing, say so; do "
    "not supply sensible advice of your own.\n"
    "4. If the document gives you nothing for a section, write exactly: Not stated in this "
    "document. A stated absence is a correct answer and is worth more than a plausible one.\n"
    "5. Write plainly, in full sentences. No bullet lists, no headings inside a section, no "
    "preamble about what you are about to do."
)


def rubric_schema(sections):
    """The rubric as the model sees it: the section key, its name, and what it is being asked
    for. THE WEIGHTS ARE DELIBERATELY NOT SENT — telling a model which sections carry the marks
    invites it to write more where the score is, and the weight is a property of how a PERSON
    reads the brief, not of what the document contains. It would also make every future weight
    change a change to the prompt, so a rubric re-weighting could no longer be compared against
    an earlier run."""
    return "\n".join("- %s: %s — %s" % (s["key"], s["name"], s.get("asks", ""))
                     for s in sections)


def build(doc_text, secs, sections, packer, budget_tokens=None):
    """Return (messages, parts, plan).

    `parts` is the decomposition the LLM lens publishes, and every part's text occurs VERBATIM in
    what is sent, in this order. The kit standard requires exactly that: a breakdown that does not
    match the bytes on the wire looks like evidence and is not.
    """
    schema = rubric_schema(sections)
    keys = [s["key"] for s in sections]
    # The scaffolding is measured before the budget is spent, not hoped to fit beside it — the
    # system prompt and the schema are sent on every call whatever the document costs.
    head = ("Fill these sections from the document below:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Each value is the section's text as a plain string.\n"
            "Use \"Not stated in this document.\" for any section the document does not support."
            "\n\nDOCUMENT\n--------\n" % (schema, ", ".join(keys)))
    reserve = len(SYSTEM) + len(head)

    plan = packer.plan(secs, budget_tokens or packer.DEFAULT_BUDGET_TOKENS, reserve_chars=reserve)
    context = "\n\n".join(s["text"].strip() for s in plan["sent"])
    user = head + context + "\n"

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "rubric", "text": schema},
        {"name": "document sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            plan)


# The exact sentence rule 4 asks for. Matched loosely on the way back in — a model that writes
# "Not stated in the document" has still refused, and scoring that as a written section would be
# the harsher error of the two.
_ABSENT = re.compile(r"^\s*not stated in (this|the) document\.?\s*$", re.I)


def is_absent(value):
    """Did the model decline this section? Distinguishes a REFUSAL from an empty string, which is
    a parsing failure, and from prose, which is an answer. Three states again, and collapsing any
    two of them is the same defect UC002's field table exists to avoid."""
    return bool(value) and bool(_ABSENT.match(str(value)))


def parse(raw, sections):
    """Pull the JSON object out of a model reply, tolerantly but never creatively.

    A model that wraps JSON in a fence or adds a sentence is handled. A model that returns
    something unparseable yields {} — every section then reads as "not written", which is the
    truthful rendering. It does NOT fall back to splitting the prose on the section names: that
    would turn a broken call into a mediocre brief, and the run record would show a working
    system. UC002 records paying for exactly that temptation.
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
    return {sec["key"]: obj.get(sec["key"]) for sec in sections}
