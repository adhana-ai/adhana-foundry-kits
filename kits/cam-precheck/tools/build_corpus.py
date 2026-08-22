#!/usr/bin/env python3
"""Generate synthetic CAM reconciliation line records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one reconciliation line per file) and data/gold.jsonl, byte-identical on
every run. Every property, tenant, managing agent and accountant note here is invented -- nothing
is fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.
No real lease, real landlord, real tenant or real published lease form is named or reproduced. See
data/SOURCES.md.

⚑ GOLD IS AN ARITHMETIC PIPELINE, NOT A LABEL SOMEBODY TYPED. `permitted_amount_usd` is derived
from the same values the record itself states, run through the same four-stage rule the kit
publishes everywhere else, and `line_ok` is the comparison of that figure against what the landlord
actually billed:

    permitted = cap( prorata( grossup( poolable( class, gross, amortization ) ) ) )
    line_ok   = "yes" iff |billed - permitted| <= 1.00

It is never derived from the property accountant's note, and the note never feeds either label.

⚑ THE FOUR STAGES, AND WHY EACH HAS A TRAP.

  1. POOLABLE. Landlord overhead and leasing costs are out entirely. A capital improvement is out
     entirely UNLESS the lease permits amortizing it -- and then the poolable figure is ONE ANNUAL
     INSTALMENT, gross / years, not the whole cost and not zero. That middle case is the one a
     reader who has learned "capital is excluded" gets wrong in the expensive direction.
  2. GROSS-UP. An occupancy-sensitive expense in a building below the 95 pct gross-up floor is
     scaled UP to what it would have cost at 95 pct occupancy, because the tenants who are there
     should not carry the vacancy's discount. An expense that does NOT vary with occupancy -- the
     insurance premium, the property tax bill -- must NOT be grossed up, and grossing it up is an
     overcharge that looks exactly like diligence.
  3. PRO RATA. The tenant's share is its area over the building's. A mid-year expansion makes that
     a WEIGHTED AVERAGE over the year, not the starting area (an undercharge) and not the expanded
     area applied to all twelve months (an overcharge). Both wrong answers are one number away
     from the right one.
  4. CAP. An annual cap ceilings this year at the prior year plus the cap percentage. A cumulative
     cap ceilings it at the BASE year COMPOUNDED over the periods since -- applying it once, as
     though it were an annual cap, undercharges. And the sharpest case in the corpus: a cap that
     does not bind on the ungrossed share and DOES bind once the gross-up is applied, so anyone who
     skips stage 2 never discovers that stage 4 was going to change the answer.

⚑ THE PLANTED AMBIGUITY, TWICE OVER.

  (a) THE NOTE. The property accountant's own note contradicts the arithmetic on `N_AMBIGUOUS` of
      records -- a materially overbilled line carrying "Line agrees to the GL detail, no issues
      noted."; a line billed exactly right carrying "Tenant's auditor queried this line last year
      -- expect pushback." Anything that classifies off the note's TONE -- including
      evals/baseline.py, deliberately -- fails those records by construction.

  (b) THE CATEGORY NAME. `N_DECOY_CATEGORY` records carry an expense CATEGORY whose name reads like
      an exclusion -- "Parking lot resurfacing", "Property management fee", "Roof membrane
      patching" -- while the record's own `expense_class` says `routine_operating`. The class field
      decides, not the name. A reader who excludes anything that sounds like a capital project or
      like the landlord's own cost writes zero where the lease permits the whole line.
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# ⚑ THE RULE IS IMPORTED, NOT RESTATED. src/rule.py is the only copy in this kit -- the
# generator that writes gold, the prompt that states it to the model in words, the extractor that
# re-runs it over the model's own values and the scorer that re-derives gold's truth at score time
# all read those same functions. The sibling kit this one is modelled on kept the same logic in TWO
# files under a comment saying they were the same function. They were, and nothing enforced it; a
# rule with two copies is two rules waiting to disagree.
from src.rule import (MATERIALITY_USD, TOLERANCE_USD,          # noqa: E402
                      grossed_up, line_is_ok, permitted_amount,
                      poolable_amount, prorata_share)
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the same discipline the
# sibling kit immediately before this one in the series (rate-verify) adopted after a kit two
# earlier asked for 40 pct ambiguity and delivered 51 pct. A count 1.7 standard deviations off its
# own design is not a corpus property, it is sampling noise being published as one.
N_AMBIGUOUS = 22                   # 40 pct, exactly -- an accountant note from the wrong register
N_ISSUED = 33                      # statement_status == "issued"; the rest are still "draft"
N_DECOY_CATEGORY = 14              # a category NAME that reads excludable on a routine line

# ⚑ THE GROSS-UP FLOOR, TOLERANCE_USD and MATERIALITY_USD all come from src/rule.py, imported
# above. The materiality floor is why no `line_ok` label in this corpus is a coin flip on the last
# cent: every fault below is asserted to move the billed figure by at least that much, so a model
# whose arithmetic is a little loose still gets the verdict right and the corpus measures reasoning
# rather than floating-point luck.

# Invented managing agents. Nothing here is a real firm.
AGENTS = [
    "Northgate Asset Services",
    "Cobblestone Property Management",
    "Vantage Point Realty Services",
    "Harborline Commercial Management",
    "Stonebrook Property Group",
    "Fairmount Estates Management",
]

# Categories that plainly ARE routine operating expenses.
PLAIN_OPERATING = [
    "Landscaping and grounds maintenance",
    "Snow and ice removal",
    "Common area janitorial",
    "Common area utilities",
    "Security services",
    "Elevator maintenance contract",
    "Pest control",
]

# ⚑ CATEGORIES THAT READ LIKE AN EXCLUSION AND ARE NOT. Every one of these sounds like a capital
# project, the landlord's own cost, or a leasing cost -- and on these records the `expense_class`
# field says `routine_operating`, which is what decides. This is the second planted ambiguity and
# it is orthogonal to the note: a reader can resist the note and still exclude the line on its name.
DECOY_OPERATING = [
    "Parking lot resurfacing",
    "Roof membrane patching",
    "Property management fee",
    "HVAC compressor overhaul",
    "Facade cleaning and sealing",
    "Marketing and promotion fund",
]

CAPITAL_CATEGORIES = [
    "Parking lot reconstruction",
    "Roof replacement",
    "Chiller plant replacement",
    "LED lighting retrofit",
    "Fire alarm system replacement",
    "Elevator modernisation",
]

OVERHEAD_CATEGORIES = [
    "Landlord corporate overhead allocation",
    "Asset management fee to the landlord",
    "Landlord home-office salaries",
]

LEASING_CATEGORIES = [
    "Leasing commissions",
    "Tenant improvement allowance",
    "Vacant space marketing and brokerage",
]

# Notes whose TONE says "this line is fine". Used truthfully on a correctly billed line, and
# against type on a materially wrong one -- half the planted ambiguity.
BREEZY_NOTES = [
    "Line agrees to the GL detail, no issues noted.",
    "Recomputed at close and it ties out; nothing further needed here.",
    "Routine line for this property, consistent with the prior cycle.",
    "Reviewed with the property accountant, all in order.",
]

# Notes whose TONE says "something is wrong with this line". Used truthfully on a wrong line, and
# against type on one billed exactly right -- the other half.
CONCERNED_NOTES = [
    "Tenant's auditor queried this line last cycle -- expect pushback on it again.",
    "Not confident the exclusion schedule was applied here; needs a second look.",
    "Something looked off when this line was recomputed -- revisit before release.",
    "Escalated for manager review; the allocation basis on this line is disputed.",
]

CLASSES = ("routine_operating", "capital_improvement", "landlord_overhead", "leasing_cost")

# The eight ways a billed figure goes wrong here. Each is a REAL miscomputation of one stage --
# never a random number -- so the wrong figure is the one a person actually arrives at.
FAULTS = [
    ("capital_full_cost", 4),             # amortizable capital billed at its whole cost
    ("excluded_billed", 4),               # an excluded line pooled as though it were operating
    ("grossup_missing", 4),               # occupancy-sensitive line not grossed up
    ("grossup_wrong_class", 3),           # a fixed expense grossed up anyway
    ("cap_ignored", 5),                   # the cap binds and the uncapped share was billed
    ("cap_not_compounded", 3),            # a cumulative cap applied once, as though annual
    ("prorata_start_area", 3),            # mid-year expansion ignored
    ("prorata_full_year_expansion", 2),   # mid-year expansion applied to all twelve months
]
N_WRONG = sum(n for _f, n in FAULTS)
N_CORRECT = N_RECORDS - N_WRONG

# Shapes a CORRECTLY billed line can take. "Correct" must not be only the easy interior of the
# rule, or the corpus proves nothing about the hard branches -- so every trap appears on both
# sides of the verdict.
CORRECT_SHAPES = [
    ("amortized_capital", 4),          # capital, amortizable, billed at one instalment's share
    ("excluded_zero", 3),              # correctly not charged at all
    ("grossup_applied", 4),            # grossed up correctly
    ("cap_binding", 3),                # cap binds and the ceiling was billed
    ("cap_binds_after_grossup", 3),    # ⚑ the sharpest: slack before gross-up, binding after
    ("cumulative_cap", 3),             # compounded correctly over several periods
    ("expansion", 4),                  # weighted-average area, correctly
    ("plain", 3),                      # nothing special, so the corpus is not all edge case
]


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs, padded with the first
    pair's value if the counts fall short. Deterministic under the seeded RNG."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


# Drawing one record.
# --------------------------------------------------------------------------------------------

def _base_facts(rng):
    """The property-and-tenant facts every record carries, whatever its shape."""
    building_area = rng.randrange(90000, 420001, 100)
    tenant_area = rng.randrange(4000, min(38000, building_area // 4) + 1, 100)
    return {"building_area_sf": building_area, "tenant_area_sf": tenant_area}


def _no_cap():
    return {"cap_type": "none", "cap_pct": None, "cap_basis_usd": None, "cap_years": None}


def _no_expansion():
    return {"expansion_area_sf": None, "expansion_month": None}


def _expansion(rng, f):
    month = rng.randint(3, 10)
    area = rng.randrange(1200, min(9000, f["building_area_sf"] // 12) + 1, 100)
    return {"expansion_area_sf": area, "expansion_month": month}


def _set_cap(rng, f, target_ceiling, cap_type):
    """Work BACKWARDS from the ceiling we want to the basis the document will state, then let
    permitted_amount() recompute forwards from the rounded basis actually written. The document is
    always the source of truth; nothing is carried in memory that the record does not state."""
    pct = rng.choice([3, 4, 5])
    if cap_type == "annual":
        years = None
        basis = target_ceiling / (1.0 + pct / 100.0)
    else:
        years = rng.randint(2, 6)
        basis = target_ceiling / (1.0 + pct / 100.0) ** years
    return {"cap_type": cap_type, "cap_pct": pct, "cap_basis_usd": round(basis, 2),
            "cap_years": years}


def _share_amount(f, skip_grossup=False):
    """The tenant's share after stages 1-3, before any cap. Used to place a cap ceiling."""
    pool = poolable_amount(f["expense_class"], f["pool_gross_usd"], f["amortization_years"])
    if not skip_grossup:
        pool = grossed_up(pool, f["occupancy_sensitive"], f["building_occupancy_pct"])
    return pool * prorata_share(f["building_area_sf"], f["tenant_area_sf"],
                                f["expansion_area_sf"], f["expansion_month"])


