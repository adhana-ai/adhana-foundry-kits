#!/usr/bin/env python3
"""Generate synthetic warranty claim records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one dealer warranty claim per file) and data/gold.jsonl, byte-identical
on every run. Every claim id, vehicle id, dealer name, platform label and technician narrative here
is invented -- nothing is fetched and nothing is licensed from anybody, so the corpus ships under
this repo's MIT licence. NO REAL VEHICLE MANUFACTURER, MODEL, VIN, DEALER OR PUBLISHED WARRANTY
BOOKLET IS NAMED OR REPRODUCED ANYWHERE. See data/SOURCES.md.

⚑ GOLD `covered` IS A DERIVATION, NOT A LABEL SOMEBODY TYPED. It is the same six-branch priority
rule the kit publishes everywhere else, run over the same values the generator itself decided:

    coverage_verdict(coverage_plan, months_in_service, odometer_miles,
                     failed_component, claimed_labor_op, narrative_finding)

⚑ THE RULE, AND WHY IT HAS A PRIORITY ORDER. Six branches, checked in this order, and each one of
them is a case a reader who checks the terms in the wrong sequence gets wrong:

  1. AN EXCLUSION NAMED IN THE TECHNICIAN'S NARRATIVE OUTRANKS EVERYTHING. Collision damage, an
     unauthorized modification or a missed maintenance interval denies the claim however new the
     vehicle is and whatever the coded cause says. THE CODED `cause_code` FIELD IS NOT THE
     EVIDENCE -- the technician's own description of what they found is. A claim coded `defect`
     whose narrative describes a curb strike is a damage claim.
  2. THE CLAIMED LABOR OPERATION MUST BE THE FAILED COMPONENT'S OWN OPERATION. A claim that pays
     a transmission operation against a blower motor is not payable as coded, whatever the
     coverage terms say about either part.
  3. A WEAR ITEM IS ITS OWN RULE, AND IT IS NOT ALWAYS "NO". Wear items are outside every plan's
     component list, but a wear item that fails EARLY -- inside 12 months AND 12,000 miles -- is
     covered as a premature failure under a bumper-to-bumper plan (`basic` or `extended`). Under a
     `powertrain` or `emissions` plan it is never covered, early or not.
  4. THE FAILED COMPONENT MUST BE ON THE PLAN'S OWN COMPONENT LIST. A powertrain plan does not
     cover an infotainment head unit at 4,000 miles.
  5. THE LIMIT IS THE PLAN'S OWN LIMIT, NOT THE BASIC ONE. This is the sharpest test in the
     corpus: a powertrain component at 44 months and 48,000 miles is well past the 36/36,000
     bumper-to-bumper terms and comfortably inside the 60/60,000 powertrain terms. A reader who
     reaches for "the 3/36" answers no, and the rule says yes.
  6. Otherwise the claim is covered.

⚑ THE PLANTED CONFUSIONS. There are two, and both live in the technician narrative, which is by
design the loudest and longest thing in the record:

  a. THE TECHNICIAN'S CLOSING OPINION. Every narrative ends with the technician's own guess about
     whether the claim will be paid. On `N_OPINION_MISMATCH` records that guess CONTRADICTS the
     rule -- a covered claim carrying "vehicle is well outside the 3/36, I expect this gets
     denied", or a denied one carrying "should be covered under the powertrain terms, no
     question". Anything that reads the opinion instead of applying the terms -- including
     evals/baseline.py, deliberately -- fails those records by construction.
  b. THE CODED CAUSE vs THE NARRATED FINDING. On `N_CAUSE_MISMATCH` records the structured
     `Cause Code` field disagrees with what the narrative actually describes, in both directions:
     a curb strike or a deleted emissions component coded `defect`, and a plain internal failure
     coded `damage`. Gold follows the NARRATIVE. Reading the coded field instead is the second
     shortcut this kit exists to refuse.
"""
import argparse
import datetime
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51
# pct. A count 1.7 standard deviations off its own design is not a corpus property, it is sampling
# noise being published as one. So each class here is a fixed COUNT, shuffled by the seeded RNG.
# The corpus is still deterministic and still byte-identical on every run.
#
# Every class names WHICH BRANCH OF THE RULE DECIDES IT, so each branch is measured rather than
# assumed. The verdict is a consequence of the branch, never dealt separately.
CLASSES = [
    # (name, count, verdict)
    ("exclusion_in_narrative", 8, "no"),    # branch 1 -- the narrative names an exclusion
    ("labor_op_mismatch", 3, "no"),         # branch 2 -- the claimed operation is another part's
    ("wear_late", 4, "no"),                 # branch 3 -- a wear item past the early-failure window
    ("wear_early", 4, "yes"),               # branch 3 -- a wear item inside it, on a b2b plan
    ("component_outside_plan", 6, "no"),    # branch 4 -- not on this plan's list at all
    ("past_limit", 7, "no"),                # branch 5 -- one month or one mile over the plan's own
    ("plan_limit_beats_basic", 5, "yes"),   # branch 5 -- past 36/36,000, inside the plan's own
    ("boundary_covered", 6, "yes"),         # branch 5 -- EXACTLY on the month or mileage limit
    ("plain_covered", 12, "yes"),           # branch 6 -- comfortably inside every term
]

