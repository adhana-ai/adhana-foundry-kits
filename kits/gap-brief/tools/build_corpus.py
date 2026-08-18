#!/usr/bin/env python3
"""Generate the planning cycles, their three plan views, their planning notes, and the gold gap
list, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/cycles.jsonl, data/notes.jsonl and data/gold.jsonl, byte-identical on every run.
Nothing is fetched and nothing is licensed from anybody: every cycle, category and note line here
is invented, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ WHY THE SCENARIO IS RETAIL S&OP-FLAVORED BUT THE PATTERN ISN'T. The originating atlas row is a
sales-and-operations-planning cycle -- reconciling a demand, supply and financial view of the same
numbers. That is one instance of a generic pattern: three independently-maintained plan views of
the same underlying reality (a budget/forecast/actuals set, a hiring-plan/headcount-budget/actual-
headcount set are others). Retail categories are the flavor of THIS corpus, not a claim about what
the kit is for -- src/segment.py, src/pack.py and src/prompt.py never mention retail or S&OP.

⚑ SEVEN SCENARIOS, EACH PLANTED ON PURPOSE -- same discipline data-reconcile's build_corpus.py
states for its own five checks. A corpus that cannot express a scenario's failure cannot show the
eval earning its keep:

    clean                 all three views agree within ordinary noise. Not itemized.
    timing_lag             one view is stale relative to a change the others reflect. Traceable
                           via two notes lines.
    assumption_mismatch    two views were built on different stated assumptions. Traceable.
    data_entry_error       a transcription/unit mistake moved one view. Traceable.
    scope_mismatch         one view rolls in a sub-line another excludes. Traceable.
    unknown_gap            a real, material gap -- but the notes do not explain it. Untraceable
                           on purpose, to prove the model says 'unknown' rather than guessing.
    missing_view           one of the three views was never submitted this cycle. Material by
                           itself (src/segment.py), cause is 'unknown', no citations -- the
                           mandatory-caveat case.

⚑ NOISE LINES ARE PLANTED TOO. Each cycle's notes log carries several lines that mention a
DIFFERENT item, or mention nothing decision-relevant at all, so a model that cites "the nearest
plausible-looking line" rather than an item-matched one is caught by the citation-fidelity check
in evals/scoring.py -- the substring must be real, but being real is not sufficient on its own for
the item it is cited against, which evals/scoring.py also checks.
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

CATEGORIES = [
    "Trail Footwear", "Packaged Snacks", "Outdoor Apparel", "Camp Cookware", "Hydration Gear",
    "Winter Layers", "Daypacks", "Trail Nutrition", "Base Layers", "Cookset Accessories",
    "Insulated Bottles", "Rain Shells",
]
BUSINESS_UNITS = ["North Region", "South Region", "East Region", "West Region", "Direct-to-Consumer"]
PERIODS = ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]

# Weighted so ~28% of items are clean and the remaining ~72% split across six planted scenarios --
# heavier on planted gaps than a real deployment would likely see, on purpose: an eval corpus that
# is mostly clean teaches a scorer almost nothing about the traceable/untraceable distinction this
# kit exists to get right.
SCENARIOS = ["clean", "timing_lag", "assumption_mismatch", "data_entry_error", "scope_mismatch",
            "unknown_gap", "missing_view"]
WEIGHTS = [0.28, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]

NOISE_LINES = [
    "Reminder: cycle sign-off is due Friday EOD, no exceptions this quarter.",
    "Finance close calendar shifted two days for the holiday -- see the shared calendar invite.",
    "New planner onboarding starts next cycle; expect handoff notes on the shared items.",
    "Warehouse slotting review is a separate meeting, not part of this reconciliation.",
    "Vendor scorecard refresh landed in the shared drive, unrelated to this cycle's numbers.",
    "Please use the new template for next cycle's submission -- old one is deprecated.",
    "IT ticket open for the planning tool's export button; workaround is CSV download.",
    "Regional lead is out next week; route urgent items to the deputy instead.",
]


def _sup_id(i):
    return "GB-%04d" % (1 + i)


def _cost_pair_notes(rng, item_label, cause, off_view, shift_dir):
    """Two verbatim notes lines that together explain `cause` for `item_label`. Phrasing is
    templated with light variation so a checker cannot key off one fixed sentence -- same
    discipline as data-reconcile's clause-variant generator."""
    view_word = {"demand_plan_usd": "demand plan", "supply_plan_usd": "supply plan",
                "financial_plan_usd": "financial plan"}[off_view]
    direction = "up" if shift_dir > 0 else "down"
    if cause == "timing_lag":
        return [
            "%s: the %s hasn't been refreshed since the schedule change went in -- still running "
            "on the prior numbers." % (item_label, view_word),
            "Follow-up on %s -- confirmed the %s update didn't make this cycle's cutoff; expect "
            "it to move %s once it does." % (item_label, view_word, direction),
        ]
    if cause == "assumption_mismatch":
        other = {"demand_plan_usd": "supply", "supply_plan_usd": "demand",
                "financial_plan_usd": "demand"}[off_view]
        return [
            "%s: %s side is modeling this at a different price/promo assumption than %s side "
            "used -- the two aren't reconciled on inputs yet."
            % (item_label, view_word.split()[0], other),
            "Flagging %s -- confirmed the assumption gap on %s is a real difference in what each "
            "side assumed, not a data issue." % (item_label, view_word),
        ]
    if cause == "data_entry_error":
        return [
            "%s: someone caught a likely transcription slip on the %s entry -- value looks "
            "%s off from what the source sheet shows." % (item_label, view_word, direction),
            "Correction thread on %s -- the %s number was carried over wrong; source system "
            "shows a different figure, fix queued for next cycle." % (item_label, view_word),
        ]
    if cause == "scope_mismatch":
        return [
            "%s: the %s is rolling in a sub-line the other views exclude -- that's most of the "
            "gap on this one." % (item_label, view_word),
            "Scope note on %s -- confirmed %s includes an extra sub-item the other two views "
            "were never asked to carry." % (item_label, view_word),
        ]
    return []


