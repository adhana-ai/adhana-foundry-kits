#!/usr/bin/env python3
"""Generate the variance events and their gold cause + citations, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/events.jsonl and data/gold.jsonl, byte-identical on every run. Nothing is fetched and
nothing is licensed from anybody: every location, SKU, category and log line here is invented, so
the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ GOLD IS DERIVED, NEVER TYPED. Each scenario builder below constructs a plausible transaction
log carrying the STRUCTURAL evidence a real one would (a flagged receiving-correction line, a
flagged counterpart-activity line, and so on) -- it never writes a `true_cause` string directly.
Once an event's log is assembled, `src/segment.py::classify()` is the ONLY thing that decides its
gold cause and citations, from the log and variance_qty alone -- the identical function the
pipeline and the scorer both call on a live run. `tools/verify_gold.py` re-runs classify() over
the finished data/gold.jsonl and fails loudly if a single row disagrees.

⚑ FIVE SCENARIOS, ONE OF THEM SPLIT IN TWO -- same discipline gap-brief's own build_corpus.py
states for its seven:

    mis_receipt            a receiving correction was logged but never applied to on-hand.
    unrecorded_transfer    PLAIN -- the variance is an ordinary size; a counterpart-activity line
                           is the only signal.
    unrecorded_transfer    TRAP -- same signal, but variance_qty is ALSO a clean case-pack
                           multiple, so it superficially reads as uom_error. This is THE named
                           failure mode the use case exists to catch: named `trap` in the tally,
                           and it is what evals/scoring.py's uom_transfer_confusion metric counts
                           a model getting wrong.
    uom_error               genuine -- variance_qty is a case-pack multiple AND a specific log
                           line shows the eaches/cases mix-up. Both conditions are required; see
                           src/segment.py::classify() for why the trap needs both to resolve.
    unscanned_movement      the log's own arithmetic (src/segment.py::accounted_change) does not
                           reconcile with variance_qty, and at least one scan line exists to
                           point to.
    unresolved               no flag fires and no scan line exists to fall back on -- the honest,
                           correct answer when the log genuinely doesn't explain the count.
"""
import argparse
import datetime
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")

from src import segment as SEG          # noqa: E402

SEED = 20260819                          # fixed. change it and every downstream file changes.

CATEGORIES = [
    "Hardware Fasteners", "Paper Products", "Cleaning Chemicals", "Small Appliances",
    "Packaged Beverages", "Office Supplies", "Pet Food", "Light Bulbs & Fixtures",
    "Batteries", "Kitchen Textiles", "Storage Containers", "Automotive Fluids",
    "Garden Tools", "Health & Wellness",
]
LOCATIONS = ["LOC-%03d" % i for i in range(1, 31)]
PERIODS = ["2026-W%02d" % w for w in range(5, 34)]

CASE_PACK_SIZES = SEG.CASE_PACK_SIZES

# One of each traceable scenario plus unresolved, with unrecorded_transfer split into its plain
# and trap variants at generation time -- see build_events() for the exact per-scenario counts,
# stated once there rather than inferred from these weights.
SCENARIOS = ["mis_receipt", "unrecorded_transfer_plain", "unrecorded_transfer_trap",
            "uom_error", "unscanned_movement", "unresolved"]
COUNTS = {"mis_receipt": 7, "unrecorded_transfer_plain": 5, "unrecorded_transfer_trap": 4,
         "uom_error": 7, "unscanned_movement": 7, "unresolved": 6}          # 36 events total


def _ev_id(i):
    return "VC-%04d" % (1 + i)


def _week_end(period):
    year, wk = int(period[:4]), int(period[6:8])
    return datetime.date.fromisocalendar(year, wk, 5)          # Friday of that ISO week


def _ts(anchor, days_before):
    return (anchor - datetime.timedelta(days=days_before)).isoformat()


def _noise_lines(rng, n, allow_scan=True):
    """Routine, unrelated transaction lines -- real data, no signal. `allow_scan=False` is used
    by the unresolved builder so no stray scan line lets src/segment.py::classify() fall through
    to unscanned_movement by accident."""
    pool = []
    kinds = ["receiving", "transfer", "adjustment"] + (["scan"] if allow_scan else [])
    for _ in range(n):
        k = rng.choice(kinds)
        if k == "receiving":
            qty = rng.randint(4, 60)
            po = "PO-%05d" % rng.randint(10000, 99999)
            pool.append(("receiving", {"qty": qty, "po_ref": po},
                        rng.choice([
                            "Received %d units against %s." % (qty, po),
                            "Receiving posted for %s: %d units logged to on-hand." % (po, qty),
                        ])))
        elif k == "transfer":
            qty = rng.randint(3, 40)
            direction = rng.choice(["in", "out"])
            counterpart = rng.choice(LOCATIONS)
            pool.append(("transfer", {"qty": qty, "direction": direction,
                                      "counterpart": counterpart},
                        ("Transfer in: %d units received from %s." % (qty, counterpart)
                         if direction == "in" else
                         "Transfer out: %d units sent to %s." % (qty, counterpart))))
        elif k == "adjustment":
            qty = rng.choice([-1, 1]) * rng.randint(2, 15)
            pool.append(("adjustment", {"qty": qty},
                        rng.choice([
                            "Manual on-hand correction posted: %+d units." % qty,
                            "Prior-period cycle count correction applied: %+d units." % qty,
                        ])))
        else:
            qty = rng.randint(5, 45)
            pool.append(("scan", {"qty": qty},
                        rng.choice([
                            "POS scan/pick: %d units moved out." % qty,
                            "%d units picked and scanned out per POS." % qty,
                        ])))
    return pool