# The eight exclusion records' KINDS are an exact composition too, for the same reason the classes
# are: drawn per record on a set this small, the three kinds came out 5/2/1 and the corpus would
# have published "collision damage coded as a defect" as its headline confusion on the strength of
# a single record.
EXCLUSION_MIX = [("collision_damage", 3), ("unauthorized_modification", 3),
                 ("missed_maintenance", 2)]

N_OPINION_MISMATCH = 22          # 40 pct, exactly -- the closing opinion contradicts the verdict
N_CAUSE_MISMATCH = 12            # the coded Cause Code disagrees with the narrated finding
N_PAID = 30                      # claim_status == "paid"; the rest are still "submitted"

# ---------------------------------------------------------------------------------------------
# THE COVERAGE TERMS. Invented. This is a plausible SHAPE for a manufacturer warranty programme --
# a bumper-to-bumper term, a longer powertrain term, a longer-still emissions term and a purchased
# extended service contract -- and it is nobody's actual published terms. No real manufacturer's
# warranty booklet, service contract or component schedule was consulted, and none is reproduced.
# ---------------------------------------------------------------------------------------------
PLANS = {
    "basic":      {"months": 36, "miles": 36000},
    "powertrain": {"months": 60, "miles": 60000},
    "emissions":  {"months": 96, "miles": 80000},
    "extended":   {"months": 84, "miles": 100000},
}

POWERTRAIN_PARTS = ["transmission_assembly", "engine_short_block", "drive_axle"]
EMISSIONS_PARTS = ["catalytic_converter", "oxygen_sensor", "evap_canister"]
ACCESSORY_PARTS = ["infotainment_head_unit", "power_window_motor", "hvac_blower_motor"]
WEAR_PARTS = ["brake_pads", "wiper_blades", "clutch_disc"]

ALL_PARTS = POWERTRAIN_PARTS + EMISSIONS_PARTS + ACCESSORY_PARTS + WEAR_PARTS

# Which components each plan's component list actually names. Wear items are on NOBODY's list --
# branch 3 is what lets one in, and only under a bumper-to-bumper plan.
PLAN_COMPONENTS = {
    "basic": POWERTRAIN_PARTS + EMISSIONS_PARTS + ACCESSORY_PARTS,
    "extended": POWERTRAIN_PARTS + EMISSIONS_PARTS + ACCESSORY_PARTS,
    "powertrain": POWERTRAIN_PARTS,
    "emissions": EMISSIONS_PARTS,
}

# One labor operation per component. Invented codes; the grouping digit is deliberately legible
# (4xxx powertrain, 2xxx emissions, 8xxx accessory, 5xxx wear) so a mismatch is visible to a
# reader as well as to the rule.
LABOR_OPS = {
    "transmission_assembly": "LOP-4412",
    "engine_short_block": "LOP-4101",
    "drive_axle": "LOP-4520",
    "catalytic_converter": "LOP-2203",
    "oxygen_sensor": "LOP-2217",
    "evap_canister": "LOP-2240",
    "infotainment_head_unit": "LOP-8310",
    "power_window_motor": "LOP-8422",
    "hvac_blower_motor": "LOP-8155",
    "brake_pads": "LOP-5701",
    "wiper_blades": "LOP-5140",
    "clutch_disc": "LOP-5330",
}

