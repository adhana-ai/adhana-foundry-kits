#!/usr/bin/env python3
"""Generate synthetic lien-waiver payment packages and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one payment package per file) and data/gold.jsonl, byte-identical on
every run. Every project, contractor, supplier, waiver number and coordinator note here is
invented -- nothing is fetched and nothing is licensed from anybody, so the corpus ships under
this repo's MIT licence.

⚠︎ NO JURISDICTION'S STATUTORY WAIVER FORM IS REPRODUCED. Lien waiver forms and the rules about
them vary by jurisdiction, and several places prescribe an exact form by statute. This corpus is
modelled on the general STRUCTURE such forms share -- a party, an amount, a through-date, and a
conditional/unconditional, progress/final distinction -- and reproduces no state's statutory text,
no real filed notice and no real project. See data/SOURCES.md.

⚠︎ THIS KIT DOES NOT DETERMINE LIEN RIGHTS AND IS NOT LEGAL ADVICE. It assembles the coverage
picture a person needs and names every gap in it; a human decides whether to release the payment.

⚑ GOLD IS THE COVERAGE RULE RUN OVER THE PACKAGE'S OWN STRUCTURED VALUES, NOT A LABEL SOMEBODY
TYPED. `parties_uncovered`, `first_gap_party` and `first_gap_reason` are all read straight off
coverage_status() applied party by party in document order. The payment coordinator's note never
feeds any of them.

⚑ THE RULE, AND WHY IT HAS A PRIORITY ORDER. Five ways a party can be uncovered, checked in a
fixed order, because more than one can be true at once and only the first one is reported:

    1. no_waiver_on_file  -- no waiver on file for this party at all
    2. notice_after_waiver -- the party's preliminary notice is dated AFTER the waiver was
       signed, so the waiver predates the claim it would have to cover. This one outranks
       everything below it, which is the trap: the waiver can be unconditional, for the full
       amount, covering the whole period, and still not reach the claim
    3. period_short       -- a PROGRESS waiver whose through-date stops before the pay
       application's period-through date. A FINAL waiver has no through-date at all -- it covers
       all work through completion -- so the period test does not apply to it
    4. amount_short       -- the waiver amount is less than the amount being released to that
       party
    5. conditional_stale  -- the waiver is CONDITIONAL and the payment it was exchanged for has
       already cleared, so an unconditional waiver is now owed. A JOINT CHECK clears on issue
       (both payees negotiate it), so a conditional waiver on a joint-check party is stale even
       when the package says the prior payment has not cleared

⚑ THE PLANTED AMBIGUITY: coverage is arithmetic over dates and amounts, and the payment
coordinator's own note disagrees with it on `N_AMBIGUOUS` of packages. A package with a real gap
carries a breezy note ("All waivers received and filed, nothing outstanding on this one.");
a fully-covered package carries a note that reads as though something is wrong. Anything that
reads the note instead of running the rule -- including evals/baseline.py, deliberately -- fails
those packages by construction.
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
N_PACKAGES = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER PACKAGE -- the same discipline the
# sibling kits in this series arrived at after one of them asked for 40 pct ambiguity and
# delivered 51 pct. A count 1.7 standard deviations off its own design is sampling noise being
# published as a corpus property. Each class here is a fixed COUNT, shuffled by the seeded RNG.
N_COVERED = 24                  # every party covered -- parties_uncovered == 0
N_AMBIGUOUS = 22                # 40 pct, exactly -- a coordinator note from the wrong register
N_SCHEDULED = 30                # release_status == "scheduled"; the rest are "on_hold"
N_SECOND_GAP = 9                # of the gap packages, how many carry a SECOND uncovered party

# ⚑ THE FAULT LIBRARY -- which reason the FIRST uncovered party carries, and how many of the 31
# gap packages each takes. `conditional_stale` is split deliberately below into the two routes it
# can arrive by, because only one of them is hard.
FAULTS = [
    ("no_waiver_on_file", 6),
    ("notice_after_waiver", 7),
    ("period_short", 7),
    ("amount_short", 5),
    ("conditional_stale", 6),
]
# Of the 6 conditional_stale packages, this many arrive by the JOINT CHECK route -- the package
# says the prior payment has NOT cleared, and the waiver is stale anyway because a joint check
# clears on issue. The rest arrive by the obvious route (the package says it cleared).
N_STALE_VIA_JOINT_CHECK = 3

WAIVER_TYPES = ["conditional_progress", "unconditional_progress",
                "conditional_final", "unconditional_final"]

GAP_REASONS = ["no_waiver_on_file", "notice_after_waiver", "period_short", "amount_short",
               "conditional_stale"]

PROJECTS = [
    "Cedar Point Transit Center",
    "Northline Water Treatment Plant",
    "Harbor Gate Mixed-Use Block",
    "Merritt Avenue Parking Structure",
    "Fallbrook Regional Hospital Wing",
    "Stonebridge Logistics Campus",
    "Vista Ridge Middle School",
    "Ardmore Street Bridge Replacement",
]

PRIMES = [
    "Northgate Builders",
    "Corvin Construction Group",
    "Halloway and Sons Contracting",
    "Westmark General Contractors",
    "Ferrand Building Company",
]

# Tier-1 trade contractors -- the party the general contractor holds the subcontract with.
TIER1 = [
    "Ridgeline Mechanical",
    "Beacon Electrical Contractors",
    "Halden Concrete",
    "Torrey Glazing Systems",
    "Marchand Roofing",
    "Kestrel Plumbing",
    "Oakfield Drywall",
    "Ironwood Structural",
]

# Lower-tier suppliers and sub-subcontractors -- tier 2 and occasionally tier 3.
LOWER = [
    "Vance Steel Supply",
    "Pinebrook Rebar",
    "Calder Aggregates",
    "Stanton Fixtures",
    "Belmont Conduit",
    "Arcadia Millwork",
    "Quarry Road Concrete Supply",
    "Linden Sheet Metal",
    "Ashby Insulation",
    "Truxton Hoisting",
    "Delmar Elevator Parts",
    "Hollis Fire Protection Supply",
]

# Notes whose TONE says "the waiver file on this package is complete". Used truthfully on a fully
# covered package, and against type on one with a real gap -- half the planted ambiguity.
BREEZY_NOTES = [
    "All waivers received and filed, nothing outstanding on this one.",
    "Waiver file reviewed at intake and it looked complete.",
    "Routine package. No concerns from the coordinator on this one.",
    "Standard progress draw, paperwork came in clean this cycle.",
]

# Notes whose TONE says "something is wrong with the waiver file". Used truthfully on a package
# with a gap, and against type on a fully covered one -- the other half.
ANXIOUS_NOTES = [
    "Waiver file looked thin on this one -- escalated for a second pass before release.",
    "Lower-tier paperwork is disputed; package under manual audit this cycle.",
    "Not confident the waiver coverage is complete here -- needs a second look before release.",
    "Something looked off in the waiver file at intake, revisit before this one goes out.",
]

BASE_YEAR, BASE_MONTH = 2026, 1


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs, padded with the
    first pair's value if the counts fall short. Deterministic under the seeded RNG."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def _money(cents):
    return "%s USD" % format(cents / 100.0, ",.2f")


def _month_end(year, month):
    if month == 12:
        return datetime.date(year, 12, 31)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


def coverage_status(waiver_type, waiver_amount, waiver_through, waiver_signed, notice_date,
                    amount_due, period_through, prior_cleared, joint_check):
    """THE RULE, in one place. src/extract.py::coverage_status() is the same function, run over
    values a reader can check against the document; data/fields.json states it to the model in
    words. Three readers, one definition, so the corpus, the prompt and the guardrail cannot
    drift apart about what "covered" means.

    Dates are ISO strings (YYYY-MM-DD) or None; amounts are floats in dollars.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COVERAGE RULE, NOT ANY JURISDICTION'S LAW. Lien waiver
    requirements vary by jurisdiction and several places prescribe the form by statute. This is
    five conditions in a fixed order, chosen because it is the smallest rule that is genuinely
    useful and readable off one package. It determines nobody's lien rights.
    """
    if waiver_type == "none":
        return "no_waiver_on_file"
    if waiver_type not in WAIVER_TYPES:
        return None
    if notice_date and waiver_signed and notice_date > waiver_signed:
        return "notice_after_waiver"
    # A FINAL waiver carries no through-date: it reaches all work through completion, so the
    # period test does not apply to it. Only a PROGRESS waiver is bounded by a through-date.
    if waiver_type.endswith("_progress"):
        if not waiver_through or not period_through or waiver_through < period_through:
            return "period_short"
    if waiver_amount is None or amount_due is None:
        return None
    if waiver_amount + 0.005 < amount_due:
        return "amount_short"
    # A joint check is negotiated by both payees, so it clears on issue -- a conditional waiver
    # against it is already spent even when the package says the prior payment has not cleared.
    if waiver_type.startswith("conditional_") and (prior_cleared == "yes" or joint_check == "yes"):
        return "conditional_stale"
    return "covered"


def package_coverage(parties, period_through, prior_cleared):
    """The three published coverage answers, read off the rule party by party in document order.

    Returns (parties_uncovered, first_gap_party, first_gap_reason, per_party_statuses).
    """
    statuses = []
    for p in parties:
        statuses.append(coverage_status(
            p["waiver_type"], p["waiver_amount"], p["waiver_through"], p["waiver_signed"],
            p["notice_date"], p["amount_due"], period_through, prior_cleared, p["joint_check"]))
    gaps = [(p, s) for p, s in zip(parties, statuses) if s != "covered"]
    if not gaps:
        return 0, None, "none", statuses
    return len(gaps), gaps[0][0]["party"], gaps[0][1], statuses


def _covered_party(rng, name, tier, amount_due_cents, period_through, prior_cleared,
                   allow_joint_check=True):
    """A party whose status computes to "covered", given the package's own prior_cleared."""
    joint_check = "yes" if (allow_joint_check and rng.random() < 0.18) else "no"
    # A conditional waiver is only ever covered when nothing has cleared against it.
    if prior_cleared == "yes" or joint_check == "yes":
        wtype = rng.choice(["unconditional_progress", "unconditional_final"])
    else:
        wtype = rng.choice(WAIVER_TYPES)

    pt = datetime.date.fromisoformat(period_through)
    if wtype.endswith("_progress"):
        through = pt + datetime.timedelta(days=rng.choice([0, 0, 0, 15, 30]))
        through_s = through.isoformat()
    else:
        through_s = None
    signed = (pt + datetime.timedelta(days=rng.randint(1, 12))).isoformat()
    # A notice, when there is one, arrived BEFORE the waiver was signed -- so it is covered.
    if rng.random() < 0.45:
        notice = (pt - datetime.timedelta(days=rng.randint(20, 240))).isoformat()
    else:
        notice = None
    # The waiver is for the amount due or a little more.
    waiver_cents = amount_due_cents + rng.choice([0, 0, 0, 2500, 25000, 100000])
    return {"party": name, "tier": tier, "amount_due": amount_due_cents / 100.0,
            "amount_due_cents": amount_due_cents, "waiver_id": "LW-%05d" % rng.randint(10000, 99999),
            "waiver_type": wtype, "waiver_amount": waiver_cents / 100.0,
            "waiver_amount_cents": waiver_cents, "waiver_through": through_s,
            "waiver_signed": signed, "notice_date": notice, "joint_check": joint_check}