def _line(kind, ts, fields, note, flag=None):
    d = {"ts": ts, "type": kind, "note": note}
    d.update(fields)
    if flag:
        d["flag"] = flag
    return d


def build_mis_receipt(rng, anchor):
    variance = rng.choice([-1, 1]) * rng.randint(15, 90)
    received = rng.randint(60, 320)
    po_expected = received + variance          # what the PO actually called for
    po = "PO-%05d" % rng.randint(10000, 99999)
    lines = [
        ("receiving", {"qty": received, "po_ref": po},
         "Received %d units against %s." % (received, po), None),
        ("adjustment", {"qty": variance, "linked_po_ref": po},
         rng.choice([
             "Correction thread on %s: PO called for %d units; %d were logged as received "
             "instead. Discrepancy of %+d units was never posted to on-hand."
             % (po, po_expected, received, variance),
             "%s discrepancy flagged: %d units logged against a PO for %d; the %+d-unit gap "
             "was never corrected on-hand." % (po, received, po_expected, variance),
         ]), "receiving_correction"),
    ]
    return variance, lines


def build_unrecorded_transfer(rng, anchor, trap):
    if trap:
        pack = rng.choice(CASE_PACK_SIZES)
        variance = rng.choice([-1, 1]) * pack * rng.randint(1, 6)
    else:
        variance = rng.choice([-1, 1]) * rng.randint(15, 90)
        while SEG.is_case_pack_multiple(variance):          # plain means NOT a coincidental hit
            variance += rng.choice([-1, 1])
    counterpart = rng.choice(LOCATIONS)
    lines = [
        ("adjustment", {"qty": abs(variance), "counterpart": counterpart},
         rng.choice([
             "Regional log shows %s posted a partial adjustment of %d units around this same "
             "count window -- not logged here as a transfer."
             % (counterpart, abs(variance)),
             "%s's own cycle count this period flagged %d units of receiving/adjustment "
             "activity that lines up with this window, though no transfer was logged between "
             "the two locations." % (counterpart, abs(variance)),
         ]), "counterpart_activity"),
    ]
    return variance, lines


def build_uom_error(rng, anchor):
    pack = rng.choice(CASE_PACK_SIZES)
    cases = rng.randint(1, 8)
    variance = rng.choice([-1, 1]) * cases * pack
    po = "PO-%05d" % rng.randint(10000, 99999)
    lines = [
        ("receiving", {"qty": cases, "po_ref": po, "pack_size": pack},
         rng.choice([
             "Received %d units against %s, logged in cases (case pack = %d) -- worth "
             "confirming this posted as eaches, not cases." % (cases, po, pack),
             "%s receiving shows %d units entered; item's case pack is %d, so confirm whether "
             "this was keyed in eaches or cases." % (po, cases, pack),
         ]), "uom_note"),
    ]
    return variance, lines


def build_unscanned_movement(rng, anchor):
    received = rng.randint(20, 120)
    po = "PO-%05d" % rng.randint(10000, 99999)
    scanned = rng.randint(10, 80)
    adj = rng.choice([-1, 1]) * rng.randint(2, 12)
    base_log = [
        ("receiving", {"qty": received, "po_ref": po},
         "Received %d units against %s." % (received, po), None),
        ("scan", {"qty": scanned}, "POS scan/pick: %d units moved out." % scanned, None),
        ("adjustment", {"qty": adj}, "Manual on-hand correction posted: %+d units." % adj, None),
    ]
    accounted = SEG.accounted_change([{"type": k, **f} for k, f, _n, _fl in base_log])
    residual = rng.randint(8, 40)          # the extra, un-logged outbound movement
    variance = accounted + residual
    return variance, base_log


def build_unresolved(rng, anchor):
    variance = rng.choice([-1, 1]) * rng.randint(15, 90)
    received = rng.randint(20, 150)
    po = "PO-%05d" % rng.randint(10000, 99999)
    transfer_qty = rng.randint(5, 30)
    counterpart = rng.choice(LOCATIONS)
    lines = [
        ("receiving", {"qty": received, "po_ref": po},
         "Received %d units against %s." % (received, po), None),
        ("transfer", {"qty": transfer_qty, "direction": "in", "counterpart": counterpart},
         "Transfer in: %d units received from %s." % (transfer_qty, counterpart), None),
    ]
    return variance, lines


