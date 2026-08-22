"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `verdict` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the terminal inspector's note and nothing else: a note carrying one of a
fixed list of concerned-sounding phrases means `refuse`, and anything else means `accept`. That is
precisely the shortcut the prompt's rules forbid -- deciding a compatibility verdict from prose
instead of from the matrix, the predecessor ban and the cleaning certificate.

⚑ AND NOTE WHAT A TONE READ CANNOT REACH AT ALL. `clean_then_load` and `undetermined` are the two
verdicts that carry the actual work of a pre-load check -- "this tank needs a specific regime
first" and "nobody can say yet" -- and no amount of reading a note produces either. The floor is
structurally incapable of them, which is the honest statement of what tone can do: it can express
alarm, and it cannot express a REQUIREMENT. 21 of this corpus's 55 sheets have a verdict the floor
cannot say.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes the incoming product, the grade, both cargoes and the certificate out of the
sheet; calling src.matrix.decide() on them would score 100 pct and tell you nothing about the
model. So the floor is deliberately the SHORTCUT, not the lookup, and the gap it opens is the gap
between reading prose and running the matrix.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a relaxed note, mis-registering four records for days before it
was caught. Every phrase here is multi-word or a stem that appears in one register only, and
evals/check_labels.py asserts that property before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived verdict produces a
tone-derived hold flag: the floor reads load_status correctly by regex every time and the verdict
wrong on the planted sheets, and the flag inherits the error. That is worth publishing rather than
hiding -- a business-condition guardrail is only ever as good as the field it reads.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any CALM note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("looked", "odour", "review") appears in BOTH
# registers on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("escalat", "not confident", "looked off", "disputed", "manual audit",
                    "second look", "faint odour", "reviewed again")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _cargo(raw):
    """A cargo section's body, or None where the sheet says there is nothing recorded."""
    if raw is None:
        return None
    low = raw.lower()
    if low.startswith("not recorded") or low.startswith("none --") or low.startswith("none -"):
        return None
    return raw


def _certificate(raw):
    """The regime a certificate actually covers, from the Cleaning Certificate section."""
    if raw is None:
        return None
    m = re.search(r"certified for:\s*(\S+)", raw)
    if m:
        return m.group(1)
    return "not_certified"


def extract_one(text, fields):
    tank_id = _section(text, "Tank")
    incoming_product = _section(text, "Incoming Product")
    incoming_grade = _section(text, "Incoming Grade")
    prior_cargo = _cargo(_section(text, "Prior Cargo"))
    two_back_cargo = _cargo(_section(text, "Two-Back Cargo"))
    wash_performed = _section(text, "Wash Performed")
    wash_certified_for = _certificate(_section(text, "Cleaning Certificate"))
    load_status = _section(text, "Load Status")
    inspector_notes = _section(text, "Inspector Notes")

    low = (inspector_notes or "").lower()
    verdict = "refuse" if any(k in low for k in WORRIED_KEYWORDS) else "accept"

    values = {
        "tank_id": tank_id, "incoming_product": incoming_product,
        "incoming_grade": incoming_grade, "prior_cargo": prior_cargo,
        "two_back_cargo": two_back_cargo, "wash_performed": wash_performed,
        "wash_certified_for": wash_certified_for, "load_status": load_status,
        "inspector_notes": inspector_notes, "verdict": verdict,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_hold": _compute(values), "recomputed_verdict": None,
            "recomputed_reason": None, "recomputed_required_wash": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
