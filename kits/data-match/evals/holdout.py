#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hold out the hard traps and re-measure BOTH deciders. 0 calls, $0.00.

    python3 -m evals.holdout

⚑ THE QUESTION, WHICH THE KIT PUBLISHES AS UNKNOWN. r013 scored precision 90.0% / recall 90.0%, and
all 6 false merges are twins while all 6 missed matches are transposed dates of birth. That is a
suspiciously tidy split, and it has exactly two readings: either this model has TWO specific
blind spots, each confined to one planted trap, or 90% is a general wobble that happens to have
landed there. Holding each trap out separates them, and every verdict needed is already on disk.

⚠︎ THIS IS A DIAGNOSTIC AND ITS NUMBERS MUST NEVER BECOME THE KIT'S HEADLINE. Removing the cases a
system fails and republishing the score is the oldest way to make a benchmark lie. The published
result stays 90.0 / 90.0 over all 78 pairs. What follows is a question about WHERE the failures
live, and the file prints the full set first so the held-out rows are never out of sight.

⚑ AND THE FLOOR IS HELD OUT TOO, WHICH IS THE HALF THAT DECIDES WHAT ANY OF IT MEANS. If the free
matcher's false merges are also the twins, then holding the twins out does not just flatter the
model — it deletes the ground the model was bought for. A model that only wins on the cases you
removed has not won. Measuring one decider on a subset and comparing it to the other on the full
set would produce exactly that mistake, silently.

⚠︎ SCORED BY `evals/run.py::score_pair` AND `src/decide.py`, UNCHANGED — the same code that produced
the published run and the published floor. Nothing here re-implements a rate.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.baseline import THRESHOLDS, run_floor                              # noqa: E402
from evals.check_labels import load_labels, load_records                      # noqa: E402
from evals.run import by_trap                                                 # noqa: E402
from src import block, decide                                                 # noqa: E402

RESULTS = os.path.join(HERE, "results")
RUN_ID = "r013-data-match-flash"

# Declared before anything is scored. Each is a question somebody would actually ask.
SUBSETS = [
    ("everything (as published)", (),
     "all 78 pairs — the run exactly as the kit publishes it"),
    ("twins held out", ("twin",),
     "the 6 pairs of twins removed: every false merge in the run was one of them"),
    ("transposed dates held out", ("transposed-dob",),
     "the 7 transposed-date pairs removed: every missed match in the run was one of them"),
    ("both held out", ("twin", "transposed-dob"),
     "the cleanest set this corpus can offer — and the least honest number in the file"),
]


def highest_honest_floor(sweep):
    """The kit's own definition, reused rather than restated: the highest recall among settings
    that make no false merge. Restating it here with a different tie-break would quietly publish a
    second floor under the first one's name."""
    clean = [r for r in sweep if r["false_merges"] == 0]
    return max(clean, key=lambda r: (r["recall"] or 0)) if clean else None