BUILDERS = {
    "mis_receipt": build_mis_receipt,
    "unrecorded_transfer_plain": lambda rng, a: build_unrecorded_transfer(rng, a, trap=False),
    "unrecorded_transfer_trap": lambda rng, a: build_unrecorded_transfer(rng, a, trap=True),
    "uom_error": build_uom_error,
    "unscanned_movement": build_unscanned_movement,
    "unresolved": build_unresolved,
}

# (min, max) noise lines added on top of each scenario's own signal lines, sized so every event
# lands in the stated 4-10 log lines/event range regardless of how many signal lines the scenario
# itself contributes.
NOISE_RANGE = {
    "mis_receipt": (2, 5), "unrecorded_transfer_plain": (3, 6),
    "unrecorded_transfer_trap": (3, 6), "uom_error": (3, 6),
    "unscanned_movement": (2, 5), "unresolved": (2, 5),
}


def build_event(i, scenario, rng):
    cat = rng.choice(CATEGORIES)
    sku = "SKU-%05d" % rng.randint(10000, 99999)
    location = rng.choice(LOCATIONS)
    period = rng.choice(PERIODS)
    anchor = _week_end(period)

    variance, signal_lines = BUILDERS[scenario](rng, anchor)

    allow_scan = scenario != "unresolved"          # keep unresolved genuinely scan-free
    lo, hi = NOISE_RANGE[scenario]
    noise = _noise_lines(rng, rng.randint(lo, hi), allow_scan=allow_scan)

    combined = []
    for kind, fields, note, flag in signal_lines:
        combined.append((kind, fields, note, flag))
    for kind, fields, note in noise:
        combined.append((kind, fields, note, None))

    # Chronological order within a ~2-week window ending at the cycle count -- a real transaction
    # log reads this way, and it is the order src/pack.py hands the model, so indices are stable.
    offsets = sorted(rng.sample(range(0, 14), k=len(combined)), reverse=True)
    log = [_line(kind, _ts(anchor, off), fields, note, flag)
          for off, (kind, fields, note, flag) in zip(offsets, combined)]

    system_qty = rng.randint(120, 1400)
    counted_qty = system_qty - variance
    if counted_qty < 0:                     # keep it physically plausible; resample the base
        system_qty += abs(counted_qty) + rng.randint(10, 50)
        counted_qty = system_qty - variance

    event = {
        "event_id": _ev_id(i), "item_id": sku, "item_label": cat, "location_id": location,
        "period": period, "system_qty": system_qty, "counted_qty": counted_qty,
        "variance_qty": variance, "log": log,
    }
    return event, scenario


CONFIRM_TEMPLATES = {
    "mis_receipt": "Confirmed cause: mis-receipt. %s",
    "unrecorded_transfer": "Confirmed cause: unrecorded transfer. %s",
    "uom_error": "Confirmed cause: unit-of-measure error. %s",
    "unscanned_movement": "Confirmed cause: unscanned movement. %s",
    "unresolved": "Confirmed cause: unresolved -- transaction history does not clearly support "
                 "one of the four named causes.",
}


def confirmed_note(cause, event, citations):
    """The short note inventory control would actually leave when confirming the cause --
    generated FROM the derived cause and its own cited line, never authored separately. This is
    what tools/verify_gold.py re-derives and checks against data/gold.jsonl's own `confirmed_note`
    field, closing the loop on 'never independently authored' for the narrative too."""
    if cause == "unresolved":
        return CONFIRM_TEMPLATES["unresolved"]
    cite_note = event["log"][citations[0]]["note"] if citations else ""
    return CONFIRM_TEMPLATES[cause] % cite_note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-events", type=int, default=None,
                    help="default: the stated per-scenario COUNTS, summing to 36")
    args = ap.parse_args()

    rng = random.Random(SEED)
    os.makedirs(DATA, exist_ok=True)

    plan = []
    for scenario, n in COUNTS.items():
        plan.extend([scenario] * n)
    rng.shuffle(plan)
    if args.n_events:
        plan = plan[:args.n_events]

    events, gold_rows = [], []
    tally = {}
    cause_tally = {}
    trap_n = 0
    for i, scenario in enumerate(plan):
        event, planted = build_event(i, scenario, rng)
        fx = SEG.classify(event)          # gold is DERIVED here, never typed
        note = confirmed_note(fx["cause"], event, fx["citations"])
        is_trap = (fx["cause"] == "unrecorded_transfer"
                  and SEG.is_case_pack_multiple(event["variance_qty"]))
        events.append(event)
        gold_rows.append({
            "event_id": event["event_id"], "planted_scenario": planted,
            "cause": fx["cause"], "citations": fx["citations"],
            "confirmed_note": note, "is_trap": is_trap,
        })
        tally[planted] = tally.get(planted, 0) + 1
        cause_tally[fx["cause"]] = cause_tally.get(fx["cause"], 0) + 1
        if is_trap:
            trap_n += 1

    with open(os.path.join(DATA, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold_rows:
            f.write(json.dumps(g) + "\n")

    print("events: %d" % len(events))
    print("planted-scenario tally:", tally)
    print("derived-cause tally:", cause_tally)
    print("trap events (unrecorded_transfer AND case-pack multiple): %d" % trap_n)


if __name__ == "__main__":
    main()
