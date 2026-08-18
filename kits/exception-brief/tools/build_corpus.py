#!/usr/bin/env python3
"""Generate the review batches, their flagged item/location evidence packets, their merchant
notes, and the gold exception list, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/batches.jsonl, data/notes.jsonl and data/gold.jsonl, byte-identical on every run.
Nothing is fetched and nothing is licensed from anybody: every batch, category and note line here
is invented, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ WHY THE SCENARIO IS RETAIL-FLAVORED BUT THE PATTERN ISN'T. The originating atlas row is a
statistical-forecast exception review -- code flags item/location combinations where recent POS
disagrees with the baseline, assembles the evidence, and the model tags a probable cause. That is
one instance of a generic pattern: an automated forecast/baseline throws exceptions, and someone
has to assemble the supporting evidence and a probable explanation before a human decides what to
do about it. Retail categories are the flavor of THIS corpus, not a claim about what the kit is for
-- src/segment.py, src/pack.py and src/prompt.py never mention retail.

⚑ SEVEN SCENARIOS, EACH PLANTED ON PURPOSE -- same discipline gap-brief's build_corpus.py states
for its own seven:

    clean                all three signals agree with ordinary forecast noise. Not itemized.
    promo_uncaptured      a promo not baked into the baseline explains an uplift. Traceable via
                          two notes lines.
    oos_suppressed        a lost-sales/OOS period explains why recent POS moved. Traceable.
    onetime_event         a one-off, non-repeating local driver explains the move. Traceable.
    assortment_shift      an item/pack/channel change broke comparability with the baseline.
                          Traceable.
    unknown_gap           a real, material exception -- but the notes do not explain it.
                          Untraceable on purpose, to prove the model says 'unknown' rather than
                          guessing.
    data_quality_flag     this item/location's recent POS is flagged unreliable (a register/data
                          outage). Material by itself, cause is 'unknown', no citations -- the
                          mandatory-caveat case.

⚑ NOISE LINES ARE PLANTED TOO. Each batch's notes log carries several lines that mention a
DIFFERENT item, or mention nothing decision-relevant at all, so a model that cites "the nearest
plausible-looking line" rather than an item-matched one is caught by the citation-fidelity check in
evals/scoring.py -- the substring must be real, but being real is not sufficient on its own for the
item it is cited against, which evals/scoring.py also checks.
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")

from src import segment as SEG          # noqa: E402

SEED = 20260818                          # fixed. change it and every downstream file changes.

CATEGORIES = ["snacks", "beverages", "personal-care", "home-goods", "seasonal-decor",
             "pet-supplies", "small-appliances", "bath-textiles", "outdoor-furniture", "cookware",
             "apparel-basics", "footwear"]
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West Coast"]
WEEKS = ["2026-W05", "2026-W12", "2026-W19", "2026-W26"]
LOCATIONS = ["Store 104", "Store 118", "Store 122", "Store 131", "Store 147", "DC-East Pool",
            "DC-West Pool"]

# Weighted so ~28% of items are clean and the remaining ~72% split across six planted scenarios --
# heavier on planted exceptions than a real deployment would likely see, on purpose: an eval corpus
# that is mostly clean teaches a scorer almost nothing about the traceable/untraceable distinction
# this kit exists to get right.
SCENARIOS = ["clean", "promo_uncaptured", "oos_suppressed", "onetime_event", "assortment_shift",
            "unknown_gap", "data_quality_flag"]
WEIGHTS = [0.28, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]

NOISE_LINES = [
    "Reminder: exception review sign-off is due Friday EOD, no exceptions this quarter.",
    "POS system maintenance window logged for Sunday overnight -- unrelated to weekday sell-through.",
    "New planner onboarding starts next cycle; expect handoff notes on the shared items.",
    "Store remodel schedule posted to the shared drive, unrelated to this week's numbers.",
    "Vendor scorecard refresh landed in the shared drive, unrelated to this cycle's exceptions.",
    "Please use the new exception-review template for next cycle -- old one is deprecated.",
    "IT ticket open for the reporting tool's export button; workaround is CSV download.",
    "Regional planner is out next week; route urgent items to the deputy instead.",
]


def _sup_id(i):
    return "EB-%04d" % (1 + i)


def _cause_notes(rng, item_label, cause, direction):
    """Two verbatim notes lines that together explain `cause` for `item_label`. Phrasing is
    templated with light variation so a checker cannot key off one fixed sentence -- same
    discipline as gap-brief's own note generator."""
    up = "up" if direction > 0 else "down"
    if cause == "promo_uncaptured":
        return [
            "%s: a promo/ad placement was locked in after the statistical forecast was generated "
            "-- the baseline never saw it." % item_label,
            "Follow-up on %s -- confirmed the promo calendar entry posted late this cycle; expect "
            "POS to keep running %s of the stat forecast while it's live." % (item_label, up),
        ]
    if cause == "oos_suppressed":
        return [
            "%s: recorded lost-sales/OOS days this week -- registers show sell-through capped by "
            "empty shelf, not soft demand." % item_label,
            "Replenishment note on %s -- confirmed the stockout window; POS this week does not "
            "reflect true demand." % item_label,
        ]
    if cause == "onetime_event":
        return [
            "%s: a local event/weather swing drove an unusual move this week -- not expected to "
            "repeat." % item_label,
            "Flagging %s -- store ops confirmed the one-off driver; no planned recurrence next "
            "cycle." % item_label,
        ]
    if cause == "assortment_shift":
        return [
            "%s: pack size/SKU changed this cycle -- the stat forecast's history is still keyed "
            "to the old item." % item_label,
            "Merchant note on %s -- confirmed the assortment change broke comparability with the "
            "forecast baseline." % item_label,
        ]
    return []


