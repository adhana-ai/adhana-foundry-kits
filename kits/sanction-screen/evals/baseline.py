"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `verdict` HERE IS A DELIBERATE TONE FLOOR, AND UNLIKE MOST FLOORS IN THIS SERIES IT CAN REACH
ALL THREE ANSWERS. It reads the triaging analyst's note and nothing else: a hedging phrase means
`insufficient_information`, a dismissive phrase means `not_a_match`, and anything else means
`same_party`. That is precisely the shortcut the prompt's rules forbid -- adjudicating an alert
from somebody's impression instead of from the identifiers.

Giving the floor access to the third verdict matters. A floor that could only say two things would
fail this corpus's fifteen undecidable alerts BY CONSTRUCTION, and the resulting number would be an
artefact of the floor's vocabulary rather than a fact about reading tone. This floor is allowed to
say "I cannot tell" whenever the note does, which makes its false-confidence count a real
measurement.

⚑ WHY THE FLOOR IS SO BAD HERE, AND WHY THAT IS THE FINDING RATHER THAN A RIGGED GAME. The note's
register on this corpus follows the screening ENGINE'S NAME SCORE -- the analyst wrote it having
seen two names and a similarity number, before anybody compared identifiers. Name similarity is
decorrelated from identity here for the same reason screening false positives exist: the alerts
whose names look most alike are frequently the ones the identifiers separate, and the alerts whose
names look least alike are frequently one party behind a transliteration. So a tone read does not
merely lose accuracy, it can score BELOW CHANCE, and the direction of its errors is worse than the
rate.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes both identifier types, both values, both dates and both places out of the
sheet; calling src.rulebook.decide() on them would score 100 pct and tell you nothing about the
model. So the floor is deliberately the SHORTCUT, not the lookup, and the gap it opens is the gap
between reading somebody's impression and comparing identifiers.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST ALL THREE NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN,
NOT AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword
("flagging") that fired on a negation inside a relaxed note, mis-registering four records for days
before it was caught. Every phrase here is multi-word, and evals/check_labels.py asserts that every
note template classifies to the register it was authored in before any run may spend. Note the trap
this corpus contains on purpose: a CONFIDENT note reads "I am satisfied these are the same party",
and the dismissive keyword is the whole negated phrase "not the same party" -- a single-word list
would have fired on it.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived verdict produces a
tone-derived escalation flag: the floor reads account_status correctly by regex every time and the
verdict wrong on most sheets, and the flag inherits the error. That is worth publishing rather than
hiding -- a business-condition guardrail is only ever as good as the field it reads.
"""
import re

from src.extract import compute as _compute
from src import rulebook as RB

# Multi-word phrases, chosen so that no phrase from one register appears in a note written in
# another. Checked directly against all three note lists in evals/check_labels.py, not assumed.
HEDGING_KEYWORDS = ("cannot separate", "not enough here", "cannot land it",
                    "second identifier before")
DISMISSIVE_KEYWORDS = ("different person", "would close this one", "coincidence of names",
                       "not the same party")

IDENTIFIER_BY_LABEL = {"passport number": "passport_number",
                       "national identity number": "national_id_number",
                       "tax reference": "tax_reference"}


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _line(section, label):
    if section is None:
        return None
    m = re.search(r"^%s:\s*(.+)$" % re.escape(label), section, re.M)
    return m.group(1).strip() if m else None


def _absent(value):
    """The two ways a sheet says a field is not there. A PARTIAL date is not one of them."""
    return value is None or value.lower() in ("not recorded", "not published")


def _stated_or_none(value):
    return None if _absent(value) else value


def _identifier(section):
    """(type, value) off a Customer Record or Watchlist Entry section."""
    if section is None:
        return "none", None
    for label, kind in IDENTIFIER_BY_LABEL.items():
        m = re.search(r"^%s:\s*(.+)$" % re.escape(label), section, re.M | re.I)
        if m:
            return kind, m.group(1).strip()
    return "none", None


def extract_one(text, fields):
    cust = _section(text, "Customer Record")
    listed = _section(text, "Watchlist Entry")

    customer_identifier_type, customer_identifier_value = _identifier(cust)
    listed_identifier_type, listed_identifier_value = _identifier(listed)

    note = _section(text, "Analyst Note")
    low = (note or "").lower()
    if any(k in low for k in HEDGING_KEYWORDS):
        verdict = "insufficient_information"
    elif any(k in low for k in DISMISSIVE_KEYWORDS):
        verdict = "not_a_match"
    else:
        verdict = "same_party"

    # ⚑ THE FLOOR NAMES A REASON TOO, AND IT HAS NONE TO GIVE. Tone cannot point at an identifier,
    # so the floor answers `none` whenever it says it cannot tell and otherwise names the strong
    # identifier type it happened to regex -- which is a guess dressed as a citation, and the
    # deciding-identifier grader is what measures how bad a guess it is.
    if verdict == "insufficient_information":
        deciding = "none"
    elif customer_identifier_type != "none":
        deciding = customer_identifier_type
    elif listed_identifier_type != "none":
        deciding = listed_identifier_type
    else:
        deciding = "date_of_birth_and_place_of_birth"

    values = {
        "alert_id": _section(text, "Alert Reference"),
        "customer_name": _line(cust, "Name"),
        "listed_name": _line(listed, "Listed Name"),
        "customer_identifier_type": customer_identifier_type,
        "customer_identifier_value": customer_identifier_value,
        "listed_identifier_type": listed_identifier_type,
        "listed_identifier_value": listed_identifier_value,
        "customer_dob": _stated_or_none(_line(cust, "Date of Birth")),
        "listed_dob": _stated_or_none(_line(listed, "Date of Birth")),
        "customer_place_of_birth": _stated_or_none(_line(cust, "Place of Birth")),
        "listed_place_of_birth": _stated_or_none(_line(listed, "Place of Birth")),
        "customer_nationality": _line(cust, "Nationality"),
        "listed_nationality": _line(listed, "Nationality"),
        "account_status": _section(text, "Account Status"),
        "analyst_note": note,
        "verdict": verdict if verdict in RB.VERDICTS else None,
        "deciding_identifier": deciding,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_escalation": _compute(values), "recomputed_verdict": None,
            "recomputed_deciding_identifier": None, "recomputed_reason": None,
            "recomputed_would_settle_it": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
