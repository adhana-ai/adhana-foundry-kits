#!/usr/bin/env python3
"""Generate synthetic usage-to-invoice reconciliation records and their gold labels, from a
fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one invoice line and its mediated-usage summary per file) and
data/gold.jsonl, byte-identical on every run. Every line id, rating domain and analyst note here
is invented -- nothing is fetched and nothing is licensed from anybody, so the corpus ships under
this repo's MIT licence. No real carrier, real mediation platform, real tariff or real customer is
named or reproduced. See data/SOURCES.md.

⚑ GOLD `variance_cause` IS ARITHMETIC, NOT A LABEL SOMEBODY TYPED. It is derived from the same
structured quantities the generator itself decided, with the same two functions the kit publishes
everywhere else:

    expected_invoiced(service_type, mediated, prior_period, confirmed_duplicates)
    classify(... , invoiced, unrated, ...)

It is never re-derived from the analyst's own note, and the note never feeds the label.

⚑ THE ARITHMETIC. The mediated total for a line and period is four DISJOINT parts:

    mediated = rated + unrated + prior_period + confirmed_duplicates

  rated                 correctly rated, billable this period
  unrated               failed rating and sat in suspense -- STILL billable this period
  prior_period          arrived after cutoff and belongs to the PREVIOUS period -- not billable here
  confirmed_duplicates  the same session counted twice, confirmed by review -- never billable

So the quantity that should have reached this invoice is

    billable = mediated - prior_period - confirmed_duplicates          (note: unrated STAYS in)
    expected = round_up(billable, increment(service_type))

and the whole decision is `invoiced - expected`, classified in a PRIORITY ORDER.

⚑ THE ROUNDING INCREMENT IS A PROPERTY OF THE SERVICE, AND IT IS THE FIRST TEST. Voice is billed
in whole minutes (60-second increments), data in whole megabytes (1024 KB), and SMS per message,
which means SMS HAS NO ROUNDING TOLERANCE AT ALL: a one-message gap on an SMS line is a real
variance, and the same one-unit gap on a voice line is not. A reader (or a model) that applies one
tolerance to all three services gets the SMS lines wrong in one direction and the voice lines wrong
in the other.

⚑ THE PRIORITY ORDER, and why each step is before the one under it:

  1. gap == 0                              -> none
  2. abs(gap) < increment                  -> rounding      CHECKED BEFORE ANY CAUSE IS NAMED,
                                                            because a sub-increment gap is
                                                            indistinguishable from a small missed
                                                            block and calling it a cause is a
                                                            guess dressed as a finding
  3. gap < 0 and it matches `unrated`      -> unrated_usage
  4. gap > 0 and it matches `confirmed_duplicates` -> duplicate_records
  5. gap > 0 and it matches `prior_period` -> late_records
  6. otherwise                             -> unexplained

⚑ THE THREE PLANTED TRAPS, all of them cases where the loud number on the page is the wrong one:

  A. PRIOR-PERIOD USAGE THAT IS CORRECTLY EXCLUDED. A line states a large late-arriving figure and
     the invoice is exactly right, because those records belong to the previous period. The answer
     is `none`. Anything that reads "late CDRs present" as "variance" fails these.
  B. DUPLICATE SUSPECTS THAT ARE NOT DUPLICATES. Every record states BOTH the raw suspect figure
     the de-duplication pass flagged AND the figure review actually confirmed. Only the confirmed
     figure is in the arithmetic; the suspects are two genuinely distinct sessions that happened to
     look alike. Anything that subtracts the suspect figure gets a gap that is not there.
  C. UNRATED USAGE THAT WAS ALREADY RE-RATED AND BILLED. `unrated` stays INSIDE billable, so a line
     with a heavy suspense bucket and a correct invoice is `none`. Anything that treats a non-zero
     suspense figure as automatically a shortfall fails these.

⚑ AND THE ANALYST NOTE IS A FOURTH DECOY, in a different dimension: on `N_AMBIGUOUS` of records it
NAMES A CAUSE THAT THE ARITHMETIC DOES NOT SUPPORT. evals/baseline.py reads exactly that note and
nothing else, deliberately, and fails those records by construction.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 55

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the same discipline the
# two sibling kits before this one in the series settled on, after one of them asked for 40 pct
# ambiguity and delivered 51 pct. A count 1.7 standard deviations off its own design is not a
# corpus property, it is sampling noise being published as one. So each class here is a fixed
# COUNT, shuffled by the seeded RNG. The corpus is still deterministic and byte-identical.
CAUSE_MIX = [
    ("none", 16),                 # the invoice is right, whatever else the line is carrying
    ("rounding", 8),              # a sub-increment gap; explained, and never an SMS line
    ("unrated_usage", 11),        # the invoice missed the suspense bucket -- under-billed
    ("duplicate_records", 8),     # the invoice billed confirmed duplicates -- over-billed
    ("late_records", 8),          # the invoice billed the previous period's late arrivals
    ("unexplained", 4),           # a real gap that ties back to none of the three blocks
]
N_AMBIGUOUS = 22                  # 40 pct, exactly -- an analyst note naming the wrong cause
N_ISSUED = 30                     # invoice_status == "issued"; the rest are still "draft"

# Exact service mix, then repaired so no `rounding` record lands on SMS (see build_all).
SERVICE_MIX = [("voice", 21), ("data", 21), ("sms", 13)]

# Invented rating domains -- the mediation platform's own partition tag. NO FIELD MAPS TO THIS
# SECTION, which is why it is here: it is the one part of every record a reader can point at and
# say "selection dropped that, and it was never sent".
RATING_DOMAINS = [
    "MED-NORTHFIELD-01", "MED-NORTHFIELD-02", "MED-CALDERA-03", "MED-CALDERA-04",
    "MED-BRIGHTWATER-01", "MED-BRIGHTWATER-05", "MED-TANNERY-02", "MED-TANNERY-07",
]

UNITS = {"voice": "seconds", "data": "KB", "sms": "messages"}

BASE_YEAR, BASE_MONTH = 2026, 1

# ⚠︎ EACH NOTE REGISTER NAMES ONE CAUSE, AND NO TEMPLATE MAY CARRY ANOTHER REGISTER'S KEYWORD.
# evals/check_labels.py asserts exactly that against evals/baseline.py's own keyword table, before
# any run is allowed to spend -- written in from the start rather than after a defect was found
# live, on the lesson a sibling kit in this series paid for (a keyword that fired on a negation
# inside a note that said the opposite, mis-registering four records for days).
NOTES = {
    "none": [
        "Line reconciled cleanly against mediation last cycle; nothing outstanding here.",
        "Routine line. Mediation and billing agreed at the last review.",
        "No open items on this line from the revenue assurance side.",
        "Checked at cycle open and again at close; this one is in order.",
    ],
    "rounding": [
        "Tiny gap on this line -- almost certainly just the billing increment.",
        "Difference here is smaller than one billing increment, so it is a rounding artefact.",
    ],
    "unrated_usage": [
        "Suspense bucket looked heavy this cycle; unrated usage is probably missing from the bill.",
        "Rating errors on this line -- expect unrated traffic that never made it onto the invoice.",
        "Some usage failed rating and I do not think it was picked back up before invoicing.",
    ],
    "duplicate_records": [
        "Duplicate session records on this line; it looks double-charged to me.",
        "De-dup flagged this one -- I think duplicate usage was billed twice.",
        "Suspect the same sessions have been counted twice and charged for.",
    ],
    "late_records": [
        "Traffic landed after the collection cutoff; I think last month's usage slipped onto this bill.",
        "Records arriving past cutoff on this line -- prior-period usage may have been billed here.",
    ],
    "unexplained": [
        "Gap on this line does not tie back to anything I can see in mediation.",
        "Cannot account for the difference here from the figures on the record.",
    ],
}


def increment(service_type):
    """THE BILLING INCREMENT, in the same unit the quantities are stated in. One place.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED INCREMENT TABLE, NOT A REAL CARRIER'S RATING CONFIGURATION.
    Whole-minute voice rounding and whole-megabyte data rounding are ordinary telecoms practice;
    the exact values here were chosen for this corpus and no published tariff or interconnect
    agreement was consulted.

    Returns None for a service this kit does not recognise -- an unknown is not a default.
    """
    return {"voice": 60, "data": 1024, "sms": 1}.get(service_type)


def round_up(x, inc):
    """Integer ceiling to the next whole increment. `-(-x // inc)` rather than math.ceil on a
    float, because a float division of two large integers is exactly where a boundary case at
    15,360 KB silently becomes 15,359."""
    return -(-x // inc) * inc


def expected_invoiced(service_type, mediated, prior_period, confirmed_duplicates):
    """What SHOULD have been on the invoice line. src/extract.py::expected_invoiced() is the same
    function, run over the MODEL's own extracted values; data/fields.json states it to the model in
    words. Three readers, one definition, so the corpus, the prompt and the guardrail cannot drift
    apart about what a correct invoice quantity means.

    ⚠︎ `unrated` IS NOT SUBTRACTED. Usage that failed rating is still this period's usage and is
    still owed; the invoice being short of it is the variance, not a reason to lower the target.
    """
    inc = increment(service_type)
    if inc is None:
        return None
    return round_up(mediated - prior_period - confirmed_duplicates, inc)


def classify(service_type, mediated, invoiced, unrated, prior_period, confirmed_duplicates):
    """THE RULE, in one place, with its priority order. Returns one of the six causes."""
    inc = increment(service_type)
    exp = expected_invoiced(service_type, mediated, prior_period, confirmed_duplicates)
    if inc is None or exp is None:
        return None
    gap = invoiced - exp
    if gap == 0:
        return "none"
    if abs(gap) < inc:
        return "rounding"
    if gap < 0 and unrated > 0 and abs(-gap - unrated) < inc:
        return "unrated_usage"
    if gap > 0 and confirmed_duplicates > 0 and abs(gap - confirmed_duplicates) < inc:
        return "duplicate_records"
    if gap > 0 and prior_period > 0 and abs(gap - prior_period) < inc:
        return "late_records"
    return "unexplained"


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


def _scale(service_type, rng):
    """A plausible rated volume for one line and period, in this service's own unit."""
    if service_type == "voice":
        return rng.randrange(120, 1400) * 600          # 72,000 - 840,000 seconds
    if service_type == "data":
        return rng.randrange(200, 3000) * 1024         # 204,800 - 3,072,000 KB
    return rng.randrange(400, 9000)                    # 400 - 9,000 messages


