#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-cut the stream at 10 and 15 minutes and re-score THE FLOOR. 0 calls, $0.00.

    python3 -m evals.recut

⚑ THE QUESTION THE KIT ASKS IN FOUR PLACES AND ANSWERS IN NONE. Every page on this kit says the
five-minute bucket is a product decision. Nothing measures how much of the score it is — so the one
knob the kit tells a reader they own is the one it never priced. This file prices it, for nothing,
because the floor calls no model.

⚠︎ THE MODEL HALF IS NOT RE-SCORED AND CANNOT BE. r014's 123 verdicts were reached on five-minute
windows; a ten-minute window is a different question with different evidence in it, and feeding a
verdict about one to a scorer about the other would be publishing a number under a shape it never
saw. `window_seconds` rides on the record as a comparability guard for exactly this reason. Pricing
the model half needs a second run and is not bought.

⚑ WHAT ACTUALLY CHANGES WHEN THE BUCKET GROWS, AND IT IS NOT ONLY THE ARITHMETIC. Three things move
at once and separating them is most of the work here:

    the labels     a coarse window inherits `page` if ANY five-minute window inside it pages
    the evidence   the same lines land in fewer, fuller buckets — a burst that filled one window
                   now shares a window with the calm either side of it
    the history    `gone_silent` reads back HISTORY *windows*, which is thirty minutes at a
                   five-minute cut and an hour at ten. "The same rule" stops being one thing.

⚠︎ THE LABEL RULE IS A CHOICE AND IT FAVOURS DETECTION. "Page if any constituent pages" makes
coarser windows likelier to be pages, which raises the base rate mechanically — 8% of windows are
incidents at five minutes and more than that at fifteen. So raw counts are NOT comparable across
cuts and are printed only beside their denominators. **The comparable numbers are the two rates**,
and the file leads with them.

⚠︎ AND THE HISTORY IS MEASURED BOTH WAYS, because there is no neutral answer. Holding the window
count fixed keeps the code identical and quietly doubles the wall-clock an outage can hide in;
holding the wall-clock fixed keeps the operator's meaning ("look back half an hour") and changes
the code. Publishing one silently would be choosing for the reader.

⚠︎ SCORED BY `src/rules.py`, `src/window.py` AND `src/decide.py`, UNCHANGED — the same modules that
produced the published floor. Only `WINDOW_S` is patched, and it is restored in a `finally`.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.baseline import THRESHOLDS, TRAPS, floor_rows, handled              # noqa: E402
from evals.check_labels import load_windows                                    # noqa: E402
from src import decide, window as W                                            # noqa: E402

RESULTS = os.path.join(HERE, "results")
CUTS = (300, 600, 900)          # five minutes (the published cut), ten, fifteen
BASE_S = 300
HISTORY_MINUTES = 30            # what HISTORY=6 means at the published cut


def recut(seconds, labels_5m):
    """The stream at `seconds`, with labels aggregated up from the five-minute ones.

    ⚠︎ `WINDOW_S` IS READ BY BOTH `index_of` AND `cut`, so it is patched rather than passed. Restored
    in a finally: leaving it changed would silently re-cut every later caller in the process,
    including the control row this file compares against.
    """
    k = seconds // BASE_S
    real = W.WINDOW_S
    try:
        W.WINDOW_S = seconds
        windows = W.cut(W.load_events())
    finally:
        W.WINDOW_S = real

    # A coarse window pages if any five-minute window inside it pages. Its trap is the trap of the
    # first constituent that pages — a coarse window can swallow two different incidents, and
    # naming it after the first one that fired is the only choice that keeps `by_trap` meaningful.
    agg = {}
    for i, lab in enumerate(labels_5m):
        j = i // k
        cur = agg.setdefault(j, {"id": "w%03d" % j, "label": "hold", "trap": "quiet",
                                 "silent_service": None, "merged_from": 0})
        cur["merged_from"] += 1
        if lab["label"] == "page" and cur["label"] != "page":
            cur["label"] = "page"
            cur["trap"] = lab["trap"]
            cur["silent_service"] = lab.get("silent_service")
    labels = [agg[j] for j in sorted(agg) if j < len(windows)]
    return windows, labels


