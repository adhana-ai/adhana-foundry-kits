"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ THE COVERAGE ANSWER HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the payment coordinator's note and nothing else: a note carrying one of a
fixed list of worried-sounding phrases means "one party uncovered", and anything else means
"every party covered". That is precisely the shortcut the prompt's rules forbid -- deciding
coverage from prose instead of from the party blocks, the period-through date and the
prior-payment answer, in their priority order.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
party blocks are as regexable as everything else in this layout, and the coverage rule is five
comparisons over dates and amounts. A rules baseline that ran the rule would score 100 pct on
this corpus and tell you nothing about the model -- so the floor is deliberately the SHORTCUT,
not the rule, and the gap it opens is the gap between reading prose and running the comparison.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a breezy note, mis-registering four records for days before it was
caught. Two obvious candidates here -- "complete" and "looked" -- appear in BOTH registers on this
corpus ("it looked complete" is settled; "Not confident the waiver coverage is complete" is not),
so both were rejected in favour of longer phrases. evals/check_labels.py asserts the property
directly, before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived count produces a
tone-derived hold flag: the floor gets release_status right by regex every time and the coverage
count wrong on the planted packages, and the flag inherits the error. That is worth publishing
rather than hiding -- a business-condition guardrail is only ever as good as the field it reads,
which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute
from src.extract import self_check as _self_check

# Worried-sounding phrases, chosen so none of them is a substring of any BREEZY note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("complete", "looked", "review", "flag")
# appears in BOTH registers on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("escalat", "disputed", "manual audit", "not confident", "second look",
                    "second pass", "revisit", "looked thin", "looked off")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _money(s):
    """Split '175,244.74 USD' into 175244.74. Returns None when the line states no number."""
    if s is None:
        return None
    m = re.match(r"\s*([\d,]+(?:\.\d+)?)", s)
    return float(m.group(1).replace(",", "")) if m else None


def _first_party(text):
    m = re.search(r"^Party 1:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def extract_one(text, fields):
    package_id = _section(text, "Package")
    project_name = _section(text, "Project")
    pay_app_number = _section(text, "Pay Application")
    period_through = _section(text, "Period Through")
    payment_amount_usd = _money(_section(text, "Payment Amount"))
    prior_payment_cleared = _section(text, "Prior Payment Cleared")
    release_status = _section(text, "Release Status")
    coordinator_note = _section(text, "Coordinator Note")

    low = (coordinator_note or "").lower()
    worried = any(k in low for k in WORRIED_KEYWORDS)
    # THE SHORTCUT, stated plainly: one uncovered party when the note sounds worried, none when
    # it does not; the first party listed, and the most obvious reason. It never opens a party
    # block.
    parties_uncovered = 1 if worried else 0
    first_gap_party = _first_party(text) if worried else None
    first_gap_reason = "no_waiver_on_file" if worried else "none"

    values = {
        "package_id": package_id, "project_name": project_name,
        "pay_app_number": pay_app_number, "period_through": period_through,
        "payment_amount_usd": payment_amount_usd,
        "prior_payment_cleared": prior_payment_cleared, "release_status": release_status,
        "coordinator_note": coordinator_note, "parties_uncovered": parties_uncovered,
        "first_gap_party": first_gap_party, "first_gap_reason": first_gap_reason,
    }
    from src.extract import spannable as _spannable
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": _spannable(f),
                       "span": None} for f in fields}
    return {"fields": out, "needs_hold": _compute(values),
            "self_check": _self_check(values, text),
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
