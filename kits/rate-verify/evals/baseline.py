"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `rate_correct` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the billing rep's account note and nothing else: a note carrying one of a
fixed list of concerned-sounding phrases means "no" (misrated), and anything else means "yes"
(correctly rated). That is precisely the shortcut the prompt's rules forbid -- deciding
correctness from prose instead of from the four structured values and their priority order.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
comparison is a few lines of arithmetic, and the baseline already regexes service_class,
meter_type, metered_usage_kwh and peak_demand_kw out of the document. A rules baseline that did
the comparison would score 100 pct on this corpus and tell you nothing about the model -- so the
floor is deliberately the SHORTCUT, not the rule, and the gap it opens is the gap between reading
prose and running the actual comparison.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a BREEZY note ("nothing worth flagging"), mis-registering four
records for days before it was caught. evals/check_labels.py here asserts the same register
property this floor's own list must satisfy, before any run may spend -- see the note there.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived `rate_correct`
produces a tone-derived review flag: the floor gets bill_status right by regex every time and the
correctness verdict wrong on the planted records, and the flag inherits the error. That is worth
publishing rather than hiding -- a business-condition guardrail is only ever as good as the field
it reads, which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any BREEZY note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("review", "flag") appears in BOTH registers
# on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("escalat", "misclassif", "manager review", "disputed", "manual audit",
                    "not confident", "second look", "looked off", "revisit")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '16820 kWh' into 16820. Returns None when the line states no number (e.g. the
    'not metered (residential account)' peak-demand line)."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+)\b", s)
    return int(m.group(1)) if m else None


def extract_one(text, fields):
    account_id = _section(text, "Account")
    service_class = _section(text, "Service Class")
    meter_type = _section(text, "Meter Type")
    billing_period = _section(text, "Billing Period")
    metered_usage_kwh = _units(_section(text, "Metered Usage"))
    peak_demand_kw = _units(_section(text, "Peak Demand"))
    applied_rate_code = _section(text, "Applied Rate Code")
    bill_status = _section(text, "Bill Status")
    account_notes = _section(text, "Account Notes")

    low = (account_notes or "").lower()
    correct = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"

    values = {
        "account_id": account_id, "service_class": service_class, "meter_type": meter_type,
        "billing_period": billing_period, "metered_usage_kwh": metered_usage_kwh,
        "peak_demand_kw": peak_demand_kw, "applied_rate_code": applied_rate_code,
        "bill_status": bill_status, "account_notes": account_notes, "rate_correct": correct,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values), "recomputed_rate_correct": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