def _block(rng, inc, lo_mult, hi_mult):
    """A quantity block sized in increments, so it is never accidentally sub-increment."""
    return rng.randint(lo_mult, hi_mult) * inc + (rng.randint(0, inc - 1) if inc > 1 else 0)


def _facts(rng, cause, service_type):
    """(mediated, invoiced, unrated, prior_period, suspects, confirmed) for one record.

    Every block is built in units of the service's own increment so that a block meant to be
    VISIBLE (a real cause) can never come out smaller than the rounding tolerance and be classified
    as rounding instead -- the one way this generator could silently disagree with its own labels.
    """
    inc = increment(service_type)
    rated = _scale(service_type, rng)

    # ⚑ THE THREE BLOCKS ARE DEALT INDEPENDENTLY OF THE CAUSE. That is what makes traps A and C
    # real: a `none` record can carry a heavy suspense bucket AND a heavy late-arrival figure and
    # still be exactly right. Only the block the cause NEEDS is forced non-zero.
    unrated = _block(rng, inc, 3, 40) if rng.random() < 0.45 else 0
    prior = _block(rng, inc, 3, 30) if rng.random() < 0.60 else 0
    confirmed = _block(rng, inc, 3, 25) if rng.random() < 0.35 else 0

    if cause == "unrated_usage" and unrated == 0:
        unrated = _block(rng, inc, 4, 40)
    if cause == "duplicate_records" and confirmed == 0:
        confirmed = _block(rng, inc, 4, 25)
    if cause == "late_records" and prior == 0:
        prior = _block(rng, inc, 4, 30)

    # ⚠︎ TWO BLOCKS THAT ARE NEARLY THE SAME SIZE MAKE THE RULE AMBIGUOUS. A gap of +D and a gap of
    # +P are told apart only by which block it matches, so if D and P are within an increment of
    # each other the same gap satisfies both branches and the label is a coin toss. Separated here,
    # and asserted in _verify() and again in evals/check_labels.py.
    while confirmed and prior and abs(confirmed - prior) < 3 * inc:
        prior += 3 * inc

    mediated = rated + unrated + prior + confirmed
    billable = mediated - prior - confirmed
    exp = round_up(billable, inc)

    if cause == "none":
        invoiced = exp
    elif cause == "rounding":
        # A sub-increment gap in either direction. Impossible on SMS, where inc == 1 -- the caller
        # guarantees no `rounding` record is ever dealt an SMS line.
        delta = rng.randint(1, inc - 1)
        invoiced = exp + delta if rng.random() < 0.5 else exp - delta
    elif cause == "unrated_usage":
        # The invoice billed only what rated cleanly; the suspense bucket never reached it.
        invoiced = round_up(billable - unrated, inc)
    elif cause == "duplicate_records":
        # The confirmed duplicates were billed as though they were real sessions.
        invoiced = round_up(billable + confirmed, inc)
    elif cause == "late_records":
        # The previous period's late arrivals were billed on this invoice.
        invoiced = round_up(billable + prior, inc)
    elif cause == "unexplained":
        # A gap of at least one increment that matches none of the three blocks. Built by search
        # rather than by assertion: pick, classify, and keep only what the rule itself calls
        # unexplained.
        for _ in range(200):
            mult = rng.choice([-1, 1])
            size = _block(rng, inc, 2, 20)
            candidate = exp + mult * size
            if candidate <= 0:
                continue
            if classify(service_type, mediated, candidate, unrated, prior, confirmed) == "unexplained":
                invoiced = candidate
                break
        else:                                          # pragma: no cover -- never reached on SEED
            raise RuntimeError("could not build an unexplained gap for %s" % service_type)
    else:
        raise ValueError(cause)

    # ⚑ THE SUSPECT FIGURE IS ALWAYS >= THE CONFIRMED FIGURE, AND USUALLY STRICTLY GREATER. The
    # excess is trap B: sessions the de-duplication pass flagged and review then cleared, because
    # they were two genuinely distinct calls that looked alike. It is stated on the record, it is
    # the larger and louder of the two numbers, and it is NOT in the arithmetic.
    extra = _block(rng, inc, 2, 20) if rng.random() < 0.75 else 0
    suspects = confirmed + extra

    return mediated, invoiced, unrated, prior, suspects, confirmed


