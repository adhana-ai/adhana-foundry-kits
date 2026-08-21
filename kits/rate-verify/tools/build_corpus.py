#!/usr/bin/env python3
"""Generate synthetic utility billing-account records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one account record per file) and data/gold.jsonl, byte-identical on
every run. Every account id, division name and billing-rep note here is invented -- nothing is
fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.
No real utility, real tariff filing or real published rate schedule is named or reproduced. See
data/SOURCES.md.

⚑ GOLD `rate_correct` IS A COMPARISON, NOT A LABEL SOMEBODY TYPED. It is derived from the same
four structured values the generator itself decided, with the same rule the kit publishes
everywhere else:

    correct_code(service_class, meter_type, usage_kwh, demand_kw) == applied_rate_code

It is never re-derived from the billing rep's account note, and the note never feeds the label.

⚑ THE RULE, AND WHY IT HAS A PRIORITY ORDER. A Residential account always qualifies for R-1,
whatever it uses. A commercial or industrial account on an INTERVAL meter with usage at or above
15,000 kWh qualifies for TOU-8 -- REGARDLESS of its demand reading, which is the sharpest test in
this corpus: a demand reading of 50 kW or more looks like the GS-2 threshold firing, and on an
interval-metered, high-usage account it is not -- TOU-8 outranks it. Only once TOU-8 does not
apply does demand decide between GS-1 and GS-2, at the >= 50 kW boundary, inclusive.

⚑ THE PLANTED AMBIGUITY: rate correctness is structured data, and the billing rep's own note
disagrees with it on `N_AMBIGUOUS` of records. A genuinely misrated account carries a breezy note
("Standard account, nothing unusual to flag this cycle."); an account whose applied rate is
exactly correct carries a note that reads as though something is wrong with it ("Escalated last
cycle for a possible rate misclassification -- pending manager review."). Anything that classifies
correctness off the note's TONE -- including evals/baseline.py, deliberately -- fails those
records by construction. Anything that runs the four-value comparison gets them right.
"""
import argparse
import datetime
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the same fix the sibling
# kit immediately before this one in the series (pod-conformance) had to make after its first
# generator asked for 40 pct ambiguity and delivered 51 pct. A count 1.7 standard deviations off
# its own design is not a corpus property, it is sampling noise being published as one. So each
# class here is a fixed COUNT, shuffled by the seeded RNG. The corpus is still deterministic and
# still byte-identical on every run.
N_CORRECT = 28                     # applied_rate_code matches the computed correct code
N_AMBIGUOUS = 22                   # 40 pct, exactly -- an account note from the wrong register
N_SENT = 30                        # bill_status == "sent"; the rest are still "draft"

# Invented utility service divisions. Nothing here is a real utility, a real tariff filing or a
# real published rate schedule -- names built so a reader can see at a glance that the corpus is
# a construction.
DIVISIONS = [
    "North Ridge Division",
    "Cedar Valley Division",
    "Blue Harbor Division",
    "Prairie Crossing Division",
    "Red Butte Division",
    "Silver Creek Division",
    "Falcon Mesa Division",
    "Willowbend Division",
]

SERVICE_CLASSES = ["Residential", "Small Commercial", "Large Commercial", "Industrial"]
COMMERCIAL_CLASSES = ["Small Commercial", "Large Commercial", "Industrial"]

# ⚑ THE FAULT LIBRARY. Every way an applied rate code can be wrong, and the exact number of the
# 27 mismatched records each one takes. `tou_override_missed` is the sharpest test in the corpus:
# demand_kw is >= 50 (the GS-2 threshold) but the account is also interval-metered with usage at
# or above 15,000 kWh, so the correct code is TOU-8 -- a reader (or a model) applying "demand
# decides it" alone answers GS-2 and the rule says TOU-8. Eight of them, not one, so the case is
# measured rather than anecdotal.
FAULTS = [
    ("class_swap", 6),            # a commercial code on a Residential account, or R-1 on a commercial one
    ("demand_boundary", 9),       # GS-1/GS-2 swapped across the 50 kW boundary, several exactly at it
    ("tou_override_missed", 8),   # should be TOU-8 (interval + usage >= 15000); GS-1/GS-2 applied instead
    ("tou_wrongly_applied", 4),   # TOU-8 applied when NOT interval-and-15000-plus
]