def best_setting(rows_by_threshold):
    """The kit's own definition, reused: among settings that make NO false page, the one that
    misses fewest incidents. Ranking by detection alone would elect "page everything"."""
    clean = [r for r in rows_by_threshold if r["tally"]["false_pages"] == 0]
    pool = clean or rows_by_threshold
    return min(pool, key=lambda r: (r["tally"]["missed_incidents"],
                                    -(r["tally"]["detection"] or 0)))


def main():
    _, labels_5m = load_windows()
    out = {"kind": "recut", "calls": 0, "cost_usd": 0.0,
           "note": "The FLOOR only, re-cut and re-scored through src/rules.py and src/decide.py. "
                   "No model was called. r014's verdicts are not transferable to another cut.",
           "label_rule": "a coarse window pages if any five-minute window inside it pages",
           "history_measured": ["fixed window count (code identical)",
                                "fixed wall clock (operator's meaning)"],
           "cuts": {}}

    print("RE-CUT — the free floor at three bucket sizes, 0 model calls, $0.00.\n")
    print("  %-16s %-9s %-7s %-11s %-11s %-8s %s"
          % ("cut / history", "windows", "pages", "detection", "precision", "missed",
             "traps clean"))

    for seconds in CUTS:
        windows, labels = recut(seconds, labels_5m)
        n_hist_fixed = W.HISTORY                              # same number of windows
        n_hist_clock = max(1, (HISTORY_MINUTES * 60) // seconds)   # same wall clock
        row = {"window_seconds": seconds, "windows": len(windows),
               "page_windows": sum(1 for l in labels if l["label"] == "page"),
               "history": {}}

        for hname, hist in (("fixed window count", n_hist_fixed),
                            ("fixed wall clock", n_hist_clock)):
            real = W.WINDOW_S
            try:
                W.WINDOW_S = seconds
                swept = []
                for t in THRESHOLDS:
                    # ⚠︎ `use_absence=False` IS LOAD-BEARING AND THE FIRST VERSION HAD IT TRUE.
                    # `floor_rows` applies the absence rule with the DEFAULT history (6 windows),
                    # and this loop can only turn HOLD into PAGE — never back. So a shorter history
                    # could add silences to the default's result but never withdraw one, and both
                    # history settings printed the same numbers at every cut. Two settings with
                    # different logic producing identical output is the tell this estate has paid
                    # for before; the absence pass is applied ONCE here, with the history under
                    # test, over a floor that has not already had one.
                    rows = floor_rows(windows, labels, t, use_absence=False)
                    idx = {w["id"]: i for i, w in enumerate(windows)}
                    for r in rows:
                        silent = W.gone_silent(windows, idx[r["id"]], history=hist)
                        if silent and r["verdict"] == decide.HOLD:
                            r["verdict"] = decide.PAGE
                            r["reasons"] = r.get("reasons", []) + [
                                "silent: %s" % ", ".join(silent)]
                        r["outcome"] = decide.outcome(r["label"], r["verdict"], True)
                    swept.append({"threshold": t, "tally": decide.tally(rows),
                                  "handled": handled(rows)})
            finally:
                W.WINDOW_S = real

            b = best_setting(swept)
            row["history"][hname] = {
                "history_windows": hist,
                "history_minutes": hist * seconds // 60,
                "best": {"threshold": b["threshold"], "handled": b["handled"],
                         **{k: b["tally"][k] for k in ("detection", "page_precision",
                                                       "missed_incidents", "false_pages",
                                                       "windows")}},
                "sweep": [{"threshold": s["threshold"],
                           "detection": s["tally"]["detection"],
                           "page_precision": s["tally"]["page_precision"],
                           "missed_incidents": s["tally"]["missed_incidents"],
                           "false_pages": s["tally"]["false_pages"]} for s in swept],
            }

        out["cuts"]["%ds" % seconds] = row
        for hname in ("fixed window count", "fixed wall clock"):
            b = row["history"][hname]["best"]
            h = row["history"][hname]
            print("  %-16s %-9d %-7d %-11s %-11s %-8d %s"
                  % ("%d min / %d min back" % (seconds // 60, h["history_minutes"]),
                     row["windows"], row["page_windows"],
                     "%.1f%%" % (100 * b["detection"]) if b["detection"] is not None else "n/a",
                     "%.1f%%" % (100 * b["page_precision"]) if b["page_precision"] is not None
                     else "n/a",
                     b["missed_incidents"], ", ".join(b["handled"]) or "none"))

    # ⚑ THE READING. The kit's claim is that the bucket is a product decision; this says what the
    # decision costs, in the two numbers the kit publishes and refuses to average.
    five = out["cuts"]["300s"]["history"]["fixed window count"]["best"]

    # ⚑ THE CONTROL ROW MUST BE THE PUBLISHED FLOOR, OR NONE OF THE OTHERS MEAN ANYTHING. At 300s
    # with history 6 this file is re-running the exact configuration `results/baseline.json`
    # already recorded, so it has to land on the same numbers. If it does not, the re-cut machinery
    # is changing something at the published setting too, and every delta below is measured against
    # a floor that never shipped.
    pub = json.load(open(os.path.join(RESULTS, "baseline.json"), encoding="utf-8"))["claim"]["best"]
    for key in ("threshold", "missed_incidents", "false_pages"):
        assert five[key] == pub[key], (
            "the 300s control re-derived %s=%r but results/baseline.json publishes %r — the re-cut "
            "is altering the published setting" % (key, five[key], pub[key]))
    out["control_reconciles_with_baseline"] = True

    print("\nWHAT THE BUCKET SIZE IS WORTH, AGAINST THE PUBLISHED FIVE-MINUTE CUT:")
    for seconds in CUTS[1:]:
        for hname in ("fixed window count", "fixed wall clock"):
            b = out["cuts"]["%ds" % seconds]["history"][hname]["best"]
            d = (b["detection"] or 0) - (five["detection"] or 0)
            p = (b["page_precision"] or 0) - (five["page_precision"] or 0)
            print("  %2d min, history by %-12s detection %+.1f pts, page precision %+.1f pts"
                  % (seconds // 60, hname.split()[-1], 100 * d, 100 * p))
    out["published_five_minute_best"] = five

    # ⚑ AND THE TRAP THAT SHOULD MOVE MOST, NAMED IN ADVANCE OF LOOKING. `silence` is the one trap
    # whose signal is an absence, so it is the one a bigger bucket should damage first: a service
    # quiet for five minutes inside a fifteen-minute window is no longer quiet for the whole window.
    # If it survives unchanged, the bucket is doing less than the kit implies.
    print("\nTHE TRAP NAMED IN ADVANCE — `silence`, whose signal is an absence:")
    for seconds in CUTS:
        b = out["cuts"]["%ds" % seconds]["history"]["fixed wall clock"]["best"]
        print("  %2d min: %s" % (seconds // 60,
                                 "handled" if "silence" in b["handled"] else "NOT handled"))

    # ⚑ WHY THE TWO HISTORY COLUMNS ARE IDENTICAL, MEASURED RATHER THAN EXPLAINED AWAY. Two settings
    # with different logic printing the same number is the tell that cost this estate a bug once
    # already, so it is checked instead of trusted: the absence rule simply stops FIRING as the
    # bucket grows, and a parameter controlling how far back a dead rule looks changes nothing.
    # A service that goes quiet for five minutes still logs in the other half of a ten-minute
    # window, so `gone_silent` never sees an absence to read history about.
    print("\nWHY THE TWO HISTORY ROWS AGREE — the absence rule stops firing, so its history is inert:")
    fires = {}
    for seconds in CUTS:
        windows, labels = recut(seconds, labels_5m)
        real = W.WINDOW_S
        try:
            W.WINDOW_S = seconds
            n_clock = max(1, (HISTORY_MINUTES * 60) // seconds)
            fired = sum(1 for i in range(len(windows))
                        if W.gone_silent(windows, i, history=n_clock))
        finally:
            W.WINDOW_S = real
        labelled = sum(1 for l in labels if l["trap"] == "silence")
        fires["%ds" % seconds] = {"absence_rule_fires_on": fired,
                                  "labelled_silence_windows": labelled}
        print("  %2d min: the rule fires on %d window(s); %d window(s) are labelled `silence`"
              % (seconds // 60, fired, labelled))
    out["absence_rule_by_cut"] = fires
    print("  -> The bucket does not merely blunt the absence signal, it DELETES it. At 15 minutes")
    print("     the rule fires zero times, so the one trap this kit was built around — a service")
    print("     that stops talking — is undetectable before any model is asked. That is the price")
    print("     of the knob the kit tells its reader they own.")

    path = os.path.join(RESULTS, "recut.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s — 0 calls, $0.00" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
