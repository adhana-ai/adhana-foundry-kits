"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `claim_valid` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the property reviewer's note and nothing else: a note carrying one of a
fixed list of disputing phrases means "no" (not owed as claimed), and anything else means "yes"
(owed as claimed). That is precisely the shortcut the prompt's rules forbid -- deciding validity
from prose instead of from the folio's own numbers in their priority order.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
computation is five branches and one multiplication, and the baseline already regexes every value
it needs out of the document. A rules baseline that did the computation would score 100 pct on
this corpus and tell you nothing about the model -- so the floor is deliberately the SHORTCUT, not
the rule, and the gap it opens is the gap between reading prose and running the arithmetic.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a settled note ("nothing worth flagging"), mis-registering four
records for days before it was caught. evals/check_labels.py here asserts the same register
property this floor's own list must satisfy, before any run may spend -- see the note there.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived `claim_valid`
produces a tone-derived recovery flag: the floor gets invoice_status right by regex every time and
the validity verdict wrong on the planted records, and the flag inherits the error. That is worth
publishing rather than hiding -- a business-condition guardrail is only ever as good as the field
it reads, which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# Disputing phrases, chosen so none of them is a substring of any ACCEPTING note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("review", "check", "line") appears in BOTH
# registers on this corpus and would misfire either way.
DISPUTING_KEYWORDS = ("flagged by", "disputed", "not confident", "looked off", "second look",
                      "revisit", "looked high", "awaiting their response")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _money(s):
    """Split '482.36 USD' into 482.36, and '17.5 pct' into 17.5. Returns None when the line states
    no number at all -- the 'not applicable (...)' refund and penalty lines."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\b", s)
    return float(m.group(1)) if m else None


def extract_one(text, fields):
    values = {
        "claim_id": _section(text, "Claim Line"),
        "confirmation_number": _section(text, "Confirmation Number"),
        "folio_status": _section(text, "Folio Status"),
        "booking_source": _section(text, "Booking Source"),
        "room_revenue_usd": _money(_section(text, "Room Revenue")),
        "room_revenue_refunded_usd": _money(_section(text, "Room Revenue Refunded")),
        "non_room_charges_usd": _money(_section(text, "Non-Room Charges")),
        "penalty_charged_usd": _money(_section(text, "Cancellation Penalty")),
        "contract_rate_pct": _money(_section(text, "Contract Rate")),
        "claimed_commission_usd": _money(_section(text, "Claimed Commission")),
        "already_commissioned": _section(text, "Previously Commissioned"),
        "invoice_status": _section(text, "Invoice Status"),
        "reviewer_note": _section(text, "Reviewer Note"),
    }
    low = (values["reviewer_note"] or "").lower()
    values["claim_valid"] = "no" if any(k in low for k in DISPUTING_KEYWORDS) else "yes"

    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_recovery": _compute(values), "recomputed_claim_valid": None,
            "recomputed_owed_usd": None, "sections_used": [], "prompt_parts": [],
            "input_tokens": 0, "output_tokens": 0, "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
