#!/usr/bin/env python3
"""Generate synthetic certificate-of-analysis records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one certificate per file) and data/gold.jsonl, byte-identical on every
run. Every batch number, product name, analyst and disposition note here is invented -- nothing is
fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.
No real specification, monograph, standard or company is named or reproduced. See data/SOURCES.md.

⚑ GOLD `conforms_to_spec` IS A NUMERIC RECOMPUTATION, NOT A LABEL SOMEBODY TYPED. It is derived
from the measured value and the spec bounds this generator itself decided, with the same
boundary-inclusive rule the kit publishes:

    conforming  <=>  (lower is None or measured >= lower) and (upper is None or measured <= upper)

It is never re-derived from the analyst's disposition note, and the note never feeds the label.

⚑ THE PLANTED AMBIGUITY: conformance is arithmetic, and this corpus is built so that the analyst's
own prose disagrees with the arithmetic on `AMBIGUOUS_FRACTION` of records. A batch that is a hair
outside its stated limits carries a reassuring note ("within normal range for this product line,
released"); a batch sitting cleanly inside its limits carries a hedging one ("borderline,
recommend re-test"). Anything that classifies conformance off the note's TONE -- including
evals/baseline.py, deliberately -- fails those records by construction. Anything that does the
comparison itself gets them right.

⚑ VALUES ARE NEVER GENERATED EXACTLY ON A BOUND. The published rule is boundary-INCLUSIVE, and a
corpus that tests the boundary would be testing the convention rather than the arithmetic. Every
measured value here is strictly inside or strictly outside its limits, so the gold label does not
depend on which side of the convention a reader lands.
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

AMBIGUOUS_FRACTION = 0.40
CONFORMING_FRACTION = 0.55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]

# Invented product names. Nothing here is a real brand, a real grade designation or a real
# manufacturer -- generic consumer-goods and industrial raw materials, named so a reader can see
# at a glance that the corpus is a construction.
PRODUCTS = [
    "Aurelin Grade Maize Starch",
    "Corvane Food-Grade Citric Acid",
    "Meltwood Refined Palm Olein",
    "Pellovan Industrial Calcium Carbonate",
    "Halvette Whey Protein Concentrate",
    "Kestrelin Xanthan Gum",
    "Orlash Dextrose Monohydrate",
    "Brindle Alkalised Cocoa Powder",
    "Vaneer Industrial Silica Filler",
    "Tarnwick Sodium Bicarbonate",
]

# ⚑ THE SPEC LIBRARY. Each entry is (parameter, unit, lower, upper, decimals, slack).
# `lower` or `upper` may be None -- a one-sided specification ("not more than", "not less than")
# is normal quality-control practice and the kit has to carry the null rather than invent a bound.
# `slack` is the distance used to place a value inside or outside the window: small on purpose, so
# an out-of-spec batch is out by a hair and a reassuring note about it is genuinely tempting.
PARAMETERS = [
    ("moisture content", "%", 8.0, 12.0, 1, 0.3),
    ("assay purity", "%", 98.5, None, 2, 0.15),
    ("particle size D50", "microns", 45.0, 75.0, 1, 1.5),
    ("total plate count", "CFU/g", None, 1000.0, 0, 40.0),
    ("bulk density", "g/mL", 0.55, 0.75, 2, 0.02),
    ("ash content", "%", None, 0.50, 2, 0.02),
]

# Notes whose TONE says "this batch is fine". Used truthfully on a conforming batch, and against
# type on a non-conforming one -- which is half the planted ambiguity.
REASSURING_NOTES = [
    "Within normal range for this product line. Released to finished-goods inventory.",
    "Result consistent with the last twelve batches of this grade. No concerns; pass.",
    "Looks fine against typical line performance. Dispositioned released by day shift.",
    "Routine result, nothing unusual for this material. Cleared for release.",
]

# Notes whose TONE says "this batch is a worry". Used truthfully on a non-conforming batch, and
# against type on a conforming one -- the other half of the planted ambiguity.
CAUTIOUS_NOTES = [
    "Borderline in my judgement. Recommend a re-test on a second sample before release.",
    "Value sits near the edge of where this line normally runs. Batch placed on hold pending review.",
    "Marginal result. Flagged for the quality supervisor to look at before any disposition.",
    "Not comfortable signing this one off on a single determination. Suggest re-testing.",
]

BASE_DATE = datetime.date(2026, 1, 6)


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _fmt(value, decimals):
    """The one string form of a number used BOTH in the document and in gold.

    ⚠︎ THE DOCUMENT AND THE LABEL ARE WRITTEN FROM THE SAME STRING, ON PURPOSE. Rounding a float
    for display and storing the unrounded one in gold is how a corpus quietly stops containing its
    own labels -- 0.60 printed against 0.6000000000000001 stored. Everything downstream (the
    _verify() pass, evals/judge.py's numeric compare, src/segment.py::locate) reads the same value.
    """
    s = "%.*f" % (decimals, value)
    return str(int(float(s))) if decimals == 0 else str(float(s))


def _num(s):
    """The numeric twin of a _fmt() string. int when there is no decimal point, so `str()` of the
    stored label is byte-identical to what the document prints -- 940, never 940.0."""
    return float(s) if "." in s else int(s)


def _draw(rng, lower, upper, slack, conforming):
    """One candidate measured value, strictly inside or strictly outside the stated window."""
    if conforming:
        lo = lower if lower is not None else (upper - 10 * slack)
        hi = upper if upper is not None else (lower + 10 * slack)
        pad = slack / 2.0
        return rng.uniform(lo + pad, hi - pad)
    # Out of spec, and out by a hair -- between half and two full `slack` units past a bound.
    over = rng.uniform(slack * 0.5, slack * 2.0)
    sides = [s for s, b in (("lower", lower), ("upper", upper)) if b is not None]
    return (lower - over) if rng.choice(sides) == "lower" else (upper + over)


def _measured(rng, lower, upper, decimals, slack, conforming):
    """Draw until the value SURVIVES ROUNDING as the side it was meant to land on, and is not
    sitting exactly on a bound. Returns (display_string, numeric_value).

    ⚠︎ THE CHECK IS AFTER ROUNDING, WHICH IS THE ONLY PLACE IT COUNTS. A value drawn 0.005 outside
    an upper limit and printed to two decimals lands ON the limit in the document -- conforming
    under the published boundary-inclusive rule, while the generator still believed it was a fail.
    Redrawing is cheaper than a corpus whose labels are right about a number nobody can read.
    """
    s = m = None
    for _ in range(200):
        s = _fmt(_draw(rng, lower, upper, slack, conforming), decimals)
        m = _num(s)
        if m == lower or m == upper:
            continue
        if _conforms(m, lower, upper) == conforming:
            return s, m
    return s, m


def _conforms(measured, lower, upper):
    """THE RULE, in one place. Boundary-inclusive; a null bound constrains nothing on that side.
    src/extract.py::compute() recomputes exactly this from the MODEL's own extracted numbers."""
    lower_ok = (lower is None) or (measured >= lower)
    upper_ok = (upper is None) or (measured <= upper)
    return lower_ok and upper_ok


def build_all(rng, n=N_RECORDS):
    stats = {"conforming": 0, "non_conforming": 0, "ambiguous": 0, "one_sided": 0}
    out = []
    for i in range(1, n + 1):
        analyst = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        product = rng.choice(PRODUCTS)
        parameter, unit, lower, upper, decimals, slack = rng.choice(PARAMETERS)
        if lower is None or upper is None:
            stats["one_sided"] += 1

        batch_id = "BATCH-%s-%04d" % (rng.choice("ABCDEFGH"), rng.randint(1000, 9999))
        # ⚑ REAL DATE ARITHMETIC, NOT STRING SURGERY. timedelta gets month lengths right; building
        # "2026-%02d-%02d" from two independent draws does not, and produces 31 February.
        test_date = (BASE_DATE + datetime.timedelta(days=rng.randint(0, 220))).isoformat()

        conforming = rng.random() < CONFORMING_FRACTION
        measured_s, measured = _measured(rng, lower, upper, decimals, slack, conforming)

        # The label is recomputed from the ROUNDED value that the document actually states -- the
        # only value a reader or a model ever sees -- so gold can never disagree with the document.
        conforming = _conforms(measured, lower, upper)
        stats["conforming" if conforming else "non_conforming"] += 1

        ambiguous = rng.random() < AMBIGUOUS_FRACTION
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the arithmetic normally, and contradicts it when this record is ambiguous.
        reassuring = conforming if not ambiguous else (not conforming)
        note = rng.choice(REASSURING_NOTES if reassuring else CAUTIOUS_NOTES)

        lower_s = _fmt(lower, decimals) if lower is not None else None
        upper_s = _fmt(upper, decimals) if upper is not None else None
        none_line = "not specified (one-sided specification)"

        rec_id = "COA-%04d" % i
        lines = [
            _underline("Batch"), batch_id, "",
            _underline("Product"), product, "",
            _underline("Test Parameter"), parameter, "",
            _underline("Measured Result"), "%s %s" % (measured_s, unit), "",
            _underline("Specification Lower Limit"),
            ("%s %s" % (lower_s, unit)) if lower_s else none_line, "",
            _underline("Specification Upper Limit"),
            ("%s %s" % (upper_s, unit)) if upper_s else none_line, "",
            _underline("Test Date"), test_date, "",
            _underline("Analyst"), analyst, "",
            _underline("Analyst Disposition Note"), note, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "batch_id": batch_id,
            "product_name": product,
            "test_parameter": parameter,
            "measured_value": measured,
            "unit": unit,
            "spec_lower_limit": _num(lower_s) if lower_s else None,
            "spec_upper_limit": _num(upper_s) if upper_s else None,
            "analyst_disposition_note": note,
            "test_date": test_date,
            "conforms_to_spec": "yes" if conforming else "no",
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    """Every gold value must be stated in the document it labels, and every gold label must be the
    arithmetic the document's own numbers produce. A corpus whose labels are not readable off its
    own text is not a corpus, it is a second opinion."""
    for rec_id, text, gold in rows:
        for field in ("batch_id", "product_name", "test_parameter", "unit",
                      "analyst_disposition_note", "test_date"):
            assert gold[field] in text, "%s: %s not stated in the document" % (rec_id, field)
        for field in ("measured_value", "spec_lower_limit", "spec_upper_limit"):
            v = gold[field]
            if v is None:
                assert "not specified" in text, "%s: %s is null with no null line" % (rec_id, field)
                continue
            assert str(v) in text, \
                "%s: %s=%r not stated verbatim in the document" % (rec_id, field, v)
        assert gold["conforms_to_spec"] == (
            "yes" if _conforms(gold["measured_value"], gold["spec_lower_limit"],
                               gold["spec_upper_limit"]) else "no"), \
            "%s: gold label disagrees with its own numbers" % rec_id
        # The date must be a real calendar date, not a plausible-looking string.
        datetime.date.fromisoformat(gold["test_date"])


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

    print("records: %d   conforming: %d   non-conforming: %d   one-sided specs: %d"
          % (len(rows), stats["conforming"], stats["non_conforming"], stats["one_sided"]))
    print("%d (%.0f%%) carry an analyst note whose TONE contradicts the arithmetic"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("internal consistency check: PASSED (every gold value is stated in its own document, "
          "every label is that document's own arithmetic, every date is a real calendar date)")


if __name__ == "__main__":
    main()
