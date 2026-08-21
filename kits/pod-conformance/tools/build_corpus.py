#!/usr/bin/env python3
"""Generate synthetic proof-of-delivery records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one POD record per file) and data/gold.jsonl, byte-identical on every
run. Every shipment number, carrier name, receiving site and driver note here is invented --
nothing is fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT
licence. No real carrier, real consignee or real published logistics standard is named or
reproduced. See data/SOURCES.md.

⚑ GOLD `delivery_complete` IS A COMPARISON, NOT A LABEL SOMEBODY TYPED. It is derived from the two
quantities and the condition code this generator itself decided, with the same strict rule the kit
publishes everywhere else:

    complete  <=>  delivered_quantity == ordered_quantity  AND  condition_code == "undamaged"

It is never re-derived from the driver's exception note, and the note never feeds the label.

⚑ EQUALITY IS EXACT, IN BOTH DIRECTIONS. A short delivery is not complete, and neither is a
surplus one: a pallet more than the order says is still an order that did not arrive as booked,
and it is the case a `>=` reading of the rule silently passes. This corpus plants a handful of
over-deliveries on purpose so that a model reading "at least what was ordered" scores worse than
one doing the comparison the prompt actually states.

⚑ THE PLANTED AMBIGUITY: completeness is structured data, and the driver's own prose disagrees
with it on `AMBIGUOUS_FRACTION` of records. A genuinely short or damaged delivery carries a
breezy note ("All good on my end. Left with the receiving clerk, no issues to report."); a
delivery whose counts match exactly and whose condition code reads `undamaged` carries an anxious
one ("Sorry for the mix-up, had to leave it at the gate because the dock was full."). Anything
that classifies completeness off the note's TONE -- including evals/baseline.py, deliberately --
fails those records by construction. Anything that compares the two numbers and reads the code
gets them right.
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

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD. The sibling kits in this
# series draw each record's class from an independent coin, which is fine at 500 records and is
# not fine at 55: the first version of this generator asked for 40 pct ambiguity and delivered 51
# pct, and asked for a share of over-deliveries and delivered ONE -- too few for the strictest
# case in the corpus to test anything. A count that is 1.7 standard deviations off its own design
# is not a corpus property, it is sampling noise being published as one.
#
# So each class is a fixed COUNT, shuffled by the seeded RNG. The corpus is still deterministic
# and still byte-identical on every run; what changes is that the numbers on the page are the
# numbers the design asked for, and the paragraph describing the corpus does not have to explain
# a gap between them.
N_COMPLETE = 28                    # exact equality on the counts AND an undamaged condition code
N_AMBIGUOUS = 22                   # 40 pct, exactly -- a driver note from the wrong register
N_NO_SIGNATURE = 18                # no recipient signature captured at the drop

# Invented carriers. Nothing here is a real haulier, a real freight brand or a real delivery
# network -- names built so a reader can see at a glance that the corpus is a construction.
CARRIERS = [
    "Northvale Freight Lines",
    "Calderon Cartage Group",
    "Brightpath Haulage",
    "Stonebridge Transport Co.",
    "Kestrel Freightways",
    "Havenport Delivery Network",
    "Ironline Carriage",
    "Larkspur Distribution",
    "Verrow Freight Services",
    "Ambermoor Logistics",
]

# Invented receiving sites. This section is deliberately NOT one of the ten extracted fields --
# it is the piece of the record src/select.py never sends, and it is here so that the saving that
# module claims is something a reader can see on the page rather than take on trust.
SITES = [
    "Depot 12, Marlow Industrial Estate",
    "Warehouse 4, Pelham Trade Park",
    "Cross-dock 7, Sandhurst Way",
    "Regional Hub 2, Calverton Road",
    "Store Yard 19, Ashcombe Lane",
    "Distribution Centre 5, Oakfield Rise",
]

# ⚑ THE FAULT LIBRARY. Every way a delivery can fail the published rule, and the exact number of
# the 27 non-complete records each one takes. `over` is the sharpest test in the corpus: the
# counts differ but the shipment is not SHORT, so a reader (or a model) applying "did at least
# the ordered quantity arrive" answers yes and the rule says no. Three of them, not one, so the
# case is measured rather than anecdotal.
FAULTS = [
    ("short", 11),            # fewer units scanned than ordered
    ("damaged", 7),           # counts match, condition code says damaged
    ("unknown", 4),           # counts match, condition could not be assessed at the drop
    ("over", 3),              # MORE units scanned than ordered -- still not what was booked
    ("short_damaged", 2),     # both at once
]

# Notes whose TONE says "this delivery went fine". Used truthfully on a complete delivery, and
# against type on one that is short, damaged or unassessed -- half the planted ambiguity.
BREEZY_NOTES = [
    "All good on my end. Left with the receiving clerk, no issues to report.",
    "Straightforward drop. Dock crew were quick, nothing worth flagging.",
    "Fine delivery, minor scuff on one of the outer boxes but nothing to worry about.",
    "Easy stop, everything handed over at the bay. No concerns from me.",
]

# Notes whose TONE says "this delivery was a problem". Used truthfully on a delivery that really
# is incomplete, and against type on one whose counts match exactly and whose condition code
# reads undamaged -- the other half.
ANXIOUS_NOTES = [
    "Sorry for the mix-up, had to leave it at the gate because the dock was full.",
    "Not happy with how this one went. Site was chaotic and I was rushed through the drop.",
    "Apologies, ran late and the receiving office had already closed when I arrived.",
    "Bit of a mess at the bay. Flagging it so someone takes a look at this stop.",
]

BASE_DATE = datetime.date(2026, 2, 2)

# The delivery window a scan timestamp is allowed to fall in. Narrow on purpose: an ISO timestamp
# is only worth extracting if it is a plausible one, and 03:00 on a retail dock is not.
WINDOW_START_MIN = 6 * 60          # 06:00
WINDOW_END_MIN = 19 * 60 + 59      # 19:59


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


def _complete(delivered, ordered, condition):
    """THE RULE, in one place. Exact equality on the counts AND an undamaged condition code.

    src/extract.py::is_complete() is the same three lines, run over the MODEL's own extracted
    values; src/prompt.py states it to the model in words. Three readers, one definition, so the
    corpus, the prompt and the guardrail cannot drift apart about what "complete" means.
    """
    return delivered == ordered and condition == "undamaged"


def _quantities(rng, fault):
    """(ordered, delivered, condition_code) for one record, from the fault mode."""
    ordered = rng.choice([24, 36, 48, 60, 72, 96, 120, 144, 180, 240, 300, 360, 480])
    if fault is None:
        return ordered, ordered, "undamaged"
    if fault == "damaged":
        return ordered, ordered, "damaged"
    if fault == "unknown":
        return ordered, ordered, "unknown"
    # A shortfall is small on purpose -- one or two cartons off a pallet, the kind of gap a
    # breezy note genuinely covers up. A surplus is smaller still.
    if fault == "over":
        return ordered, ordered + rng.randint(1, 4), "undamaged"
    short = max(1, int(round(ordered * rng.uniform(0.01, 0.09))))
    condition = "damaged" if fault == "short_damaged" else "undamaged"
    return ordered, ordered - short, condition


def build_all(rng, n=N_RECORDS):
    stats = {"complete": 0, "incomplete": 0, "ambiguous": 0, "needs_review": 0,
             "faults": {name: 0 for name, _ in FAULTS}}

    # The three exact compositions, dealt up front and consumed one per record. `faults` carries
    # None for a complete delivery, so completeness and the fault mode are one deal rather than
    # two that could disagree about how many records are complete.
    n_complete = min(N_COMPLETE, n)
    faults = _deal(rng, n, [(None, n_complete)] + FAULTS)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])
    signatures = _deal(rng, n, [("no", N_NO_SIGNATURE), ("yes", n - N_NO_SIGNATURE)])

    out = []
    for i in range(1, n + 1):
        carrier = rng.choice(CARRIERS)
        site = rng.choice(SITES)
        shipment_id = "SHP-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                         rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                         rng.randint(10000, 99999))

        # ⚑ REAL DATE ARITHMETIC, NOT STRING SURGERY. timedelta gets month lengths right;
        # building "2026-%02d-%02d" from two independent draws produces 31 February.
        delivery_date = BASE_DATE + datetime.timedelta(days=rng.randint(0, 200))
        minute = rng.randint(WINDOW_START_MIN, WINDOW_END_MIN)
        # ⚑ THE SCAN HAPPENS ON THE DELIVERY DATE, AND THAT INVARIANT IS ASSERTED IN _verify().
        # datetime.combine is the only construction here; nothing formats a date by hand.
        pod_ts = datetime.datetime.combine(
            delivery_date, datetime.time(hour=minute // 60, minute=minute % 60,
                                         second=rng.randrange(0, 60)))

        fault = faults[i - 1]
        if fault:
            stats["faults"][fault] += 1
        ordered, delivered, condition = _quantities(rng, fault)

        # Recomputed from the values the document actually states -- the only values a reader or
        # a model ever sees -- so gold can never disagree with its own document.
        complete = _complete(delivered, ordered, condition)
        stats["complete" if complete else "incomplete"] += 1

        signature = signatures[i - 1]
        if (not complete) and signature == "no":
            stats["needs_review"] += 1

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the structured facts normally, and contradicts them when ambiguous.
        breezy = complete if not ambiguous else (not complete)
        note = rng.choice(BREEZY_NOTES if breezy else ANXIOUS_NOTES)

        rec_id = "POD-%04d" % i
        lines = [
            _underline("Shipment"), shipment_id, "",
            _underline("Carrier"), carrier, "",
            _underline("Receiving Site"), site, "",
            _underline("Delivery Date"), delivery_date.isoformat(), "",
            _underline("POD Timestamp"), pod_ts.isoformat(), "",
            _underline("Ordered Quantity"), "%d units" % ordered, "",
            _underline("Delivered Quantity"), "%d units" % delivered, "",
            _underline("Condition Code"), condition, "",
            _underline("Recipient Signature On File"), signature, "",
            _underline("Driver Exception Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "shipment_id": shipment_id,
            "carrier_name": carrier,
            "delivery_date": delivery_date.isoformat(),
            "ordered_quantity": ordered,
            "delivered_quantity": delivered,
            "condition_code": condition,
            "recipient_signature_present": signature,
            "driver_exception_note": note,
            "pod_timestamp": pod_ts.isoformat(),
            "delivery_complete": "yes" if complete else "no",
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, every gold label must be the
    comparison the document's own values produce, and every timestamp must sit on the delivery
    date it claims. A corpus whose labels are not readable off its own text is not a corpus, it
    is a second opinion."""
    for rec_id, text, gold in rows:
        for field in ("shipment_id", "carrier_name", "delivery_date", "condition_code",
                      "recipient_signature_present", "driver_exception_note", "pod_timestamp"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        for field in ("ordered_quantity", "delivered_quantity"):
            assert "%d units" % gold[field] in text, \
                "%s: %s=%r not stated verbatim in the document" % (rec_id, field, gold[field])
        assert gold["delivery_complete"] == (
            "yes" if _complete(gold["delivered_quantity"], gold["ordered_quantity"],
                               gold["condition_code"]) else "no"), \
            "%s: gold label disagrees with its own quantities and condition code" % rec_id

        # ⚠︎ THE ORDERING INVARIANT, ASSERTED RATHER THAN ASSUMED. Both values are parsed back
        # out of the strings the document carries, so this checks the text and not the variables
        # that wrote it: a formatting bug that lost the date would survive any check that read
        # the generator's own objects instead.
        d = datetime.date.fromisoformat(gold["delivery_date"])
        ts = datetime.datetime.fromisoformat(gold["pod_timestamp"])
        assert ts.date() == d, "%s: pod_timestamp is not on the delivery date" % rec_id
        mins = ts.hour * 60 + ts.minute
        assert WINDOW_START_MIN <= mins <= WINDOW_END_MIN, \
            "%s: pod_timestamp %s is outside the delivery window" % (rec_id, ts.isoformat())


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
    print("records: %d   complete: %d   incomplete: %d   bytes: %d"
          % (len(rows), stats["complete"], stats["incomplete"], total))
    print("faults: %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["faults"].items()))
    print("%d (%.0f%%) carry a driver note whose TONE contradicts the structured facts"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d record(s) are incomplete AND unsigned -- the pure-code review flag" % stats["needs_review"])
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own comparison, every scan timestamp sits on its own "
          "delivery date inside the delivery window)")


if __name__ == "__main__":
    main()