EARLY_MONTHS = 12
EARLY_MILES = 12000

EXCLUSIONS = ("collision_damage", "unauthorized_modification", "missed_maintenance")

# The coded cause that HONESTLY matches each narrated finding.
CAUSE_FOR_FINDING = {
    "defect": "defect",
    "collision_damage": "damage",
    "unauthorized_modification": "modification",
    "missed_maintenance": "maintenance",
}

# Invented dealership names. Nothing here is a real dealer group.
DEALERS = [
    ("Cedar Ridge Motors", "D-4471"),
    ("Northgate Auto Center", "D-2108"),
    ("Harbor Line Automotive", "D-6633"),
    ("Prairie Fork Motors", "D-3390"),
    ("Silver Bend Auto", "D-5127"),
    ("Foxglen Motor Company", "D-7845"),
    ("Ironwood Auto Group", "D-1962"),
    ("Marsh Hollow Motors", "D-8054"),
]

# Invented platform labels -- deliberately not a make and not a model anybody sells. A reader can
# see at a glance that the fleet in this corpus does not exist.
PLATFORMS = [
    "Platform C1 compact sedan",
    "Platform C3 compact hatchback",
    "Platform M2 midsize sedan",
    "Platform U4 midsize crossover",
    "Platform U6 large crossover",
    "Platform T5 light pickup",
]

# ---------------------------------------------------------------------------------------------
# THE NARRATIVE. Two sentences and a closing opinion, in that order:
#   FINDING   -- what the technician says they actually found. This is what the rule reads.
#   WORK      -- what they say they did. Colour; nothing reads it.
#   OPINION   -- the technician's own guess about coverage. THE DECOY.
# ---------------------------------------------------------------------------------------------
FINDING_TEXT = {
    "defect": [
        "Confirmed the customer concern on the hoist and found an internal failure of the %s with no outside cause visible.",
        "Duplicated the fault twice; the %s has failed internally, nothing around it is disturbed and there is no impact damage anywhere near it.",
        "Diagnosed to the %s. Failure is internal to the unit -- no contamination, no external contact, nothing aftermarket in the circuit.",
    ],
    "collision_damage": [
        "Found the %s cracked open with fresh impact marks and road debris packed against it -- this is a strike from underneath, not a failure.",
        "The %s is physically caved in on the leading edge and the shield above it is torn back. Consistent with a curb or kerb strike, not an internal failure.",
        "Underside shows a fresh gouge running into the %s and the mount is bent. Impact damage; the part did not fail on its own.",
    ],
    "unauthorized_modification": [
        "The %s circuit has been cut into and a non-approved aftermarket controller spliced in ahead of it. The splice is what let go.",
        "Found an aftermarket performance module wired into the %s harness and the factory connector removed. Not a factory-condition vehicle.",
        "The %s has been replaced previously with a non-approved part and the tune has been altered. Failure follows the modification.",
    ],
    "missed_maintenance": [
        "Fluid at the %s came out black with heavy varnish; service history shows the required interval was skipped twice.",
        "The %s is packed with sludge and the filter has clearly never been changed -- maintenance records show no service in the required window.",
        "Severe contamination throughout the %s. The scheduled service that would have caught it was never performed.",
    ],
}

WORK_TEXT = [
    "Unit removed and replaced, road tested, no further faults stored.",
    "Component replaced and the system relearned; verified with a full drive cycle.",
    "Replaced the assembly, cleared codes, and confirmed the fault does not return.",
    "R&R complete, torque checked, and the concern no longer duplicates.",
]