def _apply_fault(rng, party, reason, period_through, prior_cleared, stale_via_joint_check):
    """Turn a covered party into one whose status computes to exactly `reason`.

    Every mutator leaves the OTHER four conditions satisfied, so the reason the rule reports is
    the reason that was planted -- which is what makes `first_gap_reason` a scorable field rather
    than a lucky guess.
    """
    pt = datetime.date.fromisoformat(period_through)

    if reason == "no_waiver_on_file":
        party.update({"waiver_id": None, "waiver_type": "none", "waiver_amount": None,
                      "waiver_amount_cents": None, "waiver_through": None, "waiver_signed": None})
        return party

    if reason == "notice_after_waiver":
        # THE TRAP: unconditional, full amount, covers the whole period -- and signed before the
        # notice that asserts the claim arrived. Everything a fast reader checks says covered.
        signed = pt - datetime.timedelta(days=rng.randint(5, 45))
        party["waiver_type"] = rng.choice(["unconditional_progress", "unconditional_final"])
        party["waiver_signed"] = signed.isoformat()
        party["notice_date"] = (signed + datetime.timedelta(days=rng.randint(3, 40))).isoformat()
        if party["waiver_type"].endswith("_progress"):
            party["waiver_through"] = (pt + datetime.timedelta(days=rng.choice([0, 15]))).isoformat()
        else:
            party["waiver_through"] = None
        party["waiver_amount_cents"] = party["amount_due_cents"] + rng.choice([0, 50000])
        party["waiver_amount"] = party["waiver_amount_cents"] / 100.0
        party["joint_check"] = "no"
        return party

    if reason == "period_short":
        # THE TRAP: the amount is generous, so an amount-first reader passes it. The through-date
        # stops inside the period. Forced to a PROGRESS waiver, because a final waiver has no
        # through-date and cannot be short on period.
        party["waiver_type"] = rng.choice(["conditional_progress", "unconditional_progress"])
        if party["waiver_type"] == "conditional_progress" and (prior_cleared == "yes"
                                                               or party["joint_check"] == "yes"):
            party["waiver_type"] = "unconditional_progress"
        party["waiver_through"] = (pt - datetime.timedelta(days=rng.randint(14, 75))).isoformat()
        party["waiver_signed"] = (pt - datetime.timedelta(days=rng.randint(0, 10))).isoformat()
        party["notice_date"] = None if rng.random() < 0.5 else (
            pt - datetime.timedelta(days=rng.randint(90, 300))).isoformat()
        party["waiver_amount_cents"] = party["amount_due_cents"] + rng.choice([0, 100000, 250000])
        party["waiver_amount"] = party["waiver_amount_cents"] / 100.0
        return party

    if reason == "amount_short":
        party["waiver_type"] = rng.choice(["unconditional_progress", "unconditional_final"])
        if party["waiver_type"].endswith("_progress"):
            party["waiver_through"] = (pt + datetime.timedelta(days=rng.choice([0, 15]))).isoformat()
        else:
            party["waiver_through"] = None
        party["waiver_signed"] = (pt + datetime.timedelta(days=rng.randint(1, 10))).isoformat()
        party["notice_date"] = None if rng.random() < 0.5 else (
            pt - datetime.timedelta(days=rng.randint(60, 300))).isoformat()
        short = int(party["amount_due_cents"] * rng.uniform(0.55, 0.94))
        party["waiver_amount_cents"] = short
        party["waiver_amount"] = short / 100.0
        return party

    if reason == "conditional_stale":
        party["waiver_type"] = rng.choice(["conditional_progress", "conditional_final"])
        if party["waiver_type"].endswith("_progress"):
            party["waiver_through"] = (pt + datetime.timedelta(days=rng.choice([0, 15]))).isoformat()
        else:
            party["waiver_through"] = None
        party["waiver_signed"] = (pt + datetime.timedelta(days=rng.randint(1, 10))).isoformat()
        party["notice_date"] = None if rng.random() < 0.5 else (
            pt - datetime.timedelta(days=rng.randint(60, 300))).isoformat()
        party["waiver_amount_cents"] = party["amount_due_cents"] + rng.choice([0, 50000])
        party["waiver_amount"] = party["waiver_amount_cents"] / 100.0
        # THE HARD ROUTE: the package says the prior payment has NOT cleared, and the waiver is
        # stale anyway because this party is on a joint check, which clears on issue.
        party["joint_check"] = "yes" if stale_via_joint_check else "no"
        return party

    raise ValueError(reason)