# Notes whose TONE says "this account's rate is fine". Used truthfully on a correctly-rated
# account, and against type on a misrated one -- half the planted ambiguity.
BREEZY_NOTES = [
    "Standard account, nothing unusual to flag this cycle.",
    "Rate schedule confirmed correct at last review.",
    "Routine account. No concerns from billing on this one.",
    "Usage looks normal for this account type, all in order.",
]

# Notes whose TONE says "something is wrong with this account's rate". Used truthfully on a
# misrated account, and against type on one whose applied rate is exactly correct -- the other
# half.
ANXIOUS_NOTES = [
    "Escalated last cycle for a possible rate misclassification -- pending manager review.",
    "Customer disputed their rate class; account under manual audit.",
    "Not confident this account is billed correctly -- needs a second look before it goes out.",
    "Something looked off on this account during the last rate review, revisit before closing.",
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


def correct_rate_code(service_class, meter_type, usage_kwh, demand_kw):
    """THE RULE, in one place. src/extract.py::correct_rate_code() is the same function, run over
    the MODEL's own extracted values; data/fields.json states it to the model in words. Three
    readers, one definition, so the corpus, the prompt and the guardrail cannot drift apart about
    what a correct rate code means.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED RATE STRUCTURE, NOT A REAL TARIFF. No published rate case,
    tariff filing or regulatory schedule was consulted, and none is reproduced. A real utility's
    rate eligibility depends on a filed tariff, a service agreement and often a customer election;
    this is four values and a priority order, chosen because it is the smallest rule that is
    genuinely useful and readable off one reply.
    """
    if service_class == "Residential":
        return "R-1"
    if meter_type == "interval" and usage_kwh is not None and usage_kwh >= 15000:
        return "TOU-8"
    if demand_kw is not None and demand_kw >= 50:
        return "GS-2"
    return "GS-1"


def _account_facts(rng, fault, service_class):
    """(meter_type, usage_kwh, demand_kw, applied_rate_code) for one record, from the fault mode.

    `service_class` is chosen by the caller BEFORE this runs, because `class_swap` needs to know
    what the account genuinely is in order to pick a code that disagrees with it.
    """
    commercial = service_class != "Residential"

    if fault == "class_swap":
        if commercial:
            # A genuinely commercial account, billed as though it were Residential. Usage and
            # demand are kept well under the TOU-8/GS-2 thresholds so the swap is the only fault.
            meter_type = rng.choice(["standard", "interval"])
            usage = rng.randint(2000, 12000)
            demand = rng.randint(10, 40)
            applied = "R-1"
        else:
            # A genuinely Residential account, billed as though it were commercial.
            meter_type = "standard"
            usage = rng.randint(400, 1800)
            demand = None
            applied = rng.choice(["GS-1", "GS-2"])
        return meter_type, usage, demand, applied

    if service_class == "Residential":
        # Residential is never wrong except via class_swap above, so every other fault mode
        # dealt to a Residential row is folded back to a correct one at assembly time.
        return "standard", rng.randint(300, 2200), None, "R-1"

    if fault == "demand_boundary":
        # Half the boundary faults land EXACTLY at 50 kW, on purpose -- inclusive means GS-2.
        at_boundary = rng.random() < 0.5
        meter_type = "standard"
        usage = rng.randint(3000, 12000)
        if at_boundary:
            demand = 50
            applied = "GS-1"       # wrong: exactly 50 qualifies for GS-2, GS-1 was applied
        else:
            below = rng.random() < 0.5
            if below:
                demand = rng.randint(20, 49)
                applied = "GS-2"   # wrong: under 50, GS-1 was correct
            else:
                demand = rng.randint(51, 90)
                applied = "GS-1"   # wrong: at or over 50, GS-2 was correct
        return meter_type, usage, demand, applied

    if fault == "tou_override_missed":
        # Interval-metered, high usage, AND demand >= 50 on most of these -- the account looks
        # like a textbook GS-2 case, and the rule says TOU-8 anyway because of the meter and usage.
        meter_type = "interval"
        usage = rng.randint(15000, 24000)
        if rng.random() < 0.5:
            usage = 15000           # exactly the boundary, on purpose
        demand = rng.randint(40, 90)
        applied = "GS-2" if demand >= 50 else "GS-1"
        return meter_type, usage, demand, applied

    if fault == "tou_wrongly_applied":
        # TOU-8 on an account that does not qualify -- either not interval-metered, or interval
        # but under the usage threshold.
        if rng.random() < 0.5:
            meter_type = "standard"
            usage = rng.randint(3000, 20000)
            demand = rng.randint(10, 90)
        else:
            meter_type = "interval"
            usage = rng.randint(3000, 14999)
            demand = rng.randint(10, 90)
        return meter_type, usage, demand, "TOU-8"

    raise ValueError(fault)


def _correct_facts(rng, service_class):
    """A record whose applied_rate_code is exactly the code the rule computes."""
    if service_class == "Residential":
        return "standard", rng.randint(300, 2200), None, "R-1"

    # A quarter of correct commercial records are TOU-8, a quarter sit exactly on the demand
    # boundary at 50 kW (GS-2), and the rest spread across GS-1/GS-2 away from any boundary --
    # so "correct" is not exclusively the easy interior of the rule either.
    shape = rng.choice(["tou", "boundary", "gs1", "gs2"])
    if shape == "tou":
        meter_type = "interval"
        usage = rng.choice([15000, rng.randint(15001, 26000)])
        demand = rng.randint(10, 90)
        return meter_type, usage, demand, "TOU-8"
    if shape == "boundary":
        meter_type = "standard"
        usage = rng.randint(3000, 12000)
        return meter_type, usage, 50, "GS-2"
    if shape == "gs1":
        meter_type = rng.choice(["standard", "interval"])
        usage = rng.randint(1000, 14000) if meter_type == "interval" else rng.randint(1000, 12000)
        demand = rng.randint(5, 49)
        return meter_type, usage, demand, "GS-1"
    meter_type = "standard"
    usage = rng.randint(4000, 20000)
    demand = rng.randint(51, 120)
    return meter_type, usage, demand, "GS-2"


def build_all(rng, n=N_RECORDS):
    stats = {"correct": 0, "mismatch": 0, "ambiguous": 0, "needs_review": 0,
             "faults": {name: 0 for name, _ in FAULTS}}

    n_correct = min(N_CORRECT, n)
    faults = _deal(rng, n, [(None, n_correct)] + FAULTS)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    sent = _deal(rng, n, [("sent", N_SENT), ("draft", n - N_SENT)])
    # Service class is dealt independently of the fault mode EXCEPT class_swap forces a specific
    # pairing -- see _account_facts. Every other fault requires a commercial class, so it is
    # dealt from the three commercial classes; complete records draw from all four.
    classes = []
    for i in range(n):
        f = faults[i]
        if f == "class_swap":
            classes.append(rng.choice(SERVICE_CLASSES))
        elif f in ("demand_boundary", "tou_override_missed", "tou_wrongly_applied"):
            classes.append(rng.choice(COMMERCIAL_CLASSES))
        else:
            classes.append(rng.choice(SERVICE_CLASSES))

    out = []
    for i in range(1, n + 1):
        division = rng.choice(DIVISIONS)
        account_id = "UTL-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                        rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                        rng.randint(10000, 99999))

        # ⚑ REAL DATE ARITHMETIC, NOT STRING SURGERY. A billing period is a calendar month; adding
        # months by hand off two independent draws is how "2026-13" or "2026-00" gets written.
        months_out = rng.randint(0, 17)
        year = BASE_YEAR + (BASE_MONTH - 1 + months_out) // 12
        month = (BASE_MONTH - 1 + months_out) % 12 + 1
        billing_period = "%04d-%02d" % (year, month)

        fault = faults[i - 1]
        service_class = classes[i - 1]
        if fault is None:
            meter_type, usage, demand, applied = _correct_facts(rng, service_class)
        else:
            meter_type, usage, demand, applied = _account_facts(rng, fault, service_class)

        correct_code = correct_rate_code(service_class, meter_type, usage, demand)
        is_correct = (applied == correct_code)
        stats["correct" if is_correct else "mismatch"] += 1
        if fault is not None:
            stats["faults"][fault] += 1

        status = sent[i - 1]
        if (not is_correct) and status == "sent":
            stats["needs_review"] += 1

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the structured facts normally, and contradicts them when ambiguous.
        breezy = is_correct if not ambiguous else (not is_correct)
        note = rng.choice(BREEZY_NOTES if breezy else ANXIOUS_NOTES)

        demand_line = "%d kW" % demand if demand is not None else "not metered (residential account)"

        rec_id = "UTL-%04d" % i
        lines = [
            _underline("Account"), account_id, "",
            _underline("Service Territory"), division, "",
            _underline("Service Class"), service_class, "",
            _underline("Meter Type"), meter_type, "",
            _underline("Billing Period"), billing_period, "",
            _underline("Metered Usage"), "%d kWh" % usage, "",
            _underline("Peak Demand"), demand_line, "",
            _underline("Applied Rate Code"), applied, "",
            _underline("Bill Status"), status, "",
            _underline("Account Notes"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "account_id": account_id,
            "service_class": service_class,
            "meter_type": meter_type,
            "billing_period": billing_period,
            "metered_usage_kwh": usage,
            "peak_demand_kw": demand,
            "applied_rate_code": applied,
            "bill_status": status,
            "account_notes": note,
            "rate_correct": "yes" if is_correct else "no",
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold label must be the
    comparison the document's own values produce, and peak_demand_kw must be null on every
    Residential row and stated on every other row. A corpus whose labels are not readable off its
    own text is not a corpus, it is a second opinion."""
    for rec_id, text, gold in rows:
        for field in ("account_id", "service_class", "meter_type", "billing_period",
                      "applied_rate_code", "bill_status", "account_notes"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        assert "%d kWh" % gold["metered_usage_kwh"] in text, \
            "%s: metered_usage_kwh not stated verbatim" % rec_id
        if gold["peak_demand_kw"] is None:
            assert gold["service_class"] == "Residential", \
                "%s: peak_demand_kw is null on a non-Residential row" % rec_id
            assert "not metered" in text, "%s: null demand not explained in the document" % rec_id
        else:
            assert gold["service_class"] != "Residential", \
                "%s: peak_demand_kw is stated on a Residential row" % rec_id
            assert "%d kW" % gold["peak_demand_kw"] in text, \
                "%s: peak_demand_kw not stated verbatim" % rec_id

        want = correct_rate_code(gold["service_class"], gold["meter_type"],
                                 gold["metered_usage_kwh"], gold["peak_demand_kw"])
        assert gold["rate_correct"] == ("yes" if want == gold["applied_rate_code"] else "no"), \
            "%s: gold label disagrees with its own values (rule says %s, applied %s)" \
            % (rec_id, want, gold["applied_rate_code"])

        y, m = (int(x) for x in gold["billing_period"].split("-"))
        assert 1 <= m <= 12, "%s: billing_period month out of range" % rec_id


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
    print("records: %d   correct: %d   mismatch: %d   bytes: %d"
          % (len(rows), stats["correct"], stats["mismatch"], total))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("%d (%.0f%%) carry an account note whose TONE contradicts the structured facts"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) are misrated AND already sent -- the pure-code review flag" % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own comparison, peak_demand_kw is null iff Residential)")


if __name__ == "__main__":
    main()