# The technician's closing guess. `pro` reads as "this gets paid", `anti` as "this gets denied".
# Neither is ever an input to the rule; both are the whole point of the free floor's failure.
#
# ⚠︎ THE OPINION IS ABOUT THE OUTCOME AND NEVER ABOUT THE CAUSE, DELIBERATELY. An earlier draft
# had a pro-coverage line reading "this is a factory failure and the vehicle is in term", which on
# a record whose own narrative describes a curb strike reads as an obvious self-contradiction --
# and a decoy a reader can spot from its incoherence is not testing anything. Every line here is a
# guess about whether the claim will PAY, which is a thing a technician says regardless of what
# they found, so it stays plausible on every record it lands on.
OPINION_PRO = [
    "Should be covered under the plan terms, no question.",
    "Straightforward warrantable repair as far as I can see -- expect this one to pay.",
    "Vehicle is well inside its term, this should go through fine.",
    "Nothing here that would keep it from being covered.",
]
OPINION_ANTI = [
    "Vehicle is well outside the 3/36 so I expect this one gets denied.",
    "I doubt this one gets paid -- looks out of term to me.",
    "Honestly I would not expect coverage on this, customer may be paying for it.",
    "This one is going to bounce, the vehicle is too far along.",
]

BASE_YEAR = 2018


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic under
    the seeded RNG, and asserts rather than pads: a spec that does not add up to `n` is an author
    error, and quietly padding it is how a published composition stops matching its own design."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    assert len(out) == n, "composition spec sums to %d, not %d" % (len(out), n)
    rng.shuffle(out)
    return out


def months_between(in_service, repair):
    """COMPLETE months in service. (y2-y1)*12 + (m2-m1), minus one when the repair falls earlier
    in the month than the in-service anniversary -- so a vehicle in service on the 18th is 35
    months old on the 17th of the 36th month and 36 months old on the 18th.

    Stated to the model in exactly these words in src/prompt.py, because "how many months old is
    it" has three defensible answers and a rule with a 36-month cliff cannot afford any of them.
    """
    m = (repair.year - in_service.year) * 12 + (repair.month - in_service.month)
    if repair.day < in_service.day:
        m -= 1
    return m


def coverage_verdict(plan, months, miles, component, labor_op, narrative_finding):
    """THE RULE, in one place. src/extract.py::coverage_verdict() is the same function, run over
    the MODEL's own extracted values; data/fields.json states it to the model in words. Three
    readers, one definition, so the corpus, the prompt and the guardrail cannot drift apart about
    what "covered" means.

    Returns "yes" / "no", or None when a value the rule needs is missing or outside its vocabulary
    -- an unknown is not a pass.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COVERAGE STRUCTURE, NOT ANY MANUFACTURER'S PUBLISHED
    WARRANTY. No real warranty booklet, service contract, component schedule or labor operation
    catalogue was consulted, and none is reproduced.
    """
    if plan not in PLANS:
        return None
    if component not in LABOR_OPS:
        return None
    if narrative_finding not in CAUSE_FOR_FINDING:
        return None
    if not isinstance(months, (int, float)) or isinstance(months, bool):
        return None
    if not isinstance(miles, (int, float)) or isinstance(miles, bool):
        return None

    # 1. An exclusion the technician describes outranks every coverage term.
    if narrative_finding in EXCLUSIONS:
        return "no"
    # 2. The claimed operation must belong to the failed component.
    if labor_op != LABOR_OPS[component]:
        return "no"
    # 3. Wear items: covered only as a premature failure, and only under a bumper-to-bumper plan.
    if component in WEAR_PARTS:
        early = months <= EARLY_MONTHS and miles <= EARLY_MILES
        return "yes" if (plan in ("basic", "extended") and early) else "no"
    # 4. The component has to be on this plan's own list.
    if component not in PLAN_COMPONENTS[plan]:
        return "no"
    # 5. The plan's OWN limits -- not the bumper-to-bumper ones.
    if months > PLANS[plan]["months"] or miles > PLANS[plan]["miles"]:
        return "no"
    # 6. Covered.
    return "yes"


def _date(rng, year_lo, year_hi):
    """An in-service date. Day is kept in 1..28 so month arithmetic has no calendar edge cases to
    argue about -- the boundary this corpus tests is the coverage limit, not February."""
    return datetime.date(rng.randint(year_lo, year_hi), rng.randint(1, 12), rng.randint(1, 28))


def _add_months(d, n, day=None):
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return datetime.date(y, m, day if day is not None else d.day)