def _render_party(i, p):
    lines = ["Party %d: %s" % (i, p["party"]),
             "  Tier: %d" % p["tier"],
             "  Amount due this application: %s" % _money(p["amount_due_cents"])]
    lines.append("  Preliminary notice on file: %s"
                 % (p["notice_date"] or "none"))
    if p["waiver_type"] == "none":
        lines.append("  Waiver on file: none")
        lines.append("  Waiver amount: n/a")
        lines.append("  Waiver covers work through: n/a")
        lines.append("  Waiver signed: n/a")
    else:
        kind = p["waiver_type"].replace("_", " ") + " waiver"
        lines.append("  Waiver on file: %s, %s" % (p["waiver_id"], kind))
        lines.append("  Waiver amount: %s" % _money(p["waiver_amount_cents"]))
        if p["waiver_through"]:
            lines.append("  Waiver covers work through: %s" % p["waiver_through"])
        else:
            lines.append("  Waiver covers work through: n/a (final waiver, all work through "
                         "completion)")
        lines.append("  Waiver signed: %s" % p["waiver_signed"])
    lines.append("  Joint check arrangement: %s" % p["joint_check"])
    return "\n".join(lines)


def build_all(rng, n=N_PACKAGES):
    stats = {"covered": 0, "gap": 0, "ambiguous": 0, "needs_hold": 0, "two_gaps": 0,
             "joint_check_parties": 0, "final_waivers": 0, "notices": 0, "parties": 0,
             "prior_cleared_yes": 0, "reasons": {r: 0 for r in GAP_REASONS}}

    n_covered = min(N_COVERED, n)
    faults = _deal(rng, n, [(None, n_covered)] + FAULTS)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    release = _deal(rng, n, [("scheduled", N_SCHEDULED), ("on_hold", n - N_SCHEDULED)])
    # Which of the conditional_stale packages take the hard joint-check route.
    stale_route = _deal(rng, sum(c for r, c in FAULTS if r == "conditional_stale"),
                        [(True, N_STALE_VIA_JOINT_CHECK),
                         (False, 6 - N_STALE_VIA_JOINT_CHECK)])
    # Which gap packages carry a SECOND uncovered party.
    second = _deal(rng, n - n_covered, [(True, N_SECOND_GAP), (False, n - n_covered - N_SECOND_GAP)])

    stale_i = second_i = 0
    out = []
    for i in range(1, n + 1):
        fault = faults[i - 1]
        via_joint = False
        if fault == "conditional_stale":
            via_joint = stale_route[stale_i]
            stale_i += 1

        # ⚑ REAL DATE ARITHMETIC, NOT STRING SURGERY. A pay application period ends on a calendar
        # month end; adding months by hand off two independent draws is how "2026-13-31" happens.
        months_out = rng.randint(0, 17)
        year = BASE_YEAR + (BASE_MONTH - 1 + months_out) // 12
        month = (BASE_MONTH - 1 + months_out) % 12 + 1
        period_through = _month_end(year, month).isoformat()

        # prior_payment_cleared is forced by the two conditional_stale routes and free otherwise.
        if fault == "conditional_stale":
            prior_cleared = "no" if via_joint else "yes"
        else:
            prior_cleared = "yes" if rng.random() < 0.45 else "no"

        n_parties = rng.randint(3, 5)
        names = [rng.choice(TIER1)] + rng.sample(LOWER, n_parties - 1)
        tiers = [1] + [rng.choice([2, 2, 2, 3]) for _ in range(n_parties - 1)]

        # The tier-1 subcontractor carries the largest share; the lower tiers split the rest.
        weights = [rng.uniform(2.2, 4.0)] + [rng.uniform(0.5, 1.6) for _ in range(n_parties - 1)]
        total_cents = rng.randint(60_000_00, 640_000_00)
        wsum = sum(weights)
        amounts = [max(2_500_00, int(total_cents * w / wsum)) for w in weights]
        total_cents = sum(amounts)

        parties = [_covered_party(rng, names[k], tiers[k], amounts[k], period_through,
                                  prior_cleared, allow_joint_check=(tiers[k] > 1))
                   for k in range(n_parties)]

        if fault is not None:
            want_second = second[second_i]
            second_i += 1
            # The FIRST gap goes on any party; every party before it stays covered, so
            # first_gap_party is the planted one by construction. When a SECOND gap is wanted the
            # first one is kept off the last party, so there is always room for it -- otherwise
            # "9 packages carry two gaps" quietly becomes 7, which is the sampling-noise-as-a-
            # corpus-property failure the exact-count discipline above exists to prevent.
            hi = n_parties - 1 if want_second else n_parties
            # A joint check names a LOWER-TIER payee alongside the subcontractor, so the
            # joint-check route never lands on the tier-1 party at index 0.
            gi = rng.randrange(1 if via_joint else 0, hi)
            parties[gi] = _apply_fault(rng, parties[gi], fault, period_through, prior_cleared,
                                       via_joint)
            if want_second:
                # Always AFTER the first, so it never displaces first_gap_party or its reason.
                gj = rng.randrange(gi + 1, n_parties)
                # ⚠︎ A SECOND GAP HAS TO ACTUALLY BE A GAP. conditional_stale needs something to
                # have cleared, so on a package whose prior payment has NOT cleared it must take
                # the joint-check route or it silently computes to "covered" -- which is exactly
                # how "9 packages carry two gaps" first came out as 6.
                parties[gj] = _apply_fault(rng, parties[gj], rng.choice(GAP_REASONS),
                                           period_through, prior_cleared,
                                           prior_cleared == "no")

        uncovered, gap_party, gap_reason, statuses = package_coverage(
            parties, period_through, prior_cleared)

        # A fully-covered package must actually compute to zero gaps; a gap package must report
        # the reason that was planted. Anything else is a generator bug, caught here rather than
        # published -- _verify() re-asserts it over the written rows.
        if fault is None:
            assert uncovered == 0, "package %d was meant to be fully covered, got %r" % (i, statuses)
        else:
            assert gap_reason == fault, ("package %d planted %s, rule says %s"
                                         % (i, fault, gap_reason))

        status = release[i - 1]
        needs_hold = (uncovered > 0) and (status == "scheduled")
        if needs_hold:
            stats["needs_hold"] += 1
        stats["covered" if uncovered == 0 else "gap"] += 1
        if uncovered > 1:
            stats["two_gaps"] += 1
        if uncovered:
            stats["reasons"][gap_reason] += 1
        if prior_cleared == "yes":
            stats["prior_cleared_yes"] += 1
        stats["parties"] += n_parties
        stats["joint_check_parties"] += sum(1 for p in parties if p["joint_check"] == "yes")
        stats["final_waivers"] += sum(1 for p in parties if p["waiver_type"].endswith("_final"))
        stats["notices"] += sum(1 for p in parties if p["notice_date"])

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the coverage picture normally, and contradicts it when ambiguous.
        breezy = (uncovered == 0) if not ambiguous else (uncovered > 0)
        note = rng.choice(BREEZY_NOTES if breezy else ANXIOUS_NOTES)

        pkg_id = "PA-%04d-%03d" % (year, rng.randint(100, 999))
        project = rng.choice(PROJECTS)
        prime = rng.choice(PRIMES)
        app_no = "Application %02d" % rng.randint(2, 19)
        subcontract = "SC-%s-%04d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"), rng.randint(1000, 9999))
        retainage = rng.choice([5, 5, 10, 10, 7])

        rec_id = "LWP-%04d" % i
        body = "\n\n".join(_render_party(k + 1, p) for k, p in enumerate(parties))
        lines = [
            _underline("Package"), pkg_id, "",
            _underline("Project"), project, "",
            _underline("Prime Contractor"), prime, "",
            _underline("Subcontract Reference"),
            "%s, retainage %d percent" % (subcontract, retainage), "",
            _underline("Pay Application"), app_no, "",
            _underline("Period Through"), period_through, "",
            _underline("Payment Amount"), _money(total_cents), "",
            _underline("Prior Payment Cleared"), prior_cleared, "",
            _underline("Release Status"), status, "",
            _underline("Waiver Coverage"), body, "",
            _underline("Coordinator Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "pkg_id": rec_id,
            "package_id": pkg_id,
            "project_name": project,
            "pay_app_number": app_no,
            "period_through": period_through,
            "payment_amount_usd": round(total_cents / 100.0, 2),
            "prior_payment_cleared": prior_cleared,
            "release_status": status,
            "coordinator_note": note,
            "parties_uncovered": uncovered,
            "first_gap_party": gap_party,
            "first_gap_reason": gap_reason,
        }
        out.append((rec_id, text, gold, parties))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold answer must be the
    rule's own answer over that document's own parties, and first_gap_party must be null exactly
    when parties_uncovered is 0. A corpus whose labels are not readable off its own text is not a
    corpus, it is a second opinion."""
    for rec_id, text, gold, parties in rows:
        for field in ("package_id", "project_name", "pay_app_number", "period_through",
                      "prior_payment_cleared", "release_status", "coordinator_note"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        assert format(gold["payment_amount_usd"], ",.2f") in text, \
            "%s: payment_amount_usd not stated verbatim" % rec_id
        assert abs(sum(p["amount_due"] for p in parties) - gold["payment_amount_usd"]) < 0.005, \
            "%s: the party amounts do not sum to the payment amount" % rec_id

        uncovered, gap_party, gap_reason, _ = package_coverage(
            parties, gold["period_through"], gold["prior_payment_cleared"])
        assert uncovered == gold["parties_uncovered"], \
            "%s: gold parties_uncovered disagrees with the rule" % rec_id
        assert gap_party == gold["first_gap_party"], \
            "%s: gold first_gap_party disagrees with the rule" % rec_id
        assert gap_reason == gold["first_gap_reason"], \
            "%s: gold first_gap_reason disagrees with the rule" % rec_id

        # ⚑ THE NULLABILITY INVARIANT: first_gap_party is null exactly when nothing is uncovered.
        assert (gold["first_gap_party"] is None) == (gold["parties_uncovered"] == 0), \
            "%s: first_gap_party nullness disagrees with parties_uncovered" % rec_id
        assert (gold["first_gap_reason"] == "none") == (gold["parties_uncovered"] == 0), \
            "%s: first_gap_reason 'none' disagrees with parties_uncovered" % rec_id
        if gold["first_gap_party"]:
            assert gold["first_gap_party"] in text, \
                "%s: first_gap_party not stated in the document" % rec_id

        y, m, d = (int(x) for x in gold["period_through"].split("-"))
        assert 1 <= m <= 12 and 1 <= d <= 31, "%s: period_through is not a real date" % rec_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_PACKAGES)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold, _parties in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold, _parties in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _p in rows)
    print("packages: %d   fully covered: %d   with a gap: %d   bytes: %d"
          % (len(rows), stats["covered"], stats["gap"], total))
    print("parties: %d   joint-check parties: %d   final waivers: %d   notices on file: %d"
          % (stats["parties"], stats["joint_check_parties"], stats["final_waivers"],
             stats["notices"]))
    print("first-gap reasons: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in stats["reasons"].items()))
    print("%d package(s) carry TWO uncovered parties" % stats["two_gaps"])
    print("%d package(s) say the prior payment has cleared" % stats["prior_cleared_yes"])
    print("%d (%.0f%%) carry a coordinator note whose TONE contradicts the coverage picture"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d package(s) have a gap AND are scheduled for release -- the pure-code hold flag"
          % stats["needs_hold"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every answer is that document's own rule, first_gap_party is null iff nothing is "
          "uncovered)")


if __name__ == "__main__":
    main()