def build_items(batch_i, rng):
    cats = rng.sample(CATEGORIES, k=5)
    items = []
    scenario_notes = []
    for j, cat in enumerate(cats):
        item_id = "IT-%d" % (j + 1)
        item_label = cat
        location = rng.choice(LOCATIONS)
        forecast = round(rng.uniform(80, 3000), 0)
        prior_year_analog = round(forecast * rng.uniform(0.85, 1.15), 0)
        scenario = rng.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        actual = None
        lost_sales_oos_flag = False
        promo_flag = False
        cause = None
        citations = []

        if scenario == "clean":
            actual = round(forecast * rng.uniform(0.95, 1.05), 0)
        elif scenario == "data_quality_flag":
            actual = None
            cause = "unknown"
        else:
            shift = rng.choice([-1, 1]) * rng.uniform(0.22, 0.48)
            actual = round(forecast * (1 + shift), 0)
            if scenario == "unknown_gap":
                cause = "unknown"
            else:
                cause = scenario
                citations = _cause_notes(rng, item_label, scenario, shift)
                if scenario == "promo_uncaptured":
                    promo_flag = True
                elif scenario == "oos_suppressed":
                    lost_sales_oos_flag = True

        item = {"item_id": item_id, "item_label": item_label, "location": location,
               "forecast_units": forecast, "actual_pos_units": actual,
               "lost_sales_oos_flag": lost_sales_oos_flag, "promo_flag": promo_flag,
               "prior_year_analog_units": prior_year_analog}
        items.append(item)
        scenario_notes.append({
            "item_id": item_id, "item_label": item_label, "scenario": scenario,
            "true_cause": cause, "citations": citations,
        })
    return items, scenario_notes


def build_batch(i, rng):
    batch_id = _sup_id(i)
    region = rng.choice(REGIONS)
    review_week = rng.choice(WEEKS)
    items, scenario_notes = build_items(i, rng)

    # Assemble the notes log: every scenario's own citation pair (if any), plus noise lines,
    # shuffled together -- order carries no signal, same discipline gap-brief's shuffled notes use.
    notes = []
    for sn in scenario_notes:
        notes.extend(sn["citations"])
    n_noise = rng.randint(3, 5)
    notes.extend(rng.sample(NOISE_LINES, k=min(n_noise, len(NOISE_LINES))))
    rng.shuffle(notes)

    batch = {"batch_id": batch_id, "region": region, "review_week": review_week, "items": items}

    exceptions = []
    for it, sn in zip(items, scenario_notes):
        fx = SEG.flag(it)
        exceptions.append({
            "item_id": it["item_id"], "item_label": it["item_label"],
            "scenario": sn["scenario"], "unreliable_evidence": fx["unreliable_evidence"],
            "delta_units": fx["delta_units"], "delta_pct": fx["delta_pct"],
            "material": fx["material"], "true_cause": sn["true_cause"],
            "citations": sn["citations"],
        })
    return batch, {"batch_id": batch_id, "notes": notes}, {"batch_id": batch_id, "items": exceptions}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-batches", type=int, default=40)
    args = ap.parse_args()

    rng = random.Random(SEED)
    os.makedirs(DATA, exist_ok=True)

    batches, notes_rows, gold_rows = [], [], []
    for i in range(args.n_batches):
        batch, notes, gold = build_batch(i, rng)
        batches.append(batch)
        notes_rows.append(notes)
        gold_rows.append(gold)

    with open(os.path.join(DATA, "batches.jsonl"), "w", encoding="utf-8") as f:
        for b in batches:
            f.write(json.dumps(b) + "\n")
    with open(os.path.join(DATA, "notes.jsonl"), "w", encoding="utf-8") as f:
        for n in notes_rows:
            f.write(json.dumps(n) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold_rows:
            f.write(json.dumps(g) + "\n")

    tally = {}
    material_n = 0
    for g in gold_rows:
        for it in g["items"]:
            tally[it["scenario"]] = tally.get(it["scenario"], 0) + 1
            if it["material"]:
                material_n += 1
    cause_tally = {}
    for g in gold_rows:
        for it in g["items"]:
            if it["material"]:
                cause_tally[it["true_cause"]] = cause_tally.get(it["true_cause"], 0) + 1

    print("batches: %d   items: %d   material exceptions: %d" % (
        len(batches), sum(len(b["items"]) for b in batches), material_n))
    print("scenario tally:", tally)
    print("material-exception cause tally:", cause_tally)


if __name__ == "__main__":
    main()