def _operating_line(rng, occupancy_sensitive, below_floor):
    return {"expense_class": "routine_operating",
            "pool_gross_usd": float(rng.randrange(18000, 260001, 100)),
            "amortization_years": None,
            "occupancy_sensitive": occupancy_sensitive,
            "building_occupancy_pct": (rng.randint(78, 94) if below_floor
                                       else rng.randint(95, 100))}


def draw(rng, shape):
    """One record's facts, for a named shape. `shape` is either a fault name or a correct shape."""
    f = _base_facts(rng)
    f.update(_no_expansion())
    f.update(_no_cap())

    # ---- the shapes that need a capital line
    if shape in ("capital_full_cost", "amortized_capital"):
        f.update({"expense_class": "capital_improvement",
                  "expense_category": rng.choice(CAPITAL_CATEGORIES),
                  "pool_gross_usd": float(rng.randrange(120000, 900001, 500)),
                  "amortization_years": rng.choice([5, 7, 10, 12, 15]),
                  "occupancy_sensitive": "no",
                  "building_occupancy_pct": rng.randint(82, 100)})
        return f

    # ---- the shapes that need an excluded line
    if shape in ("excluded_billed", "excluded_zero"):
        kind = rng.choice(["landlord_overhead", "leasing_cost", "capital_no_amort"])
        if kind == "capital_no_amort":
            f.update({"expense_class": "capital_improvement",
                      "expense_category": rng.choice(CAPITAL_CATEGORIES),
                      "pool_gross_usd": float(rng.randrange(120000, 900001, 500)),
                      "amortization_years": None})
        else:
            f.update({"expense_class": kind,
                      "expense_category": rng.choice(OVERHEAD_CATEGORIES if
                                                     kind == "landlord_overhead"
                                                     else LEASING_CATEGORIES),
                      "pool_gross_usd": float(rng.randrange(18000, 240001, 100)),
                      "amortization_years": None})
        f.update({"occupancy_sensitive": "no", "building_occupancy_pct": rng.randint(82, 100)})
        return f

    # ---- everything else is an operating line; the shape decides the rest
    if shape in ("grossup_missing", "grossup_applied"):
        f.update(_operating_line(rng, "yes", below_floor=True))
        return f

    if shape == "grossup_wrong_class":
        # A fixed expense in a partially-vacant building: the gross-up is available to be applied
        # and MUST NOT be. Nothing on the record says "do not gross this up" except its own class.
        f.update(_operating_line(rng, "no", below_floor=True))
        return f

    if shape in ("prorata_start_area", "prorata_full_year_expansion", "expansion"):
        f.update(_operating_line(rng, rng.choice(["yes", "no"]), below_floor=rng.random() < 0.4))
        f.update(_expansion(rng, f))
        return f

    if shape in ("cap_ignored", "cap_binding"):
        f.update(_operating_line(rng, rng.choice(["yes", "no"]), below_floor=rng.random() < 0.5))
        share = _share_amount(f)
        f.update(_set_cap(rng, f, share * rng.uniform(0.78, 0.92), "annual"))
        return f

    if shape == "cap_binds_after_grossup":
        # ⚑ THE SHARPEST RECORD IN THIS CORPUS. The ceiling is placed strictly BETWEEN the
        # ungrossed share and the grossed-up share, so a reader who skips the gross-up sees a cap
        # with slack in it and never applies it -- and lands on the ungrossed figure, which is
        # wrong twice over.
        f.update(_operating_line(rng, "yes", below_floor=True))
        plain = _share_amount(f, skip_grossup=True)
        grossed = _share_amount(f)
        f.update(_set_cap(rng, f, plain + (grossed - plain) * rng.uniform(0.35, 0.65), "annual"))
        return f

    if shape in ("cap_not_compounded", "cumulative_cap"):
        f.update(_operating_line(rng, rng.choice(["yes", "no"]), below_floor=rng.random() < 0.5))
        share = _share_amount(f)
        if shape == "cap_not_compounded":
            # The compounded ceiling must sit ABOVE the share (so the cap does not bind and the
            # permitted amount is the share) while the SINGLE application sits below it -- which
            # is exactly what makes applying it once an undercharge.
            f.update(_set_cap(rng, f, share * rng.uniform(1.08, 1.30), "cumulative"))
        else:
            f.update(_set_cap(rng, f, share * rng.uniform(0.75, 0.90), "cumulative"))
        return f

    if shape == "plain":
        f.update(_operating_line(rng, rng.choice(["yes", "no"]), below_floor=False))
        return f

    raise ValueError(shape)


