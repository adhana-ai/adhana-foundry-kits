#!/usr/bin/env python3
"""Generate synthetic sanctions-screening alert review sheets and their gold labels, from a fixed
seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one alert per file) and data/gold.jsonl, byte-identical on every run.

⚠︎ EVERYTHING IN THIS CORPUS IS INVENTED, AND THAT IS NOT A DISCLAIMER, IT IS THE CONSTRUCTION.
Every person name is built from an invented syllable pool; every country, city and place of birth
is invented; every list name and programme name is invented; every passport, identity and tax
number is generated from a made-up format. NO real sanctions programme, designation list,
authority, jurisdiction, country-specific regime, institution or person is named anywhere in this
kit, and none was consulted. Nothing is fetched and nothing is licensed from anybody, so the corpus
ships under this repo's MIT licence.

⚑ GOLD `verdict` AND `deciding_identifier` ARE RULEBOOK LOOKUPS, NOT LABELS SOMEBODY TYPED. Both
are derived from the same eight structured values the generator itself decided, with the same rule
the kit publishes everywhere else -- src/rulebook.py::decide(), which src/prompt.py states to the
model in words and evals/judge.py re-runs over the model's own reply. Neither is ever derived from
the names, the nationalities, the engine's match score or the analyst's note.

⚑ THE FIVE CHECKS, AND WHY THEY HAVE A STOPPING ORDER. Is a strong identifier of the SAME TYPE on
both records and equal; is one there and different; then, only then, does a comparable moderate
identifier conflict; then, do enough of them agree; and otherwise the file does not decide. Each of
the four hard buckets below exists because a reader who skips a step, or takes them out of order,
gets that bucket wrong:

  same_strong_id_translit -- the names are transliteration variants, the nationalities disagree,
                             the PLACES OF BIRTH disagree, and the engine scored the pair low --
                             and both records carry the same passport number. Same party. A strong
                             identifier outranks every disagreement below it.
  not_strong_conflict     -- the names are identical, the full dates of birth agree, the places of
                             birth agree, the nationalities agree and the engine scored it 0.9+ --
                             and the two passport numbers are different. Not a match. The same
                             absoluteness pointing the other way.
  insuff_no_secondary     -- a common name and nothing else: no comparable strong identifier, no
                             date of birth on one side, no place of birth published. Nothing on the
                             file decides it, and saying so is the answer.
  insuff_partial_dob      -- a year-only or year-and-month date of birth on the watchlist entry. A
                             partial date is a STATED FACT and it is still not comparable; with the
                             place of birth agreeing that leaves ONE agreement against a threshold
                             of two. Complete the date and the same sheet reads same_party.

⚑ THE ANALYST NOTE'S REGISTER FOLLOWS THE ENGINE'S MATCH SCORE, NOT THE VERDICT -- AND THAT IS THE
WHOLE POINT OF IT. The note is written by somebody who saw two names and a similarity score and had
not yet compared identifiers, so a high-scoring name pair gets a confident note and a low-scoring
one gets a dismissive note. Because name similarity is decorrelated from the identifiers on this
corpus -- which is exactly why screening false positives exist -- the note points the wrong way
more often than not. Anything that classifies off the note's TONE, including evals/baseline.py
deliberately, fails those sheets by construction. Anything that reads the identifiers gets them
right. The contradiction rate is MEASURED at the end of this file rather than dialled in.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51.
# A count 1.7 standard deviations off its own design is not a corpus property, it is sampling noise
# being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
BUCKETS = [
    ("same_strong_id", 8),            # same strong identifier, same value -- the ordinary hit
    ("same_strong_id_translit", 6),   # ditto, but the names, nationality and place of birth differ
    ("same_moderate_pair", 6),        # no comparable strong id; full DOB and place both agree
    ("not_strong_conflict", 8),       # same strong identifier TYPE, different value -- everything
                                      # else agrees and it is still not a match
    ("not_moderate_conflict", 7),     # no strong id; one comparable moderate identifier conflicts
    ("insuff_no_secondary", 8),       # a common name and nothing comparable at all
    ("insuff_partial_dob", 7),        # a partial date of birth; one agreement against a threshold
]

# How alike the two NAMES look, dealt exactly within each bucket. This drives the engine's match
# score, which in turn drives the analyst note's register -- so the note is a function of how the
# names read and never of what the identifiers say.
CLOSENESS = {
    "same_strong_id":          [("near", 6), ("mid", 2)],
    "same_strong_id_translit": [("far", 6)],
    "same_moderate_pair":      [("near", 3), ("mid", 2), ("far", 1)],
    "not_strong_conflict":     [("near", 6), ("mid", 2)],
    "not_moderate_conflict":   [("near", 2), ("mid", 3), ("far", 2)],
    "insuff_no_secondary":     [("near", 4), ("mid", 2), ("far", 2)],
    "insuff_partial_dob":      [("near", 3), ("mid", 2), ("far", 2)],
}

# The engine's own fuzzy-name score, by how alike the names are. It lives in the Screening List
# section, which src/select.py maps to NOTHING, so it never reaches the model at all.
SCORE_BANDS = {"near": (0.88, 0.97), "mid": (0.71, 0.84), "far": (0.55, 0.69)}

N_LIVE = 24                          # account_status == "live"; the rest are pending_onboarding

# ---- invented vocabulary ---------------------------------------------------------------------
# Names are assembled from syllables that were made up for this file. They are not drawn from any
# real name register, telephone directory, list or dataset, and any resemblance to a living person
# is a coincidence of syllables rather than a reference.
GIVEN = ["Aravel", "Bethun", "Corvane", "Dalmir", "Eskilde", "Farven", "Ghiselle", "Halvra",
         "Ivorin", "Jessamir", "Kestran", "Lorvane", "Maruth", "Nevrid", "Orsolen", "Pellamir",
         "Quenvar", "Rasmyre", "Sondrel", "Tavrick", "Urwen", "Vandric", "Wesmar", "Yorvale",
         "Zelmira"]
SURNAME = ["Aldreth", "Bracamo", "Corvella", "Dravenil", "Eskelund", "Farrowyne", "Gattikor",
           "Halbric", "Immerdav", "Jarnevik", "Kestrane", "Lomvard", "Marrowvy", "Nesvalen",
           "Oravin", "Pelleway", "Quillonet", "Ravensmoor", "Sorrenvold", "Thackmere",
           "Uldenvast", "Vessarine", "Wintermark", "Yalbrook", "Zorranth"]

# ⚑ A DELIBERATELY SMALL POOL, REUSED. The `insuff_no_secondary` bucket is about the commonest
# reason a screening desk cannot decide an alert: an ordinary name shared by a lot of people, with
# nothing else on the file. Reusing three names across those eight alerts is what makes that
# visible in the corpus rather than merely asserted in a comment.
COMMON_NAMES = [("Maruth", "Oravin"), ("Sondrel", "Halbric"), ("Nevrid", "Lomvard")]

COUNTRIES = ["Verdania", "Kastelia", "Northmarch", "Oradon", "Sulmara", "Tavrinia", "Ellisar",
             "Corvant", "Meridonia", "Brackenholt"]
PLACES = ["Port Ellisar", "Kadrun", "Veldt Harbour", "Fennmarch", "Old Saltrun", "Highspire",
          "Corvant City", "Lower Thessin", "Braymoor", "Ilvane Reach"]

# Invented list names and invented programme names. No real list, programme, regime or authority
# is named, referenced or alluded to anywhere in this kit.
WATCHLISTS = ["Consolidated Restricted Parties Index", "Global Designated Entities Register",
              "Cross-Border Restricted Persons Schedule", "Unified Prohibited Counterparties List"]
PROGRAMMES = ["Programme Ashgrove", "Programme Tallowmere", "Programme Northline",
              "Programme Cindermark", "Programme Quillstone"]

IDENTIFIER_LABEL = {"passport_number": "Passport Number",
                    "national_id_number": "National Identity Number",
                    "tax_reference": "Tax Reference"}

# Notes whose TONE says "this is the listed party". Written by an analyst looking at two names and
# a high similarity score, before anybody compared identifiers.
CONFIDENT_NOTES = [
    "Same person as far as I can see -- I would treat this as a match.",
    "Looks like a clear hit to me; the file lines up.",
    "I am satisfied these are the same party.",
    "Confident this is the listed party, on the face of it.",
]

# Notes whose TONE says "this is somebody else". Written off a low similarity score.
DISMISSIVE_NOTES = [
    "Different person, clearly. Nothing beyond the name lines up.",
    "I would close this one; it does not look like our customer at all.",
    "Coincidence of names, nothing more.",
    "Not the same party in my view -- the records read quite differently.",
]

# Notes whose TONE says "I cannot tell". Written off a middling similarity score.
HEDGING_NOTES = [
    "Honestly cannot separate these two from what is on the file.",
    "Not enough here to call it either way; asked for more from onboarding.",
    "I have gone back and forth on this one and cannot land it.",
    "Would want a second identifier before saying anything.",
]

NOTES_BY_REGISTER = {"confident": CONFIDENT_NOTES, "dismissive": DISMISSIVE_NOTES,
                     "hedging": HEDGING_NOTES}

# What each register would mean if tone were evidence. It is not, and evals/baseline.py exists to
# measure how badly that assumption does.
REGISTER_VERDICT = {"confident": "same_party", "dismissive": "not_a_match",
                    "hedging": "insufficient_information"}

# ⚑ TRANSLITERATION IS A CHARACTER RULE, NOT A TYPO. Each `far` name is the SAME invented name
# respelled by two of these substitutions -- the shape a name takes when it crosses a script and
# comes back. That is why the engine scores those pairs low and why the analyst dismisses them,
# and it is why the passport number is the only thing on the sheet that can settle them.
TRANSLIT_RULES = [("v", "w"), ("k", "kh"), ("c", "k"), ("y", "i"), ("th", "t"), ("e", "ae")]


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def _translit(name, rng):
    """A transliteration variant of an invented name. Never returns the name unchanged."""
    for _ in range(40):
        out = name
        for a, b in rng.sample(TRANSLIT_RULES, 2):
            out = out.replace(a, b)
            out = out.replace(a.capitalize(), b.capitalize())
        if out and out[-1] in "aeiou" and rng.random() < 0.7:
            out += "h"
        if out != name:
            return out
    return name + "h"


def _listed_name(given, surname, closeness, rng):
    """How the watchlist entry spells the same invented name."""
    if closeness == "near":
        return "%s %s" % (given, surname)
    if closeness == "mid":
        return "%s. %s" % (given[0], surname)
    return "%s %s" % (_translit(given, rng), _translit(surname, rng))


def _aliases(given, surname, listed, closeness, rng):
    """The `Also Listed As` line. It always carries at least one form, and on a transliteration
    alert it deliberately carries the customer's OWN spelling -- a real list does, and it is the
    trap for anything that reads the alias line instead of the Listed Name line."""
    pool = []
    if closeness == "far":
        pool.append("%s %s" % (given, surname))
        pool.append("%s. %s" % (listed.split()[0][0], listed.split()[-1]))
    elif closeness == "mid":
        pool.append("%s %s" % (given, surname))
    else:
        pool.append("%s. %s" % (given[0], surname))
        pool.append("%s %s" % (_translit(given, rng), surname))
    return "; ".join(pool[:2])


def _passport(rng):
    return "%s%s%07d" % (rng.choice("ABCDEFGHJKLMNPRSTVWXYZ"),
                         rng.choice("ABCDEFGHJKLMNPRSTVWXYZ"), rng.randint(1000000, 9999999))


def _national_id(rng):
    return "NID-%04d-%04d" % (rng.randint(1000, 9999), rng.randint(1000, 9999))


def _tax_ref(rng):
    return "TRF-%08d" % rng.randint(10000000, 99999999)


ID_MAKERS = {"passport_number": _passport, "national_id_number": _national_id,
             "tax_reference": _tax_ref}


def _make_id(rng, kind):
    return ID_MAKERS[kind](rng)


def _dob(rng):
    return "%04d-%02d-%02d" % (rng.randint(1955, 1996), rng.randint(1, 12), rng.randint(1, 28))


def _other_dob(rng, not_this):
    for _ in range(200):
        d = _dob(rng)
        if d != not_this:
            return d
    raise RuntimeError("could not draw a second date of birth")


def _partial(rng, full):
    """A year-only or year-and-month form of a full date. A STATED FACT, and still not comparable."""
    return full[:4] if rng.random() < 0.57 else full[:7]


def _other(rng, pool, not_this):
    for _ in range(200):
        v = rng.choice(pool)
        if v != not_this:
            return v
    raise RuntimeError("could not draw a different value from %r" % (pool,))


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns the eight decision values plus the presentation extras,
# and each is ASSERTED against the rulebook in build_all -- a constructor that quietly stops
# producing its own bucket is exactly the defect an exact composition exists to prevent.
#
# `no_strong` below is the three ways two records end up with nothing strong to compare, and all
# three are ordinary states on a real queue: the customer record has nothing, the list entry
# publishes nothing, or both carry an identifier and they are of DIFFERENT TYPES.
# --------------------------------------------------------------------------------------------

def _no_strong(rng):
    """(customer_type, customer_value, listed_type, listed_value) with no comparable strong pair."""
    shape = rng.choice(["customer_none", "listed_none", "different_types", "both_none"])
    a, b = rng.sample(list(RB.STRONG), 2)
    if shape == "customer_none":
        return "none", None, b, _make_id(rng, b)
    if shape == "listed_none":
        return a, _make_id(rng, a), "none", None
    if shape == "both_none":
        return "none", None, "none", None
    return a, _make_id(rng, a), b, _make_id(rng, b)


def _mk_same_strong_id(rng):
    kind = rng.choice(list(RB.STRONG))
    value = _make_id(rng, kind)
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    listed_dob = dob if rng.random() < 0.6 else None
    listed_pob = pob if rng.random() < 0.6 else None
    return {"customer_identifier_type": kind, "customer_identifier_value": value,
            "listed_identifier_type": kind, "listed_identifier_value": value,
            "customer_dob": dob, "listed_dob": listed_dob,
            "customer_place_of_birth": pob, "listed_place_of_birth": listed_pob,
            "customer_nationality": nat, "listed_nationality": nat}


def _mk_same_strong_id_translit(rng):
    """The sharpest case: one strong identifier against several weak mismatches AND a conflicting
    place of birth. Everything a reader eyeballs points the wrong way."""
    kind = rng.choice(list(RB.STRONG))
    value = _make_id(rng, kind)
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    return {"customer_identifier_type": kind, "customer_identifier_value": value,
            "listed_identifier_type": kind, "listed_identifier_value": value,
            "customer_dob": dob, "listed_dob": dob,
            "customer_place_of_birth": pob, "listed_place_of_birth": _other(rng, PLACES, pob),
            "customer_nationality": nat, "listed_nationality": _other(rng, COUNTRIES, nat)}


def _mk_same_moderate_pair(rng):
    ct, cv, lt, lv = _no_strong(rng)
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    return {"customer_identifier_type": ct, "customer_identifier_value": cv,
            "listed_identifier_type": lt, "listed_identifier_value": lv,
            "customer_dob": dob, "listed_dob": dob,
            "customer_place_of_birth": pob, "listed_place_of_birth": pob,
            "customer_nationality": nat,
            "listed_nationality": nat if rng.random() < 0.5 else _other(rng, COUNTRIES, nat)}


def _mk_not_strong_conflict(rng):
    """The identifier is the ONLY thing that separates them. Name, full date of birth, place of
    birth and nationality all agree, and the engine scored it high."""
    kind = rng.choice(list(RB.STRONG))
    a = _make_id(rng, kind)
    for _ in range(200):
        b = _make_id(rng, kind)
        if b != a:
            break
    else:
        raise RuntimeError("could not draw a conflicting identifier")
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    return {"customer_identifier_type": kind, "customer_identifier_value": a,
            "listed_identifier_type": kind, "listed_identifier_value": b,
            "customer_dob": dob, "listed_dob": dob,
            "customer_place_of_birth": pob, "listed_place_of_birth": pob,
            "customer_nationality": nat, "listed_nationality": nat}


def _mk_not_moderate_conflict(rng, on_place=False):
    ct, cv, lt, lv = _no_strong(rng)
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    if on_place:
        # The date cannot be the thing that decides it, so it is made NOT COMPARABLE -- partial on
        # the list side. The place of birth is then the only comparable moderate identifier, and
        # it conflicts.
        return {"customer_identifier_type": ct, "customer_identifier_value": cv,
                "listed_identifier_type": lt, "listed_identifier_value": lv,
                "customer_dob": dob, "listed_dob": _partial(rng, dob),
                "customer_place_of_birth": pob,
                "listed_place_of_birth": _other(rng, PLACES, pob),
                "customer_nationality": nat, "listed_nationality": nat}
    return {"customer_identifier_type": ct, "customer_identifier_value": cv,
            "listed_identifier_type": lt, "listed_identifier_value": lv,
            "customer_dob": dob, "listed_dob": _other_dob(rng, dob),
            "customer_place_of_birth": pob,
            "listed_place_of_birth": pob if rng.random() < 0.5 else None,
            "customer_nationality": nat, "listed_nationality": nat}


def _mk_insuff_no_secondary(rng):
    """A common name and nothing else. Nothing comparable on either tier."""
    ct, cv, lt, lv = _no_strong(rng)
    dob = _dob(rng)
    nat = rng.choice(COUNTRIES)
    drop_customer_dob = rng.random() < 0.5
    return {"customer_identifier_type": ct, "customer_identifier_value": cv,
            "listed_identifier_type": lt, "listed_identifier_value": lv,
            "customer_dob": None if drop_customer_dob else dob,
            "listed_dob": dob if drop_customer_dob else None,
            "customer_place_of_birth": rng.choice(PLACES) if rng.random() < 0.7 else None,
            "listed_place_of_birth": None,
            "customer_nationality": nat,
            "listed_nationality": nat if rng.random() < 0.6 else _other(rng, COUNTRIES, nat)}


def _mk_insuff_partial_dob(rng):
    """A partial date of birth on the list entry. The place of birth agrees, which is ONE
    agreement against a threshold of two -- complete the date and the same sheet reads
    same_party."""
    ct, cv, lt, lv = _no_strong(rng)
    dob = _dob(rng)
    pob = rng.choice(PLACES)
    nat = rng.choice(COUNTRIES)
    return {"customer_identifier_type": ct, "customer_identifier_value": cv,
            "listed_identifier_type": lt, "listed_identifier_value": lv,
            "customer_dob": dob, "listed_dob": _partial(rng, dob),
            "customer_place_of_birth": pob, "listed_place_of_birth": pob,
            "customer_nationality": nat, "listed_nationality": nat}


MAKERS = {
    "same_strong_id": _mk_same_strong_id,
    "same_strong_id_translit": _mk_same_strong_id_translit,
    "same_moderate_pair": _mk_same_moderate_pair,
    "not_strong_conflict": _mk_not_strong_conflict,
    "not_moderate_conflict": _mk_not_moderate_conflict,
    "insuff_no_secondary": _mk_insuff_no_secondary,
    "insuff_partial_dob": _mk_insuff_partial_dob,
}

EXPECTED_VERDICT = {
    "same_strong_id": "same_party",
    "same_strong_id_translit": "same_party",
    "same_moderate_pair": "same_party",
    "not_strong_conflict": "not_a_match",
    "not_moderate_conflict": "not_a_match",
    "insuff_no_secondary": "insufficient_information",
    "insuff_partial_dob": "insufficient_information",
}

# Of the 7 not_moderate_conflict alerts, this many are decided by the PLACE of birth rather than
# the date -- so `deciding_identifier` has members in both moderate classes and the grader over it
# is not a two-value grader wearing a seven-value label.
N_PLACE_CONFLICT = 3


def _values_for(vals):
    """The eight arguments src/rulebook.py::decide takes, in its own order."""
    return (vals["customer_identifier_type"], vals["customer_identifier_value"],
            vals["listed_identifier_type"], vals["listed_identifier_value"],
            vals["customer_dob"], vals["listed_dob"],
            vals["customer_place_of_birth"], vals["listed_place_of_birth"])


def _id_line(kind, value, side):
    if kind == "none":
        return ("No secondary identifier on file" if side == "customer"
                else "No identifier published for this entry")
    return "%s: %s" % (IDENTIFIER_LABEL[kind], value)


def _stated(value, side, what):
    if value is not None:
        return "%s: %s" % (what, value)
    return "%s: %s" % (what, "not recorded" if side == "customer" else "not published")


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:                      # a --n other than the design keeps the shape, roughly
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)
    live = _deal(rng, n, [("live", N_LIVE), ("pending_onboarding", n - N_LIVE)])

    closeness_pools = {name: _deal(rng, sum(c for _v, c in CLOSENESS[name]), CLOSENESS[name])
                       for name, _count in BUCKETS}
    place_conflicts_left = N_PLACE_CONFLICT
    common_left = list(COMMON_NAMES) * 3

    stats = {"verdicts": {}, "deciding": {}, "buckets": {name: 0 for name, _ in BUCKETS},
             "register_contradicts": 0, "needs_escalation": 0, "closeness": {},
             "translit_decided_by_id": 0, "conflict_decided_by_id": 0,
             "partial_dob": 0, "common_name": 0}

    out = []
    for i in range(1, n + 1):
        bucket = buckets[i - 1]
        closeness = closeness_pools[bucket].pop()

        if bucket == "not_moderate_conflict" and place_conflicts_left > 0:
            vals = _mk_not_moderate_conflict(rng, on_place=True)
            place_conflicts_left -= 1
        else:
            vals = MAKERS[bucket](rng)

        if bucket == "insuff_no_secondary" and common_left:
            given, surname = common_left.pop(0)
            stats["common_name"] += 1
        else:
            given, surname = rng.choice(GIVEN), rng.choice(SURNAME)
        customer_name = "%s %s" % (given, surname)
        listed_name = _listed_name(given, surname, closeness, rng)
        aliases = _aliases(given, surname, listed_name, closeness, rng)

        d = RB.decide(*_values_for(vals))
        verdict, deciding = d["verdict"], d["deciding_identifier"]
        assert verdict == EXPECTED_VERDICT[bucket], \
            "%s produced %r, not %r" % (bucket, verdict, EXPECTED_VERDICT[bucket])

        lo, hi = SCORE_BANDS[closeness]
        score = round(rng.uniform(lo, hi), 2)
        register = ("confident" if score >= 0.85 else
                    "hedging" if score >= 0.70 else "dismissive")
        note = rng.choice(NOTES_BY_REGISTER[register])
        if REGISTER_VERDICT[register] != verdict:
            stats["register_contradicts"] += 1

        status = live[i - 1]
        watchlist = rng.choice(WATCHLISTS)
        programme = rng.choice(PROGRAMMES)
        published = "%04d-%02d-%02d" % (rng.randint(2023, 2026), rng.randint(1, 12),
                                        rng.randint(1, 28))
        alert_id = "ALR-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                      rng.randint(10000, 99999))

        rec_id = "SCR-%04d" % i
        lines = [
            _underline("Alert Reference"), alert_id, "",
            _underline("Screening List"),
            "%s -- programme: %s" % (watchlist, programme),
            "Entry published: %s" % published,
            "Engine match score: %.2f" % score, "",
            _underline("Customer Record"),
            "Name: %s" % customer_name,
            _stated(vals["customer_dob"], "customer", "Date of Birth"),
            _stated(vals["customer_place_of_birth"], "customer", "Place of Birth"),
            "Nationality: %s" % vals["customer_nationality"],
            _id_line(vals["customer_identifier_type"], vals["customer_identifier_value"],
                     "customer"), "",
            _underline("Watchlist Entry"),
            "Listed Name: %s" % listed_name,
            "Also Listed As: %s" % aliases,
            _stated(vals["listed_dob"], "listed", "Date of Birth"),
            _stated(vals["listed_place_of_birth"], "listed", "Place of Birth"),
            "Nationality: %s" % vals["listed_nationality"],
            _id_line(vals["listed_identifier_type"], vals["listed_identifier_value"], "listed"), "",
            _underline("Account Status"), status, "",
            _underline("Analyst Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "alert_id_key": rec_id,
            "alert_id": alert_id,
            "customer_name": customer_name,
            "listed_name": listed_name,
            "customer_identifier_type": vals["customer_identifier_type"],
            "customer_identifier_value": vals["customer_identifier_value"],
            "listed_identifier_type": vals["listed_identifier_type"],
            "listed_identifier_value": vals["listed_identifier_value"],
            "customer_dob": vals["customer_dob"],
            "listed_dob": vals["listed_dob"],
            "customer_place_of_birth": vals["customer_place_of_birth"],
            "listed_place_of_birth": vals["listed_place_of_birth"],
            "customer_nationality": vals["customer_nationality"],
            "listed_nationality": vals["listed_nationality"],
            "account_status": status,
            "analyst_note": note,
            "verdict": verdict,
            "deciding_identifier": deciding,
        }
        out.append((rec_id, text, gold, bucket))

        stats["verdicts"][verdict] = stats["verdicts"].get(verdict, 0) + 1
        stats["deciding"][deciding] = stats["deciding"].get(deciding, 0) + 1
        stats["buckets"][bucket] += 1
        stats["closeness"][closeness] = stats["closeness"].get(closeness, 0) + 1
        if verdict != "not_a_match" and status == "live":
            stats["needs_escalation"] += 1
        if bucket == "same_strong_id_translit":
            stats["translit_decided_by_id"] += 1
        if bucket == "not_strong_conflict":
            stats["conflict_decided_by_id"] += 1
        if bucket == "insuff_partial_dob":
            stats["partial_dob"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the sheet it labels, every gold verdict and deciding
    identifier must be that sheet's own rulebook lookup, and every null must be explained in the
    text. A corpus whose labels are not readable off its own text is not a corpus, it is a second
    opinion."""
    for rec_id, text, gold, bucket in rows:
        for field in ("alert_id", "customer_name", "listed_name", "customer_nationality",
                      "listed_nationality", "account_status", "analyst_note"):
            assert gold[field] in text, "%s: %s not stated in the sheet" % (rec_id, field)

        for side, what in (("customer", "Date of Birth"), ("listed", "Date of Birth")):
            key = "%s_dob" % side
            if gold[key] is None:
                want = "not recorded" if side == "customer" else "not published"
                assert "%s: %s" % (what, want) in text, \
                    "%s: null %s not explained" % (rec_id, key)
            else:
                assert "%s: %s" % (what, gold[key]) in text, "%s: %s not stated" % (rec_id, key)

        for side in ("customer", "listed"):
            key = "%s_place_of_birth" % side
            if gold[key] is None:
                want = "not recorded" if side == "customer" else "not published"
                assert "Place of Birth: %s" % want in text, \
                    "%s: null %s not explained" % (rec_id, key)
            else:
                assert "Place of Birth: %s" % gold[key] in text, \
                    "%s: %s not stated" % (rec_id, key)

        for side in ("customer", "listed"):
            t, v = gold["%s_identifier_type" % side], gold["%s_identifier_value" % side]
            if t == "none":
                assert v is None, "%s: %s identifier value present with type none" % (rec_id, side)
                want = ("No secondary identifier on file" if side == "customer"
                        else "No identifier published for this entry")
                assert want in text, "%s: %s 'none' identifier not stated" % (rec_id, side)
            else:
                assert v is not None, "%s: %s identifier type %r with no value" % (rec_id, side, t)
                assert "%s: %s" % (IDENTIFIER_LABEL[t], v) in text, \
                    "%s: %s identifier not stated verbatim" % (rec_id, side)

        d = RB.decide(gold["customer_identifier_type"], gold["customer_identifier_value"],
                      gold["listed_identifier_type"], gold["listed_identifier_value"],
                      gold["customer_dob"], gold["listed_dob"],
                      gold["customer_place_of_birth"], gold["listed_place_of_birth"])
        assert gold["verdict"] == d["verdict"], \
            "%s: gold verdict %r disagrees with its own rulebook lookup (%r)" \
            % (rec_id, gold["verdict"], d["verdict"])
        assert gold["deciding_identifier"] == d["deciding_identifier"], \
            "%s: gold deciding identifier %r disagrees with its own lookup (%r)" \
            % (rec_id, gold["deciding_identifier"], d["deciding_identifier"])

        # ⚑ THE POINT OF THE TWO SHARPEST BUCKETS, ASSERTED HERE RATHER THAN HOPED FOR.
        if bucket == "same_strong_id_translit":
            without = RB.verdict_of("none", None, "none", None,
                                    gold["customer_dob"], gold["listed_dob"],
                                    gold["customer_place_of_birth"],
                                    gold["listed_place_of_birth"])
            assert without == "not_a_match", \
                "%s: with the shared identifier hidden this sheet must read not_a_match, not %r" \
                % (rec_id, without)
        if bucket == "not_strong_conflict":
            without = RB.verdict_of("none", None, "none", None,
                                    gold["customer_dob"], gold["listed_dob"],
                                    gold["customer_place_of_birth"],
                                    gold["listed_place_of_birth"])
            assert without == "same_party", \
                "%s: with the conflicting identifier hidden this sheet must read same_party, " \
                "not %r" % (rec_id, without)
        if bucket == "insuff_partial_dob":
            completed = RB.verdict_of(gold["customer_identifier_type"],
                                      gold["customer_identifier_value"],
                                      gold["listed_identifier_type"],
                                      gold["listed_identifier_value"],
                                      gold["customer_dob"], gold["customer_dob"],
                                      gold["customer_place_of_birth"],
                                      gold["listed_place_of_birth"])
            assert completed == "same_party", \
                "%s: completing the partial date must make this sheet read same_party, not %r" \
                % (rec_id, completed)


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
    for rec_id, text, _gold, _bucket in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold, _bucket in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _b in rows)
    print("alerts: %d   bytes: %d" % (len(rows), total))
    print("verdicts: %s" % "  ".join("%s=%d" % (k, v)
                                     for k, v in sorted(stats["verdicts"].items())))
    print("deciding: %s" % "  ".join("%s=%d" % (k, v)
                                     for k, v in sorted(stats["deciding"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("names:    %s" % "  ".join("%s=%d" % (k, v)
                                     for k, v in sorted(stats["closeness"].items())))
    print("%d (%.0f%%) carry an analyst note whose REGISTER contradicts the rulebook verdict -- "
          "measured, not dialled in: the note follows the engine's name score and the name score "
          "is decorrelated from the identifiers"
          % (stats["register_contradicts"],
             100.0 * stats["register_contradicts"] / len(rows)))
    print("%d alert(s) are the same party under a transliterated name with the nationality AND "
          "the place of birth disagreeing -- one strong identifier against several weak mismatches"
          % stats["translit_decided_by_id"])
    print("%d alert(s) are separated by a conflicting strong identifier alone, with the name, the "
          "full date of birth, the place of birth and the nationality all agreeing"
          % stats["conflict_decided_by_id"])
    print("%d alert(s) carry a PARTIAL date of birth -- a stated fact that is still not comparable"
          % stats["partial_dob"])
    print("%d alert(s) reuse one of %d common invented names with nothing comparable on the file"
          % (stats["common_name"], len(COMMON_NAMES)))
    print("%d alert(s) are not dismissible on the file AND already live -- the pure-code "
          "escalation flag" % stats["needs_escalation"])
    print("internal consistency check: PASSED (every gold value is stated in its own sheet, every "
          "verdict and deciding identifier is that sheet's own rulebook lookup, every null is "
          "explained in the text, and the three sharpest buckets each flip when their deciding "
          "identifier is removed or completed)")


if __name__ == "__main__":
    main()