def build_all(rng, n=N_RECORDS):
    causes = _deal(rng, n, CAUSE_MIX)
    services = _deal(rng, n, SERVICE_MIX)
    issued = _deal(rng, n, [("issued", N_ISSUED), ("draft", n - N_ISSUED)])
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])

    # ⚑ THE REPAIR PASS, AND WHY IT IS A SWAP RATHER THAN A REDRAW. `rounding` cannot exist on an
    # SMS line: the increment is one message, so there is no sub-increment gap to have. Redrawing
    # the service for those records would move the service totals off their exact counts, which is
    # the whole thing the exact-then-shuffle discipline exists to protect. A SWAP moves the SMS
    # line to a record that can carry it and leaves every total untouched.
    for i in range(n):
        if causes[i] == "rounding" and services[i] == "sms":
            for j in range(n):
                if causes[j] != "rounding" and services[j] != "sms":
                    services[i], services[j] = services[j], services[i]
                    break
            else:                                      # pragma: no cover -- never reached on SEED
                raise RuntimeError("no non-SMS record available to swap a rounding line onto")

    stats = {"causes": {c: 0 for c, _ in CAUSE_MIX}, "services": {s: 0 for s, _ in SERVICE_MIX},
             "ambiguous": 0, "needs_credit": 0, "prior_present": 0, "prior_present_and_none": 0,
             "suspects_over_confirmed": 0, "suspects_with_no_confirmed": 0,
             "unrated_present_and_none": 0}

    out = []
    for i in range(1, n + 1):
        cause = causes[i - 1]
        service = services[i - 1]
        status = issued[i - 1]

        line_id = "TL-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                    rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                    rng.randint(10000, 99999))
        domain = rng.choice(RATING_DOMAINS)

        # ⚑ REAL DATE ARITHMETIC, NOT STRING SURGERY. A billing period is a calendar month; adding
        # months by hand off two independent draws is how "2026-13" or "2026-00" gets written.
        months_out = rng.randint(0, 17)
        year = BASE_YEAR + (BASE_MONTH - 1 + months_out) // 12
        month = (BASE_MONTH - 1 + months_out) % 12 + 1
        billing_period = "%04d-%02d" % (year, month)

        mediated, invoiced, unrated, prior, suspects, confirmed = _facts(rng, cause, service)
        # The label is re-derived here by the published rule rather than trusted from the branch
        # that built the record -- the generator grades itself with the same function everything
        # else grades with.
        actual = classify(service, mediated, invoiced, unrated, prior, confirmed)

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            others = [c for c in NOTES if c != actual]
            note_register = rng.choice(others)
        else:
            note_register = actual
        note = rng.choice(NOTES[note_register])

        stats["causes"][actual] += 1
        stats["services"][service] += 1
        if ambiguous:
            stats["ambiguous"] += 1
        if actual in ("duplicate_records", "late_records") and status == "issued":
            stats["needs_credit"] += 1
        if prior > 0:
            stats["prior_present"] += 1
            if actual == "none":
                stats["prior_present_and_none"] += 1
        if suspects > confirmed:
            stats["suspects_over_confirmed"] += 1
            if confirmed == 0:
                stats["suspects_with_no_confirmed"] += 1
        if unrated > 0 and actual == "none":
            stats["unrated_present_and_none"] += 1

        unit = UNITS[service]
        rec_id = "TLV-%04d" % i
        lines = [
            _underline("Invoice Line"), line_id, "",
            _underline("Rating Domain"), domain, "",
            _underline("Service Type"), service, "",
            _underline("Billing Period"), billing_period, "",
            _underline("Mediated Usage"), "%d %s" % (mediated, unit), "",
            _underline("Invoiced Quantity"), "%d %s" % (invoiced, unit), "",
            _underline("Unrated Usage"), "%d %s" % (unrated, unit), "",
            _underline("Prior Period Usage"), "%d %s" % (prior, unit), "",
            _underline("Duplicate Suspects"), "%d %s" % (suspects, unit), "",
            _underline("Confirmed Duplicates"), "%d %s" % (confirmed, unit), "",
            _underline("Invoice Status"), status, "",
            _underline("Analyst Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "line_ref": rec_id,
            "line_id": line_id,
            "service_type": service,
            "billing_period": billing_period,
            "mediated_quantity": mediated,
            "invoiced_quantity": invoiced,
            "unrated_quantity": unrated,
            "prior_period_quantity": prior,
            "confirmed_duplicate_quantity": confirmed,
            "invoice_status": status,
            "analyst_note": note,
            "variance_cause": actual,
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold label must be the
    classification the document's own values produce, and no record may be ambiguous between two
    causes. A corpus whose labels are not readable off its own text is not a corpus, it is a second
    opinion."""
    for rec_id, text, gold in rows:
        for field in ("line_id", "service_type", "billing_period", "invoice_status",
                      "analyst_note"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        unit = UNITS[gold["service_type"]]
        for field in ("mediated_quantity", "invoiced_quantity", "unrated_quantity",
                      "prior_period_quantity", "confirmed_duplicate_quantity"):
            assert "%d %s" % (gold[field], unit) in text, \
                "%s: %s not stated verbatim" % (rec_id, field)
            assert gold[field] >= 0, "%s: %s is negative" % (rec_id, field)

        want = classify(gold["service_type"], gold["mediated_quantity"], gold["invoiced_quantity"],
                        gold["unrated_quantity"], gold["prior_period_quantity"],
                        gold["confirmed_duplicate_quantity"])
        assert gold["variance_cause"] == want, \
            "%s: gold label %r disagrees with its own values (rule says %r)" \
            % (rec_id, gold["variance_cause"], want)

        inc = increment(gold["service_type"])
        assert not (gold["service_type"] == "sms" and gold["variance_cause"] == "rounding"), \
            "%s: an SMS line cannot have a rounding variance -- the increment is one message" % rec_id

        # No record may satisfy two cause branches at once.
        d, p = gold["confirmed_duplicate_quantity"], gold["prior_period_quantity"]
        if d and p:
            assert abs(d - p) >= inc, \
                "%s: confirmed duplicates (%d) and prior-period usage (%d) are within one " \
                "increment of each other -- the same gap would match both branches" % (rec_id, d, p)

        assert gold["mediated_quantity"] >= (gold["unrated_quantity"] + p + d), \
            "%s: the three blocks do not fit inside the mediated total" % rec_id

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
    print("records: %d   bytes: %d" % (len(rows), total))
    print("causes:   %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["causes"].items()))
    print("services: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["services"].items()))
    print("%d (%.0f%%) carry an analyst note naming a cause the arithmetic does not support"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) over-bill the customer AND the invoice is already issued -- the credit flag"
          % stats["needs_credit"])
    print("trap A: %d record(s) state prior-period usage; %d of them are correctly invoiced anyway"
          % (stats["prior_present"], stats["prior_present_and_none"]))
    print("trap B: %d record(s) flag more duplicate suspects than review confirmed; %d confirmed none"
          % (stats["suspects_over_confirmed"], stats["suspects_with_no_confirmed"]))
    print("trap C: %d record(s) carry unrated usage and are still correctly invoiced"
          % stats["unrated_present_and_none"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own arithmetic, no record matches two causes)")


if __name__ == "__main__":
    main()