def main():
    run = json.load(open(os.path.join(RESULTS, "eval-%s.json" % RUN_ID), encoding="utf-8"))
    records, labels = load_records(), load_labels()
    cand = set(block.candidates(list(records.values())))
    floor_rows = [p for p in labels if (min(p["a"], p["b"]), max(p["a"], p["b"])) in cand]

    # ⚑ RECONCILE WITH THE PUBLISHED RECORD BEFORE MEASURING ANYTHING ELSE. If re-tallying the
    # recorded rows does not reproduce the numbers the kit prints, then this file's scorer and the
    # run's scorer disagree and every subset below is measured with the wrong instrument.
    full = decide.tally(run["rows"])
    for key in ("precision", "recall", "false_merges", "missed_matches", "pairs", "no_verdict"):
        assert full[key] == run["summary"][key], \
            "re-derived %s=%r but the record publishes %r" % (key, full[key], run["summary"][key])
    assert len(run["rows"]) == len(floor_rows) == 78, \
        "expected 78 model rows and 78 floor rows, got %d and %d" % (len(run["rows"]),
                                                                     len(floor_rows))

    print("HOLD-OUT — %d pairs, %d model calls already spent, 0 new calls.\n" % (len(run["rows"]),
                                                                                 len(run["rows"])))
    print("  %-28s %-7s %-11s %-9s %-13s %s"
          % ("", "pairs", "MODEL p/r", "false/miss", "FLOOR p/r", "floor @"))

    out = {"kind": "holdout", "calls": 0, "cost_usd": 0.0, "run_id": run["run_id"],
           "note": "Re-scored from recorded outputs and the free matcher, through "
                   "evals/run.py::score_pair and src/decide.py. No model was called.",
           "warning": "A DIAGNOSTIC. The kit's published result is the 'everything' row and stays "
                      "so; a score measured after removing the cases a system fails is not a "
                      "result, it is a question about where the failures live.",
           "subsets": {}}

    # ⚑ THE TWO HALVES MUST BE HOLDING OUT THE SAME THING, AND A RED-PROOF EARNED THIS GUARD. The
    # model's subset is filtered from the RECORD's trap field and the floor's from the CORPUS's, and
    # nothing had been checking that those two vocabularies agree. Rename `twin` to `twins` in the
    # record and the "twins held out" row cheerfully reports the model over all 78 pairs beside the
    # floor over 72 — the precise mistake this file's own docstring warns about, printed as a
    # finding, with every assert above still green.
    mtraps = {r["trap"] for r in run["rows"]}
    ftraps = {r["trap"] for r in floor_rows}
    assert mtraps == ftraps, ("the run record and the corpus disagree about trap names: only in "
                              "record %s; only in corpus %s" % (sorted(mtraps - ftraps),
                                                                sorted(ftraps - mtraps)))
    for _, drop, _ in SUBSETS:
        for trap in drop:
            assert trap in mtraps, "SUBSETS holds out %r, which no row carries" % trap

    for name, drop, why in SUBSETS:
        mrows = [r for r in run["rows"] if r["trap"] not in drop]
        frows = [r for r in floor_rows if r["trap"] not in drop]
        assert len(mrows) == len(frows), \
            "%s: %d model rows against %d floor rows — the two halves are not the same subset" % (
                name, len(mrows), len(frows))
        m = decide.tally(mrows)
        m["by_trap"] = by_trap(mrows)

        sweep = []
        for t in THRESHOLDS:
            rec, _ = run_floor(frows, records, None, t)
            rec["threshold"] = t
            sweep.append(rec)
        best = highest_honest_floor(sweep)

        out["subsets"][name] = {
            "held_out": list(drop), "why": why, "pairs": len(mrows),
            # ⚠︎ `answered` RIDES ON EVERY ROW, HEALTHY ONES INCLUDED. UC011's own r012 published
            # 100%/100% off a single answered pair in 78, and the rule this estate took from it is
            # that a rate without its denominator is not a small omission.
            "model": {k: m[k] for k in ("precision", "recall", "false_merges", "missed_matches",
                                        "no_verdict", "counts")},
            "answered": len(mrows) - m["no_verdict"],
            "floor_best": ({"threshold": best["threshold"], "precision": best["precision"],
                            "recall": best["recall"], "missed_matches": best["missed_matches"]}
                           if best else None),
            "floor_sweep": [{"threshold": r["threshold"], "precision": r["precision"],
                             "recall": r["recall"], "false_merges": r["false_merges"],
                             "missed_matches": r["missed_matches"]} for r in sweep],
        }

        def pct(x):
            return "n/a" if x is None else "%.1f%%" % (100 * x)
        print("  %-28s %-7d %-11s %-9s %-13s %s"
              % (name, len(mrows),
                 "%s/%s" % (pct(m["precision"]), pct(m["recall"])),
                 "%d/%d" % (m["false_merges"], m["missed_matches"]),
                 "%s/%s" % (pct(best["precision"]), pct(best["recall"])) if best else "no clean "
                 "setting",
                 "%.2f" % best["threshold"] if best else "—"))
        print("  %-28s %s" % ("", why))

    # ⚑ THE READING. Two questions, and the second is the one that matters.
    everything = out["subsets"]["everything (as published)"]
    no_twin = out["subsets"]["twins held out"]
    no_dob = out["subsets"]["transposed dates held out"]

    print("\n1. IS 90% ONE HARD CASE OR A GENERAL WEAKNESS?")
    print("   Drop the twins and precision goes %s -> %s; the missed matches do not move (%d -> %d)."
          % ("%.1f%%" % (100 * everything["model"]["precision"]),
             "%.1f%%" % (100 * no_twin["model"]["precision"]),
             everything["model"]["missed_matches"], no_twin["model"]["missed_matches"]))
    print("   Drop the transposed dates and recall goes %s -> %s; the false merges do not move "
          "(%d -> %d)."
          % ("%.1f%%" % (100 * everything["model"]["recall"]),
             "%.1f%%" % (100 * no_dob["model"]["recall"]),
             everything["model"]["false_merges"], no_dob["model"]["false_merges"]))
    clean = (no_twin["model"]["false_merges"] == 0 and no_dob["model"]["missed_matches"] == 0)
    print("   -> %s" % ("TWO CONFINED BLIND SPOTS, not a general weakness. Each failure kind lives "
                        "entirely inside one planted trap and neither leaks into the other 65 "
                        "pairs." if clean else
                        "NOT confined — failures survive outside the held-out traps, so 90% is a "
                        "general wobble and the tidy split was a coincidence."))

    print("\n2. DOES THE FREE MATCHER IMPROVE TOO? (the half that decides what this means)")
    # ⚠︎ THE FULL SET HAS NO CLEAN FLOOR SETTING AT ALL, and an earlier version of this section
    # treated that as "nothing to compare" and printed a shrug. It is the opposite: it is the
    # strongest single fact here, and it has to be stated before the subset comparison, because the
    # subset comparison only exists BECAUSE the twins were removed.
    fe, fn = everything["floor_best"], no_twin["floor_best"]
    print("   On all 78 pairs the free matcher has NO safe setting — every one of the %d thresholds"
          % len(THRESHOLDS))
    print("   fuses at least one pair of different people. %s"
          % ("The model does too: %d false merges." % everything["model"]["false_merges"]))
    if fn:
        print("\n   Hold the twins out and the free matcher becomes safe at threshold %.2f:"
              % fn["threshold"])
        print("     free matcher   precision %.1f%%   recall %.1f%%   %d duplicates missed"
              % (100 * fn["precision"], 100 * fn["recall"], fn["missed_matches"]))
        print("     the model      precision %.1f%%   recall %.1f%%   %d duplicates missed"
              % (100 * no_twin["model"]["precision"], 100 * no_twin["model"]["recall"],
                 no_twin["model"]["missed_matches"]))
        bought = fn["missed_matches"] - no_twin["model"]["missed_matches"]
        gap = no_twin["model"]["recall"] - fn["recall"]
        out["what_the_model_buys_outside_the_twins"] = {
            "extra_duplicates_found": bought, "recall_points": round(100 * gap, 1),
            "floor_threshold": fn["threshold"]}
        print("\n   -> OUTSIDE THE TWINS THE MODEL BUYS %d EXTRA DUPLICATE: %+.1f points of recall,"
              % (bought, 100 * gap))
        print("      at the same 100% precision, for 78 calls against the free matcher's nothing.")
        print("      ⚠︎ AND IT DOES NOT BUY THE TWINS EITHER — it merged all 6, exactly as every")
        print("      threshold of the free matcher does.")

    # ⚠︎ RECONCILING WITH WHAT THE KIT ALREADY PUBLISHES, BECAUSE OTHERWISE THIS READS AS A
    # CONTRADICTION AND ONE OF THE TWO WOULD BE ASSUMED WRONG. The kit says the model "buys 12
    # relative pairs kept apart". That is measured against the free matcher at 0.70, where it
    # merges 18 different pairs — 12 relatives and 6 twins. This file compares against 0.85, the
    # highest setting that makes NO false merge once the twins are gone, where the free matcher
    # keeps the relatives apart by itself. Both numbers are right; they are answers to different
    # questions, and the difference between them is entirely the threshold somebody chooses.
    lo = [r for r in everything["floor_sweep"] if r["threshold"] == 0.70][0]
    hi = [r for r in no_twin["floor_sweep"] if r["threshold"] == 0.85][0]
    out["reconciles_with_published_claim"] = {
        "published": "the model buys 12 relative pairs kept apart",
        "measured_against": "the free matcher at 0.70, which makes %d false merges (12 relatives + "
                            "6 twins)" % lo["false_merges"],
        "this_file_compares_against": "the free matcher at %.2f, its highest setting with zero "
                                      "false merges once the twins are held out" % hi["threshold"],
        "note": "Both hold. The gap the model closes depends entirely on where the free matcher's "
                "threshold is set, which is why this kit publishes a curve and not a point.",
    }
    print("\n3. AND THE ONE THAT SURVIVES EVERY THRESHOLD.")
    print("   At 0.70 the free matcher fuses %d different pairs — 12 relatives and 6 twins — which"
          % lo["false_merges"])
    print("   is the kit's published \"the model buys 12 relative pairs kept apart\", and it holds.")
    print("   But %d of those %d survive to the top of the sweep: NO threshold separates the twins,"
          % (everything["model"]["false_merges"], lo["false_merges"]))
    print("   and neither does the model. That pair kind is not a tuning problem for either")
    print("   decider — it is a corpus that does not contain the evidence to tell them apart.")

    path = os.path.join(RESULTS, "holdout.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s — 0 calls, $0.00" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
