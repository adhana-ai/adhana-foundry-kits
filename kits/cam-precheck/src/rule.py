"""THE LEASE RULE, and the only copy of it in this kit.

⚑ ONE DEFINITION, FIVE READERS. `tools/build_corpus.py` writes gold with it, `src/prompt.py`
states it to the model in words, `src/extract.py` re-runs it over the MODEL's own extracted values
for the self-consistency diagnostic, `evals/judge.py` re-derives gold's truth from it at score
time, and `evals/check_labels.py` refuses the run if a single gold row disagrees with it.

The sibling kit this one is modelled on kept the same logic in TWO files with a comment saying they
were the same function. They were, and nothing enforced it. Here the generator imports this module,
so there is no second copy to drift.

⚠︎ THIS IS THIS KIT'S OWN INVENTED LEASE STRUCTURE, NOT A REAL LEASE. No executed lease, no
published lease form, no landlord's or tenant's own reconciliation and no industry standard form
was consulted, and none is reproduced. A real operating-expense clause runs to pages: it separates
controllable from uncontrollable pools, caps the AGGREGATE rather than the line, carries its own
definition of rentable area and its own audit and notice mechanics, and is negotiated tenant by
tenant. This is four stages and a tolerance, chosen because it is the smallest rule that is
genuinely useful and readable off one reply. Replace it before you check anything real with it.
"""

# The lease's gross-up floor: the occupancy an occupancy-sensitive expense is restated to when the
# building ran emptier than that. 95 pct is a figure commercial leases commonly settle near;
# nothing here is quoted from a form.
GROSSUP_FLOOR_PCT = 95.0

# A line is "right" when the billed figure is within a dollar of the permitted figure. Stated once
# and read by the generator, the prompt, the scorer and the guardrail, so nothing can disagree
# about where the line between right and wrong is.
TOLERANCE_USD = 1.00

# And a wrong line in this corpus is wrong by at least this much -- see build_corpus's materiality
# guard. Published here because the scorer quotes it when it explains why a verdict is not a
# coin flip on the last cent.
MATERIALITY_USD = 25.00

CLASSES = ("routine_operating", "capital_improvement", "landlord_overhead", "leasing_cost")
CAP_TYPES = ("none", "annual", "cumulative")


def _num(v):
    """A number, or None. Booleans are refused: `True` is not a quantity, and Python would
    otherwise treat it as 1 and produce an answer nobody meant."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def poolable_amount(expense_class, pool_gross_usd, amortization_years):
    """STAGE 1. How much of this expense pool is billable to tenants at all, before anybody's
    share. Returns dollars, or None when the inputs do not let the stage run.

    ⚑ THE MIDDLE CASE IS THE ONE THAT COSTS MONEY. "Capital is excluded" is the rule most readers
    carry and it is wrong on an amortizable capital item: the lease permits ONE annual instalment,
    gross / years -- partly billable, neither the whole cost nor zero.
    """
    gross = _num(pool_gross_usd)
    if expense_class not in CLASSES or gross is None:
        return None
    if expense_class in ("landlord_overhead", "leasing_cost"):
        return 0.0
    if expense_class == "capital_improvement":
        years = _num(amortization_years)
        if years is None or years <= 0:
            return 0.0
        return gross / years
    return gross


def grossed_up(pool, occupancy_sensitive, building_occupancy_pct):
    """STAGE 2. Occupancy-sensitive expenses only, and only below the floor.

    ⚠︎ THE `no` BRANCH IS NOT A NO-OP TO SKIP READING. Grossing up a fixed expense -- an insurance
    premium, a tax bill -- is an overcharge that looks exactly like diligence, and it is one of the
    eight faults planted in this corpus.
    """
    occ = _num(building_occupancy_pct)
    if pool is None or occ is None or occ <= 0:
        return None
    if occupancy_sensitive not in ("yes", "no"):
        return None
    if occupancy_sensitive == "yes" and occ < GROSSUP_FLOOR_PCT:
        return pool * GROSSUP_FLOOR_PCT / occ
    return pool


def prorata_share(building_area_sf, tenant_area_sf, expansion_area_sf, expansion_month):
    """STAGE 3. The tenant's share of the building.

    ⚑ A MID-YEAR EXPANSION IS A WEIGHTED AVERAGE. The expansion counts for the months it was
    actually occupied -- `13 - month` of them, inclusive of the month it took effect. Using the
    starting area undercharges; using the expanded area for all twelve months overcharges. Both
    wrong answers are one number away from the right one, which is why this corpus plants both.
    """
    building = _num(building_area_sf)
    tenant = _num(tenant_area_sf)
    if building is None or tenant is None or building <= 0:
        return None
    area = _num(expansion_area_sf)
    month = _num(expansion_month)
    weighted = tenant
    if area and month and 1 <= month <= 12:
        weighted += area * (13.0 - month) / 12.0
    return weighted / building


def cap_ceiling(cap_type, cap_pct, cap_basis_usd, cap_years):
    """STAGE 4's ceiling, or None when the lease caps nothing.

    ⚑ A CUMULATIVE CAP COMPOUNDS. It ceilings this year at the BASE year raised over every period
    since, not at the base year plus one step -- applying it once undercharges the landlord, which
    is the one fault direction in this corpus that costs the landlord rather than the tenant.
    """
    if cap_type not in CAP_TYPES:
        return None
    if cap_type == "none":
        return None
    pct, basis = _num(cap_pct), _num(cap_basis_usd)
    if pct is None or basis is None:
        return None
    if cap_type == "annual":
        return basis * (1.0 + pct / 100.0)
    years = _num(cap_years)
    if years is None or years <= 0:
        return None
    return basis * (1.0 + pct / 100.0) ** years


def permitted_amount(expense_class, pool_gross_usd, amortization_years, occupancy_sensitive,
                     building_occupancy_pct, building_area_sf, tenant_area_sf, expansion_area_sf,
                     expansion_month, cap_type, cap_pct, cap_basis_usd, cap_years):
    """All four stages, in order. Dollars to the cent, or None when a value the rule needs is
    missing or malformed -- an unknown is never a zero, because a zero here reads as "the lease
    permits nothing", which is a real and very different answer."""
    pool = poolable_amount(expense_class, pool_gross_usd, amortization_years)
    if pool is None:
        return None
    pool = grossed_up(pool, occupancy_sensitive, building_occupancy_pct)
    if pool is None:
        return None
    share = prorata_share(building_area_sf, tenant_area_sf, expansion_area_sf, expansion_month)
    if share is None:
        return None
    amount = pool * share
    if cap_type not in CAP_TYPES:
        return None
    ceiling = cap_ceiling(cap_type, cap_pct, cap_basis_usd, cap_years)
    if cap_type != "none" and ceiling is None:
        return None
    if ceiling is not None:
        amount = min(amount, ceiling)
    return round(amount, 2)


def line_is_ok(billed_to_tenant_usd, permitted):
    """"yes" / "no", or None when either side is missing. The comparison, stated once."""
    billed = _num(billed_to_tenant_usd)
    want = _num(permitted)
    if billed is None or want is None:
        return None
    return "yes" if abs(billed - want) <= TOLERANCE_USD else "no"