def _facts(rng, cls, exclusion_kind=None):
    """(plan, in_service, repair, miles, component, labor_op, narrative_finding) for one record.

    Every branch returns values chosen so that `coverage_verdict` lands on the class's own branch
    for the class's own reason -- asserted at the end of build_all rather than trusted.
    """
    if cls == "exclusion_in_narrative":
        plan = rng.choice(list(PLANS))
        comp = rng.choice(PLAN_COMPONENTS[plan])
        in_service = _date(rng, BASE_YEAR + 4, BASE_YEAR + 7)
        # Deliberately WELL INSIDE every term, so the only thing denying it is the narrative.
        repair = _add_months(in_service, rng.randint(4, 20))
        miles = rng.randint(4000, 22000)
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], exclusion_kind

    if cls == "labor_op_mismatch":
        plan = rng.choice(["basic", "powertrain", "extended"])
        comp = rng.choice(PLAN_COMPONENTS[plan])
        in_service = _date(rng, BASE_YEAR + 4, BASE_YEAR + 7)
        repair = _add_months(in_service, rng.randint(6, 24))
        miles = rng.randint(6000, 25000)
        # An operation from a DIFFERENT component -- and deliberately from a different group, so
        # the mismatch is legible in the code's own leading digit.
        other = rng.choice([c for c in ALL_PARTS if c != comp])
        return plan, in_service, repair, miles, comp, LABOR_OPS[other], "defect"

    if cls in ("wear_early", "wear_late"):
        comp = rng.choice(WEAR_PARTS)
        in_service = _date(rng, BASE_YEAR + 4, BASE_YEAR + 7)
        if cls == "wear_early":
            plan = rng.choice(["basic", "extended"])
            # Inside BOTH halves of the early-failure window, and half of them exactly on one edge.
            if rng.random() < 0.5:
                repair = _add_months(in_service, EARLY_MONTHS)
                miles = rng.randint(3000, EARLY_MILES)
            else:
                repair = _add_months(in_service, rng.randint(2, 10))
                miles = EARLY_MILES if rng.random() < 0.5 else rng.randint(2000, 11000)
        else:
            # Past the window on one side or the other, or on a plan that never covers wear at all.
            plan = rng.choice(["basic", "extended", "powertrain", "emissions"])
            if plan in ("powertrain", "emissions"):
                repair = _add_months(in_service, rng.randint(3, 30))
                miles = rng.randint(3000, 40000)
            elif rng.random() < 0.5:
                repair = _add_months(in_service, EARLY_MONTHS + 1)      # one month over
                miles = rng.randint(4000, 11000)
            else:
                repair = _add_months(in_service, rng.randint(4, 11))
                miles = EARLY_MILES + rng.randint(1, 4000)              # over on mileage only
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    if cls == "component_outside_plan":
        plan = rng.choice(["powertrain", "emissions"])
        comp = rng.choice([c for c in ALL_PARTS
                           if c not in PLAN_COMPONENTS[plan] and c not in WEAR_PARTS])
        in_service = _date(rng, BASE_YEAR + 4, BASE_YEAR + 7)
        # Well inside the plan's own term, so the ONLY reason it fails is the component list.
        repair = _add_months(in_service, rng.randint(6, 30))
        miles = rng.randint(5000, 30000)
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    if cls == "past_limit":
        plan = rng.choice(list(PLANS))
        comp = rng.choice(PLAN_COMPONENTS[plan])
        in_service = _date(rng, BASE_YEAR, BASE_YEAR + 3)
        lim = PLANS[plan]
        if rng.random() < 0.5:
            # ONE MONTH over, mileage comfortably inside -- the arithmetic has to be right.
            repair = _add_months(in_service, lim["months"] + 1)
            miles = rng.randint(int(lim["miles"] * 0.4), lim["miles"] - 500)
        else:
            # ONE MILE over, term comfortably inside.
            repair = _add_months(in_service, rng.randint(6, lim["months"] - 6))
            miles = lim["miles"] + 1
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    if cls == "plan_limit_beats_basic":
        # THE BRIEF'S SHARPEST CASE: past 36 months and 36,000 miles -- the bumper-to-bumper terms
        # everybody quotes -- and inside the plan that actually applies.
        plan = rng.choice(["powertrain", "emissions", "extended"])
        comp = rng.choice(PLAN_COMPONENTS[plan])
        lim = PLANS[plan]
        in_service = _date(rng, BASE_YEAR, BASE_YEAR + 3)
        repair = _add_months(in_service, rng.randint(38, lim["months"] - 2))
        miles = rng.randint(38000, lim["miles"] - 1000)
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    if cls == "boundary_covered":
        # EXACTLY on the month limit, or exactly on the mileage limit. Inclusive: exactly 36
        # months is inside the 36-month term.
        plan = rng.choice(list(PLANS))
        comp = rng.choice(PLAN_COMPONENTS[plan])
        lim = PLANS[plan]
        in_service = _date(rng, BASE_YEAR, BASE_YEAR + 3)
        if rng.random() < 0.5:
            repair = _add_months(in_service, lim["months"])
            miles = rng.randint(int(lim["miles"] * 0.5), lim["miles"] - 1000)
        else:
            repair = _add_months(in_service, rng.randint(6, lim["months"] - 4))
            miles = lim["miles"]
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    if cls == "plain_covered":
        plan = rng.choice(list(PLANS))
        comp = rng.choice(PLAN_COMPONENTS[plan])
        lim = PLANS[plan]
        in_service = _date(rng, BASE_YEAR + 3, BASE_YEAR + 7)
        repair = _add_months(in_service, rng.randint(3, max(4, lim["months"] // 2)))
        miles = rng.randint(3000, int(lim["miles"] * 0.55))
        return plan, in_service, repair, miles, comp, LABOR_OPS[comp], "defect"

    raise ValueError(cls)


def _narrative(rng, component, finding, opinion_pro):
    part = component.replace("_", " ")
    finding_line = rng.choice(FINDING_TEXT[finding]) % part
    work_line = rng.choice(WORK_TEXT)
    opinion = rng.choice(OPINION_PRO if opinion_pro else OPINION_ANTI)
    return "%s %s %s" % (finding_line, work_line, opinion)


def build_all(rng, n=N_RECORDS):
    spec = [(name, count) for name, count, _v in CLASSES]
    assert sum(c for _n, c in spec) == n, "CLASSES sums to %d, not %d" % (
        sum(c for _n, c in spec), n)
    classes = _deal(rng, n, spec)
    opinion_mismatch = _deal(rng, n, [(True, N_OPINION_MISMATCH),
                                      (False, n - N_OPINION_MISMATCH)])
    paid = _deal(rng, n, [("paid", N_PAID), ("submitted", n - N_PAID)])
    n_excl = dict(spec)["exclusion_in_narrative"]
    exclusion_kinds = _deal(rng, n_excl, EXCLUSION_MIX)
    next_exclusion = iter(exclusion_kinds)

    stats = {"covered": 0, "denied": 0, "needs_review": 0,
             "classes": {name: 0 for name, _c, _v in CLASSES},
             "opinion_mismatch": 0, "cause_mismatch": 0,
             "cause_mismatch_exclusion_coded_defect": 0,
             "cause_mismatch_defect_coded_otherwise": 0,
             "exclusion_kinds": {k: 0 for k, _c in EXCLUSION_MIX}}

    rows = []
    for i in range(1, n + 1):
        cls = classes[i - 1]
        kind = next(next_exclusion) if cls == "exclusion_in_narrative" else None
        plan, in_service, repair, miles, comp, labor_op, finding = _facts(rng, cls, kind)
        months = months_between(in_service, repair)
        verdict = coverage_verdict(plan, months, miles, comp, labor_op, finding)

        dealer, dealer_code = rng.choice(DEALERS)
        platform = rng.choice(PLATFORMS)
        claim_id = "WCL-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.randint(10000, 99999))
        vehicle_id = "VEH-%s%s%s-%06d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                          rng.randint(100000, 999999))

        mismatch = opinion_mismatch[i - 1]
        if mismatch:
            stats["opinion_mismatch"] += 1
        # The opinion agrees with the verdict normally and contradicts it when planted.
        opinion_pro = (verdict == "yes") if not mismatch else (verdict != "yes")
        narrative = _narrative(rng, comp, finding, opinion_pro)

        rows.append({
            "cls": cls, "plan": plan, "in_service": in_service, "repair": repair,
            "miles": miles, "component": comp, "labor_op": labor_op, "finding": finding,
            "months": months, "verdict": verdict, "dealer": dealer, "dealer_code": dealer_code,
            "platform": platform, "claim_id": claim_id, "vehicle_id": vehicle_id,
            "narrative": narrative, "status": paid[i - 1],
        })
        stats["classes"][cls] += 1
        if finding in EXCLUSIONS:
            stats["exclusion_kinds"][finding] += 1
        stats["covered" if verdict == "yes" else "denied"] += 1

    # ⚑ THE CODED CAUSE IS DEALT SECOND, AND DELIBERATELY SO. Six of the eight records whose
    # narrative names an exclusion are coded `defect` -- the brief's headline confusion, "a
    # narrative describing damage the coded claim calls a defect" -- and the remaining budget goes
    # the other way, onto records whose narrative describes a plain internal failure and whose
    # coded cause claims damage, a modification or missed maintenance. Both directions, so a reader
    # who has learned "the coded field is always wrong" is no better off than one who trusts it.
    exclusion_idx = [i for i, r in enumerate(rows) if r["finding"] in EXCLUSIONS]
    defect_idx = [i for i, r in enumerate(rows) if r["finding"] == "defect"]
    rng.shuffle(exclusion_idx)
    rng.shuffle(defect_idx)
    n_excl_flip = min(6, len(exclusion_idx), N_CAUSE_MISMATCH)
    flip_excl = set(exclusion_idx[:n_excl_flip])
    flip_defect = set(defect_idx[:N_CAUSE_MISMATCH - n_excl_flip])
    for i, r in enumerate(rows):
        if i in flip_excl:
            r["cause_code"] = "defect"
            stats["cause_mismatch"] += 1
            stats["cause_mismatch_exclusion_coded_defect"] += 1
        elif i in flip_defect:
            r["cause_code"] = rng.choice(["damage", "modification", "maintenance"])
            stats["cause_mismatch"] += 1
            stats["cause_mismatch_defect_coded_otherwise"] += 1
        else:
            r["cause_code"] = CAUSE_FOR_FINDING[r["finding"]]

    out = []
    for i, r in enumerate(rows, 1):
        rec_id = "WCL-%04d" % i
        if r["verdict"] == "no" and r["status"] == "paid":
            stats["needs_review"] += 1

        lines = [
            _underline("Claim"), r["claim_id"], "",
            _underline("Servicing Dealer"), "%s (%s)" % (r["dealer"], r["dealer_code"]), "",
            _underline("Vehicle"), "%s / %s" % (r["platform"], r["vehicle_id"]), "",
            _underline("Coverage Plan"), r["plan"], "",
            _underline("In-Service Date"), r["in_service"].isoformat(), "",
            _underline("Repair Date"), r["repair"].isoformat(), "",
            _underline("Odometer"), "%d miles" % r["miles"], "",
            _underline("Failed Component"), r["component"], "",
            _underline("Claimed Labor Operation"), r["labor_op"], "",
            _underline("Cause Code"), r["cause_code"], "",
            _underline("Claim Status"), r["status"], "",
            _underline("Technician Narrative"), r["narrative"], "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "claim_ref": rec_id,
            "claim_id": r["claim_id"],
            "vehicle_id": r["vehicle_id"],
            "coverage_plan": r["plan"],
            "in_service_date": r["in_service"].isoformat(),
            "repair_date": r["repair"].isoformat(),
            "months_in_service": r["months"],
            "odometer_miles": r["miles"],
            "failed_component": r["component"],
            "claimed_labor_op": r["labor_op"],
            "cause_code": r["cause_code"],
            "claim_status": r["status"],
            "technician_narrative": r["narrative"],
            "narrative_finding": r["finding"],
            "covered": r["verdict"],
            # NOT a field the model is asked for. Recorded so evals/check_labels.py can assert that
            # every class landed on the branch it was built for, and so the published composition
            # is read off gold rather than off this file's constants.
            "_class": r["cls"],
        }
        out.append((rec_id, text, gold))
    return out, stats


def deciding_branch(g):
    """Which branch of the rule settles this row. Pure function of gold's own values -- used to
    assert that each class exercises the branch it was written for, and nothing else."""
    if g["narrative_finding"] in EXCLUSIONS:
        return "exclusion"
    if g["claimed_labor_op"] != LABOR_OPS[g["failed_component"]]:
        return "labor_op"
    if g["failed_component"] in WEAR_PARTS:
        return "wear"
    if g["failed_component"] not in PLAN_COMPONENTS[g["coverage_plan"]]:
        return "component_list"
    lim = PLANS[g["coverage_plan"]]
    if g["months_in_service"] > lim["months"] or g["odometer_miles"] > lim["miles"]:
        return "limit_exceeded"
    return "inside_terms"


EXPECTED_BRANCH = {
    "exclusion_in_narrative": "exclusion",
    "labor_op_mismatch": "labor_op",
    "wear_early": "wear",
    "wear_late": "wear",
    "component_outside_plan": "component_list",
    "past_limit": "limit_exceeded",
    "plan_limit_beats_basic": "inside_terms",
    "boundary_covered": "inside_terms",
    "plain_covered": "inside_terms",
}


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold verdict must be the
    rule run over that document's own values, and every class must land on the branch it was
    written for. A corpus whose labels are not readable off its own text is not a corpus, it is a
    second opinion."""
    for rec_id, text, g in rows:
        for field in ("claim_id", "vehicle_id", "coverage_plan", "in_service_date",
                      "repair_date", "failed_component", "claimed_labor_op", "cause_code",
                      "claim_status", "technician_narrative"):
            assert g[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        assert "%d miles" % g["odometer_miles"] in text, \
            "%s: odometer not stated verbatim" % rec_id

        want = coverage_verdict(g["coverage_plan"], g["months_in_service"], g["odometer_miles"],
                                g["failed_component"], g["claimed_labor_op"],
                                g["narrative_finding"])
        assert want == g["covered"], \
            "%s: gold verdict %r disagrees with the rule run over its own values (%r)" \
            % (rec_id, g["covered"], want)

        ins = datetime.date.fromisoformat(g["in_service_date"])
        rep = datetime.date.fromisoformat(g["repair_date"])
        assert months_between(ins, rep) == g["months_in_service"], \
            "%s: months_in_service disagrees with its own two dates" % rec_id
        assert rep > ins, "%s: repair date is not after the in-service date" % rec_id

        branch = deciding_branch(g)
        assert branch == EXPECTED_BRANCH[g["_class"]], \
            "%s: class %r was decided by branch %r, not %r" \
            % (rec_id, g["_class"], branch, EXPECTED_BRANCH[g["_class"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)
    _verify(rows)

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

    total = sum(len(t.encode("utf-8")) for _i, t, _g in rows)
    n_boundary = sum(1 for _i, _t, g in rows
                     if g["_class"] in ("boundary_covered",))
    print("claims: %d   covered: %d   denied: %d   bytes: %d"
          % (len(rows), stats["covered"], stats["denied"], total))
    print("deciding branch: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in stats["classes"].items()))
    print("%d (%.0f%%) carry a technician opinion that contradicts the verdict"
          % (stats["opinion_mismatch"], 100.0 * stats["opinion_mismatch"] / len(rows)))
    print("%d carry a Cause Code that disagrees with the narrated finding "
          "(%d exclusions coded 'defect', %d plain defects coded otherwise)"
          % (stats["cause_mismatch"], stats["cause_mismatch_exclusion_coded_defect"],
             stats["cause_mismatch_defect_coded_otherwise"]))
    print("exclusions named in the narrative: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in stats["exclusion_kinds"].items()))
    print("%d sit EXACTLY on a month or mileage limit" % n_boundary)
    print("%d claim(s) are not covered AND already paid -- the pure-code recovery flag"
          % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every verdict is that document's own rule, every class lands on its own branch)")


if __name__ == "__main__":
    main()
