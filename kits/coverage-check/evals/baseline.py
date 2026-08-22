"""A free, rules-and-regex adjudicator. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `covered` AND `narrative_finding` HERE ARE A DELIBERATE TWO-PART SHORTCUT, WRITTEN TO FAIL THE
PLANTED CONFUSIONS BY CONSTRUCTION:

  - `narrative_finding` is copied from the CODED `Cause Code` field, mapped one-for-one. That is
    precisely what the prompt forbids: the coded cause is the dealer's own classification, and on
    12 of these 55 claims it disagrees with what the technician actually describes.
  - `covered` is decided from the technician's CLOSING OPINION -- a fixed list of
    denial-sounding phrases means "no", anything else means "yes". That is the other thing the
    prompt forbids: deciding coverage from prose instead of from the six-branch rule.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
rule is thirty lines of arithmetic and dictionary lookups, and the baseline already regexes every
value it needs -- the plan, both dates, the odometer, the component and the labor operation. A
rules baseline that ran the rule would score 100 pct on this corpus and tell you nothing about the
model. So the floor is deliberately the SHORTCUT, not the rule, and the gap it opens is the gap
between reading the loudest text on the page and applying the coverage terms.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH OPINION REGISTERS BEFORE THIS FLOOR WAS FIRST RUN,
NOT AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword
("flagging") that fired on a negation inside a positive note, mis-registering four records for
days before it was caught. evals/check_labels.py here asserts the same register property this
floor's own list must satisfy, before any run may spend -- see the note there.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so an opinion-derived `covered`
produces an opinion-derived recovery flag: the floor gets claim_status right by regex every time
and the verdict wrong on the planted records, and the flag inherits the error. That is worth
publishing rather than hiding -- a business-condition guardrail is only ever as good as the field
it reads, which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute
from src.extract import months_between as _months

# Denial-sounding phrases from the technician's closing opinion, chosen so none of them is a
# substring of any PRO-coverage opinion in tools/build_corpus.py -- checked directly against both
# lists, not assumed. Multi-word phrases are used deliberately: single words like "covered" and
# "term" appear in BOTH registers on this corpus and would misfire either way.
DENIAL_KEYWORDS = ("gets denied", "doubt this one gets paid", "out of term",
                   "would not expect coverage", "going to bounce", "too far along",
                   "customer may be paying")

# The floor's second shortcut: the coded cause, mapped straight onto a finding.
CAUSE_TO_FINDING = {
    "defect": "defect",
    "damage": "collision_damage",
    "modification": "unauthorized_modification",
    "maintenance": "missed_maintenance",
}


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '48210 miles' into 48210. Returns None when the line states no number."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+)\b", s)
    return int(m.group(1)) if m else None


def extract_one(text, fields):
    claim_id = _section(text, "Claim")
    vehicle_line = _section(text, "Vehicle") or ""
    m = re.search(r"(VEH-[A-Z0-9-]+)", vehicle_line)
    vehicle_id = m.group(1) if m else None
    coverage_plan = _section(text, "Coverage Plan")
    in_service_date = _section(text, "In-Service Date")
    repair_date = _section(text, "Repair Date")
    odometer_miles = _units(_section(text, "Odometer"))
    failed_component = _section(text, "Failed Component")
    claimed_labor_op = _section(text, "Claimed Labor Operation")
    cause_code = _section(text, "Cause Code")
    claim_status = _section(text, "Claim Status")
    narrative = _section(text, "Technician Narrative")

    # The floor DOES do the date arithmetic -- it is a regex and two integers, and pretending it
    # cannot would flatter the model on a field that has nothing to do with the shortcut.
    months_in_service = _months(in_service_date, repair_date)

    low = (narrative or "").lower()
    covered = "no" if any(k in low for k in DENIAL_KEYWORDS) else "yes"
    narrative_finding = CAUSE_TO_FINDING.get(cause_code)

    values = {
        "claim_id": claim_id, "vehicle_id": vehicle_id, "coverage_plan": coverage_plan,
        "in_service_date": in_service_date, "repair_date": repair_date,
        "months_in_service": months_in_service, "odometer_miles": odometer_miles,
        "failed_component": failed_component, "claimed_labor_op": claimed_labor_op,
        "cause_code": cause_code, "claim_status": claim_status,
        "technician_narrative": narrative, "narrative_finding": narrative_finding,
        "covered": covered,
    }
    out = {f["name"]: {"value": values.get(f["name"]),
                       "spannable": f.get("type") != "enum" and f["name"] != "months_in_service",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values), "recomputed_covered": None,
            "recomputed_months": None, "sections_used": [], "prompt_parts": [],
            "input_tokens": 0, "output_tokens": 0, "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
