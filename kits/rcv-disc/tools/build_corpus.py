#!/usr/bin/env python3
"""Generate the receiving-discrepancy cases this kit checks against, from a fixed seed.

    python3 tools/build_corpus.py
    python3 tools/build_corpus.py --verify     # re-reads data/*.jsonl from disk and re-derives
                                                # every gold row independently -- see verify()

Writes data/cases.jsonl and data/gold.jsonl, byte-identical on every run. Nothing is fetched and
nothing is licensed from anybody: every SKU, PO number, case ID and carrier name here is invented,
so the corpus ships under this repo's MIT licence and there is no third-party grant to verify.

⚑ WHY THE CASES ARE INVENTED. A real receiving discrepancy names a real vendor, a real carrier and
a real dollar chargeback nobody will let leave the building. A synthetic set is the only kind of
receiving corpus that can be re-run by a stranger with a clone and no NDA to sign. See
data/SOURCES.md.

⚑ ALL THREE QUANTITIES ARE ALWAYS PRESENT, ON EVERY LINE. Every case's SKU lines carry a real
po_qty, bol_qty and received_qty -- never a blank -- because the mechanic this kit measures is
finding the ONE line where the three numbers disagree among several that agree, not filling in a
missing field. See src/prompt.py for the taxonomy stated to the model.

⚑ THE TRAP, PLANTED ON PURPOSE. A meaningful fraction of the cases whose true liable party is
`internal` (the discrepancy looks like a transit loss, but nothing corroborates it for this SKU)
are built with a carrier exception note ON FILE, naming a DIFFERENT SKU on the same case. This is a
DATA-SHAPE trap, not adversarial text -- the note is a genuine, real note about a genuine, different
line's problem. It does not excuse the discrepant line, and the eval exists to measure whether a
reader (model or baseline) checks WHICH SKU the note names or just registers "an exception exists".
See TRAP_N below for exactly how often, and `classify_case()` for the taxonomy rule itself, used
both to label gold and, independently, by --verify to catch this file lying about its own corpus.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
SEED = 20260819                              # fixed. change it and every downstream file changes.

DOCS = ("po", "bol", "received")

# 36 cases across the four liable-party values -- similar order of magnitude to every sibling
# kit's corpus. `internal` is the largest bucket on purpose: it is the one split into a trap half
# and a clean half, and it needs enough of each for the trap rate below to mean anything.
#
# ⚑ 6 OF THE 14 `internal` CASES CARRY A WRONG-SKU EXCEPTION NOTE -- ~43%, THE SAME ORDER OF
# MAGNITUDE AS fin-invval's 45% ambiguous-phrasing rate and fin-payrun's ~43% trap rate. The other
# 8 `internal` cases carry no exception note at all, so the model also has to get the plain,
# uncorroborated case right, not just the one with a decoy on file.
CASE_PLAN = (
    ("vendor", 8),
    ("carrier", 8),
    ("internal_trap", 6),
    ("internal_clean", 8),
    ("insufficient_overship", 3),
    ("insufficient_compound", 3),
)

CARRIERS = [
    "Meridian Freight Lines", "Continental Overland", "Blue Harbor Logistics",
    "Redline Transit Co", "Northbridge Carriers", "Union Point Freight",
    "Coastal Line Haul", "Anchor Point Shipping",
]

# ⚠︎ EVERY TEMPLATE EMBEDS THE SKU VERBATIM AS "{sku}" -- deliberately, so `classify_case()` (and
# a model reading the note) can tell which line it names with a plain substring check rather than
# a fragile parse. A real carrier exception feed would carry this as a structured field; the prose
# form is what makes reading it the model's job instead of a lookup.
EXCEPTION_TEMPLATES = [
    "1 carton damaged in transit, refused at dock, {sku}",
    "short-shipped at origin per carrier manifest, {sku}",
    "pallet found wet on arrival, partial refusal noted for {sku}",
    "seal broken in transit; contents inspected and short, {sku}",
    "driver logged a delivery exception for {sku} -- shortage at drop",
    "carrier reported a shortage at pickup for {sku}",
]


def classify_case(lines, carrier_exception):
    """The four-way liability rule, and the ONLY place it is written. Used to label gold at
    generation time AND, independently via --verify, to re-derive gold from the case actually
    written to disk -- so a drift between the two is caught rather than assumed away. See
    src/prompt.py's SYSTEM for the same rule stated to the model.

    Exactly one line must be discrepant (its three quantities do not all agree) -- that is a
    corpus-construction invariant, asserted here rather than trusted.
    """
    disc = [l for l in lines if not (l["po_qty"] == l["bol_qty"] == l["received_qty"])]
    assert len(disc) == 1, "expected exactly one discrepant line, found %d" % len(disc)
    ln = disc[0]
    po, bol, rec, sku = ln["po_qty"], ln["bol_qty"], ln["received_qty"], ln["sku"]

    exception_names_sku = bool(carrier_exception) and (sku in carrier_exception)

    if bol < po and rec == bol:
        # Vendor under-shipped what was ordered; the carrier delivered everything it was given.
        liable, doc_a, qty_a, doc_b, qty_b = "vendor", "po", po, "bol", bol
    elif bol == po and rec < bol and exception_names_sku:
        # Full PO qty shipped, less arrived, AND the carrier's own note corroborates THIS SKU.
        liable, doc_a, qty_a, doc_b, qty_b = "carrier", "bol", bol, "received", rec
    elif bol == po and rec < bol:
        # Same transit-loss shape, but nothing on file corroborates it for this SKU.
        liable, doc_a, qty_a, doc_b, qty_b = "internal", "bol", bol, "received", rec
    else:
        # BOL and receiving agree with each other but not with the PO (an apparent
        # over-shipment), or more than one quantity disagrees at once -- no clean basis.
        liable, doc_a, qty_a, doc_b, qty_b = "insufficient_evidence", "po", po, "received", rec

    trap = (liable == "internal" and bool(carrier_exception) and not exception_names_sku)
    return {
        "liable_party": liable, "discrepant_sku": sku,
        "doc_a": doc_a, "qty_a": qty_a, "doc_b": doc_b, "qty_b": qty_b,
        "delta": abs(qty_a - qty_b),
        "trap": trap,
        "exception_names_sku": (exception_names_sku if carrier_exception else None),
    }


def _clean_line(sku, rng):
    q = rng.randint(20, 450)
    return {"sku": sku, "po_qty": q, "bol_qty": q, "received_qty": q}


def _vendor_line(sku, rng):
    po = rng.randint(60, 450)
    shortfall = rng.randint(5, max(6, po // 3))
    bol = po - shortfall
    return {"sku": sku, "po_qty": po, "bol_qty": bol, "received_qty": bol}


def _transit_line(sku, rng):
    """Full PO qty on the BOL, less arrived -- the shape both `carrier` and `internal` share.
    Which of the two a case resolves to depends only on the carrier_exception field, not on this
    line's own numbers."""
    po = rng.randint(60, 450)
    shortfall = rng.randint(5, max(6, po // 3))
    return {"sku": sku, "po_qty": po, "bol_qty": po, "received_qty": po - shortfall}


def _overship_line(sku, rng):
    po = rng.randint(60, 450)
    surplus = rng.randint(5, max(6, po // 4))
    bol = po + surplus
    return {"sku": sku, "po_qty": po, "bol_qty": bol, "received_qty": bol}


def _compound_line(sku, rng):
    """All three quantities differ -- a vendor-shaped shortfall stacked with a further transit
    loss. Neither the vendor rule (needs received == bol) nor the carrier/internal rule (needs
    bol == po) resolves this cleanly, which is the point: a genuinely ambiguous line, not an
    engineered puzzle."""
    po = rng.randint(80, 450)
    d1 = rng.randint(5, max(6, po // 4))
    bol = po - d1
    d2 = rng.randint(5, max(6, bol // 4))
    return {"sku": sku, "po_qty": po, "bol_qty": bol, "received_qty": bol - d2}


_LINE_BUILDERS = {
    "vendor": _vendor_line,
    "carrier": _transit_line,
    "internal_trap": _transit_line,
    "internal_clean": _transit_line,
    "insufficient_overship": _overship_line,
    "insufficient_compound": _compound_line,
}

_EXPECT_LIABLE = {
    "vendor": "vendor",
    "carrier": "carrier",
    "internal_trap": "internal",
    "internal_clean": "internal",
    "insufficient_overship": "insufficient_evidence",
    "insufficient_compound": "insufficient_evidence",
}

_N_LINES_POP = [2, 3, 4]
_N_LINES_WEIGHTS = [15, 60, 25]                       # "most cases: 3" -- see the product spec


def build_case(idx, category, sku_seq, rng):
    """One case record. `category` decides the SHAPE this case is built to (which line-builder
    runs, and whether/how the exception note is planted); `classify_case()` is then run on the
    finished record and asserted to match what `category` intends -- the gold label is never the
    category string itself, precisely so a bug in this function's field construction cannot
    silently ship a mislabelled row."""
    n_lines = rng.choices(_N_LINES_POP, weights=_N_LINES_WEIGHTS, k=1)[0]
    disc_idx = rng.randrange(n_lines)

    lines = []
    disc_sku = None
    for i in range(n_lines):
        sku_seq[0] += 1
        sku = "SKU-%04d" % sku_seq[0]
        if i == disc_idx:
            lines.append(_LINE_BUILDERS[category](sku, rng))
            disc_sku = sku
        else:
            lines.append(_clean_line(sku, rng))

    carrier_exception = None
    if category == "carrier":
        carrier_exception = rng.choice(EXCEPTION_TEMPLATES).format(sku=disc_sku)
    elif category == "internal_trap":
        other_skus = [l["sku"] for l in lines if l["sku"] != disc_sku]
        carrier_exception = rng.choice(EXCEPTION_TEMPLATES).format(sku=rng.choice(other_skus))

    case = {
        "case_id": "CASE-%05d" % idx,
        "po_number": "PO-%06d" % rng.randint(100000, 999999),
        "carrier_name": rng.choice(CARRIERS),
        "lines": lines,
        "carrier_exception": carrier_exception,
    }

    result = classify_case(case["lines"], case["carrier_exception"])
    assert result["liable_party"] == _EXPECT_LIABLE[category], (
        "%s: built for %r but classify_case says %r"
        % (case["case_id"], category, result["liable_party"]))
    assert result["trap"] == (category == "internal_trap"), (
        "%s: trap flag %r does not match category %r" % (case["case_id"], result["trap"], category))

    gold = {"case_id": case["case_id"]}
    gold.update(result)
    return case, gold


def build_corpus(rng):
    plan = []
    for category, n in CASE_PLAN:
        plan.extend([category] * n)
    rng.shuffle(plan)                    # cases are not grouped by category in the file

    sku_seq = [4000]                     # mutable counter, globally unique across every case
    cases, gold = [], []
    for i, category in enumerate(plan, 1):
        case, g = build_case(i, category, sku_seq, rng)
        cases.append(case)
        gold.append(g)
    return cases, gold


def write(cases, gold):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "cases.jsonl"), "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")


def verify():
    """Re-read data/cases.jsonl and data/gold.jsonl FROM DISK -- not from build_corpus()'s
    in-memory return values -- and re-derive every gold row independently via classify_case().
    This is the mandatory internal-consistency check: gold must never be hand-labelled or
    copy-pasted, it must be reproducible from the case record alone, every time, by anyone who
    clones the repo. Same discipline data-reconcile's, fin-payrun's and fin-invval's corpus
    builders all enforce."""
    cases_path = os.path.join(DATA, "cases.jsonl")
    gold_path = os.path.join(DATA, "gold.jsonl")
    cases = [json.loads(l) for l in open(cases_path, encoding="utf-8") if l.strip()]
    gold_rows = {g["case_id"]: g for g in
                (json.loads(l) for l in open(gold_path, encoding="utf-8") if l.strip())}

    checked = 0
    for case in cases:
        g = gold_rows[case["case_id"]]
        result = classify_case(case["lines"], case["carrier_exception"])
        for field in ("liable_party", "discrepant_sku", "doc_a", "qty_a", "doc_b", "qty_b",
                     "delta", "trap", "exception_names_sku"):
            assert result[field] == g[field], (
                "%s: gold says %s=%r but classify_case(record) says %r"
                % (case["case_id"], field, g[field], result[field]))
        checked += 1

    trap_rows = [g for g in gold_rows.values() if g["trap"]]
    internal_rows = [g for g in gold_rows.values() if g["liable_party"] == "internal"]
    print("verify: %d cases checked against gold, all fields match, 0 drift" % checked)
    print("verify: %d trap cases of %d internal cases (%.0f%%), every one with a carrier "
          "exception on file that names a different SKU than its own discrepant line"
          % (len(trap_rows), len(internal_rows), 100.0 * len(trap_rows) / len(internal_rows)))
    for g in trap_rows:
        assert g["exception_names_sku"] is False


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
    cases, gold = build_corpus(rng)
    write(cases, gold)

    tally = {}
    for g in gold:
        tally[g["liable_party"]] = tally.get(g["liable_party"], 0) + 1
    n_lines_total = sum(len(c["lines"]) for c in cases)
    print("cases: %d   lines: %d (avg %.1f/case)" % (len(cases), n_lines_total,
                                                     n_lines_total / len(cases)))
    print("liable_party tally:", tally)
    verify()


if __name__ == "__main__":
    main()