def wrong_amount(fault, f, permitted):
    """The figure a person actually arrives at when they get ONE stage wrong. Never a random
    number: every value below is the same pipeline with a single step broken, which is what makes
    the corpus a test of the rule rather than of arithmetic in general."""
    g = dict(f)
    if fault == "capital_full_cost":
        g["amortization_years"] = 1              # the whole cost, not one instalment
    elif fault == "excluded_billed":
        g["expense_class"] = "routine_operating"  # pooled as though it were an operating expense
        g["amortization_years"] = None
    elif fault == "grossup_missing":
        g["occupancy_sensitive"] = "no"           # the gross-up simply not applied
    elif fault == "grossup_wrong_class":
        g["occupancy_sensitive"] = "yes"          # grossed up when it must not be
    elif fault == "cap_ignored":
        g.update(_no_cap())                       # the ceiling never looked at
    elif fault == "cap_not_compounded":
        g["cap_type"] = "annual"                  # compounded cap applied once
        g["cap_years"] = None
    elif fault == "prorata_start_area":
        g.update(_no_expansion())                 # the expansion never picked up
    elif fault == "prorata_full_year_expansion":
        g["tenant_area_sf"] = f["tenant_area_sf"] + f["expansion_area_sf"]
        g.update(_no_expansion())                 # the expansion applied to all twelve months
    else:
        raise ValueError(fault)
    return permitted_amount(g["expense_class"], g["pool_gross_usd"], g["amortization_years"],
                            g["occupancy_sensitive"], g["building_occupancy_pct"],
                            g["building_area_sf"], g["tenant_area_sf"], g["expansion_area_sf"],
                            g["expansion_month"], g["cap_type"], g["cap_pct"],
                            g["cap_basis_usd"], g["cap_years"])