def build_items(cycle_i, rng):
    cats = rng.sample(CATEGORIES, k=5)
    items = []
    scenario_notes = []
    for j, cat in enumerate(cats):
        item_id = "IT-%d" % (j + 1)
        item_label = cat
        true_value = round(rng.uniform(15000, 220000), -2)
        scenario = rng.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        views = {}
        missing_view = None
        cause = None
        citations = []

        if scenario == "clean":
            for v in SEG.VIEWS:
                views[v] = round(true_value * rng.uniform(0.97, 1.03), 2)
        elif scenario == "missing_view":
            missing = rng.choice(list(SEG.VIEWS))
            for v in SEG.VIEWS:
                views[v] = None if v == missing else round(true_value * rng.uniform(0.97, 1.03), 2)
            missing_view = missing
            cause = "unknown"
        elif scenario == "unknown_gap":
            off_view = rng.choice(list(SEG.VIEWS))
            shift = rng.choice([-1, 1]) * rng.uniform(0.18, 0.42)
            for v in SEG.VIEWS:
                views[v] = round(true_value * (1 + shift if v == off_view
                                              else rng.uniform(0.97, 1.03)), 2)
            cause = "unknown"
        else:
            off_view = rng.choice(list(SEG.VIEWS))
            shift = rng.choice([-1, 1]) * rng.uniform(0.18, 0.42)
            for v in SEG.VIEWS:
                views[v] = round(true_value * (1 + shift if v == off_view
                                              else rng.uniform(0.97, 1.03)), 2)
            cause = scenario
            citations = _cost_pair_notes(rng, item_label, scenario, off_view, shift)

        item = {"item_id": item_id, "item_label": item_label}
        item.update(views)
        items.append(item)
        scenario_notes.append({
            "item_id": item_id, "item_label": item_label, "scenario": scenario,
            "true_cause": cause, "citations": citations,
        })
    return items, scenario_notes


def build_cycle(i, rng):
    cycle_id = _sup_id(i)
    bu = rng.choice(BUSINESS_UNITS)
    period = rng.choice(PERIODS)
    items, scenario_notes = build_items(i, rng)

    # Assemble the notes log: every scenario's own citation pair (if any), plus noise lines,
    # shuffled together -- order carries no signal, same discipline data-reconcile's shuffled
    # agreement clauses use.
    notes = []
    for sn in scenario_notes:
        notes.extend(sn["citations"])
    n_noise = rng.randint(3, 5)
    notes.extend(rng.sample(NOISE_LINES, k=min(n_noise, len(NOISE_LINES))))
    rng.shuffle(notes)

    cycle = {"cycle_id": cycle_id, "business_unit": bu, "period": period, "items": items}

    gaps = []
    for it, sn in zip(items, scenario_notes):
        fx = SEG.align(it)
        gaps.append({
            "item_id": it["item_id"], "item_label": it["item_label"],
            "scenario": sn["scenario"], "missing_view": fx["missing_view"],
            "delta_usd": fx["delta_usd"], "delta_pct": fx["delta_pct"],
            "material": fx["material"], "true_cause": sn["true_cause"],
            "citations": sn["citations"],
        })
    return cycle, {"cycle_id": cycle_id, "notes": notes}, {"cycle_id": cycle_id, "gaps": gaps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cycles", type=int, default=40)
    args = ap.parse_args()

    rng = random.Random(SEED)
    os.makedirs(DATA, exist_ok=True)

    cycles, notes_rows, gold_rows = [], [], []
    for i in range(args.n_cycles):
        cycle, notes, gold = build_cycle(i, rng)
        cycles.append(cycle)
        notes_rows.append(notes)
        gold_rows.append(gold)

    with open(os.path.join(DATA, "cycles.jsonl"), "w", encoding="utf-8") as f:
        for c in cycles:
            f.write(json.dumps(c) + "\n")
    with open(os.path.join(DATA, "notes.jsonl"), "w", encoding="utf-8") as f:
        for n in notes_rows:
            f.write(json.dumps(n) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold_rows:
            f.write(json.dumps(g) + "\n")

    tally = {}
    material_n = 0
    for g in gold_rows:
        for gap in g["gaps"]:
            tally[gap["scenario"]] = tally.get(gap["scenario"], 0) + 1
            if gap["material"]:
                material_n += 1
    cause_tally = {}
    for g in gold_rows:
        for gap in g["gaps"]:
            if gap["material"]:
                cause_tally[gap["true_cause"]] = cause_tally.get(gap["true_cause"], 0) + 1

    print("cycles: %d   items: %d   material gaps: %d" % (
        len(cycles), sum(len(c["items"]) for c in cycles), material_n))
    print("scenario tally:", tally)
    print("material-gap cause tally:", cause_tally)


if __name__ == "__main__":
    main()
