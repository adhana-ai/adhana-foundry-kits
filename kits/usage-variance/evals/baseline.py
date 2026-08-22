"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `variance_cause` HERE IS A DELIBERATE NOTE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the billing analyst's note and nothing else: whichever cause the note names
is the answer, and a note that names none of them means "none". That is precisely the shortcut the
prompt's rules forbid -- deciding the cause from prose instead of from the five quantities and
their priority order.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
rule is about ten lines of integer arithmetic, and the baseline already regexes every quantity the
rule needs out of the document. A rules baseline that did the arithmetic would score 100 pct on
this corpus and tell you nothing about the model -- so the floor is deliberately the SHORTCUT, not
the rule, and the gap it opens is the gap between reading prose and doing the arithmetic.

⚠︎ THE KEYWORD TABLE WAS CHECKED AGAINST EVERY NOTE REGISTER BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a calm note ("nothing worth flagging"), mis-registering four
records for days before it was caught. evals/check_labels.py here asserts that every note template
in tools/build_corpus.py classifies to the register it was authored in -- and, because this floor
is a SIX-way classifier rather than a binary one, that no template matches two registers at once,
which is the failure mode a longer keyword table adds and a two-value one cannot have.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a note-derived cause produces a
note-derived credit flag: the floor gets invoice_status right by regex every time and the cause
wrong on the planted records, and the flag inherits the error. That is worth publishing rather
than hiding -- a business-condition guardrail is only ever as good as the field it reads, which is
the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# The order matters: the first register whose keyword appears wins. Phrases are chosen so that no
# template in tools/build_corpus.py matches more than one register -- asserted directly in
# evals/check_labels.py, not assumed.
NOTE_KEYWORDS = (
    ("duplicate_records", ("duplicate", "double-charged", "counted twice")),
    ("unrated_usage", ("unrated", "suspense", "failed rating", "rating error")),
    ("late_records", ("after the collection cutoff", "past cutoff", "prior-period usage")),
    ("rounding", ("rounding artefact", "billing increment")),
    ("unexplained", ("does not tie back", "cannot account")),
)


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '598133 KB' into 598133. Returns None when the line states no number at all."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+)\b", s)
    return int(m.group(1)) if m else None


def cause_from_note(note):
    """The floor's whole decision. First register whose keyword appears, else 'none'."""
    low = (note or "").lower()
    for cause, keys in NOTE_KEYWORDS:
        if any(k in low for k in keys):
            return cause
    return "none"


def extract_one(text, fields):
    line_id = _section(text, "Invoice Line")
    service_type = _section(text, "Service Type")
    billing_period = _section(text, "Billing Period")
    mediated = _units(_section(text, "Mediated Usage"))
    invoiced = _units(_section(text, "Invoiced Quantity"))
    unrated = _units(_section(text, "Unrated Usage"))
    prior = _units(_section(text, "Prior Period Usage"))
    confirmed = _units(_section(text, "Confirmed Duplicates"))
    invoice_status = _section(text, "Invoice Status")
    analyst_note = _section(text, "Analyst Note")

    values = {
        "line_id": line_id, "service_type": service_type, "billing_period": billing_period,
        "mediated_quantity": mediated, "invoiced_quantity": invoiced,
        "unrated_quantity": unrated, "prior_period_quantity": prior,
        "confirmed_duplicate_quantity": confirmed, "invoice_status": invoice_status,
        "analyst_note": analyst_note, "variance_cause": cause_from_note(analyst_note),
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_credit": _compute(values), "recomputed_variance_cause": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