def _money(v):
    return "%.2f USD" % v


def render(f):
    """The record as it ships. Every null is EXPLAINED in the document rather than left blank -- a
    blank section is indistinguishable from a section the generator forgot to write."""
    amort = ("%d years" % f["amortization_years"] if f["amortization_years"]
             else "not amortizable under this lease")
    exp_area = ("%d sf" % f["expansion_area_sf"] if f["expansion_area_sf"]
                else "no expansion this reconciliation year")
    exp_month = ("month %d" % f["expansion_month"] if f["expansion_month"]
                 else "no expansion this reconciliation year")
    if f["cap_type"] == "none":
        cap_pct = cap_basis = "not capped under this lease"
        cap_years = "not capped under this lease"
    else:
        cap_pct = "%d pct" % f["cap_pct"]
        cap_basis = _money(f["cap_basis_usd"])
        cap_years = ("%d periods" % f["cap_years"] if f["cap_years"]
                     else "not applicable to an annual cap")

    lines = [
        _underline("Statement Line"), f["line_id"], "",
        _underline("Managing Agent"), f["managing_agent"], "",
        _underline("Expense Category"), f["expense_category"], "",
        _underline("Expense Class"), f["expense_class"], "",
        _underline("Pool Gross Cost"), _money(f["pool_gross_usd"]), "",
        _underline("Amortization Years"), amort, "",
        _underline("Occupancy Sensitive"), f["occupancy_sensitive"], "",
        _underline("Building Occupancy"), "%d pct" % f["building_occupancy_pct"], "",
        _underline("Building Area"), "%d sf" % f["building_area_sf"], "",
        _underline("Tenant Area"), "%d sf" % f["tenant_area_sf"], "",
        _underline("Expansion Area"), exp_area, "",
        _underline("Expansion Month"), exp_month, "",
        _underline("Cap Type"), f["cap_type"], "",
        _underline("Cap Percent"), cap_pct, "",
        _underline("Cap Basis"), cap_basis, "",
        _underline("Cap Periods"), cap_years, "",
        _underline("Billed To Tenant"), _money(f["billed_to_tenant_usd"]), "",
        _underline("Statement Status"), f["statement_status"], "",
        _underline("Accountant Notes"), f["accountant_note"], "",
    ]
    return "\n".join(lines) + "\n"


