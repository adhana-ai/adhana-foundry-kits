"""TWO free, rules-and-regex extractors. No model, no key, no spend -- scored by the same judge as
a paid run, so all three are directly comparable.

⚑ WHY TWO FLOORS, WHERE EVERY SIBLING KIT SHIPS ONE. This corpus plants TWO ambiguities and they
are orthogonal, so one floor could only ever convict one of them:

  THE TONE FLOOR (`tone`) reads the property accountant's note and nothing else: a note carrying
  one of a fixed list of concerned-sounding phrases means "no" (billed wrong), and anything else
  means "yes". That is precisely the shortcut the prompt's rules forbid -- deciding from prose
  instead of from the arithmetic. It cannot produce `permitted_amount_usd` at all and returns null
  for it, which is honest: a shortcut that reads tone has no number to offer.

  THE NAME FLOOR (`name`) is the more interesting one, and it is deliberately GOOD. It does every
  piece of arithmetic in this kit correctly -- the gross-up, the weighted-average pro-rata share,
  the compounded cumulative cap, all of it, off the same src/rule.py the paid run is graded by. It
  gets ONE thing wrong: it decides what is poolable from what the expense is CALLED rather than
  from `expense_class`. A category whose name reads capital, or landlord's-own, or leasing gets
  zero; everything else gets its whole pool.

⚠︎ IT WOULD BE TRIVIAL TO MAKE EITHER FLOOR PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
name floor is three characters away from correct -- read `expense_class` instead of
`expense_category` and it scores 100 pct. Leaving it wrong is what turns "the class decides, not
the name" from an instruction in a prompt into a measured number of dollars.

⚠︎ BOTH KEYWORD LISTS WERE CHECKED AGAINST THE CORPUS'S OWN VOCABULARY BEFORE EITHER FLOOR WAS
FIRST RUN, NOT AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a
keyword ("flagging") that fired on a negation inside a breezy note ("nothing worth flagging"),
mis-registering four records for days before it was caught. evals/check_labels.py here asserts
BOTH properties -- every note template classifies to the register it was written as, and every
expense category classifies to the family it was authored in -- before any run may spend.

⚠︎ AND NOTE WHAT EACH FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
a floor's own output exactly as it is run over a model's, so a tone-derived verdict produces a
tone-derived review flag, and a name-derived permitted amount produces a name-derived one. Both
floors read `statement_status` correctly by regex every single time and the flag still fails, which
is worth publishing rather than hiding: a business-condition guardrail is only ever as good as the
fields it reads.
"""
import re

from src.extract import compute as _compute
from src.rule import (cap_ceiling, grossed_up, line_is_ok, prorata_share)

# Concerned-sounding phrases, chosen so none of them is a substring of any breezy note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("review", "line") appears in BOTH registers
# on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("queried", "not confident", "looked off", "escalated", "disputed",
                    "expect pushback", "second look", "revisit before release")

# Words that make an expense CATEGORY read like an exclusion. This list is the name floor's whole
# theory of the lease, and it is a theory about vocabulary rather than about the lease.
NAME_EXCLUDE_KEYWORDS = ("resurfacing", "reconstruction", "replacement", "retrofit",
                         "modernisation", "overhaul", "patching", "membrane", "sealing",
                         "landlord", "management fee", "home-office", "leasing", "brokerage",
                         "tenant improvement", "marketing")

MODES = ("tone", "name")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '47800.00 USD' into 47800.0, or '86 pct' into 86.0. Returns None when the line states
    no number at all -- the 'not amortizable under this lease' and 'no expansion this
    reconciliation year' lines, which are absences rather than zeroes."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\b", s)
    if not m:
        m = re.search(r"\b(\d+)\b", s)          # 'month 7', 'a 5 periods' style lines
    return float(m.group(1)) if m else None


def name_says_excluded(category):
    """The name floor's whole theory: does this expense's NAME read like an exclusion?"""
    low = (category or "").lower()
    return any(k in low for k in NAME_EXCLUDE_KEYWORDS)


def _read(text):
    """Every structured value, by regex. Both floors share this; they differ only in what they do
    with `expense_category` and `expense_class` afterwards."""
    exp_area = _section(text, "Expansion Area")
    exp_month = _section(text, "Expansion Month")
    cap_pct = _section(text, "Cap Percent")
    cap_basis = _section(text, "Cap Basis")
    cap_years = _section(text, "Cap Periods")
    return {
        "line_id": _section(text, "Statement Line"),
        "expense_category": _section(text, "Expense Category"),
        "expense_class": _section(text, "Expense Class"),
        "pool_gross_usd": _units(_section(text, "Pool Gross Cost")),
        "amortization_years": _units(_section(text, "Amortization Years")),
        "occupancy_sensitive": _section(text, "Occupancy Sensitive"),
        "building_occupancy_pct": _units(_section(text, "Building Occupancy")),
        "building_area_sf": _units(_section(text, "Building Area")),
        "tenant_area_sf": _units(_section(text, "Tenant Area")),
        "expansion_area_sf": _units(exp_area),
        "expansion_month": _units(exp_month),
        "cap_type": _section(text, "Cap Type"),
        "cap_pct": _units(cap_pct),
        "cap_basis_usd": _units(cap_basis),
        "cap_years": _units(cap_years),
        "billed_to_tenant_usd": _units(_section(text, "Billed To Tenant")),
        "statement_status": _section(text, "Statement Status"),
        "accountant_note": _section(text, "Accountant Notes"),
    }


def _name_floor_permitted(v):
    """Stages 2, 3 and 4 exactly as src/rule.py does them -- and stage 1 by the category NAME.

    ⚑ THE ONLY WRONG LINE IN THIS FUNCTION IS THE FIRST ONE. Everything below it is imported from
    the same module the paid run is graded against, so nothing here is a second, sloppier
    implementation whose failures could be blamed on the floor being badly written.
    """
    pool = 0.0 if name_says_excluded(v["expense_category"]) else v["pool_gross_usd"]
    if pool is None:
        return None
    pool = grossed_up(pool, v["occupancy_sensitive"], v["building_occupancy_pct"])
    share = prorata_share(v["building_area_sf"], v["tenant_area_sf"],
                          v["expansion_area_sf"], v["expansion_month"])
    if pool is None or share is None:
        return None
    amount = pool * share
    ceiling = cap_ceiling(v["cap_type"], v["cap_pct"], v["cap_basis_usd"], v["cap_years"])
    if ceiling is not None:
        amount = min(amount, ceiling)
    return round(amount, 2)


def extract_one(text, fields, mode="tone"):
    if mode not in MODES:
        raise ValueError("unknown baseline mode %r -- one of %s" % (mode, ", ".join(MODES)))
    values = _read(text)

    if mode == "tone":
        low = (values["accountant_note"] or "").lower()
        values["permitted_amount_usd"] = None
        values["line_ok"] = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"
    else:
        permitted = _name_floor_permitted(values)
        values["permitted_amount_usd"] = permitted
        values["line_ok"] = line_is_ok(values["billed_to_tenant_usd"], permitted)

    out = {f["name"]: {"value": values.get(f["name"]),
                       "spannable": f.get("type") != "enum" and not f.get("computed"),
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values),
            "recomputed_permitted_usd": None, "recomputed_line_ok": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields, mode="tone"):
    return extract_one(text, fields, mode=mode)
