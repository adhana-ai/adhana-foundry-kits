#!/usr/bin/env python3
"""Generate the seller onboarding applications this kit checks against, from a fixed seed.

    python3 tools/build_corpus.py
    python3 tools/build_corpus.py --verify     # re-reads data/*.jsonl from disk and re-derives
                                                # every gold row independently -- see verify()

Writes data/applications.jsonl and data/gold.jsonl, byte-identical on every run. Nothing is
fetched and nothing is licensed from anybody: every business, owner, address, tax ID and bank
detail here is invented, so the corpus ships under this repo's MIT licence and there is no
third-party grant to verify.

⚑ WHY THE RECORDS ARE INVENTED. A real onboarding application names a real business, a real owner
and a real bank account -- this repo has never held one and is not able to. A synthetic set is the
only kind of seller-verification corpus that can be re-run by a stranger with a clone and no NDA
to sign. See data/SOURCES.md.

⚑ ALL SEVEN FIELD PAIRS ARE ALWAYS PRESENT. Every application carries a full declared record and
all three document blocks (business registration, bank letter, government ID), never a partial
one -- the mechanic this kit measures is comparing all seven pairs, not filling in a blank. See
src/prompt.py for the field-pair taxonomy stated to the model.

⚑ THE TRAP, PLANTED ON PURPOSE. ~36% of applications -- inside the spec's 30-40% band -- mismatch
ONLY bank_routing_number: every other of the seven fields matches cleanly, and submission_note is
either empty or a generic remark that never mentions banking. This is the exact failure named in
the product spec: "a mismatched banking detail on an otherwise clean application... a fraudulent
application". See TRAP_N below, and `derive_flags()` for the rule that both labels gold and,
independently, lets --verify catch this file lying about its own corpus.

⚑ GOLD IS NEVER HAND-LABELLED. `derive_flags()` compares each declared value against its document
value and scans `submission_note` for a small set of field-specific trigger phrases -- the same
mechanical rule used to build the corpus and, independently, to re-check it. A "mismatch_explained"
row is never written because a builder function intended one; it is written because the finished
record's own fields and note text, read back through derive_flags(), produce it. `verification_
outcome` is derived the same way, from the flags alone, never authored -- see derive_outcome().
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
sys.path.insert(0, HERE)

from src import prompt as P                                          # noqa: E402

SEED = 20260819                              # fixed. change it and every downstream file changes.

# 36 applications, similar order of magnitude to every sibling kit's corpus.
PATTERN_COUNTS = {
    "clean": 8,
    "banking_trap": 13,
    "explained_single": 8,
    "escalated_nonbanking": 4,
    "denied_multi": 3,
}

# ⚑ 13 of 36 (~36%) ARE THE NAMED TRAP -- inside the spec's 30-40% band. A fixed count, not an
# independent coin flip per application, for the same reason fin-payrun samples TRAP_N rather than
# drawing one: an independent draw at this corpus's size can legitimately land outside the band.
TRAP_N = PATTERN_COUNTS["banking_trap"]

BANKING_FIELDS = ("bank_account_name", "bank_routing_number")

# ── mechanical "does the note explain THIS field" rule ──────────────────────────────────────
# Specific multi-word phrases, not single words, so one field's explanation cannot accidentally
# satisfy another's -- see the module docstring in src/prompt.py for why an unrelated note must
# never read as covering a discrepancy it doesn't mention. Checked against the finished note text
# by derive_flags(), never assumed true because a builder function meant to write an "explained"
# case.
KEYWORDS = {
    "business_name": ("changed our business name", "rebranded"),
    "business_address": ("changed our business address", "registration update is still pending",
                         "registration update pending"),
    "tax_id": ("corrected ein", "corrected tax id"),
    "bank_account_name": ("personal bank account", "using my personal"),
    "bank_routing_number": ("switched banks", "new routing number"),
    "owner_name": ("changed my legal name", "legal name after marriage"),
    "owner_address": ("moved to a new home", "new home address"),
}

EXPLAIN_NOTES = {
    "business_name": "We recently rebranded and changed our business name; the registration "
                     "filing is still under our prior legal name.",
    "business_address": "We recently changed our business address; registration update is "
                        "still pending with the state.",
    "tax_id": "We recently received a corrected EIN from the IRS; our registration document "
             "still shows the old tax ID.",
    "bank_account_name": "We are using my personal bank account for payouts during setup, so "
                         "the account holder name differs from the business name.",
    "bank_routing_number": "We switched banks last month; the new routing number is on this "
                           "application, but our paperwork on file still references the old "
                           "bank.",
    "owner_name": "I recently changed my legal name after marriage; my ID is being updated and "
                 "still shows my previous name.",
    "owner_address": "I moved to a new home address recently; my government ID has not been "
                     "reissued yet and still shows my prior address.",
}

# Deliberately free of every phrase in KEYWORDS above -- these are the notes a banking_trap or
# denied_multi application carries, and none of them may accidentally explain the mismatch they
# sit beside. See the assert in build_application() that catches it if one ever does.
GENERIC_NOTES = (
    "", "", "",
    "Excited to start selling on the platform!",
    "Please let us know if anything else is needed.",
    "Attached our updated product catalog for reference.",
    "Looking forward to getting started.",
    "Thank you for reviewing our application promptly.",
    "Let me know if you need any additional documents.",
    "We hope to have our store live by next month.",
)

BUSINESS_PLACE_WORDS = (
    "Northfield", "Cobalt Ridge", "Marrow Lane", "Suncrest", "Fernbridge", "Ashwell",
    "Briarcliff", "Milltown", "Hollow Oak", "Wrenhaven", "Palmerston", "Kestrel Bay",
    "Thistledown", "Ironvale", "Larkspur", "Copperfield", "Greymoor", "Windmere", "Sablewood",
    "Fenwick", "Rosemont", "Bellwater", "Thornfield", "Graystone", "Alderbrook", "Foxglove",
    "Hartwell", "Mossbank", "Wickford", "Clearwater",
)
BUSINESS_PRODUCT_WORDS = (
    "Outdoor Goods", "Apparel", "Ceramics", "Pantry Goods", "Pet Supply", "Home Decor",
    "Candle Works", "Leather Goods", "Toys", "Stationery", "Bicycle Parts", "Swimwear",
    "Bath Co", "Tools", "Garden Supply", "Coffee Roasters", "Furniture", "Baby Goods",
    "Craft Supply", "Kitchenware",
)
BUSINESS_SUFFIXES = ("LLC", "Inc.", "Co.")
CATEGORIES = ("Home & Garden", "Apparel & Accessories", "Health & Beauty", "Sporting Goods",
             "Toys & Games", "Office Supplies", "Pet Supplies", "Food & Beverage")

FIRST_NAMES = ("Maria", "James", "Priya", "Devon", "Elena", "Marcus", "Sofia", "Ibrahim", "Grace",
              "Tomas", "Aisha", "Noah", "Yuki", "Carlos", "Hannah", "Leo", "Nadia", "Owen", "Rosa",
              "Ethan")
LAST_NAMES = ("Delgado", "Whitfield", "Nakamura", "Okafor", "Petrov", "Lindqvist", "Alvarez",
             "Choudhury", "Bergstrom", "Marsh", "Kowalski", "Fontaine", "Osei", "Vance",
             "Salinas", "Bianchi", "Hollis", "Reyes", "Norgaard", "Castillo")

STREET_NAMES = ("Maple", "Birch", "Cedar", "Aspen", "Willow", "Hazel", "Linden", "Sycamore",
               "Poplar", "Elm", "Magnolia", "Juniper", "Rowan", "Alder", "Larch")
STREET_TYPES = ("St.", "Ave.", "Blvd.", "Ln.", "Dr.", "Way", "Ct.")
CITY_STATE_ZIP = (
    ("Millbrook", "OH", "44201"), ("Fairview", "TX", "75069"), ("Kingston", "NY", "12401"),
    ("Salem", "OR", "97301"), ("Brookhaven", "GA", "30319"), ("Riverton", "WY", "82501"),
    ("Clarksville", "TN", "37040"), ("Newport", "RI", "02840"), ("Bristol", "CT", "06010"),
    ("Ashland", "WI", "54806"), ("Dover", "DE", "19901"), ("Concord", "NH", "03301"),
    ("Lakeview", "MI", "48850"), ("Fairhope", "AL", "36532"), ("Ridgefield", "CT", "06877"),
    ("Greenville", "SC", "29601"), ("Bellevue", "WA", "98004"), ("Cedarburg", "WI", "53012"),
    ("Northport", "AL", "35473"), ("Havelock", "NC", "28532"),
)


def _business_name(rng):
    return "%s %s %s" % (rng.choice(BUSINESS_PLACE_WORDS), rng.choice(BUSINESS_PRODUCT_WORDS),
                        rng.choice(BUSINESS_SUFFIXES))


def _owner_name(rng):
    return "%s %s" % (rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES))


def _address(rng):
    n = rng.randint(10, 9999)
    street = "%s %s" % (rng.choice(STREET_NAMES), rng.choice(STREET_TYPES))
    city, state, zipc = rng.choice(CITY_STATE_ZIP)
    return "%d %s, %s, %s %s" % (n, street, city, state, zipc)


def _ein(rng):
    return "%02d-%07d" % (rng.randint(10, 99), rng.randint(1000000, 9999999))


def _routing(rng):
    return "%09d" % rng.randint(100000000, 999999999)


def _different(rng, gen, avoid):
    v = gen(rng)
    while v == avoid:
        v = gen(rng)
    return v


# ── derivation, the ONLY place the flag rule and the outcome rule are written ──────────────────

def derive_flags(app):
    """The three-way flag for every field pair, from the record's own values and its own note --
    never from a variable naming what the builder intended. Used to label gold at generation time
    and, independently, by --verify to re-derive gold from data/*.jsonl on disk."""
    d = app["declared"]
    doc = {
        "business_name": app["business_registration"]["legal_name"],
        "business_address": app["business_registration"]["registered_address"],
        "tax_id": app["business_registration"]["tax_id"],
        "bank_account_name": app["bank_letter"]["account_holder_name"],
        "bank_routing_number": app["bank_letter"]["routing_number"],
        "owner_name": app["id_document"]["full_name"],
        "owner_address": app["id_document"]["address"],
    }
    note = (app.get("submission_note") or "").lower()
    flags = {}
    for f in P.FIELDS:
        if d[f] == doc[f]:
            flags[f] = "match"
        else:
            explained = any(kw in note for kw in KEYWORDS[f])
            flags[f] = "mismatch_explained" if explained else "mismatch"
    return flags


def derive_outcome(flags):
    """The historical verification_outcome, derived from the flags alone -- never authored. Any
    unexplained mismatch on a banking-identity field (bank_account_name or bank_routing_number)
    is the pattern a fraudulent application produces, and is denied. An unexplained mismatch
    confined to identity fields (business or owner) is ambiguous rather than damning, and is
    escalated for a human to resolve. No unexplained mismatch at all -- everything matches, or
    every discrepancy is genuinely explained -- is approved."""
    unexplained = [f for f in P.FIELDS if flags[f] == "mismatch"]
    if not unexplained:
        return "approved"
    if any(f in BANKING_FIELDS for f in unexplained):
        return "denied"
    return "escalated"


# ── application construction ────────────────────────────────────────────────────────────────

NONBANKING_FIELDS = tuple(f for f in P.FIELDS if f not in BANKING_FIELDS)


def _base_application(app_id, rng):
    """Every field matches its document counterpart -- the starting point every pattern mutates
    from. Building "all clean" first and then mutating specific pairs is what keeps a trap
    application's other six fields honestly clean, not merely unmutated by omission."""
    business_name = _business_name(rng)
    owner_name = _owner_name(rng)
    business_address = _address(rng)
    owner_address = _different(rng, _address, business_address)
    tax_id = _ein(rng)
    routing = _routing(rng)

    declared = {
        "business_name": business_name, "business_address": business_address,
        "tax_id": tax_id, "bank_account_name": business_name,
        "bank_routing_number": routing, "owner_name": owner_name,
        "owner_address": owner_address,
    }
    return {
        "application_id": app_id,
        "category": rng.choice(CATEGORIES),
        "declared": declared,
        "business_registration": {
            "legal_name": business_name, "registered_address": business_address,
            "tax_id": tax_id,
        },
        "bank_letter": {"account_holder_name": business_name, "routing_number": routing},
        "id_document": {"full_name": owner_name, "address": owner_address},
        "submission_note": "",
    }


def _mutate(app, field, rng):
    """Change ONE document-side field to a different, plausible value -- declared stays exactly
    what the applicant typed. bank_account_name is special-cased to the applicant's own name
    rather than a random one: a bank letter naming the owner instead of the business is the real
    shape of the "personal account during setup" pattern, not an arbitrary stranger's name."""
    d = app["declared"]
    if field == "business_name":
        app["business_registration"]["legal_name"] = _different(rng, _business_name,
                                                                 d["business_name"])
    elif field == "business_address":
        app["business_registration"]["registered_address"] = _different(
            rng, _address, d["business_address"])
    elif field == "tax_id":
        app["business_registration"]["tax_id"] = _different(rng, _ein, d["tax_id"])
    elif field == "bank_account_name":
        app["bank_letter"]["account_holder_name"] = d["owner_name"]
    elif field == "bank_routing_number":
        app["bank_letter"]["routing_number"] = _different(rng, _routing,
                                                           d["bank_routing_number"])
    elif field == "owner_name":
        app["id_document"]["full_name"] = _different(rng, _owner_name, d["owner_name"])
    elif field == "owner_address":
        app["id_document"]["address"] = _different(rng, _address, d["owner_address"])
    else:
        raise ValueError("unknown field %r" % field)


def build_application(app_no, pattern, rng):
    """One application, built to a named pattern, then checked against derive_flags() /
    derive_outcome() rather than trusted -- same discipline fin-payrun's build_invoice() uses for
    derive_stage(). `expect_flags` and `expect_outcome` are what this function INTENDS to build;
    gold is written from the recomputed flags/outcome, never from these intentions directly, so a
    bug in the field construction below cannot silently ship a mislabelled row."""
    app_id = "APP-2024-%04d" % app_no
    app = _base_application(app_id, rng)
    expect_flags = {f: "match" for f in P.FIELDS}
    trap_field = None

    if pattern == "clean":
        app["submission_note"] = rng.choice(GENERIC_NOTES)

    elif pattern == "banking_trap":
        _mutate(app, "bank_routing_number", rng)
        app["submission_note"] = rng.choice(GENERIC_NOTES)          # empty or unrelated, on purpose
        expect_flags["bank_routing_number"] = "mismatch"
        trap_field = "bank_routing_number"

    elif pattern == "explained_single":
        field = _EXPLAINED_FIELD_CYCLE[app_no % len(_EXPLAINED_FIELD_CYCLE)]
        _mutate(app, field, rng)
        app["submission_note"] = EXPLAIN_NOTES[field]
        expect_flags[field] = "mismatch_explained"

    elif pattern == "escalated_nonbanking":
        field = rng.choice(NONBANKING_FIELDS)
        _mutate(app, field, rng)
        app["submission_note"] = rng.choice(GENERIC_NOTES)
        expect_flags[field] = "mismatch"

    elif pattern == "denied_multi":
        others = rng.sample([f for f in NONBANKING_FIELDS], 2)
        for f in ("bank_account_name",) + tuple(others[:rng.choice((1, 2))]):
            _mutate(app, f, rng)
            expect_flags[f] = "mismatch"
        app["submission_note"] = rng.choice(GENERIC_NOTES)

    else:
        raise ValueError("unknown pattern %r" % pattern)

    flags = derive_flags(app)
    assert flags == expect_flags, (
        "%s (pattern %s): built for %r but derive_flags() says %r -- the field construction "
        "above and the note's trigger phrases have drifted" % (app_id, pattern, expect_flags,
                                                                flags))
    outcome = derive_outcome(flags)

    gold = {"application_id": app_id, "verification_outcome": outcome,
           "trap": trap_field is not None, "trap_field": trap_field, "pattern": pattern}
    gold.update(flags)
    return app, gold


# One explained_single application per field pair, in field order, so all seven get covered before
# any field repeats -- bank_account_name and bank_routing_number each appear an extra time because
# they are the two fields evals/scoring.py's named metrics care about discriminating explained
# from unexplained.
_EXPLAINED_FIELD_CYCLE = list(P.FIELDS) + ["bank_account_name"]


def build_corpus(rng):
    plan = []
    for pattern, n in PATTERN_COUNTS.items():
        plan.extend([pattern] * n)
    rng.shuffle(plan)

    app_numbers = rng.sample(range(100, 2000), len(plan))

    applications, gold = [], []
    for no, pattern in zip(app_numbers, plan):
        app, g = build_application(no, pattern, rng)
        applications.append(app)
        gold.append(g)

    trap_n = sum(1 for g in gold if g["trap"])
    assert trap_n == TRAP_N, "expected %d trap applications, built %d" % (TRAP_N, trap_n)
    return applications, gold


def write(applications, gold):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "applications.jsonl"), "w", encoding="utf-8") as fh:
        for app in applications:
            fh.write(json.dumps(app) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")


def verify():
    """Re-read data/applications.jsonl and data/gold.jsonl FROM DISK -- not from
    build_corpus()'s in-memory return values -- and re-derive every gold row independently via
    derive_flags() / derive_outcome(). This is the mandatory internal-consistency check: gold
    must never be hand-labelled or copy-pasted, it must be reproducible from the application
    record alone, every time, by anyone who clones the repo. Same discipline fin-payrun's and
    fin-invval's corpus builders both enforce."""
    apps_path = os.path.join(DATA, "applications.jsonl")
    gold_path = os.path.join(DATA, "gold.jsonl")
    applications = [json.loads(l) for l in open(apps_path, encoding="utf-8") if l.strip()]
    gold_rows = {g["application_id"]: g for g in
                (json.loads(l) for l in open(gold_path, encoding="utf-8") if l.strip())}

    checked = 0
    for app in applications:
        g = gold_rows[app["application_id"]]
        flags = derive_flags(app)
        for f in P.FIELDS:
            assert flags[f] == g[f], (
                "%s: gold says %s=%r but derive_flags(record) says %r"
                % (app["application_id"], f, g[f], flags[f]))
        outcome = derive_outcome(flags)
        assert outcome == g["verification_outcome"], (
            "%s: gold says verification_outcome=%r but derive_outcome(flags) says %r"
            % (app["application_id"], g["verification_outcome"], outcome))
        checked += 1

    trap_rows = [g for g in gold_rows.values() if g["trap"]]
    print("verify: %d applications checked against gold, all 7 flags + outcome match, 0 drift"
          % checked)
    print("verify: %d trap applications, all trap_field=bank_routing_number, all mismatch "
          "unexplained, all denied" % len(trap_rows))
    for g in trap_rows:
        assert g["trap_field"] == "bank_routing_number"
        assert g["bank_routing_number"] == "mismatch"
        assert g["verification_outcome"] == "denied"
        assert all(g[f] == "match" for f in P.FIELDS if f != "bank_routing_number")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="re-derive gold from data/*.jsonl on disk and assert no drift; does "
                         "not regenerate anything")
    a = ap.parse_args()

    if a.verify:
        verify()
        return

    rng = random.Random(SEED)
    applications, gold = build_corpus(rng)
    write(applications, gold)

    tally = {}
    outcome_tally = {}
    for g in gold:
        tally[g["pattern"]] = tally.get(g["pattern"], 0) + 1
        outcome_tally[g["verification_outcome"]] = outcome_tally.get(g["verification_outcome"],
                                                                     0) + 1
    trap_n = sum(1 for g in gold if g["trap"])
    print("applications: %d" % len(applications))
    print("pattern tally:", tally)
    print("outcome tally:", outcome_tally)
    print("trap applications (bank_routing_number, otherwise clean): %d of %d (%.0f%%)"
          % (trap_n, len(gold), 100.0 * trap_n / len(gold)))
    verify()


if __name__ == "__main__":
    main()