def build_all(rng, n=N_RECORDS):
    stats = {"correct": 0, "wrong": 0, "ambiguous": 0, "needs_review": 0, "decoy_category": 0,
             "overcharge": 0, "undercharge": 0,
             "faults": {name: 0 for name, _c in FAULTS},
             "shapes": {name: 0 for name, _c in CORRECT_SHAPES}}

    plan = _deal(rng, n, [(None, N_CORRECT)] + FAULTS)
    correct_shapes = _deal(rng, N_CORRECT, CORRECT_SHAPES)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    status = _deal(rng, n, [("issued", N_ISSUED), ("draft", n - N_ISSUED)])

    # The decoy CATEGORY is dealt only over records whose class ends up routine_operating, so the
    # count on the page is the count in the corpus. Which records those are is not known until the
    # shapes are drawn, so the deal happens in a second pass below.
    rows, ci = [], 0
    for i in range(1, n + 1):
        fault = plan[i - 1]
        shape = fault if fault else correct_shapes[ci]
        if fault is None:
            ci += 1
            stats["shapes"][shape] += 1
        else:
            stats["faults"][fault] += 1

        for _attempt in range(200):
            f = draw(rng, shape)
            f["expense_category"] = f.get("expense_category") or rng.choice(PLAIN_OPERATING)
            permitted = permitted_amount(
                f["expense_class"], f["pool_gross_usd"], f["amortization_years"],
                f["occupancy_sensitive"], f["building_occupancy_pct"], f["building_area_sf"],
                f["tenant_area_sf"], f["expansion_area_sf"], f["expansion_month"],
                f["cap_type"], f["cap_pct"], f["cap_basis_usd"], f["cap_years"])
            if fault is None:
                billed = permitted
                break
            billed = wrong_amount(fault, f, permitted)
            # ⚑ THE MATERIALITY GUARD. A fault whose figure lands within a dollar of the right one
            # is not a fault, it is rounding -- redraw rather than publish a coin-flip label.
            if billed is not None and abs(billed - permitted) >= MATERIALITY_USD:
                break
        else:
            raise RuntimeError("could not draw a material %s after 200 attempts" % fault)

        f["fault"] = fault
        f["shape"] = shape
        f["permitted_amount_usd"] = permitted
        f["billed_to_tenant_usd"] = billed
        f["statement_status"] = status[i - 1]
        f["ambiguous"] = ambiguity[i - 1]
        f["line_id"] = "CAM-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.randint(10000, 99999))
        f["managing_agent"] = rng.choice(AGENTS)
        rows.append(f)

    # ---- second pass: the decoy category, dealt exactly over the routine_operating records
    routine = [f for f in rows if f["expense_class"] == "routine_operating"]
    n_decoy = min(N_DECOY_CATEGORY, len(routine))
    flags = _deal(rng, len(routine), [(True, n_decoy), (False, len(routine) - n_decoy)])
    for f, decoy in zip(routine, flags):
        if decoy:
            f["expense_category"] = rng.choice(DECOY_OPERATING)
            f["decoy_category"] = True
            stats["decoy_category"] += 1
        else:
            f["expense_category"] = rng.choice(PLAIN_OPERATING)
            f["decoy_category"] = False

    out = []
    for i, f in enumerate(rows, 1):
        f.setdefault("decoy_category", False)
        ok = line_is_ok(f["billed_to_tenant_usd"], f["permitted_amount_usd"])
        stats["correct" if ok == "yes" else "wrong"] += 1
        if ok == "no":
            if f["billed_to_tenant_usd"] > f["permitted_amount_usd"]:
                stats["overcharge"] += 1
            else:
                stats["undercharge"] += 1
        if f["ambiguous"]:
            stats["ambiguous"] += 1
        # Tone matches the arithmetic normally, and contradicts it when ambiguous.
        breezy = (ok == "yes") if not f["ambiguous"] else (ok != "yes")
        f["accountant_note"] = rng.choice(BREEZY_NOTES if breezy else CONCERNED_NOTES)

        if (ok == "no" and f["statement_status"] == "issued"
                and f["billed_to_tenant_usd"] > f["permitted_amount_usd"] + TOLERANCE_USD):
            stats["needs_review"] += 1

        rec_id = "CAM-%04d" % i
        gold = {
            "line_ref": rec_id,
            "line_id": f["line_id"],
            "expense_category": f["expense_category"],
            "expense_class": f["expense_class"],
            "pool_gross_usd": f["pool_gross_usd"],
            "amortization_years": f["amortization_years"],
            "occupancy_sensitive": f["occupancy_sensitive"],
            "building_occupancy_pct": f["building_occupancy_pct"],
            "building_area_sf": f["building_area_sf"],
            "tenant_area_sf": f["tenant_area_sf"],
            "expansion_area_sf": f["expansion_area_sf"],
            "expansion_month": f["expansion_month"],
            "cap_type": f["cap_type"],
            "cap_pct": f["cap_pct"],
            "cap_basis_usd": f["cap_basis_usd"],
            "cap_years": f["cap_years"],
            "billed_to_tenant_usd": f["billed_to_tenant_usd"],
            "statement_status": f["statement_status"],
            "accountant_note": f["accountant_note"],
            "permitted_amount_usd": f["permitted_amount_usd"],
            "line_ok": ok,
            # Not extracted fields -- kept in gold so the analysis in evals/ can say WHICH trap a
            # miss landed on rather than only that one did.
            "_fault": f["fault"],
            "_shape": f["shape"],
            "_decoy_category": f["decoy_category"],
        }
        out.append((rec_id, render(f), gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every derived label must be the
    document's own arithmetic, and every null must be explained in the text. A corpus whose labels
    are not readable off its own text is not a corpus, it is a second opinion."""
    for rec_id, text, g in rows:
        for field in ("line_id", "expense_category", "expense_class", "statement_status",
                      "accountant_note", "cap_type"):
            assert g[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        for field, fmt in (("pool_gross_usd", "%.2f USD"), ("billed_to_tenant_usd", "%.2f USD"),
                           ("building_occupancy_pct", "%d pct"), ("building_area_sf", "%d sf"),
                           ("tenant_area_sf", "%d sf")):
            assert (fmt % g[field]) in text, "%s: %s not stated verbatim" % (rec_id, field)

        assert (("%d years" % g["amortization_years"]) in text if g["amortization_years"]
                else "not amortizable under this lease" in text), \
            "%s: amortization term not stated or its absence not explained" % rec_id
        if g["amortization_years"]:
            assert g["expense_class"] == "capital_improvement", \
                "%s: an amortization term on a non-capital line" % rec_id
        assert (g["expansion_area_sf"] is None) == (g["expansion_month"] is None), \
            "%s: expansion area and month disagree about whether there was one" % rec_id
        if g["expansion_area_sf"]:
            assert ("%d sf" % g["expansion_area_sf"]) in text and \
                   ("month %d" % g["expansion_month"]) in text, \
                "%s: expansion not stated verbatim" % rec_id
        else:
            assert "no expansion this reconciliation year" in text, \
                "%s: absent expansion not explained" % rec_id

        assert (g["cap_pct"] is None) == (g["cap_type"] == "none"), \
            "%s: cap percentage disagrees with cap type" % rec_id
        assert (g["cap_basis_usd"] is None) == (g["cap_type"] == "none"), \
            "%s: cap basis disagrees with cap type" % rec_id
        assert (g["cap_years"] is not None) == (g["cap_type"] == "cumulative"), \
            "%s: cap periods stated on a %s cap" % (rec_id, g["cap_type"])
        if g["cap_type"] != "none":
            assert ("%d pct" % g["cap_pct"]) in text and (_money(g["cap_basis_usd"])) in text, \
                "%s: cap terms not stated verbatim" % rec_id

        want = permitted_amount(g["expense_class"], g["pool_gross_usd"], g["amortization_years"],
                                g["occupancy_sensitive"], g["building_occupancy_pct"],
                                g["building_area_sf"], g["tenant_area_sf"],
                                g["expansion_area_sf"], g["expansion_month"], g["cap_type"],
                                g["cap_pct"], g["cap_basis_usd"], g["cap_years"])
        assert abs(want - g["permitted_amount_usd"]) < 0.005, \
            "%s: gold permitted amount is not the document's own arithmetic" % rec_id
        assert g["line_ok"] == line_is_ok(g["billed_to_tenant_usd"], want), \
            "%s: gold verdict disagrees with its own comparison" % rec_id
        if g["line_ok"] == "no":
            assert abs(g["billed_to_tenant_usd"] - want) >= MATERIALITY_USD, \
                "%s: a 'no' row is wrong by less than the materiality floor" % rec_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g in rows)
    print("records: %d   billed correctly: %d   wrong: %d   bytes: %d"
          % (len(rows), stats["correct"], stats["wrong"], total))
    print("  overcharges: %d   undercharges: %d" % (stats["overcharge"], stats["undercharge"]))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("correct shapes: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["shapes"].items()))
    print("%d (%.0f%%) carry an accountant note whose TONE contradicts the arithmetic"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d carry a category NAME that reads excludable on a routine operating line"
          % stats["decoy_category"])
    print("%d line(s) are overbilled AND already issued -- the pure-code review flag"
          % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every derived label is that document's own arithmetic, every null is explained)")


if __name__ == "__main__":
    main()
