#!/usr/bin/env python3
"""What you get without a model. Run this BEFORE reading any score this kit produces.

    python3 -m evals.baseline

⚑ THE FLOOR HERE IS NOT A STRAWMAN AND THAT MAKES THIS KIT DIFFERENT FROM ITS SIBLINGS. On most kits the
free baseline is a constant — answer the same thing every time — and it exists to prove the model is
doing something. Here the free answer is a WORKING MATCHER: weighted string similarity with a threshold,
which is what a great many production dedupe systems actually run. So this file does not ask "is the
model better than nothing", it asks "is the model better than the thing you already have", and that is
the only version of the question worth paying to answer.

⚑ FREE IN THE STRICT SENSE. Nothing is sent anywhere. Every number below can be reproduced by anyone
with a clone and no key, as often as they like, which is exactly why they are committed rather than
quoted.

⚠︎ SCORED BY `evals/run.py::score_pair`, UNCHANGED. Same normalisation, same threshold rule, same five
outcomes. A floor with its own scorer is a second opinion.

⚠︎ AND THE THRESHOLD IS SWEPT, NOT CHOSEN. A single threshold would let this file pick the number that
flatters whichever conclusion we wanted; the sweep publishes the whole trade — every setting, its false
merges and its missed matches — so the model has to beat a CURVE rather than one convenient point.

The strategies:

    always-apart      never merge. Banks every different pair for free, and misses every duplicate.
    always-merge      merge everything. Banks every duplicate, and fuses every look-alike.
    similarity        the real free matcher, at nine thresholds.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels, load_records                       # noqa: E402
from evals.run import score_pair, by_trap                                      # noqa: E402
from src import block, decide                                                  # noqa: E402

THRESHOLDS = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)


def run_floor(rows, records, verdict, threshold):
    """One strategy at one threshold, through the real scorer."""
    scored = [score_pair(r, records, verdict, replied=True, threshold=threshold) for r in rows]
    out = decide.tally(scored)
    out["by_trap"] = by_trap(scored)
    return out, scored


def fmt(rate):
    return "  n/a " if rate is None else "%5.1f%%" % (100 * rate)


def main():
    records, labels = load_records(), load_labels()
    cand = set(block.candidates(list(records.values())))
    rows = [p for p in labels if (min(p["a"], p["b"]), max(p["a"], p["b"])) in cand]

    print("FLOORS — %d pairs judged, 0 model calls, $0.00\n" % len(rows))
    out = {"kind": "baseline", "calls": 0, "cost_usd": 0.0,
           "dataset": {"file": "data/labelled.jsonl", "rows": len(rows),
                       "same": sum(1 for r in rows if r["label"] == "same"),
                       "different": sum(1 for r in rows if r["label"] == "different")},
           "blocking": block.stats(list(records.values()), labels),
           "note": "Deterministic matchers scored by evals/run.py::score_pair. No model was called.",
           "floors": {}}

    # The two constants first, because they are the ceiling and floor of doing nothing clever.
    for name, verdict, why in (
        ("always-apart", "DIFFERENT",
         "never merges: perfect precision on an empty numerator, and every duplicate survives"),
        ("always-merge", "SAME",
         "merges everything: perfect recall, and every look-alike is fused"),
    ):
        rec, _ = run_floor(rows, records, verdict, 0.70)
        rec["why"] = why
        out["floors"][name] = rec
        print("  %-14s precision %s  recall %s   false merges %2d   missed %2d"
              % (name, fmt(rec["precision"]), fmt(rec["recall"]),
                 rec["false_merges"], rec["missed_matches"]))
        print("  %-14s %s" % ("", why))
    print()

    # ...then the real free matcher, swept.
    print("  similarity — the free matcher that a threshold turns into a product")
    print("  %-11s %-10s %-9s %-13s %-8s" % ("threshold", "precision", "recall",
                                             "false merges", "missed"))
    sweep = []
    for t in THRESHOLDS:
        rec, scored = run_floor(rows, records, None, t)
        rec["threshold"] = t
        rec["why"] = "weighted string similarity, merge at or above %.2f" % t
        sweep.append(rec)
        print("  %-11.2f %-10s %-9s %-13d %-8d"
              % (t, fmt(rec["precision"]).strip(), fmt(rec["recall"]).strip(),
                 rec["false_merges"], rec["missed_matches"]))
    out["floors"]["similarity_sweep"] = sweep

    # ⚑ THE HEADLINE IS THE BEST HONEST POINT ON THE CURVE, AND "BEST" NEEDS A DEFINITION. Ranking by
    # precision alone would elect a threshold that merges almost nothing; by recall alone, one that
    # merges everything. This picks the highest recall among settings that make NO false merge — the
    # cautious reading a business with un-mergeable records would actually ask for — and says so.
    clean = [r for r in sweep if r["false_merges"] == 0]
    best = max(clean, key=lambda r: (r["recall"] or 0)) if clean else None
    if best:
        out["highest_floor"] = {"rule": "highest recall with zero false merges",
                                "threshold": best["threshold"], "recall": best["recall"],
                                "precision": best["precision"],
                                "missed_matches": best["missed_matches"]}
        print("\nHIGHEST HONEST FLOOR: threshold %.2f — recall %s with ZERO false merges, "
              "%d duplicates missed."
              % (best["threshold"], fmt(best["recall"]).strip(), best["missed_matches"]))
        print("Any model score must be read against this curve, not against zero.")
        worst = max(sweep, key=lambda r: r["false_merges"])
        print("For contrast, threshold %.2f makes %d false merges — the mistake that cannot be undone."
              % (worst["threshold"], worst["false_merges"]))
    else:
        print("\nNo threshold avoided a false merge. That is the finding: this corpus cannot be "
              "deduplicated safely by string similarity at any setting.")

    # Which traps the free matcher cannot do — the gap the model is being asked to close.
    mid, _ = run_floor(rows, records, None, 0.70)
    print("\nWhere the free matcher fails at 0.70 — this is the gap a model has to close:")
    for trap, t in sorted(mid["by_trap"].items(), key=lambda x: -x[1]["wrong"]):
        if t["wrong"]:
            print("  %-16s %d/%d wrong   %s"
                  % (trap, t["wrong"], t["pairs"],
                     ", ".join("%s %d" % kv for kv in sorted(t["outcomes"].items()))))

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", "baseline.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
